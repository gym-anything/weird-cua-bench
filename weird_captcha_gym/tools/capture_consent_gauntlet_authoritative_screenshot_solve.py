#!/usr/bin/env python3
"""Run and retain complete screenshot-only Consent Gauntlet evaluator solves."""

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

from weird_captcha_gym.tools.capture_consent_gauntlet_authoritative_evaluator_evidence import (
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
    "weird_captcha_gym.tools.consent_gauntlet_screenshot_agent:"
    "ConsentGauntletScreenshotAgent"
)
BENCHMARK = ROOT / "weird_captcha_gym"


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
        help="Evaluator time mode(s) to retain.",
    )
    return parser.parse_args()


def _observation_inventory(
    episode_dir: Path,
    out_dir: Path,
    mode: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
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
                    f"{mode} {turn_dir.name} rendered at {resolution}"
                )
            frames.append(
                {
                    "path": relative(path, out_dir),
                    "sha256": sha256(path),
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
        records.append(
            {
                "turn": turn_dir.name,
                "capture_manifest": relative(manifest_path, out_dir),
                "frames": frames,
                "screen": frames[-1]["path"],
                "screen_is_final_frame": True,
                "time_status": manifest["time_status"],
            }
        )
    if len(records) < 6:
        raise AssertionError(f"{mode}: incomplete solve observation sequence")
    return records


def run_mode(mode: str, runtime_env: Path, out_dir: Path) -> dict[str, Any]:
    mode_dir = out_dir / mode
    mode_dir.mkdir(parents=True)
    episode_summary_path = mode_dir / "episode-summary.json"
    agent_args = {
        "inference_timeout_seconds": 10,
        "policy_scope": "task_specific_screenshot_only_ocr_and_pixels",
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
        "16",
        "--request-timeout-seconds",
        "15",
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
            "Only evaluator-delivered PNG frames, task instructions, and prior native-action "
            "receipts. No public_state, ground_truth, DOM, URL, browser handle, filesystem task "
            "state, or developer surface is provided to the policy."
        ),
        "classification": (
            "task-specific deterministic screenshot/OCR policy; complete runner solve, "
            "not a human run, general model-agent result, or difficulty calibration sample"
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
    observations = _observation_inventory(episode_dir, out_dir, mode)
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
        raise AssertionError(f"{mode}: policy did not stop from a visible PASS screen")
    if any(
        item.get("visible_task_ui_only_rule_present") is not True
        or item.get("screen_is_last_frame") is not True
        or item.get("frame_count") != EXPECTED_FRAMES[mode]
        for item in policy
    ):
        raise AssertionError(f"{mode}: incomplete screenshot-policy input manifest")
    decisions = [item["decision"] for item in policy]
    required_decisions = {
        "click_visible_privacy_controls_action",
        "reconcile_identity_switches",
        "reconcile_behaviour_switches",
        "open_behaviour_drawer",
        "review_current_choices",
        "click_visible_keep_current_choices_action",
        "finish_after_visible_pass",
    }
    if not required_decisions.issubset(decisions):
        raise AssertionError(
            f"{mode}: missing required visible decisions "
            f"{sorted(required_decisions.difference(decisions))}"
        )

    action_records = [
        action
        for turn in turns
        for action in (turn.get("actions") or [])
    ]
    if mode == "paused":
        if any(
            abs(float(action["task_time_delta_during_action_ms"])) > 5
            for action in action_records
        ):
            raise AssertionError("paused task time advanced during native input delivery")
        if any(
            status.get("required") is True
            and status.get("receipt_confirmed") is not True
            for action in action_records
            for status in action.get("action_delivery_statuses") or []
        ):
            raise AssertionError("paused action lacked a required trusted Chromium receipt")
    else:
        request_deltas = [
            float(request["task_time_delta_ms"])
            for turn in turns
            for request in turn.get("request_attempts") or []
        ]
        if sum(request_deltas) <= 20:
            raise AssertionError("live task clock did not advance during policy inference")

    condition = public_state["control_condition"]
    if condition.get("difficulty") != 3 or condition.get("interaction") != "full":
        raise AssertionError(f"{mode}: wrong controlled condition {condition}")
    if condition.get("real_time") != mode:
        raise AssertionError(f"{mode}: wrong controlled time label {condition}")

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
        "realtime_timing": relative(
            episode_dir / "realtime_timing.jsonl", out_dir
        ),
        "observations": observations,
        "decisions": decisions,
        "policy_turns": len(policy),
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
            "Complete authoritative runner submission from screenshot OCR and rendered pixels. "
            "This is not a human result, a general provider/model-agent result, or empirical "
            "difficulty calibration."
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
    with tempfile.TemporaryDirectory(prefix="consent-screenshot-solve-") as raw:
        runtime_env = build_runtime_environment(Path(raw), out_dir)
        results = {
            mode: run_mode(mode, runtime_env, out_dir)
            for mode in modes
        }

    if len(results) == 2:
        live = results["live"]
        paused = results["paused"]
        if live["task_seed"] != paused["task_seed"]:
            raise AssertionError("live and paused runs used different task seeds")
        if live["world_fingerprint"] != paused["world_fingerprint"]:
            raise AssertionError("live and paused runs used different generated worlds")

    sources = {
        "capture_driver": Path(__file__).resolve(),
        "screenshot_policy": (
            BENCHMARK / "tools" / "consent_gauntlet_screenshot_agent.py"
        ),
        "evaluator": EVALUATOR,
        "runner": BENCHMARK / "runner.py",
        "environment": ENVIRONMENT / "env.json",
        "controls": ENVIRONMENT / "controls.json",
        "task": (
            ENVIRONMENT
            / "tasks"
            / "consent_gauntlet_seed_0001"
            / "task.json"
        ),
        "browser": (
            BENCHMARK
            / "shared_runtime"
            / "app"
            / "mechanics"
            / "consent_gauntlet.js"
        ),
        "generator": (
            BENCHMARK
            / "shared_scripts"
            / "incubator_generators"
            / "consent_gauntlet.py"
        ),
        "grader": (
            BENCHMARK
            / "shared_runtime"
            / "server"
            / "incubator_graders"
            / "consent_gauntlet.py"
        ),
    }
    summary = {
        "ok": all(item["verifier"].get("passed") is True for item in results.values()),
        "environment": "Consent Gauntlet",
        "policy": "task-specific deterministic screenshot/OCR and rendered-pixel policy",
        "complete_authoritative_runner_submissions": True,
        "same_generated_world": len(results) < 2 or (
            results["live"]["world_fingerprint"]
            == results["paused"]["world_fingerprint"]
        ),
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
            "The retained episodes are complete authoritative runner passes from a "
            "task-specific policy whose only task input is the evaluator-delivered screenshot. "
            "They are not human/VNC usability evidence, general model-agent performance, or "
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
