#!/usr/bin/env python3
"""Randomized 75-environment programmatic solves through ``env.step`` only.

There are two intentionally separate phases:

``record`` runs each privileged controlled solver in an isolated headless
browser and records its trusted visible input. This phase is an oracle, not a
benchmark pass.

``verify`` replays those standard mouse/keyboard groups against the real
Gym-Anything environment. Every action, wait, and paused-time advance goes
through ``env.step``. Only the final Gym verifier result is accepted.
"""
from __future__ import annotations

import argparse
import ast
import copy
from collections import deque
import hashlib
import importlib.util
import json
import math
import os
import random
import re
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENTS = BENCHMARK / "environments"
APP = BENCHMARK / "shared_runtime" / "app"
SERVER = BENCHMARK / "shared_runtime" / "server" / "weird_captcha_server.py"
SETUP = BENCHMARK / "shared_scripts" / "setup_task.py"
TRACE_PARSER_VERSION = 3

from weird_captcha_gym.tools.env_step_action_trace import (  # noqa: E402
    RECORDER_SCRIPT,
    compact_agent_actions,
    parse_input_trace,
)
from weird_captcha_gym.tools.materialize_controlled_tasks import (  # noqa: E402
    materialize_environment,
)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _reject_programmatic_solver_actions(path: Path) -> None:
    """Reject browser-script actions that cannot be replayed through env.step."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden = re.compile(r"\.click\s*\(|dispatchEvent\s*\(|requestSubmit\s*\(")
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "dispatch_event"
        ):
            raise AssertionError(
                f"{path}:{node.lineno} dispatches a synthetic browser event; "
                "oracle actions must use trusted visible input so env.step can replay them"
            )
        if (
            not isinstance(node, ast.Call)
            or not isinstance(node.func, ast.Attribute)
            or node.func.attr not in {"evaluate", "eval_on_selector", "evaluate_all"}
            or not node.args
        ):
            continue
        script = node.args[0]
        if isinstance(script, ast.Constant) and isinstance(script.value, str) and forbidden.search(script.value):
            raise AssertionError(
                f"{path}:{node.lineno} performs a browser-script action; "
                "oracle actions must use trusted visible input so env.step can replay them"
            )


def _base_task(env_root: Path, mechanic: str) -> dict[str, Any]:
    path = env_root / "tasks" / f"{mechanic}_seed_0001" / "task.json"
    return _read(path)


def build_manifest(matrix_seed: int) -> dict[str, Any]:
    rng = random.Random(matrix_seed)
    entries = []
    for index, controls_path in enumerate(sorted(ENVIRONMENTS.glob("*_env/controls.json"))):
        controls = _read(controls_path)
        env_root = controls_path.parent
        mechanic = str(controls["mechanic_id"])
        difficulty = rng.randint(1, 5)
        interaction = rng.choice(("simplified", "full"))
        time_mode = rng.choice(("live", "paused"))
        challenge_seed = rng.randint(1, 2_147_483_647)
        task_id = f"{mechanic}_d{difficulty}_{interaction}_seed_0001"
        entries.append({
            "index": index,
            "environment": env_root.name,
            "public_name": str(_base_task(env_root, mechanic)["name"]),
            "mechanic": mechanic,
            "difficulty": difficulty,
            "interaction": interaction,
            "time_mode": time_mode,
            "challenge_seed": challenge_seed,
            "task_id": task_id,
            "observation_window_ms": int(controls["real_time"]["observation_window_ms"]),
            "frames_per_observation": int(controls["real_time"]["frames_per_observation"]),
            "play_time_seconds": int(controls["real_time"]["play_time_seconds"]),
        })
    if len(entries) != 75:
        raise AssertionError(f"expected 75 controlled environments, found {len(entries)}")
    return {
        "schema_version": 1,
        "matrix_seed": matrix_seed,
        "sampling": "independent PRNG draws per environment for D1-D5, Simplified/Full, live/paused, and challenge seed",
        "entries": entries,
    }


def _selected(entries: list[dict[str, Any]], shard_index: int, shard_count: int) -> list[dict[str, Any]]:
    if shard_count < 1 or not 0 <= shard_index < shard_count:
        raise ValueError("shard index must be within shard count")
    return [entry for entry in entries if int(entry["index"]) % shard_count == shard_index]


def _viewport(env_root: Path) -> dict[str, int]:
    config = _read(env_root / "env.json")
    screens = [
        item for item in config.get("observation", [])
        if item.get("type") in {"frame_window", "rgb_screen"}
    ]
    if len(screens) != 1:
        raise AssertionError(f"{env_root.name}: expected one screen observation")
    width, height = screens[0]["resolution"]
    return {"width": int(width), "height": int(height)}


def _reserve_port() -> int:
    with socket.socket() as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def _start_server(task_json: Path, state_dir: Path, seed: int) -> tuple[subprocess.Popen, int]:
    subprocess.run(
        [sys.executable, "-B", str(SETUP), "--task-json", str(task_json), "--state-dir", str(state_dir), "--seed", str(seed)],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    port = _reserve_port()
    server_env = os.environ.copy()
    server_env["WEIRD_CAPTCHA_CHALLENGE_SEED"] = str(seed)
    process = subprocess.Popen(
        [sys.executable, "-B", str(SERVER), "--host", "127.0.0.1", "--port", str(port), "--app-dir", str(APP), "--state-dir", str(state_dir)],
        cwd=ROOT,
        env=server_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            import urllib.request

            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=.5).read()
            return process, port
        except Exception:
            time.sleep(.1)
    process.kill()
    raise RuntimeError("local oracle server did not start")


def _patch_real_time(task_json: Path, mode: str) -> None:
    task = _read(task_json)
    metadata = dict(task.get("metadata") or {})
    condition = dict(metadata.get("control_condition") or {})
    condition["real_time"] = mode
    metadata["control_condition"] = condition
    task["metadata"] = metadata
    _write(task_json, task)


def _collect_context_events(context) -> list[dict[str, Any]]:
    """Collect trusted task input from the main page and task-created tabs."""
    merged: list[tuple[float, int, int, int, dict[str, Any]]] = []
    for page_index, candidate_page in enumerate(context.pages):
        if candidate_page.is_closed():
            continue
        for frame_index, frame in enumerate(candidate_page.frames):
            try:
                events = frame.evaluate("() => window.__weirdEnvStepInputTrace || []")
            except Exception:
                continue
            for event in events:
                merged.append((
                    float(event.get("absolute_time_ms") or event.get("time_ms") or 0),
                    page_index,
                    frame_index,
                    int(event.get("sequence") or 0),
                    dict(event),
                ))
    result = []
    for sequence, (absolute_time_ms, page_index, frame_index, _local_sequence, event) in enumerate(sorted(merged), 1):
        event["sequence"] = sequence
        event["time_ms"] = absolute_time_ms
        event["page_index"] = page_index
        event["frame_index"] = frame_index
        result.append(event)
    return result


def _world_fingerprint(value: dict[str, Any]) -> str:
    state = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition", "prompt", "rules"):
        state.pop(key, None)
    payload = json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _weighted_median(values: list[tuple[float, float]]) -> float:
    ordered = sorted(values)
    halfway = sum(weight for _value, weight in ordered) / 2
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= halfway:
            return value
    return ordered[-1][0]


def _filter_registration_displacement_outliers(
    matches: list[tuple[float, float, float, float]],
    *,
    maximum_axis_deviation: float = 48.0,
) -> tuple[list[tuple[float, float, float, float]], dict[str, float]]:
    """Reject repeated-feature matches that imply a control-grid jump."""
    if not matches:
        return [], {"median_dx": 0.0, "median_dy": 0.0}
    median_dx = float(statistics.median(match[2] for match in matches))
    median_dy = float(statistics.median(match[3] for match in matches))
    filtered = [
        match
        for match in matches
        if abs(match[2] - median_dx) <= maximum_axis_deviation
        and abs(match[3] - median_dy) <= maximum_axis_deviation
    ]
    return filtered, {"median_dx": median_dx, "median_dy": median_dy}


def _bound_local_registration_displacement(
    local: float,
    global_median: float,
    *,
    maximum_local_deviation: float = 14.0,
) -> float:
    """Reject a local repeated-feature jump while retaining real layout drift."""
    if abs(local - global_median) > maximum_local_deviation:
        return global_median
    return local


def _visible_coordinate_mapper(reference_path: Path, current_path: Path):
    """Map oracle pixels onto the delivered production screenshot.

    The oracle and the VM render the same visible task, but their installed
    fonts can produce local layout shifts.  Match visible image features and
    use the nearest robust displacement for each mouse position.  This keeps
    the replay screenshot-based; it does not inspect the DOM or browser state.
    """
    import cv2

    reference = cv2.imread(str(reference_path), cv2.IMREAD_GRAYSCALE)
    current = cv2.imread(str(current_path), cv2.IMREAD_GRAYSCALE)
    if reference is None or current is None:
        raise RuntimeError("could not read oracle/current screenshots for coordinate registration")
    if reference.shape != current.shape:
        raise RuntimeError(
            f"oracle/current screenshot sizes differ: {reference.shape} != {current.shape}"
        )
    detector = cv2.SIFT_create(nfeatures=12_000, contrastThreshold=.02)
    reference_points, reference_descriptors = detector.detectAndCompute(reference, None)
    current_points, current_descriptors = detector.detectAndCompute(current, None)
    if reference_descriptors is None or current_descriptors is None:
        raise RuntimeError("visible screenshot registration found no feature descriptors")
    candidates = cv2.BFMatcher().knnMatch(reference_descriptors, current_descriptors, k=2)
    height, width = reference.shape
    matches: list[tuple[float, float, float, float]] = []
    for nearest, runner_up in candidates:
        if nearest.distance >= .72 * runner_up.distance:
            continue
        source = reference_points[nearest.queryIdx]
        target = current_points[nearest.trainIdx]
        x, y = source.pt
        target_x, target_y = target.pt
        if abs(target_x - x) > max(180, width * .12) or abs(target_y - y) > max(180, height * .16):
            continue
        scale_ratio = target.size / max(source.size, 1e-6)
        if not .45 <= scale_ratio <= 2.2:
            continue
        matches.append((x, y, target_x - x, target_y - y))
    raw_match_count = len(matches)
    matches, displacement = _filter_registration_displacement_outliers(matches)
    if len(matches) < 8:
        raise RuntimeError(f"visible screenshot registration found only {len(matches)} usable matches")

    mapped: dict[tuple[int, int], tuple[int, int]] = {}
    mapping_records: list[dict[str, list[int]]] = []

    def transform(x: float, y: float) -> tuple[int, int]:
        key = (round(x), round(y))
        if key in mapped:
            return mapped[key]
        neighbours = sorted(
            matches,
            key=lambda match: (match[0] - x) ** 2 + (match[1] - y) ** 2,
        )[:24]
        weighted_dx: list[tuple[float, float]] = []
        weighted_dy: list[tuple[float, float]] = []
        for source_x, source_y, dx, dy in neighbours:
            distance = ((source_x - x) ** 2 + (source_y - y) ** 2) ** .5
            weight = 1 / (distance + 18) ** 2
            weighted_dx.append((dx, weight))
            weighted_dy.append((dy, weight))
        local_dx = _bound_local_registration_displacement(
            _weighted_median(weighted_dx),
            displacement["median_dx"],
        )
        local_dy = _bound_local_registration_displacement(
            _weighted_median(weighted_dy),
            displacement["median_dy"],
        )
        mapped_x = min(width - 1, max(0, round(x + local_dx)))
        mapped_y = min(height - 1, max(0, round(y + local_dy)))
        mapped[key] = (mapped_x, mapped_y)
        mapping_records.append({"source": list(key), "target": [mapped_x, mapped_y]})
        return mapped[key]

    diagnostics = {
        "method": "visible screenshot SIFT outlier-filtered nearest weighted-median displacement",
        "reference": str(reference_path.resolve()),
        "current": str(current_path.resolve()),
        "reference_feature_count": len(reference_points),
        "current_feature_count": len(current_points),
        "usable_match_count": len(matches),
        "raw_match_count": raw_match_count,
        "registration_median_displacement": displacement,
        "image_size": [width, height],
        "mapped_points": mapping_records,
    }
    return transform, diagnostics


def _remap_visible_mouse_coordinates(
    groups: list[dict[str, Any]],
    transform,
) -> tuple[list[dict[str, Any]], int]:
    remapped = copy.deepcopy(groups)
    count = 0
    for group in remapped:
        page_indices = group.get("action_page_indices") or [0] * len(group["actions"])
        for action_index, action in enumerate(group["actions"]):
            # The registration reference is the main task screenshot. Task-
            # created tabs occupy the same delivered screen but have their
            # own layout; retain their recorded visible coordinates.
            if int(page_indices[action_index]) != 0:
                continue
            mouse = action.get("mouse") or {}
            for key in (
                "move", "left_click", "right_click", "middle_click",
                "double_click", "triple_click",
            ):
                point = mouse.get(key)
                if not isinstance(point, list) or len(point) != 2:
                    continue
                mouse[key] = list(transform(float(point[0]), float(point[1])))
                count += 1
            for key in ("left_click_drag", "right_click_drag"):
                points = mouse.get(key)
                if not isinstance(points, list) or len(points) != 2:
                    continue
                mapped_points = []
                for point in points:
                    if not isinstance(point, list) or len(point) != 2:
                        break
                    mapped_points.append(list(transform(float(point[0]), float(point[1]))))
                if len(mapped_points) == 2:
                    mouse[key] = mapped_points
                    count += 2
    return remapped, count


def record_entry(
    browser,
    entry: dict[str, Any],
    output_root: Path,
    *,
    browser_engine: str,
    initial_only: bool = False,
) -> dict[str, Any]:
    env_root = ENVIRONMENTS / str(entry["environment"])
    entry_dir = output_root / "entries" / f"{int(entry['index']):02d}-{entry['mechanic']}"
    with tempfile.TemporaryDirectory(prefix=f"env-step-oracle-{entry['mechanic']}-") as temporary_name:
        temporary = Path(temporary_name)
        materialized = temporary / "materialized"
        materialize_environment(env_root, materialized)
        task_json = materialized / env_root.name / "tasks" / str(entry["task_id"]) / "task.json"
        _patch_real_time(task_json, str(entry["time_mode"]))
        state_dir = temporary / "state"
        state_dir.mkdir()
        process, port = _start_server(task_json, state_dir, int(entry["challenge_seed"]))
        context = browser.new_context(viewport=_viewport(env_root), device_scale_factor=1)
        context.add_init_script(script=RECORDER_SCRIPT)
        page = context.new_page()
        browser_errors: list[str] = []
        page.on("pageerror", lambda error: browser_errors.append(str(error)))
        try:
            # Production startup fetches /state once after pre_task. The
            # server deliberately turns that into the deterministic
            # ``<reset seed>:refresh:1`` challenge; the oracle must solve that
            # same world rather than the pre-fetch setup artifact.
            page.goto(
                f"http://127.0.0.1:{port}/?time_mode=live&start_paused=0&time_control=1",
                wait_until="domcontentloaded",
            )
            page.wait_for_function("() => window.WeirdCaptchaTime?.status().ready === true")
            page.locator("[data-interaction]").wait_for(state="attached")
            if entry["mechanic"] == "popup_exorcist":
                page.wait_for_timeout(150)
            initial_public = _read(state_dir / "public_state.json")
            initial_truth = _read(state_dir / "ground_truth.json")
            # Match reset's first observation window before the first agent action.
            if int(entry["observation_window_ms"]):
                page.wait_for_timeout(int(entry["observation_window_ms"]))
            entry_dir.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(entry_dir / "oracle-initial.png"))
            _write(entry_dir / "oracle-initial.json", {
                "browser_engine": browser_engine,
                "browser_version": browser.version,
                "challenge_id": initial_public.get("challenge_id"),
                "world_fingerprint": _world_fingerprint(initial_public),
            })
            if initial_only:
                return {
                    "index": entry["index"],
                    "mechanic": entry["mechanic"],
                    "status": "snapshotted",
                    "screenshot": str((entry_dir / "oracle-initial.png").resolve()),
                }
            for frame in page.frames:
                try:
                    frame.evaluate("() => window.__resetWeirdEnvStepInputTrace?.()")
                except Exception:
                    pass
            recording_origin_ms = float(page.evaluate("() => performance.timeOrigin + performance.now()"))
            solver_path = BENCHMARK / "tools" / "incubator_solvers" / f"{entry['mechanic']}.py"
            _reject_programmatic_solver_actions(solver_path)
            solver = _load_module(
                f"env_step_oracle_{entry['mechanic']}_{entry['index']}",
                solver_path,
            )
            evidence_dir = entry_dir / "oracle-screens"
            solver.solve(page, state_dir, evidence_dir, str(entry["mechanic"]))
            deadline = time.time() + 10
            while time.time() < deadline and not (state_dir / "result.json").is_file():
                time.sleep(.05)
            if not (state_dir / "result.json").is_file():
                raise AssertionError("oracle solve produced no result.json")
            result = _read(state_dir / "result.json")
            grade = dict(result.get("server_grade") or {})
            if grade.get("passed") is not True:
                raise AssertionError(f"oracle server rejected solve: {grade}")
            recording_end_ms = float(page.evaluate("() => performance.timeOrigin + performance.now()"))
            raw_events = _collect_context_events(context)
            groups = parse_input_trace(raw_events)
            if not groups:
                raise AssertionError("oracle solve produced no visible input trace")
            trace = {
                "schema_version": 1,
                "trace_parser_version": TRACE_PARSER_VERSION,
                "entry": entry,
                "initial_challenge_id": initial_public.get("challenge_id"),
                "initial_world_fingerprint": _world_fingerprint(initial_public),
                "ground_truth_seed": initial_truth.get("seed"),
                "oracle_browser_engine": browser_engine,
                "oracle_browser_version": browser.version,
                "oracle_server_grade": grade,
                "browser_errors": browser_errors,
                "raw_event_count": len(raw_events),
                "action_group_count": len(groups),
                "action_count": sum(len(group["actions"]) for group in groups),
                "recording_origin_ms": recording_origin_ms,
                "recording_end_ms": recording_end_ms,
                "initial_action_delay_ms": round(max(
                    0.0,
                    min(
                        (float(event.get("time_ms") or recording_origin_ms) for event in raw_events),
                        default=recording_origin_ms,
                    ) - recording_origin_ms,
                ), 3),
                "trailing_delay_ms": round(max(
                    0.0,
                    recording_end_ms - max(
                        (float(event.get("time_ms") or recording_origin_ms) for event in raw_events),
                        default=recording_origin_ms,
                    ),
                ), 3),
                "groups": groups,
            }
            _write(entry_dir / "trace.json", trace)
            _write(entry_dir / "raw-events.json", raw_events)
            return {
                "index": entry["index"],
                "mechanic": entry["mechanic"],
                "status": "recorded",
                "action_group_count": len(groups),
                "action_count": trace["action_count"],
                "trace": str((entry_dir / "trace.json").resolve()),
            }
        except Exception:
            failure_state = entry_dir / "oracle-failure-state"
            failure_state.mkdir(parents=True, exist_ok=True)
            for state_file in state_dir.iterdir():
                if state_file.is_file():
                    shutil.copy2(state_file, failure_state / state_file.name)
            try:
                _write(failure_state / "raw-events.json", _collect_context_events(context))
                page.screenshot(path=str(failure_state / "failure.png"), full_page=True)
            except Exception:
                pass
            raise
        finally:
            context.close()
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()


def record_shard(
    manifest: dict[str, Any],
    output_root: Path,
    shard_index: int,
    shard_count: int,
    *,
    browser_engine: str,
    initial_only: bool = False,
    selected_indices: set[int] | None = None,
) -> int:
    from playwright.sync_api import sync_playwright

    records = []
    failures = 0
    entries = list(manifest["entries"])
    selected = (
        [entry for entry in entries if int(entry["index"]) in selected_indices]
        if selected_indices is not None
        else _selected(entries, shard_index, shard_count)
    )
    if selected_indices is not None:
        found = {int(entry["index"]) for entry in selected}
        missing = sorted(selected_indices - found)
        if missing:
            raise ValueError(f"manifest has no entries for indices {missing}")
    for solver_path in sorted((BENCHMARK / "tools" / "incubator_solvers").glob("*.py")):
        if solver_path.name.startswith("._"):
            continue
        _reject_programmatic_solver_actions(solver_path)
    with sync_playwright() as playwright:
        browser_type = getattr(playwright, browser_engine)
        browser = browser_type.launch(headless=True)
        for position, entry in enumerate(selected, 1):
            print(f"[record {position}/{len(selected)}] {entry['mechanic']} D{entry['difficulty']} {entry['interaction']} {entry['time_mode']}", flush=True)
            try:
                record = record_entry(
                    browser,
                    entry,
                    output_root,
                    browser_engine=browser_engine,
                    initial_only=initial_only,
                )
            except Exception as error:
                failures += 1
                record = {
                    "index": entry["index"],
                    "mechanic": entry["mechanic"],
                    "status": "record_failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "traceback": traceback.format_exc(),
                }
                print(record["traceback"], flush=True)
            records.append(record)
            prefix = "snapshot" if initial_only else "record"
            _write(output_root / f"{prefix}-shard-{shard_index:02d}.json", {"records": records})
        browser.close()
    return 1 if failures else 0


def _runtime_environment(entry: dict[str, Any], temporary: Path, output_root: Path) -> Path:
    env_root = ENVIRONMENTS / str(entry["environment"])
    materialized = temporary / "materialized"
    materialize_environment(env_root, materialized)
    tasks = materialized / env_root.name / "tasks"
    task_json = tasks / str(entry["task_id"]) / "task.json"
    _patch_real_time(task_json, str(entry["time_mode"]))
    runtime_benchmark = temporary / "weird_captcha_gym"
    runtime_env = runtime_benchmark / "environments" / env_root.name
    runtime_env.mkdir(parents=True)
    shutil.copytree(tasks, runtime_env / "tasks")
    shutil.copytree(BENCHMARK / "shared_runtime", runtime_benchmark / "shared_runtime")
    config = _read(env_root / "env.json")
    config["recording"]["output_dir"] = str((output_root / "raw-episodes").resolve())
    for mount in config["mounts"]:
        if mount.get("target") == "/workspace/tasks":
            mount["source"] = str((runtime_env / "tasks").resolve())
    _write(runtime_env / "env.json", config)
    return runtime_env


def _step(env, actions: list[dict[str, Any]]) -> tuple[dict[str, Any], bool, dict[str, Any]]:
    observation, _reward, done, info = env.step(
        actions,
        # Match the public env.step default used by normal agents. In paused
        # mode this wall spacing does not advance the task clock, but it does
        # let one complete browser event dispatch finish before the next
        # semantic action is injected.
        wait_between_actions=0.2,
        settle_after_actions=False,
    )
    if not done and ("frames" not in observation or "screen" not in observation):
        raise RuntimeError("env.step returned no frame-window observation")
    return observation, bool(done), dict(info)


def _step_without_observation(
    env,
    actions: list[dict[str, Any]],
    *,
    wait_between_actions: float = 0.0,
) -> tuple[bool, dict[str, Any]]:
    """Inject public actions through env.step without a screenshot round trip."""
    _observation, _reward, done, info = env.step(
        actions,
        wait_between_actions=wait_between_actions,
        capture_observation=False,
        settle_after_actions=False,
    )
    return bool(done), dict(info)


def _paused_timeline_buckets(
    groups: list[dict[str, Any]],
    *,
    observation_window_ms: int,
    trailing_delay_ms: float,
) -> list[list[dict[str, Any]]]:
    """Place each semantic visible-input group on a paused turn boundary."""
    scheduled_groups: list[tuple[list[float], list[dict[str, Any]]]] = []
    for group in groups:
        times = group.get("action_at_ms") or []
        if len(times) != len(group["actions"]):
            times = [float(group.get("at_ms") or 0)] * len(group["actions"])
        actions = [dict(action) for action in group["actions"]]
        if not actions:
            continue
        normalized_times = [max(0.0, float(at_ms)) for at_ms in times]
        scheduled_groups.append((normalized_times, actions))
    if not scheduled_groups:
        return []
    if observation_window_ms <= 0:
        # Static paused tasks still need a browser/DOM turn between distinct
        # semantic gestures. Flattening every recorded gesture into one
        # env.step can press controls belonging to a later synchronous stage
        # before that stage has replaced the visible interface.
        return [actions for _times, actions in scheduled_groups]

    buckets: list[list[dict[str, Any]]] = []
    for times, actions in scheduled_groups:
        desired_indices = [int(at_ms // observation_window_ms) for at_ms in times]
        # A semantic group is one agent turn. Never merge two independent
        # gestures merely because their live timestamps fall within the same
        # paused observation window; the first turn's frames are the visible
        # state from which the second gesture would be chosen.
        shift = max(0, len(buckets) - min(desired_indices))
        for desired_index, action in zip(desired_indices, actions):
            bucket_index = desired_index + shift
            while len(buckets) <= bucket_index:
                buckets.append([])
            buckets[bucket_index].append(action)

    last_action_ms = max(max(times) for times, _actions in scheduled_groups)
    total_ms = last_action_ms + max(0.0, float(trailing_delay_ms))
    bucket_count = max(1, math.ceil(total_ms / observation_window_ms))
    while len(buckets) < bucket_count:
        buckets.append([])
    return buckets


def _live_timeline_batches(
    groups: list[dict[str, Any]],
    *,
    initial_action_delay_ms: float,
    estimated_action_execution_ms: float = 12.0,
) -> list[dict[str, Any]]:
    """Build calibrated public-action batches for a live trace.

    Atomic mouse and keyboard actions already consume real execution time in
    ``env.step``. Re-adding every recorded browser dispatch gap as a wait
    double-counts that time; removing every gap makes dense temporal traces
    several seconds early. Preserve the recorded cadence while subtracting
    the measured 12 ms FastIO execution cost from each inter-action gap.

    Each physical group remains one ordinary ``env.step`` call. The caller
    schedules group starts against the absolute trace clock, preventing a
    small within-group estimate error from accumulating across the trace.
    """
    batches: list[dict[str, Any]] = []
    for group in groups:
        times = group.get("action_at_ms") or []
        if len(times) != len(group["actions"]):
            # Uncompacted trusted traces retain the original timestamp on
            # each action. Compaction promotes those values to
            # ``action_at_ms``; direct motor replays deliberately bypass
            # compaction, so recover the same cadence here.
            times = [
                float(action.get("_trace_time_ms", group.get("at_ms") or 0))
                for action in group["actions"]
            ]
        scheduled: list[tuple[float, dict[str, Any]]] = []
        for action, at_ms in zip(group["actions"], times):
            clean = {
                key: copy.deepcopy(value)
                for key, value in action.items()
                if not key.startswith("_trace_")
            }
            if clean.get("action") == "wait":
                # Short waits are recorder dispatch latency and are rebuilt
                # from the semantic timestamps below. Preserve an explicit
                # long hold if a trace contains one.
                seconds = max(0.0, float(clean.get("time") or 0))
                if seconds < 0.12:
                    continue
            scheduled.append((
                max(0.0, initial_action_delay_ms + float(at_ms)),
                clean,
            ))
        if not scheduled:
            continue
        actions: list[dict[str, Any]] = []
        previous_target_ms = scheduled[0][0]
        for index, (target_ms, action) in enumerate(scheduled):
            if index:
                gap_ms = max(
                    0.0,
                    target_ms - previous_target_ms - estimated_action_execution_ms,
                )
                if gap_ms >= 1:
                    actions.append({"action": "wait", "time": gap_ms / 1000})
            actions.append(action)
            previous_target_ms = max(previous_target_ms, target_ms)
        batches.append({
            "target_start_ms": scheduled[0][0],
            "target_end_ms": max(item[0] for item in scheduled),
            "actions": actions,
            "semantic_action_count": len(scheduled),
            "estimated_action_execution_ms": estimated_action_execution_ms,
        })
    return batches


def _lidar_visible_heading(
    observation: dict[str, Any],
    transform,
    working_dir: Path,
    *,
    expected_degrees: float,
) -> float:
    """Read the heading printed in the visible LIDAR status panel."""
    from PIL import Image

    screen = Path(str((observation.get("screen") or {}).get("path") or ""))
    if not screen.is_file():
        raise RuntimeError("LIDAR env.step observation has no readable screenshot")
    center_x, center_y = transform(1297, 330)
    expected = ((expected_degrees + 180) % 360) - 180
    with Image.open(screen) as source:
        gray = source.convert("L")
        source_crop = gray.crop((
            center_x - 22,
            center_y - 11,
            center_x + 23,
            center_y + 10,
        ))
        crops = [
            ("nearest", source_crop, Image.Resampling.NEAREST),
            ("lanczos", source_crop, Image.Resampling.LANCZOS),
        ]
        candidates: list[float] = []
        for label, crop, resampling in crops:
            crop = crop.resize(
                (crop.width * 12, crop.height * 12),
                resampling,
            )
            crop_path = working_dir / f"lidar-visible-heading-{label}.png"
            crop.save(crop_path)
            completed = subprocess.run(
                ["tesseract", str(crop_path), "stdout", "--psm", "8"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            text_value = completed.stdout.strip().lower().replace("°", "")
            # At this tiny visible type size Tesseract occasionally reads the
            # leading Courier 8 as ``o``.
            if re.fullmatch(r"o\d{1,2}", text_value):
                text_value = "8" + text_value[1:]
            match = re.search(r"-?\d{1,3}", text_value)
            if match is None:
                continue
            value = float(match.group())
            if expected < -45 and value > 45 and abs(value - abs(expected)) <= 20:
                value = -value
            value = ((value + 180) % 360) - 180
            candidates.append(value)
        # This is a closed-loop observer: a large physical overshoot is the
        # very condition it must report.  Filtering OCR readings by proximity
        # to the requested heading silently converted real overshoots into the
        # desired value and defeated the correction loop.
        if not candidates:
            return float(round(expected))
        return min(
            candidates,
            key=lambda candidate: abs(((candidate - expected + 180) % 360) - 180),
        )


def _direct_lidar_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
    working_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Solve continuous LIDAR controls as a closed-loop env.step agent.

    The route is privileged oracle information, but every physical hold and
    click is delivered by GymAnythingEnv.step. Heading corrections use only
    the status text in screenshots returned by env.step.
    """
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_lidar_closed_loop_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "lidar_blacksite.py",
    )
    public, truth = generator.generate(task, str(trace["ground_truth_seed"]))
    solution = truth["solution"]
    route = [tuple(map(float, point)) for point in solution["route_points"]]
    scan_indices = {int(value) for value in solution["scan_route_indices"]}
    beacon_index = int(solution["beacon_route_index"])
    controls = truth["controls"]
    if str(entry["interaction"]) != "simplified":
        raise RuntimeError("closed-loop LIDAR env.step driver currently expects its sampled simplified controls")

    points = {
        "forward": list(transform(1422, 485)),
        "back": list(transform(1422, 561)),
        "strafe_left": list(transform(1375, 561)),
        "strafe_right": list(transform(1469, 561)),
        "turn_left": list(transform(1375, 523)),
        "turn_right": list(transform(1469, 523)),
        "scan": list(transform(1422, 611)),
        "pickup": list(transform(1345, 655)),
        "verify": list(transform(1499, 655)),
    }
    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    working_dir.mkdir(parents=True, exist_ok=True)
    for prior in working_dir.glob("step-*.png"):
        prior.unlink()

    def step(actions: list[dict[str, Any]]) -> None:
        nonlocal observation, done, info, steps
        observation, _reward, done, info = env.step(
            actions,
            wait_between_actions=0.0,
            settle_after_actions=False,
        )
        steps += 1
        screen = Path(str((observation.get("screen") or {}).get("path") or ""))
        if screen.is_file():
            working_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(screen, working_dir / f"step-{steps:03d}.png")

    def click(name: str) -> None:
        step([{"mouse": {"left_click": points[name]}}])

    def hold_windows(name: str, held_windows: int) -> None:
        # Paused input is delivered before the observation window.  A down
        # and up in the same action batch would therefore finish while task
        # time is still frozen and produce no continuous motion.  Keep the
        # visible control physically held across whole observation windows,
        # then release it on the following paused boundary.
        point = points[name]
        held_windows = max(1, int(held_windows))
        step([
            {"mouse": {"move": point}},
            {"mouse": {"buttons": {"left_down": True}}},
        ])
        for _ in range(held_windows - 1):
            step([])
        step([{"mouse": {"buttons": {"left_up": True}}}])

    window_seconds = int(entry["observation_window_ms"]) / 1000
    movement_per_window = float(controls["move_speed"]) * window_seconds
    turn_per_window = math.radians(float(controls["turn_speed_deg"])) * window_seconds
    initial_heading = float(truth["initial_player"]["heading_millirad"]) / 1000
    predicted_position = [
        float(truth["initial_player"]["x"]),
        float(truth["initial_player"]["y"]),
    ]

    # A paused observation is an indivisible 500 ms control interval here.
    # The facility route is axis aligned, so keep the initial heading fixed
    # and use the task's visible W/S/A/D controls for all four world-cardinal
    # directions. This avoids turning a 90-degree corridor corner with the
    # task's 50-degree paused turn quantum.
    forward_vector = (math.cos(initial_heading), math.sin(initial_heading))
    strafe_vector = (-math.sin(initial_heading), math.cos(initial_heading))

    def move_to(waypoint: tuple[float, float]) -> None:
        delta = (
            float(waypoint[0]) - predicted_position[0],
            float(waypoint[1]) - predicted_position[1],
        )
        forward_amount = delta[0] * forward_vector[0] + delta[1] * forward_vector[1]
        strafe_amount = delta[0] * strafe_vector[0] + delta[1] * strafe_vector[1]
        if abs(forward_amount) >= abs(strafe_amount):
            name = "forward" if forward_amount >= 0 else "back"
            signed_amount = forward_amount
            vector = forward_vector
        else:
            name = "strafe_right" if strafe_amount >= 0 else "strafe_left"
            signed_amount = strafe_amount
            vector = strafe_vector
        windows = max(1, round(abs(signed_amount) / movement_per_window))
        sign = 1 if signed_amount >= 0 else -1
        hold_windows(name, windows)
        predicted_position[0] += vector[0] * movement_per_window * windows * sign
        predicted_position[1] += vector[1] * movement_per_window * windows * sign

    def scan_toward(waypoint: tuple[float, float]) -> None:
        desired = math.atan2(
            float(waypoint[1]) - predicted_position[1],
            float(waypoint[0]) - predicted_position[0],
        )
        difference = (desired - initial_heading + math.pi) % (2 * math.pi) - math.pi
        turn_windows = round(abs(difference) / turn_per_window)
        if turn_windows:
            direction = "turn_right" if difference > 0 else "turn_left"
            inverse = "turn_left" if difference > 0 else "turn_right"
            hold_windows(direction, turn_windows)
            click("scan")
            hold_windows(inverse, turn_windows)
        else:
            click("scan")

    for index, waypoint in enumerate(route):
        if index:
            move_to(waypoint)
        if index in scan_indices:
            if index < len(route) - 1:
                scan_toward(route[index + 1])
            else:
                click("scan")
        if index == beacon_index:
            click("pickup")
    click("verify")
    return observation, done, info, steps


def _marionette_visible_target_lengths(
    observation: dict[str, Any],
    transform,
) -> list[int]:
    """Recover the four visible ring targets from an env.step screenshot."""
    import cv2

    screen = Path(str((observation.get("screen") or {}).get("path") or ""))
    image = cv2.imread(str(screen))
    if image is None:
        raise RuntimeError("Marionette env.step observation has no readable screenshot")
    left, top = transform(10, 132)
    right, bottom = transform(963, 638)
    crop = image[top:bottom + 1, left:right + 1]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=35,
        param1=100,
        param2=20,
        minRadius=15,
        maxRadius=30,
    )
    if circles is None:
        raise RuntimeError("visible Marionette screenshot contains no inspection rings")
    candidates = [
        (float(x) + left, float(y) + top, float(radius))
        for x, y, radius in circles[0]
        if top + 70 <= float(y) + top <= bottom - 35
    ]
    # HoughCircles occasionally proposes a joint or curved limb as a fifth
    # circle.  The actual inspection rings are the only circles whose annuli
    # contain the visible lime stroke, so rank detections using screenshot
    # pixels instead of assuming that the detector returns exactly four.
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    lime = cv2.inRange(hsv, (25, 90, 120), (55, 255, 255))

    def lime_score(candidate: tuple[float, float, float]) -> int:
        x, y, radius = candidate
        mask = cv2.circle(
            cv2.UMat(lime.shape[0], lime.shape[1], cv2.CV_8UC1).get(),
            (round(x), round(y)),
            round(radius + 4),
            255,
            thickness=-1,
        )
        return int(cv2.countNonZero(cv2.bitwise_and(lime, mask)))

    candidates = sorted(candidates, key=lime_score, reverse=True)[:4]
    if len(candidates) != 4 or min(map(lime_score, candidates)) < 100:
        raise RuntimeError(
            f"visible Marionette screenshot yielded {len(candidates)} credible inspection rings"
        )
    upper = sorted(sorted(candidates, key=lambda item: item[1])[:2], key=lambda item: item[0])
    lower = sorted(sorted(candidates, key=lambda item: item[1])[2:], key=lambda item: item[0])
    internal_y = lambda screen_y: (screen_y - top) * 480 / max(1, bottom - top)
    lengths = [
        50 + (internal_y(upper[0][1]) - 220) / 2.05,
        50 + (internal_y(upper[1][1]) - 220) / 2.05,
        50 + (internal_y(lower[0][1]) - 365) / 1.55,
        50 + (internal_y(lower[1][1]) - 365) / 1.55,
    ]
    return [max(20, min(80, round(value))) for value in lengths]


def _marionette_visible_status(
    observation: dict[str, Any],
    transform,
) -> tuple[int, int, float]:
    """Read the visible ACT/FRAME counters and the screenshot's current age."""
    import cv2

    screen = Path(str((observation.get("screen") or {}).get("path") or ""))
    image = cv2.imread(str(screen))
    if image is None:
        raise RuntimeError("Marionette env.step observation has no readable screenshot")
    left, top = transform(10, 132)
    right, bottom = transform(760, 198)
    crop = image[top:bottom + 1, left:right + 1]
    crop = cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    encoded_ok, encoded = cv2.imencode(".png", crop)
    if not encoded_ok:
        raise RuntimeError("could not encode the visible Marionette status line")
    result = subprocess.run(
        ["tesseract", "stdin", "stdout", "--psm", "7"],
        input=encoded.tobytes(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    text = result.stdout.decode("utf-8", errors="replace").upper()
    act_match = re.search(r"\bACT\s*(\d+)\s*/", text)
    frame_match = re.search(r"\bFRAME\s*(\d+)\b", text)
    if result.returncode or act_match is None or frame_match is None:
        raise RuntimeError(
            "could not read visible Marionette ACT/FRAME counters: "
            f"tesseract={result.returncode}, text={text!r}"
        )
    age_ms = max(0.0, (time.time() - screen.stat().st_mtime) * 1000)
    return int(act_match.group(1)), int(frame_match.group(1)), age_ms


def _direct_marionette_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Track generated choreography while every slider action uses env.step."""
    if str(entry["interaction"]) != "simplified":
        raise RuntimeError("closed-loop Marionette driver expects its sampled simplified controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_marionette_closed_loop_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "_interaction_vii_viii_common.py",
    )
    _public, truth = generator.generate(
        "marionette_checkpoint",
        task,
        str(trace["ground_truth_seed"]),
    )
    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    evidence_dir.mkdir(parents=True, exist_ok=True)
    slider_min_x, _ = transform(1078, 170)
    slider_max_x, _ = transform(1214, 170)
    slider_ys = [transform(1146, y)[1] for y in (170, 204, 238, 272)]
    steps = 0

    def capture() -> None:
        nonlocal observation, done, info, steps
        observation, _reward, done, info = env.step(
            [],
            wait_between_actions=0.0,
            settle_after_actions=False,
        )
        steps += 1
        screen = Path(str((observation.get("screen") or {}).get("path") or ""))
        if screen.is_file():
            shutil.copy2(screen, evidence_dir / f"step-{steps:03d}.png")

    # Paused task time advances only while env.step captures the next frame
    # window.  Choose one constant rack position that covers the complete
    # upcoming window, then observe the visible ACT/FRAME counters again.  Wall
    # time between calls is irrelevant and must not be projected into puppet
    # ticks.
    tick_ms = float(condition["difficulty_parameters"]["tick_ms"])
    horizon = math.ceil(int(entry["observation_window_ms"]) / tick_ms) + 1
    act_number, visible_tick, _screenshot_age_ms = _marionette_visible_status(
        observation, transform,
    )
    if act_number != 1:
        raise RuntimeError(f"fresh Marionette run unexpectedly began on act {act_number}")
    for _turn in range(120):
        if done or act_number > len(truth["poses"]):
            break
        pose = truth["poses"][act_number - 1]
        targets = []
        for index, base in enumerate(pose["base_lengths"]):
            values = [
                float(base)
                + float(pose["amplitudes"][index])
                * math.sin(
                    tick * float(pose["angular_rate"])
                    + float(pose["phases"][index])
                )
                for tick in range(visible_tick + 1, visible_tick + horizon + 1)
            ]
            targets.append(round(sum(values) / len(values)))
        actions = []
        for target, y in zip(targets, slider_ys):
            x = round(
                slider_min_x
                + (target - 20) / 60 * (slider_max_x - slider_min_x)
            )
            actions.append({"mouse": {"left_click": [x, y]}})
        observation, _reward, done, info = env.step(
            actions,
            wait_between_actions=0.03,
            settle_after_actions=False,
        )
        steps += 1
        if done:
            break
        screen = Path(str((observation.get("screen") or {}).get("path") or ""))
        if screen.is_file():
            shutil.copy2(screen, evidence_dir / f"step-{steps:03d}.png")
        act_number, visible_tick, _screenshot_age_ms = _marionette_visible_status(
            observation, transform,
        )
    return observation, done, info, steps


def _direct_pheromone_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Paint and refresh continuous fields without open-loop event coalescing.

    The generated reference paths are privileged solve information. Every
    field selection, continuous pointer stroke, dispatch click, and elapsed
    interval is nevertheless delivered through ``GymAnythingEnv.step``.
    Short waits between pointer samples ensure that the browser observes the
    same continuous geometry instead of coalescing a whole stroke to its end.
    """
    if str(entry["interaction"]) != "full":
        raise RuntimeError("closed-loop Pheromone driver expects its sampled full controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_pheromone_closed_loop_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "pheromone_dispatch.py",
    )
    public, truth = generator.generate(task, str(trace["ground_truth_seed"]))

    # These are visible geometry in the recorded initial screenshot. Mapping
    # through the current initial screenshot preserves the actual UI surface
    # while truth supplies only which route to draw.
    field_points = {
        "amber": list(transform(1691, 232)),
        "violet": list(transform(1829, 232)),
    }
    dispatch_point = list(transform(1760, 288))
    canvas_left, canvas_top = 10.0, 123.0
    canvas_width, canvas_height = 1593.0, 885.0

    def screen(point: list[float]) -> list[int]:
        source = (
            round(canvas_left + float(point[0]) / 900 * canvas_width),
            round(canvas_top + float(point[1]) / 480 * canvas_height),
        )
        return list(transform(*source))

    def dense_path(field_id: str) -> list[list[int]]:
        path = truth["reference_paths"][field_id]
        cache = next(
            list(field["cache"])
            for field in public["fields"]
            if str(field["id"]) == field_id
        )
        points = [list(path[0])]
        for first, second in zip(path, path[1:]):
            # Keep samples well inside the game's 160-unit continuity limit.
            # The serialized wait following each point below gives the page a
            # chance to observe every part of the held-button gesture.
            steps = max(1, math.ceil(math.dist(first, second) / 45))
            points.extend([
                [
                    float(first[0]) + (float(second[0]) - float(first[0])) * step / steps,
                    float(first[1]) + (float(second[1]) - float(first[1])) * step / steps,
                ]
                for step in range(1, steps + 1)
            ])
            if math.dist(second, cache) < .01:
                # USB tablet events can occasionally skip an intermediate
                # pointer position even when wall time separates the moves.
                # Sweep a small visible cluster through the cache so at least
                # one browser-observed sample remains inside its hit radius.
                cx, cy = float(cache[0]), float(cache[1])
                points.extend([
                    [cx - 28, cy],
                    [cx - 14, cy + 8],
                    [cx, cy],
                    [cx + 14, cy - 8],
                    [cx + 28, cy],
                    [cx, cy],
                ])
        return [screen(point) for point in points]

    routes = {field_id: dense_path(field_id) for field_id in truth["reference_paths"]}
    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def step(
        actions: list[dict[str, Any]],
        *,
        capture: bool = False,
        action_spacing: float = 0.0,
    ) -> None:
        nonlocal observation, done, info, steps
        if capture:
            observation, _reward, done, info = env.step(
                actions,
                wait_between_actions=action_spacing,
                settle_after_actions=False,
            )
        else:
            done, info = _step_without_observation(
                env,
                actions,
                wait_between_actions=action_spacing,
            )
        steps += 1
        if done:
            # The visible terminal card can be painted just before the
            # mechanics' asynchronous submission POST reaches the loopback
            # server. Keep the VM alive long enough for that already-issued
            # request to be persisted before the program verifier reads it.
            time.sleep(1.0)
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        if capture and screen_path.is_file():
            shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")

    def paint(field_id: str) -> None:
        route = routes[field_id]
        step([{"mouse": {"left_click": field_points[field_id]}}])
        actions: list[dict[str, Any]] = [
            {"mouse": {"move": route[0]}},
            {"mouse": {"buttons": {"left_down": True}}},
            {"action": "wait", "time": .07},
        ]
        for point in route[1:]:
            actions.extend([
                {"mouse": {"move": point}},
                {"action": "wait", "time": .07},
            ])
        actions.extend([
            {"action": "wait", "time": .07},
            {"mouse": {"buttons": {"left_up": True}}},
        ])
        # One env.step owns the complete held-button gesture. Keeping the
        # delays in the public action sequence preserves pointer capture while
        # ensuring that the page samples the route between USB pointer moves.
        step(actions)

    for field_id in routes:
        paint(field_id)
    # Move, press, and release explicitly after the final canvas pointer
    # capture has ended. This is the same visible button operation an agent
    # performs, while ensuring the browser observes the move out of canvas
    # before the click rather than coalescing both pointer transitions.
    step([
        {"mouse": {"move": dispatch_point}},
        {"action": "wait", "time": .08},
        {"mouse": {"buttons": {"left_down": True}}},
        {"action": "wait", "time": .04},
        {"mouse": {"buttons": {"left_up": True}}},
    ], capture=True)
    # Each env.step observation itself advances the sampled live world. Keep
    # alternating complete fields; this is intentionally closed-loop at the
    # task/API boundary and stops as soon as the Gym verifier terminates.
    tick_ms = int(public["physics"]["tick_ms"])
    shortest_ttl = min(int(field["trail_ttl_ticks"]) for field in public["fields"])
    conservative_ticks_per_window = math.ceil(int(entry["observation_window_ms"]) / tick_ms)
    refresh_every = max(1, shortest_ttl // max(1, 2 * conservative_ticks_per_window))
    for _round in range(24):
        if _round and _round % refresh_every == 0:
            for field_id in routes:
                if done:
                    return observation, done, info, steps
                paint(field_id)
        if not done:
            # Only an observation advances paused task time.  A wall-clock
            # wait injected with capture_observation=False leaves both ant
            # populations frozen at the dispatch boundary.
            step([], capture=True)
    if not done:
        # Archive the complete visible stroke ledger when delivery did not
        # terminate, using the task's explicit failure control via env.step.
        step([{"mouse": {"left_click": list(transform(1760, 372))}}], capture=True)
    return observation, done, info, steps


def _direct_clockwork_doppelganger_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Record coarse paused-window loops and phase their visible controls."""
    if str(entry["interaction"]) != "full" or str(entry["time_mode"]) != "paused":
        raise RuntimeError("clockwork direct driver expects its sampled Full paused controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_clockwork_doppelganger_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "clockwork_doppelganger_customs.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def step(actions: list[dict[str, Any]], *, capture: bool = True) -> None:
        nonlocal observation, done, info, steps
        if capture:
            observation, _reward, done, info = env.step(
                actions,
                wait_between_actions=0.0,
                settle_after_actions=False,
            )
        else:
            done, info = _step_without_observation(env, actions)
        steps += 1
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        if capture and screen_path.is_file():
            shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")

    # Trace compaction may merge adjacent timing groups. Identify the visible
    # controls by their stable layout instead of assigning semantic meaning to
    # a group ordinal. The five stations form the left-to-right track; the
    # three record and phase controls form two right-side columns.
    distinct_clicks = sorted({
        (int(point[0]), int(point[1]))
        for group in groups
        for action in group["actions"]
        if isinstance((point := (action.get("mouse") or {}).get("left_click")), list)
        and len(point) == 2
    })
    if len(distinct_clicks) < 13:
        raise RuntimeError(
            f"clockwork trace exposed only {len(distinct_clicks)} distinct visible controls"
        )
    submit_button = list(max(distinct_clicks, key=lambda point: point[1]))
    without_submit = [point for point in distinct_clicks if point != tuple(submit_button)]
    run_button = list(max(without_submit, key=lambda point: point[1]))
    main_controls = [point for point in without_submit if point != tuple(run_button)]
    ordered_x = sorted(main_controls, key=lambda point: point[0])
    stations = [list(point) for point in ordered_x[:5]]
    phase_controls = [list(point) for point in sorted(
        ordered_x[5:8], key=lambda point: point[1]
    )]
    record_buttons = [list(point) for point in sorted(
        ordered_x[8:], key=lambda point: point[1]
    )]
    if len(record_buttons) != 3 or len(phase_controls) != 3 or len(stations) != 5:
        raise RuntimeError(
            "clockwork visible control classification failed: "
            f"records={len(record_buttons)}, phases={len(phase_controls)}, stations={len(stations)}"
        )
    role_targets = [
        stations[:2],
        stations[1:4],
        stations[3:],
    ]

    for slot, targets in enumerate(role_targets):
        # Action injection does not consume paused task time. Start the take
        # and punch its first station at the same frozen boundary, then use
        # one ordinary env.step window per next station. This gives the game
        # a replayable 0/800/1600/... task-time path without depending on the
        # host time spent executing an action list.
        step([
            {"mouse": {"move": targets[0]}},
            {"mouse": {"left_click": record_buttons[slot]}},
            {"mouse": {"left_click": targets[0]}},
        ])
        for target in targets[1:]:
            step([{"mouse": {"left_click": target}}])
        elapsed_windows = len(targets)
        required_windows = math.ceil(
            int(truth["controls"]["record_duration_ms"])
            / int(entry["observation_window_ms"])
        )
        for _ in range(elapsed_windows, required_windows):
            step([])

    phase_step = int(truth["controls"]["phase_step_ms"])
    catch_time = int(truth["conveyor"]["catch_time_ms"])
    gap = int(truth["solution"]["handoff_gap_ms"])
    action_time_maps = [
        {"grab": 0, "release": 800},
        {"grab": 0, "stamp": 800, "release": 1600},
        {"grab": 0, "release": 800},
    ]
    phases: list[int] = []
    for slot, times in enumerate(action_time_maps):
        target = catch_time if slot == 0 else phases[slot - 1] + action_time_maps[slot - 1]["release"] + gap
        phases.append(round((target - times["grab"]) / phase_step) * phase_step)
    phase_actions: list[dict[str, Any]] = []
    for control, phase in zip(phase_controls, phases, strict=True):
        plus_button = [control[0] + 220, control[1]]
        increments = phase // phase_step
        phase_actions.extend(
            {"mouse": {"triple_click": plus_button}}
            for _ in range(increments // 3)
        )
        if increments % 3 == 2:
            phase_actions.append({"mouse": {"double_click": plus_button}})
        elif increments % 3 == 1:
            phase_actions.append({"mouse": {"left_click": plus_button}})
    step(phase_actions)

    step([{"mouse": {"left_click": run_button}}])
    window_ms = max(1, int(entry["observation_window_ms"]))
    loop_windows = math.ceil(int(truth["controls"]["loop_duration_ms"]) / window_ms) + 2
    for _ in range(loop_windows):
        if done:
            return observation, done, info, steps
        step([])
    if not done:
        step([{"mouse": {"left_click": submit_button}}])
    return observation, done, info, steps


def _direct_polyrhythm_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    groups: list[dict[str, Any]],
    transform,
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Perform the generated score with within-action timing through env.step."""
    import cv2

    if str(entry["interaction"]) != "simplified" or str(entry["time_mode"]) != "paused":
        raise RuntimeError("polyrhythm direct driver expects its sampled Simplified paused controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_polyrhythm_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "polyrhythm_customs.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))

    clicks = [
        [int(point[0]), int(point[1])]
        for group in groups
        for action in group["actions"]
        if isinstance((point := (action.get("mouse") or {}).get("left_click")), list)
        and len(point) == 2
    ]
    if not clicks:
        raise RuntimeError("polyrhythm trace exposed no visible controls")
    start_point = max(clicks, key=lambda point: point[1])

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def step(actions: list[dict[str, Any]]) -> None:
        nonlocal observation, done, info, steps
        observation, _reward, done, info = env.step(
            actions,
            wait_between_actions=0.0,
            settle_after_actions=False,
        )
        steps += 1
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        if screen_path.is_file():
            shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")

    window_ms = int(entry["observation_window_ms"])
    settings = truth["settings"]
    preview_ms = len(truth["lanes"]) * (
        float(settings["performance_ms"]) * float(settings["preview_scale"])
        + float(settings["preview_gap_ms"])
    ) + float(settings["countdown_ms"])
    preview_windows = math.ceil(preview_ms / window_ms)

    step([{"mouse": {"left_click": start_point}}])
    for _ in range(1, preview_windows):
        step([])
    # The ledger persists until explicit certification. One additional fixed
    # window absorbs a boundary paint if countdown completion landed on the
    # final frame of the computed preview schedule.
    step([])
    # Simplified interaction is an authored blank timing ledger. Horizontal
    # position declares task time, a click declares a tap, and a drag declares
    # a held bar. This preserves the hidden score reconstruction without using
    # action-transport wall time as part of the puzzle.
    track_left = float(transform(134, 0)[0])
    track_right = float(transform(1_552, 0)[0])
    lane_top = float(transform(0, 227)[1])
    lane_bottom = float(transform(0, 462)[1])
    lane_ids = [str(lane["id"]) for lane in truth["lanes"]]
    lane_y = {
        lane_id: round(lane_top + (index + 0.5) * (lane_bottom - lane_top) / len(lane_ids))
        for index, lane_id in enumerate(lane_ids)
    }
    performance_ms = float(settings["performance_ms"])
    note_actions: list[dict[str, Any]] = []
    for note in truth["expected_notes"]:
        start_x = round(track_left + float(note["start_ms"]) / performance_ms * (track_right - track_left))
        y = lane_y[str(note["lane"])]
        if str(note["kind"]) == "hold":
            end_x = round(
                track_left
                + (float(note["start_ms"]) + float(note["duration_ms"]))
                / performance_ms
                * (track_right - track_left)
            )
            note_actions.append({"mouse": {"left_click_drag": [[start_x, y], [end_x, y]]}})
        else:
            note_actions.append({"mouse": {"left_click": [start_x, y]}})
    step(note_actions)
    if not done:
        step([{"mouse": {"left_click": list(transform(1_666, 574))}}])
    return observation, done, info, steps


def _direct_clockwork_clutch_safe_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Operate the load-coupled safe on exact paused observation boundaries."""
    if str(entry["interaction"]) != "simplified" or str(entry["time_mode"]) != "paused":
        raise RuntimeError(
            "clockwork clutch direct driver expects its sampled Simplified paused controls"
        )
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_clockwork_clutch_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "clockwork_clutch_safe.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))

    release_schedule = list(truth["release_schedule"])
    shaft_count = len(truth["initial_angles"])
    # These are stable, labelled controls in the fixed task viewport.  Map
    # their visible layout anchors into the current screenshot instead of
    # borrowing clicks from the live trace: that trace can contain repeated
    # drive-button clicks near the highly repetitive side panel, which makes
    # nearest-feature remapping ambiguous.
    drive_button = list(transform(1760, 230))
    unlock_button = list(transform(1779, 270))
    clutch_buttons = {
        0: list(transform(411, 539)),
        1: list(transform(1200, 539)),
        2: list(transform(411, 975)),
        3: list(transform(1200, 975)),
    }
    if shaft_count != len(clutch_buttons):
        raise RuntimeError("clockwork clutch direct driver expects the four-shaft layout")

    physics = dict(truth["physics"])
    tick_ms = int(physics["tick_ms"])
    ticks_per_window = int(entry["observation_window_ms"]) // tick_ms
    if ticks_per_window < 1:
        raise RuntimeError("clockwork clutch observation window is shorter than one drive tick")
    ratios = tuple(float(value) for value in truth["ratios"])
    initial_angles = tuple(round(float(value), 3) for value in truth["initial_angles"])
    drive = float(physics["drive_deg_per_tick"])
    load_numerator = int(physics["load_numerator"])
    tolerance = float(physics["phase_tolerance_deg"])
    max_windows = int(physics["max_ticks"]) // ticks_per_window

    def phase_error(angle: float) -> float:
        normalized = angle % 360.0
        return min(normalized, 360.0 - normalized)

    active_sets: list[tuple[int, tuple[float, ...]]] = []
    for mask in range(1, 1 << shaft_count):
        active_count = mask.bit_count()
        increments = tuple(
            (
                ticks_per_window
                * ratios[index]
                * drive
                * load_numerator
                / active_count
            )
            if mask & (1 << index)
            else 0.0
            for index in range(shaft_count)
        )
        active_sets.append((mask, increments))

    # Search only boundary-reachable physical states. Re-engagement is an
    # authored recovery control, so a plan may redistribute load differently
    # from the continuous live oracle while preserving the same visible goal.
    target_tolerance = max(0.0, tolerance - 1.0)
    states: dict[tuple[float, ...], tuple[int, ...]] = {initial_angles: ()}
    plan: tuple[int, ...] | None = None
    for _window in range(1, max_windows + 1):
        next_states: dict[tuple[float, ...], tuple[int, ...]] = {}
        for angles, prior_masks in states.items():
            for mask, increments in active_sets:
                updated = tuple(
                    round((angles[index] + increments[index]) % 360.0, 3)
                    for index in range(shaft_count)
                )
                next_states.setdefault(updated, prior_masks + (mask,))
                if all(phase_error(angle) <= target_tolerance for angle in updated):
                    plan = prior_masks + (mask,)
                    break
            if plan is not None:
                break
        if plan is not None:
            break
        # Four shafts produce a small exact state graph for calibrated
        # profiles. The cap only protects future profiles from unbounded
        # growth and retains the states closest to a simultaneous witness.
        if len(next_states) > 300_000:
            def state_score(angles: tuple[float, ...]) -> tuple[float, float]:
                errors = [phase_error(angle) for angle in angles]
                return max(errors), sum(error * error for error in errors)
            retained = sorted(next_states, key=state_score)[:300_000]
            states = {angles: next_states[angles] for angles in retained}
        else:
            states = next_states
    if plan is None:
        raise RuntimeError("clockwork clutch has no paused-window recovery plan")

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def step(actions: list[dict[str, Any]]) -> None:
        nonlocal observation, done, info, steps
        observation, _reward, done, info = env.step(
            actions,
            wait_between_actions=0.03,
            settle_after_actions=False,
        )
        steps += 1
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        if screen_path.is_file():
            shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")

    active_mask = (1 << shaft_count) - 1
    for window_index, desired_mask in enumerate(plan):
        actions = [
            {"mouse": {"left_click": clutch_buttons[index]}}
            for index in range(shaft_count)
            if bool(active_mask & (1 << index)) != bool(desired_mask & (1 << index))
        ]
        if window_index == 0:
            actions.append({"mouse": {"left_click": drive_button}})
        step(actions)
        if done:
            return observation, done, info, steps
        active_mask = desired_mask

    final_actions = [
        {"mouse": {"left_click": clutch_buttons[index]}}
        for index in range(shaft_count)
        if active_mask & (1 << index)
    ]
    final_actions.append({"mouse": {"left_click": unlock_button}})
    step(final_actions)
    return observation, done, info, steps


def _direct_hovercar_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    groups: list[dict[str, Any]],
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Plan fixed-window proxy states and fly the paused sampled course."""
    if str(entry["interaction"]) != "simplified" or str(entry["time_mode"]) != "paused":
        raise RuntimeError("hovercar direct driver expects its sampled Simplified paused controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_hovercar_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "crash_deadline_hovercar.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))
    physics = truth["physics"]

    all_clicks: list[tuple[int, int]] = []
    for group in groups:
        for action in group["actions"]:
            point = (action.get("mouse") or {}).get("left_click")
            if isinstance(point, list) and len(point) == 2:
                all_clicks.append((int(point[0]), int(point[1])))
    distinct = sorted(set(all_clicks), key=lambda point: (point[1], point[0]))
    submit_point = list(max(distinct, key=lambda point: point[1]))
    controls = [point for point in distinct if point != tuple(submit_point)]
    tracker_point = list(max(controls, key=lambda point: point[1]))
    grid = [point for point in controls if point != tuple(tracker_point)]
    if len(grid) != 4:
        raise RuntimeError(f"hovercar trace exposed {len(grid)} proxy drive controls")
    rows = sorted({point[1] for point in grid})
    if len(rows) != 2:
        raise RuntimeError("hovercar proxy controls did not form two visible rows")
    top = sorted((point for point in grid if point[1] == rows[0]))
    bottom = sorted((point for point in grid if point[1] == rows[1]))
    control_points = {
        "up": list(top[0]),
        "down": list(top[1]),
        "left": list(bottom[0]),
        "right": list(bottom[1]),
    }

    def road(progress: float) -> float:
        return 240 + float(physics["road_amplitude"]) * math.sin(
            progress / float(physics["road_period"]) + float(physics["road_phase"])
        )

    # State tuple: tick, progress, lateral, lateral velocity, speed.
    def physics_tick(
        state: tuple[int, float, float, float, float],
        keys: frozenset[str],
    ) -> tuple[tuple[int, float, float, float, float], str | None]:
        tick, progress, lateral, velocity, speed = state
        speed = max(
            float(physics["min_speed"]),
            min(
                float(physics["max_speed"]),
                speed
                + (float(physics["acceleration"]) if "up" in keys else 0)
                - (float(physics["brake"]) if "down" in keys else 0)
                - float(physics["drag"]),
            ),
        )
        steer = (1 if "right" in keys else 0) - (1 if "left" in keys else 0)
        velocity = (velocity + steer * float(physics["steer_gain"])) * float(physics["lateral_damping"])
        lateral += velocity
        progress += speed / 10
        tick += 1
        reason = None
        if abs(lateral - road(progress)) > float(physics["road_half_width"]) - float(physics["car_half_height"]):
            reason = "road_departure"
        for obstacle in truth["obstacles"]:
            obstacle_y = road(float(obstacle["world_x"])) + float(obstacle["lane_offset"])
            hit_x = abs(progress - float(obstacle["world_x"])) <= float(obstacle["width"]) / 2 + float(physics["car_half_width"])
            hit_y = abs(lateral - obstacle_y) <= float(obstacle["height"]) / 2 + float(physics["car_half_height"])
            if hit_x and hit_y:
                reason = str(obstacle["id"])
                break
        if tick > int(physics["deadline_tick"]):
            reason = "deadline"
        return (tick, progress, lateral, velocity, speed), reason

    ticks_per_window = max(1, round(int(entry["observation_window_ms"]) / int(physics["tick_ms"])))
    # The time controller starts the first fixed observation window from the
    # ready, zero-task-time boundary. The mechanic's virtual interval therefore
    # advances exactly one tick_ms cadence per authored window.
    import cv2

    initial_screen = Path(str((initial_observation.get("screen") or {}).get("path") or ""))
    initial_image = cv2.imread(str(initial_screen))
    if initial_image is None:
        raise RuntimeError("hovercar initial env.step screenshot is unreadable")
    height = initial_image.shape[0]
    # The footer button is flush to the viewport bottom. Feature registration
    # can pull its recorded Y coordinate below the actual control because the
    # browser chrome/footer boundary has no stable keypoints; use the visible
    # current viewport for its vertical center while retaining the registered X.
    submit_point[1] = height - 50
    # Read the fixed-step boundary actually visible in the reset observation.
    # Browser startup can consume seven ticks here rather than the nominal ten;
    # treating the window length as the observed tick shifts the whole plan and
    # can cross the finish gate before the final inspection dwell completes.
    initial_tick_crop = initial_image[
        round(initial_image.shape[0] * .67):round(initial_image.shape[0] * .79),
        round(initial_image.shape[1] * .82):round(initial_image.shape[1] * .995),
    ]
    initial_tick_crop = cv2.resize(
        initial_tick_crop,
        None,
        fx=3,
        fy=3,
        interpolation=cv2.INTER_CUBIC,
    )
    encoded_ok, encoded_tick = cv2.imencode(".png", initial_tick_crop)
    if not encoded_ok:
        raise RuntimeError("hovercar visible course-time crop could not be encoded")
    tick_ocr = subprocess.run(
        ["tesseract", "stdin", "stdout", "--psm", "6"],
        input=encoded_tick.tobytes(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    tick_text = tick_ocr.stdout.decode("utf-8", errors="replace")
    tick_match = re.search(r"COURSE\s+TIME\s+(\d+)\s*/", tick_text, re.IGNORECASE)
    if tick_ocr.returncode or tick_match is None:
        raise RuntimeError(
            "hovercar visible initial course time was unreadable: "
            f"tesseract={tick_ocr.returncode}, text={tick_text!r}"
        )
    visible_initial_tick = int(tick_match.group(1))
    initial_state = (0, 0.0, road(0), 0.0, float(physics["start_speed"]))
    empty = frozenset()
    for _ in range(visible_initial_tick):
        initial_state, reason = physics_tick(initial_state, empty)
        if reason:
            raise RuntimeError(f"hovercar crashed during its initial observation: {reason}")

    choices = [
        frozenset(key for key in (throttle, steering) if key)
        for throttle in (None, "up", "down")
        for steering in (None, "left", "right")
    ]
    minimum_finish_tick = max(
        int(target["window_start"]) + int(target["required_ticks"])
        for target in truth["targets"]
    ) + ticks_per_window
    beam: list[tuple[float, tuple[int, float, float, float, float], list[frozenset[str]]]] = [
        (0.0, initial_state, [])
    ]
    plan: list[frozenset[str]] | None = None
    for _window in range(math.ceil(int(physics["deadline_tick"]) / ticks_per_window)):
        candidates: list[tuple[float, tuple[int, float, float, float, float], list[frozenset[str]]]] = []
        for prior_cost, state, prior_plan in beam:
            for keys in choices:
                next_state = state
                reason = None
                for _ in range(ticks_per_window):
                    next_state, reason = physics_tick(next_state, keys)
                    if reason:
                        break
                if reason:
                    continue
                tick, progress, lateral, velocity, speed = next_state
                next_plan = [*prior_plan, keys]
                if progress >= float(physics["finish_progress"]):
                    if tick >= minimum_finish_tick:
                        plan = next_plan
                        break
                    continue
                desired = road(progress)
                for obstacle in truth["obstacles"]:
                    distance = float(obstacle["world_x"]) - progress
                    if -55 <= distance <= 150:
                        desired += 55 if float(obstacle["lane_offset"]) < 0 else -55
                        break
                stage_cost = (
                    abs(lateral - desired) * 2
                    + abs(velocity) * 2
                    + abs(speed - 45) * .4
                    - progress * .04
                )
                candidates.append((prior_cost * .15 + stage_cost, next_state, next_plan))
            if plan is not None:
                break
        if plan is not None:
            break
        candidates.sort(key=lambda item: item[0])
        beam = []
        seen: set[tuple[int, int, int, int]] = set()
        for candidate in candidates:
            state = candidate[1]
            identity = (
                round(state[1] / 10),
                round(state[2] / 8),
                round(state[3] / 3),
                round(state[4] / 5),
            )
            if identity in seen:
                continue
            seen.add(identity)
            beam.append(candidate)
            if len(beam) >= 1500:
                break
        if not beam:
            break
    if plan is None:
        raise RuntimeError("no collision-free paused hovercar proxy plan was found")

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def step(actions: list[dict[str, Any]]) -> None:
        nonlocal observation, done, info, steps
        observation, _reward, done, info = env.step(
            actions,
            wait_between_actions=0.08,
            settle_after_actions=False,
        )
        steps += 1
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        if screen_path.is_file():
            shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")

    held: frozenset[str] = frozenset()
    for window_index, desired in enumerate(plan):
        actions: list[dict[str, Any]] = []
        if window_index == 0:
            actions.append({"mouse": {"left_click": tracker_point}})
        for key in sorted(held ^ desired):
            actions.append({"mouse": {"left_click": control_points[key]}})
        step(actions)
        held = desired
    if not done:
        step([{"mouse": {"left_click": submit_point}}])
    return observation, done, info, steps


def _direct_palimpsest_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    groups: list[dict[str, Any]],
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Scan and capture moving echoes through the sampled coordinate UI."""
    if str(entry["interaction"]) != "simplified" or str(entry["time_mode"]) != "paused":
        raise RuntimeError("palimpsest direct driver expects its sampled Simplified paused controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_palimpsest_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "cursor_lens_reveal.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))

    all_actions = [action for group in groups for action in group["actions"]]
    distinct_clicks = sorted({
        (int(point[0]), int(point[1]))
        for action in all_actions
        if isinstance((point := (action.get("mouse") or {}).get("left_click")), list)
        and len(point) == 2
    })
    submit_button = list(max(distinct_clicks, key=lambda point: point[1]))
    initial_screen = Path(str((initial_observation.get("screen") or {}).get("path") or ""))
    import cv2

    initial_image = cv2.imread(str(initial_screen))
    if initial_image is None:
        raise RuntimeError("palimpsest initial env.step screenshot is unreadable")
    # The footer submit is intentionally clipped by the 1080 px viewport.
    # Local repeated-line registration can pull its Y coordinate upward; its
    # X coordinate remains registered and the visible button occupies the
    # final 33 px of the current screenshot.
    submit_button[1] = int(initial_image.shape[0] - 16)
    input_points: list[list[int]] = []
    last_click: list[int] | None = None
    for action in all_actions:
        point = (action.get("mouse") or {}).get("left_click")
        if isinstance(point, list) and len(point) == 2:
            last_click = [int(point[0]), int(point[1])]
        if (action.get("keyboard") or {}).get("text") is not None and last_click is not None:
            if last_click not in input_points:
                input_points.append(last_click)
            if len(input_points) == 2:
                break
    if len(input_points) != 2:
        raise RuntimeError("palimpsest trace did not expose both visible coordinate fields")
    x_input, y_input = input_points
    input_row_y = round((x_input[1] + y_input[1]) / 2)
    button_row = sorted(
        (
            list(point)
            for point in distinct_clicks
            if point not in {tuple(x_input), tuple(y_input), tuple(submit_button)}
            and input_row_y < point[1] <= input_row_y + 90
        ),
        key=lambda point: point[0],
    )
    polarization_row = sorted(
        (
            list(point)
            for point in distinct_clicks
            if point[1] < input_row_y - 30
        ),
        key=lambda point: point[0],
    )
    if len(button_row) != 2 or len(polarization_row) != 2:
        raise RuntimeError(
            "palimpsest visible control classification failed: "
            f"buttons={len(button_row)}, polarization={len(polarization_row)}"
        )
    move_button, capture_button = button_row
    pol_left, pol_right = polarization_row

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def step(actions: list[dict[str, Any]]) -> None:
        nonlocal observation, done, info, steps
        observation, _reward, done, info = env.step(
            actions,
            wait_between_actions=0.03,
            settle_after_actions=False,
        )
        steps += 1
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        if screen_path.is_file():
            shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")

    # Input fields and their adjacent buttons need distinct browser dispatches;
    # the wall spacing does not advance paused task time.
    def position_actions(point: list[float], *, move: bool = True) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = [
            {"mouse": {"left_click": x_input}},
            {"keyboard": {"keys": ["ctrl", "a"]}},
            {"keyboard": {"text": f"{float(point[0]):.2f}"}},
            {"mouse": {"left_click": y_input}},
            {"keyboard": {"keys": ["ctrl", "a"]}},
            {"keyboard": {"text": f"{float(point[1]):.2f}"}},
        ]
        if move:
            actions.append({"mouse": {"left_click": move_button}})
        return actions

    # Build the required broad visible scan while task time remains paused.
    scan_actions: list[dict[str, Any]] = []
    for row in range(6):
        for column in range(8):
            scan_actions.extend(position_actions([55 + column * 116, 42 + row * 82]))
    step(scan_actions)

    elapsed_ms = int(entry["observation_window_ms"]) * 2
    polarization = 0
    for node in truth["nodes"]:
        target = int(node["polarization_deg"])
        clockwise = ((target - polarization) % 180) // 45
        counter = ((polarization - target) % 180) // 45
        tune_button = pol_right if clockwise <= counter else pol_left
        tune_count = clockwise if clockwise <= counter else counter
        actions = [{"mouse": {"left_click": tune_button}} for _ in range(tune_count)]
        polarization = target
        motion = node["motion"]
        angle = math.tau * elapsed_ms / float(motion["period_ms"]) + float(motion["phase"])
        point = [
            float(node["base"][0]) + float(motion["radius_x"]) * math.sin(angle),
            float(node["base"][1]) + float(motion["radius_y"]) * math.cos(angle * float(motion["ratio"])),
        ]
        actions.extend(position_actions(point))
        actions.append({"mouse": {"left_click": capture_button}})
        step(actions)
        elapsed_ms += int(entry["observation_window_ms"])
    if not done:
        step([{"mouse": {"left_click": submit_button}}])
    return observation, done, info, steps


def _direct_panorama_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    groups: list[dict[str, Any]],
    transform,
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Frame the generated specimen and expose it on a paused event onset."""
    if str(entry["interaction"]) != "full" or str(entry["time_mode"]) != "paused":
        raise RuntimeError("panorama direct driver expects its sampled Full paused controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_panorama_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "impossible_panorama.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))

    all_actions = [action for group in groups for action in group["actions"]]
    clicks = [
        [int(point[0]), int(point[1])]
        for action in all_actions
        if isinstance((point := (action.get("mouse") or {}).get("left_click")), list)
        and len(point) == 2
    ]
    if len(clicks) < 3:
        raise RuntimeError("panorama trace did not expose its two sliders and submit control")
    zoom_slider, focus_slider = clicks[:2]
    submit_button = clicks[-1]
    shutter_button: list[int] | None = None
    last_move: list[int] | None = None
    for action in all_actions:
        mouse = action.get("mouse") or {}
        point = mouse.get("move")
        if isinstance(point, list) and len(point) == 2:
            last_move = [int(point[0]), int(point[1])]
        if (mouse.get("buttons") or {}).get("left_down") and last_move is not None:
            shutter_button = list(last_move)
    if shutter_button is None:
        raise RuntimeError("panorama trace did not expose the visible shutter hold")

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def step(actions: list[dict[str, Any]]) -> None:
        nonlocal observation, done, info, steps
        observation, _reward, done, info = env.step(
            actions,
            wait_between_actions=0.03,
            settle_after_actions=False,
        )
        steps += 1
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        if screen_path.is_file():
            shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")

    solution = truth["solution"]
    controls = truth["controls"]
    zoom = float(solution["zoom"])
    zoom_presses = round((zoom - float(controls["zoom_min"])) / float(controls["zoom_step"]))
    focus_presses = round(
        (float(solution["target_depth"]) - float(controls["focus_min"]))
        / float(controls["focus_step"])
    )
    setup_actions: list[dict[str, Any]] = [
        {"mouse": {"left_click": zoom_slider}},
        {"keyboard": {"keys": ["home"]}},
    ]
    setup_actions.extend({"keyboard": {"keys": ["right"]}} for _ in range(zoom_presses))
    setup_actions.extend([
        {"mouse": {"left_click": focus_slider}},
        {"keyboard": {"keys": ["home"]}},
    ])
    setup_actions.extend({"keyboard": {"keys": ["right"]}} for _ in range(focus_presses))

    # Full interaction exposes only the canvas drag. Convert the privileged
    # target camera delta into ordinary short physical drags whose intrinsic
    # canvas steps remain below the grader's 225 px movement ceiling.
    initial_camera = truth["initial_camera"]
    target_camera = solution["target_base"]
    viewport = truth["viewport"]
    canvas_left, canvas_center_y = transform(363, 344)
    canvas_right, _ = transform(1259, 344)
    canvas_center_x, canvas_top = transform(811, 123)
    _, canvas_bottom = transform(811, 565)
    canvas_width = float(canvas_right - canvas_left)
    canvas_height = float(canvas_bottom - canvas_top)
    center = [int(canvas_center_x), int(canvas_center_y)]
    total_intrinsic_x = -(float(target_camera["x"]) - float(initial_camera["x"])) * zoom
    total_intrinsic_y = -(float(target_camera["y"]) - float(initial_camera["y"])) * zoom
    segment_count = max(1, math.ceil(math.hypot(total_intrinsic_x, total_intrinsic_y) / 175))
    total_screen_x = total_intrinsic_x / float(viewport["width"]) * canvas_width
    total_screen_y = total_intrinsic_y / float(viewport["height"]) * canvas_height
    prior_x = prior_y = 0
    for segment in range(1, segment_count + 1):
        cumulative_x = round(total_screen_x * segment / segment_count)
        cumulative_y = round(total_screen_y * segment / segment_count)
        delta_x, delta_y = cumulative_x - prior_x, cumulative_y - prior_y
        prior_x, prior_y = cumulative_x, cumulative_y
        setup_actions.append({
            "mouse": {
                "left_click_drag": [
                    center,
                    [center[0] + delta_x, center[1] + delta_y],
                ]
            }
        })
    step(setup_actions)

    # Setup consumed one observation window. Select the first generated event
    # whose next boundary leaves a complete two-window hold inside its authored
    # visibility interval, then reach it using ordinary no-action env.step turns.
    window_ms = int(entry["observation_window_ms"])
    hold_ms = window_ms * 2
    # Reset already delivered one window and setup delivered a second.
    current_task_ms = window_ms * 2
    event = truth["event_contract"]
    period_ms = int(event["period_ms"])
    offset_ms = int(event["offset_ms"])
    event_index = max(1, math.ceil((current_task_ms + offset_ms) / period_ms))
    while True:
        # The browser phase is `(task_time + offset) % period < window`, so
        # each onset is n*period-offset, not offset+n*period.
        onset_ms = event_index * period_ms - offset_ms
        boundary_ms = math.ceil(onset_ms / window_ms) * window_ms
        if boundary_ms - onset_ms + hold_ms <= int(event["window_ms"]):
            break
        event_index += 1
    while current_task_ms < boundary_ms:
        step([])
        current_task_ms += window_ms

    step([
        {"mouse": {"move": shutter_button}},
        {"mouse": {"buttons": {"left_down": True}}},
    ])
    step([])
    step([
        {"mouse": {"move": shutter_button}},
        {"mouse": {"buttons": {"left_up": True}}},
    ])
    if not done:
        step([{"mouse": {"left_click": submit_button}}])
    return observation, done, info, steps


def _direct_wonky_registration_env_step_solve(
    env,
    entry: dict[str, Any],
    groups: list[dict[str, Any]],
    initial_observation: dict[str, Any],
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Replay physical plate controls and anchor the flush-bottom press button."""
    from PIL import Image

    actions = [copy.deepcopy(action) for group in groups for action in group["actions"]]
    click_actions = [
        action for action in actions
        if isinstance((action.get("mouse") or {}).get("left_click"), list)
    ]
    if not click_actions:
        raise RuntimeError("wonky registration trace exposed no visible press control")
    submit_action = max(
        click_actions,
        key=lambda action: (action.get("mouse") or {})["left_click"][1],
    )
    initial_screen = Path(str((initial_observation.get("screen") or {}).get("path") or ""))
    with Image.open(initial_screen) as image:
        height = image.height
    submit_action["mouse"]["left_click"][1] = height - 20
    observation, _reward, done, info = env.step(
        actions,
        wait_between_actions=.03,
        settle_after_actions=False,
    )
    return observation, bool(done), dict(info), 1


def _direct_reload_interruption_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Replay the memory drum and physically hold each frozen-world spark."""
    import cv2
    import numpy as np

    if str(entry["interaction"]) != "full" or str(entry["time_mode"]) != "paused":
        raise RuntimeError("reload direct driver expects its sampled Full paused controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_reload_interruption_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "reload_interruption.py",
    )
    public, truth = generator.generate(task, str(trace["ground_truth_seed"]))

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def step(actions: list[dict[str, Any]]) -> None:
        nonlocal observation, done, info, steps
        observation, _reward, done, info = env.step(
            actions,
            wait_between_actions=0.0,
            settle_after_actions=False,
        )
        steps += 1
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        if screen_path.is_file():
            shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")

    window_ms = int(entry["observation_window_ms"])
    preview_ms = 700 + len(truth["sequence"]) * int(public["preview_step_ms"])
    for _ in range(1, math.ceil(preview_ms / window_ms)):
        step([])

    # The immutable oracle layout is a 1920x1080 task viewport offset by the
    # VNC framebuffer border. Registration maps these visible coordinates to
    # the current screenshot, so no DOM or page-state access is involved.
    lever_center = list(transform(976, 568))
    direction_delta = {
        "up": [0, -58],
        "right": [58, 0],
        "down": [0, 58],
        "left": [-58, 0],
    }
    interruptions = {
        int(spec["after_step"]): spec
        for spec in truth["interruptions"]
    }
    for sequence_index, direction in enumerate(truth["sequence"], start=1):
        delta = direction_delta[str(direction)]
        step([{
            "mouse": {
                "left_click_drag": [
                    lever_center,
                    [lever_center[0] + delta[0], lever_center[1] + delta[1]],
                ]
            }
        }])
        if done:
            return observation, done, info, steps
        spec = interruptions.get(sequence_index)
        if spec is None:
            continue

        def paused_image(label: str) -> Any:
            """Capture the current frozen framebuffer without advancing time."""
            captured = env.capture_screenshot_image()
            if captured is None:
                raise RuntimeError("reload paused framebuffer capture failed")
            captured = captured.convert("RGB")
            captured.save(evidence_dir / f"paused-{steps:03d}-{label}.png")
            return cv2.cvtColor(np.asarray(captured), cv2.COLOR_RGB2BGR)

        def visible_spark(image: Any | None = None) -> list[int] | None:
            """Locate the currently rendered spark, or None after it clears."""
            if image is None:
                screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
                image = cv2.imread(str(screen_path))
                if image is None:
                    raise RuntimeError("reload observation screenshot is unavailable")
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
            lime = cv2.inRange(hsv, (25, 70, 100), (55, 255, 255))
            stage_left, stage_top = transform(626, 373)
            stage_right, stage_bottom = transform(1326, 763)
            clipped = cv2.UMat(lime.shape[0], lime.shape[1], cv2.CV_8UC1).get()
            clipped[max(0, stage_top):min(lime.shape[0], stage_bottom), max(0, stage_left):min(lime.shape[1], stage_right)] = \
                lime[max(0, stage_top):min(lime.shape[0], stage_bottom), max(0, stage_left):min(lime.shape[1], stage_right)]
            candidates: list[tuple[float, int, int, int, int]] = []
            for contour in cv2.findContours(clipped, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
                x, y, width, height = cv2.boundingRect(contour)
                area = float(cv2.contourArea(contour))
                if 30 <= width <= 56 and 30 <= height <= 56 and area >= 500:
                    candidates.append((area, x, y, width, height))
            if not candidates:
                return None
            _area, x, y, width, height = max(candidates)
            return [x + width // 2, y + height // 2]

        def visible_hold_started(before: Any, after: Any, point: list[int]) -> bool:
            """Detect the spark's visible held ring from frozen screenshots."""
            radius = 55
            left, right = max(0, point[0] - radius), min(after.shape[1], point[0] + radius + 1)
            top, bottom = max(0, point[1] - radius), min(after.shape[0], point[1] + radius + 1)
            before_hsv = cv2.cvtColor(before[top:bottom, left:right], cv2.COLOR_BGR2HSV)
            after_hsv = cv2.cvtColor(after[top:bottom, left:right], cv2.COLOR_BGR2HSV)
            before_lime = cv2.inRange(before_hsv, (25, 70, 70), (55, 255, 255))
            after_lime = cv2.inRange(after_hsv, (25, 70, 70), (55, 255, 255))
            return int(cv2.countNonZero(after_lime)) >= int(cv2.countNonZero(before_lime)) + 80

        # Input is still delivered only through env.step. A privileged frozen
        # framebuffer check distinguishes a missed pointer-down from a started
        # hold without advancing the task world or fabricating browser events.
        before = paused_image(f"overload-{sequence_index}-before")
        spark = visible_spark(before)
        if spark is None:
            raise RuntimeError("reload interruption appeared without a visible spark")
        stage_left, stage_top = transform(626, 373)
        local_x = spark[0] - stage_left
        local_y = spark[1] - stage_top
        visible_angle = math.atan2(
            (local_y - float(spec["center"][1])) / float(spec["radius_y"]),
            (local_x - float(spec["center"][0])) / float(spec["radius_x"]),
        )
        candidate_angles = [visible_angle]
        for offset_index in range(1, 17):
            offset = math.pi * offset_index / 16
            candidate_angles.extend((visible_angle + offset, visible_angle - offset))
        candidates = [spark]
        candidates.extend([
            round(stage_left + float(spec["center"][0]) + math.cos(candidate) * float(spec["radius_x"])),
            round(stage_top + float(spec["center"][1]) + math.sin(candidate) * float(spec["radius_y"])),
        ] for candidate in candidate_angles[1:])

        hold_started = False
        for candidate_index, candidate in enumerate(candidates):
            done, info = _step_without_observation(env, [
                {"mouse": {"move": candidate}},
                {"mouse": {"buttons": {"left_down": True}}},
            ])
            steps += 1
            if done:
                return observation, done, info, steps
            after_down = paused_image(
                f"overload-{sequence_index}-candidate-{candidate_index:02d}-down"
            )
            if visible_hold_started(before, after_down, candidate):
                spark = candidate
                hold_started = True
                break
            done, info = _step_without_observation(
                env,
                [{"mouse": {"buttons": {"left_up": True}}}],
            )
            steps += 1
            if done:
                return observation, done, info, steps
        if not hold_started:
            raise RuntimeError("reload native pointer-down never acquired the frozen spark")

        hold_seconds = (int(spec["hold_ms"]) + 120) / 1000.0
        done, info = _step_without_observation(env, [
            {"action": "wait", "time": hold_seconds / 2},
            {"mouse": {"move": [spark[0] + 1, spark[1]]}},
            {"action": "wait", "time": hold_seconds / 2},
            {"mouse": {"move": spark}},
            {"mouse": {"buttons": {"left_up": True}}},
        ])
        steps += 1
        if done:
            return observation, done, info, steps
        after_release = paused_image(f"overload-{sequence_index}-released")
        if visible_spark(after_release) is not None:
            raise RuntimeError("reload acquired hold did not clear the frozen spark")
    return observation, done, info, steps


def _direct_semantic_drag_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Sample both visible probe channels, then route every specimen."""
    if str(entry["interaction"]) != "full" or str(entry["time_mode"]) != "paused":
        raise RuntimeError("semantic drag direct driver expects its sampled Full paused controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_semantic_drag_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "semantic_drag_drop_absurdity.py",
    )
    public, truth = generator.generate(task, str(trace["ground_truth_seed"]))

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def step(actions: list[dict[str, Any]]) -> None:
        nonlocal observation, done, info, steps
        observation, _reward, done, info = env.step(
            actions,
            wait_between_actions=0.0,
            settle_after_actions=False,
        )
        steps += 1
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        if screen_path.is_file():
            shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")

    object_points = {
        str(item["id"]): list(transform(626 + float(item["x"]) + 48, 373 + float(item["y"]) + 41))
        for item in public["objects"]
    }
    receiver_points = {
        str(item["id"]): list(transform(626 + float(item["x"]) + 48, 373 + float(item["y"]) + 41))
        for item in public["receivers"]
    }
    probe_points = {
        "thermal": list(transform(75, 1058)),
        "polarity": list(transform(147, 1058)),
    }
    hold_seconds = (int(public["probe_hold_ms"]) + 120) / 1000
    for item in public["objects"]:
        object_id = str(item["id"])
        target = object_points[object_id]
        for channel in ("thermal", "polarity"):
            step([
                {"mouse": {"move": probe_points[channel]}},
                {"mouse": {"buttons": {"left_down": True}}},
                {"mouse": {"move": target}},
                {"action": "wait", "time": hold_seconds},
                {"mouse": {"buttons": {"left_up": True}}},
            ])
            if done:
                return observation, done, info, steps

    for object_id, receiver_id in truth["expected_assignments"].items():
        step([{
            "mouse": {
                "left_click_drag": [
                    object_points[str(object_id)],
                    receiver_points[str(receiver_id)],
                ]
            }
        }])
        if done:
            return observation, done, info, steps
    step([{"mouse": {"left_click": list(transform(1833, 1058))}}])
    return observation, done, info, steps


def _direct_slime_commute_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Plan on the exact paused observation boundaries and cross by keyboard."""
    if str(entry["interaction"]) != "full" or str(entry["time_mode"]) != "paused":
        raise RuntimeError("slime direct driver expects its sampled Full paused controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_slime_commute_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "slime_commute.py",
    )
    solver = _load_module(
        "env_step_slime_commute_planner",
        BENCHMARK / "tools" / "incubator_solvers" / "slime_commute.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))
    board = truth["board"]
    ticks_per_window = int(entry["observation_window_ms"]) // int(board["tick_ms"])
    if ticks_per_window < 1 or ticks_per_window * int(board["tick_ms"]) != int(entry["observation_window_ms"]):
        raise RuntimeError("slime observation window is not an integral number of world ticks")

    start = (float(board["start_x"]), 10, 0, 0)
    queue = deque([start])
    parent: dict[tuple[Any, ...], tuple[tuple[Any, ...], tuple[int, str] | None] | None] = {start: None}
    goal_state: tuple[Any, ...] | None = None
    while queue:
        x, y, tick, cooldown = queue.popleft()
        if tick >= min(int(board["max_ticks"]), 900):
            continue
        choices = [None] + (list(solver.KEYS) if cooldown == 0 else [])
        for key in choices:
            next_x, next_y, next_cooldown = x, y, cooldown
            action = None
            if key is not None:
                dx, dy = solver.KEYS[key]
                next_x, next_y = x + dx, y + dy
                if not (0 <= next_x <= int(board["columns"]) - 1 and 0 <= next_y <= 10):
                    continue
                if not solver._safe(board, next_x, next_y, tick):
                    continue
                next_cooldown = int(board["hop_cooldown_ticks"])
                action = (tick, key)
                if next_y == 0 and abs(next_x - float(board["goal_x"])) < .42:
                    goal_state = (round(next_x, 4), next_y, tick, next_cooldown, "goal")
                    parent[goal_state] = ((x, y, tick, cooldown), action)
                    queue.clear()
                    break
            next_state: tuple[Any, ...] = (next_x, next_y, tick, next_cooldown)
            for _ in range(ticks_per_window):
                advanced = solver._world_step(board, *next_state)
                if advanced is None:
                    next_state = ()
                    break
                next_state = advanced
            if next_state and next_state not in parent:
                parent[next_state] = ((x, y, tick, cooldown), action)
                queue.append(next_state)
        if goal_state is not None:
            break
    if goal_state is None:
        raise RuntimeError("immutable slime world has no route on paused observation boundaries")
    plan: list[tuple[int, str]] = []
    cursor = goal_state
    while parent[cursor] is not None:
        previous, action = parent[cursor]
        if action is not None:
            plan.append(action)
        cursor = previous
    action_at_tick = dict(reversed(plan))

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)
    tick = 0
    while not done and tick <= max(action_at_tick):
        actions: list[dict[str, Any]] = []
        if tick == 0:
            actions.append({"mouse": {"left_click": list(transform(976, 563))}})
        if tick in action_at_tick:
            actions.append({"keyboard": {"keys": [action_at_tick[tick]]}})
        observation, _reward, done, info = env.step(
            actions,
            wait_between_actions=0.0,
            settle_after_actions=False,
        )
        steps += 1
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        if screen_path.is_file():
            shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")
        tick += ticks_per_window
    return observation, done, info, steps


def _direct_wrong_number_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    groups: list[dict[str, Any]],
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Track the authorized carrier at each paused observation boundary."""
    if str(entry["interaction"]) != "full" or str(entry["time_mode"]) != "paused":
        raise RuntimeError("wrong-number direct driver expects its sampled Full paused controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_wrong_number_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "wrong_number.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))

    clicks = [
        [int(point[0]), int(point[1])]
        for group in groups
        for action in group["actions"]
        if isinstance((point := (action.get("mouse") or {}).get("left_click")), list)
    ]
    if len(clicks) < 4:
        raise RuntimeError("wrong-number trace did not expose its line, sliders, and test control")
    line_point = list(min(clicks, key=lambda point: point[1]))
    test_point = list(max(clicks, key=lambda point: point[0]))
    tuning = [point for point in clicks if point != line_point and point != test_point]
    phase_point = list(min(tuning, key=lambda point: point[0]))
    skew_point = list(max(tuning, key=lambda point: point[0]))

    def set_range(point: list[int], value: int, minimum: int) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = [
            {"mouse": {"left_click": point}},
            {"keyboard": {"keys": ["home"]}},
        ]
        actions.extend({"keyboard": {"keys": ["right"]}} for _ in range(value - minimum))
        return actions

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def step(actions: list[dict[str, Any]]) -> None:
        nonlocal observation, done, info, steps
        observation, _reward, done, info = env.step(
            actions,
            wait_between_actions=0.0,
            settle_after_actions=False,
        )
        steps += 1
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        if screen_path.is_file():
            shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")

    qualification = truth["qualification"]
    target = next(line for line in truth["lines"] if line["id"] == truth["target_line_id"])
    phase_steps = int(qualification["phase_steps"])
    phase = int(truth["solution_phase_step"])
    skew = int(truth["solution_skew_step"])
    setup_actions = [{"mouse": {"left_click": line_point}}]
    setup_actions.extend(set_range(phase_point, phase, 0))
    setup_actions.extend(set_range(skew_point, skew, int(qualification["skew_min"])))
    setup_actions.append({"mouse": {"left_click": test_point}})
    step(setup_actions)

    window_ms = int(entry["observation_window_ms"])
    trial_ms = int(qualification["trial_ms"])
    elapsed_ms = window_ms
    while not done and elapsed_ms < trial_ms:
        midpoint_ms = min(trial_ms, elapsed_ms + window_ms / 2)
        target_phase = (
            -float(target["phase_offset_steps"])
            - float(target["drift_milli_steps_per_second"]) * midpoint_ms / 1_000_000
        ) % phase_steps
        phase = round(target_phase) % phase_steps
        step(set_range(phase_point, phase, 0))
        elapsed_ms += window_ms
    return observation, done, info, steps


def _direct_robot_art_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Draw the privileged class prototype through continuous UI strokes."""
    if str(entry["interaction"]) != "full":
        raise RuntimeError("robot-art direct driver expects its sampled Full controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_robot_art_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "robot_art_critic.py",
    )
    grader = _load_module(
        "env_step_robot_art_prototypes",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "robot_art_critic.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))
    target = truth["target"]
    strokes = grader._transform_template(
        str(target["class_name"]),
        float(target["pose"]["angle_deg"]),
        int(target["style"]["x_scale_milli"]),
    )

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def canvas_point(point: tuple[float, float]) -> list[int]:
        local_x = max(0.0, min(float(truth["canvas"]["width"]), point[0] * float(truth["canvas"]["width"])))
        local_y = max(0.0, min(float(truth["canvas"]["height"]), point[1] * float(truth["canvas"]["height"])))
        return list(transform(
            339 + local_x / float(truth["canvas"]["width"]) * 908,
            274 + local_y / float(truth["canvas"]["height"]) * 517,
        ))

    for stroke in strokes:
        dense: list[tuple[float, float]] = [stroke[0]]
        for first, second in zip(stroke, stroke[1:]):
            distance_px = math.hypot(
                (second[0] - first[0]) * float(truth["canvas"]["width"]),
                (second[1] - first[1]) * float(truth["canvas"]["height"]),
            )
            segment_steps = max(1, math.ceil(distance_px / 15))
            dense.extend((
                first[0] + (second[0] - first[0]) * index / segment_steps,
                first[1] + (second[1] - first[1]) * index / segment_steps,
            ) for index in range(1, segment_steps + 1))
        while len(dense) < int(truth["requirements"]["minimum_points_per_stroke"]):
            expanded: list[tuple[float, float]] = [dense[0]]
            for first, second in zip(dense, dense[1:]):
                expanded.append(((first[0] + second[0]) / 2, (first[1] + second[1]) / 2))
                expanded.append(second)
            dense = expanded
        actions: list[dict[str, Any]] = [
            {"mouse": {"move": canvas_point(dense[0])}},
            {"mouse": {"buttons": {"left_down": True}}},
        ]
        actions.extend({"mouse": {"move": canvas_point(point)}} for point in dense[1:])
        # The dense physical moves themselves provide the minimum stroke
        # duration. An explicit wait can exceed the input clock's adjacency
        # window on QEMU and incorrectly split pointer-up from this gesture.
        actions.append({"mouse": {"buttons": {"left_up": True}}})
        done, info = _step_without_observation(env, actions)
        steps += 1
        if done:
            return observation, done, info, steps

    observation, _reward, done, info = env.step(
        [{"mouse": {"left_click": list(transform(1336, 863))}}],
        wait_between_actions=0.0,
        settle_after_actions=False,
    )
    steps += 1
    screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
    if screen_path.is_file():
        shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")
    return observation, bool(done), dict(info), steps


def _direct_specular_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Track each receiver at the immutable eight-tick paused boundaries."""
    import cv2
    import numpy as np

    if str(entry["interaction"]) != "simplified" or str(entry["time_mode"]) != "paused":
        raise RuntimeError("specular direct driver expects its sampled Simplified paused controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_specular_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "specular_lighthouse_relay.py",
    )
    grader = _load_module(
        "env_step_specular_replay",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "specular_lighthouse_relay.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)
    ticks_per_window = int(entry["observation_window_ms"]) // 80
    if ticks_per_window != 8:
        raise RuntimeError("immutable specular window is not eight optical ticks")

    row_y = (176, 218, 260, 302)
    minus_x, plus_x = 1707, 1850

    def adjustment_actions(index: int, before: float, after: float, step_degrees: float) -> list[dict[str, Any]]:
        plus_steps = round(((after - before) % 180) / step_degrees)
        minus_steps = round(((before - after) % 180) / step_degrees)
        x = plus_x if plus_steps <= minus_steps else minus_x
        point = list(transform(x, row_y[index]))
        count = min(plus_steps, minus_steps)
        actions = [
            {"mouse": {"triple_click": point}}
            for _ in range(count // 3)
        ]
        if count % 3 == 2:
            actions.append({"mouse": {"double_click": point}})
        elif count % 3 == 1:
            actions.append({"mouse": {"left_click": point}})
        return actions

    def visible_optical_state(
        previous_round: int,
        previous_tick: int,
    ) -> tuple[int, int, int]:
        """Read the visible receiver round, timer tick, and charge meter."""
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        image = cv2.imread(str(screen_path))
        if image is None:
            raise RuntimeError("specular visible screenshot is unavailable")
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        # The canvas publishes the exact visible timer as "SHUTTER n / N ·
        # TRACK t". Read that UI instead of inferring a periodic sine phase;
        # multiple ticks can occupy nearly the same receiver pixels, which made
        # the geometric inverse select the wrong cycle on later rounds.
        label_crop = image[
            round(image.shape[0] * .125):round(image.shape[0] * .215),
            round(image.shape[1] * .01):round(image.shape[1] * .30),
        ]
        label_crop = cv2.resize(label_crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        encoded_ok, encoded_label = cv2.imencode(".png", label_crop)
        if not encoded_ok:
            raise RuntimeError("specular visible track label could not be encoded")
        label_ocr = subprocess.run(
            ["tesseract", "stdin", "stdout", "--psm", "6"],
            input=encoded_label.tobytes(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        label_text = " ".join(label_ocr.stdout.decode("utf-8", errors="replace").split())
        label_match = re.search(
            r"SHUTTER\s*(\d+)\s*/.*?TRACK\s*([0-9SO]+)",
            label_text,
            re.IGNORECASE,
        )
        numeric_text = ""
        numeric_match = None
        if label_match is None:
            label_gray = cv2.cvtColor(label_crop, cv2.COLOR_BGR2GRAY)
            _threshold, numeric_label = cv2.threshold(
                label_gray,
                round(255 * .45),
                255,
                cv2.THRESH_BINARY,
            )
            numeric_label = cv2.bitwise_not(numeric_label)
            numeric_ok, numeric_encoded = cv2.imencode(".png", numeric_label)
            if numeric_ok:
                numeric_ocr = subprocess.run(
                    [
                        "tesseract", "stdin", "stdout", "--psm", "7",
                        "-c", "tessedit_char_whitelist=0123456789/",
                    ],
                    input=numeric_encoded.tobytes(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                numeric_text = "".join(
                    numeric_ocr.stdout.decode("utf-8", errors="replace").split()
                )
                numeric_match = re.search(
                    rf"(\d+)/{len(truth['rounds'])}(\d+)",
                    numeric_text,
                )
        if label_ocr.returncode or (label_match is None and numeric_match is None):
            raise RuntimeError(
                "specular visible round/tick label was unreadable: "
                f"tesseract={label_ocr.returncode}, text={label_text!r}, "
                f"numeric={numeric_text!r}"
            )
        match = label_match if label_match is not None else numeric_match
        assert match is not None
        visible_round = int(match.group(1)) - 1
        # The canvas font makes a lone 5 look like S (and occasionally 0
        # like O) to Tesseract. This substitution is confined to the numeric
        # token after the literal visible TRACK label.
        visible_tick = int(match.group(2).upper().translate(str.maketrans({"S": "5", "O": "0"})))
        if visible_round < previous_round or visible_round > min(len(truth["rounds"]) - 1, previous_round + 1):
            raise RuntimeError("specular visible round moved outside the next legal receiver")
        if visible_round == previous_round and visible_tick < previous_tick:
            raise RuntimeError("specular visible timer moved backward")
        meter_left, meter_y = transform(1624.0, 391.0)
        meter_right, _ = transform(1895.0, 391.0)
        meter_x0 = max(0, round(min(meter_left, meter_right)))
        meter_x1 = min(image.shape[1], round(max(meter_left, meter_right)) + 1)
        meter_y0 = max(0, round(meter_y - 5))
        meter_y1 = min(image.shape[0], round(meter_y + 6))
        meter_hsv = hsv[meter_y0:meter_y1, meter_x0:meter_x1]
        meter_lime = cv2.inRange(
            meter_hsv,
            np.array([25, 80, 100]),
            np.array([55, 255, 255]),
        )
        columns = np.flatnonzero(np.count_nonzero(meter_lime, axis=0) >= max(1, meter_lime.shape[0] // 2))
        fill_width = 0
        if len(columns):
            runs = np.split(columns, np.where(np.diff(columns) > 1)[0] + 1)
            fill_width = max(len(run) for run in runs)
        required_charge = int(truth["rounds"][visible_round]["required_charge_ticks"])
        meter_width = max(1, meter_x1 - meter_x0)
        visible_charge = min(required_charge, round(fill_width / meter_width * required_charge))
        return visible_round, visible_tick, visible_charge

    def visible_terminal_pass() -> bool:
        """Recognize the final verdict from the delivered screenshot."""
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        image = cv2.imread(str(screen_path))
        if image is None:
            return False
        height, width = image.shape[:2]
        verdict_crop = image[
            round(height * .37):round(height * .61),
            round(width * .23):round(width * .77),
        ]
        encoded_ok, encoded_verdict = cv2.imencode(".png", verdict_crop)
        if not encoded_ok:
            return False
        verdict_ocr = subprocess.run(
            ["tesseract", "stdin", "stdout", "--psm", "6"],
            input=encoded_verdict.tobytes(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        verdict_text = " ".join(
            verdict_ocr.stdout.decode("utf-8", errors="replace").upper().split()
        )
        return (
            verdict_ocr.returncode == 0
            and "LIGHTHOUSE RELAY" in verdict_text
            and "AUTHENTICATED" in verdict_text
        )

    visible_round = 0
    visible_tick = 0
    for round_index, (round_data, solution) in enumerate(zip(truth["rounds"], truth["solutions"], strict=True)):
        if visible_round != round_index:
            raise RuntimeError(
                f"specular visible round {visible_round} did not advance to expected round {round_index}"
            )
        angles = [float(item["angle_deg"]) for item in round_data["mirrors"]]
        step_degrees = float(round_data["angle_step_deg"])
        actions: list[dict[str, Any]] = []
        charge = 0
        for mirror_index, target in enumerate(solution["angles"][:-1]):
            target = float(target)
            actions.extend(adjustment_actions(mirror_index, angles[mirror_index], target, step_degrees))
            angles[mirror_index] = target % 180

        # Set the static part of the optical path while the authored shutter
        # is closed. The following observation window cannot advance the
        # receiver timer, so every native button click has visibly settled
        # before live charge begins.
        if actions:
            observation, _reward, done, info = env.step(
                actions,
                wait_between_actions=0.0,
                settle_after_actions=False,
            )
            actions = []
            steps += 1
            screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
            if screen_path.is_file():
                shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")
            if done:
                return observation, done, info, steps
            visible_round, visible_tick, charge = visible_optical_state(round_index, visible_tick)

        tick = visible_tick
        for _window in range(40):
            last_index = len(angles) - 1
            reachable = [
                (angles[last_index] + offset * step_degrees) % 180
                for offset in range(round(180 / step_degrees))
            ]
            candidates: list[tuple[int, int, float, list[bool]]] = []
            for candidate in reachable:
                candidate_angles = [*angles[:-1], candidate]
                trial_charge = charge
                outcomes: list[bool] = []
                for future_tick in range(tick + 1, tick + ticks_per_window + 1):
                    hit = bool(grader._trace_hit(round_data, candidate_angles, future_tick))
                    outcomes.append(hit)
                    trial_charge = trial_charge + 1 if hit else max(0, trial_charge - int(round_data["miss_decay_ticks"]))
                candidates.append((trial_charge, sum(outcomes), candidate, outcomes))
            _next_charge, _hits, target, _outcomes = max(candidates, key=lambda item: (item[0], item[1], -abs(item[2] - angles[last_index])))
            actions.extend(adjustment_actions(last_index, angles[last_index], target, step_degrees))
            angles[last_index] = target
            actions.append({"mouse": {"left_click": list(transform(1760, 356))}})
            observation, _reward, done, info = env.step(
                actions,
                wait_between_actions=0.0,
                settle_after_actions=False,
            )
            actions = []
            steps += 1
            screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
            if screen_path.is_file():
                shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")
            if done:
                return observation, done, info, steps
            if round_index == len(truth["rounds"]) - 1 and visible_terminal_pass():
                return observation, done, info, steps
            observed_round, observed_tick, observed_charge = visible_optical_state(round_index, tick)
            if observed_round > round_index:
                visible_round, visible_tick = observed_round, observed_tick
                break
            if observed_tick < tick:
                raise RuntimeError("specular visible timer moved backward")
            tick = visible_tick = observed_tick
            charge = observed_charge

            # Freeze the mechanic's own receiver/charge timer before changing
            # the next angle. This is a visible game control exercised through
            # env.step, not generic action settlement or a runner-side pause.
            observation, _reward, done, info = env.step(
                [{"mouse": {"left_click": list(transform(1760, 356))}}],
                wait_between_actions=0.0,
                settle_after_actions=False,
            )
            steps += 1
            screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
            if screen_path.is_file():
                shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")
            if done:
                return observation, done, info, steps
            if round_index == len(truth["rounds"]) - 1 and visible_terminal_pass():
                return observation, done, info, steps
            observed_round, observed_tick, observed_charge = visible_optical_state(round_index, tick)
            if observed_round > round_index:
                visible_round, visible_tick = observed_round, observed_tick
                break
            if observed_tick < tick:
                raise RuntimeError("specular visible timer moved backward while closing shutter")
            tick = visible_tick = observed_tick
            charge = observed_charge
        else:
            raise RuntimeError(f"specular receiver {round_index + 1} did not charge within 40 visible windows")
    return observation, done, info, steps


def _direct_time_wheel_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Set all three rings with visible one-detent drags and the brake."""
    if str(entry["interaction"]) != "full" or str(entry["time_mode"]) != "paused":
        raise RuntimeError("time-wheel direct driver expects its sampled Full paused controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_time_wheel_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "thirty_year_time_wheel.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # Coordinates are measured from the immutable 1920x1080 task screenshot;
    # registration maps them to the current VNC framebuffer. A fourteen-degree
    # chord crosses exactly one twelve-degree detent even on the small year
    # ring. The visible brake is clicked after every release. If the release
    # started inertia, that stops it before paused task time can advance; if it
    # did not, the same click is the documented idle-brake operation.
    center = (784.0, 356.0)
    radii = {"day": 183.0, "month": 129.0, "year": 79.0}
    brake = list(transform(1367, 241))
    start_angle = -math.pi / 2
    gesture_angle = math.radians(14)

    for route in truth["direct_recovery_route"]:
        component = str(route["component"])
        signed_steps = int(route["steps"])
        direction = 1 if signed_steps > 0 else -1
        radius = radii[component]
        actions: list[dict[str, Any]] = []
        for _ in range(abs(signed_steps)):
            end_angle = start_angle + direction * gesture_angle
            start = list(transform(
                center[0] + radius * math.cos(start_angle),
                center[1] + radius * math.sin(start_angle),
            ))
            end = list(transform(
                center[0] + radius * math.cos(end_angle),
                center[1] + radius * math.sin(end_angle),
            ))
            actions.extend((
                {"mouse": {"move": start}},
                {"mouse": {"buttons": {"left_down": True}}},
                {"mouse": {"move": end}},
                {"mouse": {"buttons": {"left_up": True}}},
                {"mouse": {"left_click": brake}},
            ))
        observation, _reward, done, info = env.step(
            actions,
            wait_between_actions=0.0,
            settle_after_actions=False,
        )
        steps += 1
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        if screen_path.is_file():
            shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")
        if done:
            return observation, done, info, steps

    observation, _reward, done, info = env.step(
        [{"mouse": {"left_click": list(transform(1434, 652))}}],
        wait_between_actions=0.0,
        settle_after_actions=False,
    )
    steps += 1
    screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
    if screen_path.is_file():
        shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")
    return observation, bool(done), dict(info), steps


def _direct_reverse_identity_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Operate every real limb tab through conservative fixed-step holds."""
    import cv2
    import numpy as np

    if str(entry["interaction"]) != "full" or str(entry["time_mode"]) != "paused":
        raise RuntimeError("reverse-identity direct driver expects its sampled Full paused controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_reverse_identity_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "reverse_identity_gate.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def step(actions: list[dict[str, Any]], *, capture: bool) -> None:
        nonlocal observation, done, info, steps
        if capture:
            observation, _reward, done, info = env.step(
                actions,
                wait_between_actions=0.0,
                settle_after_actions=False,
            )
            screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
            if screen_path.is_file():
                shutil.copy2(screen_path, evidence_dir / f"step-{steps + 1:03d}.png")
        else:
            done, info = _step_without_observation(env, actions)
        steps += 1

    station_colors = {
        int(station["id"]): np.array([
            int(str(station["color"])[5:7], 16),
            int(str(station["color"])[3:5], 16),
            int(str(station["color"])[1:3], 16),
        ], dtype=np.int16)
        for station in truth["stations"]
    }

    def visible_page() -> int | None:
        """Classify the visible master/limb page from its screenshot colors."""
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        image = cv2.imread(str(screen_path))
        if image is None:
            raise RuntimeError("four-tab visible screenshot is unavailable")
        pixels = image.astype(np.int16)
        counts = {
            station_id: int(np.count_nonzero(np.max(np.abs(pixels - color), axis=2) < 40))
            for station_id, color in station_colors.items()
        }
        station_id, count = max(counts.items(), key=lambda item: item[1])
        # A limb repeats its single accent through the large heading, orbit,
        # console, and footer. The master only uses each accent on one compact
        # deployment card.
        return station_id if count >= 1_200 else None

    def visible_phase_angles(expected_stage: int) -> tuple[float, float]:
        """Read the active relay and both orbit angles from its screenshot."""
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        image = cv2.imread(str(screen_path))
        if image is None:
            raise RuntimeError("four-tab visible screenshot is unavailable")
        station_id = int(truth["stages"][expected_stage]["station"])
        station_color = station_colors[station_id]
        status_left, status_top = transform(1_800, 40)
        status_right, status_bottom = transform(1_890, 100)
        status_pixels = image[
            min(status_top, status_bottom):max(status_top, status_bottom),
            min(status_left, status_right):max(status_left, status_right),
        ].astype(np.int16)
        active_color_count = int(np.count_nonzero(
            np.max(np.abs(status_pixels - station_color), axis=2) < 55
        )) if status_pixels.size else 0
        if active_color_count < 20:
            raise RuntimeError(
                f"four-tab station {station_id} was visible but not the active relay for stage {expected_stage + 1}"
            )

        height, width = image.shape[:2]
        center_x, center_y = transform(820, 569)
        scale_x = abs(float(transform(1_020, 569)[0]) - float(center_x)) / 200.0
        scale_y = abs(float(transform(820, 769)[1]) - float(center_y)) / 200.0
        yy, xx = np.ogrid[:height, :width]
        normalized_radius_sq = (
            ((xx - float(center_x)) / max(scale_x, 1e-6)) ** 2
            + ((yy - float(center_y)) / max(scale_y, 1e-6)) ** 2
        )

        pixels = image.astype(np.int16)
        pulse_mask = (
            (np.max(np.abs(pixels - station_color), axis=2) < 55)
            & (normalized_radius_sq > 185**2)
            & (normalized_radius_sq < 235**2)
        )
        neutral_spread = np.max(pixels, axis=2) - np.min(pixels, axis=2)
        receiver_mask = (
            (neutral_spread < 30)
            & (np.min(pixels, axis=2) > 145)
            & (normalized_radius_sq > 145**2)
            & (normalized_radius_sq < 190**2)
        )

        def largest_component_center(mask: np.ndarray, label: str) -> tuple[float, float]:
            count, _labels, stats, centroids = cv2.connectedComponentsWithStats(
                mask.astype(np.uint8),
                8,
            )
            candidates = [
                (int(stats[index, cv2.CC_STAT_AREA]), centroids[index])
                for index in range(1, count)
                if int(stats[index, cv2.CC_STAT_AREA]) >= 20
            ]
            if not candidates:
                raise RuntimeError(f"four-tab visible {label} marker was not found")
            _area, marker = max(candidates, key=lambda item: item[0])
            return float(marker[0]), float(marker[1])

        def marker_angle(marker: tuple[float, float]) -> float:
            dx = (marker[0] - float(center_x)) / max(scale_x, 1e-6)
            dy = (marker[1] - float(center_y)) / max(scale_y, 1e-6)
            return math.degrees(math.atan2(dx, -dy)) % 360.0

        pulse_marker = largest_component_center(pulse_mask, "pulse")
        receiver_marker = largest_component_center(receiver_mask, "receiver")
        return marker_angle(pulse_marker), marker_angle(receiver_marker)

    def focus_page(target: int | None) -> None:
        if visible_page() == target:
            return
        # The VM browser can insert window.open pages on either side of their
        # opener, so a station's absolute tab number is not portable. Cycle
        # only through this fresh task's finite authored tab set and classify
        # each resulting visible page.
        for _ in range(len(truth["stations"]) + 1):
            step([{"keyboard": {"keys": ["ctrl", "tab"]}}], capture=True)
            if done or visible_page() == target:
                return
        raise RuntimeError(f"four-tab task-tab cycle could not expose page {target}")

    for station_id in range(len(truth["stations"])):
        focus_page(None)
        # Opening the real child tab is only the first half of deployment.
        # Its visible runtime must load and register with the shared ledger
        # before the master's sequential interlock enables the next button.
        step([{
            "mouse": {"left_click": list(transform(1748, 269 + station_id * 76))}
        }], capture=True)

    receiver_speed = int(truth["physics"]["receiver_control_deg_per_tick"])
    tick_ms = int(truth["physics"]["tick_ms"])
    ticks_per_window = int(entry["observation_window_ms"]) // tick_ms
    if ticks_per_window < 1:
        raise RuntimeError("four-tab observation window is shorter than one relay tick")
    contact = list(transform(1761, 333))
    previous_station: int | None = None
    previous_key: str | None = None
    for stage_index, stage in enumerate(truth["stages"]):
        station = int(stage["station"])
        key = "d" if int(stage["pulse_speed_deg_per_tick"]) > 0 else "a"
        # Each completed relay visibly focuses the next limb tab and clears
        # the shared direction/contact state. Release the physical holds in
        # that newly active tab, then start its own controls at the same frozen
        # boundary. Cycling back to the sealed tab only adds unrelated browser
        # navigation and can race the game's intentional focus transition.
        focus_page(station)
        pulse_angle, receiver_angle = visible_phase_angles(stage_index)
        direction = 1 if key == "d" else -1
        capture_delta = next((
            delta
            for delta in range(1, 361)
            if abs((
                (
                    receiver_angle
                    + direction * receiver_speed * delta
                )
                - (
                    pulse_angle
                    + int(stage["pulse_speed_deg_per_tick"]) * delta
                )
                + 180
            ) % 360 - 180) <= max(1, int(truth["physics"]["capture_tolerance_deg"]) - 4)
        ), None)
        if capture_delta is None:
            raise RuntimeError(f"four-tab relay {stage_index + 1} has no reachable phase lock")
        # The capture tick contributes the first charge unit. Include one
        # conservative extra tick so an observation-boundary paint cannot
        # leave the final relay one tick short.
        drive_ticks = capture_delta + int(truth["physics"]["hold_ticks"]) + 2
        windows_per_stage = math.ceil(drive_ticks / ticks_per_window)
        actions: list[dict[str, Any]] = []
        if previous_station is not None and previous_key is not None:
            actions.extend((
                {"mouse": {"buttons": {"left_up": True}}},
                {"keyboard": {"keys_up": [previous_key]}},
            ))
        actions.extend([
            {"keyboard": {"keys_down": [key]}},
            {"mouse": {"move": contact}},
            {"mouse": {"buttons": {"left_down": True}}},
        ])
        step(actions, capture=True)
        for _hold_window in range(1, windows_per_stage):
            # In paused mode capture_observation=False injects input but does
            # not run the authored observation window. Every relay hold window
            # must therefore use the normal env.step observation path so the
            # fixed task clock actually advances.
            step([], capture=True)
            if done:
                return observation, done, info, steps
        previous_station = station
        previous_key = key

    final_actions: list[dict[str, Any]] = []
    if previous_station is not None and previous_key is not None:
        final_actions.extend((
            {"mouse": {"buttons": {"left_up": True}}},
            {"keyboard": {"keys_up": [previous_key]}},
        ))
    focus_page(None)
    final_actions.append({"mouse": {"left_click": list(transform(1799, 1053))}})
    step(final_actions, capture=True)
    return observation, done, info, steps


def _direct_wizard_interception_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Exhaust the visible time glass, then launch a boundary-safe net."""
    if str(entry["interaction"]) != "full" or str(entry["time_mode"]) != "paused":
        raise RuntimeError("wizard direct driver expects its sampled Full paused controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_wizard_interception_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "wizard_critter_capture.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def step(actions: list[dict[str, Any]]) -> None:
        nonlocal observation, done, info, steps
        observation, _reward, done, info = env.step(
            actions,
            wait_between_actions=0.0,
            settle_after_actions=False,
        )
        steps += 1
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        if screen_path.is_file():
            shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")

    window_ms = int(entry["observation_window_ms"])
    tick_ms = int(truth["arena"]["tick_ms"])
    # reset() has already supplied one complete observation window.
    for _ in range(1, math.ceil(1080 / window_ms)):
        step([])

    lure = [int(value) for value in truth["solver_lure"]]
    canvas_point = lambda point: list(transform(382 + int(point[0]), 123 + int(point[1])))
    step([
        {"mouse": {"left_click": list(transform(1386, 273))}},
        {"mouse": {"left_click": canvas_point(lure)}},
        {"keyboard": {"keys_down": ["f"]}},
    ])
    # A second fixed window exhausts the D5 time glass. Exhaustion is the
    # game's visible automatic release, and is replayed by the grader.
    step([])

    freeze_ticks = int(truth["requirements"]["freeze_energy_ticks"])
    lure10 = (lure[0] * 10, lure[1] * 10)
    states = generator._baseline_states(
        truth["critters"],
        lure10,
        freeze_ticks=freeze_ticks,
        ticks=int(truth["requirements"]["time_limit_ticks"]),
    )
    estimated_shot_tick = (2 * window_ms) // tick_ms
    target_id = str(truth["target_id"])
    future = next(
        item for item in states[estimated_shot_tick + int(truth["arena"]["net_flight_ticks"])]
        if str(item["id"]) == target_id
    )
    center_x = round(int(future["x10"]) / 10)
    center_y = round(int(future["y10"]) / 10)
    aim: list[int] | None = None
    candidates = {
        (x, y)
        for y in range(max(0, center_y - 90), min(int(truth["arena"]["height"]), center_y + 90) + 1, 2)
        for x in range(max(0, center_x - 90), min(int(truth["arena"]["width"]), center_x + 90) + 1, 2)
    }
    candidates.add((center_x, center_y))
    for x, y in sorted(
        candidates,
        key=lambda point: ((point[0] - center_x) ** 2 + (point[1] - center_y) ** 2, point[1], point[0]),
    ):
        candidate = (x * 10, y * 10)
        if all(
            generator._first_projectile_hit(states, shot_tick, candidate)[0] == target_id
            for shot_tick in range(max(0, estimated_shot_tick - 2), estimated_shot_tick + 3)
        ):
            aim = [x, y]
            break
    if aim is None:
        raise RuntimeError(f"no boundary-safe wizard aim around tick {estimated_shot_tick}")

    step([
        {"keyboard": {"keys_up": ["f"]}},
        {"mouse": {"left_click": canvas_point(aim)}},
    ])
    if not done:
        step([])
    return observation, done, info, steps


def _direct_relation_prompt_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Catch the moving carousel and operate the full rig through env.step."""
    if str(entry["interaction"]) != "full":
        raise RuntimeError("closed-loop relation driver expects its sampled full controls")
    import cv2

    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_relation_closed_loop_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "relation_prompt_grounding.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # The stage geometry is visible in the immutable oracle screenshot. All
    # points are then registered to the current Gym screenshot; generated
    # truth decides only which visible object and destination to operate.
    def stage_point(x: float, y: float) -> list[int]:
        return list(transform(
            round(340 + float(x) / float(truth["stage"]["width"]) * 958),
            round(160 + float(y) / float(truth["stage"]["height"]) * 458),
        ))

    def step(actions: list[dict[str, Any]], *, capture: bool = False) -> None:
        nonlocal observation, done, info, steps
        if capture:
            observation, _reward, done, info = env.step(
                actions,
                wait_between_actions=0.0,
                settle_after_actions=False,
            )
        else:
            done, info = _step_without_observation(env, actions)
        steps += 1
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        if capture and screen_path.is_file():
            shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")

    stage_left, stage_top = transform(340, 160)
    stage_right, stage_bottom = transform(1297, 618)
    carousel_right = stage_point(338, 0)[0]

    def visible_object_center(shape: str) -> list[int]:
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        image = cv2.imread(str(screen_path))
        if image is None:
            raise RuntimeError("relation env.step observation has no readable screenshot")
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if shape == "disk":
            mask = cv2.inRange(hsv, (165, 90, 70), (179, 255, 255))
        elif shape == "orb":
            mask = cv2.inRange(hsv, (8, 90, 55), (40, 255, 255))
        elif shape == "star":
            mask = cv2.inRange(gray, 0, 38)
        else:
            mask = cv2.inRange(hsv, (5, 18, 35), (45, 180, 235))
        # Find connected components only inside the carousel. On the complete
        # page the black star joins the dashboard's dark borders and labels
        # into one enormous external contour, even though it is plainly
        # visible. Cropping first preserves the object's own contour.
        roi_left = int(stage_left)
        roi_top = int(stage_top)
        roi_right = int(carousel_right)
        roi_bottom = int(stage_bottom)
        roi = mask[roi_top:roi_bottom + 1, roi_left:roi_right]
        contour_mask = roi if shape == "star" else mask
        contour_offset_x = roi_left if shape == "star" else 0
        contour_offset_y = roi_top if shape == "star" else 0
        candidates: list[tuple[float, int, int, int, int]] = []
        for contour in cv2.findContours(contour_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
            x, y, width, height = cv2.boundingRect(contour)
            x += contour_offset_x
            y += contour_offset_y
            area = cv2.contourArea(contour)
            # A source is always one of the moving carousel objects. Exclude
            # the worktable, including already-placed objects and their
            # selection glows, from every color/shape detector.
            if not (stage_left <= x < carousel_right and stage_top <= y <= stage_bottom):
                continue
            if shape in {"disk", "orb"} and not (35 <= width <= 100 and 35 <= height <= 100 and area >= 500):
                continue
            if shape == "star" and not (30 <= width <= 110 and 30 <= height <= 110 and area >= 450):
                continue
            if shape == "frame" and not (
                130 <= width <= 200
                and 130 <= height <= 200
                and .82 <= width / height <= 1.18
                and area >= .62 * width * height
            ):
                continue
            candidates.append((area, x, y, width, height))
        if not candidates:
            raise RuntimeError(f"could not locate the visible carousel {shape}")
        _area, x, y, width, height = max(candidates)
        return [round(x + width / 2), round(y + height / 2)]

    def predicted_object_center(
        item: dict[str, Any],
        remaining: list[dict[str, Any]],
    ) -> list[int]:
        """Infer the visible carousel tick and account for screenshot age."""
        references = sorted(
            remaining,
            key=lambda candidate: {
                "disk": 0,
                "orb": 1,
                "frame": 2,
                "star": 3,
            }.get(str(candidate["shape"]), 4),
        )
        reference = references[0]
        observed = visible_object_center(str(reference["shape"]))
        carousel = truth["carousel"]
        tick_count = int(carousel["ticks"])

        def carousel_screen(candidate: dict[str, Any], tick: int) -> list[int]:
            angle = math.tau * (
                (int(candidate["carousel_phase"]) + tick) % tick_count
            ) / tick_count
            return stage_point(
                float(carousel["center"][0]) + float(carousel["radius_x"]) * math.cos(angle),
                float(carousel["center"][1]) + float(carousel["radius_y"]) * math.sin(angle),
            )

        visible_tick = min(
            range(tick_count),
            key=lambda tick: math.dist(observed, carousel_screen(reference, tick)),
        )
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        screenshot_age_ms = max(0.0, (time.time() - screen_path.stat().st_mtime) * 1000)
        if str(entry["time_mode"]) == "paused":
            # The screenshot is the latest frame at the paused boundary. The
            # following capture-free env.step injects its drag at that same
            # task time; host-side thinking and file-copy latency stay frozen.
            action_transport_lead_ticks = 0
        else:
            # In live mode the task continues during caller-side screenshot
            # handling as well as during action transport.
            action_transport_lead_ticks = (
                round(screenshot_age_ms / float(carousel["tick_ms"])) + 10
            )
        return carousel_screen(item, (visible_tick + action_transport_lead_ticks) % tick_count)

    ordered = [item for item in truth["objects"] if item.get("container")]
    ordered.extend(item for item in truth["objects"] if not item.get("container"))
    for item_index, item in enumerate(ordered):
        # Refresh immediately before each catch; the returned screenshot is
        # the only source used to recover the moving carousel phase.
        step([], capture=True)
        target_state = truth["solution_positions"][item["id"]]
        target = stage_point(target_state["x"], target_state["y"])
        for _attempt in range(3):
            # The carousel is frozen after this screenshot is returned. Catch
            # the requested visible shape at its measured center with the
            # public drag action, then inspect the next delivered boundary.
            source = visible_object_center(str(item["shape"]))
            step([{"mouse": {"left_click_drag": [source, target]}}])
            if done:
                return observation, done, info, steps
            step([], capture=True)
            try:
                visible_object_center(str(item["shape"]))
            except RuntimeError:
                break
        else:
            raise RuntimeError(f"visible carousel {item['shape']} did not leave the staging carousel")

    # Console list order follows the generated object order. Its last entry
    # spans both columns by design, so derive each visible selector rather
    # than replaying a solution-specific recorded sequence.
    object_count = len(truth["objects"])
    for object_index, item in enumerate(truth["objects"]):
        if object_index == object_count - 1:
            selector = transform(1443, 388 + 32 * math.ceil(object_index / 2))
        else:
            selector = transform(1380 + 126 * (object_index % 2), 388 + 32 * (object_index // 2))
        depth = int(truth["solution_positions"][item["id"]]["depth"])
        target_y = round(349 - depth * .72)
        step([
            {"mouse": {"left_click": list(selector)}},
            {"mouse": {"move": list(transform(1340, 314))}},
            {"mouse": {"buttons": {"left_down": True}}},
            {"mouse": {"move": list(transform(1340, target_y))}},
            {"mouse": {"buttons": {"left_up": True}}},
        ])

    # The force inspection is eight 110 ms task-clock ticks. Start it while
    # paused, then provide the exact number of complete observation windows
    # needed to expose the settled graph before pressing the visible certify
    # control. A wall-clock wait inside the paused action batch cannot advance
    # this timer.
    settle_windows = math.ceil(
        int(truth["settle_ticks"]) * int(_public["settle_tick_ms"])
        / int(entry["observation_window_ms"])
    )
    step([{"mouse": {"left_click": list(transform(1443, 513))}}], capture=True)
    for _ in range(max(0, settle_windows - 1)):
        step([], capture=True)
    step([
        {"mouse": {"left_click": list(transform(1479, 652))}},
        {"action": "wait", "time": 1.0},
    ])
    return observation, done, info, steps


def _direct_photograph_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Solve the sampled one-stage room on paused movement boundaries."""
    if str(entry["interaction"]) != "simplified" or int(entry["difficulty"]) != 1:
        raise RuntimeError("photograph direct driver expects its sampled D1 simplified room")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_photograph_paused_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "photograph_eats_the_room.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))
    if len(truth["solution"]["captures"]) != 1:
        raise RuntimeError("sampled photograph room unexpectedly has more than one rewrite")

    points = {
        "forward": list(transform(1414, 268)),
        "turn_left": list(transform(1324, 268)),
        "turn_right": list(transform(1504, 268)),
        "capture": list(transform(1414, 348)),
        "scale_up": list(transform(1495, 516)),
        "develop": list(transform(1457, 553)),
        "verify": list(transform(1467, 637)),
    }
    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def step(actions: list[dict[str, Any]], *, capture: bool = False) -> None:
        nonlocal observation, done, info, steps
        if capture:
            observation, _reward, done, info = env.step(
                actions,
                wait_between_actions=0.0,
                settle_after_actions=False,
            )
        else:
            done, info = _step_without_observation(env, actions)
        steps += 1
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        if capture and screen_path.is_file():
            shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")

    def click(name: str, count: int = 1) -> None:
        step([
            {"mouse": {"left_click": points[name]}}
            for _ in range(count)
        ])

    def hold_forward(windows: int) -> None:
        # Press before the first window and release on its following paused
        # boundary. Releasing inside the same action batch would yield no
        # continuous movement at all.
        step([
            {"mouse": {"move": points["forward"]}},
            {"mouse": {"buttons": {"left_down": True}}},
        ], capture=True)
        for _ in range(windows - 1):
            step([], capture=True)
        step([{"mouse": {"buttons": {"left_up": True}}}])

    # The fixed paused window carries a held movement beyond the narrow
    # authored x=4.0 capture mark. From the initial visible camera, a 45-degree
    # view already contains both complete beam endpoints and is inside range.
    click("turn_right", 3)
    click("capture")
    click("turn_left", 3)

    # Five windows stop at the near lip of the void. At that boundary
    # the print's default 1.2-depth plane is already inside the D1 socket
    # tolerance; four visible scale increments supply the required span.
    hold_forward(5)
    click("scale_up", 4)
    click("develop")

    # The developed bridge now makes six further forward windows collision-
    # safe and leaves the camera inside the terminal's visible contact radius.
    hold_forward(6)
    step([
        {"mouse": {"left_click": points["verify"]}},
        {"action": "wait", "time": 1.0},
    ])
    return observation, done, info, steps


def _direct_impossible_ecology_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Herd the sampled ecology on exact paused physics boundaries."""
    import cv2
    import numpy as np

    if str(entry["interaction"]) != "full":
        raise RuntimeError("ecology boundary driver expects its sampled full controls")
    window_ms = int(entry["observation_window_ms"])
    if str(entry["time_mode"]) != "paused" or window_ms <= 0:
        raise RuntimeError("ecology boundary driver expects a positive paused observation window")

    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_ecology_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "impossible_ecology.py",
    )
    grader = _load_module(
        "env_step_ecology_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "impossible_ecology.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))
    tick_ms = int(truth["controls"]["tick_ms"])
    if window_ms % tick_ms:
        raise RuntimeError("sampled ecology window is not an integral number of physics ticks")
    ticks_per_window = window_ms // tick_ms

    organisms = grader._initial_organisms(truth)
    targets = grader._targets(truth)
    arena_width = float(truth["arena"]["width"])
    arena_height = float(truth["arena"]["height"])
    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def step(actions: list[dict[str, Any]], *, capture: bool = False) -> None:
        nonlocal observation, done, info, steps
        if capture:
            observation, _reward, done, info = env.step(
                actions,
                wait_between_actions=0.0,
                settle_after_actions=False,
            )
        else:
            done, info = _step_without_observation(env, actions)
        steps += 1
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        if capture and screen_path.is_file():
            shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")

    # These are visible geometry from the immutable oracle screenshot. The
    # canvas backing store is 1000x430 while CSS stretches it into 928x522.
    def arena_point(point: list[float]) -> list[int]:
        return list(transform(
            344 + float(point[0]) / arena_width * 928,
            96 + float(point[1]) / arena_height * 522,
        ))

    field_points = {
        "CLIMATE": list(transform(1343, 191)),
        "FOOD": list(transform(1437, 191)),
        "LIGHT": list(transform(1532, 191)),
    }

    # Read coordinates in the delivered screenshot's fixed FHD observation
    # surface. Applying the action registration's nearest-feature displacement
    # here can bend opposite canvas corners independently; that mapper is for
    # action targets, not inverse measurement geometry.
    canvas_left, canvas_top = 344, 96
    canvas_right, canvas_bottom = 1272, 618

    def visible_organism_positions() -> dict[str, list[float]]:
        """Read every colored body that remains detectable in the screenshot."""
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        image = cv2.imread(str(screen_path))
        if image is None:
            raise RuntimeError("ecology env.step observation has no readable screenshot")
        positions: dict[str, list[float]] = {}
        for organism in truth["organisms"]:
            color = str(organism["color"]).lstrip("#")
            rgb = np.array(
                [int(color[index:index + 2], 16) for index in (0, 2, 4)],
                dtype=np.int16,
            )
            difference = np.max(
                np.abs(image.astype(np.int16) - rgb[::-1]),
                axis=2,
            )
            mask = (difference < 18).astype(np.uint8) * 255
            components = cv2.connectedComponentsWithStats(mask)
            candidates: list[tuple[int, float, float]] = []
            for component_index, (x, y, width, height, area) in enumerate(components[2][1:], start=1):
                if not (
                    100 <= int(area) <= 1_000
                    and canvas_left <= int(x) < canvas_right
                    and canvas_top <= int(y) < canvas_bottom
                    and 8 < int(width) < 45
                    and 8 < int(height) < 55
                ):
                    continue
                center = components[3][component_index]
                candidates.append((int(area), float(center[0]), float(center[1])))
            # The completion card can cover a body near the canvas center.
            # Use the remaining visible bodies to identify the exact paused
            # boundary instead of substituting the solver's predicted state.
            if not candidates:
                continue
            _area, screen_x, screen_y = max(candidates)
            positions[str(organism["id"])] = [
                (screen_x - canvas_left) / (canvas_right - canvas_left) * arena_width,
                (screen_y - canvas_top) / (canvas_bottom - canvas_top) * arena_height,
            ]
        if len(positions) < 3:
            raise RuntimeError(
                "too few visible ecology bodies to reconcile paused state: "
                f"found={len(positions)}"
            )
        return positions

    def reconcile_visible_boundary(
        previous: dict[str, dict[str, Any]],
        field: str,
        lure: list[float],
    ) -> dict[str, dict[str, Any]]:
        """Recover the exact callback count from visible body positions."""
        visible = visible_organism_positions()
        # Locked organisms are rendered together with same-colored sanctuary
        # outlines and labels, which can displace a connected-component
        # centroid by several pixels. The still-mobile bodies are the actual
        # physics clock: match only those that were mobile at the preceding
        # paused boundary.
        clock_positions = {
            organism_id: point
            for organism_id, point in visible.items()
            if not bool(previous[organism_id]["captured"])
        }
        if not clock_positions:
            raise RuntimeError("no visible mobile ecology body remains for paused-boundary reconciliation")
        candidates: list[tuple[float, int, dict[str, dict[str, Any]]]] = []
        candidate = copy.deepcopy(previous)
        # An 800 ms window normally contains sixteen 50 ms callbacks. Browser
        # interval phase makes the observed boundary vary slightly (the first
        # active window in this sampled run contains ten). Match the complete
        # rendered coupled state rather than assuming a callback count.
        for elapsed_ticks in range(1, max(25, ticks_per_window + 8)):
            grader._advance(candidate, targets, truth, True, field, lure)
            squared_error = 0.0
            for organism_id, point in clock_positions.items():
                state = candidate[organism_id]
                squared_error += (
                    (float(state["x"]) - point[0]) ** 2
                    + (float(state["y"]) - point[1]) ** 2
                )
            candidates.append((squared_error, elapsed_ticks, copy.deepcopy(candidate)))
        error, elapsed_ticks, matched = min(candidates, key=lambda item: item[0])
        root_mean_square_error = math.sqrt(error / len(clock_positions))
        # Colored tethers and labels are rendered into the same connected
        # component as a body and can move its pixel centroid within the
        # visible body radius. Reject a boundary only when even its best fit
        # falls outside that task-authored visual extent.
        visual_body_radius = max(float(item["radius"]) for item in truth["organisms"])
        if root_mean_square_error > visual_body_radius:
            raise RuntimeError(
                "visible ecology state does not match any plausible paused boundary: "
                f"best={elapsed_ticks} ticks, rms={root_mean_square_error:.2f}"
            )
        return matched

    def simulate(
        states: dict[str, dict[str, Any]],
        field: str,
        lure: list[float],
    ) -> dict[str, dict[str, Any]]:
        candidate = copy.deepcopy(states)
        for _ in range(ticks_per_window):
            grader._advance(candidate, targets, truth, True, field, lure)
        return candidate

    # Each organism has one dominant signed response. Work one sanctuary at
    # a time, but simulate the coupled effect on every still-mobile organism.
    # At a paused boundary, search constant lures for the next complete 800ms
    # window and inject the chosen pointer position before resuming the clock.
    for organism_id in sorted(organisms):
        if organisms[organism_id]["captured"]:
            continue
        response = organisms[organism_id]["responses"]
        field = max(response, key=lambda name: abs(float(response[name])))
        sign = 1 if float(response[field]) > 0 else -1
        step([{"mouse": {"left_click": field_points[field]}}])

        pointer_is_down = False
        for _turn in range(30):
            if organisms[organism_id]["captured"]:
                break
            state = organisms[organism_id]
            target = targets[organism_id]
            dx = float(target["center"][0]) - float(state["x"])
            dy = float(target["center"][1]) - float(state["y"])
            bearing = math.atan2(dy, dx)
            candidates: list[list[float]] = []
            for offset in (
                -math.pi,
                -3 * math.pi / 4,
                -math.pi / 2,
                -math.pi / 3,
                -math.pi / 4,
                -math.pi / 6,
                0,
                math.pi / 6,
                math.pi / 4,
                math.pi / 3,
                math.pi / 2,
                3 * math.pi / 4,
            ):
                for magnitude in (50, 100, 180, 300, 500, 800, 1200):
                    angle = bearing + offset
                    candidates.append([
                        max(4.0, min(arena_width - 4, float(state["x"]) + sign * math.cos(angle) * magnitude)),
                        max(4.0, min(arena_height - 4, float(state["y"]) + sign * math.sin(angle) * magnitude)),
                    ])
            for offset in (-math.pi / 2, -math.pi / 4, 0, math.pi / 4, math.pi / 2):
                for magnitude in (0, 50, 100, 200, 500, 1000):
                    angle = bearing + offset
                    candidates.append([
                        max(4.0, min(arena_width - 4, float(target["center"][0]) + sign * math.cos(angle) * magnitude)),
                        max(4.0, min(arena_height - 4, float(target["center"][1]) + sign * math.sin(angle) * magnitude)),
                    ])

            scored: list[tuple[float, list[float], dict[str, dict[str, Any]]]] = []
            for lure in candidates:
                candidate = simulate(organisms, field, lure)
                candidate_state = candidate[organism_id]
                distance = math.dist(
                    [float(candidate_state["x"]), float(candidate_state["y"])],
                    [float(value) for value in target["center"]],
                )
                score = distance - (1_000_000 if candidate_state["captured"] else 0)
                scored.append((score, lure, candidate))
            _score, lure, _predicted = min(scored, key=lambda item: item[0])
            actions = [{"mouse": {"move": arena_point(lure)}}]
            if not pointer_is_down:
                actions.append({"mouse": {"buttons": {"left_down": True}}})
                pointer_is_down = True
            previous = organisms
            step(actions, capture=True)
            if done:
                return observation, done, info, steps
            organisms = reconcile_visible_boundary(previous, field, lure)
        else:
            raise RuntimeError(f"ecology could not capture {organism_id} within 30 paused windows")

        # Completion clears pointerDown itself. Otherwise release on the
        # paused boundary so selecting the next field is a valid visible act.
        if not all(item["captured"] for item in organisms.values()):
            step([{"mouse": {"buttons": {"left_up": True}}}])

    if not all(item["captured"] for item in organisms.values()):
        raise RuntimeError("ecology boundary model ended with a mobile organism")
    # The game clears its logical lure state when the fifth sanctuary locks,
    # but the native pointer is still physically down and the arena retains
    # pointer capture. Release it on the paused boundary before clicking the
    # now-visible submit control.
    if pointer_is_down:
        step([{"mouse": {"buttons": {"left_up": True}}}])
    step([
        {"mouse": {"left_click": list(transform(1467, 684))}},
        {"action": "wait", "time": 1.0},
    ])
    return observation, done, info, steps


def _direct_trajectory_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Commit each hidden-flight catcher through the sampled simplified UI."""
    if str(entry["interaction"]) != "simplified":
        raise RuntimeError("closed-loop trajectory driver expects its sampled simplified controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_trajectory_closed_loop_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "trajectory_catcher.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def step(actions: list[dict[str, Any]], *, capture: bool = False) -> None:
        nonlocal observation, done, info, steps
        if capture:
            observation, _reward, done, info = env.step(
                actions,
                wait_between_actions=0.0,
                settle_after_actions=False,
            )
        else:
            done, info = _step_without_observation(env, actions)
        steps += 1
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        if capture and screen_path.is_file():
            shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")

    def canvas_point(point: dict[str, Any]) -> list[int]:
        return list(transform(
            round(370 + float(point["x"])),
            round(132 + float(point["y"]) * 440 / 480),
        ))

    paused = str(entry["time_mode"]) == "paused"
    window_ms = int(entry["observation_window_ms"])
    if paused:
        if window_ms <= 0:
            raise RuntimeError("trajectory catcher needs a positive paused observation window")
        # reset() has already supplied the first complete observation window.
        # No replay/reset is needed: the immutable first flight is still in
        # progress and its task clock is exactly one window old.
        elapsed_ms = window_ms
    else:
        # In live mode the clock keeps running while privileged state is
        # loaded and screenshot registration is calculated. Let that first
        # attempt finish, then use the visible REWIND control.
        step([
            {"action": "wait", "time": float(truth["rounds"][0]["duration_ms"]) / 1000 + .25},
        ])
        step([{"mouse": {"left_click": list(transform(1417, 619))}}])
        elapsed_ms = 0

    for round_index, (round_data, solution) in enumerate(zip(truth["rounds"], truth["solutions"], strict=True)):
        if paused:
            # Advance only in complete observation windows until the visible
            # world is inside the authored hidden commitment interval.
            while elapsed_ms < int(round_data["wall_enter_ms"]):
                step([], capture=True)
                elapsed_ms += window_ms
            if elapsed_ms > int(round_data["wall_exit_ms"]) - int(round_data["commit_margin_ms"]):
                raise RuntimeError("paused trajectory boundary skipped its commitment interval")
        else:
            wait_ms = int(round_data["wall_enter_ms"]) + 300
            step([{"action": "wait", "time": wait_ms / 1000}])
            elapsed_ms = wait_ms

        initial = round_data["initial_catcher"]
        current_angle = int(initial["angle_deg"]) % 180
        target_angle = int(solution["angle_deg"]) % 180
        clockwise = ((target_angle - current_angle) % 180) // int(round_data["rotation_step_deg"])
        counter = ((current_angle - target_angle) % 180) // int(round_data["rotation_step_deg"])
        rotate_point = transform(1498, 267) if clockwise and clockwise <= counter else transform(1336, 267)
        rotate_count = clockwise if clockwise and clockwise <= counter else counter
        aperture_delta = int(solution["aperture"]) - int(initial["aperture"])
        size_point = transform(1498, 320) if aperture_delta > 0 else transform(1336, 320)

        displacement = math.dist(
            (float(initial["x"]), float(initial["y"])),
            (float(solution["x"]), float(solution["y"])),
        )
        move_count = max(1, math.ceil(displacement / 100))
        drag_actions: list[dict[str, Any]] = [
            {"mouse": {"move": canvas_point(initial)}},
            {"mouse": {"buttons": {"left_down": True}}},
        ]
        for move_index in range(1, move_count + 1):
            amount = move_index / move_count
            drag_actions.extend((
                {"mouse": {"move": canvas_point({
                    "x": float(initial["x"]) + (float(solution["x"]) - float(initial["x"])) * amount,
                    "y": float(initial["y"]) + (float(solution["y"]) - float(initial["y"])) * amount,
                })}},
                # Without an interval FastIO may correctly deliver several
                # absolute positions before Chromium paints one pointermove.
                # The real intermediate motion must reach the game transcript.
                {"action": "wait", "time": .025},
            ))
        drag_actions.append({"mouse": {"buttons": {"left_up": True}}})
        step(drag_actions)
        for _ in range(rotate_count):
            step([{"mouse": {"left_click": list(rotate_point)}}])
        for _ in range(abs(aperture_delta) // int(round_data["aperture_step"])):
            step([{"mouse": {"left_click": list(size_point)}}])
        step([{"mouse": {"left_click": list(transform(1417, 408))}}])

        # Finish the analytic flight and capture the visible result. Paused
        # task time advances only through complete observation windows.
        if paused:
            while elapsed_ms < int(round_data["duration_ms"]):
                step([], capture=True)
                elapsed_ms += window_ms
        else:
            remaining_ms = int(round_data["duration_ms"]) - elapsed_ms + 650
            step([{"action": "wait", "time": remaining_ms / 1000}], capture=True)
        if done:
            return observation, done, info, steps
        if round_index + 1 < len(truth["rounds"]):
            step([{"mouse": {"left_click": list(transform(1417, 619))}}])
            elapsed_ms = 0

    step([
        {"mouse": {"left_click": list(transform(1469, 689))}},
        {"action": "wait", "time": 1.0},
    ], capture=not paused)
    return observation, done, info, steps


def _direct_uncompacted_trace_env_step_solve(
    env,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Replay trusted visible input with its recorded within-group cadence."""
    groups, _remapped = _remap_visible_mouse_coordinates(
        copy.deepcopy(list(trace["groups"])),
        transform,
    )
    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    replay_started = time.monotonic()
    batches = _live_timeline_batches(
        groups,
        initial_action_delay_ms=float(trace.get("initial_action_delay_ms") or 0),
    )
    for batch in batches:
        elapsed_ms = (time.monotonic() - replay_started) * 1000
        wait_ms = max(0.0, float(batch["target_start_ms"]) - elapsed_ms)
        actions: list[dict[str, Any]] = []
        if wait_ms >= 1:
            actions.append({"action": "wait", "time": wait_ms / 1000})
        actions.extend(batch["actions"])
        done, info = _step_without_observation(env, actions)
        steps += 1
        if done:
            break
    return observation, done, info, steps


def _direct_terminal_escape_env_step_solve(
    env,
    groups: list[dict[str, Any]],
    transform,
    initial_observation: dict[str, Any],
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Replay the terminal transcript and use its visible Verify control.

    Live play normally auto-submits 140 ms after the last modal layer closes.
    A zero-window paused task intentionally does not advance that timer, but
    the same completed screen exposes an explicit Verify Session button.  A
    paused agent can therefore finish through that visible control.
    """
    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    for group in groups:
        observation, done, info = _step(env, list(group["actions"]))
        steps += 1
        if done:
            return observation, done, info, steps
    observation, done, info = _step(
        env,
        [
            {"mouse": {"left_click": list(transform(1477, 683))}},
            {"action": "wait", "time": 1.0},
        ],
    )
    steps += 1
    return observation, done, info, steps


def _direct_ribbon_switchboard_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Operate the sampled coordinate console through compact visible input."""
    if str(entry["interaction"]) != "simplified":
        raise RuntimeError("ribbon switchboard direct driver expects its sampled simplified controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_ribbon_switchboard_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "ribbon_switchboard.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))
    path = [list(map(int, point)) for point in truth["target_path"]]
    target_crossings = list(truth["target_crossings"])
    requirements = dict(truth["requirements"])

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0

    # The console's X and Y number fields precede its four operation buttons
    # in keyboard order. A triple-click selects the visible X value; typing X
    # and Tab then selecting Y lets the next standard keyboard.text action set
    # Y, tab to the requested visible button, and press Enter. This is the same
    # public mouse/keyboard API an agent has, but avoids replaying three
    # separately recorded actions for every individual field edit.
    # The current 1920x1080 task viewport places the visible number-input
    # baseline at y=298.  The older recorded action trace used y=274, which
    # lands in the console label after the task header's current line wrap.
    x_field = list(transform(1406, 298))

    def coordinate_operation(point: list[int], button_tabs: int) -> list[dict[str, Any]]:
        return [
            {"mouse": {"triple_click": x_field}},
            {
                "keyboard": {
                    "text": f"{int(point[0])}\t",
                    "keys": ["ctrl", "a"],
                },
            },
            {
                "keyboard": {
                    "text": f"{int(point[1])}" + "\t" * button_tabs + "\n",
                },
            },
        ]

    min_hover = int(requirements["min_hover_samples"])
    if min_hover < 1:
        raise RuntimeError("ribbon switchboard requires no visible exploration")
    # Uniform samples of the visible target ribbon maximize route and cell
    # coverage. Add any crossing that the selected inspection lenses do not
    # yet cover; this is derived from the sampled task rather than a recorded
    # action transcript.
    hover_indices = [
        round(index * (len(path) - 1) / max(1, min_hover - 1))
        for index in range(min_hover)
    ]
    hover_points = [path[index] for index in hover_indices]
    crossing_radius = float(truth["hover_radius"]) * .58
    for crossing in target_crossings:
        point = list(map(int, crossing["point"]))
        if not any(math.dist(point, candidate) <= crossing_radius for candidate in hover_points):
            hover_points.append(point)

    covered_path = {
        index
        for point in hover_points
        for index, candidate in enumerate(path)
        if math.dist(point, candidate) <= float(truth["hover_radius"])
    }
    covered_crossings = {
        str(crossing["id"])
        for point in hover_points
        for crossing in target_crossings
        if math.dist(point, crossing["point"]) <= crossing_radius
    }
    covered_cells = {f"{point[0] // 55}:{point[1] // 55}" for point in hover_points}
    if (
        len(hover_points) < min_hover
        or len(covered_cells) < int(requirements["min_hover_cells"])
        or len(covered_path) < int(requirements["min_target_coverage"])
        or len(covered_crossings) < int(requirements["min_crossing_coverage"])
    ):
        raise RuntimeError("derived ribbon inspection points do not satisfy the visible exploration meters")

    setup_actions: list[dict[str, Any]] = []
    for point in hover_points:
        setup_actions.extend(coordinate_operation(point, 1))

    # Start at the marked source, then take exactly as many monotonically
    # spaced samples as the task requires. The generated route is already the
    # visible ribbon polyline; validate both raw-distance and curve-parameter
    # limits before sending any input.
    setup_actions.extend(coordinate_operation(path[0], 2))
    required_samples = int(requirements["min_trace_samples"])
    # Repeated samples at the same visible coordinate are valid continuous
    # hold observations. Use them to meet the sample-count meter, while the
    # smaller set of coordinate changes is determined solely by the maximum
    # allowed curve-parameter advance. The START button retains focus, so Tab
    # reaches RECORD TRACE SAMPLE and each Enter is a real visible-button
    # activation delivered inside one ordinary keyboard.text action.
    maximum_index_advance = max(1, math.floor(float(requirements["max_parameter_jump"])))
    sample_indices: list[int] = []
    previous_index = 0
    while previous_index < len(path) - 1:
        path_index = min(len(path) - 1, previous_index + maximum_index_advance)
        while (
            path_index > previous_index
            and math.dist(path[previous_index], path[path_index]) > int(requirements["max_raw_step"])
        ):
            path_index -= 1
        if path_index == previous_index:
            raise RuntimeError("no ribbon polyline advance satisfies the visible continuity limits")
        sample_indices.append(path_index)
        previous_index = path_index
    movement_sample_count = len(sample_indices)
    duplicate_sample_count = max(0, required_samples - movement_sample_count)
    trace_actions: list[dict[str, Any]] = []
    if duplicate_sample_count:
        trace_actions.append({"keyboard": {"text": "\t" + "\n" * duplicate_sample_count}})
    previous_index = 0
    for path_index in sample_indices:
        if (
            path_index - previous_index > float(requirements["max_parameter_jump"])
            or math.dist(path[previous_index], path[path_index]) > int(requirements["max_raw_step"])
        ):
            raise RuntimeError("derived ribbon trace exceeds the visible continuity limits")
        trace_actions.extend(coordinate_operation(path[path_index], 3))
        previous_index = path_index
    # The final sample leaves both terminal coordinates in the console and
    # focus on RECORD TRACE SAMPLE. Tab once and press Enter to release using
    # that same visible point.
    trace_actions.append({"keyboard": {"text": "\t\n"}})

    # Exploration and trace start are synchronous visible-control actions at
    # one frozen boundary. The held signal then spans only complete paused
    # observation windows; no wall-time wait or task-specific settlement is
    # allowed to contribute to its duration.
    done, info = _step_without_observation(env, setup_actions)
    steps += 1
    if done:
        return observation, done, info, steps
    held_ms = 0
    window_ms = int(entry["observation_window_ms"])
    if window_ms <= 0:
        raise RuntimeError("ribbon switchboard held trace requires a nonzero observation window")
    while held_ms < int(requirements["min_trace_ms"]):
        observation, done, info = _step(env, [])
        steps += 1
        held_ms += window_ms
        if done:
            return observation, done, info, steps
    done, info = _step_without_observation(env, trace_actions)
    steps += 1
    if done:
        return observation, done, info, steps
    terminal_actions = [
        {"mouse": {"left_click": list(transform(1479, 643))}},
        {"action": "wait", "time": 1.0},
    ]
    done, info = _step_without_observation(env, terminal_actions)
    steps += 1
    return observation, done, info, steps


def _direct_gravity_room_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Execute each authored quarter-turn after the prior one visibly settles."""
    if str(entry["interaction"]) != "simplified":
        raise RuntimeError("gravity-room direct driver expects its sampled simplified controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_gravity_room_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "gravity_room_freight.py",
    )
    public, truth = generator.generate(task, str(trace["ground_truth_seed"]))
    window_ms = int(entry["observation_window_ms"])
    if window_ms <= 0:
        raise RuntimeError("gravity-room rotation needs a positive paused observation window")
    settle_windows = max(1, math.ceil(float(public["rotation_ms"]) / window_ms))
    buttons = {
        "ccw": list(transform(1120, 245)),
        "cw": list(transform(1120, 314)),
    }

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0

    def step(actions: list[dict[str, Any]]) -> None:
        nonlocal observation, done, info, steps
        observation, done, info = _step(env, actions)
        steps += 1

    for direction in truth["solution"]:
        step([{"mouse": {"left_click": buttons[str(direction)]}}])
        if done:
            return observation, done, info, steps
        for _ in range(settle_windows - 1):
            step([])
    step([{"mouse": {"left_click": list(transform(1120, 478))}}])
    return observation, done, info, steps


def _direct_slot_reel_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Capture each reel on a reachable paused task-clock boundary."""
    if str(entry["interaction"]) != "simplified":
        raise RuntimeError("slot-reel direct driver expects its sampled simplified controls")
    window_ms = int(entry["observation_window_ms"])
    if window_ms <= 0:
        raise RuntimeError("slot-reel direct driver needs a positive observation window")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_slot_reel_generator",
        BENCHMARK / "shared_scripts" / "setup_task.py",
    )
    public, _truth = generator.generate_slot_reel_capture(
        task,
        str(trace["ground_truth_seed"]),
    )
    capture_ratio = float(public.get("capture_window_ratio", 1.0))

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    # reset() has already collected the first complete observation window.
    elapsed_ms = window_ms

    def step(actions: list[dict[str, Any]]) -> None:
        nonlocal observation, done, info, steps, elapsed_ms
        observation, done, info = _step(env, actions)
        steps += 1
        elapsed_ms += window_ms

    for reel in public["reels"]:
        for _ in range(1_000):
            interval_ms = int(reel["interval_ms"])
            token_index = (
                math.floor(elapsed_ms / interval_ms) + int(reel.get("phase") or 0)
            ) % len(reel["tokens"])
            cycle_position = (elapsed_ms % interval_ms) / interval_ms
            ready = (
                capture_ratio >= 1.0
                or abs(cycle_position - 0.5) <= capture_ratio / 2.0
            )
            if str(reel["tokens"][token_index]) == str(reel["target"]) and ready:
                break
            step([])
        else:
            raise RuntimeError(f"no paused capture boundary found for reel {reel['id']}")
        step([{"mouse": {"left_click": list(transform(1138, 591))}}])
        if done:
            return observation, done, info, steps
    step(
        [
            {"mouse": {"left_click": list(transform(1310, 591))}},
            {"action": "wait", "time": 1.0},
        ]
    )
    return observation, done, info, steps


def _direct_microgame_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Operate every reactor system on the paused task-clock boundaries."""
    import numpy as np

    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_microgame_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "microgame_gauntlet.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))
    groups, _remapped = _remap_visible_mouse_coordinates(
        copy.deepcopy(list(trace["groups"])),
        transform,
    )

    # Continuous intercept catches were deliberately driven from the moving
    # visible target and therefore are not stable recorded groups. The two
    # untimed motor trials and final certificate are recognizable from their
    # public action shapes and can be reused verbatim.
    route_groups = [
        group for group in groups
        if sum("move" in (action.get("mouse") or {}) for action in group["actions"]) >= 10
        and any((action.get("mouse") or {}).get("buttons", {}).get("left_down") for action in group["actions"])
    ]
    pressure_groups = [
        group for group in groups
        if any("space" in (action.get("keyboard") or {}).get("keys_down", []) for action in group["actions"])
    ]
    certificate_groups = [
        group for group in groups
        if group not in route_groups
        and group not in pressure_groups
        and any((action.get("mouse") or {}).get("buttons", {}).get("left_down") for action in group["actions"])
    ]
    if len(route_groups) != 1 or len(pressure_groups) != 1 or not certificate_groups:
        raise RuntimeError("reactor trace does not expose the route, pressure, and certificate gestures")
    certificate_group = certificate_groups[-1]

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    window_ms = int(entry["observation_window_ms"])
    if str(entry["time_mode"]) != "paused" or window_ms <= 0:
        raise RuntimeError("reactor boundary driver expects a positive paused observation window")

    def step(actions: list[dict[str, Any]], *, capture: bool = False) -> None:
        nonlocal observation, done, info, steps
        if capture:
            observation, _reward, done, info = env.step(
                actions,
                wait_between_actions=0.0,
                settle_after_actions=False,
            )
        else:
            done, info = _step_without_observation(env, actions)
        steps += 1

    def replay(selected: list[dict[str, Any]]) -> None:
        batches = _live_timeline_batches(selected, initial_action_delay_ms=0)
        if not batches:
            return
        origin_ms = float(batches[0]["target_start_ms"])
        started = time.monotonic()
        for batch in batches:
            elapsed_ms = (time.monotonic() - started) * 1000
            wait_ms = max(0.0, float(batch["target_start_ms"]) - origin_ms - elapsed_ms)
            actions: list[dict[str, Any]] = []
            if wait_ms >= 1:
                actions.append({"action": "wait", "time": wait_ms / 1000})
            actions.extend(batch["actions"])
            step(actions)
            if done:
                return

    for round_index, round_data in enumerate(truth["rounds"]):
        round_type = str(round_data["type"])
        if round_type == "dial":
            # Browser timer phase makes the callback count at the delivered
            # screenshot boundary vary. Do not infer that count. Re-grip the
            # still-visible dial at a range of release angles and brake only
            # when the delivered screenshot visibly marks the brake in-zone.
            velocity = 4.0
            center_x, center_y, radius = 770.0, 389.0, 88.0

            def dial_point(angle: float) -> list[int]:
                radians = math.radians(angle)
                return list(transform(
                    center_x + math.cos(radians) * radius,
                    center_y + math.sin(radians) * radius,
                ))

            def visible_dial_angle() -> float:
                import cv2

                screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
                image = cv2.imread(str(screen_path))
                if image is None:
                    raise RuntimeError("reactor env.step observation has no readable screenshot")
                hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
                dial_center_x, dial_center_y = transform(770, 381)
                dial_edge_x = transform(858, 381)[0]
                dial_radius = abs(dial_edge_x - dial_center_x)
                rows, columns = np.indices(hsv.shape[:2])
                radial_distance = np.hypot(
                    columns - dial_center_x,
                    rows - dial_center_y,
                )
                # The blue needle is the only component of this hue inside
                # the wheel annulus. Its vector from the dial center directly
                # exposes the same visible angle printed below the wheel.
                needle = (
                    (hsv[:, :, 0] >= 90) & (hsv[:, :, 0] <= 105)
                    & (hsv[:, :, 1] >= 160)
                    & (radial_distance >= dial_radius * .38)
                    & (radial_distance <= dial_radius * 1.25)
                )
                if int(np.count_nonzero(needle)) < 40:
                    raise RuntimeError("could not locate the visible reactor dial needle")
                needle_x = float(columns[needle].mean())
                needle_y = float(rows[needle].mean())
                return math.degrees(math.atan2(
                    needle_x - dial_center_x,
                    -(needle_y - dial_center_y),
                )) % 360

            # At this sampled D5 boundary, an 800 ms window produces nine
            # 88 ms coast ticks.  The four-degree launch loses about 27
            # degrees between the requested pointer angle and the delivered
            # frozen angle (coast displacement minus pointer-angle bias).
            # Launch once so the transcript remains one valid physical state
            # transition; repeated calibration drags during coast are not a
            # legal reactor trace.
            release_angle = (float(round_data["target_angle"]) - 27.0) % 360
            step([
                {"mouse": {"move": dial_point(release_angle - 2 * velocity)}},
                {"mouse": {"buttons": {"left_down": True}}},
                {"mouse": {"move": dial_point(release_angle - velocity)}},
                {"mouse": {"move": dial_point(release_angle)}},
                {"mouse": {"buttons": {"left_up": True}}},
            ], capture=True)
            delivered_angle = visible_dial_angle()
            signed_angle_error = (
                delivered_angle - float(round_data["target_angle"]) + 180
            ) % 360 - 180
            if abs(signed_angle_error) > float(round_data["target_tolerance"]):
                raise RuntimeError(
                    f"single reactor coast froze {signed_angle_error:.2f} degrees outside the brake target"
                )
            step([{"mouse": {"left_click": list(transform(770, 554))}}])
        elif round_type == "intercept":
            step([{"mouse": {"left_click": list(transform(770, 482))}}])

            def visible_intercept_state(packet: dict[str, Any]) -> tuple[list[int] | None, float | None]:
                import cv2

                screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
                image = cv2.imread(str(screen_path))
                if image is None:
                    raise RuntimeError("reactor env.step observation has no readable screenshot")
                left, top = transform(380, 330)
                right, bottom = transform(1160, 450)
                hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
                def circle_center(source: Any) -> tuple[float, float] | None:
                    region = cv2.cvtColor(
                        source[top:bottom, left:right],
                        cv2.COLOR_BGR2GRAY,
                    )
                    circles = cv2.HoughCircles(
                        cv2.medianBlur(region, 5),
                        cv2.HOUGH_GRADIENT,
                        dp=1,
                        minDist=80,
                        param1=80,
                        param2=30,
                        minRadius=25,
                        maxRadius=42,
                    )
                    if circles is None:
                        return None
                    return (
                        left + float(circles[0][0][0]),
                        top + float(circles[0][0][1]),
                    )

                center = circle_center(image)
                if center is None:
                    return None, None
                center_x, center_y = center
                track_left, track_right = transform(411, 389)[0], transform(1129, 389)[0]
                gate_top = transform(770, 340)[1]
                gate_bottom = transform(770, 477)[1]
                gate_color = (
                    (hsv[:, :, 0] <= 15)
                    & (hsv[:, :, 1] >= 120)
                )
                column_counts = gate_color[
                    max(0, gate_top):min(image.shape[0], gate_bottom + 1),
                    max(0, track_left):min(image.shape[1], track_right + 1),
                ].sum(axis=0)
                gate_columns = np.flatnonzero(column_counts >= 80) + track_left
                if gate_columns.size < 4:
                    return None, None
                groups: list[list[int]] = []
                for column in map(int, gate_columns):
                    if not groups or column > groups[-1][-1] + 1:
                        groups.append([column])
                    else:
                        groups[-1].append(column)
                if len(groups) < 2:
                    return None, None
                gate_left = float(np.mean(groups[0]))
                gate_right = float(np.mean(groups[-1]))
                gate_center = (gate_left + gate_right) / 2
                frames = list(observation.get("frames") or [])
                if len(frames) < 2:
                    return None, gate_center
                previous_path = Path(str((frames[-2] or {}).get("path") or ""))
                previous_image = cv2.imread(str(previous_path))
                previous = circle_center(previous_image) if previous_image is not None else None
                if previous is None or abs(center_x - previous[0]) < 2:
                    return None, gate_center
                direction = 1 if center_x > previous[0] else -1
                track_width = float(track_right - track_left)
                predicted_x = center_x + direction * float(packet["speed"]) / 100 * track_width
                predicted_x = min(
                    track_left + .92 * track_width,
                    max(track_left + .08 * track_width, predicted_x),
                )
                predicted_position = (predicted_x - track_left) / track_width * 100
                # The selected final frame can precede the exact frozen
                # boundary by one timer tick (for example 795 ms versus an
                # 800 ms pause).  Judge the projected frozen position, not
                # whether the slightly earlier screenshot is already orange.
                if abs(predicted_position - float(packet["gate_center"])) > float(packet["gate_half_width"]):
                    return None, gate_center
                return [round(predicted_x), round(center_y)], gate_center

            for packet in round_data["packets"]:
                for _window in range(80):
                    step([], capture=True)
                    target, gate_center = visible_intercept_state(packet)
                    if target is not None:
                        step([
                            {"mouse": {"move": target}},
                            {"mouse": {"buttons": {"left_down": True}}},
                            {"mouse": {"buttons": {"left_up": True}}},
                        ])
                        # A successful hit either advances to the next visibly
                        # different gate or seals the round, removing the gate.
                        # Verify that boundary before counting the packet; if
                        # the click missed, re-arm the still-visible scanner
                        # and continue observing the same packet.
                        step([], capture=True)
                        _next_target, next_gate_center = visible_intercept_state(packet)
                        if (
                            next_gate_center is None
                            or gate_center is not None
                            and abs(next_gate_center - gate_center) > 10
                        ):
                            break
                else:
                    raise RuntimeError(f"packet {packet['id']} never reached a paused capture boundary")
        elif round_type == "chord":
            charge_windows = math.ceil(
                int(round_data["required_ticks"]) * int(round_data["tick_ms"])
                / window_ms
            )
            for first, second in round_data["chords"]:
                step([{"keyboard": {"keys_down": [str(first), str(second)]}}])
                for _ in range(charge_windows):
                    step([], capture=True)
                step([{"keyboard": {"keys_up": [str(first), str(second)]}}])
        elif round_type in {"route", "pressure"}:
            # These systems are geometric/event ordered rather than timed.
            # Their successful recorded physical gesture is reusable verbatim
            # while task time is paused.
            replay(route_groups if round_type == "route" else pressure_groups)
        else:
            raise RuntimeError(f"unsupported reactor round {round_type}")
        if done:
            return observation, done, info, steps
        if round_index < len(truth["rounds"]) - 1:
            # Every successful system seals through a 420 ms visible task
            # transition. One 800 ms observation both shows that transition
            # and reaches the next system without any generic settlement.
            step([], capture=True)

    terminal_actions = [
        *list(certificate_group["actions"]),
        {"action": "wait", "time": 1.0},
    ]
    step(terminal_actions)
    return observation, done, info, steps


def _direct_rorschach_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    groups: list[dict[str, Any]],
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Let each visible material response finish before the next probe."""
    if str(entry["interaction"]) != "simplified":
        raise RuntimeError("paused Rorschach driver expects its sampled simplified controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    specimen_count = int(parameters["specimen_count"])
    required_tool_count = int(parameters["required_tool_count"])
    response_group_count = specimen_count * required_tool_count
    if required_tool_count != 1 or len(groups) != response_group_count + 1:
        raise RuntimeError(
            "sampled Rorschach trace does not contain one probe group per specimen plus stamping"
        )

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def step(actions: list[dict[str, Any]]) -> None:
        nonlocal observation, done, info, steps
        observation, _reward, done, info = env.step(
            actions,
            wait_between_actions=0.0,
            settle_after_actions=False,
        )
        steps += 1
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        if screen_path.is_file():
            shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")

    cycle_ms = int(parameters["ticks_per_cycle"]) * int(parameters["tick_ms"])
    windows_per_cycle = math.ceil(cycle_ms / int(entry["observation_window_ms"]))
    for group in groups[:response_group_count]:
        # The registered oracle group contains only visible card selection and
        # the labelled test proxy. Its env.step supplies the first task-time
        # window; any remaining windows are explicit no-action observations.
        step(list(group["actions"]))
        for _ in range(max(0, windows_per_cycle - 1)):
            step([])
    step(list(groups[-1]["actions"]))
    return observation, done, info, steps


def _direct_scroll_cage_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Drive the fixed-step checkbox body using its visible pointer field."""
    import cv2
    import numpy as np

    if str(entry["interaction"]) != "simplified":
        raise RuntimeError("closed-loop scroll-cage driver expects its sampled simplified controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_scroll_cage_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "moving_checkbox_evasive_button.py",
    )
    grader = _load_module(
        "env_step_scroll_cage_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "moving_checkbox_evasive_button.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))
    scene = truth["scene"]
    physics = truth["physics"]
    offsets = [int(value) for value in truth["solution_offsets"]]
    ticks_per_window = int(entry["observation_window_ms"]) // int(physics["tick_ms"])
    if ticks_per_window < 1:
        raise RuntimeError("scroll-cage observation window contains no fixed physics tick")

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0

    def step(actions: list[dict[str, Any]], *, capture: bool = False) -> None:
        nonlocal observation, done, info, steps
        if capture:
            observation, _reward, done, info = env.step(
                actions,
                wait_between_actions=0.0,
                settle_after_actions=False,
            )
        else:
            done, info = _step_without_observation(env, actions)
        steps += 1

    # Operate the sampled simplified shaft buttons. Their positions are fixed
    # visible controls in the registered screenshot, while truth supplies
    # only the desired offset register.
    shaft_actions: list[dict[str, Any]] = []
    for shaft, (before, after) in enumerate(zip(scene["initial_offsets"], offsets, strict=True)):
        direction = 1 if int(after) > int(before) else -1
        button = transform(1884 if direction > 0 else 1702, 272 + shaft * 72)
        shaft_actions.extend(
            {"mouse": {"left_click": list(button)}}
            for _ in range(abs(int(after) - int(before)) // int(scene["offset_step"]))
        )
    step(shaft_actions)

    def arena_point(x: float, y: float) -> list[int]:
        return list(transform(
            round(52 + max(0.0, min(1000.0, x)) / 1000 * 1606),
            round(152 + max(0.0, min(520.0, y)) / 520 * 830),
        ))

    arena_left, arena_top = transform(52, 152)
    arena_right, arena_bottom = transform(1658, 982)
    pointer_park = list(transform(1760, 700))

    def visible_body() -> tuple[float, float]:
        """Read the checkbox itself from the latest env.step screenshot."""
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        image = cv2.imread(str(screen_path))
        if image is None:
            raise RuntimeError("scroll-cage env.step observation has no readable screenshot")
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        teal = cv2.inRange(hsv, (70, 80, 40), (105, 255, 255))
        candidates: list[tuple[float, int, int, int, int]] = []
        for contour in cv2.findContours(teal, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
            x, y, width, height = cv2.boundingRect(contour)
            area = cv2.contourArea(contour)
            if not (arena_left <= x <= arena_right and arena_top <= y <= arena_bottom):
                continue
            # The form's visible cyan inset is an 18 px square at 1920x1080.
            # Portal strokes are thinner and less square, so this remains
            # identifiable after every motion pulse without private state.
            if 10 <= width <= 32 and 10 <= height <= 32 and .72 <= width / height <= 1.38 and area >= 110:
                candidates.append((area, x, y, width, height))
        if not candidates:
            raise RuntimeError("could not locate the visible scroll-cage checkbox")
        _area, x, y, width, height = max(candidates)
        center_x = x + width / 2
        center_y = y + height / 2
        return (
            (center_x - arena_left) / max(1, arena_right - arena_left) * 1000,
            (center_y - arena_top) / max(1, arena_bottom - arena_top) * 520,
        )

    def advance(
        body: dict[str, Any],
        cursor: dict[str, Any],
        ticks: int,
    ) -> dict[str, Any]:
        candidate = copy.deepcopy(body)
        for _ in range(ticks):
            candidate, _crossings = grader._step(
                candidate,
                cursor,
                offsets,
                scene,
                physics,
            )
        return candidate

    def reconcile(
        previous: dict[str, Any],
        previous_cursor: dict[str, Any],
        cursor: dict[str, Any],
        *,
        record_lag: bool = True,
    ) -> dict[str, Any]:
        visible_x, visible_y = visible_body()
        candidates: list[tuple[float, int, int, dict[str, Any]]] = []
        # The visible boundary can precede the point at which a newly injected
        # pointer position begins affecting the fixed-step timer. Recover that
        # split explicitly: first the previous field, then the new field.
        for total_ticks in range(0, ticks_per_window + 9):
            for previous_ticks in range(0, total_ticks + 1):
                current_ticks = total_ticks - previous_ticks
                boundary = advance(previous, previous_cursor, previous_ticks)
                candidate = advance(boundary, cursor, current_ticks)
                error = math.hypot(
                    float(candidate["x"]) - visible_x,
                    float(candidate["y"]) - visible_y,
                )
                candidates.append((
                    error,
                    previous_ticks,
                    current_ticks,
                    copy.deepcopy(candidate),
                ))
        error, previous_ticks, _current_ticks, matched = min(
            candidates,
            key=lambda item: item[0],
        )
        # The checkbox inset itself is the authoritative visible position.
        # Preserve the best boundary's velocity/collision state, but anchor
        # its position to that measured center so a small unobserved timer
        # phase does not accumulate across later control decisions.
        if error > 24:
            raise RuntimeError(
                f"visible scroll-cage boundary disagrees with fixed physics by {error:.1f}px"
            )
        matched["x"] = visible_x
        matched["y"] = visible_y
        if record_lag:
            observed_lag_ticks.append(previous_ticks)
        return matched

    initial_body = {
        "x": int(scene["target"]["x"]),
        "y": int(scene["target"]["y"]),
        "vx": int(scene["target"]["vx"]),
        "vy": int(scene["target"]["vy"]),
        "captured": False,
    }
    inactive_cursor = {"active": False, "x": 0, "y": 0}
    observed_lag_ticks: list[int] = []
    current_cursor = inactive_cursor
    body = reconcile(
        initial_body,
        inactive_cursor,
        inactive_cursor,
        record_lag=False,
    )

    def drive(goal_x: float, goal_y: float, *, tolerance: float, limit: int) -> None:
        nonlocal body, current_cursor
        for _ in range(limit):
            distance_to_goal = math.hypot(
                goal_x - float(body["x"]),
                goal_y - float(body["y"]),
            )
            if distance_to_goal <= tolerance:
                return

            cursors: list[dict[str, Any]] = [
                {"active": False, "x": 0, "y": 0},
            ]
            for offset_x in (-140, -110, -80, -55, 0, 55, 80, 110, 140):
                for offset_y in (-140, -110, -80, -55, 0, 55, 80, 110, 140):
                    if offset_x == 0 and offset_y == 0:
                        continue
                    cursor_x = int(body["x"]) + offset_x
                    cursor_y = int(body["y"]) + offset_y
                    if 0 <= cursor_x <= int(scene["width"]) and 0 <= cursor_y <= int(scene["height"]):
                        cursors.append({
                            "active": True,
                            "x": cursor_x,
                            "y": cursor_y,
                        })

            scored: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
            lag_ticks = (
                round(float(np.median(observed_lag_ticks[-4:])))
                if observed_lag_ticks
                else min(3, ticks_per_window // 3)
            )
            active_ticks = max(1, ticks_per_window - lag_ticks)
            for cursor in cursors:
                predicted = advance(
                    advance(body, current_cursor, lag_ticks),
                    cursor,
                    active_ticks,
                )
                remaining = math.hypot(
                    goal_x - float(predicted["x"]),
                    goal_y - float(predicted["y"]),
                )
                speed = math.hypot(
                    float(predicted["vx"]),
                    float(predicted["vy"]),
                )
                scored.append((remaining + .9 * speed, cursor, predicted))
            _score, cursor, _predicted = min(scored, key=lambda item: item[0])
            action_point = (
                arena_point(float(cursor["x"]), float(cursor["y"]))
                if cursor["active"] else pointer_park
            )
            previous = body
            step([{"mouse": {"move": action_point}}], capture=True)
            if done:
                return
            body = reconcile(previous, current_cursor, cursor)
            current_cursor = cursor
        raise RuntimeError(f"visible scroll-cage controller did not reach ({goal_x}, {goal_y})")

    route = list(truth["route_screen_y"])
    for index, boundary in enumerate(scene["boundaries"]):
        boundary_x = float(boundary["x"])
        drive(boundary_x - 48, float(route[index]), tolerance=10, limit=28)
        drive(boundary_x + 49, float(route[index]), tolerance=12, limit=28)
    clamp = scene["clamp"]
    drive(float(clamp["x"]), float(clamp["y"]), tolerance=18, limit=36)
    step([{"mouse": {"left_click": list(transform(1793, 977))}}])
    step([{"mouse": {"left_click": list(transform(1819, 1054))}}])
    return observation, done, info, steps


def _direct_orchard_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Solve the responsive simplified orchard entirely through env.step."""
    import cv2

    if str(entry["interaction"]) != "simplified":
        raise RuntimeError("closed-loop orchard driver expects its sampled simplified controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_orchard_closed_loop_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "surreal_apple_on_tree_grid.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))

    observation = initial_observation
    screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
    image = cv2.imread(str(screen_path))
    if image is None:
        raise RuntimeError("orchard env.step observation has no readable screenshot")
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    gold = cv2.inRange(hsv, (15, 40, 80), (45, 255, 255))
    rectangles: list[tuple[int, int, int, int]] = []
    for contour in cv2.findContours(gold, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, width, height = cv2.boundingRect(contour)
        if x > image.shape[1] * .64 and width > image.shape[1] * .08 and 20 <= height <= 70:
            rectangle = (x, y, width, height)
            if not any(abs(x - other[0]) <= 2 and abs(y - other[1]) <= 2 for other in rectangles):
                rectangles.append(rectangle)
    visible = sorted(rectangles, key=lambda item: item[1])
    if len(visible) < 4:
        raise RuntimeError(f"visible orchard exposed only {len(visible)} gold controls")

    orbit_left = visible[0]
    orbit_right = visible[1]
    orbit_left_center = [round(orbit_left[0] + orbit_left[2] / 2), round(orbit_left[1] + orbit_left[3] / 2)]
    orbit_right_center = [round(orbit_right[0] + orbit_right[2] / 2), round(orbit_right[1] + orbit_right[3] / 2)]
    submit = visible[-1]
    submit_center = [round(submit[0] + submit[2] / 2), round(submit[1] + submit[3] / 2)]
    # The stage canvas is the left 960 CSS pixels of the responsive main
    # panel. Its internal 960x520 drawing is stretched to the visible stage
    # height, so map privileged fruit geometry through that displayed box.
    image_height, image_width = image.shape[:2]
    canvas_left = image_width * 355 / 1920
    canvas_top = image_height * 162 / 1080
    canvas_width = image_width * 960 / 1920
    canvas_height = image_height * 866 / 1080
    angle = float(truth["view_limit_deg"])

    def project(point: list[float]) -> list[int]:
        radians = math.radians(angle)
        x, y, z = map(float, point)
        internal_x = 430 + x * math.cos(radians) + z * math.sin(radians)
        internal_y = 246 + y + .10 * z * math.cos(radians) - .05 * x * math.sin(radians)
        return [
            round(canvas_left + internal_x / 960 * canvas_width),
            round(canvas_top + internal_y / 520 * canvas_height),
        ]

    basket = truth["basket"]
    basket_center = [
        round(canvas_left + (float(basket["x"]) + float(basket["width"]) / 2) / 960 * canvas_width),
        round(canvas_top + (float(basket["y"]) + float(basket["height"]) / 2) / 520 * canvas_height),
    ]
    by_id = {str(apple["id"]): apple for apple in truth["apples"]}
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def execute(actions: list[dict[str, Any]]) -> None:
        nonlocal done, info, steps
        done, info = _step_without_observation(env, actions)
        steps += 1

    step_degrees = 6
    left_count = math.ceil(float(truth["view_limit_deg"]) / step_degrees)
    right_count = math.ceil(float(truth["view_limit_deg"]) * 2 / step_degrees)
    orbit_actions: list[dict[str, Any]] = []
    for point, count in ((orbit_left_center, left_count), (orbit_right_center, right_count)):
        for _ in range(count):
            orbit_actions.extend((
                {"mouse": {"left_click": point}},
                {"action": "wait", "time": .02},
            ))
    execute(orbit_actions)
    for fruit_id in truth["attached_ids"]:
        execute([{"mouse": {"left_click": project(by_id[str(fruit_id)]["position"])}}])
        execute([{"mouse": {"left_click": basket_center}}])
    execute([{"mouse": {"left_click": submit_center}}])
    return observation, done, info, steps


def _direct_temporal_memory_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    transform,
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Review the first-change evidence using only visible env.step controls."""
    if str(entry["interaction"]) != "full":
        raise RuntimeError("closed-loop first-change driver expects its sampled full controls")
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_temporal_memory_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "temporal_memory_first_change.py",
    )
    public, truth = generator.generate(task, str(trace["ground_truth_seed"]))
    timeline = public["timeline"]
    target_id = str(truth["target_object_id"])
    target = next(item for item in timeline["objects"] if item["id"] == target_id)
    first = min(timeline["events"], key=lambda item: int(item["at_ms"]))

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def step(actions: list[dict[str, Any]]) -> None:
        nonlocal observation, done, info, steps
        observation, _reward, done, info = env.step(
            actions,
            wait_between_actions=0.0,
            settle_after_actions=False,
        )
        steps += 1
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        if screen_path.is_file():
            shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")

    def moving_position(elapsed_ms: float) -> tuple[float, float]:
        return (
            float(target["x0"]) + math.sin(float(target["phase"]) + elapsed_ms * float(target["rate_x"])) * float(target["amp_x"]),
            float(target["y0"]) + math.cos(float(target["phase"]) * .83 + elapsed_ms * float(target["rate_y"])) * float(target["amp_y"]),
        )

    # Visible geometry from the oracle screenshot: the 700x330 canvas is
    # displayed one-for-one inside x=624..1328 and y=355..688. The review
    # range's usable thumb centers are x=635..1084 at y=976.
    def canvas_point(point: tuple[float, float]) -> list[int]:
        return list(transform(round(624 + point[0]), round(355 + point[1])))

    def review_point(at_ms: float) -> list[int]:
        ratio = max(0.0, min(1.0, at_ms / float(timeline["review_end_ms"])))
        return list(transform(round(635 + ratio * 449), 976))

    step([{"mouse": {"left_click": list(transform(976, 521))}}])
    settle_windows = math.ceil(
        float(timeline["settle_ms"]) / int(entry["observation_window_ms"])
    )
    for _ in range(max(0, settle_windows - 1)):
        step([])

    # Holding the lens over one fixed review instant produces several visible
    # observation samples during the 600 ms frame window, satisfying the
    # generated proof counts without manufacturing private events.
    pre_time = float(first["at_ms"]) - 180
    change_time = float(first["at_ms"]) + float(first["duration_ms"]) * .5
    for at_ms in (pre_time, change_time):
        step([
            {"mouse": {"left_click": review_point(at_ms)}},
            {"mouse": {"move": canvas_point(moving_position(at_ms))}},
        ])

    step([{"mouse": {"left_click": list(transform(1216, 968))}}])
    slot_index = list(timeline["settle_order"]).index(target_id)
    grid = timeline["settle_grid"]
    settled = (
        float(grid["x0"]) + (slot_index % int(grid["columns"])) * float(grid["dx"]),
        float(grid["y0"]) + (slot_index // int(grid["columns"])) * float(grid["dy"]),
    )
    step([{"mouse": {"left_click": canvas_point(settled)}}])
    return observation, done, info, steps


def _direct_kinetic_restoration_env_step_solve(
    env,
    entry: dict[str, Any],
    runtime_env: Path,
    trace: dict[str, Any],
    initial_observation: dict[str, Any],
    evidence_dir: Path,
) -> tuple[dict[str, Any], bool, dict[str, Any], int]:
    """Operate the reflowing simplified press through its visible proxies."""
    if str(entry["interaction"]) != "simplified":
        raise RuntimeError("closed-loop restoration driver expects its sampled simplified controls")
    import cv2
    task_json = runtime_env / "tasks" / str(entry["task_id"]) / "task.json"
    task = _read(task_json)
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    task["_control_condition"] = condition
    generator = _load_module(
        "env_step_kinetic_restoration_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "modifier_stack_image_grid.py",
    )
    _public, truth = generator.generate(task, str(trace["ground_truth_seed"]))

    observation = initial_observation
    done = False
    info: dict[str, Any] = {}
    steps = 0
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def step(actions: list[dict[str, Any]], *, capture: bool = False) -> None:
        nonlocal observation, done, info, steps
        if capture:
            observation, _reward, done, info = env.step(
                actions,
                wait_between_actions=0.0,
                settle_after_actions=False,
            )
        else:
            done, info = _step_without_observation(env, actions)
        steps += 1
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        if capture and screen_path.is_file():
            shutil.copy2(screen_path, evidence_dir / f"step-{steps:03d}.png")

    def enabled_buttons(*, proxy_only: bool = True) -> list[list[int]]:
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        image = cv2.imread(str(screen_path))
        if image is None:
            raise RuntimeError("restoration env.step observation has no readable screenshot")
        height, width = image.shape[:2]
        scale_x, scale_y = width / 1280, height / 720
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        gold = cv2.inRange(hsv, (15, 40, 80), (45, 255, 255))
        rectangles: set[tuple[int, int, int, int]] = set()
        for contour in cv2.findContours(gold, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]:
            x, y, rect_width, rect_height = cv2.boundingRect(contour)
            if proxy_only:
                if not (
                    x >= 1000 * scale_x
                    and 184 * scale_x <= rect_width <= 220 * scale_x
                    and 20 * scale_y <= rect_height <= 42 * scale_y
                    and y < 630 * scale_y
                ):
                    continue
            else:
                if not (
                    x >= 970 * scale_x
                    and 205 * scale_x <= rect_width <= 245 * scale_x
                    and y >= 620 * scale_y
                ):
                    continue
            rectangles.add((x, y, rect_width, rect_height))
        # RETR_LIST reports both sides of a one-pixel border. Merge those
        # duplicate boxes before interpreting the visible document order.
        merged: list[tuple[int, int, int, int]] = []
        for rectangle in sorted(rectangles, key=lambda item: (item[1], item[0], -item[2])):
            if any(abs(rectangle[0] - other[0]) <= 2 and abs(rectangle[1] - other[1]) <= 2 for other in merged):
                continue
            merged.append(rectangle)
        return [[round(x + rect_width / 2), round(y + rect_height / 2)] for x, y, rect_width, rect_height in merged]

    def outlined_buttons() -> list[list[int]]:
        """Return enabled outlined proxies, excluding already-set fills."""
        screen_path = Path(str((observation.get("screen") or {}).get("path") or ""))
        image = cv2.imread(str(screen_path))
        if image is None:
            raise RuntimeError("restoration env.step observation has no readable screenshot")
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        height, width = image.shape[:2]
        half_width = max(10, round(70 * width / 1280))
        half_height = max(4, round(8 * height / 720))
        result: list[list[int]] = []
        for center_x, center_y in enabled_buttons():
            crop = hsv[
                max(0, center_y - half_height):min(height, center_y + half_height + 1),
                max(0, center_x - half_width):min(width, center_x + half_width + 1),
            ]
            gold_pixels = cv2.inRange(crop, (15, 40, 80), (45, 255, 255))
            fill_ratio = cv2.countNonZero(gold_pixels) / max(1, crop.shape[0] * crop.shape[1])
            if fill_ratio < .45:
                result.append([center_x, center_y])
        return result

    def click(point: list[int], *, capture: bool = True) -> None:
        step([{"mouse": {"left_click": point}}], capture=capture)

    # Initial reset observations can land anywhere in the film. Only captured
    # observation windows advance paused playback; a wall-time wait action is
    # deliberately excluded from task time.
    for artifact_index, artifact in enumerate(truth["artifacts"]):
        playback_windows = math.ceil(
            float(artifact["playback_ms"]) / int(entry["observation_window_ms"])
        ) + 1
        for _ in range(playback_windows):
            step([], capture=True)
        # The proxy rack continues below the initial viewport. This is a
        # normal visible page scroll through env.step, equivalent to the
        # browser's automatic scroll when a human tabs to the lower control.
        step([
            {"mouse": {"move": [1100, 600]}},
            {"mouse": {"scroll": 5}},
        ], capture=True)
        available = [str(token_id) for token_id in artifact["rack_order"]]
        desired = [str(item["id"]) for item in reversed(artifact["stack"])]
        for slot_index, token_id in enumerate(desired):
            buttons = enabled_buttons()
            module_buttons = buttons[:len(available)]
            click(module_buttons[available.index(token_id)])
            buttons = enabled_buttons()
            # Empty slot buttons follow all available module buttons. Slots
            # are filled in order, so the next desired slot is the first one.
            click(buttons[len(available)])
            available.remove(token_id)

        # With no modules left, the visible enabled proxies are the slot-order
        # inverse switches. START HOLD appears after the last switch becomes
        # inverse-ready.
        for switch_index in range(len(desired)):
            # Set each switch exactly once. A set switch remains enabled and
            # would toggle back if clicked again, so retain document index.
            click(enabled_buttons()[switch_index])
        # Switches remain visible above START HOLD after they are set.
        click(enabled_buttons()[len(desired)])

        rail_buttons = enabled_buttons()[:2]
        if len(rail_buttons) < 2:
            raise RuntimeError(f"visible restoration rail exposed {len(rail_buttons)} controls")
        minimum_samples = int(truth["requirements"]["minimum_rail_samples"])
        for _ in range(minimum_samples):
            click(rail_buttons[0], capture=False)
        step([{"action": "wait", "time": float(truth["requirements"]["minimum_rail_ms"]) / 1000 + .08}])
        click(rail_buttons[1])
        if done:
            return observation, done, info, steps

    submit_buttons = enabled_buttons(proxy_only=False)
    if not submit_buttons:
        raise RuntimeError("visible restoration terminal has no stamp button")
    click(submit_buttons[-1])
    return observation, done, info, steps


def verify_entry(entry: dict[str, Any], output_root: Path, *, fast_io: bool) -> dict[str, Any]:
    from gym_anything.api import from_config

    entry_dir = output_root / "entries" / f"{int(entry['index']):02d}-{entry['mechanic']}"
    trace = _read(entry_dir / "trace.json")
    # Coordinate registration and compaction deliberately rewrite nested
    # action dictionaries.  Keep the immutable oracle trace untouched: direct
    # drivers such as Clockwork Clutch Safe recover fixed visible controls
    # from those original coordinates after registration has been computed.
    groups = copy.deepcopy(list(trace["groups"]))
    steps = 0
    noop_steps = 0
    with tempfile.TemporaryDirectory(prefix=f"env-step-runtime-{entry['mechanic']}-") as temporary_name:
        runtime_env = _runtime_environment(entry, Path(temporary_name), output_root)
        settings = {
            "time_mode": str(entry["time_mode"]),
            "start_paused": True,
            "observation_window_ms": int(entry["observation_window_ms"]),
            "frames_per_observation": int(entry["frames_per_observation"]),
            "play_time_seconds": int(entry["play_time_seconds"]),
        }
        env = from_config(
            str(runtime_env),
            task_id=str(entry["task_id"]),
            overrides={"runner_options": settings},
            fast_io=fast_io,
        )
        episode_dir: Path | None = None
        closed = False
        try:
            initial = env.reset(
                seed=int(entry["challenge_seed"]),
                # Every matrix entry is a different environment and is run
                # once. Building a multi-gigabyte per-entry checkpoint would
                # add work without a cache hit.
                use_cache=False,
                cache_level="pre_start",
                use_savevm=False,
            )
            if "frames" not in initial or "screen" not in initial:
                raise RuntimeError("env.reset returned no frame-window observation")
            oracle_initial = entry_dir / "oracle-initial.png"
            if not oracle_initial.is_file():
                raise RuntimeError(f"missing oracle initial screenshot: {oracle_initial}")
            current_initial = Path(str(initial["screen"]["path"]))
            transform, coordinate_diagnostics = _visible_coordinate_mapper(
                oracle_initial,
                current_initial,
            )
            groups, remapped_mouse_moves = _remap_visible_mouse_coordinates(groups, transform)
            groups, compaction = compact_agent_actions(groups)
            coordinate_diagnostics["remapped_mouse_moves"] = remapped_mouse_moves
            coordinate_diagnostics["agent_action_compaction"] = compaction
            _write(entry_dir / "coordinate-registration.json", coordinate_diagnostics)
            window_ms = int(entry["observation_window_ms"])
            mode = str(entry["time_mode"])
            done = False
            info: dict[str, Any] = {}
            replay_started = time.monotonic()
            live_completion_lateness_ms: list[float] = []
            verification_driver = "recorded visible-input trace replay"
            if str(entry["mechanic"]) == "clockwork_clutch_safe" and mode == "paused":
                _observation, done, info, direct_steps = _direct_clockwork_clutch_safe_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "privileged boundary-state search through visible paused-window clutch controls"
                )
            elif str(entry["mechanic"]) == "polyrhythm_customs":
                _observation, done, info, direct_steps = _direct_polyrhythm_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    groups,
                    transform,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "generated score through visible timing-ledger taps and holds via env.step"
                )
            elif str(entry["mechanic"]) == "clockwork_doppelganger_customs":
                _observation, done, info, direct_steps = _direct_clockwork_doppelganger_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    groups,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "paused-window env.step loop recording with privileged phase calculation"
                )
            elif str(entry["mechanic"]) == "crash_deadline_hovercar":
                _observation, done, info, direct_steps = _direct_hovercar_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    groups,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "privileged fixed-step planning through visible paused-window proxy controls"
                )
            elif str(entry["mechanic"]) == "cursor_lens_reveal":
                _observation, done, info, direct_steps = _direct_palimpsest_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    groups,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "privileged moving-echo positions through visible env.step coordinate controls"
                )
            elif str(entry["mechanic"]) == "impossible_panorama":
                _observation, done, info, direct_steps = _direct_panorama_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    groups,
                    transform,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "privileged camera framing and visible event-onset shutter hold through env.step"
                )
            elif str(entry["mechanic"]) == "wonky_text_hostile_rendering":
                _observation, done, info, direct_steps = _direct_wonky_registration_env_step_solve(
                    env,
                    entry,
                    groups,
                    initial,
                )
                steps += direct_steps
                verification_driver = (
                    "recorded physical plate controls with current-screen press anchoring through env.step"
                )
            elif str(entry["mechanic"]) == "robot_art_critic":
                _observation, done, info, direct_steps = _direct_robot_art_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "privileged class prototype through visible continuous pointer strokes"
                )
            elif str(entry["mechanic"]) == "specular_lighthouse_relay":
                _observation, done, info, direct_steps = _direct_specular_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "privileged eight-tick optical tracking through visible gimbal buttons and shutter"
                )
            elif str(entry["mechanic"]) == "thirty_year_time_wheel":
                _observation, done, info, direct_steps = _direct_time_wheel_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "privileged calendar route through visible one-detent ring drags and brake clicks"
                )
            elif str(entry["mechanic"]) == "reload_interruption":
                _observation, done, info, direct_steps = _direct_reload_interruption_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "privileged memory sequence through visible lever drags and frozen-world spark holds via env.step"
                )
            elif str(entry["mechanic"]) == "reverse_identity_gate":
                _observation, done, info, direct_steps = _direct_reverse_identity_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "privileged relay order through visible real-tab keyboard and pointer holds"
                )
            elif str(entry["mechanic"]) == "semantic_drag_drop_absurdity":
                _observation, done, info, direct_steps = _direct_semantic_drag_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "privileged specimen routing through visible physical probes and drags via env.step"
                )
            elif str(entry["mechanic"]) == "slime_commute":
                _observation, done, info, direct_steps = _direct_slime_commute_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "privileged fixed-step route through visible keyboard moves on paused observation boundaries"
                )
            elif str(entry["mechanic"]) == "wrong_number":
                _observation, done, info, direct_steps = _direct_wrong_number_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    groups,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "privileged carrier identity and drift correction through visible sliders via env.step"
                )
            elif str(entry["mechanic"]) == "wizard_critter_capture":
                _observation, done, info, direct_steps = _direct_wizard_interception_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "privileged fixed-step interception through visible lure, freeze, and arena controls"
                )
            elif str(entry["mechanic"]) == "lidar_blacksite":
                _observation, done, info, direct_steps = _direct_lidar_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "closed-loop env.step solve with privileged route and visible heading OCR"
                )
            elif str(entry["mechanic"]) == "marionette_checkpoint":
                _observation, done, info, direct_steps = _direct_marionette_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "continuous env.step slider tracking from visible phase and privileged choreography"
                )
            elif str(entry["mechanic"]) == "pheromone_dispatch":
                _observation, done, info, direct_steps = _direct_pheromone_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "closed-loop env.step solve using privileged routes and continuous visible field strokes"
                )
            elif str(entry["mechanic"]) == "rorschach_fixed_rubric" and mode == "paused":
                _observation, done, info, direct_steps = _direct_rorschach_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    groups,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "recorded visible material probes with complete paused response windows via env.step"
                )
            elif str(entry["mechanic"]) == "microgame_gauntlet":
                _observation, done, info, direct_steps = _direct_microgame_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                )
                steps += direct_steps
                verification_driver = (
                    "staged env.step replay preserving each visible reactor system and authored transition"
                )
            elif str(entry["mechanic"]) == "moving_checkbox_evasive_button":
                _observation, done, info, direct_steps = _direct_scroll_cage_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                )
                steps += direct_steps
                verification_driver = (
                    "closed-loop env.step solve using privileged waypoints and the visible pointer field"
                )
            elif str(entry["mechanic"]) == "surreal_apple_on_tree_grid":
                _observation, done, info, direct_steps = _direct_orchard_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "closed-loop env.step solve using privileged fruit identity and visible orchard controls"
                )
            elif str(entry["mechanic"]) == "photograph_eats_the_room" and mode == "paused":
                _observation, done, info, direct_steps = _direct_photograph_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "privileged one-stage route through held visible movement controls on paused windows"
                )
            elif str(entry["mechanic"]) == "impossible_ecology" and mode == "paused":
                _observation, done, info, direct_steps = _direct_impossible_ecology_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "privileged coupled-physics search through visible field and pointer controls on paused windows"
                )
            elif str(entry["mechanic"]) == "relation_prompt_grounding":
                _observation, done, info, direct_steps = _direct_relation_prompt_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "closed-loop env.step solve using privileged assembly targets and visible carousel phase"
                )
            elif str(entry["mechanic"]) == "trajectory_catcher":
                _observation, done, info, direct_steps = _direct_trajectory_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "closed-loop env.step solve using privileged intercepts and visible hidden-flight controls"
                )
            elif str(entry["mechanic"]) == "temporal_memory_first_change":
                _observation, done, info, direct_steps = _direct_temporal_memory_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "closed-loop env.step solve using privileged identity and visible review controls"
                )
            elif str(entry["mechanic"]) == "modifier_stack_image_grid":
                _observation, done, info, direct_steps = _direct_kinetic_restoration_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    initial,
                    entry_dir / "closed-loop-env-step",
                )
                steps += direct_steps
                verification_driver = (
                    "closed-loop env.step solve using privileged stack order and visible keyboard focus"
                )
            elif str(entry["mechanic"]) == "exit_vim_terminal_escape" and mode == "paused":
                _observation, done, info, direct_steps = _direct_terminal_escape_env_step_solve(
                    env,
                    groups,
                    transform,
                    initial,
                )
                steps += direct_steps
                verification_driver = (
                    "recorded terminal keystrokes followed by its visible Verify Session control"
                )
            elif str(entry["mechanic"]) == "gravity_room_freight" and mode == "paused":
                _observation, done, info, direct_steps = _direct_gravity_room_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                )
                steps += direct_steps
                verification_driver = (
                    "privileged dual-body route through settled visible quarter-turn controls"
                )
            elif str(entry["mechanic"]) == "slot_reel_capture" and mode == "paused":
                _observation, done, info, direct_steps = _direct_slot_reel_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                )
                steps += direct_steps
                verification_driver = (
                    "privileged reel targets captured on reachable paused task-clock boundaries"
                )
            elif str(entry["mechanic"]) == "ribbon_switchboard" and mode == "paused":
                _observation, done, info, direct_steps = _direct_ribbon_switchboard_env_step_solve(
                    env,
                    entry,
                    runtime_env,
                    trace,
                    transform,
                    initial,
                )
                steps += direct_steps
                verification_driver = (
                    "privileged route through the visible coordinate console and explicit result completion via env.step"
                )
            elif mode == "live":
                live_batches = _live_timeline_batches(
                    groups,
                    initial_action_delay_ms=float(trace.get("initial_action_delay_ms") or 0),
                )
                for batch in live_batches:
                    elapsed_ms = (time.monotonic() - replay_started) * 1000
                    wait_ms = max(0.0, float(batch["target_start_ms"]) - elapsed_ms)
                    step_actions: list[dict[str, Any]] = []
                    if wait_ms >= 1:
                        step_actions.append({"action": "wait", "time": wait_ms / 1000})
                    step_actions.extend(batch["actions"])
                    done, info = _step_without_observation(env, step_actions)
                    steps += 1
                    completion_ms = (time.monotonic() - replay_started) * 1000
                    expected_completion_ms = (
                        float(batch["target_end_ms"])
                        + float(batch["estimated_action_execution_ms"])
                    )
                    live_completion_lateness_ms.append(
                        completion_ms - expected_completion_ms
                    )
                    if done:
                        break
                final_target_ms = (
                    (
                        float(live_batches[-1]["target_end_ms"])
                        if live_batches else float(trace.get("initial_action_delay_ms") or 0)
                    )
                    + float(trace.get("trailing_delay_ms") or 0)
                )
                remaining_ms = max(
                    0.0,
                    final_target_ms - (time.monotonic() - replay_started) * 1000,
                )
                if not done and remaining_ms >= 1:
                    done, info = _step_without_observation(
                        env,
                        [{"action": "wait", "time": remaining_ms / 1000}],
                    )
                    steps += 1
            else:
                # The observation window is the only paused task-time unit.
                # Actions recorded within the same window are one standard
                # env.step action list; empty windows are no-action env.step
                # turns. This preserves temporal holds and trailing state
                # transitions without adding settlement time.
                paused_buckets = _paused_timeline_buckets(
                    groups,
                    observation_window_ms=window_ms,
                    trailing_delay_ms=float(trace.get("trailing_delay_ms") or 0),
                )
                for actions in paused_buckets:
                    _observation, done, info = _step(env, actions)
                    if not actions:
                        noop_steps += 1
                    steps += 1
                    if done:
                        break
            replay_wall_seconds = time.monotonic() - replay_started
            if not done:
                # Let the terminal fetch and browser microtasks finish without
                # changing paused task time, then finalize through the same API.
                _observation, done, info = _step(env, [{"action": "wait", "time": 1.0}])
                steps += 1
            if not done:
                _observation, _reward, done, info = env.step(
                    [],
                    mark_done=True,
                    capture_observation=False,
                    settle_after_actions=False,
                )
                steps += 1
            episode_dir = Path(env.episode_dir)
            verifier = dict(info.get("verifier") or {})
            # Failed browser submissions are regenerated immediately, which
            # intentionally clears result.json. Preserve the server's
            # archived attempt ledger as privileged diagnostic evidence. It
            # never supplies an action: accepted input above still travels
            # exclusively through GymAnythingEnv.step.
            attempts_path = entry_dir / "env-step-attempts.jsonl"
            try:
                env.copy_from_env(
                    "/tmp/weird_captcha_gym/attempts.jsonl",
                    str(attempts_path),
                )
            except Exception:
                attempts_path.unlink(missing_ok=True)
            server_log_path = entry_dir / "env-step-server.log"
            try:
                env.copy_from_env(
                    "/tmp/weird_captcha_server.log",
                    str(server_log_path),
                )
            except Exception:
                server_log_path.unlink(missing_ok=True)
            runner = getattr(env, "_runner", None)
            input_log = getattr(runner, "input_log", None)
            if isinstance(input_log, list):
                _write(entry_dir / "env-step-input-log.json", input_log)
            env.close()
            closed = True
            current_task = _read(episode_dir / "current_task.json") if (episode_dir / "current_task.json").is_file() else {}
            public_state = _read(episode_dir / "public_state.json") if (episode_dir / "public_state.json").is_file() else {}
            task_document = current_task.get("task") if isinstance(current_task.get("task"), dict) else current_task
            return {
                "index": entry["index"],
                "environment": entry["environment"],
                "public_name": entry["public_name"],
                "mechanic": entry["mechanic"],
                "difficulty": entry["difficulty"],
                "interaction": entry["interaction"],
                "time_mode": entry["time_mode"],
                "challenge_seed": entry["challenge_seed"],
                "task_id": entry["task_id"],
                "observation_window_ms": entry["observation_window_ms"],
                "frames_per_observation": entry["frames_per_observation"],
                "play_time_seconds": entry["play_time_seconds"],
                "status": "passed" if verifier.get("passed") is True else "verifier_failed",
                "verifier": verifier,
                "done": bool(done),
                "env_step_calls": steps,
                "noop_env_step_calls": noop_steps,
                "action_replay_wall_seconds": round(replay_wall_seconds, 3),
                "recorded_initial_action_delay_ms": trace.get("initial_action_delay_ms"),
                "recorded_trailing_delay_ms": trace.get("trailing_delay_ms"),
                "recorded_timeline_ms": round(
                    float(trace.get("recording_end_ms") or 0)
                    - float(trace.get("recording_origin_ms") or 0),
                    3,
                ),
                "live_max_action_completion_lateness_ms": (
                    round(max(live_completion_lateness_ms), 3)
                    if live_completion_lateness_ms else None
                ),
                "trace_action_groups": len(groups),
                "trace_actions": sum(len(group["actions"]) for group in groups),
                **compaction,
                "remapped_mouse_moves": remapped_mouse_moves,
                "coordinate_registration": coordinate_diagnostics["method"],
                "coordinate_registration_matches": coordinate_diagnostics["usable_match_count"],
                "episode_dir": str(episode_dir.resolve()),
                "challenge_id": public_state.get("challenge_id"),
                "task_control_condition": (task_document.get("metadata") or {}).get("control_condition"),
                "world_fingerprint": _world_fingerprint(public_state) if public_state else None,
                "oracle_world_fingerprint": trace.get("initial_world_fingerprint"),
                "same_oracle_world": bool(public_state) and _world_fingerprint(public_state) == trace.get("initial_world_fingerprint"),
                "action_api": "GymAnythingEnv.step only",
                "verification_driver": verification_driver,
                "fast_io": fast_io,
            }
        finally:
            if episode_dir is None and getattr(env, "episode_dir", None):
                episode_dir = Path(env.episode_dir)
            if not closed:
                env.close()


def verify_shard(
    manifest: dict[str, Any],
    output_root: Path,
    shard_index: int,
    shard_count: int,
    *,
    fast_io: bool,
    result_label: str | None = None,
    selected_indices: set[int] | None = None,
) -> int:
    records = []
    failures = 0
    entries = list(manifest["entries"])
    selected = (
        [entry for entry in entries if int(entry["index"]) in selected_indices]
        if selected_indices is not None
        else _selected(entries, shard_index, shard_count)
    )
    if selected_indices is not None:
        found = {int(entry["index"]) for entry in selected}
        missing = sorted(selected_indices - found)
        if missing:
            raise ValueError(f"manifest has no entries for indices {missing}")
    for position, entry in enumerate(selected, 1):
        print(f"[verify {position}/{len(selected)}] {entry['mechanic']} D{entry['difficulty']} {entry['interaction']} {entry['time_mode']}", flush=True)
        try:
            record = verify_entry(entry, output_root, fast_io=fast_io)
            if record["status"] != "passed" or not record["same_oracle_world"]:
                failures += 1
        except Exception as error:
            failures += 1
            record = {
                **{key: entry[key] for key in (
                    "index", "environment", "public_name", "mechanic",
                    "difficulty", "interaction", "time_mode", "challenge_seed",
                    "task_id", "observation_window_ms", "frames_per_observation",
                    "play_time_seconds",
                )},
                "status": "infrastructure_error",
                "error_type": type(error).__name__,
                "error": str(error),
                "traceback": traceback.format_exc(),
                "action_api": "GymAnythingEnv.step only",
                "fast_io": fast_io,
            }
            print(record["traceback"], flush=True)
        records.append(record)
        label = result_label or f"{shard_index:02d}"
        _write(output_root / f"verify-shard-{label}.json", {"records": records})
    return 1 if failures else 0


def reparse_traces(
    manifest: dict[str, Any],
    output_root: Path,
    *,
    selected_indices: set[int] | None = None,
) -> int:
    """Rebuild action groups from the immutable trusted raw-event records."""
    entries = list(manifest["entries"])
    selected = (
        [entry for entry in entries if int(entry["index"]) in selected_indices]
        if selected_indices is not None
        else entries
    )
    if selected_indices is not None:
        found = {int(entry["index"]) for entry in selected}
        missing = sorted(selected_indices - found)
        if missing:
            raise ValueError(f"manifest has no entries for indices {missing}")
    for entry in selected:
        entry_dir = output_root / "entries" / f"{int(entry['index']):02d}-{entry['mechanic']}"
        trace_path = entry_dir / "trace.json"
        raw_events_path = entry_dir / "raw-events.json"
        trace = _read(trace_path)
        raw_events = json.loads(raw_events_path.read_text(encoding="utf-8"))
        if not isinstance(raw_events, list):
            raise ValueError(f"expected a JSON list in {raw_events_path}")
        groups = parse_input_trace(raw_events)
        if not groups:
            raise AssertionError(f"{entry['mechanic']}: raw trace produced no visible actions")
        trace["trace_parser_version"] = TRACE_PARSER_VERSION
        trace["raw_event_count"] = len(raw_events)
        trace["action_group_count"] = len(groups)
        trace["action_count"] = sum(len(group["actions"]) for group in groups)
        trace["groups"] = groups
        _write(trace_path, trace)
        print(
            f"[reparse] {entry['index']} {entry['mechanic']}: "
            f"{len(raw_events)} events -> {trace['action_count']} actions",
            flush=True,
        )
    return 0


def summarize(
    manifest: dict[str, Any],
    output_root: Path,
    *,
    result_prefix: str | None = None,
) -> int:
    entries_by_index = {
        int(entry["index"]): entry for entry in manifest["entries"]
    }
    latest_by_index: dict[int, dict[str, Any]] = {}
    accepted_by_index: dict[int, dict[str, Any]] = {}
    attempt_status_counts: dict[str, int] = {}
    ignored_condition_mismatch_count = 0
    pattern = f"verify-shard-{result_prefix}*.json" if result_prefix else "verify-shard-*.json"
    result_paths = sorted(output_root.glob(pattern))
    for path in result_paths:
        for record in _read(path).get("records", []):
            record = dict(record)
            record["evidence_result_file"] = str(path.resolve())
            index = int(record["index"])
            entry = entries_by_index.get(index)
            if entry is None or any(
                key in entry and record.get(key) != entry[key]
                for key in (
                    "mechanic",
                    "difficulty",
                    "interaction",
                    "time_mode",
                    "challenge_seed",
                )
            ):
                ignored_condition_mismatch_count += 1
                continue
            latest_by_index[index] = record
            status = str(record.get("status") or "missing")
            attempt_status_counts[status] = attempt_status_counts.get(status, 0) + 1
            if (
                status == "passed"
                and record.get("same_oracle_world") is True
                and record.get("action_api") == "GymAnythingEnv.step only"
            ):
                accepted_by_index[index] = record
    # A later diagnostic rerun must not erase an earlier valid pass for the
    # exact immutable condition. Failed attempts remain counted separately.
    rows = [
        accepted_by_index.get(
            int(entry["index"]),
            latest_by_index.get(int(entry["index"]), {**entry, "status": "missing"}),
        )
        for entry in manifest["entries"]
    ]
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "missing")
        counts[status] = counts.get(status, 0) + 1
    summary = {
        "matrix_seed": manifest["matrix_seed"],
        "total": len(rows),
        "counts": counts,
        "all_passed": len(rows) == 75 and counts == {"passed": 75},
        "all_actions_through": "GymAnythingEnv.step",
        "accepted_pass_count": len(accepted_by_index),
        "attempt_status_counts": attempt_status_counts,
        "attempt_count": sum(attempt_status_counts.values()),
        "ignored_condition_mismatch_count": ignored_condition_mismatch_count,
        "result_prefix": result_prefix,
        "result_files": [str(path.resolve()) for path in result_paths],
        "records": rows,
    }
    _write(output_root / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["all_passed"] else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("prepare", "record", "snapshot", "reparse", "verify", "summarize"),
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--matrix-seed", type=int)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument(
        "--result-label",
        help="optional suffix for a non-destructive exact-condition rerun result",
    )
    parser.add_argument(
        "--result-prefix",
        help="summarize only verify result labels beginning with this prefix",
    )
    parser.add_argument(
        "--indices",
        help="comma-separated exact manifest indices to verify sequentially",
    )
    parser.add_argument(
        "--browser-engine",
        choices=("chromium", "firefox"),
        default=os.environ.get("WEIRD_CUA_ORACLE_BROWSER", "chromium"),
        help="isolated headless browser used only to record visible-input oracle traces",
    )
    parser.add_argument("--no-fast-io", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = args.manifest.resolve()
    if args.command == "prepare":
        if args.matrix_seed is None:
            raise SystemExit("prepare requires --matrix-seed")
        if manifest_path.exists():
            raise SystemExit(f"refusing to resample existing manifest: {manifest_path}")
        manifest = build_manifest(args.matrix_seed)
        _write(manifest_path, manifest)
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return
    manifest = _read(manifest_path)
    if args.result_label is not None and not re.fullmatch(r"[A-Za-z0-9_.-]+", args.result_label):
        raise SystemExit("--result-label may contain only letters, numbers, dots, underscores, and hyphens")
    if args.result_prefix is not None and not re.fullmatch(r"[A-Za-z0-9_.-]+", args.result_prefix):
        raise SystemExit("--result-prefix may contain only letters, numbers, dots, underscores, and hyphens")
    selected_indices = None
    if args.indices is not None:
        try:
            selected_indices = {int(value) for value in args.indices.split(",") if value.strip()}
        except ValueError as error:
            raise SystemExit("--indices must be a comma-separated list of integers") from error
        if not selected_indices or min(selected_indices) < 0:
            raise SystemExit("--indices must contain at least one non-negative integer")
    if args.command in {"record", "snapshot"}:
        raise SystemExit(record_shard(
            manifest,
            output_root,
            args.shard_index,
            args.shard_count,
            browser_engine=args.browser_engine,
            initial_only=args.command == "snapshot",
            selected_indices=selected_indices,
        ))
    if args.command == "reparse":
        raise SystemExit(reparse_traces(
            manifest,
            output_root,
            selected_indices=selected_indices,
        ))
    if args.command == "verify":
        raise SystemExit(verify_shard(
            manifest,
            output_root,
            args.shard_index,
            args.shard_count,
            fast_io=not args.no_fast_io,
            result_label=args.result_label,
            selected_indices=selected_indices,
        ))
    raise SystemExit(summarize(manifest, output_root, result_prefix=args.result_prefix))


if __name__ == "__main__":
    main()
