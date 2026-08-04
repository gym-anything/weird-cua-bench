#!/usr/bin/env python3
"""Capture the configured live and paused observation windows headlessly."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "trace_shape_without_walls_env"
MECHANIC = "trace_shape_without_walls"
APP_DIR = BENCHMARK / "shared_runtime" / "app"
SERVER = BENCHMARK / "shared_runtime" / "server" / "weird_captcha_server.py"
SETUP = BENCHMARK / "shared_scripts" / "setup_task.py"
MATERIALIZER = BENCHMARK / "tools" / "materialize_controlled_tasks.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _reserve_port() -> int:
    with socket.socket() as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def _controlled_task(tasks_root: Path) -> Path:
    matches = [
        path
        for path in tasks_root.glob("*/task.json")
        if ((value := _read_json(path).get("metadata") or {}).get("control_condition") or {})
        == {
            "difficulty": 4,
            "interaction": "full",
            "real_time": "live",
            "difficulty_parameters": _read_json(ENVIRONMENT / "controls.json")["difficulty"]["4"]["parameters"],
        }
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected one L4 full controlled task, found {matches}")
    return matches[0]


def _start_server(task_json: Path, state_dir: Path) -> tuple[subprocess.Popen[str], int]:
    subprocess.run(
        [
            "python", "-B", str(SETUP), "--task-json", str(task_json),
            "--state-dir", str(state_dir), "--seed", "trace-observation-evidence",
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    port = _reserve_port()
    process = subprocess.Popen(
        [
            "python", "-B", str(SERVER), "--host", "127.0.0.1", "--port", str(port),
            "--app-dir", str(APP_DIR), "--state-dir", str(state_dir),
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        env=os.environ.copy(),
    )
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            import urllib.request

            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5).read()
            return process, port
        except Exception:
            time.sleep(0.05)
    process.kill()
    raise RuntimeError("headless observation server did not become ready")


def _status(page) -> dict:
    return page.evaluate("() => WeirdCaptchaTime.status()")


def _capture_mode(page, base_url: str, mode: str, output: Path, settings: dict) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    page.goto(
        f"{base_url}/?time_mode={mode}&start_paused={'1' if mode == 'paused' else '0'}",
        wait_until="networkidle",
    )
    shell = page.locator('.blind-corridor-captcha[data-interaction="full"]')
    shell.wait_for(state="visible")
    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.resume()")
    stage = page.locator(".trace-stage").bounding_box()
    if not stage:
        raise RuntimeError("blind-corridor stage is not visible")
    page.mouse.move(stage["x"] + stage["width"] * 0.42, stage["y"] + stage["height"] * 0.46)
    started = _status(page)
    frames = []
    count = int(settings["frames_per_observation"])
    duration = int(settings["observation_window_ms"])
    for index in range(count):
        if index:
            page.wait_for_timeout(duration / (count - 1))
        path = output / f"frame-{index:03d}.png"
        page.screenshot(path=str(path))
        frames.append({
            "path": path.name,
            "offset_ms": round(float(_status(page)["task_time_ms"]) - float(started["task_time_ms"]), 1),
        })
    screen_path = output / "screen-latest-frame.png"
    shutil.copy2(output / f"frame-{count - 1:03d}.png", screen_path)
    after_window = _status(page)
    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.pause()")
    before_delay = _status(page)
    page.screenshot(path=str(output / "before-model-delay.png"))
    page.wait_for_timeout(600)
    after_delay = _status(page)
    page.screenshot(path=str(output / "after-model-delay.png"))
    delay_delta = float(after_delay["task_time_ms"]) - float(before_delay["task_time_ms"])
    if mode == "live" and delay_delta < 420:
        raise AssertionError(f"live task time did not advance during inference delay: {delay_delta}")
    if mode == "paused" and abs(delay_delta) > 2:
        raise AssertionError(f"paused task time advanced during inference delay: {delay_delta}")
    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.resume()")
    action_before = _status(page)
    page.mouse.move(stage["x"] + stage["width"] * 0.57, stage["y"] + stage["height"] * 0.54)
    page.wait_for_timeout(40)
    action_after = _status(page)
    if float(action_after["task_time_ms"]) <= float(action_before["task_time_ms"]):
        raise AssertionError(f"{mode} task did not advance during resumed visible action")
    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.pause()")
    return {
        "frames": frames,
        "screen": screen_path.name,
        "before_window": started,
        "after_window": after_window,
        "before_model_delay": before_delay,
        "after_model_delay": after_delay,
        "model_delay_task_delta_ms": round(delay_delta, 1),
        "before_resumed_action": action_before,
        "after_resumed_action": action_after,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture Trace Shape Without Walls live and paused observation frames with headless Playwright."
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    controls = _read_json(ENVIRONMENT / "controls.json")
    settings = dict(controls["real_time"])
    materializer = _load("trace_observation_materializer", MATERIALIZER)
    temp_root = Path(tempfile.mkdtemp(prefix="trace-shape-observation-"))
    process: subprocess.Popen[str] | None = None
    try:
        materializer.materialize_environment(ENVIRONMENT, temp_root / "materialized")
        task = _controlled_task(temp_root / "materialized" / ENVIRONMENT.name / "tasks")
        process, port = _start_server(task, temp_root / "state")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            summary = {
                "environment": ENVIRONMENT.name,
                "mechanic": MECHANIC,
                "settings": settings,
                "live": _capture_mode(page, f"http://127.0.0.1:{port}", "live", output / "live", settings),
                "paused": _capture_mode(page, f"http://127.0.0.1:{port}", "paused", output / "paused", settings),
            }
            if errors:
                raise AssertionError(f"browser page errors: {errors}")
            context.close()
            browser.close()
        (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2, sort_keys=True))
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    main()
