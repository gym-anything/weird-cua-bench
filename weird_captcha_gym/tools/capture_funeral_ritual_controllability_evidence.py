#!/usr/bin/env python3
"""Capture visible, local evidence for Funeral With No Instructions controls.

This is a validation tool, not a benchmark solver. It reads generated state to
choose a scripted path, but drives the same visible buttons, pointer actions,
and pointer-drag surface that a browser user receives.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENV_ROOT = BENCHMARK / "environments" / "funeral_ritual_env"
APP_DIR = BENCHMARK / "shared_runtime" / "app"
SERVER = BENCHMARK / "shared_runtime" / "server" / "weird_captcha_server.py"
SETUP = BENCHMARK / "shared_scripts" / "setup_task.py"
EXPORT = BENCHMARK / "shared_scripts" / "export_result.sh"
MATERIALIZER_PATH = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
HELPERS_PATH = BENCHMARK / "shared_runtime" / "verifier_helpers.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture Funeral ritual controllability evidence.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ENV_ROOT / "evidence_docs",
        help="Evidence directory (created or replaced).",
    )
    return parser.parse_args()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_server(task_path: Path, state_dir: Path, port: int, seed: str) -> subprocess.Popen:
    subprocess.run(
        ["python", "-B", str(SETUP), "--task-json", str(task_path), "--state-dir", str(state_dir), "--seed", seed],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    process = subprocess.Popen(
        ["python", "-B", str(SERVER), "--host", "127.0.0.1", "--port", str(port), "--app-dir", str(APP_DIR), "--state-dir", str(state_dir)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            import urllib.request

            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=.5).read()
            return process
        except Exception:
            time.sleep(.05)
    process.kill()
    raise TimeoutError(f"server did not start for {task_path}")


def stop_server(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()


def wait_for_funeral(page) -> None:
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(".funeral-captcha")


def flower_ids_in_ui_order(state: dict[str, Any]) -> list[str]:
    by_kind = {str(item["kind"]): str(item["id"]) for item in state.get("flowers") or []}
    visible_order = [str(kind) for kind in state.get("tribute_order") or []]
    if visible_order:
        return [by_kind[kind] for kind in visible_order]
    return [str(item["id"]) for item in state.get("flowers") or []]


def run_paused_action(page, action_name: str, perform, *, running_ms: int = 60) -> dict[str, Any]:
    """Run one browser action through the shared paused-mode action cycle.

    The clock must be resumed for every complete user action, then paused again
    before the next model-observation/inference interval.  Keeping this in the
    browser evidence tool prevents a paused screenshot from being mistaken for
    evidence that paused episodes can also execute and submit an action.
    """
    before = page.evaluate("WeirdCaptchaTime.status()")
    if before["state"] != "paused":
        raise AssertionError(f"paused action {action_name} began while clock was not paused: {before}")
    resumed = page.evaluate("WeirdCaptchaTime.resume()")
    if resumed["state"] != "running":
        raise AssertionError(f"paused action {action_name} did not resume the clock: {resumed}")
    perform()
    page.wait_for_timeout(running_ms)
    after_action = page.evaluate("WeirdCaptchaTime.status()")
    if after_action["state"] != "running" or float(after_action["task_time_ms"]) <= float(before["task_time_ms"]):
        raise AssertionError(
            f"paused action {action_name} was not executed while time advanced: {before} -> {after_action}"
        )
    paused = page.evaluate("WeirdCaptchaTime.pause()")
    if paused["state"] != "paused":
        raise AssertionError(f"paused action {action_name} did not pause the clock: {paused}")
    page.wait_for_timeout(80)
    frozen = page.evaluate("WeirdCaptchaTime.status()")
    if abs(float(frozen["task_time_ms"]) - float(paused["task_time_ms"])) > 1:
        raise AssertionError(
            f"paused action {action_name} let task time advance during inference: {paused} -> {frozen}"
        )
    return {
        "action": action_name,
        "before_resume": before,
        "after_action": after_action,
        "after_pause": paused,
        "after_inference_delay": frozen,
    }


def capture_visible_order_failure(
    page,
    state: dict[str, Any],
    interaction: str,
    *,
    paused_action_cycle: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Use visible controls to submit a wrong ordered flower and recover.

    Only L4/L5 expose an ordered tribute.  Clicking a non-next flower is a
    normal task-page action; the controlled browser renderer submits that
    rejected attempt to the same server and renders the fresh challenge the
    server returns.  No endpoint call or manual render happens in this helper.
    """
    ordered_ids = flower_ids_in_ui_order(state)
    if len(ordered_ids) < 2:
        raise AssertionError("visible failure capture requires an ordered L4/L5 tribute")
    wrong_id = next(flower_id for flower_id in ordered_ids if flower_id != ordered_ids[0])
    before = str(state.get("challenge_id") or "")
    if not before:
        raise AssertionError("visible failure capture requires the generated challenge id")
    action_cycles: list[dict[str, Any]] = []

    def perform(action_name: str, callback, *, running_ms: int = 60) -> None:
        if paused_action_cycle:
            action_cycles.append(run_paused_action(page, action_name, callback, running_ms=running_ms))
        else:
            callback()

    if interaction == "simplified":
        perform("inspect", lambda: page.locator('[data-proxy-action="inspect"]').click())
        perform("brush", lambda: page.locator('[data-proxy-action="brush"]').click())
        perform("light", lambda: page.locator('[data-proxy-action="light"]').click())
        perform(
            f"wrong-gather:{wrong_id}",
            lambda: page.locator(f'[data-proxy-flower-id="{wrong_id}"]').click(),
            running_ms=140,
        )
    else:
        perform("inspect", lambda: page.locator(".tombstone").click(position={"x": 110, "y": 60}))
        cells = page.locator(".moss-cell")
        for index in range(int(state["brush_threshold"])):
            perform(f"brush:{index}", lambda index=index: cells.nth(index).click())
        perform("light", lambda: page.locator(".grave-candle").click())
        perform(
            f"wrong-gather:{wrong_id}",
            lambda: page.locator(f'.ritual-flower[data-flower-id="{wrong_id}"]').click(),
            running_ms=140,
        )

    expect(page.locator(".readout")).to_have_text("FAIL", timeout=5_000)
    if paused_action_cycle and page.evaluate("WeirdCaptchaTime.status().state") != "paused":
        raise AssertionError("visible paused failure did not return to the inference pause")
    return {
        "method": "visible_wrong_ordered_flower",
        "wrong_flower_id": wrong_id,
        "before_challenge_id": before,
        "visible_fail_rendered": True,
    }, action_cycles


def save_visible_failure_artifact(state_dir: Path, output: Path, label: str, challenge_id: str) -> dict[str, Any]:
    attempts_path = state_dir / "attempts.jsonl"
    if not attempts_path.is_file():
        raise AssertionError(f"visible failure did not create an archived attempt for {label}")
    entries = [json.loads(line) for line in attempts_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(entries) != 1:
        raise AssertionError(f"expected one rejected visible attempt for {label}, got {len(entries)}")
    attempt = entries[0]
    grade = attempt.get("server_grade") or {}
    if str(attempt.get("challenge_id") or "") != challenge_id or grade.get("passed") is not False:
        raise AssertionError(f"unexpected rejected visible attempt for {label}: {attempt!r}")
    artifact = output / "failure_artifacts" / f"{label}-rejected-attempt.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(attempt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"artifact": str(artifact.relative_to(output)), "server_grade": grade}


def solve_visible_ritual(
    page,
    state: dict[str, Any],
    interaction: str,
    on_stage=None,
    *,
    paused_action_cycle: bool = False,
) -> list[dict[str, Any]]:
    """Use only the selected visible UI surface and return paused-cycle traces."""
    required = set(str(item) for item in (state.get("control_condition") or {}).get("difficulty_parameters", {}).get("required_events") or [])
    action_cycles: list[dict[str, Any]] = []

    def perform(action_name: str, callback, *, running_ms: int = 60) -> None:
        if paused_action_cycle:
            action_cycles.append(run_paused_action(page, action_name, callback, running_ms=running_ms))
        else:
            callback()

    if interaction == "simplified":
        perform("inspect", lambda: page.locator('[data-proxy-action="inspect"]').click())
        if "brush" in required:
            perform("brush", lambda: page.locator('[data-proxy-action="brush"]').click())
            if state.get("tribute_order") and on_stage:
                page.wait_for_timeout(500)
                on_stage("tribute-order")
        perform("light", lambda: page.locator('[data-proxy-action="light"]').click())
        if state.get("tribute_order_mode") == "memory" and on_stage:
            page.wait_for_timeout(450)
            on_stage("tribute-memory-hidden")
        for flower_id in flower_ids_in_ui_order(state):
            perform(f"gather:{flower_id}", lambda flower_id=flower_id: page.locator(f'[data-proxy-flower-id="{flower_id}"]').click())
        # The submission is intentionally delayed by the task through the
        # shared virtual timer.  The whole offer, including that timer, runs
        # before we pause the next inference interval.
        perform("offer", lambda: page.locator('[data-proxy-action="offer"]').click(), running_ms=850)
        return action_cycles

    perform("inspect", lambda: page.locator(".tombstone").click(position={"x": 110, "y": 60}))
    if "brush" in required:
        cells = page.locator(".moss-cell")
        for index in range(int(state["brush_threshold"])):
            perform(f"brush:{index}", lambda index=index: cells.nth(index).click())
        if state.get("tribute_order") and on_stage:
            page.wait_for_timeout(500)
            on_stage("tribute-order")
    perform("light", lambda: page.locator(".grave-candle").click())
    if state.get("tribute_order_mode") == "memory" and on_stage:
        page.wait_for_timeout(450)
        on_stage("tribute-memory-hidden")
    for flower_id in flower_ids_in_ui_order(state):
        perform(f"gather:{flower_id}", lambda flower_id=flower_id: page.locator(f'.ritual-flower[data-flower-id="{flower_id}"]').click())
    def drag_bouquet() -> None:
        bouquet = page.locator(".ritual-bouquet").bounding_box()
        grave = page.locator(".grave-bed").bounding_box()
        if bouquet is None or grave is None:
            raise AssertionError("funeral bouquet transfer endpoints have no visible bounds")
        page.mouse.move(bouquet["x"] + bouquet["width"] / 2, bouquet["y"] + bouquet["height"] / 2)
        page.mouse.down()
        page.mouse.move(grave["x"] + grave["width"] / 2, grave["y"] + grave["height"] / 2)
        page.mouse.up()

    perform("offer", drag_bouquet, running_ms=850)
    return action_cycles


def export_and_verify(state_dir: Path, output: Path, label: str, helpers, task_verifier_path: Path) -> dict[str, Any]:
    environment = dict(os.environ)
    environment["WEIRD_CAPTCHA_STATE_DIR"] = str(state_dir)
    completed = subprocess.run(
        ["bash", str(EXPORT)], cwd=ROOT, env=environment, capture_output=True, text=True, check=True
    )
    exported_path = Path("/tmp/task_result.json")
    exported = read_json(exported_path)
    saved_export = output / "result_artifacts" / f"{label}-export.json"
    saved_export.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exported_path, saved_export)
    verified = helpers.verify_funeral_ritual(exported)
    verifier = load_module(f"funeral_task_verifier_{label.replace('-', '_')}", task_verifier_path)

    def copy_from_env(source: str, destination: str) -> None:
        if source != "/tmp/task_result.json":
            raise ValueError(f"unexpected verifier export path: {source}")
        shutil.copy2(exported_path, destination)

    task_verified = verifier.verify_task(env_info={"copy_from_env": copy_from_env})
    if not verified.get("passed") or not task_verified.get("passed"):
        raise AssertionError(f"export verifier failed for {label}: {verified!r}; {task_verified!r}")
    result = exported.get("result") or {}
    server_grade = result.get("server_grade") or {}
    if server_grade.get("passed") is not True:
        raise AssertionError(f"live server grade failed for {label}: {server_grade!r}")
    return {
        "export_result": saved_export.name,
        "export_command_stdout": completed.stdout.strip(),
        "server_grade": server_grade,
        "verifier": verified,
        "task_verifier": task_verified,
        "result": result,
    }


def verify_wrong_surface(helpers, exported: dict[str, Any]) -> dict[str, Any]:
    wrong = copy.deepcopy(exported)
    result = wrong["result"]
    expected = str((wrong["ground_truth"].get("control_condition") or {}).get("interaction") or "")
    opposite = "full" if expected == "simplified" else "simplified"
    result["interaction_mode"] = opposite
    result["action_surfaces"] = [
        {"event": str(item["event"]), "surface": opposite}
        for item in result.get("action_surfaces") or []
    ]
    result["flower_sources"] = {
        str(key): opposite for key in (result.get("flower_sources") or {})
    }
    decision = helpers.verify_funeral_ritual(wrong)
    if decision.get("passed"):
        raise AssertionError("wrong interaction surface unexpectedly passed exported verification")
    return decision


def strip_condition(state: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(state)
    value.pop("task_id", None)
    value.pop("challenge_id", None)
    value.pop("control_condition", None)
    return value


def capture_time_observations(browser, tasks: list[tuple[str, Path]], scratch: Path, output: Path) -> dict[str, Any]:
    observations: dict[str, Any] = {}
    for label, task_path in tasks:
        port = free_port()
        state_dir = scratch / f"time-observation-{label}"
        state_dir.mkdir(parents=True)
        process = start_server(task_path, state_dir, port, f"funeral-time-observation-{label}")
        try:
            live = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
            live.set_default_timeout(5_000)
            live.goto(f"http://127.0.0.1:{port}/?time_mode=live")
            wait_for_funeral(live)
            live.wait_for_function("window.WeirdCaptchaTime?.status().state === 'running'")
            live_before = live.evaluate("WeirdCaptchaTime.status()")
            live.wait_for_timeout(220)
            live_after = live.evaluate("WeirdCaptchaTime.status()")
            live.screenshot(path=str(output / f"{label}-model-observation-live.png"))
            if float(live_after["task_time_ms"]) <= float(live_before["task_time_ms"]):
                raise AssertionError(f"live task clock did not advance for {label}: {live_before} -> {live_after}")
            live.close()

            paused = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
            paused.set_default_timeout(5_000)
            paused.goto(f"http://127.0.0.1:{port}/?time_mode=paused&start_paused=1")
            wait_for_funeral(paused)
            paused.wait_for_function("window.WeirdCaptchaTime?.status().state === 'paused'")
            paused_before = paused.evaluate("WeirdCaptchaTime.status()")
            paused.wait_for_timeout(220)
            paused_after = paused.evaluate("WeirdCaptchaTime.status()")
            paused.screenshot(path=str(output / f"{label}-model-observation-paused.png"))
            if abs(float(paused_after["task_time_ms"]) - float(paused_before["task_time_ms"])) > 1:
                raise AssertionError(f"paused task clock advanced for {label}: {paused_before} -> {paused_after}")
            paused.close()
            observations[label] = {
                "live_before": live_before,
                "live_after_220ms": live_after,
                "paused_before": paused_before,
                "paused_after_220ms": paused_after,
            }
        finally:
            stop_server(process)
    return observations


def repeat_timing_sensitive_paused_completion(
    browser,
    task_path: Path,
    scratch: Path,
    output: Path,
    helpers,
) -> list[dict[str, Any]]:
    """Repeat L5/full paused completion twice, including its virtual submit timer."""
    repetitions: list[dict[str, Any]] = []
    for run_number in range(1, 3):
        label = f"d5-full-paused-repeat-{run_number}"
        print(f"capturing {label}", flush=True)
        state_dir = scratch / label
        state_dir.mkdir()
        port = free_port()
        process = start_server(task_path, state_dir, port, "funeral-controls-l5-paused-repeat")
        errors: list[str] = []
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
            page.set_default_timeout(5_000)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{port}/?time_mode=paused&start_paused=1")
            wait_for_funeral(page)
            page.wait_for_function("window.WeirdCaptchaTime?.status().state === 'paused'")
            page.screenshot(path=str(output / f"{label}-initial.png"))
            public_state = read_json(state_dir / "public_state.json")
            action_cycles = solve_visible_ritual(
                page,
                public_state,
                "full",
                paused_action_cycle=True,
            )
            expect(page.locator(".readout")).to_have_text("PASS", timeout=5_000)
            final_clock = page.evaluate("WeirdCaptchaTime.status()")
            if final_clock["state"] != "paused":
                raise AssertionError(f"timing repeat {run_number} did not return to paused state: {final_clock}")
            page.screenshot(path=str(output / f"{label}-pass.png"))
            if errors:
                raise AssertionError(f"browser errors for {label}: {errors}")
            export = export_and_verify(
                state_dir,
                output,
                label,
                helpers,
                ENV_ROOT / "tasks" / "funeral_ritual_seed_0001" / "verifier.py",
            )
            repetitions.append({
                "run": run_number,
                "task": task_path.parent.name,
                "screenshots": [f"{label}-initial.png", f"{label}-pass.png"],
                "final_clock": final_clock,
                "paused_action_cycles": action_cycles,
                "server_grade": export["server_grade"],
                "verifier": export["verifier"],
                "task_verifier": export["task_verifier"],
                "export_command": ["bash", str(EXPORT)],
                "export_command_stdout": export["export_command_stdout"],
                "export_result": export["export_result"],
            })
            page.close()
        finally:
            stop_server(process)
    return repetitions


def main() -> None:
    args = parse_args()
    output = args.out_dir.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    materializer = load_module("funeral_materializer", MATERIALIZER_PATH)
    setup = load_module("funeral_setup", SETUP)
    helpers = load_module("funeral_helpers", HELPERS_PATH)
    controls = read_json(ENV_ROOT / "controls.json")

    with tempfile.TemporaryDirectory(prefix="funeral-controls-evidence-") as temporary:
        scratch = Path(temporary)
        materialized_root = scratch / "controlled"
        materializer.materialize_environment(ENV_ROOT, materialized_root)
        tasks_root = materialized_root / ENV_ROOT.name / "tasks"
        variants: list[dict[str, Any]] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for level in range(1, 6):
                for interaction in ("simplified", "full"):
                    base_label = f"d{level}-{interaction}"
                    task_dir = tasks_root / f"funeral_ritual_d{level}_{interaction}_seed_0001"
                    task_path = task_dir / "task.json"
                    for time_mode in ("live", "paused"):
                        label = base_label if time_mode == "live" else f"{base_label}-paused"
                        print(f"capturing {label}", flush=True)
                        state_dir = scratch / label
                        state_dir.mkdir()
                        port = free_port()
                        process = start_server(task_path, state_dir, port, f"funeral-controls-{level}")
                        errors: list[str] = []
                        try:
                            page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
                            page.set_default_timeout(5_000)
                            page.on("pageerror", lambda error: errors.append(str(error)))
                            query = "?time_mode=live" if time_mode == "live" else "?time_mode=paused&start_paused=1"
                            page.goto(f"http://127.0.0.1:{port}/{query}")
                            wait_for_funeral(page)
                            expected_clock_state = "running" if time_mode == "live" else "paused"
                            page.wait_for_function(f"window.WeirdCaptchaTime?.status().state === '{expected_clock_state}'")
                            initial_public = read_json(state_dir / "public_state.json")
                            page.screenshot(path=str(output / f"{label}-initial.png"))
                            failure_recovery: dict[str, Any] | None = None
                            failure_action_cycles: list[dict[str, Any]] = []
                            failure_screenshots: list[str] = []
                            recovered_public = initial_public
                            if level >= 4:
                                failure_recovery, failure_action_cycles = capture_visible_order_failure(
                                    page,
                                    initial_public,
                                    interaction,
                                    paused_action_cycle=time_mode == "paused",
                                )
                                failure_name = f"{label}-visible-failure-retry.png"
                                page.screenshot(path=str(output / failure_name))
                                failure_screenshots.append(failure_name)
                                recovered_public = read_json(state_dir / "public_state.json")
                                recovered_challenge_id = str(recovered_public.get("challenge_id") or "")
                                if not recovered_challenge_id or recovered_challenge_id == failure_recovery["before_challenge_id"]:
                                    raise AssertionError(f"visible recovery did not issue a fresh server challenge for {label}")
                                failure_recovery["recovered_challenge_id"] = recovered_challenge_id
                                failure_recovery["archived_attempt"] = save_visible_failure_artifact(
                                    state_dir,
                                    output,
                                    label,
                                    failure_recovery["before_challenge_id"],
                                )
                            stage_screenshots: list[str] = []

                            def capture_stage(stage: str) -> None:
                                name = f"{label}-{stage}.png"
                                page.screenshot(path=str(output / name))
                                stage_screenshots.append(name)

                            action_cycles = [*failure_action_cycles, *solve_visible_ritual(
                                page,
                                recovered_public,
                                interaction,
                                capture_stage,
                                paused_action_cycle=time_mode == "paused",
                            )]
                            expect(page.locator(".readout")).to_have_text("PASS", timeout=5_000)
                            final_clock = page.evaluate("WeirdCaptchaTime.status()")
                            if time_mode == "paused" and final_clock["state"] != "paused":
                                raise AssertionError(f"paused run did not return to inference pause after offer for {label}: {final_clock}")
                            page.screenshot(path=str(output / f"{label}-pass.png"))
                            if errors:
                                raise AssertionError(f"browser errors for {label}: {errors}")
                            export = export_and_verify(
                                state_dir,
                                output,
                                label,
                                helpers,
                                ENV_ROOT / "tasks" / "funeral_ritual_seed_0001" / "verifier.py",
                            )
                            exported = read_json(output / "result_artifacts" / export["export_result"])
                            wrong_surface = verify_wrong_surface(helpers, exported)
                            variants.append({
                                "condition": {"difficulty": level, "interaction": interaction, "real_time": time_mode},
                                "task": task_dir.name,
                                "initial_challenge_id": initial_public["challenge_id"],
                                "failure_recovery": failure_recovery,
                                "server_grade": export["server_grade"],
                                "verifier": export["verifier"],
                                "task_verifier": export["task_verifier"],
                                "wrong_surface_verifier": wrong_surface,
                                "export_command": ["bash", str(EXPORT)],
                                "export_command_stdout": export["export_command_stdout"],
                                "final_clock": final_clock,
                                "paused_action_cycles": action_cycles,
                                "screenshots": [f"{label}-initial.png", *failure_screenshots, *stage_screenshots, f"{label}-pass.png"],
                            })
                            page.close()
                        finally:
                            stop_server(process)

                simplified_task = read_json(tasks_root / f"funeral_ritual_d{level}_simplified_seed_0001" / "task.json")
                full_task = read_json(tasks_root / f"funeral_ritual_d{level}_full_seed_0001" / "task.json")
                simplified_public, simplified_truth = setup.generate_task_state(simplified_task, f"funeral-controls-{level}")
                full_public, full_truth = setup.generate_task_state(full_task, f"funeral-controls-{level}")
                if strip_condition(simplified_public) != strip_condition(full_public) or strip_condition(simplified_truth) != strip_condition(full_truth):
                    raise AssertionError(f"interaction pair d{level} changed its generated world or goal")

            original_task = ENV_ROOT / "tasks" / "funeral_ritual_seed_0001" / "task.json"
            baseline_task = tasks_root / "funeral_ritual_d3_full_seed_0001" / "task.json"
            original_public, original_truth = setup.generate_task_state(read_json(original_task), "funeral-baseline-evidence")
            baseline_public, baseline_truth = setup.generate_task_state(read_json(baseline_task), "funeral-baseline-evidence")
            baseline_preserved = strip_condition(original_public) == strip_condition(baseline_public) and strip_condition(original_truth) == strip_condition(baseline_truth)
            if not baseline_preserved:
                raise AssertionError("L3 full did not preserve the uncontrolled ritual")
            time_tasks = [
                (
                    f"d{level}-{interaction}",
                    tasks_root / f"funeral_ritual_d{level}_{interaction}_seed_0001" / "task.json",
                )
                for level in range(1, 6)
                for interaction in ("simplified", "full")
            ]
            time_observations = capture_time_observations(browser, time_tasks, scratch, output)
            timing_repetitions = repeat_timing_sensitive_paused_completion(
                browser,
                tasks_root / "funeral_ritual_d5_full_seed_0001" / "task.json",
                scratch,
                output,
                helpers,
            )
            browser.close()

    summary = {
        "environment": "Funeral With No Instructions",
        "baseline": controls["baseline"],
        "baseline_preserved": baseline_preserved,
        "difficulty_profiles": {
            level: {
                "summary": profile["summary"],
                "parameters": profile["parameters"],
            }
            for level, profile in controls["difficulty"].items()
        },
        "interaction_pair_worlds_preserved": True,
        "variants": variants,
        "time_observations": time_observations,
        "timing_sensitive_paused_repetitions": timing_repetitions,
        "real_time_settings": controls["real_time"],
        "notes": [
            "Every L4/L5 interaction and time-mode pair first uses a wrong visible ordered-flower action; the normal renderer submits that rejected attempt, displays FAIL on the fresh server challenge, and then solves the replacement through its selected visible surface.",
            "L1-L3 have no ordered-flower error path, so their evidence records normal selected-surface completions without fabricating a failure transcript.",
            "Each paused action cycle resumes the shared clock for the complete visible action, pauses it for an 80 ms inference interval, and records both clock states.",
            "The result artifacts are exports produced by shared_scripts/export_result.sh after the local server accepted the browser interaction in the stated real-time mode.",
            "The scripted path selects generated flowers from test state but performs only ordinary visible browser actions; it is implementation evidence, not human calibration or an agent evaluation.",
        ],
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    command_results = {
        "capture_command": "python weird_captcha_gym/tools/capture_funeral_ritual_controllability_evidence.py",
        "materialized_task_count": 10,
        "browser_runs": len(variants),
        "timing_sensitive_repetitions": len(timing_repetitions),
        "exports": [
            {
                "condition": item["condition"],
                "command": item["export_command"],
                "stdout": item["export_command_stdout"],
                "artifact": item["server_grade"],
            }
            for item in variants
        ] + [
            {
                "condition": {"difficulty": 5, "interaction": "full", "real_time": "paused", "repeat": item["run"]},
                "command": item["export_command"],
                "stdout": item["export_command_stdout"],
                "artifact": item["server_grade"],
            }
            for item in timing_repetitions
        ],
    }
    (output / "command_results.json").write_text(json.dumps(command_results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "README.md").write_text(
        """# Funeral With No Instructions controllability evidence

`summary.json` and `command_results.json` were generated by:

```bash
python weird_captcha_gym/tools/capture_funeral_ritual_controllability_evidence.py
```

The capture materializes every difficulty/interaction condition, then completes
each through a visible local browser in both live and paused real-time modes.
It saves the local-server export and checks the direct and task verifiers after
each completion.

- `d3-full-initial.png` is the unchanged L3/full reference condition. `d2-full-initial.png`, `d3-full-initial.png`, and `d4-full-tribute-order.png` show adjacent profile changes. The L5 `tribute-order` images show its revealed six-item order, while matching `tribute-memory-hidden` images show that lighting the candle removes it.
- Matching `d*-simplified-initial.png` and `d*-full-initial.png` frames show the two input surfaces for the same generated world. `summary.json` records the generator equality check for every pair.
- Every L4/L5 `d*-visible-failure-retry.png` frame is a normal wrong-flower page interaction: it has submitted an invalid ordered tribute through the selected visible surface, the server has rejected it, and the renderer is showing `FAIL` on the replacement challenge. The matching `failure_artifacts/*.json` files are the archived rejected UI submissions. These eight runs cover simplified/full and live/paused. L1-L3 have no ordered-flower error path and therefore retain normal initial/pass evidence rather than fabricated failure requests.
- `d*-model-observation-live.png` and `d*-model-observation-paused.png` show model observations for the same condition. `summary.json` records the task clock before and after a 220 ms artificial inference delay.
- Each paused browser completion records `paused_action_cycles` in `summary.json`: it verifies that task time advances while the shared clock is resumed for every click or drag, then stays frozen during the following inference interval. The `d*-paused-pass.png` frames and their matching exports show that those resumed actions reach grading and submission.
- `d5-full-paused-repeat-1-*` and `d5-full-paused-repeat-2-*` are two independent repetitions of the timing-sensitive L5/full paused path, including its shared virtual delayed-submission timer. Their action-cycle traces, verifier results, exports, and exact command output are in `summary.json` and `command_results.json`.
- `result_artifacts/d*-export.json` and `result_artifacts/d*-paused-export.json` are the post-pass export artifacts. `command_results.json` contains the exact `export_result.sh` command stdout associated with each artifact.
- `validation_command_outputs.md` records the post-capture focused, full-suite, static-browser, and strict-quality commands.

All captured failure/recovery and normal completion paths use the selected
visible browser controls. In paused runs the shared time controller is resumed
and paused around those controls; it is never used to submit or render a
failure. The harness reads generated state only to choose its scripted clicks
and drags; it is implementation evidence, not human calibration or a
computer-use-agent evaluation.
""",
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "out_dir": str(output), "browser_runs": len(variants)}, indent=2))


if __name__ == "__main__":
    main()
