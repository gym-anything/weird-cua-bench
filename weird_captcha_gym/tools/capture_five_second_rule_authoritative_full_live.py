#!/usr/bin/env python3
"""Retain a screenshot-only authoritative L4/Full/Live completion.

The fixed replay policy consumes only evaluator-delivered screenshots.  Each
action group is gated on OCR text from the current visible dispatch, and its
coordinates/cadence are measurements from the retained 1920x1080 UI.  The
policy is evidence for authoritative transport playability, not a general
agent baseline or empirical difficulty calibration.
"""

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

from weird_captcha_gym.tools import (
    capture_five_second_rule_authoritative_evaluator_evidence as probe,
)


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments/five_second_rule_env"
EVALUATOR = BENCHMARK / "tools/run_realtime_evaluation.py"
TASK_ID = "five_second_rule_d4_full_seed_0001"
SEED = 32
RESOLUTION = [1920, 1080]


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


def expected_world() -> dict[str, Any]:
    generator_path = BENCHMARK / "shared_scripts/incubator_generators/five_second_rule.py"
    spec = importlib.util.spec_from_file_location("five_second_full_live_expected", generator_path)
    if spec is None or spec.loader is None:
        raise ImportError(generator_path)
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    task = read_json(ENVIRONMENT / "tasks/five_second_rule_seed_0001/task.json")
    controls = read_json(ENVIRONMENT / "controls.json")
    task["_control_condition"] = {
        "difficulty": 4,
        "interaction": "full",
        "real_time": "live",
        "difficulty_parameters": copy.deepcopy(
            controls["difficulty"]["4"]["parameters"]
        ),
    }
    public, _truth = generator.generate(task, f"{SEED}:refresh:1")
    return public


def action_groups() -> list[dict[str, Any]]:
    # Points are centers measured from the visible 1920x1080 stage.  Each
    # expected marker must be present in OCR from the exact delivered frame
    # before the policy releases the corresponding native gesture.
    return [
        {
            "decision_label": "hold_visible_violet_kite_through_amber_flash",
            "expected_text_markers": ["HOLD THE VIOLET KITE"],
            "refresh_on_marker_miss": True,
            "actions": [
                {"action": "wait", "time": 0.5},
                {"mouse": {"move": [333, 506]}},
                {"mouse": {"buttons": {"left_down": True}}},
                {"action": "wait", "time": 0.61},
                {"mouse": {"buttons": {"left_up": True}}},
            ],
        },
        {
            "decision_label": "drag_visible_coral_ring_into_open_coral_bay",
            "expected_text_markers": ["MOVE THE CORAL RING"],
            "refresh_on_marker_miss": True,
            "actions": [
                {"action": "wait", "time": 0.15},
                {"mouse": {"move": [372, 724]}},
                {"mouse": {"buttons": {"left_down": True}}},
                {"mouse": {"move": [1540, 540]}},
                {"mouse": {"buttons": {"left_up": True}}},
            ],
        },
        {
            "decision_label": "tag_visible_ice_crown_at_white_gate",
            "expected_text_markers": ["FOLLOW THE ICE CROWN"],
            "refresh_on_marker_miss": True,
            "actions": [
                {"action": "wait", "time": 0.3},
                {"mouse": {"left_click": [758, 731]}},
            ],
        },
        {
            "decision_label": "flick_visible_violet_bloom_east_at_west_heading",
            "expected_text_markers": ["VIOLET BLOOM POINTER FACES WEST"],
            "refresh_on_marker_miss": True,
            "actions": [
                {"action": "wait", "time": 0.55},
                {"mouse": {"move": [1393, 482]}},
                {"mouse": {"buttons": {"left_down": True}}},
                {"mouse": {"move": [1525, 482]}},
                {"mouse": {"buttons": {"left_up": True}}},
            ],
        },
        {
            "decision_label": "tap_unique_visible_down_left_then_plain_relay_pair",
            "expected_text_markers": ["DOWN-LEFT OF THE ROSE RING"],
            "refresh_on_marker_miss": True,
            "actions": [
                {"mouse": {"left_click": [633, 816]}},
                {"mouse": {"left_click": [269, 458]}},
            ],
        },
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ENVIRONMENT / "evidence_docs/authoritative_full_live",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    expected = expected_world()
    groups = action_groups()
    expected_order = [
        "sync_hold",
        "shutter_drop",
        "gate_tag",
        "vector_flick",
        "relay_pair",
    ]
    if [item["family"] for item in expected["rounds"]] != expected_order:
        raise AssertionError("seed-32 visible replay world changed")

    with tempfile.TemporaryDirectory(prefix="five-second-authoritative-full-live-") as raw:
        runtime_env = probe.build_runtime_environment(Path(raw), out_dir)
        episode_summary_path = out_dir / "episode-summary.json"
        agent_args = {
            "transient_timeout_attempts": 0,
            "inference_timeout_seconds": 10,
            "expected_text_markers": [
                marker
                for group in groups
                for marker in group["expected_text_markers"]
            ],
            "action_groups": groups,
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
            "live",
            "--seed",
            str(SEED),
            "--steps",
            "8",
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
            "visible_coordinate_measurements": {
                "viewport": RESOLUTION,
                "source": "retained evaluator screenshots",
                "logical_stage_labels_used_only_for_post_run_validation": True,
            },
            "isolation": {
                "host_foreground_application": False,
                "environment_vnc_ui_enabled": False,
                "interactive_vnc_client_opened": False,
                "runner_background_virtual_display": True,
                "ephemeral_virtual_machine": True,
                "existing_browser_profile": False,
            },
        }
        (out_dir / "run-command.json").write_text(
            json.dumps(run_record, indent=2) + "\n", encoding="utf-8"
        )
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        (out_dir / "evaluator.log").write_text(
            completed.stdout + completed.stderr, encoding="utf-8"
        )
        if completed.returncode:
            raise RuntimeError(
                f"authoritative full-live evaluator exited {completed.returncode}; "
                f"see {out_dir / 'evaluator.log'}"
            )

    episode_summary = read_json(episode_summary_path)
    episode_dir = Path(episode_summary["episode_dir"]).resolve()
    timing_path = episode_dir / "realtime_timing.jsonl"
    model_path = episode_dir / "model_input_manifest.jsonl"
    timing = read_jsonl(timing_path)
    model_inputs = read_jsonl(model_path)
    observations = probe.observation_records(
        episode_dir, out_dir, "live", expected_frames=6
    )
    verifier = (episode_summary.get("info") or {}).get("verifier") or {}
    attempts = episode_summary.get("attempts") or {}
    if verifier.get("passed") is not True or verifier.get("decided") is not True:
        raise AssertionError(f"authoritative Full/Live verifier did not pass: {verifier}")
    if attempts != {"graded_failures": 0, "graded_total": 1, "submitted": True}:
        raise AssertionError(f"unexpected submission record: {attempts}")

    action_records = [
        action
        for turn in timing
        if turn.get("event") == "turn"
        for action in turn.get("actions") or []
    ]
    if len(action_records) != 5:
        raise AssertionError(f"expected five gesture records, got {len(action_records)}")
    expected_counts = [5, 5, 2, 5, 2]
    for index, (record, count) in enumerate(zip(action_records, expected_counts)):
        if record.get("action_count") != count or record.get("transport_action_count") != 1:
            raise AssertionError(f"gesture {index + 1} was not one atomic transport group")
        statuses = record.get("action_delivery_statuses") or []
        if len(statuses) != 1 or statuses[0].get("receipt_confirmed") is not True:
            raise AssertionError(f"gesture {index + 1} lacks one native browser receipt")
        if float(record["task_time_delta_during_action_ms"]) >= 5000:
            raise AssertionError(f"gesture {index + 1} exceeded its visible dispatch")

    decisions = [
        item
        for item in model_inputs
        if str(item.get("decision") or "").startswith(
            ("hold_", "drag_", "tag_", "flick_", "tap_")
        )
    ]
    if len(decisions) != 5 or any(
        item.get("visible_group_marker_confirmed") is not True for item in decisions
    ):
        raise AssertionError("not every gesture was released by its visible OCR marker")
    if any(item.get("visible_task_ui_only_rule_present") is not True for item in model_inputs):
        raise AssertionError("visible-task-only rule missing from a model request")
    if any(item.get("frame_count") != 6 for item in model_inputs):
        raise AssertionError("the authoritative Live model did not receive six frames")

    task_result_path = episode_dir / "task_result.json"
    task_result = read_json(task_result_path)
    exported_result = task_result.get("result") or {}
    if (
        exported_result.get("completed") is not True
        or (exported_result.get("server_grade") or {}).get("passed") is not True
    ):
        raise AssertionError("passing task export was not retained")
    for item in observations:
        with Image.open(out_dir / item["screen"]) as image:
            if list(image.size) != RESOLUTION:
                raise AssertionError("authoritative screenshot resolution changed")

    source_paths = {
        "capture_driver": Path(__file__).resolve(),
        "evaluator": EVALUATOR,
        "observation_agent": BENCHMARK / "tools/authoritative_observation_probe_agent.py",
        "runner": BENCHMARK / "runner.py",
        "input_batch": BENCHMARK / "shared_scripts/inject_input_batch.py",
        "observation_capture": BENCHMARK / "shared_scripts/capture_observation_window.py",
        "browser": BENCHMARK / "shared_runtime/app/mechanics/five_second_rule.js",
        "generator": BENCHMARK / "shared_scripts/incubator_generators/five_second_rule.py",
        "grader": BENCHMARK / "shared_runtime/server/incubator_graders/five_second_rule.py",
        "verifier": ENVIRONMENT / "tasks/five_second_rule_seed_0001/verifier.py",
    }
    summary = {
        "ok": True,
        "environment": "Five-Second Rule",
        "condition": {"difficulty": 4, "interaction": "full", "real_time": "live"},
        "seed": SEED,
        "task_seed": f"{SEED}:refresh:1",
        "challenge_id": expected["challenge_id"],
        "world_fingerprint": expected["world_fingerprint"],
        "round_order": expected_order,
        "visible_task_only": True,
        "actual_inference_backend": "Tesseract 5 LSTM OCR plus fixed pixel-coordinate replay",
        "general_agent_or_difficulty_calibration": False,
        "verifier": verifier,
        "attempts": attempts,
        "action_records": action_records,
        "model_input_manifest": relative(model_path, out_dir),
        "realtime_timing": relative(timing_path, out_dir),
        "task_result_export": relative(task_result_path, out_dir),
        "task_result": task_result,
        "observations": observations,
        "first_frame_task_time_ms": observations[0]["time_status"]["task_time_ms"],
        "source_sha256": {name: sha256(path) for name, path in source_paths.items()},
        "request_policy": next(
            item for item in timing if item.get("event") == "setup"
        )["request_retry_policy"],
        "isolation": run_record["isolation"],
        "evidence_boundary": (
            "This fixed-seed screenshot-only replay establishes that every Full gesture "
            "can traverse the authoritative Live runner inside its unchanged five-second "
            "window and produce a passing export/verifier result. It is not a general "
            "computer-use-agent baseline, human/VNC evidence, or empirical L4 calibration."
        ),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"ok": True, "evidence": str(out_dir)}, sort_keys=True))


if __name__ == "__main__":
    main()
