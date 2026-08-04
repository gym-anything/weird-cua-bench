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

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENV_ROOT = BENCHMARK / "environments" / "slot_reel_capture_env"
MATERIALIZER = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
EVALUATOR = BENCHMARK / "tools" / "run_realtime_evaluation.py"
TASK_ID = "slot_reel_capture_d4_full_seed_0001"
SEED = 271828
EXPECTED_RESOLUTION = [1280, 720]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run live and paused Slot-Reel episodes through the authoritative "
            "real-time evaluator and retain the exact model observations, "
            "retry records, keyboard action, and server witness."
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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    runtime_benchmark = temp_root / "weird_captcha_gym"
    runtime_env = runtime_benchmark / "environments" / ENV_ROOT.name
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


def run_mode(
    mode: str,
    runtime_env: Path,
    out_dir: Path,
) -> dict[str, Any]:
    mode_dir = out_dir / mode
    mode_dir.mkdir(parents=True, exist_ok=True)
    episode_summary_path = mode_dir / "episode-summary.json"
    agent_args = {
        "transient_timeout_attempts": 1,
        "inference_timeout_seconds": 10,
        "expected_text_markers": ["CAPTURE", "STRIKES", "LIVE"],
        "decision_label": "press_visible_task_keyboard_key_1",
        "actions": [{"keyboard": {"text": "1"}}],
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
                    "authoritative evaluator transport, timing, retry, "
                    "keyboard-action, and next-observation evidence probe; "
                    "not a benchmark capability evaluation"
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
    model_inputs = read_jsonl(
        episode_dir / "model_input_manifest.jsonl"
    )
    current_task = read_json(episode_dir / "current_task.json")
    public_state = read_json(episode_dir / "public_state.json")
    witness_ledger = read_json(
        episode_dir / "slot_reel_witness_ledger.json"
    )

    observations = []
    for turn_dir in sorted((episode_dir / "observations").glob("turn-*")):
        manifest_path = turn_dir / "guest-capture-manifest.json"
        manifest = read_json(manifest_path)
        frames = []
        for index, frame in enumerate(manifest["frames"]):
            path = turn_dir / f"frame-{index:03d}.png"
            with Image.open(path) as image:
                resolution = list(image.size)
            if resolution != EXPECTED_RESOLUTION:
                raise AssertionError(
                    f"{mode}: authoritative frame is {resolution}, "
                    f"expected {EXPECTED_RESOLUTION}"
                )
            frames.append(
                {
                    "path": relative(path, out_dir),
                    "sha256": sha256(path),
                    "resolution": resolution,
                    "offset_ms": frame["offset_ms"],
                    "target_offset_ms": frame["target_offset_ms"],
                }
            )
        if len(frames) != 6:
            raise AssertionError(
                f"{mode}: expected six evaluator-delivered frames"
            )
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
        raise AssertionError(
            f"{mode}: keyboard action lacks a following observation"
        )

    turn_records = [
        row for row in timing if row.get("event") == "turn"
    ]
    first_turn = turn_records[0]
    attempts = first_turn["request_attempts"]
    if [row["outcome"] for row in attempts] != ["error", "success"]:
        raise AssertionError(
            f"{mode}: transient inference retry is missing"
        )
    if attempts[0].get("error_type") != "TimeoutError":
        raise AssertionError(
            f"{mode}: first model attempt was not the timeout probe"
        )
    if not first_turn.get("actions"):
        raise AssertionError(
            f"{mode}: evaluator applied no visible keyboard action"
        )
    action_record = first_turn["actions"][0]
    if action_record["task_time_delta_during_action_ms"] <= 0:
        raise AssertionError(
            f"{mode}: keyboard action did not run task time"
        )
    if mode == "paused":
        if any(
            abs(float(item["task_time_delta_ms"])) > 5
            for item in attempts
        ):
            raise AssertionError(
                "paused task time advanced during inference or retry"
            )
        if action_record["clock_after_action"].get("state") != "paused":
            raise AssertionError(
                "paused keyboard action did not return to pause"
            )
    elif sum(
        float(item["task_time_delta_ms"]) for item in attempts
    ) <= 20:
        raise AssertionError(
            "live task time did not advance during inference"
        )

    if len(model_inputs) < 3:
        raise AssertionError(
            f"{mode}: model input records are incomplete"
        )
    for model_input in model_inputs:
        if (
            model_input.get("frame_count") != 6
            or model_input.get("screen_is_last_frame") is not True
        ):
            raise AssertionError(
                f"{mode}: model did not receive the six-frame window"
            )

    actions = witness_ledger.get("actions") or []
    if (
        len(actions) != 1
        or actions[0].get("entered_key") != "1"
        or actions[0].get("accepted") is not False
        or actions[0].get("input_source") != "physical_keyboard"
        or actions[0].get("event_surface") != "keyboard_keydown"
    ):
        raise AssertionError(
            f"{mode}: server did not witness the evaluator key: {actions}"
        )

    condition = public_state.get("control_condition") or {}
    parameters = condition.get("difficulty_parameters") or {}
    token_counts = [
        len(reel["tokens"]) for reel in public_state.get("reels") or []
    ]
    if (
        condition.get("difficulty") != 4
        or condition.get("interaction") != "full"
        or parameters.get("token_count") != 7
        or token_counts != [7] * 5
    ):
        raise AssertionError(
            f"{mode}: evaluator did not load original L4/full: "
            f"{condition}, {token_counts}"
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
        "controlled_condition": condition,
        "token_counts": token_counts,
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
        "action": action_record,
        "server_witness_ledger": relative(
            episode_dir / "slot_reel_witness_ledger.json",
            out_dir,
        ),
        "server_witness_action": actions[0],
        "screen_is_final_frame_for_all_requests": True,
        "actual_inference_backend": "Tesseract 5 LSTM OCR",
        "evidence_boundary": (
            "This local screenshot-only vision policy audits the "
            "authoritative evaluator transport, finite request deadline, "
            "retry, keyboard action, and next-observation cycle. It is not "
            "a human or general computer-use-agent performance result."
        ),
    }


def make_contact_sheet(
    out_dir: Path,
    live: dict[str, Any],
    paused: dict[str, Any],
) -> None:
    rows = []
    for mode, record in (("LIVE", live), ("PAUSED", paused)):
        for observation in record["observations"][:2]:
            rows.append(
                (
                    f"{mode} / {observation['turn']} / exact model frames",
                    [
                        out_dir / frame["path"]
                        for frame in observation["frames"]
                    ],
                )
            )
    thumb_size = (320, 180)
    label_height = 36
    sheet = Image.new(
        "RGB",
        (thumb_size[0] * 6, (thumb_size[1] + label_height) * len(rows)),
        "#12080a",
    )
    draw = ImageDraw.Draw(sheet)
    for row_index, (label, frames) in enumerate(rows):
        top = row_index * (thumb_size[1] + label_height)
        draw.text((12, top + 10), label, fill="#ffe7a2")
        for column, path in enumerate(frames):
            with Image.open(path).convert("RGB") as frame:
                thumb = frame.resize(thumb_size)
            sheet.paste(
                thumb,
                (column * thumb_size[0], top + label_height),
            )
    sheet.save(out_dir / "contact_sheet.png")


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
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
        prefix="slot-reel-authoritative-"
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

    make_contact_sheet(out_dir, live, paused)
    source_paths = {
        "capture_driver": Path(__file__).resolve(),
        "evaluator": EVALUATOR,
        "observation_probe": (
            BENCHMARK
            / "tools"
            / "authoritative_observation_probe_agent.py"
        ),
        "materializer": MATERIALIZER,
        "guest_x11_capture": (
            BENCHMARK
            / "shared_scripts"
            / "capture_observation_window.py"
        ),
        "environment": ENV_ROOT / "env.json",
        "controls": ENV_ROOT / "controls.json",
        "base_task": (
            ENV_ROOT
            / "tasks"
            / "slot_reel_capture_seed_0001"
            / "task.json"
        ),
        "app": BENCHMARK / "shared_runtime" / "app" / "app.js",
        "styles": (
            BENCHMARK / "shared_runtime" / "app" / "styles.css"
        ),
        "generator": BENCHMARK / "shared_scripts" / "setup_task.py",
        "server_witness": (
            BENCHMARK
            / "shared_runtime"
            / "server"
            / "slot_reel_witness.py"
        ),
    }
    summary = {
        "ok": True,
        "authoritative_evaluator_action_cycle": True,
        "capture_function": (
            "weird_captcha_gym.tools."
            "run_realtime_evaluation._capture_observation"
        ),
        "model_observation_resolution": EXPECTED_RESOLUTION,
        "same_controlled_task_seed_interaction_and_world": True,
        "task_id": TASK_ID,
        "seed": SEED,
        "settings": {
            "play_time_seconds": 90,
            "observation_window_ms": 800,
            "frames_per_observation": 6,
            "request_timeout_seconds": 15,
            "request_attempts": 2,
        },
        "source_sha256": {
            name: sha256(path) for name, path in source_paths.items()
        },
        "contact_sheet": "contact_sheet.png",
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
