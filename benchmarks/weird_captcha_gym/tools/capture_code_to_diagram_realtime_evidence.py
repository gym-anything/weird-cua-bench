#!/usr/bin/env python3
"""Capture the live-versus-paused transient-register evidence for Code-to-Diagram."""
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

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "code_to_diagram_captcha_env"
MATERIALIZER = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
SETUP = BENCHMARK / "shared_scripts" / "setup_task.py"
SERVER = BENCHMARK / "shared_runtime" / "server" / "weird_captcha_server.py"
APP = BENCHMARK / "shared_runtime" / "app"


def reserve_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def controlled_task(tasks_root: Path) -> Path:
    expected = "code_to_diagram_captcha_d4_full_seed_0001"
    task = tasks_root / expected / "task.json"
    if not task.is_file():
        raise FileNotFoundError(task)
    return task


def start_server(task: Path, state_dir: Path, mode: str) -> tuple[subprocess.Popen[bytes], int]:
    subprocess.run(
        ["python", "-B", str(SETUP), "--task-json", str(task), "--state-dir", str(state_dir), "--seed", "code-to-diagram-realtime-evidence"],
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
        except Exception:  # noqa: BLE001 - health endpoint is intentionally retried.
            time.sleep(.1)
    process.kill()
    raise TimeoutError("Code-to-Diagram evidence server did not start")


def status(page) -> dict:
    return page.evaluate("() => WeirdCaptchaTime.status()")


def capture_mode(page, out_dir: Path, mode: str) -> dict:
    page.wait_for_selector('.flow-lab[data-interaction="full"]')
    expect(page.locator("[data-probe-index]").first).to_be_visible()
    if mode == "live":
        page.evaluate("() => WeirdCaptchaTime.resume()")
    else:
        expect(page.locator(".flow-lab")).to_be_visible()
        if status(page)["state"] != "paused":
            page.evaluate("() => WeirdCaptchaTime.pause()")

    before_action = status(page)
    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.resume()")
    page.locator("[data-probe-index]").first.click()
    page.locator("#flow-step").click()
    page.wait_for_timeout(80)
    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.pause()")
    after_action = status(page)
    page.screenshot(path=str(out_dir / f"{mode}-observation-before-delay.png"))
    page.wait_for_timeout(950)
    after_delay = status(page)
    page.screenshot(path=str(out_dir / f"{mode}-observation-after-delay.png"))
    return {
        "before_action": before_action,
        "after_action": after_action,
        "after_delay": after_delay,
        "delay_task_time_delta_ms": after_delay["task_time_ms"] - after_action["task_time_ms"],
        "register_after_delay": page.locator("#flow-current-state").inner_text(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ENVIRONMENT / "evidence_docs" / "realtime_delay",
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="code-to-diagram-realtime-") as temporary_name, sync_playwright() as playwright:
        temporary = Path(temporary_name)
        subprocess.run(
            ["python", str(MATERIALIZER), "--environment", ENVIRONMENT.name, "--output-root", str(temporary / "materialized")],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        task = controlled_task(temporary / "materialized" / ENVIRONMENT.name / "tasks")
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
    if live_delta < 700 or abs(paused_delta) > 2:
        raise AssertionError(f"unexpected delay contract: live {live_delta}ms; paused {paused_delta}ms")
    (args.out_dir / "realtime-delay.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
