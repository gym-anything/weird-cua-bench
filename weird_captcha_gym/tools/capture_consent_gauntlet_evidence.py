#!/usr/bin/env python3
"""Capture isolated headless evidence for Consent Gauntlet.

Every condition uses a fresh temporary persistent Chromium profile, headless
mode, and a loopback-only server. The script never attaches to an existing
browser, profile, desktop, mouse, keyboard, or foreground application.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
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
ENVIRONMENT = BENCHMARK / "environments/consent_gauntlet_env"
MECHANIC = "consent_gauntlet"
BASE_TASK = ENVIRONMENT / "tasks/consent_gauntlet_seed_0001/task.json"
CONTROLS = ENVIRONMENT / "controls.json"
SETUP = BENCHMARK / "shared_scripts/setup_task.py"
EXPORT = BENCHMARK / "shared_scripts/export_result.sh"
SERVER = BENCHMARK / "shared_runtime/server/weird_captcha_server.py"
APP = BENCHMARK / "shared_runtime/app"
GRADER = BENCHMARK / "shared_runtime/server/incubator_graders/consent_gauntlet.py"
SOLVER = BENCHMARK / "tools/incubator_solvers/consent_gauntlet.py"
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
    task["natural_language"] = controls["difficulty"][str(level)]["natural_language"]
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
        env={**os.environ, "WEIRD_CAPTCHA_CHALLENGE_SEED": seed, "WEIRD_CAPTCHA_CHEAT_PASSWORD": "consent-evidence-only"},
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
    value = {"surface": state["surface"], "parameters": state["parameters"]}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def export_result(state_dir: Path, output: Path, label: str) -> tuple[dict, dict]:
    completed = subprocess.run(
        ["bash", str(EXPORT)], cwd=ROOT,
        env={**os.environ, "WEIRD_CAPTCHA_STATE_DIR": str(state_dir)},
        check=True, text=True, capture_output=True,
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
    verifier = load_module(VERIFIER, f"consent_verifier_{label.replace('-', '_')}")

    def copy_from_env(source: str, destination: str) -> None:
        if source != "/tmp/task_result.json":
            raise AssertionError(f"unexpected verifier source {source}")
        shutil.copyfile(export_path, destination)

    return verifier.verify_task(env_info={"copy_from_env": copy_from_env})


def option_centers(page) -> list[list[float]]:
    centers = []
    for node in page.locator(".consent-orbit-card").all():
        box = node.bounding_box()
        if box is None:
            raise AssertionError("moving option has no visible box")
        centers.append([round(box["x"] + box["width"] / 2, 3), round(box["y"] + box["height"] / 2, 3)])
    return centers


def max_center_delta(first: list[list[float]], second: list[list[float]]) -> float:
    return max((((ax - bx) ** 2 + (ay - by) ** 2) ** .5 for (ax, ay), (bx, by) in zip(first, second)), default=0.0)


def capture_direct_browser_clock_frames(page, output: Path, mode: str) -> dict:
    """Capture the page clock directly; this is not an evaluator observation."""
    frame_dir = output / "direct_browser_clock_frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    centers = []
    for index in range(5):
        path = frame_dir / f"baseline-full-{mode}-frame-{index:03d}.png"
        page.screenshot(path=str(path))
        data = path.read_bytes()
        frames.append({
            "index": index,
            "offset_ms": index * 180,
            "path": str(path.relative_to(output)),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        })
        centers.append(option_centers(page))
        if index < 4:
            page.wait_for_timeout(180)
    screen = frames[-1]
    return {
        "time_mode": mode,
        "capture_span_ms": 720,
        "direct_page_screenshot_count": 5,
        "frames": frames,
        "screen": screen["path"],
        "screen_sha256": screen["sha256"],
        "screen_is_final_captured_frame": screen == frames[-1],
        "maximum_option_motion_px": max(max_center_delta(centers[0], item) for item in centers[1:]),
        "evidence_boundary": "Direct isolated-browser shared-clock capture; these files were not delivered to a model or evaluator.",
    }


def visible_surface_copy_check(page, label: str) -> dict:
    text = page.locator(".consent-gauntlet").inner_text().upper()
    answer_leak_phrases = (
        "CORRECT ANSWER",
        "PURPOSES BLOCKED",
        "REMAINING CORRECT",
        "TARGET VALUE",
        "NEXT CORRECT ACTION",
        "ALL ANSWERS CORRECT",
    )
    tutorial_rule_phrases = (
        "NEGATIVE WORDING MAY REQUIRE YES",
        "PROVIDER RESET CONTROLS RESTORE",
        "CHANGES FROM A LINKED ROW",
        "COLOUR AND SIZE ARE DECORATION",
        "NO COLOUR OR SIZE IS A PRIVACY SIGNAL",
        "THE NUMBERED CHOICES MATCH THE MOVING PACKET",
        "WATCH THE VISIBLE DIRECTED SWITCH LINK",
        "CHANGING ITS SOURCE FLIPS",
        "ACCOUNT FOR BOTH VISIBLE DIRECTED SWITCH LINKS",
        "AVOID THE PROVIDER-RESET CONTROLS",
    )
    answer_leaks = [item for item in answer_leak_phrases if item in text]
    tutorial_rules = [item for item in tutorial_rule_phrases if item in text]
    cheat_visible = page.locator(".cheat-panel:visible, [data-cheat-panel]:visible").count()
    return {
        "label": label,
        "answer_leak_phrases": answer_leaks,
        "tutorial_rule_phrases": tutorial_rules,
        "cheat_panel_visible": bool(cheat_visible),
        "passed": not answer_leaks and not tutorial_rules and not cheat_visible,
    }


def review_style(page) -> dict | None:
    button = page.locator("#consent-review")
    if not button.count() or not button.is_visible():
        return None
    return button.evaluate(
        """node => {
          const style = getComputedStyle(node);
          return {
            color: style.color,
            backgroundColor: style.backgroundColor,
            borderColor: style.borderColor,
            boxShadow: style.boxShadow,
            opacity: style.opacity,
          };
        }"""
    )


def option_geometry(page) -> dict:
    viewport = page.viewport_size or {"width": 1440, "height": 900}
    boxes = []
    for node in page.locator(".consent-orbit-card").all():
        box = node.bounding_box()
        if box is None:
            raise AssertionError("gateway option has no visible bounds")
        boxes.append({key: round(float(box[key]), 3) for key in ("x", "y", "width", "height")})
    contained = all(
        box["x"] >= -0.5
        and box["y"] >= 91.5
        and box["x"] + box["width"] <= viewport["width"] + 0.5
        and box["y"] + box["height"] <= viewport["height"] - 55.5
        for box in boxes
    )
    overlaps = []
    for first_index, first in enumerate(boxes):
        for second_index, second in enumerate(boxes[first_index + 1 :], first_index + 1):
            width = min(first["x"] + first["width"], second["x"] + second["width"]) - max(first["x"], second["x"])
            height = min(first["y"] + first["height"], second["y"] + second["height"]) - max(first["y"], second["y"])
            if width > 1 and height > 1:
                overlaps.append({"first": first_index, "second": second_index, "width": round(width, 3), "height": round(height, 3)})
    return {"viewport": viewport, "card_bounds": boxes, "contained": contained, "overlaps": overlaps}


def active_before_failure(page, solver, interaction: str, state: dict, screenshots: Path, label: str) -> tuple[dict, dict | None]:
    solver._click_option(page, interaction, "manage")
    expect(page.locator(".consent-ledger")).to_be_visible()
    if state["surface"].get("links"):
        source_id = state["surface"]["links"][0]["source_id"]
        purpose = next(item for item in state["surface"]["purposes"] if item["id"] == source_id)
        drawer = next(item for item in state["surface"]["drawers"] if item["id"] == purpose["drawer_id"])
        solver._open_drawer(page, interaction, drawer)
    page.screenshot(path=str(screenshots / f"{label}-active.png"))
    if state["parameters"]["purpose_count"] == 6:
        page.screenshot(path=str(screenshots / f"baseline-{interaction}-active.png"))
    surface = visible_surface_copy_check(page, f"{label}-active")
    style = review_style(page)
    page.locator("#consent-review").click()
    solver._click_option(page, interaction, "commit")
    return surface, style


def stationary_switch_attempt(page) -> dict:
    rail = page.locator("[data-purpose-switch]").first
    before = rail.get_attribute("aria-checked")
    box = rail.bounding_box()
    if box is None:
        raise AssertionError("switch rail not visible")
    x = box["x"] + box["width"] * (0.82 if before == "true" else 0.18)
    y = box["y"] + box["height"] / 2
    page.mouse.click(x, y)
    after = page.locator("[data-purpose-switch]").first.get_attribute("aria-checked")
    if after != before:
        raise AssertionError("stationary click changed a full switch")
    return {"before": before, "after": after, "changed": False, "click": [round(x, 3), round(y, 3)]}


def capture_condition(playwright, temporary: Path, output: Path, level: int, interaction: str, mode: str) -> dict:
    label = f"d{level}-{interaction}-{mode}"
    state_dir = temporary / "states" / label
    state_dir.mkdir(parents=True)
    task = condition_task(temporary, level, interaction, mode)
    seed = f"consent-visible-d{level}"
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
    solver = load_module(SOLVER, f"consent_solver_{label.replace('-', '_')}")
    try:
        page.goto(f"http://127.0.0.1:{port}/?time_mode={mode}&start_paused=1", wait_until="networkidle")
        expect(page.locator(".consent-gauntlet")).to_be_visible(timeout=8_000)
        classes = (page.locator(".consent-gauntlet").get_attribute("class") or "").split()
        if f"mode-{interaction}" not in classes:
            raise AssertionError(f"rendered interaction class mismatch: {classes}")
        initial_state = read_json(state_dir / "public_state.json")
        page.screenshot(path=str(screenshots / f"{label}-initial.png"))
        surface_checks = [visible_surface_copy_check(page, f"{label}-initial")]
        geometry = option_geometry(page)
        if not geometry["contained"] or geometry["overlaps"]:
            raise AssertionError(f"gateway cards overlap or leave the benchmark viewport: {geometry}")

        before = page.evaluate("() => WeirdCaptchaTime.status()")
        timer_before = page.locator("[data-packet-time]").inner_text()
        centers_before = option_centers(page)
        if mode == "live":
            page.evaluate("() => WeirdCaptchaTime.resume()")
        page.wait_for_timeout(420)
        after = page.evaluate("() => WeirdCaptchaTime.status()")
        timer_after = page.locator("[data-packet-time]").inner_text()
        centers_after = option_centers(page)
        delay_delta = float(after["task_time_ms"]) - float(before["task_time_ms"])
        option_delta = max_center_delta(centers_before, centers_after)
        if mode == "live" and delay_delta < 300:
            raise AssertionError(f"live task time did not advance: {delay_delta}")
        if mode == "paused" and abs(delay_delta) > 2:
            raise AssertionError(f"paused task time advanced: {delay_delta}")
        if initial_state["parameters"]["moving_gateways"] and mode == "live" and option_delta < 8:
            raise AssertionError(f"moving live gateway did not move visibly: {option_delta}")
        if mode == "paused" and option_delta > 1:
            raise AssertionError(f"paused gateway moved: {option_delta}")
        if mode == "paused" and timer_after != timer_before:
            raise AssertionError(f"paused packet timer advanced: {timer_before} -> {timer_after}")
        if mode == "live" and timer_after == timer_before:
            raise AssertionError("live packet timer did not visibly advance")

        observation = None
        if level == 3 and interaction == "full":
            observation = capture_direct_browser_clock_frames(page, output, mode)
            if mode == "live" and observation["maximum_option_motion_px"] < 12:
                raise AssertionError("live observation frames do not show gateway motion")
            if mode == "paused" and observation["maximum_option_motion_px"] > 1:
                raise AssertionError("paused observation frames are not frozen")

        action_before = page.evaluate("() => WeirdCaptchaTime.status().task_time_ms")
        stationary = None
        active_style = None
        if level == 3 or (level in {4, 5} and mode == "live"):
            active_check, active_style = active_before_failure(page, solver, interaction, initial_state, screenshots, label)
            surface_checks.append(active_check)
            if interaction == "full" and mode == "paused":
                # The active baseline capture above already issued the incomplete
                # final action. The stationary switch check is performed after
                # the fresh packet loads below.
                stationary = {"deferred_until_fresh_packet": True}
        else:
            solver.fail_once(page, state_dir, output, MECHANIC)
        expect(page.locator(".consent-verdict.is-fail")).to_be_visible(timeout=8_000)
        action_after = page.evaluate("() => WeirdCaptchaTime.status().task_time_ms")
        if mode == "paused" and abs(float(action_after) - float(action_before)) > 2:
            raise AssertionError("paused native action advanced task time")
        retry_state = read_json(state_dir / "public_state.json")
        if retry_state["challenge_id"] == initial_state["challenge_id"]:
            raise AssertionError("failed submission did not produce a fresh challenge")
        page.screenshot(path=str(screenshots / f"{label}-failure-fresh.png"))
        surface_checks.append(visible_surface_copy_check(page, f"{label}-failure-fresh"))

        if stationary is not None:
            solver._click_option(page, interaction, "manage")
            stationary.update(stationary_switch_attempt(page))
            page.locator("#consent-review").click()
            solver._click_option(page, interaction, "commit")
            expect(page.locator(".consent-verdict.is-fail")).to_be_visible(timeout=8_000)
            retry_state = read_json(state_dir / "public_state.json")

        solver.prepare_solution(page, state_dir, output, MECHANIC)
        solved_style = review_style(page)
        surface_checks.append(visible_surface_copy_check(page, f"{label}-solved-ledger"))
        if active_style is not None and solved_style != active_style:
            raise AssertionError("review control visually reveals that every purpose is correct")
        if level in {3, 5} and mode == "live":
            page.screenshot(path=str(screenshots / f"{label}-solved-ledger.png"))
        page.locator("#consent-review").click()
        surface_checks.append(visible_surface_copy_check(page, f"{label}-final-before-commit"))
        if level in {3, 5} and mode == "live":
            page.screenshot(path=str(screenshots / f"{label}-final-before-commit.png"))
        solver._click_option(page, interaction, "commit")
        expect(page.locator(".consent-verdict.is-pass")).to_be_visible(timeout=8_000)
        expect(page.locator(".consent-footer .readout")).to_have_attribute("data-status", "passed")
        page.screenshot(path=str(screenshots / f"{label}-pass.png"))
        surface_checks.append(visible_surface_copy_check(page, f"{label}-pass"))

        exported, command = export_result(state_dir, output, label)
        direct = load_module(GRADER, f"consent_grader_{label.replace('-', '_')}").grade(exported["result"], exported["ground_truth"], exported["public_state"])
        verifier = verify_export(output / command["artifact"], label)
        server_grade = exported["result"].get("server_grade") or {}
        if not all(item.get("passed") is True for item in (server_grade, direct, verifier)):
            raise AssertionError(f"grade disagreement: server={server_grade} direct={direct} verifier={verifier}")
        if errors:
            raise AssertionError(f"browser console errors: {errors}")
        record = {
            "label": label,
            "headless": True,
            "fresh_profile": str(profile.relative_to(temporary)),
            "loopback_origin": f"http://127.0.0.1:{port}",
            "difficulty": level,
            "interaction": interaction,
            "time_mode": mode,
            "world_fingerprint": world_fingerprint(initial_state),
            "initial_challenge_id": initial_state["challenge_id"],
            "retry_challenge_id": retry_state["challenge_id"],
            "model_delay_task_time_delta_ms": round(delay_delta, 3),
            "packet_timer_before_delay": timer_before,
            "packet_timer_after_delay": timer_after,
            "option_motion_during_delay_px": round(option_delta, 3),
            "paused_action_task_time_delta_ms": round(float(action_after) - float(action_before), 3),
            "direct_browser_clock_capture": observation,
            "stationary_switch_attempt": stationary,
            "gateway_geometry": geometry,
            "visible_surface_copy_checks": surface_checks,
            "review_style_unchanged_when_solved": active_style is None or solved_style == active_style,
            "failure_fresh_retry_checked": True,
            "graded_failures": exported.get("graded_failures"),
            "export_command": command,
            "server_grade": server_grade,
            "direct_grade": direct,
            "verifier": verifier,
        }
        write_json(output / "matrix" / f"{label}.json", record)
        return record
    finally:
        context.close()
        stop_server(process)


def reset_recovery(playwright, temporary: Path, output: Path) -> dict:
    """Exercise the misleading provider reset, then recover on the same packet."""
    label = "baseline-full-reset-recovery"
    state_dir = temporary / "states" / label
    state_dir.mkdir(parents=True)
    task = condition_task(temporary, 3, "full", "live")
    process, port = start_server(task, state_dir, "consent-reset-recovery")
    profile = temporary / "fresh-profiles" / label
    screenshots = output / "screenshots"
    context = playwright.chromium.launch_persistent_context(
        str(profile), headless=True, viewport={"width": 1440, "height": 900}, device_scale_factor=1,
    )
    page = context.pages[0]
    errors: list[str] = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    solver = load_module(SOLVER, "consent_solver_reset_recovery")
    try:
        page.goto(f"http://127.0.0.1:{port}/?time_mode=live", wait_until="networkidle")
        expect(page.locator(".consent-gauntlet.mode-full")).to_be_visible(timeout=8_000)
        state = read_json(state_dir / "public_state.json")
        solver._click_option(page, "full", "manage")
        trap = state["surface"]["reset_traps"][0]
        drawer = next(item for item in state["surface"]["drawers"] if item["id"] == trap["drawer_id"])
        solver._open_drawer(page, "full", drawer)
        purpose = next(item for item in state["surface"]["purposes"] if item["id"] == drawer["purpose_ids"][0])
        initial = bool(purpose["initial_state"])
        solver._set_purpose(page, "full", purpose["id"], not initial)
        changed = solver._current(page, purpose["id"])
        if changed == initial:
            raise AssertionError("edge-case setup did not change the reset target")
        page.screenshot(path=str(screenshots / f"{label}-before-reset.png"))

        rail = page.locator(f'[data-reset-slider="{trap["id"]}"]')
        box = rail.bounding_box()
        if box is None:
            raise AssertionError("provider reset drag rail is not visible")
        y = box["y"] + box["height"] / 2
        start = box["x"] + box["width"] * .18
        end = box["x"] + box["width"] * .82
        page.mouse.move(start, y)
        page.mouse.down()
        page.mouse.move(end, y, steps=7)
        page.mouse.up()
        expect(page.locator(f'[data-purpose-switch="{purpose["id"]}"]')).to_have_attribute(
            "aria-checked", str(initial).lower(), timeout=2_000,
        )
        after_reset = solver._current(page, purpose["id"])
        page.screenshot(path=str(screenshots / f"{label}-after-reset.png"))

        solver.solve_open_ledger(page, state_dir, output, MECHANIC)
        expect(page.locator(".consent-verdict.is-pass")).to_be_visible(timeout=8_000)
        page.screenshot(path=str(screenshots / f"{label}-pass.png"))
        exported, command = export_result(state_dir, output, label)
        direct = load_module(GRADER, "consent_grader_reset_recovery").grade(
            exported["result"], exported["ground_truth"], exported["public_state"],
        )
        verifier = verify_export(output / command["artifact"], label)
        server_grade = exported["result"].get("server_grade") or {}
        trap_events = [item for item in exported["result"]["events"] if item["type"] == "trap"]
        if not trap_events or trap_events[0].get("input_source") != "trap_slider":
            raise AssertionError("reset edge case did not export a physical trap-slider event")
        if not all(item.get("passed") is True for item in (server_grade, direct, verifier)):
            raise AssertionError("reset recovery grade disagreement")
        if errors:
            raise AssertionError(f"browser console errors: {errors}")
        result = {
            "ok": True,
            "headless": True,
            "fresh_persistent_profile": True,
            "loopback_only": True,
            "challenge_id": state["challenge_id"],
            "world_fingerprint": world_fingerprint(state),
            "changed_purpose": purpose["id"],
            "initial_state": initial,
            "state_before_reset": changed,
            "state_after_reset": after_reset,
            "trap_event": trap_events[0],
            "server_grade": server_grade,
            "direct_grade": direct,
            "verifier": verifier,
            "console_errors": errors,
        }
        write_json(output / "reset_recovery.json", result)
        return result
    finally:
        context.close()
        stop_server(process)


def negative_contract(output: Path) -> dict:
    exported = read_json(output / "exports/d4-full-live.json")
    payload = exported["result"]
    truth = exported["ground_truth"]
    public = exported["public_state"]
    grader = load_module(GRADER, "consent_negative_evidence")
    cases = {}

    wrong_surface = copy.deepcopy(payload)
    wrong_surface["events"][0]["input_source"] = "option_proxy"
    cases["wrong_interaction_surface"] = grader.grade(wrong_surface, truth, public)

    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "cgt-stale-evidence"
    cases["stale_challenge"] = grader.grade(stale, truth, public)

    stationary = copy.deepcopy(payload)
    switch = next(item for item in stationary["events"] if item["type"] == "purpose")
    switch["gesture"]["travel_px"] = 0
    switch["gesture"]["sample_count"] = 1
    cases["stationary_click_mislabeled_as_drag"] = grader.grade(stationary, truth, public)

    forged = copy.deepcopy(payload)
    linked = next(item for item in forged["events"] if item.get("effects"))
    linked["effects"][0]["after"] = not linked["effects"][0]["after"]
    cases["forged_link_effect"] = grader.grade(forged, truth, public)

    final = copy.deepcopy(payload)
    purpose_id = next(iter(final["final_state"]["purpose_states"]))
    final["final_state"]["purpose_states"][purpose_id] = not final["final_state"]["purpose_states"][purpose_id]
    cases["forged_final_state"] = grader.grade(final, truth, public)

    geometry = copy.deepcopy(payload)
    gateway = next(item for item in geometry["events"] if item["type"] == "gateway")
    gateway["card_center_x_norm"] = min(0.99, gateway["card_center_x_norm"] + 0.15)
    cases["forged_gateway_geometry"] = grader.grade(geometry, truth, public)

    phase = copy.deepcopy(payload)
    gateway = next(item for item in phase["events"] if item["type"] == "gateway")
    gateway["phase_deg"] += 20
    cases["forged_gateway_phase"] = grader.grade(phase, truth, public)

    time_order = copy.deepcopy(payload)
    time_order["events"][1]["task_time_ms"] = -1
    cases["forged_task_time_order"] = grader.grade(time_order, truth, public)
    result = {"all_rejected": all(item.get("passed") is False for item in cases.values()), "cases": cases}
    write_json(output / "negative_contract.json", result)
    return result


def main() -> None:
    output = ENVIRONMENT / "evidence_docs"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="consent-gauntlet-headless-") as raw:
        temporary = Path(raw)
        records = []
        with sync_playwright() as playwright:
            for level in range(1, 6):
                for interaction in ("simplified", "full"):
                    for mode in ("live", "paused"):
                        records.append(capture_condition(playwright, temporary, output, level, interaction, mode))
            reset = reset_recovery(playwright, temporary, output)

    same_world = {}
    for level in range(1, 6):
        for mode in ("live", "paused"):
            selected = [item for item in records if item["difficulty"] == level and item["time_mode"] == mode]
            same_world[f"d{level}-{mode}"] = {
                item["interaction"]: item["world_fingerprint"] for item in selected
            }
            same_world[f"d{level}-{mode}"]["same_world"] = len({item["world_fingerprint"] for item in selected}) == 1
    negative = negative_contract(output)
    surface_checks = [check for item in records for check in item["visible_surface_copy_checks"]]
    surface_quality = {
        "ok": bool(surface_checks)
        and all(check["passed"] for check in surface_checks)
        and all(item["review_style_unchanged_when_solved"] for item in records),
        "checks": len(surface_checks),
        "visible_copy_failures": [check for check in surface_checks if not check["passed"]],
        "review_style_unchanged_when_solved": all(item["review_style_unchanged_when_solved"] for item in records),
        "evidence_boundary": "Automated answer-leak, tutorial-copy, cheat-panel, and solved-style regression; human affordance inference remains a separate gate.",
    }
    write_json(output / "visible_surface_copy_gate.json", surface_quality)
    summary = {
        "ok": len(records) == 20 and all(item["server_grade"]["passed"] and item["direct_grade"]["passed"] and item["verifier"]["passed"] for item in records) and all(item["same_world"] for item in same_world.values()) and negative["all_rejected"] and surface_quality["ok"] and reset["ok"],
        "isolation": {"headless": True, "fresh_persistent_profile_per_condition": True, "loopback_only": True, "existing_profile_used": False, "foreground_browser_used": False},
        "conditions_checked": len(records),
        "all_failure_recovery_passed": all(item["failure_fresh_retry_checked"] for item in records),
        "same_world_pairs": same_world,
        "records": records,
        "negative_contract": negative,
        "visible_surface_copy_gate": surface_quality,
        "reset_recovery": reset,
    }
    write_json(output / "validation_summary.json", summary)
    print(json.dumps({"ok": summary["ok"], "conditions_checked": len(records), "evidence": str(output)}, sort_keys=True))


if __name__ == "__main__":
    main()
