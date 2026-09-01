#!/usr/bin/env python3
"""Preserve evaluator-delivered Five-Second Rule observations and input receipts."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
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
ENVIRONMENT = BENCHMARK / "environments/five_second_rule_env"
MATERIALIZER = BENCHMARK / "tools/materialize_controlled_tasks.py"
EVALUATOR = BENCHMARK / "tools/run_realtime_evaluation.py"
TASK_IDS = {
    "live": "five_second_rule_d4_full_seed_0001",
    "paused": "five_second_rule_d4_full_seed_0001_tpaused",
}
SEED = 3
EXPECTED_RESOLUTION = [1920, 1080]
EXPECTED_FRAMES = {"live": 6, "paused": 6}
OBSERVATION_WINDOWS = {"live": 600, "paused": 600}

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
    shutil.copytree(BENCHMARK / "shared_runtime", runtime_benchmark / "shared_runtime")
    shutil.copytree(materialized_tasks, runtime_env / "tasks")
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
    *,
    expected_frames: int | None = None,
) -> list[dict[str, Any]]:
    records = []
    expected_frame_count = (
        EXPECTED_FRAMES[mode] if expected_frames is None else expected_frames
    )
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
                    f"{mode} {turn_dir.name}: got {resolution}, "
                    f"expected {EXPECTED_RESOLUTION}"
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
        if len(frames) != expected_frame_count:
            raise AssertionError(
                f"{mode} {turn_dir.name}: expected {expected_frame_count} frames, "
                f"got {len(frames)}"
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


def expected_initial_world(mode: str) -> dict[str, Any]:
    generator_path = (
        BENCHMARK / "shared_scripts/incubator_generators/five_second_rule.py"
    )
    spec = importlib.util.spec_from_file_location(
        f"five_second_authoritative_expected_{mode}", generator_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(generator_path)
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    task = read_json(
        ENVIRONMENT / "tasks/five_second_rule_seed_0001/task.json"
    )
    controls = read_json(ENVIRONMENT / "controls.json")
    task["_control_condition"] = {
        "difficulty": 4,
        "interaction": "full",
        "real_time": mode,
        "difficulty_parameters": copy.deepcopy(
            controls["difficulty"]["4"]["parameters"]
        ),
    }
    public, _truth = generator.generate(task, f"{SEED}:refresh:1")
    return public


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ENVIRONMENT / "evidence_docs/authoritative_evaluator",
    )
    return parser.parse_args()


def run_mode(mode: str, runtime_env: Path, out_dir: Path) -> dict[str, Any]:
    mode_dir = out_dir / mode
    mode_dir.mkdir(parents=True)
    episode_summary_path = mode_dir / "episode-summary.json"
    # Seed 3 starts on the L4 relay. This point is the center of the unique
    # visible DOWN-LEFT answer in a 1920x1080 render, measured in an isolated
    # headless preflight with the same viewport and generated world.
    visible_point = [633, 814]
    agent_args = {
        "transient_timeout_attempts": 1,
        "inference_timeout_seconds": 10,
        "expected_text_markers": [
            "FIVE SECOND",
            "READ TWO LINES",
            "FIRST TAP",
        ],
        "decision_label": "click_unique_visible_down_left_relay_token",
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
                "coordinate_preflight": {
                    "viewport": EXPECTED_RESOLUTION,
                    "headless": True,
                    "fresh_temporary_profile": True,
                    "loopback_only": True,
                    "first_visible_answer_center": [633.109, 813.812],
                },
                "isolation": {
                    "host_foreground_application": False,
                    "environment_vnc_ui_enabled": False,
                    "interactive_vnc_client_opened": False,
                    "runner_background_virtual_display": True,
                    "ephemeral_virtual_machine": True,
                    "existing_browser_profile": False,
                },
                "purpose": (
                    "authoritative evaluator frame delivery, inference-time clock, "
                    "single-layer retry, native input receipt, and post-action observation; "
                    "not a task-solving result"
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
            f"{mode} evaluator exited {completed.returncode}; "
            f"see {mode_dir / 'evaluator.log'}"
        )

    episode_summary = read_json(episode_summary_path)
    episode_dir = Path(episode_summary["episode_dir"]).resolve()
    timing = read_jsonl(episode_dir / "realtime_timing.jsonl")
    model_inputs = read_jsonl(episode_dir / "model_input_manifest.jsonl")
    public_state = read_json(episode_dir / "public_state.json")
    current_task = read_json(episode_dir / "current_task.json")
    observations = observation_records(episode_dir, out_dir, mode)
    expected_initial = expected_initial_world(mode)

    setup = next(item for item in timing if item.get("event") == "setup")
    effective = setup["effective_runner_options"]
    if (
        effective.get("frames_per_observation") != EXPECTED_FRAMES[mode]
        or effective.get("observation_window_ms") != OBSERVATION_WINDOWS[mode]
    ):
        raise AssertionError(f"{mode}: unexpected observation schedule {effective}")
    if len(model_inputs) < 3:
        raise AssertionError(f"{mode}: timeout, retry, and post-action requests missing")
    for item in model_inputs:
        if (
            item.get("frame_count") != EXPECTED_FRAMES[mode]
            or item.get("screen_is_last_frame") is not True
            or item.get("visible_task_ui_only_rule_present") is not True
        ):
            raise AssertionError(f"{mode}: retained model input is incomplete")
    initial_success = next(
        item
        for item in model_inputs
        if item.get("outcome") == "success"
        and item.get("successful_turn_before_request") == 0
    )
    normalized_ocr = " ".join(str(initial_success.get("ocr_excerpt") or "").split())
    for line in expected_initial["rounds"][0]["instruction"]:
        if line not in normalized_ocr:
            raise AssertionError(
                f"{mode}: initial evaluator OCR does not match expected seed-3 world: {line}"
            )

    turns = [item for item in timing if item.get("event") == "turn"]
    first_turn = turns[0]
    attempts = first_turn["request_attempts"]
    if [item.get("outcome") for item in attempts] != ["error", "success"]:
        raise AssertionError(f"{mode}: required single-layer retry was not retained")
    if attempts[0].get("error_type") != "TimeoutError":
        raise AssertionError(f"{mode}: first request was not the simulated timeout")
    action = first_turn["actions"][0]
    statuses = action.get("action_delivery_statuses") or []
    required_statuses = [item for item in statuses if item.get("required") is True]
    if len(required_statuses) != 1 or any(
        item.get("receipt_confirmed") is not True for item in required_statuses
    ):
        raise AssertionError(
            f"{mode} atomic native gesture lacks its trusted browser receipt"
        )
    observed_types = {
        event.get("type")
        for event in required_statuses[0].get("observed_events") or []
    }
    if not {"pointerdown", "pointerup", "click"} <= observed_types:
        raise AssertionError(f"{mode} receipt lacks the complete click: {observed_types}")
    if action.get("action_count") != 3 or action.get("transport_action_count") != 1:
        raise AssertionError(f"{mode} gesture did not use one atomic transport action")
    if mode == "paused":
        if any(abs(float(item["task_time_delta_ms"])) > 5 for item in attempts):
            raise AssertionError("paused task time advanced during inference or retry")
        if abs(float(action["task_time_delta_during_action_ms"])) > 5:
            raise AssertionError("paused native action advanced task time")
        observation_delta = (
            float(action["task_time_ms"])
            - float(action["task_time_after_execution_ms"])
        )
        if not 595 <= observation_delta <= 605:
            raise AssertionError(
                f"paused post-action observation advanced {observation_delta} ms"
            )
        if action["clock_after_action"].get("controller_state") != "paused":
            raise AssertionError("paused trusted-input boundary did not retain pause")
    else:
        if sum(float(item["task_time_delta_ms"]) for item in attempts) <= 20:
            raise AssertionError("live task time did not advance during inference and retry")
        if float(action["task_time_delta_during_action_ms"]) >= 5000:
            raise AssertionError("live atomic click still exceeded the complete dispatch")

    initial_screen = out_dir / observations[0]["screen"]
    post_action_screen = out_dir / observations[1]["screen"]
    if sha256(initial_screen) == sha256(post_action_screen):
        raise AssertionError(f"{mode}: post-action evaluator observation did not change")

    condition = public_state["control_condition"]
    if condition.get("difficulty") != 4 or condition.get("interaction") != "full":
        raise AssertionError(f"{mode}: evaluator loaded the wrong condition")
    if condition.get("real_time") != mode:
        raise AssertionError(f"{mode}: task reports {condition.get('real_time')}")
    verifier = (episode_summary.get("info") or {}).get("verifier") or {}
    attempts_summary = episode_summary.get("attempts") or {}
    if verifier.get("passed") is not False:
        raise AssertionError("transport probe must not be reported as a task pass")
    if attempts_summary.get("submitted") is not False:
        raise AssertionError(f"{mode} one-click probe unexpectedly submitted the task")

    return {
        "mode": mode,
        "task_id": TASK_IDS[mode],
        "seed": SEED,
        "task_seed": f"{SEED}:refresh:1",
        "challenge_id": expected_initial["challenge_id"],
        "world_fingerprint": expected_initial["world_fingerprint"],
        "first_round_family": expected_initial["rounds"][0]["family"],
        "first_round_instruction": expected_initial["rounds"][0]["instruction"],
        "initial_world_instruction_confirmed_by_evaluator_ocr": True,
        "final_current_task_seed_after_probe": current_task["seed"],
        "final_public_challenge_after_probe": public_state["challenge_id"],
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
        "native_action_receipts_confirmed": True,
        "action_delivery_statuses": statuses,
        "screen_is_final_frame_for_all_requests": True,
        "visible_task_ui_only_rule_present_for_all_requests": True,
        "request_retry_policy": setup["request_retry_policy"],
        "request_timeout_seconds": setup["request_timeout_seconds"],
        "request_attempts": setup["request_attempts"],
        "attempts_summary": attempts_summary,
        "verifier": verifier,
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
    with tempfile.TemporaryDirectory(prefix="five-second-authoritative-evaluator-") as raw:
        runtime_env = build_runtime_environment(Path(raw), out_dir)
        live = run_mode("live", runtime_env, out_dir)
        paused = run_mode("paused", runtime_env, out_dir)

    if live["task_seed"] != paused["task_seed"]:
        raise AssertionError("live and paused tasks have different generator seeds")
    if live["world_fingerprint"] != paused["world_fingerprint"]:
        raise AssertionError("live and paused tasks do not preserve the same world")
    source_paths = {
        "capture_driver": Path(__file__).resolve(),
        "evaluator": EVALUATOR,
        "observation_probe": BENCHMARK / "tools/authoritative_observation_probe_agent.py",
        "materializer": MATERIALIZER,
        "runner": BENCHMARK / "runner.py",
        "guest_capture": BENCHMARK / "shared_scripts/capture_observation_window.py",
        "input_batch": BENCHMARK / "shared_scripts/inject_input_batch.py",
        "environment": ENVIRONMENT / "env.json",
        "controls": ENVIRONMENT / "controls.json",
        "base_task": ENVIRONMENT / "tasks/five_second_rule_seed_0001/task.json",
        "browser": BENCHMARK / "shared_runtime/app/mechanics/five_second_rule.js",
        "generator": BENCHMARK / "shared_scripts/incubator_generators/five_second_rule.py",
        "grader": BENCHMARK / "shared_runtime/server/incubator_graders/five_second_rule.py",
    }
    summary = {
        "ok": True,
        "environment": "Five-Second Rule",
        "authoritative_evaluator_action_cycle": True,
        "same_generated_world": True,
        "settings": {
            "configured_observation_window_ms": 600,
            "configured_frames_per_observation": 6,
            "effective_live_observation": "six chronological frames over 600 ms",
            "effective_paused_observation": "six chronological frames over 600 ms",
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
        "source_sha256": {
            name: sha256(path) for name, path in source_paths.items()
        },
        "evidence_boundary": (
            "These are the exact frames and task description received by a local "
            "screenshot-only evaluator transport probe. They establish evaluator delivery, "
            "live/paused inference-time behavior, finite single-layer retry, native Chromium "
            "input receipts, atomic gesture transport, and the post-action observation cycle. "
            "Neither one-click relay probe submits or solves the puzzle, and neither counts as human-usability or "
            "general computer-use-agent performance evidence."
        ),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "evidence": str(out_dir)}, sort_keys=True))


if __name__ == "__main__":
    main()
