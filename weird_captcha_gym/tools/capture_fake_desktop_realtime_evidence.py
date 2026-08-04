#!/usr/bin/env python3
"""Capture shared-clock live and paused evidence for Fake Desktop."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "fake_desktop_automation_inversion_env"
MATERIALIZER = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
SETUP = BENCHMARK / "shared_scripts" / "setup_task.py"
SERVER = BENCHMARK / "shared_runtime" / "server" / "weird_captcha_server.py"
APP = BENCHMARK / "shared_runtime" / "app"


def reserve_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def start_server(task: Path, state_dir: Path, mode: str) -> tuple[subprocess.Popen[bytes], int]:
    subprocess.run(
        ["python", "-B", str(SETUP), "--task-json", str(task), "--state-dir", str(state_dir), "--seed", "fake-desktop-realtime-evidence"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    port = reserve_port()
    process = subprocess.Popen(
        ["python", "-B", str(SERVER), "--host", "127.0.0.1", "--port", str(port), "--app-dir", str(APP), "--state-dir", str(state_dir)],
        cwd=ROOT,
        env={**os.environ, "WEIRD_CAPTCHA_TIME_MODE": mode, "WEIRD_CAPTCHA_START_PAUSED": "1"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            urlopen(f"http://127.0.0.1:{port}/health", timeout=.5).read()
            return process, port
        except Exception:  # noqa: BLE001 - the server has no readiness event.
            time.sleep(.1)
    process.kill()
    raise TimeoutError("Fake Desktop evidence server did not start")


def status(page) -> dict:
    return page.evaluate("() => WeirdCaptchaTime.status()")


def capture_mode(page, out_dir: Path, mode: str) -> dict:
    page.wait_for_selector('.fake-desktop-captcha[data-interaction="full"]')
    if mode == "live":
        page.evaluate("() => WeirdCaptchaTime.resume()")
    elif status(page)["state"] != "paused":
        page.evaluate("() => WeirdCaptchaTime.pause()")
    # This task is static: its configured one-frame model observation is the
    # current rendered task surface.  The public static inspector separately
    # demonstrates the same shared observation UI.
    page.screenshot(path=str(out_dir / f"{mode}-model-observation.png"))

    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.resume()")
    before_action = status(page)
    page.locator(".fd-reset").click()
    page.wait_for_timeout(100)
    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.pause()")
    after_action = status(page)
    page.screenshot(path=str(out_dir / f"{mode}-before-delay.png"))
    page.wait_for_timeout(900)
    after_delay = status(page)
    page.screenshot(path=str(out_dir / f"{mode}-after-delay.png"))
    return {
        "before_action": before_action,
        "after_action": after_action,
        "after_delay": after_delay,
        "delay_task_time_delta_ms": after_delay["task_time_ms"] - after_action["task_time_ms"],
        "action_task_time_delta_ms": after_action["task_time_ms"] - before_action["task_time_ms"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ENVIRONMENT / "evidence_docs" / "realtime_delay")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="fake-desktop-realtime-") as temporary_name, sync_playwright() as playwright:
        temporary = Path(temporary_name)
        subprocess.run(
            ["python", str(MATERIALIZER), "--environment", ENVIRONMENT.name, "--output-root", str(temporary / "materialized")],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        task = temporary / "materialized" / ENVIRONMENT.name / "tasks" / "fake_desktop_automation_inversion_d3_full_seed_0001" / "task.json"
        browser = playwright.chromium.launch(headless=True)
        evidence: dict[str, object] = {"environment": ENVIRONMENT.name, "task": task.parent.name, "modes": {}}
        for mode in ("live", "paused"):
            state_dir = temporary / mode
            state_dir.mkdir()
            process, port = start_server(task, state_dir, mode)
            page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            try:
                page.goto(f"http://127.0.0.1:{port}/?time_mode={mode}&start_paused=1", wait_until="networkidle")
                result = capture_mode(page, args.out_dir, mode)
                if errors:
                    raise AssertionError(f"{mode} browser errors: {errors}")
                evidence["modes"][mode] = result
            finally:
                page.close()
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
        browser.close()

    live_delta = float(evidence["modes"]["live"]["delay_task_time_delta_ms"])
    paused_delta = float(evidence["modes"]["paused"]["delay_task_time_delta_ms"])
    paused_action_delta = float(evidence["modes"]["paused"]["action_task_time_delta_ms"])
    if live_delta < 700 or abs(paused_delta) > 2 or paused_action_delta <= 0:
        raise AssertionError(
            f"unexpected shared-clock contract: live delay={live_delta}ms; paused delay={paused_delta}ms; paused action={paused_action_delta}ms"
        )
    (args.out_dir / "realtime-delay.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
