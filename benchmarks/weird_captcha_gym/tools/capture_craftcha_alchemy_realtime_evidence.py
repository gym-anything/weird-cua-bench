#!/usr/bin/env python3
"""Capture repeatable live/paused Craftcha real-time evidence in a visible UI."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "craftcha_alchemy_bench_env"
MATERIALIZER = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
SETUP = BENCHMARK / "shared_scripts" / "setup_task.py"
SERVER = BENCHMARK / "shared_runtime" / "server" / "weird_captcha_server.py"
APP = BENCHMARK / "shared_runtime" / "app"
FRAME_COUNT = 8
OBSERVATION_MS = 1200


def reserve_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def task_path(tasks_root: Path) -> Path:
    task = tasks_root / "craftcha_alchemy_bench_d4_full_seed_0001" / "task.json"
    if not task.is_file():
        raise FileNotFoundError(task)
    return task


def public_world_fingerprint(state_dir: Path) -> str:
    public_state = json.loads((state_dir / "public_state.json").read_text(encoding="utf-8"))
    return hashlib.sha256(
        json.dumps(public_state, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def start_server(task: Path, state_dir: Path, mode: str) -> tuple[subprocess.Popen[bytes], int]:
    subprocess.run(
        [
            "python", "-B", str(SETUP), "--task-json", str(task), "--state-dir", str(state_dir),
            "--seed", "craftcha-alchemy-realtime-evidence",
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    port = reserve_port()
    process = subprocess.Popen(
        [
            "python", "-B", str(SERVER), "--host", "127.0.0.1", "--port", str(port),
            "--app-dir", str(APP), "--state-dir", str(state_dir),
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "WEIRD_CAPTCHA_TIME_MODE": mode,
            "WEIRD_CAPTCHA_START_PAUSED": "1",
            "WEIRD_CAPTCHA_CHALLENGE_SEED": "craftcha-alchemy-realtime-evidence",
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5).read()
            return process, port
        except Exception:  # noqa: BLE001 - the health endpoint is intentionally retried.
            time.sleep(0.1)
    process.kill()
    raise TimeoutError("Craftcha evidence server did not start")


def time_status(page) -> dict[str, object]:
    return page.evaluate("() => WeirdCaptchaTime.status()")


def stop_process(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()


def capture_observations(page, out_dir: Path, mode: str) -> dict[str, object]:
    page.wait_for_selector('.alchemy-bench[data-interaction="full"]')
    page.wait_for_selector(".alchemy-recipe-shutter.is-open")
    paused_before_observation = time_status(page)
    page.evaluate("() => WeirdCaptchaTime.resume()")
    frames: list[dict[str, object]] = []
    previous_target = 0.0
    for number in range(1, FRAME_COUNT + 1):
        target = OBSERVATION_MS * (number - 1) / (FRAME_COUNT - 1)
        if target > previous_target:
            page.wait_for_timeout(target - previous_target)
        page.screenshot(path=str(out_dir / f"{mode}-observation-frame-{number:03d}.png"))
        frames.append(
            {
                "frame": number,
                "target_elapsed_ms": target,
                "task_time_ms": time_status(page)["task_time_ms"],
                "recipe": page.locator(".alchemy-bench").get_attribute("data-recipe"),
            }
        )
        previous_target = target
    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.pause()")
    status_after_observation = time_status(page)
    page.screenshot(path=str(out_dir / f"{mode}-observation-after-window.png"))

    before_delay = time_status(page)
    page.wait_for_timeout(760)
    after_delay = time_status(page)
    page.screenshot(path=str(out_dir / f"{mode}-observation-after-delay.png"))

    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.resume()")
    page.wait_for_selector('.alchemy-bench[data-recipe="sealed"]', timeout=9000)
    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.pause()")
    sealed = time_status(page)
    page.screenshot(path=str(out_dir / f"{mode}-recipe-sealed.png"))

    action_before = time_status(page)
    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.resume()")
    page.locator("#alchemy-replay").click()
    page.wait_for_timeout(100)
    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.pause()")
    action_after = time_status(page)
    recipe_after_action = page.locator(".alchemy-bench").get_attribute("data-recipe")
    page.screenshot(path=str(out_dir / f"{mode}-replay-action.png"))

    if recipe_after_action != "open":
        raise AssertionError(f"{mode}: replay did not visibly re-open the recipe")
    if mode == "paused" and action_after["task_time_ms"] <= action_before["task_time_ms"]:
        raise AssertionError("paused action did not advance the shared task clock while resumed")
    return {
        "challenge_id": page.locator(".alchemy-bench").get_attribute("data-challenge-id"),
        "recipe_code": page.locator(".alchemy-recipe-shutter .recipe-card header b").inner_text(),
        "paused_before_observation": paused_before_observation,
        "frames": frames,
        "status_after_observation": status_after_observation,
        "delay_before": before_delay,
        "delay_after": after_delay,
        "delay_task_time_delta_ms": after_delay["task_time_ms"] - before_delay["task_time_ms"],
        "sealed": sealed,
        "action_before": action_before,
        "action_after": action_after,
        "action_task_time_delta_ms": action_after["task_time_ms"] - action_before["task_time_ms"],
        "recipe_after_action": recipe_after_action,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ENVIRONMENT / "evidence_docs" / "realtime")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="craftcha-alchemy-realtime-") as temporary_name, sync_playwright() as playwright:
        temporary = Path(temporary_name)
        subprocess.run(
            ["python", str(MATERIALIZER), "--environment", ENVIRONMENT.name, "--output-root", str(temporary / "materialized")],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        task = task_path(temporary / "materialized" / ENVIRONMENT.name / "tasks")
        browser = playwright.chromium.launch(headless=True)
        evidence: dict[str, object] = {
            "environment": ENVIRONMENT.name,
            "task": task.parent.name,
            "frames_per_observation": FRAME_COUNT,
            "observation_window_ms": OBSERVATION_MS,
            "modes": {},
        }
        try:
            for mode in ("live", "paused"):
                state_dir = temporary / mode
                process, port = start_server(task, state_dir, mode)
                page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                try:
                    page.goto(f"http://127.0.0.1:{port}/?time_mode={mode}&start_paused=1", wait_until="networkidle")
                    result = capture_observations(page, args.out_dir, mode)
                    result["public_world_fingerprint"] = public_world_fingerprint(state_dir)
                    if errors:
                        raise AssertionError(f"{mode} browser errors: {errors}")
                    evidence["modes"][mode] = result
                finally:
                    page.close()
                    stop_process(process)
        finally:
            browser.close()

    live = evidence["modes"]["live"]
    paused = evidence["modes"]["paused"]
    if live["public_world_fingerprint"] != paused["public_world_fingerprint"]:
        raise AssertionError("live and paused checks did not use the same generated challenge")
    if live["delay_task_time_delta_ms"] < 650:
        raise AssertionError(f"live clock did not advance during an agent delay: {live['delay_task_time_delta_ms']}ms")
    if abs(paused["delay_task_time_delta_ms"]) > 5:
        raise AssertionError(f"paused clock advanced during an agent delay: {paused['delay_task_time_delta_ms']}ms")
    (args.out_dir / "realtime-summary.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
