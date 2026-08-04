#!/usr/bin/env python3
"""Collect browser-visible controllability evidence for Scroll-Cage Checkbox.

This is an implementation audit, not human calibration or an agent evaluation.
It materializes every controlled task, solves each through ordinary Playwright
pointer/wheel/button input, and preserves the browser, server, direct-grader,
and exported-verifier results alongside representative screenshots.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from weird_captcha_gym.dashboard.export_static import export_dashboard  # noqa: E402
from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment  # noqa: E402


BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "moving_checkbox_evasive_button_env"
MECHANIC = "moving_checkbox_evasive_button"
APP_DIR = BENCHMARK / "shared_runtime" / "app"
SERVER = BENCHMARK / "shared_runtime" / "server" / "weird_captcha_server.py"
SETUP = BENCHMARK / "shared_scripts" / "setup_task.py"
GRADER = BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py"
VERIFIER = ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "verifier.py"
SOLVER = BENCHMARK / "tools" / "incubator_solvers" / f"{MECHANIC}.py"
BASELINE_CONTRACT = "Check the box."
SYNTHETIC_OBSERVER_FRAME_SOURCE = "synthetic canvas frames for the observer-contract check only; not Scroll-Cage task frames"
HEADLESS_DISPLAY_CAPTURE_LIMITATION = (
    "literal target display capture is unavailable in the isolated headless Chromium "
    "static-browser path"
)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ENVIRONMENT / "evidence_docs",
        help="Evidence directory to populate.",
    )
    parser.add_argument("--port", type=int, default=9660)
    parser.add_argument("--seed-prefix", default="scroll-cage-controllability-audit")
    parser.add_argument("--levels", type=int, choices=range(1, 6), nargs="+", default=[1, 2, 3, 4, 5])
    parser.add_argument("--interactions", choices=("simplified", "full"), nargs="+", default=["simplified", "full"])
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--observations-only", action="store_true")
    parser.add_argument("--observation-label", default="", help="suffix for a repeated observation audit")
    parser.add_argument("--summarize", action="store_true")
    return parser.parse_args()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def start_server(task_json: Path, state_dir: Path, port: int, seed: str, command_log: list[dict]) -> subprocess.Popen:
    setup_command = [
        "python", "-B", str(SETUP), "--task-json", str(task_json),
        "--state-dir", str(state_dir), "--seed", seed,
    ]
    setup = subprocess.run(setup_command, cwd=ROOT, text=True, capture_output=True, check=True)
    command_log.append({
        "command": setup_command,
        "returncode": setup.returncode,
        "stdout": setup.stdout,
        "stderr": setup.stderr,
    })
    server_command = [
        "python", "-B", str(SERVER), "--host", "127.0.0.1", "--port", str(port),
        "--app-dir", str(APP_DIR), "--state-dir", str(state_dir),
    ]
    process = subprocess.Popen(
        server_command,
        cwd=ROOT,
        env={
            **os.environ,
            "WEIRD_CAPTCHA_CHEAT_PASSWORD": "scroll-cage-audit-only",
            # The first visible /state request deliberately creates a fresh
            # browser challenge. Keep that refresh and the retry deterministic
            # so paired input surfaces can be compared at one fixed seed.
            "WEIRD_CAPTCHA_CHALLENGE_SEED": seed,
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5).read()
            command_log.append({"command": server_command, "returncode": "running", "stdout": "health check passed", "stderr": ""})
            return process
        except Exception:
            time.sleep(0.1)
    process.kill()
    raise RuntimeError(f"server did not start for {task_json}")


def stop_server(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()


def run_verifier(exported: dict, temporary: Path) -> dict:
    verifier = load_module(VERIFIER, "scroll_cage_controllability_verifier")
    export_path = temporary / "exported-result.json"
    write_json(export_path, exported)

    def copy_from_env(source: str, destination: str) -> None:
        if source != "/tmp/task_result.json":
            raise ValueError(f"unexpected verifier source {source}")
        shutil.copyfile(export_path, destination)

    result = verifier.verify_task(env_info={"copy_from_env": copy_from_env})
    if not isinstance(result, dict):
        raise AssertionError(f"task verifier returned {result!r}")
    return result


def copy_artifacts(state_dir: Path, evidence_root: Path, label: str) -> dict[str, str]:
    copied: dict[str, str] = {}
    for name in ("public_state.json", "ground_truth.json", "result.json"):
        source = state_dir / name
        if source.is_file():
            destination = evidence_root / "artifacts" / f"{label}-{name}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied[name] = str(destination.relative_to(evidence_root))
    return copied


def exercise_full_drag_register(page, truth: dict) -> None:
    """Move one full-mode register down and back using visible pointer drag."""
    control = page.locator("[data-shaft-control='0']")
    drag = control.locator("[data-shaft-drag='0']")
    label = control.locator("[data-offset-label='0']")
    before_label = label.inner_text()
    scene = truth["scene"]
    before = int(before_label)
    direction = -1 if before >= int(scene["offset_max"]) else 1
    box = drag.bounding_box()
    if box is None:
        raise AssertionError("full-mode shaft register is not visible")
    x = box["x"] + box["width"] / 2
    y = box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x, y + direction * 24, steps=2)
    page.mouse.move(x, y, steps=2)
    page.mouse.up()
    if label.inner_text() != before_label:
        raise AssertionError("full-mode drag register did not return to its starting offset")


def l5_console_layout(page) -> dict[str, float]:
    """Ensure the fifth register and checkbox remain inside the workbench at 1280×720."""
    console = page.locator(".scroll-cage-console").bounding_box()
    check = page.locator("#scroll-cage-check").bounding_box()
    footer = page.locator(".scroll-cage-foot").bounding_box()
    if console is None or check is None or footer is None:
        raise AssertionError("L5 console geometry is not visible")
    check_bottom = check["y"] + check["height"]
    console_bottom = console["y"] + console["height"]
    if check["y"] < console["y"] or check_bottom > console_bottom or check_bottom > footer["y"]:
        raise AssertionError(
            "L5 final checkbox overlaps the footer or leaves the console: "
            f"console={console}, check={check}, footer={footer}"
        )
    return {
        "console_bottom": round(console_bottom, 2),
        "check_bottom": round(check_bottom, 2),
        "footer_top": round(footer["y"], 2),
    }


def without_control_identity(value: dict) -> dict:
    normalized = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        normalized.pop(key, None)
    return normalized


def audit_baseline(output: Path, port: int, seed_prefix: str) -> dict:
    """Archive the exact uncontrolled L4 world and both controlled L4 surfaces."""
    command_log: list[dict] = []
    seed = f"{seed_prefix}-baseline-preservation"
    with tempfile.TemporaryDirectory(prefix="scroll-cage-baseline-") as temporary_name:
        temporary = Path(temporary_name)
        original_task = ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json"
        if read_json(original_task).get("natural_language") != BASELINE_CONTRACT:
            raise AssertionError("the source task no longer has the exact historical Scroll-Cage instruction")
        materialized_root = temporary / "materialized"
        materialize_environment(ENVIRONMENT, materialized_root)
        cases = [
            ("baseline-original", original_task),
            ("baseline-l4-simplified", materialized_root / ENVIRONMENT.name / "tasks" / f"{MECHANIC}_d4_simplified_seed_0001" / "task.json"),
            ("baseline-l4-full", materialized_root / ENVIRONMENT.name / "tasks" / f"{MECHANIC}_d4_full_seed_0001" / "task.json"),
        ]
        snapshots: dict[str, dict] = {}
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for index, (label, task_json) in enumerate(cases):
                    state_dir = temporary / label / "state"
                    state_dir.mkdir(parents=True)
                    process = start_server(task_json, state_dir, port + 100 + index, seed, command_log)
                    page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
                    try:
                        page.goto(f"http://127.0.0.1:{port + 100 + index}/", wait_until="networkidle")
                        expect(page.locator(".scroll-cage")).to_be_visible()
                        screenshot = output / "screenshots" / f"{label}.png"
                        screenshot.parent.mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=str(screenshot), full_page=True)
                        artifacts = copy_artifacts(state_dir, output, label)
                        snapshots[label] = {
                            "prompt": page.locator(".scroll-cage-head h1").inner_text(),
                            "screenshot": str(screenshot.relative_to(output)),
                            "artifacts": artifacts,
                        }
                    finally:
                        page.close()
                        stop_server(process)
            finally:
                browser.close()

    original_public = read_json(output / snapshots["baseline-original"]["artifacts"]["public_state.json"])
    original_truth = read_json(output / snapshots["baseline-original"]["artifacts"]["ground_truth.json"])
    simplified_public = read_json(output / snapshots["baseline-l4-simplified"]["artifacts"]["public_state.json"])
    simplified_truth = read_json(output / snapshots["baseline-l4-simplified"]["artifacts"]["ground_truth.json"])
    full_public = read_json(output / snapshots["baseline-l4-full"]["artifacts"]["public_state.json"])
    full_truth = read_json(output / snapshots["baseline-l4-full"]["artifacts"]["ground_truth.json"])
    preservation = {
        "fixed_seed": seed,
        "exact_historical_instruction": BASELINE_CONTRACT,
        "snapshots": snapshots,
        "original_to_l4_public_unchanged": without_control_identity(original_public) == without_control_identity(simplified_public),
        "original_to_l4_truth_unchanged": without_control_identity(original_truth) == without_control_identity(simplified_truth),
        "l4_interaction_pair_public_same_world": without_control_identity(simplified_public) == without_control_identity(full_public),
        "l4_interaction_pair_truth_same_world": without_control_identity(simplified_truth) == without_control_identity(full_truth),
        "command_log": command_log,
    }
    if not all(value is True for key, value in preservation.items() if key.endswith(("unchanged", "same_world"))):
        raise AssertionError(f"Scroll-Cage exact baseline preservation failed: {preservation}")
    write_json(output / "baseline-preservation.json", preservation)
    write_json(output / "command-results" / "baseline-preservation.json", command_log)
    return preservation


def audit_variants(output: Path, port: int, seed_prefix: str, levels: list[int], interactions: list[str]) -> tuple[list[dict], list[dict]]:
    command_log: list[dict] = []
    variants: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="scroll-cage-controlled-") as temporary_name:
        temporary = Path(temporary_name)
        materialized_root = temporary / "materialized"
        written = materialize_environment(ENVIRONMENT, materialized_root)
        command_log.append({
            "command": ["python", "weird_captcha_gym/tools/materialize_controlled_tasks.py", "--environment", ENVIRONMENT.name, "--output-root", str(materialized_root)],
            "returncode": 0,
            "stdout": f"materialized {len(written)} tasks",
            "stderr": "",
        })
        grader = load_module(GRADER, "scroll_cage_controllability_grader")
        solver = load_module(SOLVER, "scroll_cage_controllability_solver")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for index, interaction in enumerate(interactions):
                    for level in levels:
                        label = f"d{level}_{interaction}"
                        task_json = materialized_root / ENVIRONMENT.name / "tasks" / f"{MECHANIC}_{label}_seed_0001" / "task.json"
                        state_dir = temporary / label / "state"
                        capture_dir = output / "screenshots" / label
                        state_dir.mkdir(parents=True)
                        capture_dir.mkdir(parents=True, exist_ok=True)
                        process = start_server(task_json, state_dir, port + index * 10 + level, f"{seed_prefix}-d{level}_simplified", command_log)
                        page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
                        console_errors: list[str] = []
                        page.on("console", lambda message, errors=console_errors: errors.append(message.text) if message.type == "error" else None)
                        page.on("pageerror", lambda error, errors=console_errors: errors.append(str(error)))
                        try:
                            page.goto(f"http://127.0.0.1:{port + index * 10 + level}/", wait_until="networkidle")
                            expect(page.locator(".scroll-cage")).to_be_visible()
                            console_layout = l5_console_layout(page) if level == 5 else None
                            page.screenshot(path=str(capture_dir / "initial.png"), full_page=True)
                            before_challenge = read_json(state_dir / "ground_truth.json")["challenge_id"]
                            solver.fail_once(page, state_dir, capture_dir, MECHANIC)
                            after_challenge = read_json(state_dir / "ground_truth.json")["challenge_id"]
                            if before_challenge == after_challenge:
                                raise AssertionError("failure did not create a fresh controlled challenge")
                            full_drag_probe = False
                            if interaction == "full":
                                exercise_full_drag_register(page, read_json(state_dir / "ground_truth.json"))
                                full_drag_probe = True
                            solver.solve(page, state_dir, capture_dir, MECHANIC)
                            expect(page.locator(".readout")).to_have_text("PASS", timeout=15_000)
                            completed_console_layout = l5_console_layout(page) if level == 5 else None
                            page.screenshot(path=str(capture_dir / "final-pass.png"), full_page=True)
                            if console_errors:
                                raise AssertionError(f"browser console errors: {console_errors}")

                            exported = {
                                "public_state": read_json(state_dir / "public_state.json"),
                                "ground_truth": read_json(state_dir / "ground_truth.json"),
                                "result": read_json(state_dir / "result.json"),
                            }
                            server_grade = exported["result"].get("server_grade") or {}
                            direct_grade = grader.grade(exported["result"], exported["ground_truth"], exported["public_state"])
                            verifier = run_verifier(exported, temporary / label)
                            if not all(decision.get("passed") is True for decision in (server_grade, direct_grade, verifier)):
                                raise AssertionError({"server": server_grade, "direct": direct_grade, "verifier": verifier})
                            events = exported["result"].get("events") or []
                            scroll_sources = sorted({str(event.get("input_source") or "") for event in events if event.get("type") == "scroll"})
                            expected_sources = {"simplified": {"shaft_button"}, "full": {"shaft_drag", "shaft_wheel"}}[interaction]
                            if not scroll_sources or not set(scroll_sources) <= expected_sources:
                                raise AssertionError(f"{label} recorded unexpected scroll sources {scroll_sources}")
                            if interaction == "full" and set(scroll_sources) != expected_sources:
                                raise AssertionError(f"{label} did not exercise both full scroll surfaces: {scroll_sources}")
                            wrong = copy.deepcopy(exported["result"])
                            first_scroll = next(event for event in wrong["events"] if event.get("type") == "scroll")
                            first_scroll["input_source"] = "shaft_wheel" if interaction == "simplified" else "shaft_button"
                            wrong_grade = grader.grade(wrong, exported["ground_truth"], exported["public_state"])
                            if wrong_grade.get("passed") is not False or "wrong interaction input" not in str(wrong_grade.get("feedback") or ""):
                                raise AssertionError(f"{label} accepted cross-mode transcript: {wrong_grade}")
                            artifacts = copy_artifacts(state_dir, output, label)
                            variants.append({
                                "condition": exported["public_state"]["control_condition"],
                                "challenge_id_before_failure": before_challenge,
                                "challenge_id_after_failure": after_challenge,
                                "console_layout": (
                                    {"initial": console_layout, "completed": completed_console_layout}
                                    if level == 5 else None
                                ),
                                "full_drag_probe": full_drag_probe,
                                "scroll_sources": scroll_sources,
                                "server_grade": server_grade,
                                "direct_grade": direct_grade,
                                "verifier": verifier,
                                "cross_mode_rejection": wrong_grade,
                                "artifacts": artifacts,
                                "screenshots": sorted(str(path.relative_to(output)) for path in capture_dir.glob("*.png")),
                            })
                            write_json(output / "variant-results" / f"{label}.json", variants[-1])
                        finally:
                            page.close()
                            stop_server(process)
            finally:
                browser.close()

        by_level: dict[int, list[dict]] = {}
        for variant in variants:
            by_level.setdefault(int(variant["condition"]["difficulty"]), []).append(variant)
        equivalence: list[dict] = []
        for level, members in sorted(by_level.items()):
            if len(members) != 2:
                continue
            first, second = members
            first_state = read_json(output / first["artifacts"]["public_state.json"])
            second_state = read_json(output / second["artifacts"]["public_state.json"])
            first_truth = read_json(output / first["artifacts"]["ground_truth.json"])
            second_truth = read_json(output / second["artifacts"]["ground_truth.json"])
            same_world = without_control_identity(first_state) == without_control_identity(second_state)
            same_truth = without_control_identity(first_truth) == without_control_identity(second_truth)
            if not same_world or not same_truth:
                raise AssertionError(f"difficulty {level} interaction variants changed the generated world")
            equivalence.append({"difficulty": level, "same_world": same_world, "same_truth": same_truth})
    return variants, command_log + [{"command": ["interaction-pair-equivalence"], "returncode": 0, "stdout": json.dumps(equivalence), "stderr": ""}]


def summarize(output: Path) -> dict:
    variants = [read_json(path) for path in sorted((output / "variant-results").glob("d*_*.json"))]
    if len(variants) != 10:
        raise AssertionError(f"expected ten controlled variant results, found {len(variants)}")
    observations = read_json(output / "observation-results.json")
    if set(observations) != {"live", "paused"}:
        raise AssertionError("both live and paused observation results are required")
    repeated_observations = read_json(output / "observation-results-repeat.json")
    if set(repeated_observations) != {"live", "paused"}:
        raise AssertionError("a repeated live and paused observation audit is required")
    for name, observation_set in (("initial", observations), ("repeat", repeated_observations)):
        for mode in ("live", "paused"):
            observer_contract = observation_set[mode].get("observer_contract_only")
            if not isinstance(observer_contract, dict) or observer_contract.get("synthetic") is not True:
                raise AssertionError(f"{name} {mode} observation frame provenance is not explicitly synthetic")
            if observer_contract.get("frame_source") != SYNTHETIC_OBSERVER_FRAME_SOURCE:
                raise AssertionError(f"{name} {mode} observation frame source is mislabeled")
            if observer_contract.get("literal_target_display_capture") != HEADLESS_DISPLAY_CAPTURE_LIMITATION:
                raise AssertionError(f"{name} {mode} display-capture limitation is missing")
            if int(observer_contract.get("frame_count", 0)) != 5:
                raise AssertionError(f"{name} {mode} observer-contract frame count is incorrect")
            if observer_contract.get("final_synthetic_frame_is_obs_screen") is not True:
                raise AssertionError(f"{name} {mode} final synthetic observer frame is not obs.screen")
            if not observation_set[mode].get("direct_target_screen_screenshot"):
                raise AssertionError(f"{name} {mode} direct target screen evidence is missing")
        if observation_set["live"]["task_time_after_delay_ms"] <= observation_set["live"]["task_time_before_delay_ms"] + 100:
            raise AssertionError(f"{name} live observation did not advance task time")
        if abs(observation_set["paused"]["task_time_after_delay_ms"] - observation_set["paused"]["task_time_before_delay_ms"]) > 1:
            raise AssertionError(f"{name} paused observation advanced task time")
        if observation_set["paused"].get("paused_action", {}).get("offset_changed") is not True:
            raise AssertionError(f"{name} paused observation did not apply a visible action")
        if int(observation_set["paused"]["paused_action"]["tick_after"]) <= int(observation_set["paused"]["paused_action"]["tick_before"]):
            raise AssertionError(f"{name} paused action did not advance the fixed-step simulation")
    baseline_preservation = read_json(output / "baseline-preservation.json")
    required_baseline_checks = (
        "original_to_l4_public_unchanged",
        "original_to_l4_truth_unchanged",
        "l4_interaction_pair_public_same_world",
        "l4_interaction_pair_truth_same_world",
    )
    if any(baseline_preservation.get(check) is not True for check in required_baseline_checks):
        raise AssertionError("fixed-seed original/L4 preservation evidence is incomplete")
    l5_variants = [variant for variant in variants if int(variant["condition"]["difficulty"]) == 5]
    if len(l5_variants) != 2:
        raise AssertionError("both L5 interaction variants are required for the console layout check")
    for variant in l5_variants:
        layout = variant.get("console_layout")
        if not isinstance(layout, dict):
            raise AssertionError(f"L5 {variant['condition']['interaction']} lacks console layout evidence")
        for phase in ("initial", "completed"):
            bounds = layout.get(phase)
            if not isinstance(bounds, dict):
                raise AssertionError(f"L5 {variant['condition']['interaction']} lacks {phase} console bounds")
            if not float(bounds["check_bottom"]) <= float(bounds["console_bottom"]) < float(bounds["footer_top"]):
                raise AssertionError(f"L5 {variant['condition']['interaction']} overlaps the footer at {phase}")
    by_level: dict[int, list[dict]] = {}
    for variant in variants:
        by_level.setdefault(int(variant["condition"]["difficulty"]), []).append(variant)
    equivalence: list[dict] = []
    for level, members in sorted(by_level.items()):
        if len(members) != 2:
            raise AssertionError(f"difficulty {level} does not have both interaction variants")
        first, second = members
        first_state = read_json(output / first["artifacts"]["public_state.json"])
        second_state = read_json(output / second["artifacts"]["public_state.json"])
        first_truth = read_json(output / first["artifacts"]["ground_truth.json"])
        second_truth = read_json(output / second["artifacts"]["ground_truth.json"])
        same_world = without_control_identity(first_state) == without_control_identity(second_state)
        same_truth = without_control_identity(first_truth) == without_control_identity(second_truth)
        if not same_world or not same_truth:
            raise AssertionError(f"difficulty {level} interaction variants changed the generated world")
        equivalence.append({"difficulty": level, "same_world": same_world, "same_truth": same_truth})
    # The advertised complete matrix invocation writes one combined log.  Keep
    # supporting the earlier pair of split logs, but never require callers to
    # run the matrix twice solely to make --summarize work.
    command_log_dir = output / "command-results"
    baseline_log = command_log_dir / "baseline-preservation.json"
    combined_candidates = sorted(
        (
            path for path in command_log_dir.glob("d1_d2_d3_d4_d5_*.json")
            if path.stem.removeprefix("d1_d2_d3_d4_d5_") in {"simplified_full", "full_simplified"}
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if combined_candidates:
        command_log_paths = [baseline_log, combined_candidates[0]]
    else:
        command_log_paths = [
            baseline_log,
            command_log_dir / "d1_d2_d3_d4_d5_simplified.json",
            command_log_dir / "d1_d2_d3_d4_d5_full.json",
        ]
    missing_command_logs = [path for path in command_log_paths if not path.is_file()]
    if missing_command_logs:
        raise AssertionError(f"current complete-matrix command logs are missing: {missing_command_logs}")
    command_logs = [read_json(path) for path in command_log_paths]
    return {
        "environment": ENVIRONMENT.name,
        "mechanic_id": MECHANIC,
        "automated_scope": "Visible browser interaction, failure/retry, live grade, direct grade, exported verifier, interaction-pair equivalence, and browser observation inspector.",
        "not_established": ["human usability", "human calibration", "computer-use-agent difficulty"],
        "variant_count": len(variants),
        "variants": variants,
        "baseline_preservation": baseline_preservation,
        "interaction_pair_equivalence": equivalence,
        "observations": observations,
        "repeated_observations": repeated_observations,
        "command_log_files": [str(path.relative_to(output)) for path in command_log_paths],
        "command_logs": command_logs,
    }


def audit_observations(output: Path, label: str = "") -> dict:
    """Exercise the observer contract with explicitly synthetic frames.

    Chromium's isolated headless mode cannot provide a literal tab-display
    capture stream.  The canvas stream below verifies frame count, ordering,
    and final-screen selection only; direct task page screenshots and clock
    checks are captured separately and are not presented as observer frames.
    """
    suffix = f"-{label}" if label else ""
    with tempfile.TemporaryDirectory(prefix="scroll-cage-static-") as temporary_name:
        site = Path(temporary_name) / "site"
        export_dashboard(site, copy_media=False)
        handler = partial(QuietHandler, directory=str(site))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        result: dict[str, dict] = {}
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1280, "height": 720})
                context.add_init_script(
                    """(() => {
                      const canvas = document.createElement('canvas');
                      canvas.width = 1280; canvas.height = 720;
                      const context = canvas.getContext('2d'); let frame = 0;
                      setInterval(() => { frame += 1; context.fillStyle = frame % 2 ? '#102418' : '#182d3a'; context.fillRect(0, 0, 1280, 720); }, 32);
                      const mediaDevices = navigator.mediaDevices || {};
                      Object.defineProperty(mediaDevices, 'getDisplayMedia', {configurable: true, value: async () => canvas.captureStream(30)});
                      if (!navigator.mediaDevices) Object.defineProperty(navigator, 'mediaDevices', {configurable: true, value: mediaDevices});
                    })()"""
                )
                for mode in ("live", "paused"):
                    page = context.new_page()
                    try:
                        page.goto(
                            f"{base_url}/play/?environment=moving_checkbox_evasive_button_env&attempt=0&difficulty=4&interaction=simplified&time_mode={mode}",
                            wait_until="networkidle",
                        )
                        expect(page.locator(".scroll-cage")).to_be_visible()
                        page.get_by_role("button", name="Expand observation controls").click()
                        if mode == "paused":
                            page.get_by_role("button", name="Paused").click()
                            page.wait_for_function("WeirdCaptchaTime.status().state === 'paused'")
                        else:
                            page.get_by_role("button", name="Live").click()
                            page.wait_for_function("WeirdCaptchaTime.status().state === 'running'")
                        direct_target_screen = output / "screenshots" / f"direct-target-screen-{mode}{suffix}.png"
                        direct_target_screen.parent.mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=str(direct_target_screen), full_page=True)
                        before = page.evaluate("WeirdCaptchaTime.status().task_time_ms")
                        page.wait_for_timeout(240)
                        after = page.evaluate("WeirdCaptchaTime.status().task_time_ms")
                        if mode == "live" and after <= before + 100:
                            raise AssertionError(f"live task clock did not advance: {before} -> {after}")
                        if mode == "paused" and abs(after - before) > 1:
                            raise AssertionError(f"paused task clock advanced: {before} -> {after}")
                        paused_action: dict[str, int | bool] | None = None
                        if mode == "paused":
                            # The expanded demo inspector deliberately floats over the
                            # right-hand panel. Collapse it before issuing a task input.
                            page.get_by_role("button", name="Collapse observation controls").click()
                            shaft = page.locator("[data-shaft-down='0']")
                            offset_before = page.evaluate("window.scrollCageModel.offsets[0]")
                            tick_before = page.evaluate("window.scrollCageModel.tick")
                            box = shaft.bounding_box()
                            if box is None:
                                raise AssertionError("could not locate the paused-mode shaft control")
                            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                            page.mouse.down()
                            page.wait_for_timeout(90)
                            page.mouse.up()
                            page.wait_for_function("WeirdCaptchaTime.status().state === 'paused'")
                            offset_after = page.evaluate("window.scrollCageModel.offsets[0]")
                            tick_after = page.evaluate("window.scrollCageModel.tick")
                            if offset_after == offset_before or tick_after <= tick_before:
                                raise AssertionError(
                                    "paused action did not both change the puzzle and advance its simulation "
                                    f"(offset {offset_before} -> {offset_after}, tick {tick_before} -> {tick_after})"
                                )
                            paused_action = {
                                "offset_changed": offset_after != offset_before,
                                "tick_before": tick_before,
                                "tick_after": tick_after,
                            }
                            page.get_by_role("button", name="Expand observation controls").click()
                        page.get_by_role("button", name="Capture model observation").click()
                        expect(page.locator(".weird-demo-observation")).to_have_attribute("data-open", "true", timeout=10_000)
                        expect(page.locator(".weird-demo-frame")).to_have_count(5)
                        expect(page.locator("[data-demo-screen-label]")).to_contain_text("obs.screen")
                        synthetic_observer_contract = output / "screenshots" / f"observer-contract-only-synthetic-{mode}{suffix}.png"
                        synthetic_observer_contract.parent.mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=str(synthetic_observer_contract), full_page=True)
                        result[mode] = {
                            "task_time_before_delay_ms": before,
                            "task_time_after_delay_ms": after,
                            "direct_target_screen_screenshot": str(direct_target_screen.relative_to(output)),
                            "observer_contract_only": {
                                "synthetic": True,
                                "frame_source": SYNTHETIC_OBSERVER_FRAME_SOURCE,
                                "literal_target_display_capture": HEADLESS_DISPLAY_CAPTURE_LIMITATION,
                                "frame_count": page.locator(".weird-demo-frame").count(),
                                "final_synthetic_frame_is_obs_screen": "obs.screen" in page.locator("[data-demo-screen-label]").inner_text().lower(),
                                "screenshot": str(synthetic_observer_contract.relative_to(output)),
                            },
                            "paused_action": paused_action,
                        }
                    finally:
                        page.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
    return result


def main() -> None:
    args = parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.summarize:
        summary = summarize(output)
        write_json(output / "validation.json", summary)
        write_json(output / "command-output.json", summary["command_logs"])
        print(json.dumps({"ok": True, "variants": summary["variant_count"], "observations": summary["observations"]}, indent=2))
        return
    if args.baseline_only:
        baseline = audit_baseline(output, args.port, args.seed_prefix)
        print(json.dumps({"ok": True, "baseline": baseline}, indent=2))
        return
    if args.observations_only:
        label = str(args.observation_label).strip().replace("/", "-")
        if label and not label.replace("-", "").isalnum():
            raise ValueError("observation label must use letters, digits, and hyphens")
        observations = audit_observations(output, label)
        name = "observation-results.json" if not label else f"observation-results-{label}.json"
        write_json(output / name, observations)
        print(json.dumps({"ok": True, "observations": observations}, indent=2))
        return
    variants, commands = audit_variants(output, args.port, args.seed_prefix, args.levels, args.interactions)
    chunk = "_".join(f"d{level}" for level in args.levels) + "_" + "_".join(args.interactions)
    write_json(output / "command-results" / f"{chunk}.json", commands)
    print(json.dumps({"ok": True, "variants": [variant["condition"] for variant in variants]}, indent=2))


if __name__ == "__main__":
    main()
