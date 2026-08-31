#!/usr/bin/env python3
"""Capture isolated headless evidence for Cockpit Preflight Checklist.

Every browser run uses a new temporary persistent Chromium profile, headless
mode, and a loopback-only puzzle server. It never attaches to an existing
browser or desktop session.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "cockpit_preflight_checklist_env"
MECHANIC = "cockpit_preflight_checklist"
BASE_TASK = ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json"
CONTROLS = ENVIRONMENT / "controls.json"
SETUP = BENCHMARK / "shared_scripts" / "setup_task.py"
EXPORT = BENCHMARK / "shared_scripts" / "export_result.sh"
SERVER = BENCHMARK / "shared_runtime" / "server" / "weird_captcha_server.py"
APP = BENCHMARK / "shared_runtime" / "app"
GRADER = BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py"
SOLVER = BENCHMARK / "tools" / "incubator_solvers" / f"{MECHANIC}.py"
VERIFIER = BASE_TASK.parent / "verifier.py"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reserve_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def condition_task(temporary: Path, level: int, interaction: str, mode: str) -> Path:
    controls = read_json(CONTROLS)
    task = read_json(BASE_TASK)
    task["metadata"]["control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": mode,
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
    }
    task["id"] = f"{MECHANIC}_d{level}_{interaction}_seed_0001{'_tpaused' if mode == 'paused' else ''}@0.2"
    path = temporary / "tasks" / f"d{level}-{interaction}-{mode}.json"
    write_json(path, task)
    return path


def start_server(task: Path, state_dir: Path, seed: str) -> tuple[subprocess.Popen[bytes], int]:
    subprocess.run(
        ["python", "-B", str(SETUP), "--task-json", str(task), "--state-dir", str(state_dir), "--seed", seed],
        cwd=ROOT, check=True, stdout=subprocess.DEVNULL,
    )
    port = reserve_port()
    process = subprocess.Popen(
        ["python", "-B", str(SERVER), "--host", "127.0.0.1", "--port", str(port), "--app-dir", str(APP), "--state-dir", str(state_dir)],
        cwd=ROOT,
        env={**os.environ, "WEIRD_CAPTCHA_CHALLENGE_SEED": seed, "WEIRD_CAPTCHA_CHEAT_PASSWORD": "cockpit-evidence-only"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            urlopen(f"http://127.0.0.1:{port}/health", timeout=.5).read()
            return process, port
        except Exception:  # noqa: BLE001
            time.sleep(.1)
    process.kill()
    raise TimeoutError(f"loopback server did not start on {port}")


def stop_server(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()


def world_fingerprint(state: dict) -> str:
    return hashlib.sha256(json.dumps({"panel": state["panel"], "parameters": state["parameters"]}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def exported(state_dir: Path, output: Path, label: str) -> tuple[dict, dict]:
    """Invoke the exact shared post-task exporter and retain its output.

    The task hook execs this script at ``/workspace/shared_scripts`` in the
    benchmark container. Calling the repository copy with the same state-dir
    environment exercises the implementation behind that mount without
    creating a host-level ``/workspace`` alias.
    """
    completed = subprocess.run(
        ["bash", str(EXPORT)],
        cwd=ROOT,
        env={**os.environ, "WEIRD_CAPTCHA_STATE_DIR": str(state_dir)},
        check=True,
        text=True,
        capture_output=True,
    )
    task_result = Path("/tmp/task_result.json")
    if not task_result.is_file():
        raise AssertionError("shared export did not create /tmp/task_result.json")
    payload = read_json(task_result)
    export_path = output / "exports" / f"{label}.json"
    write_json(export_path, payload)
    command = {
        "command": ["bash", "weird_captcha_gym/shared_scripts/export_result.sh"],
        "environment": {"WEIRD_CAPTCHA_STATE_DIR": "<isolated-condition-state-dir>"},
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "artifact": str(export_path.relative_to(output)),
        "artifact_sha256": hashlib.sha256(export_path.read_bytes()).hexdigest(),
    }
    return payload, command


def verify_export(export_path: Path, label: str) -> dict:
    verifier = load_module(VERIFIER, f"cockpit_verifier_{label.replace('-', '_')}")

    def copy_from_env(source: str, destination: str) -> None:
        if source != "/tmp/task_result.json":
            raise AssertionError(f"unexpected verifier source {source}")
        shutil.copyfile(export_path, destination)

    return verifier.verify_task(env_info={"copy_from_env": copy_from_env})


def one_visible_action(page, state: dict, mode: str, solver) -> None:
    item = state["panel"]["ranges"][0]
    if mode == "full":
        solver._full_range(page, item, item["target_low"])
    else:
        direction = 1 if item["target_low"] > item["low"] else -1
        page.locator(f'[data-range-step="{item["id"]}:low:{direction}"]').click()


def stationary_click_only_attempt(page, state: dict) -> dict:
    before = page.locator("[aria-valuenow]").evaluate_all("nodes => nodes.map(node => node.getAttribute('aria-valuenow'))")
    current_handle_clicks = 0
    target_coordinate_clicks = 0
    for item in state["panel"]["ranges"]:
        rail = page.locator(f'[data-range-rail="{item["id"]}"]')
        box = rail.bounding_box()
        if box is None:
            raise AssertionError(item["id"])
        for current in (item["low"], item["high"]):
            fraction = (current - item["minimum"]) / (item["maximum"] - item["minimum"])
            page.mouse.click(box["x"] + box["width"] * fraction, box["y"] + box["height"] / 2)
            current_handle_clicks += 1
        for target in (item["target_low"], item["target_high"]):
            fraction = (target - item["minimum"]) / (item["maximum"] - item["minimum"])
            page.mouse.click(box["x"] + box["width"] * fraction, box["y"] + box["height"] / 2)
            target_coordinate_clicks += 1
    for item in state["panel"]["dials"]:
        node = page.locator(f'[data-dial="{item["id"]}"]')
        box = node.bounding_box()
        if box is None:
            raise AssertionError(item["id"])
        current_fraction = (item["value"] - item["minimum"]) / (item["maximum"] - item["minimum"])
        current_angle = (-150 + current_fraction * 300 - 90) * math.pi / 180
        radius = min(box["width"], box["height"]) * .39
        page.mouse.click(
            box["x"] + box["width"] / 2 + math.cos(current_angle) * radius,
            box["y"] + box["height"] / 2 + math.sin(current_angle) * radius,
        )
        current_handle_clicks += 1
        fraction = (item["target"] - item["minimum"]) / (item["maximum"] - item["minimum"])
        angle = (-150 + fraction * 300 - 90) * math.pi / 180
        page.mouse.click(
            box["x"] + box["width"] / 2 + math.cos(angle) * radius,
            box["y"] + box["height"] / 2 + math.sin(angle) * radius,
        )
        target_coordinate_clicks += 1
    after = page.locator("[aria-valuenow]").evaluate_all("nodes => nodes.map(node => node.getAttribute('aria-valuenow'))")
    if before != after:
        raise AssertionError(f"stationary analog clicks changed state: {before} -> {after}")
    panel = state["panel"]
    for branch in panel["branches"]:
        if not branch["expanded"]:
            page.locator(f'[data-branch="{branch["id"]}"]').click()
        for row in branch["rows"]:
            current = row["state"]
            while current != row["target"]:
                page.locator(f'[data-circuit="{row["id"]}"]').click()
                current = panel["tree_states"][(panel["tree_states"].index(current) + 1) % len(panel["tree_states"])]
    return {
        "analog_values_before": before,
        "analog_values_after": after,
        "stationary_clicks_changed_analog_state": False,
        "stationary_clicks_on_current_handles": current_handle_clicks,
        "stationary_clicks_at_target_coordinates": target_coordinate_clicks,
    }


def visible_observation(page) -> dict:
    return {
        "prompt": page.locator(".cpf-masthead h1").inner_text(),
        "card": page.locator(".cpf-checklist").inner_text(),
        "range_units": page.locator(".cpf-range-unit").count(),
        "dial_units": page.locator(".cpf-dial-unit").count(),
        "branch_units": page.locator(".cpf-tree-branch").count(),
        "certify_label": page.locator("#cpf-certify").inner_text(),
    }


def normal_surface_check(page, phase: str) -> dict:
    text = page.locator(".cockpit-preflight").inner_text().upper()
    forbidden = [
        "EXACT CHANNELS",
        "CALIBRATION LINKS TRACED",
        "PROBE THE FIRST VISIBLE TARGET",
        "TARGET RELEASED",
        "MOVED / TARGET LOCKED",
        "FRESH PANEL ISSUED",
        "FRESH CARD ISSUED",
        "PREFLIGHT VECTOR CERTIFIED",
    ]
    present = [item for item in forbidden if item in text]
    result = {
        "phase": phase,
        "forbidden_visible_strings": present,
        "exact_counter_nodes": page.locator("#cpf-match-count").count(),
        "progress_nodes": page.locator(".cpf-progress").count(),
        "all_correct_style_attribute": page.locator(".cockpit-preflight[data-exact]").count(),
        "certify_background": page.locator("#cpf-certify").evaluate("node => getComputedStyle(node).backgroundImage"),
        "visible_verdict": page.locator(".cpf-verdict").inner_text().strip(),
        "readout": page.locator(".cpf-footer .readout").inner_text().strip(),
        "passed": False,
    }
    result["passed"] = not present and result["exact_counter_nodes"] == 0 and result["progress_nodes"] == 0 and result["all_correct_style_attribute"] == 0
    if phase == "failure-fresh":
        result["passed"] = result["passed"] and result["visible_verdict"] == "FAIL" and result["readout"] == "FAIL"
    elif phase == "solved-before-certification":
        result["passed"] = result["passed"] and result["visible_verdict"] == ""
    elif phase == "pass":
        result["passed"] = result["passed"] and result["visible_verdict"] == "PASS" and result["readout"] == "PASS"
    if not result["passed"]:
        raise AssertionError(f"benchmark-surface feedback leaked during {phase}: {result}")
    return result


def dial_tick_geometry(page) -> dict:
    records = []
    for dial_index, dial in enumerate(page.locator(".cpf-dial").all()):
        dial_box = dial.bounding_box()
        if dial_box is None:
            raise AssertionError(f"dial {dial_index} has no rendered box")
        center_x = dial_box["x"] + dial_box["width"] / 2
        center_y = dial_box["y"] + dial_box["height"] / 2
        centers = []
        angle_errors = []
        radii = []
        for tick_index, tick in enumerate(dial.locator("i").all()):
            box = tick.bounding_box()
            if box is None:
                raise AssertionError(f"dial {dial_index} tick {tick_index} has no rendered box")
            x = box["x"] + box["width"] / 2
            y = box["y"] + box["height"] / 2
            dx, dy = x - center_x, y - center_y
            actual_angle = math.degrees(math.atan2(dx, -dy))
            expected_angle = -150 + tick_index / 11 * 300
            error = abs((actual_angle - expected_angle + 180) % 360 - 180)
            centers.append([round(x, 3), round(y, 3)])
            radii.append(math.hypot(dx, dy))
            angle_errors.append(error)
        distinct = len({(round(x, 1), round(y, 1)) for x, y in centers})
        x_span = max(x for x, _ in centers) - min(x for x, _ in centers)
        y_span = max(y for _, y in centers) - min(y for _, y in centers)
        record = {
            "dial_index": dial_index,
            "dial_box": {key: round(value, 3) for key, value in dial_box.items()},
            "tick_count": len(centers),
            "distinct_center_count": distinct,
            "center_x_span_px": round(x_span, 3),
            "center_y_span_px": round(y_span, 3),
            "minimum_radius_px": round(min(radii), 3),
            "maximum_radius_px": round(max(radii), 3),
            "maximum_angle_error_degrees": round(max(angle_errors), 3),
            "tick_centers": centers,
        }
        record["passed"] = (
            record["tick_count"] == 12
            and distinct == 12
            and x_span >= dial_box["width"] * .65
            and y_span >= dial_box["height"] * .55
            and record["maximum_angle_error_degrees"] <= 2.0
        )
        if not record["passed"]:
            raise AssertionError(f"dial detents do not follow the control arc: {record}")
        records.append(record)
    return {"dial_count": len(records), "all_passed": bool(records) and all(item["passed"] for item in records), "dials": records}


def capture_model_frame(page, output: Path, time_mode: str) -> dict:
    path = output / "model_observations" / f"baseline-full-{time_mode}-frame-000.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path))
    data = path.read_bytes()
    return {
        "path": str(path.relative_to(output)),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "viewport": [1440, 900],
        "frame_index": 0,
    }


def capture_condition(playwright, *, temporary: Path, output: Path, level: int, interaction: str, time_mode: str) -> dict:
    label = f"d{level}-{interaction}-{time_mode}"
    state_dir = temporary / "states" / label
    state_dir.mkdir(parents=True)
    task = condition_task(temporary, level, interaction, time_mode)
    seed = f"cockpit-visible-d{level}"
    process, port = start_server(task, state_dir, seed)
    profile = temporary / "fresh-profiles" / label
    screenshots = output / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    context = playwright.chromium.launch_persistent_context(
        str(profile), headless=True, viewport={"width": 1440, "height": 900}, device_scale_factor=1,
    )
    page = context.pages[0]
    errors: list[str] = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    solver = load_module(SOLVER, f"cockpit_solver_{label.replace('-', '_')}")
    try:
        page.goto(f"http://127.0.0.1:{port}/?time_mode={time_mode}&start_paused=1", wait_until="networkidle")
        expect(page.locator(".cockpit-preflight")).to_be_visible(timeout=8_000)
        classes = page.locator(".cockpit-preflight").get_attribute("class") or ""
        if f"mode-{interaction}" not in classes.split():
            raise AssertionError(f"rendered interaction class mismatch: {classes}")
        initial_state = read_json(state_dir / "public_state.json")
        initial_truth = read_json(state_dir / "ground_truth.json")
        surface_checks = [normal_surface_check(page, "initial")]
        initial_certify_background = surface_checks[0]["certify_background"]
        tick_geometry = dial_tick_geometry(page) if level == 5 else None
        if time_mode == "live":
            page.screenshot(path=str(screenshots / f"{label}-initial.png"), full_page=True)
        before = page.evaluate("() => WeirdCaptchaTime.status()")
        if time_mode == "live":
            page.evaluate("() => WeirdCaptchaTime.resume()")
        page.wait_for_timeout(420)
        after = page.evaluate("() => WeirdCaptchaTime.status()")
        delay_delta = float(after["task_time_ms"]) - float(before["task_time_ms"])
        if time_mode == "live" and delay_delta < 300:
            raise AssertionError(f"live model-delay clock did not advance: {delay_delta}")
        if time_mode == "paused" and abs(delay_delta) > 2:
            raise AssertionError(f"paused model-delay clock advanced: {delay_delta}")
        observation = visible_observation(page)
        model_frame = None
        if level == 2 and interaction == "full":
            model_frame = capture_model_frame(page, output, time_mode)
            page.screenshot(path=str(screenshots / f"baseline-full-{time_mode}-observation.png"), full_page=True)
        if time_mode == "paused":
            page.evaluate("() => WeirdCaptchaTime.resume()")
        if level in {2, 5} and time_mode == "live":
            one_visible_action(page, initial_state, interaction, solver)
            if level == 2:
                page.screenshot(path=str(screenshots / f"baseline-{interaction}-active.png"), full_page=True)
            else:
                page.screenshot(path=str(screenshots / f"d5-{interaction}-post-action.png"), full_page=True)
            surface_checks.append(normal_surface_check(page, "active"))
        if level == 3 and interaction == "full" and time_mode == "live":
            nested = next(branch for branch in initial_state["panel"]["branches"] if branch.get("parent_id"))
            parent_id = nested["parent_id"]
            parent = next(branch for branch in initial_state["panel"]["branches"] if branch["id"] == parent_id)
            if not parent["expanded"]:
                page.locator(f'[data-branch="{parent_id}"]').click()
            expect(page.locator(f'[data-branch-id="{nested["id"]}"]')).to_be_visible()
            page.screenshot(path=str(screenshots / "d3-full-parent-open-nested-visible.png"), full_page=True)
        click_only = None
        if level == 2 and interaction == "full" and time_mode == "paused":
            click_only = stationary_click_only_attempt(page, initial_state)
        page.locator("#cpf-certify").click()
        expect(page.locator(".cpf-verdict.is-fail")).to_be_visible(timeout=8_000)
        surface_checks.append(normal_surface_check(page, "failure-fresh"))
        refreshed = read_json(state_dir / "public_state.json")
        if refreshed["challenge_id"] == initial_state["challenge_id"]:
            raise AssertionError("failed submission did not issue a fresh challenge")
        if click_only is not None:
            archived = json.loads((state_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()[0])
            click_only["archived_analog_events"] = sum(event.get("type") in {"range", "dial"} for event in archived.get("events") or [])
            click_only["archived_tree_events"] = sum(event.get("type") in {"branch", "circuit"} for event in archived.get("events") or [])
            click_only["direct_grade"] = load_module(GRADER, "cockpit_click_only_grader").grade(archived, initial_truth, initial_state)
            if click_only["archived_analog_events"] != 0 or click_only["direct_grade"].get("passed") is not False:
                raise AssertionError(f"stationary click-only shortcut was accepted: {click_only}")
            write_json(output / "click_only_full_rejection.json", click_only)
            page.screenshot(path=str(screenshots / "baseline-full-click-only-rejected-fresh.png"), full_page=True)
        failure_checked = True
        if level == 2 and interaction == "full" and time_mode == "live":
            page.screenshot(path=str(screenshots / "baseline-full-failure-fresh.png"), full_page=True)
        visible_surface_solve = None
        if level == 5:
            visible_surface_solve = solver.solve_visible_surface(page, interaction, certify=False)
        else:
            solver.solve(page, state_dir, output, MECHANIC, certify=False)
        solved_surface = normal_surface_check(page, "solved-before-certification")
        surface_checks.append(solved_surface)
        if solved_surface["certify_background"] != initial_certify_background:
            raise AssertionError("certify button styling disclosed all-correct state before submission")
        if level == 5 and time_mode == "live":
            page.screenshot(path=str(screenshots / f"d5-{interaction}-solved-before-certify.png"), full_page=True)
        page.locator("#cpf-certify").click()
        expect(page.locator('.cpf-verdict.is-pass')).to_be_visible(timeout=8_000)
        expect(page.locator(".readout")).to_have_attribute("data-status", "passed")
        surface_checks.append(normal_surface_check(page, "pass"))
        if level == 2 and time_mode == "live":
            page.screenshot(path=str(screenshots / f"baseline-{interaction}-pass.png"), full_page=True)
        if level == 5 and time_mode == "live":
            page.screenshot(path=str(screenshots / f"d5-{interaction}-pass.png"), full_page=True)
        if time_mode == "paused":
            page.evaluate("() => WeirdCaptchaTime.pause()")
        export, export_command = exported(state_dir, output, label)
        direct = load_module(GRADER, f"cockpit_grader_{label.replace('-', '_')}").grade(export["result"], export["ground_truth"], export["public_state"])
        export_path = output / export_command["artifact"]
        verifier = verify_export(export_path, label)
        server_grade = export["result"].get("server_grade") or {}
        if not all(result.get("passed") is True for result in (server_grade, direct, verifier)):
            raise AssertionError(f"grade mismatch server={server_grade} direct={direct} verifier={verifier}")
        if errors:
            raise AssertionError(f"browser console errors: {errors}")
        record = {
            "label": label,
            "headless": True,
            "fresh_profile": str(profile.relative_to(temporary)),
            "loopback_origin": f"http://127.0.0.1:{port}",
            "difficulty": level,
            "interaction": interaction,
            "time_mode": time_mode,
            "world_fingerprint": world_fingerprint(initial_state),
            "visible_observation": observation,
            "normal_surface_checks": surface_checks,
            "dial_tick_geometry": tick_geometry,
            "visible_surface_solve": visible_surface_solve,
            "model_observation_frame": model_frame,
            "model_delay_task_time_delta_ms": delay_delta,
            "failure_fresh_retry_checked": failure_checked,
            "stationary_click_only_attempt": click_only,
            "initial_challenge_id": initial_state["challenge_id"],
            "retry_challenge_id": refreshed["challenge_id"],
            "graded_failures": export["graded_failures"],
            "export_command": export_command,
            "server_grade": server_grade,
            "direct_grade": direct,
            "verifier": verifier,
            "result": export,
        }
        write_json(output / "matrix" / f"{label}.json", record)
        return record
    finally:
        context.close()
        stop_server(process)


def capture_negative_contract(output: Path) -> dict:
    exported_payload = read_json(output / "exports/d2-full-live.json")
    payload = exported_payload["result"]
    truth = exported_payload["ground_truth"]
    public = exported_payload["public_state"]
    grader = load_module(GRADER, "cockpit_negative_contract_grader")
    cases: dict[str, dict] = {}

    wrong_surface = copy.deepcopy(payload)
    wrong_surface["events"][0]["input_source"] = "range_step_button"
    cases["wrong_interaction_surface"] = grader.grade(wrong_surface, truth, public)

    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "cpf-stale-evidence"
    cases["stale_challenge"] = grader.grade(stale, truth, public)

    wrong_geometry = copy.deepcopy(payload)
    geometry_event = next(event for event in wrong_geometry["events"] if "pointer_fraction" in event)
    geometry_event["pointer_fraction"] = 0.0 if geometry_event["pointer_fraction"] != 0.0 else 1.0
    cases["tampered_pointer_geometry"] = grader.grade(wrong_geometry, truth, public)

    stationary = copy.deepcopy(payload)
    gesture_event = next(event for event in stationary["events"] if event.get("gesture"))
    gesture_event["gesture"]["travel_px"] = 0
    gesture_event["gesture"]["sample_count"] = 1
    cases["stationary_click_mislabeled_as_drag"] = grader.grade(stationary, truth, public)

    forged_bus = copy.deepcopy(payload)
    bus_event = next(event for event in forged_bus["events"] if event.get("effects"))
    bus_event["effects"][0]["after"] += 1
    cases["forged_calibration_bus_effect"] = grader.grade(forged_bus, truth, public)

    wrong_final = copy.deepcopy(payload)
    first_range = public["panel"]["ranges"][0]
    wrong_final["final_state"][first_range["id"]]["low"] += first_range["step"]
    cases["final_state_not_bound_to_transcript"] = grader.grade(wrong_final, truth, public)

    record = {
        "all_rejected": all(item.get("passed") is False for item in cases.values()),
        "source_export": "exports/d2-full-live.json",
        "cases": cases,
    }
    write_json(output / "negative_contract.json", record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=ENVIRONMENT / "evidence_docs")
    args = parser.parse_args()
    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    records = []
    started = time.time()
    with tempfile.TemporaryDirectory(prefix="cockpit-preflight-isolated-") as temp_name, sync_playwright() as playwright:
        temporary = Path(temp_name)
        for level in range(1, 6):
            for interaction in ("simplified", "full"):
                for time_mode in ("live", "paused"):
                    records.append(capture_condition(playwright, temporary=temporary, output=output, level=level, interaction=interaction, time_mode=time_mode))
    pairs = {}
    for level in range(1, 6):
        for time_mode in ("live", "paused"):
            selected = [item for item in records if item["difficulty"] == level and item["time_mode"] == time_mode]
            pairs[f"d{level}-{time_mode}"] = {
                "same_world": selected[0]["world_fingerprint"] == selected[1]["world_fingerprint"],
                "simplified": selected[0]["world_fingerprint"],
                "full": selected[1]["world_fingerprint"],
            }
    baseline_live = next(item for item in records if item["difficulty"] == 2 and item["interaction"] == "full" and item["time_mode"] == "live")
    baseline_paused = next(item for item in records if item["difficulty"] == 2 and item["interaction"] == "full" and item["time_mode"] == "paused")
    negative_contract = capture_negative_contract(output)
    surface_quality = {
        "normal_task_url": True,
        "conditions_checked": len(records),
        "phases_checked": sum(len(item["normal_surface_checks"]) for item in records),
        "all_checks_passed": all(check["passed"] for item in records for check in item["normal_surface_checks"]),
        "certify_style_unchanged_when_solved": all(
            next(check for check in item["normal_surface_checks"] if check["phase"] == "initial")["certify_background"]
            == next(check for check in item["normal_surface_checks"] if check["phase"] == "solved-before-certification")["certify_background"]
            for item in records
        ),
        "forbidden_feedback": [
            "EXACT CHANNELS",
            "CALIBRATION LINKS TRACED",
            "PROBE THE FIRST VISIBLE TARGET",
            "TARGET RELEASED",
            "MOVED / TARGET LOCKED",
            "FRESH PANEL ISSUED",
            "FRESH CARD ISSUED",
            "PREFLIGHT VECTOR CERTIFIED",
        ],
    }
    write_json(output / "normal_surface_quality_gate.json", surface_quality)
    d5_tick_geometry = {
        "same_300_degree_mapping_as_pointer_input": True,
        "conditions_checked": 4,
        "all_passed": all(item["dial_tick_geometry"]["all_passed"] for item in records if item["difficulty"] == 5),
        "records": {
            item["label"]: item["dial_tick_geometry"]
            for item in records if item["difficulty"] == 5
        },
    }
    write_json(output / "d5_dial_tick_geometry.json", d5_tick_geometry)
    summary = {
        "ok": (
            len(records) == 20
            and all(item["server_grade"].get("passed") for item in records)
            and all(item["direct_grade"].get("passed") for item in records)
            and all(item["verifier"].get("passed") for item in records)
            and all(item["failure_fresh_retry_checked"] for item in records)
            and all(item["graded_failures"] == 1 for item in records)
            and all(item["export_command"]["returncode"] == 0 for item in records)
            and negative_contract["all_rejected"]
            and surface_quality["all_checks_passed"]
            and surface_quality["certify_style_unchanged_when_solved"]
            and d5_tick_geometry["all_passed"]
        ),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": round(time.time() - started, 3),
        "browser_isolation": {"headless": True, "fresh_persistent_profile_per_run": True, "loopback_only": True, "existing_profile_reused": False},
        "conditions": len(records),
        "same_world_pairs": pairs,
        "baseline_live_paused_visible_observation_equal": baseline_live["visible_observation"] == baseline_paused["visible_observation"],
        "failure_and_retry": {
            "conditions_checked": sum(item["failure_fresh_retry_checked"] for item in records),
            "all_fresh_challenges": all(item["initial_challenge_id"] != item["retry_challenge_id"] for item in records),
            "graded_failures_per_condition": sorted({item["graded_failures"] for item in records}),
            "all_recovery_passed": all(item["server_grade"]["passed"] is True for item in records),
        },
        "export": {
            "conditions_checked": sum(item["export_command"]["returncode"] == 0 for item in records),
            "exact_shared_exporter": "weird_captcha_gym/shared_scripts/export_result.sh",
            "all_exported_verifiers_passed": all(item["verifier"]["passed"] is True for item in records),
        },
        "model_observations": {
            "live": baseline_live["model_observation_frame"],
            "paused": baseline_paused["model_observation_frame"],
        },
        "negative_contract": negative_contract,
        "normal_surface_quality_gate": surface_quality,
        "d5_dial_tick_geometry": {
            "artifact": "d5_dial_tick_geometry.json",
            "conditions_checked": d5_tick_geometry["conditions_checked"],
            "all_passed": d5_tick_geometry["all_passed"],
        },
        "records": [{key: item[key] for key in ("label", "world_fingerprint", "model_delay_task_time_delta_ms", "graded_failures", "failure_fresh_retry_checked")} for item in records],
    }
    write_json(output / "validation_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["ok"] or not all(pair["same_world"] for pair in pairs.values()) or not summary["baseline_live_paused_visible_observation_equal"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
