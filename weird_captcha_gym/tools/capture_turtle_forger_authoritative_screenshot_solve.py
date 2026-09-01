#!/usr/bin/env python3
"""Retain a complete screenshot-only Turtle Forger evaluator submission."""

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

from weird_captcha_gym.tools.capture_turtle_forger_authoritative_evaluator_evidence import (
    BENCHMARK,
    ENVIRONMENT,
    EVALUATOR,
    EXPECTED_FRAMES,
    EXPECTED_RESOLUTION,
    ROOT,
    SEED,
    TASK_IDS,
    build_runtime_environment,
    read_json,
    read_jsonl,
    relative,
    sha256,
    world_fingerprint,
)


AGENT = (
    "weird_captcha_gym.tools.turtle_forger_screenshot_agent:"
    "TurtleForgerScreenshotAgent"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ENVIRONMENT / "evidence_docs" / "authoritative_screenshot_policy",
    )
    parser.add_argument(
        "--mode",
        choices=("live", "paused", "both"),
        default="paused",
    )
    return parser.parse_args()


def observation_inventory(
    episode_dir: Path,
    out_dir: Path,
    mode: str,
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for turn_dir in sorted((episode_dir / "observations").glob("turn-*")):
        manifest_path = turn_dir / "guest-capture-manifest.json"
        manifest = read_json(manifest_path)
        frames: list[dict[str, Any]] = []
        for index, item in enumerate(manifest["frames"]):
            frame_path = turn_dir / f"frame-{index:03d}.png"
            with Image.open(frame_path) as image:
                resolution = list(image.size)
            if resolution != EXPECTED_RESOLUTION:
                raise AssertionError(
                    f"{mode} {turn_dir.name} rendered at {resolution}"
                )
            frames.append(
                {
                    "path": relative(frame_path, out_dir),
                    "sha256": sha256(frame_path),
                    "offset_ms": item["offset_ms"],
                    "target_offset_ms": item["target_offset_ms"],
                    "resolution": resolution,
                }
            )
        if len(frames) != EXPECTED_FRAMES[mode]:
            raise AssertionError(
                f"{mode} {turn_dir.name}: expected {EXPECTED_FRAMES[mode]} frames, "
                f"got {len(frames)}"
            )
        observations.append(
            {
                "turn": turn_dir.name,
                "capture_manifest": relative(manifest_path, out_dir),
                "frames": frames,
                "screen": frames[-1]["path"],
                "screen_is_final_frame": True,
                "time_status": manifest["time_status"],
            }
        )
    if len(observations) < 8:
        raise AssertionError(f"{mode}: authoritative solve had too few observations")
    return observations


def run_mode(mode: str, runtime_env: Path, out_dir: Path) -> dict[str, Any]:
    mode_dir = out_dir / mode
    mode_dir.mkdir(parents=True)
    episode_summary_path = mode_dir / "episode-summary.json"
    agent_args = {
        "inference_timeout_seconds": 30,
        "policy_scope": "task_specific_screenshot_only_ocr_pixels_and_geometry",
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
        AGENT,
        "--agent-args",
        json.dumps(agent_args, separators=(",", ":")),
        "--time-mode",
        mode,
        "--seed",
        str(SEED),
        "--steps",
        "40" if mode == "paused" else "56",
        "--request-timeout-seconds",
        "45",
        "--request-attempts",
        "2",
        "--episode-summary-path",
        str(episode_summary_path),
    ]
    run_record = {
        "argv": command,
        "agent_args": agent_args,
        "isolation": {
            "host_foreground_application": False,
            "environment_vnc_ui_enabled": False,
            "interactive_vnc_client_opened": False,
            "runner_background_virtual_display": True,
            "ephemeral_virtual_machine": True,
            "existing_browser_profile": False,
            "connected_browser_or_desktop_automation": False,
        },
        "policy_input_boundary": (
            "Only evaluator-delivered chronological PNG frames, task instructions, and prior "
            "native-action receipts. No public_state, ground_truth, DOM, URL, browser handle, "
            "filesystem task state, or developer surface is provided to the policy."
        ),
        "classification": (
            "task-specific deterministic screenshot/OCR/pixel-geometry policy; complete "
            "authoritative runner solve, not a human run, general model-agent result, or "
            "difficulty calibration sample"
        ),
    }
    (mode_dir / "run-command.json").write_text(
        json.dumps(run_record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
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
    policy_manifest_path = episode_dir / "screenshot_policy_manifest.jsonl"
    policy = read_jsonl(policy_manifest_path)
    timing = read_jsonl(episode_dir / "realtime_timing.jsonl")
    public_state = read_json(episode_dir / "public_state.json")
    current_task = read_json(episode_dir / "current_task.json")
    observations = observation_inventory(episode_dir, out_dir, mode)
    setup = next(item for item in timing if item.get("event") == "setup")
    turns = [item for item in timing if item.get("event") == "turn"]
    verifier = (episode_summary.get("info") or {}).get("verifier") or {}
    attempts = episode_summary.get("attempts") or {}

    if verifier.get("passed") is not True:
        raise AssertionError(f"{mode}: authoritative verifier did not pass: {verifier}")
    if attempts.get("submitted") is not True or attempts.get("graded_total") != 1:
        raise AssertionError(f"{mode}: expected one successful submission: {attempts}")
    if attempts.get("graded_failures") != 0:
        raise AssertionError(f"{mode}: screenshot policy incurred a graded failure")
    if not policy or policy[-1].get("decision") != "finish_after_visible_pass":
        raise AssertionError(f"{mode}: policy did not stop from the visible PASS state")
    if any(
        item.get("visible_task_ui_only_rule_present") is not True
        or item.get("screen_is_last_frame") is not True
        or item.get("frame_count") != EXPECTED_FRAMES[mode]
        for item in policy
    ):
        raise AssertionError(f"{mode}: incomplete screenshot-policy input manifest")

    decisions = [item["decision"] for item in policy]
    required = {
        "click_visible_auto_replay",
        "continue_chronological_scan_observation",
        "drag_reconstructed_program_from_visible_drawer",
        "continue_drag_reconstructed_program",
        "click_visible_run_proof",
        "click_visible_certify_plate",
        "finish_after_visible_pass",
    }
    if not required.issubset(decisions):
        raise AssertionError(
            f"{mode}: missing screenshot-policy decisions {sorted(required.difference(decisions))}"
        )
    construction = next(
        item
        for item in policy
        if item.get("decision") == "drag_reconstructed_program_from_visible_drawer"
    )
    measured = construction.get("measured_strokes") or {}
    program = construction.get("program") or []
    if len(measured) != 8 or len(program) != 15:
        raise AssertionError(
            f"{mode}: incomplete visible reconstruction: strokes={len(measured)} program={len(program)}"
        )

    condition = public_state["control_condition"]
    if condition.get("difficulty") != 3 or condition.get("interaction") != "full":
        raise AssertionError(f"{mode}: wrong controlled condition {condition}")
    if condition.get("real_time") != mode:
        raise AssertionError(f"{mode}: wrong controlled time mode {condition}")

    action_records = [
        action
        for turn in turns
        for action in (turn.get("actions") or [])
    ]
    native_input_records = [
        action
        for action in action_records
        if any(
            requested.get("action") != "wait"
            for requested in (action.get("requested_actions") or [])
        )
    ]
    if mode == "paused":
        if any(
            abs(float(action["task_time_delta_during_action_ms"])) > 5
            for action in native_input_records
        ):
            raise AssertionError("paused task time advanced during native input delivery")
        if any(
            status.get("required") is True
            and status.get("receipt_confirmed") is not True
            for action in native_input_records
            for status in action.get("action_delivery_statuses") or []
        ):
            raise AssertionError("paused action lacked a trusted native-input receipt")

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
        "policy_manifest": relative(policy_manifest_path, out_dir),
        "realtime_timing": relative(episode_dir / "realtime_timing.jsonl", out_dir),
        "observations": observations,
        "decisions": decisions,
        "policy_turns": len(policy),
        "measured_stroke_count": len(measured),
        "constructed_program": program,
        "environment_action_groups": len(action_records),
        "verifier": verifier,
        "attempts": attempts,
        "request_timeout_seconds": setup["request_timeout_seconds"],
        "request_attempts": setup["request_attempts"],
        "request_retry_policy": setup["request_retry_policy"],
        "effective_runner_options": setup["effective_runner_options"],
        "visible_task_ui_only_rule_present_for_all_requests": True,
        "screen_is_final_frame_for_all_requests": True,
        "outcome_class": "task_specific_screenshot_only_policy_pass",
        "evidence_boundary": (
            "Complete authoritative runner submission reconstructed from evaluator-delivered "
            "chronological screenshots. This is not human evidence, a general provider/model "
            "agent result, or empirical difficulty calibration."
        ),
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
    modes = ("live", "paused") if args.mode == "both" else (args.mode,)
    with tempfile.TemporaryDirectory(prefix="turtle-screenshot-solve-") as raw:
        runtime_env = build_runtime_environment(Path(raw), out_dir)
        results = {mode: run_mode(mode, runtime_env, out_dir) for mode in modes}

    if len(results) == 2:
        if results["live"]["task_seed"] != results["paused"]["task_seed"]:
            raise AssertionError("live and paused solves used different task seeds")
        if results["live"]["world_fingerprint"] != results["paused"]["world_fingerprint"]:
            raise AssertionError("live and paused solves used different generated worlds")

    sources = {
        "capture_driver": Path(__file__).resolve(),
        "screenshot_policy": BENCHMARK / "tools" / "turtle_forger_screenshot_agent.py",
        "evaluator": EVALUATOR,
        "runner": BENCHMARK / "runner.py",
        "environment": ENVIRONMENT / "env.json",
        "controls": ENVIRONMENT / "controls.json",
        "task": ENVIRONMENT / "tasks" / "turtle_forger_seed_0001" / "task.json",
        "browser": BENCHMARK / "shared_runtime" / "app" / "mechanics" / "turtle_forger.js",
        "generator": BENCHMARK / "shared_scripts" / "incubator_generators" / "turtle_forger.py",
        "grader": BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "turtle_forger.py",
    }
    summary = {
        "ok": all(item["verifier"].get("passed") is True for item in results.values()),
        "environment": "Turtle Forger",
        "policy": "task-specific deterministic screenshot/OCR/pixel-geometry policy",
        "complete_authoritative_runner_submissions": True,
        "results": results,
        "source_sha256": {name: sha256(path) for name, path in sources.items()},
        "isolation": {
            "host_foreground_application": False,
            "environment_vnc_ui_enabled": False,
            "interactive_vnc_client_opened": False,
            "runner_background_virtual_display": True,
            "ephemeral_virtual_machine_per_episode": True,
            "existing_browser_profile": False,
            "connected_browser_or_desktop_automation": False,
        },
        "evidence_boundary": (
            "The retained episode is a complete authoritative runner pass from a task-specific "
            "policy whose only task input is evaluator-delivered chronological screenshots. "
            "It is not human/VNC usability evidence, general model-agent performance, or "
            "L1-L5 empirical calibration."
        ),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": summary["ok"], "evidence": str(out_dir)}, sort_keys=True))
    if not summary["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
