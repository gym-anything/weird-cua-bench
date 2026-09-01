#!/usr/bin/env python3
"""Retain Turtle Forger observations delivered by the production evaluator.

The policy is a local screenshot/OCR transport probe.  It clicks the visible
SCAN MASTER control, records the runner's input frames and action receipt, and
stops without constructing or submitting a solution.  It is not human or
general computer-use-agent performance evidence.
"""

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

from PIL import Image, ImageChops, ImageStat


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "turtle_forger_env"
MATERIALIZER = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
EVALUATOR = BENCHMARK / "tools" / "run_realtime_evaluation.py"
TASK_IDS = {
    "live": "turtle_forger_d3_full_seed_0001",
    "paused": "turtle_forger_d3_full_seed_0001_tpaused",
}
SEED = 271828
EXPECTED_RESOLUTION = [1920, 1080]
EXPECTED_FRAMES = {"live": 1, "paused": 6}


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
        "canvas": public_state["canvas"],
        "start": public_state["start"],
        "command_palette": public_state["command_palette"],
        "runtime_target_segments": public_state["runtime_target_segments"],
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
    paused_task["id"] = f"{TASK_IDS['paused']}@0.1"
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
    shutil.copytree(materialized_tasks, runtime_env / "tasks")
    config = read_json(ENVIRONMENT / "env.json")
    if config.get("vnc", {}).get("enable") is not False:
        raise AssertionError("authoritative evidence requires VNC to remain disabled")
    config["recording"]["output_dir"] = str(
        (out_dir / "raw_episodes").resolve()
    )
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
                "distinct_frame_hashes": len(
                    {frame["sha256"] for frame in frames}
                ),
            }
        )
    if len(records) < 2:
        raise AssertionError(f"{mode}: missing initial or post-action observation")
    return records


def reference_region_difference(before: Path, after: Path) -> float:
    with Image.open(before).convert("RGB") as left, Image.open(after).convert("RGB") as right:
        # 1920x1080 scaling of the left reference plate in the 1280x720 page.
        crop = (34, 194, 703, 694)
        difference = ImageChops.difference(left.crop(crop), right.crop(crop))
        return round(sum(ImageStat.Stat(difference).mean), 4)


def run_mode(mode: str, runtime_env: Path, out_dir: Path) -> dict[str, Any]:
    mode_dir = out_dir / mode
    mode_dir.mkdir(parents=True)
    episode_summary_path = mode_dir / "episode-summary.json"
    # Measured from the exact initial 1920x1080 runner observation retained by
    # this evidence protocol. AUTO REPLAY runs the same ordered transient scan
    # repeatedly, so a slow live action/provider cycle still reaches later
    # strokes instead of landing after a one-shot scan has erased itself.
    scan_point = [647, 807]
    actions = [
        {"mouse": {"move": scan_point}},
        {"action": "wait", "time": 0.12},
        {"mouse": {"buttons": {"left_down": True}}},
        {"action": "wait", "time": 0.12},
        {"mouse": {"buttons": {"left_up": True}}},
    ]
    agent_args = {
        "transient_timeout_attempts": 1,
        "inference_timeout_seconds": 10,
        "expected_text_markers": [
            "BUREAU OF GEOMETRIC SEALS",
            "SCAN MASTER",
            "AUTO REPLAY",
            "PUNCH-CARD",
        ],
        "decision_label": "click_visible_auto_replay",
        "actions": actions,
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
                "purpose": (
                    "authoritative evaluator observation, retry, clock, and visible "
                    "AUTO REPLAY action probe; not a puzzle-solving result"
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
    expected_window = 0 if mode == "live" else 900
    if (
        effective.get("frames_per_observation") != EXPECTED_FRAMES[mode]
        or effective.get("observation_window_ms") != expected_window
    ):
        raise AssertionError(f"{mode}: unexpected observation schedule {effective}")
    if len(model_inputs) < 3:
        raise AssertionError(f"{mode}: timeout, retry, and post-action inputs are missing")
    if any(
        item.get("frame_count") != EXPECTED_FRAMES[mode]
        or item.get("screen_is_last_frame") is not True
        or item.get("visible_task_ui_only_rule_present") is not True
        for item in model_inputs
    ):
        raise AssertionError(f"{mode}: retained model input is incomplete")

    turns = [item for item in timing if item.get("event") == "turn"]
    first_turn = turns[0]
    attempts = first_turn["request_attempts"]
    if [item.get("outcome") for item in attempts] != ["error", "success"]:
        raise AssertionError(f"{mode}: single-layer timeout retry was not retained")
    if attempts[0].get("error_type") != "TimeoutError":
        raise AssertionError(f"{mode}: first request was not the simulated timeout")
    action = first_turn["actions"][0]
    statuses = action.get("action_delivery_statuses") or []
    required_statuses = [item for item in statuses if item.get("required") is True]
    if required_statuses and any(
        item.get("receipt_confirmed") is not True for item in required_statuses
    ):
        raise AssertionError(f"{mode}: required native input receipt was not confirmed")
    if mode == "paused":
        if any(abs(float(item["task_time_delta_ms"])) > 5 for item in attempts):
            raise AssertionError("paused task advanced during inference or retry")
        if action["clock_after_action"].get("controller_state") != "paused":
            raise AssertionError("paused action boundary did not retain the pause")
    elif sum(float(item["task_time_delta_ms"]) for item in attempts) <= 20:
        raise AssertionError("live task did not advance during inference and retry")

    initial_screen = out_dir / observations[0]["screen"]
    post_action_screen = out_dir / observations[1]["screen"]
    region_difference = reference_region_difference(initial_screen, post_action_screen)
    if region_difference <= 0.25:
        raise AssertionError(
            f"{mode}: AUTO REPLAY did not visibly change the reference plate ({region_difference})"
        )
    condition = public_state["control_condition"]
    if condition.get("difficulty") != 3 or condition.get("interaction") != "full":
        raise AssertionError(f"{mode}: evaluator loaded the wrong controlled condition")
    if condition.get("real_time") != mode:
        raise AssertionError(f"{mode}: task reports {condition.get('real_time')}")
    verifier = (episode_summary.get("info") or {}).get("verifier") or {}
    attempts_summary = episode_summary.get("attempts") or {}
    if verifier.get("passed") is not False or attempts_summary.get("submitted") is not False:
        raise AssertionError("transport probe must remain a no-submission result")

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
        "realtime_timing": relative(
            episode_dir / "realtime_timing.jsonl", out_dir
        ),
        "effective_runner_options": effective,
        "first_model_request_attempts": attempts,
        "action": action,
        "reference_region_difference": region_difference,
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
    with tempfile.TemporaryDirectory(prefix="turtle-authoritative-evaluator-") as raw:
        runtime_env = build_runtime_environment(Path(raw), out_dir)
        live = run_mode("live", runtime_env, out_dir)
        paused = run_mode("paused", runtime_env, out_dir)
    if live["task_seed"] != paused["task_seed"]:
        raise AssertionError("live and paused tasks use different generator seeds")
    if live["world_fingerprint"] != paused["world_fingerprint"]:
        raise AssertionError("live and paused tasks do not preserve the generated world")

    source_paths = {
        "capture_driver": Path(__file__).resolve(),
        "evaluator": EVALUATOR,
        "observation_probe": BENCHMARK / "tools" / "authoritative_observation_probe_agent.py",
        "materializer": MATERIALIZER,
        "runner": BENCHMARK / "runner.py",
        "guest_capture": BENCHMARK / "shared_scripts" / "capture_observation_window.py",
        "environment": ENVIRONMENT / "env.json",
        "controls": ENVIRONMENT / "controls.json",
        "browser": BENCHMARK / "shared_runtime" / "app" / "mechanics" / "turtle_forger.js",
    }
    summary = {
        "ok": True,
        "environment": "Turtle Forger",
        "authoritative_evaluator_action_cycle": True,
        "same_generated_world": True,
        "settings": {
            "configured_observation_window_ms": 900,
            "configured_frames_per_observation": 6,
            "effective_live_observation": "one instantaneous frame",
            "effective_paused_observation": "six chronological frames over 900 ms",
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
            "These are the exact task description and frames received by a local "
            "screenshot/OCR evaluator transport probe. They establish delivery, retry, "
            "live-versus-paused inference time, AUTO REPLAY input receipt, and the "
            "post-action observation. The probe did not solve or submit Turtle Forger "
            "and is not human-usability or general computer-use-agent performance evidence."
        ),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "evidence": str(out_dir)}, sort_keys=True))


if __name__ == "__main__":
    main()
