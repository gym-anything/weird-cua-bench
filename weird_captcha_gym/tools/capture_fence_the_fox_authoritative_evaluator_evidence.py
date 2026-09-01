#!/usr/bin/env python3
"""Capture Fence the Fox observations through the actual benchmark runner.

The coordinate preflight is an isolated, headless, loopback-only browser
check.  Every artifact called an evaluator observation is subsequently
produced by WeirdCaptchaRunner and delivered to the screenshot-only probe.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from PIL import Image
from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments/fence_the_fox_env"
MATERIALIZER = BENCHMARK / "tools/materialize_controlled_tasks.py"
EVALUATOR = BENCHMARK / "tools/run_realtime_evaluation.py"
SETUP = BENCHMARK / "shared_scripts/setup_task.py"
SERVER = BENCHMARK / "shared_runtime/server/weird_captcha_server.py"
GRADER = BENCHMARK / "shared_runtime/server/incubator_graders/fence_the_fox.py"
APP = BENCHMARK / "shared_runtime/app"
TASK_IDS = {
    ("simplified", "live"): "fence_the_fox_d3_simplified_seed_0001",
    ("simplified", "paused"): "fence_the_fox_d3_simplified_seed_0001_tpaused",
    ("full", "live"): "fence_the_fox_d3_full_seed_0001",
    ("full", "paused"): "fence_the_fox_d3_full_seed_0001_tpaused",
}
SEED = 271828
RESOLUTION = [1920, 1080]
WINDOW_MS = 480


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FOX_GRADER = load_module("fence_the_fox_evidence_grader", GRADER)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ENVIRONMENT / "evidence_docs/authoritative_evaluator",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected an object in {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def world_fingerprint(state: dict[str, Any]) -> str:
    world = {
        key: state[key]
        for key in (
            "radius",
            "cells",
            "fox_start",
            "initial_fences",
            "stake_budget",
            "wind_start",
            "runtime_wind_sequence",
            "runtime_driver_patterns",
            "parameters",
            "palette",
        )
    }
    return hashlib.sha256(
        json.dumps(world, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def find_escape_plan(truth: dict[str, Any]) -> list[list[int]]:
    """Find a legal visible-input path that lets the current fox escape."""

    radius = int(truth["radius"])
    budget = int(truth["stake_budget"])
    wind_sequence = [int(value) for value in truth["wind_sequence"]]
    cells = sorted(
        (tuple(item) for item in truth["cells"]),
        key=lambda item: (item[1], item[0]),
    )
    initial_fox = tuple(truth["fox_start"])
    initial_blocked = frozenset(tuple(item) for item in truth["initial_fences"])
    frontier = [(initial_fox, initial_blocked, [])]
    seen = {(initial_fox, initial_blocked)}
    for depth in range(budget):
        following = []
        for fox, blocked, path in frontier:
            for placement in cells:
                if placement == fox or placement in blocked:
                    continue
                next_blocked = blocked | {placement}
                reply = FOX_GRADER._fox_choice(
                    radius,
                    fox,
                    next_blocked,
                    wind_sequence[depth],
                )
                candidate = [*path, [placement[0], placement[1]]]
                if reply["outcome"] == "escaped":
                    return candidate
                if reply["outcome"] != "moved":
                    continue
                state = (reply["fox"], next_blocked)
                if state in seen:
                    continue
                seen.add(state)
                following.append((reply["fox"], next_blocked, candidate))
        frontier = following
    raise AssertionError("could not find a legal escape transcript for boundary evidence")


def reserve_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def build_runtime_environment(temporary: Path, out_dir: Path) -> tuple[Path, Path]:
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
    tasks = materialized / ENVIRONMENT.name / "tasks"
    for interaction in ("simplified", "full"):
        live_id = TASK_IDS[(interaction, "live")]
        paused_id = TASK_IDS[(interaction, "paused")]
        paused_dir = tasks / paused_id
        shutil.copytree(tasks / live_id, paused_dir)
        for script in paused_dir.glob("*.sh"):
            script.write_text(
                script.read_text(encoding="utf-8").replace(live_id, paused_id),
                encoding="utf-8",
            )
        task = read_json(paused_dir / "task.json")
        task["id"] = f"{paused_id}@0.2"
        task["name"] = f"{task['name']} · Paused Time"
        task["hooks"] = {
            key: value.replace(live_id, paused_id)
            for key, value in task["hooks"].items()
        }
        task["metadata"]["control_condition"]["real_time"] = "paused"
        write_json(paused_dir / "task.json", task)

    runtime_benchmark = temporary / "weird_captcha_gym"
    runtime_env = runtime_benchmark / "environments" / ENVIRONMENT.name
    runtime_env.mkdir(parents=True)
    shutil.copytree(BENCHMARK / "shared_runtime", runtime_benchmark / "shared_runtime")
    shutil.copytree(tasks, runtime_env / "tasks")
    config = read_json(ENVIRONMENT / "env.json")
    if config.get("vnc", {}).get("enable") is not False:
        raise AssertionError("authoritative evidence requires VNC to stay disabled")
    if config["runner_options"] != {
        "observation_window_ms": WINDOW_MS,
        "frames_per_observation": 1,
        "play_time_seconds": 180,
    }:
        raise AssertionError("the target shared observation schedule changed")
    config["recording"]["output_dir"] = str((out_dir / "raw_episodes").resolve())
    for mount in config["mounts"]:
        if mount.get("target") == "/workspace/tasks":
            mount["source"] = str((runtime_env / "tasks").resolve())
    write_json(runtime_env / "env.json", config)
    return runtime_env, tasks


def start_preflight_server(task: Path, state_dir: Path) -> tuple[subprocess.Popen[bytes], int]:
    subprocess.run(
        [
            sys.executable,
            "-B",
            str(SETUP),
            "--task-json",
            str(task),
            "--state-dir",
            str(state_dir),
            "--seed",
            str(SEED),
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    port = reserve_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-B",
            str(SERVER),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--app-dir",
            str(APP),
            "--state-dir",
            str(state_dir),
        ],
        cwd=ROOT,
        env={**os.environ, "WEIRD_CAPTCHA_CHALLENGE_SEED": str(SEED)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5).read()
            return process, port
        except Exception:
            time.sleep(0.1)
    process.kill()
    raise TimeoutError("isolated coordinate preflight server did not start")


def stop_process(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()


def center(box: dict[str, float]) -> list[int]:
    return [round(box["x"] + box["width"] / 2), round(box["y"] + box["height"] / 2)]


def coordinate_preflight(temporary: Path, tasks: Path, out_dir: Path) -> dict[str, Any]:
    state_dir = temporary / "coordinate-preflight-state"
    state_dir.mkdir()
    process, port = start_preflight_server(
        tasks / TASK_IDS[("simplified", "live")] / "task.json",
        state_dir,
    )
    profile = temporary / "fresh-headless-coordinate-profile"
    screenshot = out_dir / "coordinate_preflight/direct-page-not-model-observation.png"
    screenshot.parent.mkdir(parents=True)
    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(profile),
                headless=True,
                viewport={"width": RESOLUTION[0], "height": RESOLUTION[1]},
                device_scale_factor=1,
            )
            page = context.pages[0]
            page.goto(
                f"http://127.0.0.1:{port}/?time_mode=paused&start_paused=1&time_control=1",
                wait_until="domcontentloaded",
            )
            expect(page.locator(".fence-fox-captcha")).to_be_visible(timeout=8_000)
            cells: dict[str, list[int]] = {}
            cell_half_sizes: dict[str, float] = {}
            for locator in page.locator(".fox-cell").all():
                cell_key = str(locator.get_attribute("data-cell-key"))
                box = locator.bounding_box()
                if box is None:
                    raise AssertionError(f"cell {cell_key} has no visible hit box")
                cells[cell_key] = center(box)
                cell_half_sizes[cell_key] = round(box["width"] / 2, 3)
            token_box = page.locator("#fox-stake-token").bounding_box()
            if token_box is None:
                raise AssertionError("stake token has no visible hit box")
            prompt = page.locator(".fox-header > p").inner_text()
            tutorial_selectors = (
                ".fox-right-rail",
                ".fox-policy-card",
                ".fox-wind-card",
                ".fox-rule-strip",
                ".fox-legend",
                ".fox-supply-card p",
            )
            tutorial_counts = {selector: page.locator(selector).count() for selector in tutorial_selectors}
            if any(tutorial_counts.values()):
                raise AssertionError(f"persistent tutorial nodes remain: {tutorial_counts}")
            normalized = prompt.upper()
            required = (
                "CLICK AN OPEN HEX",
                "SHORTEST OPEN ROUTE",
                "MORE SHORTEST CONTINUATIONS",
                "MORE OPEN NEIGHBORS",
                "CURRENT WIND",
                "WIND ORDER CHANGES AFTER EVERY FOX STEP",
                "CUTTING EVERY OPEN ROUTE TO THE RIM",
            )
            if any(item not in normalized for item in required):
                raise AssertionError(f"generated prompt is incomplete: {prompt}")
            page.screenshot(path=str(screenshot))
            context.close()
    finally:
        stop_process(process)
    public = read_json(state_dir / "public_state.json")
    truth = read_json(state_dir / "ground_truth.json")
    record = {
        "purpose": "coordinate-only scripted transport preflight; not a model observation or agent solve",
        "isolation": {
            "headless": True,
            "fresh_temporary_profile": True,
            "loopback_only": True,
            "existing_browser_profile": False,
            "foreground_application": False,
        },
        "resolution": RESOLUTION,
        "cells": cells,
        "cell_half_sizes": cell_half_sizes,
        "stake_token_center": center(token_box),
        "prompt": prompt,
        "tutorial_counts": tutorial_counts,
        "screenshot": relative(screenshot, out_dir),
        "screenshot_sha256": sha256(screenshot),
        "initial_public_state": public,
        "initial_ground_truth": truth,
        "world_fingerprint": world_fingerprint(public),
    }
    write_json(out_dir / "coordinate_preflight/preflight.json", record)
    return record


def click_actions(point: list[int]) -> list[dict[str, Any]]:
    return [
        {"mouse": {"move": point}},
        {"mouse": {"buttons": {"left_down": True}}},
        {"mouse": {"buttons": {"left_up": True}}},
    ]


def drag_actions(start: list[int], end: list[int]) -> list[dict[str, Any]]:
    points = [
        [round(start[0] + (end[0] - start[0]) * fraction), round(start[1] + (end[1] - start[1]) * fraction)]
        for fraction in (0.3, 0.6, 1.0)
    ]
    return [
        {"mouse": {"move": start}},
        {"mouse": {"buttons": {"left_down": True}}},
        *({"mouse": {"move": point}} for point in points),
        {"mouse": {"buttons": {"left_up": True}}},
    ]


def arm_driver_actions(start: list[int], end: list[int]) -> list[dict[str, Any]]:
    points = [
        [round(start[0] + (end[0] - start[0]) * fraction), round(start[1] + (end[1] - start[1]) * fraction)]
        for fraction in (0.3, 0.6, 1.0)
    ]
    return [
        {"mouse": {"move": start}},
        {"mouse": {"buttons": {"left_down": True}}},
        *(
            action
            for point in points
            for action in (
                {"mouse": {"move": point}},
                {"action": "wait", "time": 0.04},
            )
        ),
        {"action": "wait", "time": 0.12},
    ]


def seat_driver_actions(center_point: list[int], half_size: float, pattern: list[int]) -> list[dict[str, Any]]:
    checkpoints = []
    for angle_index in pattern:
        angle = int(angle_index) * math.pi / 6 - math.pi / 2
        checkpoints.append([
            round(center_point[0] + math.cos(angle) * 0.68 * half_size),
            round(center_point[1] + math.sin(angle) * 0.68 * half_size),
        ])
    return [
        *(
            action
            for point in checkpoints
            for action in (
                {"mouse": {"move": point}},
                {"action": "wait", "time": 0.04},
            )
        ),
        {"mouse": {"move": center_point}},
        {"action": "wait", "time": 0.04},
        {"mouse": {"buttons": {"left_up": True}}},
        {"action": "wait", "time": 0.32},
    ]


def move_driver_mark_actions(center_point: list[int], half_size: float, angle_index: int) -> list[dict[str, Any]]:
    angle = int(angle_index) * math.pi / 6 - math.pi / 2
    point = [
        round(center_point[0] + math.cos(angle) * 0.68 * half_size),
        round(center_point[1] + math.sin(angle) * 0.68 * half_size),
    ]
    return [
        {"mouse": {"move": point}},
        {"action": "wait", "time": 0.08},
    ]


def release_driver_actions(center_point: list[int]) -> list[dict[str, Any]]:
    return [
        {"mouse": {"move": center_point}},
        {"action": "wait", "time": 0.08},
        {"mouse": {"buttons": {"left_up": True}}},
        {"action": "wait", "time": 0.32},
    ]


def observation_records(episode_dir: Path, out_dir: Path) -> list[dict[str, Any]]:
    records = []
    for turn_dir in sorted((episode_dir / "observations").glob("turn-*")):
        manifest_path = turn_dir / "guest-capture-manifest.json"
        manifest = read_json(manifest_path)
        frames = []
        for index, item in enumerate(manifest["frames"]):
            frame_path = turn_dir / f"frame-{index:03d}.png"
            with Image.open(frame_path) as image:
                resolution = list(image.size)
            if resolution != RESOLUTION:
                raise AssertionError(f"{turn_dir.name}: unexpected resolution {resolution}")
            frames.append(
                {
                    "path": relative(frame_path, out_dir),
                    "sha256": sha256(frame_path),
                    "resolution": resolution,
                    "offset_ms": item["offset_ms"],
                    "target_offset_ms": item["target_offset_ms"],
                }
            )
        if len(frames) != 1:
            raise AssertionError(f"{turn_dir.name}: target declares one delivered frame")
        records.append({
            "turn": turn_dir.name,
            "guest_capture_manifest": relative(manifest_path, out_dir),
            "capture_method": manifest.get("capture_method", "guest_fixed_window_recorder"),
            "presentation_delay_ms": manifest.get("presentation_delay_ms"),
            "capture_transport_clock_state": manifest.get("capture_transport_clock_state"),
            "window_started_wall_ms": manifest.get("window_started_wall_ms"),
            "window_completed_wall_ms": manifest.get("window_completed_wall_ms"),
            "scheduled_window_completed_wall_ms": manifest.get("scheduled_window_completed_wall_ms"),
            "actual_window_wall_ms": manifest.get("actual_window_wall_ms"),
            "time_status": manifest["time_status"],
            "frames": frames,
            "screen": frames[-1]["path"],
            "screen_sha256": frames[-1]["sha256"],
            "screen_is_final_frame": True,
        })
    return records


def flatten_actions(timing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        action
        for turn in timing
        if turn.get("event") == "turn"
        for action in turn.get("actions", [])
    ]


def run_condition(
    interaction: str,
    mode: str,
    runtime_env: Path,
    out_dir: Path,
    groups: list[dict[str, Any]],
) -> dict[str, Any]:
    label = f"{interaction}-{mode}"
    condition_dir = out_dir / label
    condition_dir.mkdir(parents=True)
    summary_path = condition_dir / "episode-summary.json"
    agent_args = {
        "transient_timeout_attempts": 1,
        "inference_timeout_seconds": 10,
        "expected_text_markers": ["FENCE"],
        "action_groups": groups,
    }
    command = [
        sys.executable,
        "-B",
        str(EVALUATOR),
        "--env-dir",
        str(runtime_env),
        "--task",
        TASK_IDS[(interaction, mode)],
        "--agent",
        "AuthoritativeObservationProbeAgent",
        "--agent-args",
        json.dumps(agent_args, separators=(",", ":")),
        "--time-mode",
        mode,
        "--seed",
        str(SEED),
        "--steps",
        str(len(groups) + 2),
        "--request-timeout-seconds",
        "15",
        "--request-attempts",
        "2",
        "--episode-summary-path",
        str(summary_path),
    ]
    write_json(
        condition_dir / "run-command.json",
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
            "purpose": "scripted screenshot-only runner transport and fixed-window boundary probe",
        },
    )
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    (condition_dir / "evaluator.log").write_text(completed.stdout + completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(f"{label} evaluator failed; see {condition_dir / 'evaluator.log'}")

    episode_summary = read_json(summary_path)
    episode_dir = Path(episode_summary["episode_dir"]).resolve()
    timing = read_jsonl(episode_dir / "realtime_timing.jsonl")
    model_inputs = read_jsonl(episode_dir / "model_input_manifest.jsonl")
    observations = observation_records(episode_dir, out_dir)
    successful_model_inputs = [item for item in model_inputs if item.get("outcome") == "success"]
    if len(successful_model_inputs) != len(observations):
        raise AssertionError(
            f"{label}: successful model requests ({len(successful_model_inputs)}) do not match "
            f"runner observations ({len(observations)})"
        )
    for observation, model_input in zip(observations, successful_model_inputs, strict=True):
        observation["model_request_index"] = model_input["request_index"]
        observation["model_ocr_excerpt"] = model_input.get("ocr_excerpt")
    final_public_state = read_json(episode_dir / "public_state.json")
    setup = next(item for item in timing if item.get("event") == "setup")
    effective = setup["effective_runner_options"]
    expected_window = 0 if mode == "live" else WINDOW_MS
    if effective.get("observation_window_ms") != expected_window or effective.get("frames_per_observation") != 1:
        raise AssertionError(f"{label}: unexpected effective observation schedule {effective}")
    if len(observations) != len(groups) + 1:
        raise AssertionError(f"{label}: missing initial or following runner observations")
    if any(
        item.get("frame_count") != 1
        or item.get("screen_is_last_frame") is not True
        or item.get("visible_task_ui_only_rule_present") is not True
        for item in model_inputs
    ):
        raise AssertionError(f"{label}: incomplete model input manifest")
    first_turn = next(item for item in timing if item.get("event") == "turn")
    if [item.get("outcome") for item in first_turn["request_attempts"]] != ["error", "success"]:
        raise AssertionError(f"{label}: single-layer transient retry was not exercised")
    if first_turn["request_attempts"][0].get("error_type") != "TimeoutError":
        raise AssertionError(f"{label}: first request was not the simulated timeout")
    actions = flatten_actions(timing)
    if len(actions) != len(groups):
        raise AssertionError(f"{label}: action/observation cycle count mismatch")
    if mode == "paused":
        if any(
            abs(float(attempt["task_time_delta_ms"])) > 5
            for turn in timing
            if turn.get("event") == "turn"
            for attempt in turn.get("request_attempts", [])
        ):
            raise AssertionError(f"{label}: task time advanced during a model request")
        for index, action in enumerate(actions):
            statuses = action.get("action_delivery_statuses") or []
            if statuses:
                if abs(float(action["task_time_delta_during_action_ms"])) > 5:
                    raise AssertionError(f"{label} action {index}: input advanced frozen task time")
                delta = float(action["task_time_ms"]) - float(action["task_time_after_execution_ms"])
                if not 475 <= delta <= 485:
                    raise AssertionError(f"{label} action {index}: following window advanced {delta} ms")
                if action["clock_after_action"].get("controller_state") != "paused":
                    raise AssertionError(f"{label} action {index}: input boundary was not paused")
            else:
                # A wait(0) has no native Chromium input receipt, so the
                # evaluator can only report the endpoint status returned by
                # runner.step.  Its previous delivered observation is the
                # frozen before-input boundary.
                total_delta = float(action["task_time_ms"]) - float(action["task_time_before_action_ms"])
                if not 475 <= total_delta <= 485:
                    raise AssertionError(f"{label} action {index}: no-input window advanced {total_delta} ms")
    else:
        if sum(float(item["task_time_delta_ms"]) for item in first_turn["request_attempts"]) <= 20:
            raise AssertionError(f"{label}: live clock did not advance during model inference")

    return {
        "label": label,
        "interaction": interaction,
        "mode": mode,
        "task_id": TASK_IDS[(interaction, mode)],
        "seed": SEED,
        "episode_dir": relative(episode_dir, out_dir),
        "episode_summary": relative(summary_path, out_dir),
        "effective_runner_options": effective,
        "observations": observations,
        "model_input_manifest": relative(episode_dir / "model_input_manifest.jsonl", out_dir),
        "realtime_timing": relative(episode_dir / "realtime_timing.jsonl", out_dir),
        "actions": actions,
        "action_group_labels": [str(group.get("decision_label") or "") for group in groups],
        "request_timeout_seconds": setup["request_timeout_seconds"],
        "request_attempts": setup["request_attempts"],
        "request_retry_policy": setup["request_retry_policy"],
        "attempts": episode_summary.get("attempts"),
        "verifier": (episode_summary.get("info") or {}).get("verifier"),
        "model_screen_is_final_frame_for_every_request": True,
        "visible_task_ui_only_rule_present_for_every_request": True,
        "actual_inference_backend": "Tesseract 5 LSTM OCR",
        "final_public_world_fingerprint": world_fingerprint(final_public_state),
    }


def annotate_boundaries(record: dict[str, Any]) -> None:
    labels = record["action_group_labels"]
    observations = record["observations"]
    actions = record["actions"]

    def action_index(label: str) -> int:
        return labels.index(label)

    def action_indexes(prefix: str) -> list[int]:
        return [index for index, label in enumerate(labels) if label.startswith(prefix)]

    def require_visible(observation_index: int, *markers: str) -> str:
        text = str(observations[observation_index].get("model_ocr_excerpt") or "").upper()
        if not any(marker.upper() in text for marker in markers):
            raise AssertionError(
                f"{record['label']} observation {observation_index} does not visibly contain "
                f"any of {markers}: {text!r}"
            )
        return text

    if record["label"] == "full-paused":
        arm_index = action_index("carry_stake_and_hold_for_driver_key")
        mark_one_index = action_index("trace_visible_driver_mark_1")
        mark_two_index = action_index("trace_visible_driver_mark_2")
        seat_index = action_index("return_to_center_and_release_driver")
        arm_observation = arm_index + 1
        mark_one_observation = mark_one_index + 1
        mark_two_observation = mark_two_index + 1
        settled_observation = seat_index + 1
        if int(actions[arm_index]["clock_after_action"].get("pending_action_count") or 0) != 1:
            raise AssertionError("held full-mode stake did not create one pending action")
        if int(observations[arm_observation]["time_status"].get("pending_action_count") or 0) != 1:
            raise AssertionError("held full-mode stake unexpectedly settled before release")
        for observation_index in (mark_one_observation, mark_two_observation):
            if int(observations[observation_index]["time_status"].get("pending_action_count") or 0) != 1:
                raise AssertionError("full-mode held action settled between driver marks")
        if int(actions[seat_index]["clock_after_action"].get("pending_action_count") or 0) != 1:
            raise AssertionError("released stake was not pending at the frozen input receipt")
        if int(observations[settled_observation]["time_status"].get("pending_action_count") or 0) != 0:
            raise AssertionError("full-mode placement did not settle in its release window")
        driver_text = str(observations[arm_observation].get("model_ocr_excerpt") or "").upper()
        mark_one_text = str(observations[mark_one_observation].get("model_ocr_excerpt") or "").upper()
        mark_two_text = str(observations[mark_two_observation].get("model_ocr_excerpt") or "").upper()
        settled_text = str(observations[settled_observation].get("model_ocr_excerpt") or "").upper()
        boundary_hashes = {
            observations[index]["screen_sha256"]
            for index in (arm_observation, mark_one_observation, mark_two_observation, settled_observation)
        }
        if len(boundary_hashes) != 4:
            raise AssertionError("full-mode driver boundary screens were not visually distinct")
        record["fixed_window_cases"] = {
            "driver_reveal_while_held": {
                "action_index": arm_index,
                "following_observation_index": arm_observation,
            },
            "first_driver_mark_while_held": {
                "action_index": mark_one_index,
                "following_observation_index": mark_one_observation,
            },
            "second_driver_mark_while_held": {
                "action_index": mark_two_index,
                "following_observation_index": mark_two_observation,
            },
            "ordinary_placement": {
                "action_index": seat_index,
                "following_observation_index": settled_observation,
            },
        }
        record["model_visible_boundary_assertions"] = {
            "four_distinct_runner_screens_retained": True,
            "held_driver_ocr_support": "DRIVER" in driver_text or "STEP 1" in driver_text,
            "first_driver_mark_ocr_support": "STEP 2" in mark_one_text or "DRIVER MARK 1" in mark_one_text,
            "second_driver_mark_ocr_support": "RETURN TO CENTER" in mark_two_text or "DRIVER MARKS SET" in mark_two_text,
            "one_window_fox_moved_ocr_support": "FOX MOVED" in settled_text,
            "semantic_visual_review_required": True,
        }
        return
    if record["label"] != "simplified-paused":
        return
    rejected_index = action_index("reject_click_on_fox_while_frozen")
    escape_indexes = action_indexes("escape_setup_placement_")
    continuation_indexes = action_indexes("advance_")
    fresh_indexes = action_indexes("fresh_world_canonical_placement_")
    submission_index = action_index("submit_visible_enclosure")
    if not escape_indexes or not continuation_indexes or not fresh_indexes:
        raise AssertionError("paused boundary action labels are incomplete")
    escape_index = escape_indexes[-1]
    ordinary_index = fresh_indexes[0]
    winning_index = fresh_indexes[-1]
    cases = {
        "rejected_fox_cell": {"action_index": rejected_index, "following_observation_index": rejected_index + 1},
        "ordinary_placement": {"action_index": ordinary_index, "following_observation_index": ordinary_index + 1},
        "escape_first_window": {"action_index": escape_index, "following_observation_index": escape_index + 1},
        "escape_continuation_windows": {
            "action_indexes": continuation_indexes,
            "following_observation_indexes": [index + 1 for index in continuation_indexes],
        },
        "winning_placement": {"action_index": winning_index, "following_observation_index": winning_index + 1},
        "terminal_submission": {"action_index": submission_index, "following_observation_index": submission_index + 1},
    }
    if int(actions[rejected_index]["clock_after_action"].get("pending_action_count") or 0) != 0:
        raise AssertionError("rejected input left a pending action")
    if int(observations[rejected_index + 1]["time_status"].get("pending_action_count") or 0) != 0:
        raise AssertionError("rejected input was not settled at its fixed-window endpoint")
    if int(actions[ordinary_index]["clock_after_action"].get("pending_action_count") or 0) != 1:
        raise AssertionError("ordinary placement was not pending immediately after frozen input")
    if int(observations[ordinary_index + 1]["time_status"].get("pending_action_count") or 0) != 0:
        raise AssertionError("ordinary placement did not settle inside one fixed window")
    if int(actions[escape_index]["clock_after_action"].get("pending_action_count") or 0) != 1:
        raise AssertionError("escape action was not pending immediately after input")
    if int(observations[escape_index + 1]["time_status"].get("pending_action_count") or 0) != 1:
        raise AssertionError("long escape/refresh effect incorrectly settled in one window")
    continuation_pending = [
        int(observations[index]["time_status"].get("pending_action_count") or 0)
        for index in cases["escape_continuation_windows"]["following_observation_indexes"]
    ]
    settled = [
        index
        for index, pending in zip(
            cases["escape_continuation_windows"]["following_observation_indexes"],
            continuation_pending,
            strict=True,
        )
        if pending == 0
    ]
    if not settled:
        raise AssertionError("long escape/refresh effect did not settle in four following windows")
    cases["escape_continuation_windows"]["pending_action_counts"] = continuation_pending
    cases["escape_continuation_windows"]["first_settled_observation_index"] = settled[0]
    if int(actions[winning_index]["clock_after_action"].get("pending_action_count") or 0) != 1:
        raise AssertionError("winning placement was not pending immediately after input")
    if int(observations[winning_index + 1]["time_status"].get("pending_action_count") or 0) != 0:
        raise AssertionError("winning placement did not settle inside one fixed window")
    ordinary_text = str(observations[ordinary_index + 1].get("model_ocr_excerpt") or "").upper()
    winning_text = str(observations[winning_index + 1].get("model_ocr_excerpt") or "").upper()
    if observations[ordinary_index]["screen_sha256"] == observations[ordinary_index + 1]["screen_sha256"]:
        raise AssertionError("ordinary placement did not produce a distinct runner screen")
    if observations[winning_index]["screen_sha256"] == observations[winning_index + 1]["screen_sha256"]:
        raise AssertionError("winning placement did not produce a distinct runner screen")
    record["fixed_window_cases"] = cases
    record["long_effect_required_following_runner_observations"] = True
    record["model_visible_boundary_assertions"] = {
        "ordinary_endpoint_screen_changed": True,
        "winning_endpoint_screen_changed": True,
        "ordinary_one_window_fox_moved_ocr_support": "FOX MOVED" in ordinary_text,
        "winning_one_window_enclosure_ocr_support": "FOX ENCLOSED" in winning_text,
        "semantic_visual_review_required": True,
    }


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    (out_dir / "tesseract-version.txt").write_text(
        subprocess.check_output(["tesseract", "--version"], text=True, stderr=subprocess.STDOUT),
        encoding="utf-8",
    )
    with tempfile.TemporaryDirectory(prefix="fence-fox-authoritative-evaluator-") as raw:
        temporary = Path(raw)
        runtime_env, tasks = build_runtime_environment(temporary, out_dir)
        preflight = coordinate_preflight(temporary, tasks, out_dir)
        cell = preflight["cells"]
        cell_half_sizes = preflight["cell_half_sizes"]
        token = preflight["stake_token_center"]
        initial_truth = preflight["initial_ground_truth"]

        refreshed_state_dir = temporary / "refresh-state"
        refreshed_state_dir.mkdir()
        subprocess.run(
            [
                sys.executable,
                "-B",
                str(SETUP),
                "--task-json",
                str(tasks / TASK_IDS[("simplified", "live")] / "task.json"),
                "--state-dir",
                str(refreshed_state_dir),
                "--seed",
                f"{SEED}:fail:2",
            ],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        refreshed_public = read_json(refreshed_state_dir / "public_state.json")
        refreshed_truth = read_json(refreshed_state_dir / "ground_truth.json")

        first_plan = initial_truth["canonical_plan"]
        first_key = f"{first_plan[0][0]},{first_plan[0][1]}"
        first_center = cell[first_key]
        first_pattern = initial_truth["driver_patterns"][0]
        simple_live_groups = [
            {"decision_label": "click_first_visible_canonical_cell", "actions": click_actions(first_center)},
            {"decision_label": "capture_next_live_state", "actions": [{"action": "wait", "time": 0.45}]},
        ]
        full_live_groups = [
            {"decision_label": "carry_stake_and_hold_for_driver_key", "actions": arm_driver_actions(token, first_center)},
            {
                "decision_label": "trace_visible_driver_mark_1",
                "actions": move_driver_mark_actions(first_center, cell_half_sizes[first_key], first_pattern[0]),
            },
            {
                "decision_label": "trace_visible_driver_mark_2",
                "actions": move_driver_mark_actions(first_center, cell_half_sizes[first_key], first_pattern[1]),
            },
            {
                "decision_label": "return_to_center_and_release_driver",
                "actions": release_driver_actions(first_center),
            },
            {
                "decision_label": "confirm_completed_visible_fox_reply",
                "actions": [{"action": "wait", "time": 0.0}],
            },
        ]
        full_paused_groups = [
            {"decision_label": "carry_stake_and_hold_for_driver_key", "actions": arm_driver_actions(token, first_center)},
            {
                "decision_label": "trace_visible_driver_mark_1",
                "actions": move_driver_mark_actions(first_center, cell_half_sizes[first_key], first_pattern[0]),
            },
            {
                "decision_label": "trace_visible_driver_mark_2",
                "actions": move_driver_mark_actions(first_center, cell_half_sizes[first_key], first_pattern[1]),
            },
            {
                "decision_label": "return_to_center_and_release_driver",
                "actions": release_driver_actions(first_center),
            },
            {
                "decision_label": "confirm_completed_visible_fox_reply",
                "actions": [{"action": "wait", "time": 0.0}],
            },
        ]
        bad_plan = find_escape_plan(initial_truth)
        simple_paused_groups = [
            {"decision_label": "reject_click_on_fox_while_frozen", "actions": click_actions(cell["0,0"])},
            *(
                {
                    "decision_label": f"escape_setup_placement_{index}",
                    "actions": click_actions(cell[f"{coord[0]},{coord[1]}"]),
                }
                for index, coord in enumerate(bad_plan, start=1)
            ),
            {"decision_label": "advance_following_fixed_window_for_refresh", "actions": [{"action": "wait", "time": 0.0}]},
            {"decision_label": "advance_second_following_fixed_window_for_refresh", "actions": [{"action": "wait", "time": 0.0}]},
            {"decision_label": "advance_third_following_fixed_window_for_refresh", "actions": [{"action": "wait", "time": 0.0}]},
            {"decision_label": "advance_fourth_following_fixed_window_for_refresh", "actions": [{"action": "wait", "time": 0.0}]},
            *(
                {
                    "decision_label": f"fresh_world_canonical_placement_{index}",
                    "actions": click_actions(cell[f"{coord[0]},{coord[1]}"]),
                }
                for index, coord in enumerate(refreshed_truth["canonical_plan"], start=1)
            ),
            {"decision_label": "submit_visible_enclosure", "actions": click_actions([1810, 1029])},
        ]

        records = [
            run_condition("full", "live", runtime_env, out_dir, full_live_groups),
            run_condition("full", "paused", runtime_env, out_dir, full_paused_groups),
            run_condition("simplified", "live", runtime_env, out_dir, simple_live_groups),
            run_condition("simplified", "paused", runtime_env, out_dir, simple_paused_groups),
        ]

    for record in records:
        annotate_boundaries(record)
    initial_runner_fingerprints = {
        item["final_public_world_fingerprint"]
        for item in records
        if item["label"] in {"simplified-live", "full-live", "full-paused"}
    }
    if len(initial_runner_fingerprints) != 1:
        raise AssertionError("runner live/paused and simplified/full tasks did not preserve the initial world")
    paused_simple = next(item for item in records if item["label"] == "simplified-paused")
    if (paused_simple.get("verifier") or {}).get("passed") is not True:
        raise AssertionError("paused simplified boundary episode did not finish with a verified pass")
    by_label = {item["label"]: item for item in records}
    settled_index = int(
        paused_simple["fixed_window_cases"]["escape_continuation_windows"][
            "first_settled_observation_index"
        ]
    )
    representative_sources = {
        "full-paused-initial.png": by_label["full-paused"]["observations"][0]["screen"],
        "full-paused-driver-revealed.png": by_label["full-paused"]["observations"][
            by_label["full-paused"]["fixed_window_cases"]["driver_reveal_while_held"]["following_observation_index"]
        ]["screen"],
        "full-paused-placement-settled.png": by_label["full-paused"]["observations"][
            by_label["full-paused"]["fixed_window_cases"]["ordinary_placement"]["following_observation_index"]
        ]["screen"],
        "simplified-paused-escape-first-window.png": paused_simple["observations"][
            paused_simple["fixed_window_cases"]["escape_first_window"]["following_observation_index"]
        ]["screen"],
        "simplified-paused-refresh-settled.png": paused_simple["observations"][settled_index]["screen"],
        "simplified-paused-winning-placement.png": paused_simple["observations"][
            paused_simple["fixed_window_cases"]["winning_placement"]["following_observation_index"]
        ]["screen"],
        "simplified-paused-verified-pass.png": paused_simple["observations"][
            paused_simple["fixed_window_cases"]["terminal_submission"]["following_observation_index"]
        ]["screen"],
    }
    representative = {}
    for name, source in representative_sources.items():
        source_path = out_dir / source
        destination = out_dir / "representative" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        representative[name] = {
            "path": relative(destination, out_dir),
            "sha256": sha256(destination),
            "source_runner_frame": source,
        }
    source_paths = {
        "capture_driver": Path(__file__).resolve(),
        "evaluator": EVALUATOR,
        "observation_probe": BENCHMARK / "tools/authoritative_observation_probe_agent.py",
        "runner": BENCHMARK / "runner.py",
        "guest_capture": BENCHMARK / "shared_scripts/capture_observation_window.py",
        "time_controller": BENCHMARK / "shared_runtime/app/time_controller.js",
        "environment": ENVIRONMENT / "env.json",
        "controls": ENVIRONMENT / "controls.json",
        "browser": BENCHMARK / "shared_runtime/app/mechanics/fence_the_fox.js",
        "generator": BENCHMARK / "shared_scripts/incubator_generators/fence_the_fox.py",
        "grader": BENCHMARK / "shared_runtime/server/incubator_graders/fence_the_fox.py",
    }
    summary = {
        "ok": True,
        "environment": "Fence the Fox",
        "authoritative_runner_observations": True,
        "same_initial_generated_world": True,
        "initial_world_fingerprint": next(iter(initial_runner_fingerprints)),
        "first_failure_world_seed": f"{SEED}:fail:2",
        "first_failure_world_fingerprint": world_fingerprint(refreshed_public),
        "settings": {
            "configured_observation_window_ms": WINDOW_MS,
            "configured_frames_per_observation": 1,
            "effective_live_observation": "one instantaneous runner frame",
            "effective_paused_observation": "one runner frame at the endpoint of an exact 480 ms virtual-time window",
            "request_timeout_seconds": 15,
            "request_attempts": 2,
        },
        "isolation": {
            "host_foreground_application": False,
            "environment_vnc_ui_enabled": False,
            "interactive_vnc_client_opened": False,
            "runner_background_virtual_display": True,
            "ephemeral_virtual_machine_per_episode": True,
            "coordinate_preflight_headless_fresh_profile_loopback_only": True,
            "existing_browser_profile": False,
            "connected_browser_or_desktop_automation": False,
        },
        "conditions": {item["label"]: item for item in records},
        "representative_runner_screens": representative,
        "source_sha256": {name: sha256(path) for name, path in source_paths.items()},
        "evidence_boundary": (
            "The observations below are exact WeirdCaptchaRunner outputs delivered to a local screenshot-only "
            "Tesseract transport probe. The preflight screenshot is explicitly separate and was used only to "
            "choose scripted visible coordinates. This establishes model-input delivery, fixed-window timing, "
            "pending/settled boundaries, trusted paused input, refresh splitting, and retry behavior; it is not "
            "human/VNC usability or a general computer-use-agent performance result."
        ),
    }
    write_json(out_dir / "summary.json", summary)
    print(json.dumps({"ok": True, "evidence": str(out_dir)}, sort_keys=True))


if __name__ == "__main__":
    main()
