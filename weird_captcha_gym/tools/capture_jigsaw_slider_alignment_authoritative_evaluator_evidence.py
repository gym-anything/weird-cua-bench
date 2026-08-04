#!/usr/bin/env python3
"""Preserve evaluator-delivered live and paused observations for Jigsaw Alignment."""

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
BENCH = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCH / "environments" / "jigsaw_slider_alignment_env"
MATERIALIZER = BENCH / "tools" / "materialize_controlled_tasks.py"
EVALUATOR = BENCH / "tools" / "run_realtime_evaluation.py"
TASK_ID = "jigsaw_slider_alignment_d4_full_seed_0001"
SEED = 271828


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ENVIRONMENT / "evidence_docs" / "authoritative_evaluator")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected an object in {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def build_runtime_environment(temporary: Path, out_dir: Path) -> Path:
    materialized = temporary / "materialized"
    subprocess.run(
        [sys.executable, "-B", str(MATERIALIZER), "--environment", ENVIRONMENT.name, "--output-root", str(materialized)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    runtime_bench = temporary / "weird_captcha_gym"
    runtime_env = runtime_bench / "environments" / ENVIRONMENT.name
    runtime_env.mkdir(parents=True)
    shutil.copytree(BENCH / "shared_runtime", runtime_bench / "shared_runtime")
    shutil.copytree(materialized / ENVIRONMENT.name / "tasks", runtime_env / "tasks")
    config = read_json(ENVIRONMENT / "env.json")
    config["recording"]["output_dir"] = str((out_dir / "raw_episodes_1280").resolve())
    for mount in config["mounts"]:
        if mount.get("target") == "/workspace/tasks":
            mount["source"] = str((runtime_env / "tasks").resolve())
    (runtime_env / "env.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return runtime_env


def observation_records(episode_dir: Path, out_dir: Path, mode: str, expected_frames: int) -> list[dict[str, Any]]:
    records = []
    for turn_dir in sorted((episode_dir / "observations").glob("turn-*")):
        manifest_path = turn_dir / "guest-capture-manifest.json"
        manifest = read_json(manifest_path)
        frames = []
        for index, item in enumerate(manifest["frames"]):
            path = turn_dir / f"frame-{index:03d}.png"
            frames.append({
                "path": relative(path, out_dir),
                "sha256": sha256(path),
                "offset_ms": item["offset_ms"],
                "target_offset_ms": item["target_offset_ms"],
            })
        if len(frames) != expected_frames:
            raise AssertionError(f"{mode} {turn_dir.name}: expected {expected_frames} frames, got {len(frames)}")
        records.append({
            "turn": turn_dir.name,
            "guest_capture_manifest": relative(manifest_path, out_dir),
            "frames": frames,
            "screen": frames[-1]["path"],
            "screen_is_final_frame": True,
            "time_status": manifest["time_status"],
            "distinct_frame_hashes": len({frame["sha256"] for frame in frames}),
        })
    if len(records) < 2:
        raise AssertionError(f"{mode}: expected an initial and post-action observation")
    return records


def run_mode(mode: str, runtime_env: Path, out_dir: Path, settings: dict[str, int]) -> dict[str, Any]:
    mode_dir = out_dir / mode
    mode_dir.mkdir(parents=True, exist_ok=True)
    episode_summary_path = mode_dir / "episode-summary.json"
    # At the preserved 1280x720 benchmark viewport these coordinates target
    # the visible +15 degree orientation button. The action is intentionally
    # incomplete: this is an observation-transport and timing probe, not a solver.
    visible_action = [
        {"mouse": {"move": [1160, 194]}},
        {"mouse": {"buttons": {"left_down": True}}},
        {"action": "wait", "time": 0.12},
        {"mouse": {"buttons": {"left_up": True}}},
    ]
    agent_args = {
        "transient_timeout_attempts": 1,
        "inference_timeout_seconds": 10,
        "expected_text_markers": ["PARALLAX", "CALIBRATE", "OPTICAL"],
        "decision_label": "press_visible_orientation_plus_button",
        "actions": visible_action,
    }
    command = [
        sys.executable, "-B", str(EVALUATOR), "--env-dir", str(runtime_env), "--task", TASK_ID,
        "--agent", "AuthoritativeObservationProbeAgent", "--agent-args", json.dumps(agent_args, separators=(",", ":")),
        "--time-mode", mode, "--seed", str(SEED), "--steps", "3", "--request-timeout-seconds", "15",
        "--request-attempts", "2", "--episode-summary-path", str(episode_summary_path),
    ]
    (mode_dir / "run-command.json").write_text(
        json.dumps({"argv": command, "agent_args": agent_args, "purpose": "evaluator transport/timing probe, not a benchmark capability result"}, indent=2) + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    (mode_dir / "evaluator.log").write_text(completed.stdout + completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(f"{mode} evaluator exited {completed.returncode}; see {mode_dir / 'evaluator.log'}")

    episode_summary = read_json(episode_summary_path)
    episode_dir = Path(episode_summary["episode_dir"]).resolve()
    timing = read_jsonl(episode_dir / "realtime_timing.jsonl")
    model_inputs = read_jsonl(episode_dir / "model_input_manifest.jsonl")
    public = read_json(episode_dir / "public_state.json")
    current_task = read_json(episode_dir / "current_task.json")
    observations = observation_records(episode_dir, out_dir, mode, settings["frames_per_observation"])
    if len(model_inputs) < 3:
        raise AssertionError(f"{mode}: expected timeout, retried action, and post-action model observations")
    if any(item.get("frame_count") != settings["frames_per_observation"] or item.get("screen_is_last_frame") is not True for item in model_inputs):
        raise AssertionError(f"{mode}: delivered observation did not bind obs.screen to its final frame")
    turns = [item for item in timing if item.get("event") == "turn"]
    first = turns[0]
    attempts = first["request_attempts"]
    if [item.get("outcome") for item in attempts] != ["error", "success"] or attempts[0].get("error_type") != "TimeoutError":
        raise AssertionError(f"{mode}: required single-layer transient retry was not recorded")
    action = first["actions"][0]
    if action["task_time_delta_during_action_ms"] <= 0:
        raise AssertionError(f"{mode}: visible action did not run task time")
    if mode == "paused":
        if any(abs(float(item["task_time_delta_ms"])) > 5 for item in attempts):
            raise AssertionError("paused task advanced during a model request or retry")
        if action["clock_after_action"].get("state") != "paused":
            raise AssertionError("paused action did not return the shared clock to pause")
    elif sum(float(item["task_time_delta_ms"]) for item in attempts) <= 20:
        raise AssertionError("live task did not advance during model request/retry")

    first_screen = out_dir / observations[0]["screen"]
    after_action_screen = out_dir / observations[1]["screen"]
    if sha256(first_screen) == sha256(after_action_screen):
        raise AssertionError(f"{mode}: post-action observation did not visibly change")
    return {
        "mode": mode,
        "episode_dir": relative(episode_dir, out_dir),
        "episode_summary": relative(episode_summary_path, out_dir),
        "task_id": TASK_ID,
        "seed": SEED,
        "task_seed": current_task["seed"],
        "challenge_id": public["challenge_id"],
        "controlled_condition": public["control_condition"],
        "observations": observations,
        "model_input_manifest": relative(episode_dir / "model_input_manifest.jsonl", out_dir),
        "realtime_timing": relative(episode_dir / "realtime_timing.jsonl", out_dir),
        "first_model_request_attempts": attempts,
        "action": action,
        "screen_is_final_frame_for_all_requests": True,
        "actual_inference_backend": "Tesseract 5 LSTM OCR",
    }


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    controls = read_json(ENVIRONMENT / "controls.json")
    settings = {key: int(value) for key, value in controls["real_time"].items()}
    with tempfile.TemporaryDirectory(prefix="jigsaw-authoritative-evaluator-") as temporary_name:
        runtime_env = build_runtime_environment(Path(temporary_name), out_dir)
        live = run_mode("live", runtime_env, out_dir, settings)
        paused = run_mode("paused", runtime_env, out_dir, settings)
    for key in ("task_id", "seed", "task_seed", "challenge_id", "controlled_condition"):
        if live[key] != paused[key]:
            raise AssertionError(f"live and paused evaluator episodes disagree on {key}")
    summary = {
        "ok": True,
        "environment": ENVIRONMENT.name,
        "same_controlled_task_seed_interaction_and_world": True,
        "settings": {**settings, "request_timeout_seconds": 15, "request_attempts": 2},
        "live": live,
        "paused": paused,
        "evidence_boundary": "The local screenshot-only probe audits evaluator transport, request timing/retry, and the action cycle. It is not a human or general computer-use-agent performance result.",
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
