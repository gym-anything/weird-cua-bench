#!/usr/bin/env python3
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

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENV_ROOT = BENCHMARK / "environments" / "domino_autopsy_env"
APP_DIR = BENCHMARK / "shared_runtime" / "app"
SETUP = BENCHMARK / "shared_scripts" / "setup_task.py"
SERVER = BENCHMARK / "shared_runtime" / "server" / "weird_captcha_server.py"
MATERIALIZER = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
EXPORT = BENCHMARK / "shared_scripts" / "export_result.sh"
VERIFIERS = BENCHMARK / "shared_runtime" / "verifier_helpers.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture Domino Autopsy live/paused model observations and timing evidence."
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def world_fingerprint(public_state: dict) -> str:
    value = copy.deepcopy(public_state)
    for key in ("task_id", "challenge_id", "control_condition"):
        value.pop(key, None)
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def controlled_task(tasks_root: Path, difficulty: int, interaction: str) -> Path:
    matches = []
    for path in tasks_root.glob("*/task.json"):
        condition = (read_json(path).get("metadata") or {}).get("control_condition") or {}
        if (
            int(condition.get("difficulty") or 0) == difficulty
            and condition.get("interaction") == interaction
        ):
            matches.append(path)
    if len(matches) != 1:
        raise AssertionError(
            f"expected one level {difficulty} {interaction} task, found {matches}"
        )
    return matches[0]


def reserve_port() -> int:
    with socket.socket() as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def start_server(task_json: Path, state_dir: Path, seed: str) -> tuple[subprocess.Popen, int]:
    subprocess.run(
        [
            "python",
            "-B",
            str(SETUP),
            "--task-json",
            str(task_json),
            "--state-dir",
            str(state_dir),
            "--seed",
            seed,
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    # Keep both real-time modes on the exact generated seed. The live server's
    # normal refresh regeneration is separately exercised by the matrix smoke.
    (state_dir / "current_task.json").unlink()
    port = reserve_port()
    process = subprocess.Popen(
        [
            "python",
            "-B",
            str(SERVER),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--app-dir",
            str(APP_DIR),
            "--state-dir",
            str(state_dir),
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            import urllib.request

            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=.5).read()
            return process, port
        except Exception:
            time.sleep(.1)
    process.kill()
    raise RuntimeError("Domino evidence server did not start")


def canvas_point(box: dict, x: float, y: float) -> tuple[float, float]:
    return (
        float(box["x"]) + x * float(box["width"]) / 720,
        float(box["y"]) + y * float(box["height"]) / 410,
    )


def place_dominoes(page, truth: dict, time_mode: str, interaction: str) -> dict:
    box = page.locator(".domino-physics-canvas").bounding_box()
    if not box:
        raise AssertionError("Domino canvas has no visible bounds")
    action_timing = {}
    for index, (domino_id, target) in enumerate(zip(truth["loose_ids"], truth["target_slots"])):
        position = page.evaluate(
            "id => ({x: dominoModel.bodiesById[id].position.x, y: dominoModel.bodiesById[id].position.y})",
            domino_id,
        )
        start = canvas_point(box, float(position["x"]), float(position["y"]))
        end = canvas_point(box, float(target["x"]), float(target["y"]))
        if time_mode == "paused":
            before = page.evaluate("WeirdCaptchaTime.status()")
            page.evaluate("WeirdCaptchaTime.resume()")
        if interaction == "simplified":
            page.mouse.click(*start)
            page.mouse.click(*end)
        else:
            page.mouse.move(*start)
            page.mouse.down()
            page.mouse.move(*end, steps=10)
            page.mouse.up()
        if time_mode == "paused":
            page.evaluate("WeirdCaptchaTime.pause()")
            after = page.evaluate("WeirdCaptchaTime.status()")
            if index == 0:
                action_timing = {
                    "before_task_time_ms": before["task_time_ms"],
                    "after_task_time_ms": after["task_time_ms"],
                    "task_time_delta_ms": after["task_time_ms"] - before["task_time_ms"],
                }
        for _ in range(14):
            angle = float(
                page.evaluate(
                    "id => dominoAxisAngle(dominoModel.bodiesById[id].angle * 180 / Math.PI)",
                    domino_id,
                )
            )
            if abs(angle) <= 8:
                break
            if time_mode == "paused":
                page.evaluate("WeirdCaptchaTime.resume()")
            page.locator("#domino-rotate-right").click()
            if time_mode == "paused":
                page.evaluate("WeirdCaptchaTime.pause()")
        else:
            raise AssertionError(f"could not level {domino_id}")
        if index == 0:
            if time_mode == "paused":
                page.evaluate("WeirdCaptchaTime.resume()")
            page.locator("#domino-flip").click()
            if time_mode == "paused":
                page.evaluate("WeirdCaptchaTime.pause()")
    return action_timing


def capture_observation(page, mode: str, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    targets = [0, 200, 400, 600, 800, 1000]
    frames = []
    start_wall = time.monotonic()
    start_task = float(page.evaluate("WeirdCaptchaTime.status().task_time_ms"))
    if mode == "paused":
        page.evaluate("WeirdCaptchaTime.resume()")
    for index, target in enumerate(targets):
        remaining = target / 1000 - (time.monotonic() - start_wall)
        if remaining > 0:
            page.wait_for_timeout(remaining * 1000)
        if mode == "paused" and index == len(targets) - 1:
            page.evaluate("WeirdCaptchaTime.pause()")
        path = out_dir / f"frame-{index + 1:02d}.png"
        page.screenshot(path=str(path))
        task_time = float(page.evaluate("WeirdCaptchaTime.status().task_time_ms"))
        frames.append(
            {
                "path": str(path.relative_to(out_dir.parent.parent)),
                "target_offset_ms": target,
                "task_offset_ms": round(task_time - start_task, 3),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return {
        "screen": frames[-1]["path"],
        "frames": frames,
        "observation_window_ms": 1000,
        "frames_per_observation": 6,
    }


def inference_delay(page, mode: str, out_dir: Path) -> dict:
    before = page.evaluate("WeirdCaptchaTime.status()")
    before_path = out_dir / "inference-before.png"
    page.screenshot(path=str(before_path))
    page.wait_for_timeout(700)
    after_path = out_dir / "inference-after.png"
    page.screenshot(path=str(after_path))
    after = page.evaluate("WeirdCaptchaTime.status()")
    return {
        "mode": mode,
        "wall_delay_ms": 700,
        "before_task_time_ms": before["task_time_ms"],
        "after_task_time_ms": after["task_time_ms"],
        "task_time_delta_ms": round(after["task_time_ms"] - before["task_time_ms"], 3),
        "screenshots_identical": before_path.read_bytes() == after_path.read_bytes(),
    }


def run_mode(browser, task_json: Path, mode: str, root: Path) -> dict:
    state_dir = root / f"state-{mode}"
    if state_dir.exists():
        shutil.rmtree(state_dir)
    state_dir.mkdir(parents=True)
    process, port = start_server(task_json, state_dir, "domino-realtime-shared-seed")
    errors: list[str] = []
    page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page.on("pageerror", lambda error: errors.append(str(error)))
    mode_dir = root / "observations" / mode
    mode_dir.mkdir(parents=True, exist_ok=True)
    try:
        page.goto(
            f"http://127.0.0.1:{port}/?time_mode={mode}&start_paused={'1' if mode == 'paused' else '0'}",
            wait_until="networkidle",
        )
        expect(page.locator(".domino-captcha")).to_have_attribute("data-interaction", "full")
        truth = read_json(state_dir / "ground_truth.json")
        public = read_json(state_dir / "public_state.json")
        if mode == "paused":
            page.evaluate("WeirdCaptchaTime.resume()")
            page.wait_for_timeout(50)
            page.evaluate("WeirdCaptchaTime.pause()")
        page.screenshot(path=str(mode_dir / "prepared-initial.png"))
        action_timing = place_dominoes(page, truth, mode, "full")
        if mode == "paused":
            page.evaluate("WeirdCaptchaTime.resume()")
        page.locator("#domino-run").click()
        if mode == "paused":
            page.evaluate("WeirdCaptchaTime.pause()")
        observation = capture_observation(page, mode, mode_dir)
        delay = inference_delay(page, mode, mode_dir)

        if mode == "paused":
            page.evaluate("WeirdCaptchaTime.resume()")
        page.wait_for_function("dominoModel.mode === 'result'", timeout=11_000)
        expect(page.locator(".domino-verdict")).to_contain_text("PHYSICS PASS")
        page.locator("#domino-submit").click()
        expect(page.locator(".readout")).to_have_attribute("data-status", "passed", timeout=8_000)
        if mode == "paused":
            page.evaluate("WeirdCaptchaTime.pause()")
        page.screenshot(path=str(mode_dir / "final-pass.png"))
        result = read_json(state_dir / "result.json")
        return {
            "mode": mode,
            "world": {
                "challenge_id": public["challenge_id"],
                "fixed": public["board"]["fixed"],
                "loose": public["board"]["loose"],
                "bell": public["board"]["bell"],
            },
            "action_timing": action_timing,
            "observation": observation,
            "inference_delay": delay,
            "server_grade": result["server_grade"],
            "browser_errors": errors,
            "state_dir": str(state_dir),
        }
    finally:
        page.close()
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()


def export_and_verify(state_dir: Path, artifact_path: Path, verifiers) -> tuple[str, dict]:
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    export_env = os.environ.copy()
    export_env["WEIRD_CAPTCHA_STATE_DIR"] = str(state_dir)
    export_command = subprocess.run(
        ["bash", str(EXPORT)],
        cwd=ROOT,
        env=export_env,
        check=True,
        capture_output=True,
        text=True,
    )
    shutil.copy2("/tmp/task_result.json", artifact_path)
    verification = verifiers.verify_domino_autopsy(read_json(artifact_path))
    if verification.get("passed") is not True or verification.get("score") != 100:
        raise AssertionError(f"export verifier failed: {verification}")
    return export_command.stdout.strip(), verification


def run_matrix_condition(
    browser,
    task_json: Path,
    difficulty: int,
    interaction: str,
    time_mode: str,
    state_root: Path,
    evidence_root: Path,
    verifiers,
) -> dict:
    condition_name = f"d{difficulty}-{interaction}-{time_mode}"
    state_dir = state_root / condition_name
    state_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = evidence_root / condition_name
    evidence_dir.mkdir(parents=True, exist_ok=True)
    process, port = start_server(
        task_json,
        state_dir,
        f"domino-realtime-matrix-d{difficulty}-shared-seed",
    )
    errors: list[str] = []
    page = browser.new_page(
        viewport={"width": 1280, "height": 720},
        device_scale_factor=1,
    )
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(
            (
                f"http://127.0.0.1:{port}/?time_mode={time_mode}"
                f"&start_paused={'1' if time_mode == 'paused' else '0'}"
            ),
            wait_until="networkidle",
        )
        expect(page.locator(".domino-captcha")).to_have_attribute(
            "data-interaction",
            interaction,
        )
        truth = read_json(state_dir / "ground_truth.json")
        public = read_json(state_dir / "public_state.json")
        if time_mode == "paused":
            page.evaluate("WeirdCaptchaTime.resume()")
            page.wait_for_timeout(50)
            page.evaluate("WeirdCaptchaTime.pause()")
        page.screenshot(path=str(evidence_dir / "initial.png"))

        inference_before = page.evaluate("WeirdCaptchaTime.status()")
        page.wait_for_timeout(200)
        inference_after = page.evaluate("WeirdCaptchaTime.status()")
        inference_delta = round(
            float(inference_after["task_time_ms"])
            - float(inference_before["task_time_ms"]),
            3,
        )
        if time_mode == "paused" and inference_delta > 5:
            raise AssertionError(
                f"{condition_name} advanced during paused inference: {inference_delta}"
            )
        if time_mode == "live" and inference_delta < 150:
            raise AssertionError(
                f"{condition_name} failed to advance during live inference: {inference_delta}"
            )

        action_timing = place_dominoes(page, truth, time_mode, interaction)
        if time_mode == "paused":
            page.evaluate("WeirdCaptchaTime.resume()")
        page.locator("#domino-run").click()
        page.wait_for_function("dominoModel.mode === 'result'", timeout=11_000)
        expect(page.locator(".domino-verdict")).to_contain_text("PHYSICS PASS")
        page.locator("#domino-submit").click()
        expect(page.locator(".readout")).to_have_attribute(
            "data-status",
            "passed",
            timeout=8_000,
        )
        if time_mode == "paused":
            page.evaluate("WeirdCaptchaTime.pause()")
        page.screenshot(path=str(evidence_dir / "pass.png"))
        result = read_json(state_dir / "result.json")
        server_grade = result.get("server_grade") or {}
        if server_grade.get("passed") is not True:
            raise AssertionError(
                f"server rejected {condition_name}: {server_grade}"
            )
        export_artifact = evidence_dir / "task_result.json"
        export_stdout, verification = export_and_verify(
            state_dir,
            export_artifact,
            verifiers,
        )
        if errors:
            raise AssertionError(f"browser errors in {condition_name}: {errors}")
        placement_sources = sorted(
            {
                str(source)
                for source in (result.get("placement_sources") or {}).values()
                if source
            }
        )
        return {
            "difficulty": difficulty,
            "interaction": interaction,
            "time_mode": time_mode,
            "passed": True,
            "world_fingerprint": world_fingerprint(public),
            "challenge_id": public["challenge_id"],
            "inference_delay": {
                "wall_delay_ms": 200,
                "task_time_delta_ms": inference_delta,
            },
            "action_timing": action_timing,
            "input_sources": placement_sources,
            "server_grade": server_grade,
            "export": {
                "artifact": str(export_artifact.relative_to(evidence_root)),
                "command_stdout": export_stdout,
            },
            "verification": verification,
            "browser_errors": errors,
            "screenshots": {
                "initial": str((evidence_dir / "initial.png").relative_to(evidence_root)),
                "pass": str((evidence_dir / "pass.png").relative_to(evidence_root)),
            },
        }
    finally:
        page.close()
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()


def capture_realtime_matrix(
    browser,
    tasks_root: Path,
    temporary: Path,
    out_dir: Path,
    verifiers,
) -> dict:
    matrix_root = out_dir / "matrix"
    matrix_root.mkdir(parents=True, exist_ok=True)
    entries = []
    for difficulty in range(1, 6):
        for interaction in ("simplified", "full"):
            task_json = controlled_task(tasks_root, difficulty, interaction)
            for time_mode in ("paused", "live"):
                entries.append(
                    run_matrix_condition(
                        browser,
                        task_json,
                        difficulty,
                        interaction,
                        time_mode,
                        temporary / "matrix-state",
                        matrix_root,
                        verifiers,
                    )
                )

    expected_source = {
        "simplified": "domino_click_place",
        "full": "domino_drag",
    }
    for entry in entries:
        if entry["input_sources"] != [expected_source[entry["interaction"]]]:
            raise AssertionError(
                f"wrong input source in realtime matrix entry: {entry}"
            )
        if entry["time_mode"] == "paused":
            if entry["inference_delay"]["task_time_delta_ms"] > 5:
                raise AssertionError(f"paused matrix entry advanced: {entry}")
            if entry["action_timing"]["task_time_delta_ms"] <= 0:
                raise AssertionError(f"paused matrix action did not advance: {entry}")
        elif entry["inference_delay"]["task_time_delta_ms"] < 150:
            raise AssertionError(f"live matrix entry did not advance: {entry}")

    same_world_by_difficulty = {}
    for difficulty in range(1, 6):
        fingerprints = {
            entry["world_fingerprint"]
            for entry in entries
            if entry["difficulty"] == difficulty
        }
        same_world_by_difficulty[str(difficulty)] = len(fingerprints) == 1
        if len(fingerprints) != 1:
            raise AssertionError(
                f"level {difficulty} differs across interaction/time modes: {fingerprints}"
            )

    summary = {
        "ok": True,
        "condition_count": len(entries),
        "same_world_by_difficulty": same_world_by_difficulty,
        "entries": entries,
    }
    (matrix_root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="domino-realtime-evidence-"))
    try:
        materializer = load_module("domino_evidence_materializer", MATERIALIZER)
        verifiers = load_module("domino_evidence_verifiers", VERIFIERS)
        materialized = temporary / "materialized"
        materializer.materialize_environment(ENV_ROOT, materialized)
        tasks_root = materialized / "domino_autopsy_env" / "tasks"
        task_json = (
            tasks_root
            / "domino_autopsy_d3_full_seed_0001"
            / "task.json"
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            paused = run_mode(browser, task_json, "paused", out_dir)
            live = run_mode(browser, task_json, "live", out_dir)
            realtime_matrix = capture_realtime_matrix(
                browser,
                tasks_root,
                temporary,
                out_dir,
                verifiers,
            )
            browser.close()

        if paused["world"] != live["world"]:
            raise AssertionError("live and paused evidence did not use the same generated world")
        if paused["inference_delay"]["task_time_delta_ms"] > 5:
            raise AssertionError(f"paused inference advanced task time: {paused['inference_delay']}")
        if live["inference_delay"]["task_time_delta_ms"] < 600:
            raise AssertionError(f"live inference failed to advance task time: {live['inference_delay']}")
        if paused["action_timing"]["task_time_delta_ms"] <= 0:
            raise AssertionError(f"paused action did not run with the task resumed: {paused['action_timing']}")
        if paused["browser_errors"] or live["browser_errors"]:
            raise AssertionError(f"browser errors: paused={paused['browser_errors']} live={live['browser_errors']}")

        paused_state_dir = Path(paused.pop("state_dir"))
        live_state_dir = Path(live.pop("state_dir"))
        export_dir = out_dir / "export"
        export_dir.mkdir(parents=True, exist_ok=True)
        export_env = os.environ.copy()
        export_env["WEIRD_CAPTCHA_STATE_DIR"] = str(paused_state_dir)
        export_command = subprocess.run(
            ["bash", str(EXPORT)],
            cwd=ROOT,
            env=export_env,
            check=True,
            capture_output=True,
            text=True,
        )
        exported_path = export_dir / "paused_task_result.json"
        shutil.copy2("/tmp/task_result.json", exported_path)
        exported = read_json(exported_path)
        verification = verifiers.verify_domino_autopsy(exported)
        if verification.get("passed") is not True or verification.get("score") != 100:
            raise AssertionError(f"export verifier failed: {verification}")
        shutil.rmtree(paused_state_dir)
        shutil.rmtree(live_state_dir)

        summary = {
            "ok": True,
            "same_generated_world": True,
            "paused": paused,
            "live": live,
            "matrix": {
                "artifact": "matrix/summary.json",
                "condition_count": realtime_matrix["condition_count"],
                "same_world_by_difficulty": realtime_matrix[
                    "same_world_by_difficulty"
                ],
            },
            "export": {
                "command_stdout": export_command.stdout.strip(),
                "artifact": str(exported_path.relative_to(out_dir)),
                "verification": verification,
            },
        }
        (out_dir / "realtime_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


if __name__ == "__main__":
    main()
