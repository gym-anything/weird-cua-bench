#!/usr/bin/env python3
"""Capture preservation, difficulty, interaction, and replay evidence for Shadow Crime Lab.

All browser work is intentionally performed in headless Chromium, in a new
temporary Playwright context for each capture, against a disposable loopback
server.  The helper is evidence plumbing: it is not a computer-use evaluation
and it never attaches to a user browser profile.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import Browser, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "shadow_crime_lab_env"
MECHANIC = "shadow_crime_lab"
MATERIALIZER = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
SETUP = BENCHMARK / "shared_scripts" / "setup_task.py"
SERVER = BENCHMARK / "shared_runtime" / "server" / "weird_captcha_server.py"
APP = BENCHMARK / "shared_runtime" / "app"
GRADER_PATH = BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py"
VERIFIER_PATH = ENVIRONMENT / "tasks" / "shadow_crime_lab_seed_0001" / "verifier.py"
ORIGINAL_TASK = ENVIRONMENT / "tasks" / "shadow_crime_lab_seed_0001" / "task.json"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _reserve_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _stop(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()


def _start_server(task: Path, state_dir: Path, seed: str) -> tuple[subprocess.Popen[bytes], int]:
    subprocess.run(
        [
            "python", "-B", str(SETUP), "--task-json", str(task), "--state-dir", str(state_dir),
            "--seed", seed,
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    port = _reserve_port()
    process = subprocess.Popen(
        [
            "python", "-B", str(SERVER), "--host", "127.0.0.1", "--port", str(port),
            "--app-dir", str(APP), "--state-dir", str(state_dir),
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "WEIRD_CAPTCHA_TIME_MODE": "paused",
            "WEIRD_CAPTCHA_START_PAUSED": "1",
            "WEIRD_CAPTCHA_CHALLENGE_SEED": seed,
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5).read()
            return process, port
        except Exception:  # noqa: BLE001 - health polling intentionally retries.
            time.sleep(0.1)
    process.kill()
    raise TimeoutError(f"Shadow Crime Lab evidence server did not start for {task}")


def _normalised_baseline(value: dict) -> dict:
    result = copy.deepcopy(value)
    for key in ("task_id", "control_condition"):
        result.pop(key, None)
    return result


def _normalised_interaction_world(value: dict) -> dict:
    result = copy.deepcopy(value)
    result.pop("task_id", None)
    result.pop("prompt", None)
    condition = result.pop("control_condition", None)
    if not isinstance(condition, dict):
        raise AssertionError("controlled Shadow Crime Lab state has no control condition")
    condition.pop("interaction", None)
    result["control_condition_without_interaction"] = condition
    return result


def _generate(task: Path, seed: str, state_dir: Path) -> tuple[dict, dict]:
    subprocess.run(
        [
            "python", "-B", str(SETUP), "--task-json", str(task), "--state-dir", str(state_dir),
            "--seed", seed,
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return _read(state_dir / "public_state.json"), _read(state_dir / "ground_truth.json")


def _screen_point(canvas_box: dict, point: dict) -> tuple[float, float]:
    return (
        canvas_box["x"] + float(point["x"]) / 900 * canvas_box["width"],
        canvas_box["y"] + float(point["y"]) / 480 * canvas_box["height"],
    )


def _capture_initial(browser: Browser, task: Path, state_dir: Path, seed: str, screenshot: Path) -> dict:
    process, port = _start_server(task, state_dir, seed)
    context = browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page = context.new_page()
    errors: list[str] = []
    console: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: console.append(message.text) if message.type == "error" else None)
    try:
        page.goto(f"http://127.0.0.1:{port}/?time_mode=paused&start_paused=1", wait_until="networkidle")
        root = page.locator(".shadow-crime-lab")
        root.wait_for()
        image = page.screenshot(path=str(screenshot), full_page=True)
        public = _read(state_dir / "public_state.json")
        truth = _read(state_dir / "ground_truth.json")
        if errors or console:
            raise AssertionError(f"browser errors for {task.parent.name}: page={errors}; console={console}")
        return {
            "image": image,
            "public": public,
            "truth": truth,
            "challenge_id": public["challenge_id"],
            "rendered_interaction": root.get_attribute("data-interaction"),
            "rendered_probe_total": root.get_attribute("data-probe-total"),
            "object_count": len(public["objects"]),
            "probe_count": len(public["probe_zones"]),
            "zone_radius": public["probe_zones"][0]["radius"],
        }
    finally:
        page.close()
        context.close()
        _stop(process)


def _capture_interaction(browser: Browser, task: Path, temporary: Path, interaction: str, out_dir: Path) -> dict:
    state_dir = temporary / f"interaction-{interaction}"
    seed = "shadow-crime-lab-same-world-interaction-evidence"
    process, port = _start_server(task, state_dir, seed)
    context = browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page = context.new_page()
    errors: list[str] = []
    console: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: console.append(message.text) if message.type == "error" else None)
    try:
        page.goto(f"http://127.0.0.1:{port}/?time_mode=paused&start_paused=1", wait_until="networkidle")
        root = page.locator(f'.shadow-crime-lab[data-interaction="{interaction}"]')
        root.wait_for()
        public = _read(state_dir / "public_state.json")
        page.screenshot(path=str(out_dir / f"{interaction}-same-world-initial.png"), full_page=True)
        if interaction == "simplified":
            probe = page.locator(".shadow-proxy-probe").first
            probe.click()
            if root.get_attribute("data-probe-count") != "1":
                raise AssertionError("simplified probe card did not produce a visible causal sample")
            page.screenshot(path=str(out_dir / "simplified-proxy-probe-response.png"), full_page=True)
            action = "click the visible probe-zone card"
        else:
            canvas = page.locator("#shadow-canvas")
            box = canvas.bounding_box()
            if box is None:
                raise AssertionError("full interaction surface has no visible canvas geometry")
            start = _screen_point(box, public["lamp"])
            end = _screen_point(box, public["probe_zones"][0])
            page.mouse.move(*start)
            page.mouse.down()
            page.mouse.move(*end, steps=8)
            if root.get_attribute("data-probe-count") != "1" or root.get_attribute("data-dragging") != "true":
                raise AssertionError("direct lamp drag did not produce the matching visible causal sample")
            page.screenshot(path=str(out_dir / "full-physical-lamp-drag.png"), full_page=True)
            page.mouse.up()
            action = "drag the visible lamp into the same probe zone"
        if errors or console:
            raise AssertionError(f"{interaction} browser errors: page={errors}; console={console}")
        return {
            "challenge_id": public["challenge_id"],
            "rendered_interaction": root.get_attribute("data-interaction"),
            "world": _normalised_interaction_world(public),
            "visible_action": action,
            "first_probe_id": public["probe_zones"][0]["id"],
            "first_probe_position": {"x": public["probe_zones"][0]["x"], "y": public["probe_zones"][0]["y"]},
        }
    finally:
        page.close()
        context.close()
        _stop(process)


def _capture_realtime(browser: Browser, task: Path, temporary: Path, mode: str, out_dir: Path) -> dict:
    """Record the actual shared-clock boundary used for one model observation.

    Shadow Crime Lab has a zero-length, one-frame observation profile because
    its world is static between visible input events.  The capture therefore
    proves clock behavior rather than inventing a task-local live/paused
    branch or claiming that the static image changes over the delay.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    state_dir = temporary / f"realtime-{mode}"
    seed = "shadow-crime-lab-realtime-observation-evidence"
    process, port = _start_server(task, state_dir, seed)
    context = browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page = context.new_page()
    errors: list[str] = []
    console: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: console.append(message.text) if message.type == "error" else None)
    try:
        page.goto(
            f"http://127.0.0.1:{port}/?time_mode={mode}&start_paused=1",
            wait_until="networkidle",
        )
        root = page.locator('.shadow-crime-lab[data-interaction="full"]')
        root.wait_for()
        public = _read(state_dir / "public_state.json")
        if mode == "live":
            page.evaluate("() => WeirdCaptchaTime.resume()")
        before = page.evaluate("() => WeirdCaptchaTime.status()")
        before_image = page.screenshot(path=str(out_dir / f"{mode}-observation-frame-001.png"), full_page=True)
        page.wait_for_timeout(400)
        after = page.evaluate("() => WeirdCaptchaTime.status()")
        after_image = page.screenshot(path=str(out_dir / f"{mode}-after-model-delay.png"), full_page=True)
        delta = float(after["task_time_ms"]) - float(before["task_time_ms"])
        if mode == "live" and delta < 300:
            raise AssertionError(f"live shared clock did not advance through model delay: {delta}ms")
        if mode == "paused" and abs(delta) > 2:
            raise AssertionError(f"paused shared clock advanced through model delay: {delta}ms")

        action_before = page.evaluate("() => WeirdCaptchaTime.status()")
        if mode == "paused":
            page.evaluate("() => WeirdCaptchaTime.resume()")
        canvas = page.locator("#shadow-canvas")
        box = canvas.bounding_box()
        if box is None:
            raise AssertionError("realtime full surface has no visible canvas geometry")
        start = _screen_point(box, public["lamp"])
        end = _screen_point(box, public["probe_zones"][0])
        page.mouse.move(*start)
        page.mouse.down()
        page.mouse.move(*end, steps=6)
        page.wait_for_timeout(35)
        page.mouse.up()
        if mode == "paused":
            page.evaluate("() => WeirdCaptchaTime.pause()")
        action_after = page.evaluate("() => WeirdCaptchaTime.status()")
        if root.get_attribute("data-probe-count") != "1":
            raise AssertionError(f"{mode} resumed visible action did not sample the first probe")
        if float(action_after["task_time_ms"]) <= float(action_before["task_time_ms"]):
            raise AssertionError(f"{mode} task time did not advance while its visible action was applied")
        action_path = out_dir / f"{mode}-resumed-lamp-action.png"
        page.screenshot(path=str(action_path), full_page=True)
        if errors or console:
            raise AssertionError(f"{mode} realtime browser errors: page={errors}; console={console}")
        return {
            "challenge_id": public["challenge_id"],
            "public_world": _normalised_interaction_world(public),
            "before_model_delay": before,
            "after_model_delay": after,
            "model_delay_task_time_delta_ms": delta,
            "observation_frame": f"{mode}-observation-frame-001.png",
            "after_delay_frame": f"{mode}-after-model-delay.png",
            "static_visible_frame_bytes_equal_after_delay": before_image == after_image,
            "action_before": action_before,
            "action_after": action_after,
            "action_task_time_delta_ms": float(action_after["task_time_ms"]) - float(action_before["task_time_ms"]),
            "resumed_action_frame": action_path.name,
        }
    finally:
        page.close()
        context.close()
        _stop(process)


def _capture_generation_contract(tasks: Path, temporary: Path) -> dict:
    baseline: list[dict] = []
    for index, seed in enumerate(("shadow-baseline-alpha", "shadow-baseline-beta", "shadow-baseline-gamma")):
        original_public, original_truth = _generate(ORIGINAL_TASK, seed, temporary / f"original-{index}")
        l4_public, l4_truth = _generate(tasks / "shadow_crime_lab_d4_full_seed_0001" / "task.json", seed, temporary / f"l4-{index}")
        public_equal = _normalised_baseline(original_public) == _normalised_baseline(l4_public)
        truth_equal = _normalised_baseline(original_truth) == _normalised_baseline(l4_truth)
        if not public_equal or not truth_equal or original_public["challenge_id"] != l4_public["challenge_id"]:
            raise AssertionError(f"controlled L4 did not preserve uncontrolled Shadow Crime Lab for {seed}")
        baseline.append({
            "seed": seed,
            "challenge_id": original_public["challenge_id"],
            "public_state_equal_after_only_task_and_control_identity_removed": public_equal,
            "ground_truth_equal_after_only_task_and_control_identity_removed": truth_equal,
        })

    conditions: dict[str, dict] = {}
    for level in range(1, 6):
        seed = f"shadow-profile-pair-{level}"
        simplified_public, simplified_truth = _generate(
            tasks / f"shadow_crime_lab_d{level}_simplified_seed_0001" / "task.json",
            seed,
            temporary / f"d{level}-simplified",
        )
        full_public, full_truth = _generate(
            tasks / f"shadow_crime_lab_d{level}_full_seed_0001" / "task.json",
            seed,
            temporary / f"d{level}-full",
        )
        public_equal = _normalised_interaction_world(simplified_public) == _normalised_interaction_world(full_public)
        truth_equal = _normalised_interaction_world(simplified_truth) == _normalised_interaction_world(full_truth)
        if not public_equal or not truth_equal or simplified_public["challenge_id"] != full_public["challenge_id"]:
            raise AssertionError(f"L{level} modes did not share one generated world")
        condition = simplified_public["control_condition"]
        conditions[str(level)] = {
            "seed": seed,
            "challenge_id": simplified_public["challenge_id"],
            "objects": len(simplified_public["objects"]),
            "probe_zones": len(simplified_public["probe_zones"]),
            "zone_radius": simplified_public["probe_zones"][0]["radius"],
            "difficulty_parameters": condition["difficulty_parameters"],
            "same_generated_public_world_across_interactions": public_equal,
            "same_generated_hidden_world_across_interactions": truth_equal,
        }
    return {
        "environment": ENVIRONMENT.name,
        "baseline": {"difficulty": 4, "interaction": "full", "fixed_seed_comparisons": baseline},
        "all_controlled_conditions": conditions,
    }


def _task_verdict(verifier, exported: dict, temporary: Path, label: str) -> dict:
    exported_path = temporary / f"{label}.json"
    _write(exported_path, exported)

    def copy_from_env(remote: str, destination: str) -> None:
        if remote != "/tmp/task_result.json":
            raise AssertionError(f"unexpected exported-result path {remote}")
        Path(destination).write_bytes(exported_path.read_bytes())

    return verifier.verify_task(env_info={"copy_from_env": copy_from_env})


def _grade_both(grader, verifier, exported: dict, temporary: Path, label: str) -> dict:
    return {
        "server_grader": grader.grade(exported["result"], exported["ground_truth"], exported["public_state"]),
        "exported_task_verifier": _task_verdict(verifier, exported, temporary, label),
    }


def _assert_rejected(label: str, verdicts: dict) -> None:
    if any(value.get("passed") is True for value in verdicts.values()):
        raise AssertionError(f"{label} was incorrectly accepted: {verdicts}")


def _capture_adversarial_replay(browser_live_dir: Path, temporary: Path) -> dict:
    grader = _load("shadow_crime_evidence_grader", GRADER_PATH)
    verifier = _load("shadow_crime_evidence_verifier", VERIFIER_PATH)
    simplified = _read(browser_live_dir / "d4-simplified" / "exported-result.json")
    full = _read(browser_live_dir / "d4-full" / "exported-result.json")
    accepted = {
        "simplified": _grade_both(grader, verifier, simplified, temporary, "accepted-simplified"),
        "full": _grade_both(grader, verifier, full, temporary, "accepted-full"),
    }
    if any(value.get("passed") is not True for mode in accepted.values() for value in mode.values()):
        raise AssertionError(f"recorded browser exports did not pass independent replay: {accepted}")

    sparse_full = copy.deepcopy(full)
    sparse_full["result"]["events"] = [
        event for event in sparse_full["result"]["events"] if event["type"] != "tag_move"
    ]
    for sequence, event in enumerate(sparse_full["result"]["events"], start=1):
        event["seq"] = sequence
    sparse_full_verdicts = _grade_both(grader, verifier, sparse_full, temporary, "sparse-full")
    if any(value.get("passed") is not True for value in sparse_full_verdicts.values()):
        raise AssertionError(f"a sparse full dock-to-polygon tag drop was rejected: {sparse_full_verdicts}")

    wrong_surface: dict[str, dict] = {}
    simplified_wrong = copy.deepcopy(simplified)
    next(event for event in simplified_wrong["result"]["events"] if event["type"] == "proxy_probe")["input_surface"] = "direct_lamp_drag"
    wrong_surface["simplified_proxy_probe_as_direct_drag"] = _grade_both(
        grader, verifier, simplified_wrong, temporary, "wrong-simplified-probe"
    )
    full_wrong = copy.deepcopy(full)
    next(event for event in full_wrong["result"]["events"] if event["type"] == "lamp_start")["input_surface"] = "probe_zone_button"
    wrong_surface["full_direct_drag_as_proxy_probe"] = _grade_both(
        grader, verifier, full_wrong, temporary, "wrong-full-drag"
    )
    for label, verdicts in wrong_surface.items():
        _assert_rejected(label, verdicts)

    stale = copy.deepcopy(simplified)
    stale["result"]["challenge_id"] = "stale-shadow-crime-lab-challenge"
    stale_verdicts = _grade_both(grader, verifier, stale, temporary, "stale")
    _assert_rejected("stale challenge", stale_verdicts)
    return {
        "browser_live_matrix": str(browser_live_dir),
        "accepted_browser_exports": accepted,
        "sparse_full_tag_without_pointermove_callbacks": sparse_full_verdicts,
        "wrong_interaction_sources": wrong_surface,
        "stale_challenge": stale_verdicts,
    }


def _record(capture: dict, screenshot: Path) -> dict:
    return {
        "screenshot": screenshot.name,
        "challenge_id": capture["challenge_id"],
        "rendered_interaction": capture["rendered_interaction"],
        "objects": capture["object_count"],
        "probe_zones": capture["probe_count"],
        "zone_radius": capture["zone_radius"],
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ENVIRONMENT / "evidence_docs")
    parser.add_argument(
        "--browser-live-dir",
        type=Path,
        help="Current repaired live browser matrix; defaults to <out-dir>/browser_live_repaired.",
    )
    parser.add_argument(
        "--browser-paused-dir",
        type=Path,
        help="Current repaired paused browser matrix; defaults to <out-dir>/browser_paused_repaired.",
    )
    parser.add_argument(
        "--static-smoke-dir",
        type=Path,
        help="Current repaired static smoke directory; defaults to <out-dir>/static_browser_smoke_repaired.",
    )
    args = parser.parse_args()
    out_dir = args.out_dir.resolve()
    difficulty_out = out_dir / "difficulty_comparison"
    interaction_out = out_dir / "interaction_comparison"
    browser_live_dir = (args.browser_live_dir or out_dir / "browser_live_repaired").resolve()
    browser_paused_dir = (args.browser_paused_dir or out_dir / "browser_paused_repaired").resolve()
    static_smoke_dir = (args.static_smoke_dir or out_dir / "static_browser_smoke_repaired").resolve()
    difficulty_out.mkdir(parents=True, exist_ok=True)
    interaction_out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="shadow-crime-lab-evidence-") as temporary_name:
        temporary = Path(temporary_name)
        materialized_root = temporary / "materialized"
        subprocess.run(
            ["python", str(MATERIALIZER), "--environment", ENVIRONMENT.name, "--output-root", str(materialized_root)],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        tasks = materialized_root / ENVIRONMENT.name / "tasks"
        generation_contract = _capture_generation_contract(tasks, temporary / "generation")
        _write(out_dir / "generation_contract.json", generation_contract)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                baseline_seed = "shadow-crime-lab-original-l4-visual-evidence"
                original_path = difficulty_out / "original-uncontrolled-initial.png"
                l4_path = difficulty_out / "controlled-l4-full-initial.png"
                original = _capture_initial(browser, ORIGINAL_TASK, temporary / "original", baseline_seed, original_path)
                l4 = _capture_initial(
                    browser,
                    tasks / "shadow_crime_lab_d4_full_seed_0001" / "task.json",
                    temporary / "controlled-l4",
                    baseline_seed,
                    l4_path,
                )
                adjacent: dict[str, dict] = {}
                adjacent_seed = "shadow-crime-lab-adjacent-difficulty-evidence"
                for level in (3, 4, 5):
                    screenshot = difficulty_out / f"adjacent-l{level}-full-initial.png"
                    adjacent[str(level)] = _capture_initial(
                        browser,
                        tasks / f"shadow_crime_lab_d{level}_full_seed_0001" / "task.json",
                        temporary / f"adjacent-l{level}",
                        adjacent_seed,
                        screenshot,
                    )
                interactions = {
                    interaction: _capture_interaction(
                        browser,
                        tasks / f"shadow_crime_lab_d4_{interaction}_seed_0001" / "task.json",
                        temporary,
                        interaction,
                        interaction_out,
                    )
                    for interaction in ("simplified", "full")
                }
                realtime = {
                    mode: _capture_realtime(
                        browser,
                        tasks / "shadow_crime_lab_d4_full_seed_0001" / "task.json",
                        temporary,
                        mode,
                        out_dir / "realtime_observations",
                    )
                    for mode in ("live", "paused")
                }
            finally:
                browser.close()

        public_equal = _normalised_baseline(original["public"]) == _normalised_baseline(l4["public"])
        truth_equal = _normalised_baseline(original["truth"]) == _normalised_baseline(l4["truth"])
        screenshot_equal = original["image"] == l4["image"]
        if not public_equal or not truth_equal or not screenshot_equal:
            raise AssertionError("uncontrolled original and controlled L4/full failed fixed-seed visual preservation")
        difficulty_summary = {
            "environment": ENVIRONMENT.name,
            "baseline": {
                "difficulty": 4,
                "interaction": "full",
                "seed": baseline_seed,
                "uncontrolled": _record(original, original_path),
                "controlled_l4": _record(l4, l4_path),
                "public_state_equal_after_only_task_and_control_identity_removed": public_equal,
                "ground_truth_equal_after_only_task_and_control_identity_removed": truth_equal,
                "visible_screenshot_bytes_equal": screenshot_equal,
            },
            "adjacent_difficulties": {
                "seed": adjacent_seed,
                **{
                    str(level): _record(adjacent[str(level)], difficulty_out / f"adjacent-l{level}-full-initial.png")
                    for level in (3, 4, 5)
                },
            },
        }
        _write(difficulty_out / "summary.json", difficulty_summary)

        same_world = interactions["simplified"]["world"] == interactions["full"]["world"]
        if not same_world:
            raise AssertionError("simplified and full L4 surfaces changed the generated world")
        interaction_summary = {
            "environment": ENVIRONMENT.name,
            "difficulty": 4,
            "same_generated_world": same_world,
            "challenge_id": interactions["full"]["challenge_id"],
            "interactions": {
                interaction: {
                    "challenge_id": item["challenge_id"],
                    "rendered_interaction": item["rendered_interaction"],
                    "first_probe_id": item["first_probe_id"],
                    "first_probe_position": item["first_probe_position"],
                    "visible_action": item["visible_action"],
                }
                for interaction, item in interactions.items()
            },
        }
        _write(interaction_out / "summary.json", interaction_summary)

        if realtime["live"]["public_world"] != realtime["paused"]["public_world"]:
            raise AssertionError("live and paused model observations did not use one generated world")
        realtime_summary = {
            "environment": ENVIRONMENT.name,
            "difficulty": 4,
            "interaction": "full",
            "shared_real_time_profile": _read(ENVIRONMENT / "controls.json")["real_time"],
            "modes": realtime,
        }
        _write(out_dir / "realtime_observations" / "summary.json", realtime_summary)

        adversarial = _capture_adversarial_replay(browser_live_dir, temporary / "adversarial")
        _write(out_dir / "adversarial_transcript_rejection.json", adversarial)

    expected = [
        out_dir / "generation_contract.json",
        out_dir / "adversarial_transcript_rejection.json",
        difficulty_out / "summary.json",
        difficulty_out / "original-uncontrolled-initial.png",
        difficulty_out / "controlled-l4-full-initial.png",
        difficulty_out / "adjacent-l3-full-initial.png",
        difficulty_out / "adjacent-l4-full-initial.png",
        difficulty_out / "adjacent-l5-full-initial.png",
        interaction_out / "summary.json",
        interaction_out / "simplified-same-world-initial.png",
        interaction_out / "simplified-proxy-probe-response.png",
        interaction_out / "full-same-world-initial.png",
        interaction_out / "full-physical-lamp-drag.png",
        out_dir / "realtime_observations" / "summary.json",
        out_dir / "realtime_observations" / "live-observation-frame-001.png",
        out_dir / "realtime_observations" / "live-after-model-delay.png",
        out_dir / "realtime_observations" / "live-resumed-lamp-action.png",
        out_dir / "realtime_observations" / "paused-observation-frame-001.png",
        out_dir / "realtime_observations" / "paused-after-model-delay.png",
        out_dir / "realtime_observations" / "paused-resumed-lamp-action.png",
        browser_live_dir / "summary.json",
        browser_live_dir / "d4-full" / "shadow_crime_lab-active-causal-probes.png",
        browser_live_dir / "d4-full" / "shadow_crime_lab-solved-forged-shadow-tag.png",
        browser_live_dir / "d4-full" / "pass.png",
        browser_live_dir / "d4-simplified" / "shadow_crime_lab-solved-forged-shadow-tag.png",
        browser_paused_dir / "summary.json",
        static_smoke_dir / "summary.json",
    ]
    missing = [str(path) for path in expected if not path.is_file()]
    if missing:
        raise AssertionError(f"evidence capture did not create: {missing}")
    manifest = {
        "environment": ENVIRONMENT.name,
        "capture": "headless Playwright with a fresh temporary context per page and loopback-only servers",
        "repaired_browser_matrices": {
            "live": str(browser_live_dir),
            "paused": str(browser_paused_dir),
            "static_smoke": str(static_smoke_dir),
        },
        "artifacts": {
            str(path.relative_to(out_dir)): {"sha256": _sha256(path), "bytes": path.stat().st_size}
            for path in expected
        },
    }
    _write(out_dir / "evidence_manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
