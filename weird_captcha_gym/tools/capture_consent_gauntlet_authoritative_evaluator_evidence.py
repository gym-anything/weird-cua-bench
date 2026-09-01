#!/usr/bin/env python3
"""Preserve evaluator-delivered Consent Gauntlet observations and timing."""

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

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "consent_gauntlet_env"
MATERIALIZER = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
EVALUATOR = BENCHMARK / "tools" / "run_realtime_evaluation.py"
TASK_IDS = {
    "live": "consent_gauntlet_d3_full_seed_0001",
    "paused": "consent_gauntlet_d3_full_seed_0001_tpaused",
}
SEED = 271828
EXPECTED_RESOLUTION = [1920, 1080]
EXPECTED_FRAMES = {"live": 1, "paused": 5}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ENVIRONMENT / "evidence_docs" / "authoritative_evaluator",
    )
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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def world_fingerprint(public_state: dict[str, Any]) -> str:
    value = {
        "surface": public_state["surface"],
        "parameters": public_state["parameters"],
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_runtime_environment(temporary: Path, out_dir: Path) -> Path:
    materialized = temporary / "materialized"
    subprocess.run(
        [
            sys.executable,
            "-B",
            str(MATERIALIZER),
            "--environment",
            ENVIRONMENT.name,
            "--output-root",
            str(materialized),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    materialized_tasks = materialized / ENVIRONMENT.name / "tasks"
    live_task_dir = materialized_tasks / TASK_IDS["live"]
    paused_task_dir = materialized_tasks / TASK_IDS["paused"]
    shutil.copytree(live_task_dir, paused_task_dir)
    for script in paused_task_dir.glob("*.sh"):
        script.write_text(
            script.read_text(encoding="utf-8").replace(
                TASK_IDS["live"], TASK_IDS["paused"]
            ),
            encoding="utf-8",
        )
    paused_task = read_json(paused_task_dir / "task.json")
    paused_task["id"] = f"{TASK_IDS['paused']}@0.2"
    paused_task["name"] = f"{paused_task['name']} · Paused Time"
    paused_task["hooks"] = {
        key: value.replace(TASK_IDS["live"], TASK_IDS["paused"])
        for key, value in paused_task["hooks"].items()
    }
    paused_task["metadata"]["control_condition"]["real_time"] = "paused"
    (paused_task_dir / "task.json").write_text(
        json.dumps(paused_task, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    runtime_benchmark = temporary / "weird_captcha_gym"
    runtime_env = runtime_benchmark / "environments" / ENVIRONMENT.name
    runtime_env.mkdir(parents=True)
    shutil.copytree(
        BENCHMARK / "shared_runtime",
        runtime_benchmark / "shared_runtime",
    )
    shutil.copytree(
        materialized_tasks,
        runtime_env / "tasks",
    )
    config = read_json(ENVIRONMENT / "env.json")
    if config.get("vnc", {}).get("enable") is not False:
        raise AssertionError("authoritative evidence requires VNC to remain disabled")
    config["recording"]["output_dir"] = str((out_dir / "raw_episodes").resolve())
    for mount in config["mounts"]:
        if mount.get("target") == "/workspace/tasks":
            mount["source"] = str((runtime_env / "tasks").resolve())
    (runtime_env / "env.json").write_text(
        json.dumps(config, indent=2) + "\n",
        encoding="utf-8",
    )
    return runtime_env


def observation_records(
    episode_dir: Path,
    out_dir: Path,
    mode: str,
) -> list[dict[str, Any]]:
    records = []
    expected_frames = EXPECTED_FRAMES[mode]
    for turn_dir in sorted((episode_dir / "observations").glob("turn-*")):
        manifest_path = turn_dir / "guest-capture-manifest.json"
        manifest = read_json(manifest_path)
        frames = []
        for index, item in enumerate(manifest["frames"]):
            path = turn_dir / f"frame-{index:03d}.png"
            with Image.open(path) as image:
                resolution = list(image.size)
            if resolution != EXPECTED_RESOLUTION:
                raise AssertionError(
                    f"{mode} {turn_dir.name}: got {resolution}, expected {EXPECTED_RESOLUTION}"
                )
            frames.append(
                {
                    "path": relative(path, out_dir),
                    "sha256": sha256(path),
                    "resolution": resolution,
                    "offset_ms": item["offset_ms"],
                    "target_offset_ms": item["target_offset_ms"],
                }
            )
        if len(frames) != expected_frames:
            raise AssertionError(
                f"{mode} {turn_dir.name}: expected {expected_frames} frames, got {len(frames)}"
            )
        records.append(
            {
                "turn": turn_dir.name,
                "guest_capture_manifest": relative(manifest_path, out_dir),
                "frames": frames,
                "screen": frames[-1]["path"],
                "screen_is_final_frame": True,
                "time_status": manifest["time_status"],
                "distinct_frame_hashes": len({item["sha256"] for item in frames}),
            }
        )
    if len(records) < 2:
        raise AssertionError(f"{mode}: missing initial or post-action observation")
    return records


def run_mode(mode: str, runtime_env: Path, out_dir: Path) -> dict[str, Any]:
    mode_dir = out_dir / mode
    mode_dir.mkdir(parents=True)
    episode_summary_path = mode_dir / "episode-summary.json"
    visible_point = [560, 810] if mode == "paused" else [976, 574]
    decision_label = (
        "click_visible_review_data_controls_card"
        if mode == "paused"
        else "click_visible_optional_processing_orbit_core"
    )
    agent_args = {
        "transient_timeout_attempts": 1,
        "inference_timeout_seconds": 10,
        "expected_text_markers": [
            "LEAVE EVERY OPTIONAL PURPOSE",
            "THE NOTICE WON'T DISMISS",
            "RECOMMENDED SETTINGS",
        ],
        "decision_label": decision_label,
        "actions": [
            {"mouse": {"move": visible_point}},
            {"mouse": {"buttons": {"left_down": True}}},
            {"mouse": {"buttons": {"left_up": True}}},
        ],
    }
    command = [
        sys.executable,
        "-B",
        str(EVALUATOR),
        "--env-dir",
        str(runtime_env),
        "--task",
        TASK_IDS[mode],
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
                "isolation": {
                    "host_foreground_application": False,
                    "environment_vnc_ui_enabled": False,
                    "interactive_vnc_client_opened": False,
                    "runner_background_virtual_display": True,
                    "ephemeral_virtual_machine": True,
                    "existing_browser_profile": False,
                },
                "purpose": (
                    "authoritative evaluator transport, timing, retry, trusted-input, "
                    "and post-action observation probe; not a task-solving result"
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    (mode_dir / "evaluator.log").write_text(
        completed.stdout + completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"{mode} evaluator exited {completed.returncode}; see {mode_dir / 'evaluator.log'}"
        )

    episode_summary = read_json(episode_summary_path)
    episode_dir = Path(episode_summary["episode_dir"]).resolve()
    timing = read_jsonl(episode_dir / "realtime_timing.jsonl")
    model_inputs = read_jsonl(episode_dir / "model_input_manifest.jsonl")
    public_state = read_json(episode_dir / "public_state.json")
    current_task = read_json(episode_dir / "current_task.json")
    observations = observation_records(episode_dir, out_dir, mode)

    setup = next(item for item in timing if item.get("event") == "setup")
    effective = setup["effective_runner_options"]
    if (
        effective.get("frames_per_observation") != EXPECTED_FRAMES[mode]
        or effective.get("observation_window_ms") != (0 if mode == "live" else 720)
    ):
        raise AssertionError(f"{mode}: unexpected evaluator observation schedule {effective}")

    if len(model_inputs) < 3:
        raise AssertionError(f"{mode}: timeout, retry, and post-action requests were not retained")
    for item in model_inputs:
        if (
            item.get("frame_count") != EXPECTED_FRAMES[mode]
            or item.get("screen_is_last_frame") is not True
            or item.get("visible_task_ui_only_rule_present") is not True
        ):
            raise AssertionError(f"{mode}: retained model input is incomplete")

    turns = [item for item in timing if item.get("event") == "turn"]
    first_turn = turns[0]
    attempts = first_turn["request_attempts"]
    if [item.get("outcome") for item in attempts] != ["error", "success"]:
        raise AssertionError(f"{mode}: required single-layer retry was not retained")
    if attempts[0].get("error_type") != "TimeoutError":
        raise AssertionError(f"{mode}: first request was not the simulated transient timeout")
    action = first_turn["actions"][0]
    if mode == "paused":
        if any(abs(float(item["task_time_delta_ms"])) > 5 for item in attempts):
            raise AssertionError("paused task clock advanced during inference or retry")
        statuses = action.get("action_delivery_statuses") or []
        required_statuses = [item for item in statuses if item.get("required") is True]
        if len(required_statuses) != 2 or any(
            item.get("receipt_confirmed") is not True for item in required_statuses
        ):
            raise AssertionError("paused native mouse press/release lacks trusted Chromium receipts")
        if abs(float(action["task_time_delta_during_action_ms"])) > 5:
            raise AssertionError("paused native action advanced task time before observation")
        observation_delta = (
            float(action["task_time_ms"])
            - float(action["task_time_after_execution_ms"])
        )
        if not 715 <= observation_delta <= 725:
            raise AssertionError(
                f"paused post-action observation advanced {observation_delta} ms, not 720 ms"
            )
        if action["clock_after_action"].get("controller_state") != "paused":
            raise AssertionError("paused trusted-input boundary did not retain the pause")
    elif sum(float(item["task_time_delta_ms"]) for item in attempts) <= 20:
        raise AssertionError("live task clock did not advance during inference and retry")

    initial_screen = out_dir / observations[0]["screen"]
    post_action_screen = out_dir / observations[1]["screen"]
    if sha256(initial_screen) == sha256(post_action_screen):
        raise AssertionError(f"{mode}: post-action evaluator observation did not change")

    condition = public_state["control_condition"]
    if condition.get("difficulty") != 3 or condition.get("interaction") != "full":
        raise AssertionError(f"{mode}: evaluator loaded the wrong controlled condition")
    expected_real_time = mode
    if condition.get("real_time") != expected_real_time:
        raise AssertionError(f"{mode}: controlled task reports {condition.get('real_time')}")

    verifier = (episode_summary.get("info") or {}).get("verifier") or {}
    attempts_summary = episode_summary.get("attempts") or {}
    if verifier.get("passed") is not False or attempts_summary.get("submitted") is not False:
        raise AssertionError("transport probe must remain a classified no-submission result")

    return {
        "mode": mode,
        "task_id": TASK_IDS[mode],
        "seed": SEED,
        "task_seed": current_task["seed"],
        "challenge_id": public_state["challenge_id"],
        "world_fingerprint": world_fingerprint(public_state),
        "controlled_condition": condition,
        "episode_dir": relative(episode_dir, out_dir),
        "episode_summary": relative(episode_summary_path, out_dir),
        "observations": observations,
        "model_input_manifest": relative(
            episode_dir / "model_input_manifest.jsonl", out_dir
        ),
        "realtime_timing": relative(episode_dir / "realtime_timing.jsonl", out_dir),
        "effective_runner_options": effective,
        "first_model_request_attempts": attempts,
        "action": action,
        "screen_is_final_frame_for_all_requests": True,
        "visible_task_ui_only_rule_present_for_all_requests": True,
        "request_retry_policy": setup["request_retry_policy"],
        "request_timeout_seconds": setup["request_timeout_seconds"],
        "request_attempts": setup["request_attempts"],
        "outcome_class": "transport_probe_no_submission_not_a_task_pass",
        "actual_inference_backend": "Tesseract 5 LSTM OCR",
    }


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    (out_dir / "tesseract-version.txt").write_text(
        subprocess.check_output(
            ["tesseract", "--version"],
            text=True,
            stderr=subprocess.STDOUT,
        ),
        encoding="utf-8",
    )
    with tempfile.TemporaryDirectory(prefix="consent-authoritative-evaluator-") as raw:
        runtime_env = build_runtime_environment(Path(raw), out_dir)
        live = run_mode("live", runtime_env, out_dir)
        paused = run_mode("paused", runtime_env, out_dir)

    if live["task_seed"] != paused["task_seed"]:
        raise AssertionError("live and paused tasks do not share the same generator seed")
    if live["world_fingerprint"] != paused["world_fingerprint"]:
        raise AssertionError("live and paused tasks do not preserve the same generated world")

    source_paths = {
        "capture_driver": Path(__file__).resolve(),
        "evaluator": EVALUATOR,
        "observation_probe": BENCHMARK / "tools" / "authoritative_observation_probe_agent.py",
        "materializer": MATERIALIZER,
        "runner": BENCHMARK / "runner.py",
        "guest_capture": BENCHMARK / "shared_scripts" / "capture_observation_window.py",
        "environment": ENVIRONMENT / "env.json",
        "controls": ENVIRONMENT / "controls.json",
        "base_task": ENVIRONMENT / "tasks" / "consent_gauntlet_seed_0001" / "task.json",
        "browser": BENCHMARK / "shared_runtime" / "app" / "mechanics" / "consent_gauntlet.js",
        "generator": BENCHMARK / "shared_scripts" / "incubator_generators" / "consent_gauntlet.py",
        "grader": BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "consent_gauntlet.py",
    }
    summary = {
        "ok": True,
        "environment": "Consent Gauntlet",
        "authoritative_evaluator_action_cycle": True,
        "same_generated_world": True,
        "settings": {
            "configured_observation_window_ms": 720,
            "configured_frames_per_observation": 5,
            "effective_live_observation": "one instantaneous frame",
            "effective_paused_observation": "five chronological frames over 720 ms",
            "request_timeout_seconds": 15,
            "request_attempts": 2,
        },
        "isolation": {
            "host_foreground_application": False,
            "environment_vnc_ui_enabled": False,
            "interactive_vnc_client_opened": False,
            "runner_background_virtual_display": True,
            "ephemeral_virtual_machine_per_episode": True,
            "existing_browser_profile": False,
            "connected_browser_or_desktop_automation": False,
        },
        "live": live,
        "paused": paused,
        "source_sha256": {name: sha256(path) for name, path in source_paths.items()},
        "evidence_boundary": (
            "These retained files are the exact observations and task description received "
            "by a local screenshot-only evaluator transport probe. They establish delivery, "
            "clock/retry behavior, trusted paused input receipt, and the next-observation cycle. "
            "The probe did not solve or submit the puzzle and is not human-usability or general "
            "computer-use-agent performance evidence."
        ),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "evidence": str(out_dir)}, sort_keys=True))


if __name__ == "__main__":
    main()
