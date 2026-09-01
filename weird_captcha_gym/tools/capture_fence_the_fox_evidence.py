#!/usr/bin/env python3
"""Capture Fence the Fox's controlled matrix in isolated headless Chromium.

Each condition uses a loopback-only puzzle server and a new temporary
persistent Chromium profile. The script never attaches to a running browser,
an existing profile, or a foreground application.
"""
from __future__ import annotations

import argparse
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
ENVIRONMENT = BENCHMARK / "environments" / "fence_the_fox_env"
EVIDENCE = ENVIRONMENT / "evidence_docs"
MECHANIC = "fence_the_fox"
BASE_TASK = ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json"
CONTROLS = ENVIRONMENT / "controls.json"
SETUP = BENCHMARK / "shared_scripts" / "setup_task.py"
EXPORT = BENCHMARK / "shared_scripts" / "export_result.sh"
SERVER = BENCHMARK / "shared_runtime" / "server" / "weird_captcha_server.py"
APP = BENCHMARK / "shared_runtime" / "app"
GRADER = BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py"
SOLVER = BENCHMARK / "tools" / "incubator_solvers" / f"{MECHANIC}.py"
VERIFIER = BASE_TASK.parent / "verifier.py"
VIEWPORT = {"width": 1440, "height": 900}


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
    profile = controls["difficulty"][str(level)]
    task["difficulty"] = profile["label"]
    task["natural_language"] = profile["natural_language"]
    task["metadata"]["control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": mode,
        "difficulty_parameters": copy.deepcopy(profile["parameters"]),
    }
    suffix = "_tpaused" if mode == "paused" else ""
    task["id"] = f"{MECHANIC}_d{level}_{interaction}_seed_0001{suffix}@0.1"
    path = temporary / "tasks" / f"d{level}-{interaction}-{mode}.json"
    write_json(path, task)
    return path


def start_server(task: Path, state_dir: Path, seed: str) -> tuple[subprocess.Popen[bytes], int]:
    subprocess.run(
        ["python", "-B", str(SETUP), "--task-json", str(task), "--state-dir", str(state_dir), "--seed", seed],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    port = reserve_port()
    process = subprocess.Popen(
        ["python", "-B", str(SERVER), "--host", "127.0.0.1", "--port", str(port), "--app-dir", str(APP), "--state-dir", str(state_dir)],
        cwd=ROOT,
        env={**os.environ, "WEIRD_CAPTCHA_CHALLENGE_SEED": seed, "WEIRD_CAPTCHA_CHEAT_PASSWORD": "fox-evidence-only"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 10
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
    content = {
        "radius": state["radius"],
        "cells": state["cells"],
        "fox_start": state["fox_start"],
        "initial_fences": state["initial_fences"],
        "stake_budget": state["stake_budget"],
        "wind_start": state["wind_start"],
        "runtime_wind_sequence": state["runtime_wind_sequence"],
        "runtime_driver_patterns": state["runtime_driver_patterns"],
        "parameters": state["parameters"],
        "palette": state["palette"],
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exported(state_dir: Path, output: Path, label: str) -> tuple[dict, dict]:
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
    path = output / "exports" / f"{label}.json"
    write_json(path, payload)
    return payload, {
        "command": ["bash", "weird_captcha_gym/shared_scripts/export_result.sh"],
        "environment": {"WEIRD_CAPTCHA_STATE_DIR": "<isolated-condition-state-dir>"},
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "artifact": str(path.relative_to(output)),
        "artifact_sha256": sha256(path),
    }


def verify_export(export_path: Path, label: str) -> dict:
    verifier = load_module(VERIFIER, f"fox_verifier_{label.replace('-', '_')}")

    def copy_from_env(source: str, destination: str) -> None:
        if source != "/tmp/task_result.json":
            raise AssertionError(f"unexpected verifier source {source}")
        shutil.copyfile(export_path, destination)

    return verifier.verify_task(env_info={"copy_from_env": copy_from_env})


def surface_contract(page, phase: str) -> dict:
    shell = page.locator(".fence-fox-captcha")
    field = page.locator(".fox-field")
    fox = page.locator("#fox-runner")
    text = shell.inner_text().upper()
    forbidden = [term for term in ("CANONICAL_PLAN", "GROUND_TRUTH", "CHALLENGE_ID") if term in text]
    field_box = field.bounding_box()
    fox_box = fox.bounding_box()
    verdict_node = page.locator(".fox-verdict")
    verdict = verdict_node.inner_text().strip() if verdict_node.count() else ""
    prompt = page.locator(".fox-header > p").inner_text().upper()
    tutorial_selectors = (
        ".fox-right-rail",
        ".fox-policy-card",
        ".fox-wind-card",
        ".fox-rule-strip",
        ".fox-legend",
        ".fox-supply-card p",
    )
    tutorial_nodes = {
        selector: page.locator(selector).count()
        for selector in tutorial_selectors
    }
    shell_classes = (shell.get_attribute("class") or "").split()
    input_rule = "DRAG THE REUSABLE STAKE" if "mode-full" in shell_classes else "CLICK AN OPEN HEX"
    prompt_requirements = {
        "goal_and_rim": "CUTTING EVERY OPEN ROUTE TO THE RIM" in prompt,
        "stake_budget": "STAKES" in prompt,
        "interaction": input_rule in prompt,
        "shortest_route": "SHORTEST OPEN ROUTE" in prompt,
        "continuation_tie_break": "MORE SHORTEST CONTINUATIONS" in prompt,
        "neighbor_tie_break": "MORE OPEN NEIGHBORS" in prompt,
        "changing_wind": "WIND ORDER CHANGES AFTER EVERY FOX STEP" in prompt,
        "direction_order": all(f"{direction}" in prompt for direction in ("E", "NE", "NW", "W", "SW", "SE")),
    }
    current_wind_state = page.locator(".fox-vane-card").count() == 1 and bool(
        page.locator("#fox-vane-order").inner_text().strip()
    )
    passed = (
        field_box is not None
        and fox_box is not None
        and field_box["x"] >= 0
        and field_box["y"] >= 0
        and field_box["x"] + field_box["width"] <= VIEWPORT["width"] + 1
        and field_box["y"] + field_box["height"] <= VIEWPORT["height"] + 1
        and not forbidden
        and not any(tutorial_nodes.values())
        and all(prompt_requirements.values())
        and current_wind_state
    )
    if phase == "initial":
        passed = passed and verdict == ""
    elif phase == "failure-fresh":
        passed = passed and "FAIL" in verdict
    elif phase == "pass":
        passed = passed and "PASS" in verdict
    result = {
        "phase": phase,
        "field_box": field_box,
        "fox_box": fox_box,
        "open_cells": page.locator(".fox-cell:not([disabled])").count(),
        "forbidden_visible_strings": forbidden,
        "prompt": prompt,
        "prompt_requirements": prompt_requirements,
        "tutorial_nodes": tutorial_nodes,
        "prompt_is_only_persistent_rules_copy": True,
        "current_wind_state_visible": current_wind_state,
        "verdict": verdict,
        "passed": passed,
    }
    if not passed:
        raise AssertionError(f"visible surface contract failed: {result}")
    return result


def input_binding_contract(page, interaction: str) -> dict:
    state_before = page.evaluate(
        "() => ({turns: fenceTheFoxModel.turns, events: fenceTheFoxModel.events.length, "
        "pendingActions: WeirdCaptchaTime.status().pending_action_count})"
    )
    if interaction == "full":
        page.locator(".fox-cell:not([disabled])").first.click()
        page.wait_for_timeout(80)
        forbidden_action = "cell_click"
    else:
        page.locator("#fox-stake-token").dispatch_event("pointerdown", {"pointerId": 97, "clientX": 120, "clientY": 330})
        page.wait_for_timeout(80)
        forbidden_action = "stake_pointerdown"
    state_after = page.evaluate(
        "() => ({turns: fenceTheFoxModel.turns, events: fenceTheFoxModel.events.length, "
        "pendingActions: WeirdCaptchaTime.status().pending_action_count})"
    )
    if state_before != state_after:
        raise AssertionError(f"{interaction} accepted its other mode's action: {state_before} -> {state_after}")
    return {
        "interaction": interaction,
        "forbidden_action_tested": forbidden_action,
        "before": state_before,
        "after": state_after,
        "rejected_without_state_change": True,
    }


def edge_case_input(page, interaction: str, fox_start: list[int], solver) -> dict:
    before = page.evaluate(
        """() => ({
          turns: fenceTheFoxModel.turns,
          events: fenceTheFoxModel.events.length,
          fences: fenceTheFoxModel.playerFences.map(item => [...item]),
        })"""
    )
    if interaction == "simplified":
        lifecycle = solver._place(page, fox_start, interaction)
    else:
        source_box = page.locator("#fox-stake-token").bounding_box()
        target_box = page.locator(
            f'.fox-cell[data-q="{int(fox_start[0])}"][data-r="{int(fox_start[1])}"]'
        ).bounding_box()
        if source_box is None or target_box is None:
            raise AssertionError("fox-occupied drop endpoints are not visible")
        page.mouse.move(source_box["x"] + source_box["width"] / 2, source_box["y"] + source_box["height"] / 2)
        page.mouse.down()
        page.mouse.move(target_box["x"] + target_box["width"] / 2, target_box["y"] + target_box["height"] / 2, steps=5)
        page.mouse.up()
        lifecycle = solver._settle_turn(page)
    after = page.evaluate(
        """() => ({
          turns: fenceTheFoxModel.turns,
          events: fenceTheFoxModel.events.length,
          fences: fenceTheFoxModel.playerFences.map(item => [...item]),
        })"""
    )
    readout = page.locator(".fox-readout").inner_text().strip()
    clock = page.evaluate("() => WeirdCaptchaTime.status()")
    if before != after:
        raise AssertionError(f"fox-occupied drop changed the field: {before} -> {after}")
    if "FOX OCCUPIES" not in readout.upper():
        raise AssertionError(f"fox-occupied drop did not explain the rejection: {readout!r}")
    if clock["pending_action_count"] != 0:
        raise AssertionError(f"rejected input leaked an action handle: {clock}")
    return {
        "strategy": "place a stake on the fox-occupied hex, observe rejection, then recover and solve",
        "interaction": interaction,
        "fox_hex": fox_start,
        "before": before,
        "after": after,
        "visible_readout": readout,
        "clock_after_rejection": clock,
        "action_lifecycle": lifecycle,
        "rejected_without_state_change": True,
        "action_handle_settled": True,
    }


def observation_and_delay_contract(page, output: Path, mode: str, label: str, capture: bool) -> dict:
    if mode == "live":
        page.evaluate("() => WeirdCaptchaTime.resume()")
    else:
        page.evaluate("() => WeirdCaptchaTime.pause()")
    before_clock = page.evaluate("() => WeirdCaptchaTime.status()")
    before_state = page.evaluate(
        "() => ({fox: [...fenceTheFoxModel.fox], turns: fenceTheFoxModel.turns, "
        "events: fenceTheFoxModel.events.length, fences: fenceTheFoxModel.playerFences.map(item => [...item])})"
    )
    page.wait_for_timeout(520)
    after_clock = page.evaluate("() => WeirdCaptchaTime.status()")
    after_state = page.evaluate(
        "() => ({fox: [...fenceTheFoxModel.fox], turns: fenceTheFoxModel.turns, "
        "events: fenceTheFoxModel.events.length, fences: fenceTheFoxModel.playerFences.map(item => [...item])})"
    )
    delta = float(after_clock["task_time_ms"]) - float(before_clock["task_time_ms"])
    if mode == "live" and delta < 400:
        raise AssertionError(f"live clock did not advance during model delay: {delta}")
    if mode == "paused" and abs(delta) > 2:
        raise AssertionError(f"paused clock advanced during model delay: {delta}")
    if before_state != after_state:
        raise AssertionError(f"fox decision changed without an action: {before_state} -> {after_state}")
    frames = []
    if capture:
        folder = output / "direct_browser_delay_captures" / f"baseline-full-{mode}"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "frame-000.png"
        page.screenshot(path=str(path))
        frames.append({
            "frame_index": 0,
            "path": str(path.relative_to(output)),
            "sha256": sha256(path),
            "task_time_ms": round(float(after_clock["task_time_ms"]), 3),
        })
    return {
        "label": label,
        "mode": mode,
        "native_delay_ms": 520,
        "task_time_delta_ms": round(delta, 3),
        "world_state_before": before_state,
        "world_state_after": after_state,
        "correct_action_expired": False,
        "frames_per_observation": 1,
        "frames": frames,
    }


def invalid_attempt(page, state_dir: Path) -> dict:
    initial = read_json(state_dir / "public_state.json")
    page.locator("#fox-certify").click()
    try:
        expect(page.locator(".fox-verdict.is-fail")).to_be_visible(timeout=30_000)
    except AssertionError as exc:
        browser_state = page.evaluate(
            """() => ({
                model: window.fenceTheFoxModel,
                readout: document.querySelector('.fox-readout')?.textContent || '',
                verdict: document.querySelector('.fox-verdict')?.textContent || '',
            })"""
        )
        attempts_path = state_dir / "attempts.jsonl"
        attempts = attempts_path.read_text(encoding="utf-8") if attempts_path.exists() else ""
        raise AssertionError(
            "invalid enclosure report did not yield a visible failed refresh; "
            f"browser={browser_state!r}; attempts={attempts[-4000:]!r}"
        ) from exc
    refreshed = read_json(state_dir / "public_state.json")
    if refreshed["challenge_id"] == initial["challenge_id"]:
        raise AssertionError("invalid enclosure report did not rotate to a fresh field")
    attempts = (state_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    archived = json.loads(attempts[-1])
    return {
        "initial_challenge_id": initial["challenge_id"],
        "fresh_challenge_id": refreshed["challenge_id"],
        "rotated": True,
        "server_grade": archived.get("server_grade"),
    }


def capture_condition(playwright, temporary: Path, output: Path, level: int, interaction: str, mode: str) -> dict:
    label = f"d{level}-{interaction}-{mode}"
    state_dir = temporary / "states" / label
    state_dir.mkdir(parents=True)
    task = condition_task(temporary, level, interaction, mode)
    seed = f"fox-visible-d{level}"
    process, port = start_server(task, state_dir, seed)
    profile = temporary / "fresh-profiles" / label
    screenshots = output / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    context = playwright.chromium.launch_persistent_context(
        str(profile), headless=True, viewport=VIEWPORT, device_scale_factor=1,
    )
    page = context.pages[0]
    errors: list[str] = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    solver = load_module(SOLVER, f"fox_solver_{label.replace('-', '_')}")
    grader = load_module(GRADER, f"fox_grader_{label.replace('-', '_')}")
    try:
        page.goto(
            f"http://127.0.0.1:{port}/?time_mode={mode}&start_paused=1&time_control=1",
            # The evaluator control channel intentionally keeps a long-poll
            # request open, so network-idle is not a reachable readiness gate.
            wait_until="domcontentloaded",
        )
        expect(page.locator(".fence-fox-captcha")).to_be_visible(timeout=8_000)
        classes = (page.locator(".fence-fox-captcha").get_attribute("class") or "").split()
        if f"mode-{interaction}" not in classes:
            raise AssertionError(f"rendered interaction class mismatch: {classes}")
        initial_state = read_json(state_dir / "public_state.json")
        initial_truth = read_json(state_dir / "ground_truth.json")
        checks = [surface_contract(page, "initial")]
        initial_path = screenshots / f"{label}-initial.png"
        if mode == "live":
            page.screenshot(path=str(initial_path))
        binding = input_binding_contract(page, interaction)
        observation = observation_and_delay_contract(
            page, output, mode, label, capture=level == 3 and interaction == "full",
        )
        edge_case = edge_case_input(page, interaction, initial_state["fox_start"], solver)

        active = None
        if level == 3 and interaction == "full":
            first = initial_truth["canonical_plan"][0]
            lifecycle = solver._place(page, first, interaction)
            active_path = screenshots / f"baseline-full-{mode}-active.png"
            page.screenshot(path=str(active_path))
            active = {
                "path": str(active_path.relative_to(output)),
                "sha256": sha256(active_path),
                "placed": first,
                "browser_state": page.evaluate(
                    "() => ({fox: [...fenceTheFoxModel.fox], turns: fenceTheFoxModel.turns, "
                    "events: fenceTheFoxModel.events.length, terminal: fenceTheFoxModel.terminal, "
                    "clock: WeirdCaptchaTime.status()})"
                ),
                "action_lifecycle": lifecycle,
            }
        failure = invalid_attempt(page, state_dir)
        checks.append(surface_contract(page, "failure-fresh"))
        if level == 3 and interaction == "full":
            failure_path = screenshots / f"baseline-full-{mode}-failure-fresh.png"
            page.screenshot(path=str(failure_path))
        # The harness records the representative initial/active/pass states
        # above. Keep the solver's diagnostic frames in the temporary run
        # directory so the committed evidence bundle is not needlessly large.
        action_cycles = solver.solve(page, state_dir, temporary / "solver-frames" / label, MECHANIC)
        if not action_cycles or not all(
            cycle["before_settle"]["pending_action_count"] == 1
            and cycle["after_settle"]["pending_action_count"] == 0
            for cycle in action_cycles
        ):
            raise AssertionError(f"accepted action lifecycle was not arm → settle: {action_cycles}")
        expect(page.locator(".fox-verdict.is-pass")).to_be_visible(timeout=8_000)
        checks.append(surface_contract(page, "pass"))
        if mode == "live" and (level in {2, 3, 4} or interaction == "full"):
            pass_path = screenshots / f"{label}-pass.png"
            page.screenshot(path=str(pass_path))
        if mode == "paused":
            page.evaluate("() => WeirdCaptchaTime.pause()")
        export, export_command = exported(state_dir, output, label)
        export_path = output / export_command["artifact"]
        direct = grader.grade(export["result"], export["ground_truth"], export["public_state"])
        verified = verify_export(export_path, label)
        server_grade = export["result"].get("server_grade") or {}
        if not all(item.get("passed") is True for item in (server_grade, direct, verified)):
            raise AssertionError(f"grade mismatch server={server_grade} direct={direct} verifier={verified}")
        if errors:
            raise AssertionError(f"browser errors: {errors}")
        final_clock = page.evaluate("() => WeirdCaptchaTime.status()")
        if final_clock["pending_action_count"] != 0:
            raise AssertionError(f"condition ended with pending actions: {final_clock}")
        return {
            "label": label,
            "level": level,
            "interaction": interaction,
            "time_mode": mode,
            "headless": True,
            "fresh_profile": str(profile.relative_to(temporary)),
            "loopback_origin": f"http://127.0.0.1:{port}",
            "challenge_seed": seed,
            "world_fingerprint": world_fingerprint(initial_state),
            "canonical_plan_length": len(initial_truth["canonical_plan"]),
            "initial_screenshot": {
                "path": str(initial_path.relative_to(output)),
                "sha256": sha256(initial_path),
            } if initial_path.is_file() else None,
            "active_evidence": active,
            "direct_browser_delay_check": observation,
            "input_binding": binding,
            "edge_case_recovery": edge_case,
            "failure_retry": failure,
            "action_barrier": {
                "protocol": "loopback /time-control resume then settle_pause for each paused action",
                "final_clock": final_clock,
                "solution_action_cycles": action_cycles,
                "all_action_handles_settled": True,
                "every_accepted_action_observed_pending_then_settled": True,
            },
            "visible_surface_checks": checks,
            "server_grade": server_grade,
            "direct_grade": direct,
            "verifier": verified,
            "export": export_command,
            "browser_errors": errors,
        }
    finally:
        context.close()
        stop_server(process)


def negative_contract(output: Path) -> dict:
    export_path = output / "exports" / "d3-full-live.json"
    exported_payload = read_json(export_path)
    grader = load_module(GRADER, "fox_negative_contract_grader")
    payload = exported_payload["result"]
    truth = exported_payload["ground_truth"]
    public = exported_payload["public_state"]
    cases: dict[str, dict] = {}

    def check(name: str, mutate) -> None:
        candidate = copy.deepcopy(payload)
        mutate(candidate)
        decision = grader.grade(candidate, truth, public)
        if decision.get("passed") is not False:
            raise AssertionError(f"negative contract case passed: {name}: {decision}")
        cases[name] = decision

    check("stale_challenge", lambda item: item.__setitem__("challenge_id", "stale-challenge"))
    check("wrong_interaction_source", lambda item: item["events"][0].__setitem__("input_source", "cell_click"))
    check("forged_fox_reply", lambda item: item["events"][0].__setitem__("fox_to", [0, 0]))
    check("short_full_drag", lambda item: item["events"][0]["gesture"].__setitem__("travel_px", 3))
    check("missing_stake_driver_path", lambda item: item["events"][0]["gesture"].__setitem__("driver_path", [[0, 0]]))
    check("forged_visible_wind", lambda item: item["events"][0].__setitem__("wind_start", (item["events"][0]["wind_start"] + 1) % 6))
    check("forged_final_fences", lambda item: item.__setitem__("player_fences", []))
    artifact = {
        "source_export": str(export_path.relative_to(output)),
        "all_rejected": True,
        "cases": cases,
    }
    write_json(output / "negative_contract.json", artifact)
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=EVIDENCE)
    parser.add_argument("--levels", type=int, nargs="+", default=list(range(1, 6)))
    parser.add_argument("--interactions", nargs="+", choices=("simplified", "full"), default=["simplified", "full"])
    parser.add_argument("--modes", nargs="+", choices=("live", "paused"), default=["live", "paused"])
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Older creator evidence mislabeled direct page screenshots as model
    # observations. Remove that stale folder before writing correctly named
    # direct-browser artifacts; runner observations are captured separately.
    shutil.rmtree(output / "model_observations", ignore_errors=True)
    with tempfile.TemporaryDirectory(prefix="fence-the-fox-isolated-") as temporary_text:
        temporary = Path(temporary_text)
        matrix = []
        with sync_playwright() as playwright:
            for level in args.levels:
                for interaction in args.interactions:
                    for mode in args.modes:
                        print(f"capturing d{level}-{interaction}-{mode}", flush=True)
                        matrix.append(capture_condition(playwright, temporary, output, level, interaction, mode))
        for level in args.levels:
            worlds = {item["world_fingerprint"] for item in matrix if item["level"] == level}
            if len(worlds) != 1:
                raise AssertionError(f"interaction or schedule changed the d{level} world: {worlds}")
        complete_matrix = (
            set(args.levels) == set(range(1, 6))
            and set(args.interactions) == {"simplified", "full"}
            and set(args.modes) == {"live", "paused"}
        )
        negative = negative_contract(output) if complete_matrix else {"all_rejected": False, "cases": {}}
        summary = {
            "environment": "Fence the Fox",
            "mechanic_id": MECHANIC,
            "browser_isolation": {
                "headless": True,
                "fresh_temporary_persistent_profile_per_condition": True,
                "loopback_only": True,
                "existing_profile_or_window_attached": False,
            },
            "matrix_size": len(matrix),
            "all_twenty_passed": complete_matrix and len(matrix) == 20,
            "live_paused_same_world": True,
            "interaction_modes_same_world": True,
            "all_negative_contract_cases_rejected": negative["all_rejected"] if complete_matrix else None,
            "all_action_barriers_settled": all(
                item["action_barrier"]["all_action_handles_settled"] is True
                and item["action_barrier"]["every_accepted_action_observed_pending_then_settled"] is True
                and item["action_barrier"]["final_clock"]["pending_action_count"] == 0
                for item in matrix
            ),
            "all_edge_case_recoveries_passed": all(
                item["edge_case_recovery"]["rejected_without_state_change"] is True
                and item["server_grade"].get("passed") is True
                for item in matrix
            ),
            "conditions": matrix,
        }
        write_json(output / "browser_matrix.json", summary)
        write_json(output / "validation_summary.json", {
            "matrix_size": len(matrix),
            "all_twenty_passed": complete_matrix and len(matrix) == 20,
            "server_direct_verifier_agreement": all(
                item["server_grade"].get("passed") is True
                and item["direct_grade"].get("passed") is True
                and item["verifier"].get("passed") is True
                for item in matrix
            ),
            "failure_refresh_recovery": all(item["failure_retry"]["rotated"] is True for item in matrix),
            "edge_case_recovery": all(item["edge_case_recovery"]["rejected_without_state_change"] is True for item in matrix),
            "action_barrier_settled": all(
                item["action_barrier"]["final_clock"]["pending_action_count"] == 0 for item in matrix
            ),
            "paused_protocol": "loopback /time-control resume then settle_pause",
            "live_paused_same_world": True,
            "interaction_modes_same_world": True,
            "negative_contract_cases_rejected": list(negative["cases"]),
            "browser_isolation": summary["browser_isolation"],
        })
        print(json.dumps({
            "matrix_size": len(matrix),
            "all_twenty_passed": complete_matrix and len(matrix) == 20,
            "output": str(output),
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
