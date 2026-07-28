#!/usr/bin/env python3
"""Capture live and paused model-observation evidence for Modal Terminal Escape."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from PIL import Image, ImageChops, ImageStat
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "exit_vim_terminal_escape_env"
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
        [
            "python",
            "-B",
            str(SETUP),
            "--task-json",
            str(task),
            "--state-dir",
            str(state_dir),
            "--seed",
            "exit-vim-terminal-realtime-evidence",
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
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
            str(APP),
            "--state-dir",
            str(state_dir),
        ],
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
        except Exception:  # noqa: BLE001 - the local server is intentionally retried.
            time.sleep(.1)
    process.kill()
    raise TimeoutError("Modal Terminal Escape evidence server did not start")


def controlled_task(tasks_root: Path) -> Path:
    task = tasks_root / "exit_vim_terminal_escape_d4_full_seed_0001" / "task.json"
    if not task.is_file():
        raise FileNotFoundError(task)
    return task


def status(page) -> dict:
    return page.evaluate("() => WeirdCaptchaTime.status()")


def image_difference(left: bytes, right: bytes) -> float:
    """Return the mean per-channel difference between two raster frames."""
    with Image.open(io.BytesIO(left)).convert("RGB") as left_image, Image.open(io.BytesIO(right)).convert("RGB") as right_image:
        if left_image.size != right_image.size:
            return float("inf")
        return sum(ImageStat.Stat(ImageChops.difference(left_image, right_image)).mean) / 3


def raster_layout(image: Image.Image) -> dict[str, int]:
    """Measure visible UI in independent screen regions, not DOM state."""
    def lit_pixels(box: tuple[int, int, int, int]) -> int:
        region = image.crop(box).convert("RGB")
        return sum(1 for red, green, blue in region.getdata() if max(red, green, blue) >= 55)

    return {
        "header_lit_pixels": lit_pixels((10, 10, 1270, 80)),
        "editor_lit_pixels": lit_pixels((25, 115, 925, 645)),
        "briefing_panel_lit_pixels": lit_pixels((940, 90, 1260, 640)),
        "footer_lit_pixels": lit_pixels((10, 650, 1270, 710)),
    }


def capture_visible_frame(page, out_dir: Path, filename: str, settle_ms: int) -> dict:
    """Capture a settled terminal root, rejecting an unstable compositor frame.

    The terminal root must be visible and settled before a model-facing browser
    viewport capture is requested. The terminal's composited texture needs a
    full settle interval after an initial render or a state change, then we
    sample the viewport three times and retain the closest pair.
    """
    terminal = page.locator(".terminal-escape")
    terminal.wait_for(state="visible")
    page.evaluate(
        """() => {
          const root = document.querySelector('.terminal-escape');
          root.getBoundingClientRect();
          void document.documentElement.offsetHeight;
        }"""
    )
    page.wait_for_timeout(settle_ms)
    samples: list[bytes] = []
    for _ in range(3):
        samples.append(page.screenshot(type="jpeg", quality=100, scale="css"))
        page.wait_for_timeout(120)
    pairs = [
        (image_difference(samples[left], samples[right]), left, right)
        for left in range(len(samples))
        for right in range(left + 1, len(samples))
    ]
    delta, left, right = min(pairs)
    # A blinking cursor can change a few pixels. A partly composited terminal
    # produces a much larger difference, so retain only a settled pair.
    if delta > 2.0:
        raise AssertionError(f"unstable visual capture for {filename}: mean pixel delta {delta:.3f}")
    selected = samples[left]
    (out_dir / filename).write_bytes(selected)
    with Image.open(io.BytesIO(selected)) as image:
        width, height = image.size
        layout = raster_layout(image)
    if width < 1000 or height < 600:
        raise AssertionError(f"unexpected terminal screenshot size for {filename}: {width}x{height}")
    minimum_visible_ui = {
        "header_lit_pixels": 2000,
        "editor_lit_pixels": 9000,
        "briefing_panel_lit_pixels": 5000,
        "footer_lit_pixels": 1000,
    }
    missing = {key: value for key, value in layout.items() if value < minimum_visible_ui[key]}
    if missing:
        raise AssertionError(f"incomplete visual terminal capture for {filename}: {missing}")
    return {
        "path": filename,
        "size": [width, height],
        "sha256": hashlib.sha256(selected).hexdigest(),
        "stability_samples": len(samples),
        "closest_pair": [left, right],
        "mean_pixel_delta": delta,
        "raster_layout": layout,
    }


def current_editor_line(page) -> str:
    return str(page.locator(".terminal-buffer-line.is-current i").inner_text()).strip()


def capture_mode(page, out_dir: Path, mode: str, delay_ms: int, settle_ms: int) -> dict:
    page.wait_for_selector('.terminal-escape[data-interaction="full"]')
    page.wait_for_function("() => WeirdCaptchaTime.status().ready === true")
    if mode == "live":
        page.evaluate("() => WeirdCaptchaTime.resume()")
    else:
        page.evaluate("() => WeirdCaptchaTime.pause()")
    page.wait_for_timeout(50)

    before_path = f"{mode}-model-observation-before-delay.jpg"
    before_frame = capture_visible_frame(page, out_dir, before_path, settle_ms)
    # The observation itself is captured before this status sample. Keeping the
    # clock samples adjacent to the deliberately injected wait excludes the
    # extra settling samples used solely to validate screenshot integrity.
    before_delay = status(page)
    page.wait_for_timeout(delay_ms)
    after_delay = status(page)
    after_path = f"{mode}-model-observation-after-delay.jpg"
    after_delay_frame = capture_visible_frame(page, out_dir, after_path, settle_ms)

    # A paused action resumes the shared clock only while the browser performs
    # the key event; the terminal itself has no live/paused branch. Freeze it
    # again before the compositor-settle interval so that interval cannot be
    # mistaken for task time available to the model.
    editor_line_before_action = current_editor_line(page)
    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.resume()")
        before_key_action = status(page)
        page.locator(".terminal-escape").click(position={"x": 300, "y": 250})
        page.keyboard.press("ArrowDown")
        after_key_action = status(page)
        if current_editor_line(page) == editor_line_before_action:
            raise AssertionError("paused action did not visibly move the editor cursor")
        running_action = after_key_action
        page.evaluate("() => WeirdCaptchaTime.pause()")
        page.wait_for_timeout(settle_ms)
    else:
        before_key_action = status(page)
        page.locator(".terminal-escape").click(position={"x": 300, "y": 250})
        page.keyboard.press("ArrowDown")
        after_key_action = status(page)
        running_action = None
    after_action = status(page)
    action_path = f"{mode}-action-observation.jpg"
    action_frame = capture_visible_frame(page, out_dir, action_path, settle_ms)
    editor_line_after_action = current_editor_line(page)
    if editor_line_before_action == editor_line_after_action:
        raise AssertionError(f"{mode} action did not visibly move the editor cursor")

    frozen_frame_delta = image_difference(
        (out_dir / before_path).read_bytes(),
        (out_dir / after_path).read_bytes(),
    )
    if mode == "paused" and frozen_frame_delta > 0.02:
        raise AssertionError(f"paused before/after inference frames changed visually: {frozen_frame_delta:.3f}")

    return {
        "before_delay": before_delay,
        "after_delay": after_delay,
        "after_action": after_action,
        "running_action": running_action,
        "delay_wall_ms": delay_ms,
        "delay_task_time_delta_ms": after_delay["task_time_ms"] - before_delay["task_time_ms"],
        "key_action_task_time_delta_ms": after_key_action["task_time_ms"] - before_key_action["task_time_ms"],
        "post_key_status_task_time_delta_ms": after_action["task_time_ms"] - after_key_action["task_time_ms"],
        "editor_line_before_action": editor_line_before_action,
        "editor_line_after_action": editor_line_after_action,
        "before_after_frame_mean_pixel_delta": frozen_frame_delta,
        "observation": {
            "screen": before_path,
            "screen_artifact": before_frame,
            "frames": [before_path],
            "frame_artifacts": [before_frame],
            "frames_per_observation": 1,
            "observation_window_ms": 0,
            "after_delay_screen": after_path,
            "after_delay_screen_artifact": after_delay_frame,
            "action_screen": action_path,
            "action_screen_artifact": action_frame,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ENVIRONMENT / "evidence_docs" / "realtime_delay",
    )
    parser.add_argument("--delay-ms", type=int, default=900)
    parser.add_argument("--settle-ms", type=int, default=1600)
    args = parser.parse_args()
    if args.delay_ms < 700:
        raise SystemExit("--delay-ms must be at least 700")
    if args.settle_ms < 1200:
        raise SystemExit("--settle-ms must be at least 1200")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="exit-vim-terminal-realtime-") as temporary_name, sync_playwright() as playwright:
        temporary = Path(temporary_name)
        subprocess.run(
            ["python", str(MATERIALIZER), "--environment", ENVIRONMENT.name, "--output-root", str(temporary / "materialized")],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        task = controlled_task(temporary / "materialized" / ENVIRONMENT.name / "tasks")
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--force-color-profile=srgb"],
        )
        evidence: dict[str, object] = {
            "environment": ENVIRONMENT.name,
            "task": task.parent.name,
            "task_behavior": "static; one model observation frame with a zero-length observation window",
            "capture_surface": "Playwright viewport screenshot of the rendered task UI (1280x720 JPEG)",
            "capture_integrity": "three settled screenshots per evidence frame; raster regions for header, editor, briefing panel, and footer must all be visibly populated",
            "modes": {},
        }
        for mode in ("live", "paused"):
            state_dir = temporary / mode
            state_dir.mkdir()
            process, port = start_server(task, state_dir, mode)
            page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            try:
                page.goto(f"http://127.0.0.1:{port}/?time_mode={mode}&start_paused=1", wait_until="networkidle")
                evidence["modes"][mode] = capture_mode(page, args.out_dir, mode, args.delay_ms, args.settle_ms)
                if errors:
                    raise AssertionError(f"{mode} browser errors: {errors}")
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
    if live_delta < args.delay_ms - 160 or abs(paused_delta) > 2:
        raise AssertionError(f"unexpected inference-delay contract: live {live_delta}ms; paused {paused_delta}ms")
    (args.out_dir / "realtime-delay.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
