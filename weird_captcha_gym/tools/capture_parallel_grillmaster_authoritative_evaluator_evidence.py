#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENV_ROOT = BENCHMARK / "environments" / "parallel_grillmaster_env"
MATERIALIZER = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
EVALUATOR = BENCHMARK / "tools" / "run_realtime_evaluation.py"
TASK_ID = "parallel_grillmaster_d2_full_seed_0001"
SEED = 271828


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run live and paused Parallel Grillmaster episodes through the "
            "authoritative evaluator and preserve its delivered observations."
        )
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected an object in {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def relative(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def build_runtime_environment(temp_root: Path, out_dir: Path) -> Path:
    materialized_root = temp_root / "materialized"
    subprocess.run(
        [
            sys.executable,
            str(MATERIALIZER),
            "--environment",
            ENV_ROOT.name,
            "--output-root",
            str(materialized_root),
        ],
        cwd=ROOT,
        check=True,
    )
    runtime_benchmark = (
        temp_root / "weird_captcha_gym"
    )
    runtime_env = (
        runtime_benchmark
        / "environments"
        / ENV_ROOT.name
    )
    runtime_env.mkdir(parents=True)
    shutil.copytree(
        BENCHMARK / "shared_runtime",
        runtime_benchmark / "shared_runtime",
    )
    shutil.copytree(
        materialized_root / ENV_ROOT.name / "tasks",
        runtime_env / "tasks",
    )
    config = read_json(ENV_ROOT / "env.json")
    config["recording"]["output_dir"] = str(
        (out_dir / "raw_episodes").resolve()
    )
    for mount in config["mounts"]:
        if mount["target"] == "/workspace/tasks":
            mount["source"] = str((runtime_env / "tasks").resolve())
    (runtime_env / "env.json").write_text(
        json.dumps(config, indent=2) + "\n",
        encoding="utf-8",
    )
    return runtime_env


def run_mode(mode: str, runtime_env: Path, out_dir: Path) -> dict[str, Any]:
    mode_dir = out_dir / mode
    mode_dir.mkdir(parents=True, exist_ok=True)
    episode_summary_path = mode_dir / "episode-summary.json"
    agent_args = {
        "transient_timeout_attempts": 1,
        "inference_timeout_seconds": 10,
        "drag_start": [546, 400],
        "drag_end": [990, 510],
    }
    command = [
        sys.executable,
        "-B",
        str(EVALUATOR),
        "--env-dir",
        str(runtime_env),
        "--task",
        TASK_ID,
        "--agent",
        "AuthoritativeObservationProbeAgent",
        "--agent-args",
        json.dumps(agent_args, separators=(",", ":")),
        "--time-mode",
        mode,
        "--seed",
        str(SEED),
        "--steps",
        "3",
        "--request-timeout-seconds",
        "15",
        "--request-attempts",
        "2",
        "--episode-summary-path",
        str(episode_summary_path),
    ]
    (mode_dir / "run-command.json").write_text(
        json.dumps(
            {
                "argv": command,
                "agent_args": agent_args,
                "purpose": (
                    "transport/timing evidence probe; not a benchmark "
                    "capability evaluation"
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    (mode_dir / "evaluator.log").write_text(
        completed.stdout + completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"{mode} evaluator exited {completed.returncode}; "
            f"see {mode_dir / 'evaluator.log'}"
        )

    episode_summary = read_json(episode_summary_path)
    episode_dir = Path(episode_summary["episode_dir"]).resolve()
    timing = read_jsonl(episode_dir / "realtime_timing.jsonl")
    model_inputs = read_jsonl(episode_dir / "model_input_manifest.jsonl")
    current_task = read_json(episode_dir / "current_task.json")
    public_state = read_json(episode_dir / "public_state.json")
    witness_ledger = read_json(
        episode_dir / "parallel_grillmaster_witness_ledger.json"
    )

    observations = []
    observation_root = episode_dir / "observations"
    for turn_dir in sorted(observation_root.glob("turn-*")):
        manifest_path = turn_dir / "guest-capture-manifest.json"
        manifest = read_json(manifest_path)
        frames = []
        for index, frame in enumerate(manifest["frames"]):
            path = turn_dir / f"frame-{index:03d}.png"
            frames.append(
                {
                    "path": relative(path, out_dir),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "offset_ms": frame["offset_ms"],
                    "target_offset_ms": frame["target_offset_ms"],
                }
            )
        if len(frames) != 6:
            raise AssertionError(f"{mode}: expected six delivered frames")
        observations.append(
            {
                "turn": turn_dir.name,
                "guest_capture_manifest": relative(
                    manifest_path,
                    out_dir,
                ),
                "frames": frames,
                "screen": frames[-1]["path"],
                "screen_is_final_frame": True,
                "time_status": manifest["time_status"],
                "distinct_frame_hashes": len(
                    {frame["sha256"] for frame in frames}
                ),
            }
        )
    if len(observations) < 2:
        raise AssertionError(f"{mode}: action was not followed by observation")

    turn_records = [row for row in timing if row.get("event") == "turn"]
    first_turn = turn_records[0]
    attempts = first_turn["request_attempts"]
    if [row["outcome"] for row in attempts] != ["error", "success"]:
        raise AssertionError(f"{mode}: transient inference retry is missing")
    if attempts[0].get("error_type") != "TimeoutError":
        raise AssertionError(f"{mode}: first request was not a timeout")
    if not first_turn.get("actions"):
        raise AssertionError(f"{mode}: evaluator applied no visible action")
    action = first_turn["actions"][0]
    if action["task_time_delta_during_action_ms"] <= 0:
        raise AssertionError(f"{mode}: action did not run task time")
    if mode == "paused":
        if any(
            abs(float(item["task_time_delta_ms"])) > 5
            for item in attempts
        ):
            raise AssertionError(
                "paused task time advanced during inference or retry"
            )
        if action["clock_after_action"].get("state") != "paused":
            raise AssertionError("paused action did not return to pause")
    else:
        if sum(
            float(item["task_time_delta_ms"]) for item in attempts
        ) <= 20:
            raise AssertionError("live task time did not advance during inference")

    if len(model_inputs) < 3:
        raise AssertionError(f"{mode}: model input records are incomplete")
    for model_input in model_inputs:
        if (
            model_input.get("frame_count") != 6
            or model_input.get("screen_is_last_frame") is not True
        ):
            raise AssertionError(
                f"{mode}: model did not record the six-frame observation"
            )
    actions = witness_ledger.get("actions") or []
    if (
        len(actions) != 1
        or actions[0].get("input_source") != "food_drag"
        or actions[0].get("event_surface") != "pointer_drag"
    ):
        raise AssertionError(
            f"{mode}: server did not witness the evaluator's drag"
        )

    return {
        "mode": mode,
        "episode_dir": relative(episode_dir, out_dir),
        "episode_summary": relative(episode_summary_path, out_dir),
        "task_id": TASK_ID,
        "seed": SEED,
        "task_seed": current_task["seed"],
        "challenge_id": public_state["challenge_id"],
        "mechanic_id": public_state["mechanic_id"],
        "controlled_condition": public_state["control_condition"],
        "observations": observations,
        "model_input_manifest": relative(
            episode_dir / "model_input_manifest.jsonl",
            out_dir,
        ),
        "realtime_timing": relative(
            episode_dir / "realtime_timing.jsonl",
            out_dir,
        ),
        "first_model_request_attempts": attempts,
        "action": action,
        "server_witness_ledger": relative(
            episode_dir / "parallel_grillmaster_witness_ledger.json",
            out_dir,
        ),
        "server_witness_action": actions[0],
        "screen_is_final_frame_for_all_requests": True,
        "actual_inference_backend": "Tesseract 5 LSTM OCR",
        "evidence_boundary": (
            "This local vision policy audits the authoritative evaluator "
            "transport, request timing, retry, and action cycle. It is not a "
            "human or general computer-use-agent performance result."
        ),
    }


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    tesseract_version = subprocess.check_output(
        ["tesseract", "--version"],
        text=True,
        stderr=subprocess.STDOUT,
    )
    (out_dir / "tesseract-version.txt").write_text(
        tesseract_version,
        encoding="utf-8",
    )
    with tempfile.TemporaryDirectory(
        prefix="parallel-grillmaster-authoritative-"
    ) as temp:
        runtime_env = build_runtime_environment(Path(temp), out_dir)
        live = run_mode("live", runtime_env, out_dir)
        paused = run_mode("paused", runtime_env, out_dir)

    if (
        live["task_id"] != paused["task_id"]
        or live["seed"] != paused["seed"]
        or live["task_seed"] != paused["task_seed"]
        or live["challenge_id"] != paused["challenge_id"]
        or live["controlled_condition"] != paused["controlled_condition"]
    ):
        raise AssertionError(
            "authoritative live and paused episodes did not share a world"
        )
    summary = {
        "ok": True,
        "same_controlled_task_seed_interaction_and_world": True,
        "task_id": TASK_ID,
        "seed": SEED,
        "settings": {
            "play_time_seconds": 120,
            "observation_window_ms": 800,
            "frames_per_observation": 6,
            "request_timeout_seconds": 15,
            "request_attempts": 2,
        },
        "live": live,
        "paused": paused,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
