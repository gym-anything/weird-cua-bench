#!/usr/bin/env python3
"""Capture visible Wind-Tunnel Seed Courier observation samples.

This companion to ``smoke_controlled_interaction_ui.py`` makes the target
environment's configured five-frame observation policy inspectable with
visible active-flight and paused-hold samples. Screenshot rasterization is
slower than the configured sampling schedule, so the manifest records the
actual task-time offsets rather than presenting these debug screenshots as a
literal evaluator transport trace. It starts only ephemeral headless
Playwright contexts with new browser contexts and serves each task from a
disposable 127.0.0.1 server. It never uses a user's browser, profile,
desktop, or foreground application.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.weird_captcha_gym.tools import materialize_controlled_tasks as materializer
from benchmarks.weird_captcha_gym.tools import smoke_controlled_interaction_ui as browser_smoke


ENVIRONMENT = "wind_tunnel_seed_courier_env"
MECHANIC = "wind_tunnel_seed_courier"
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENV_ROOT = BENCHMARK / "environments" / ENVIRONMENT
CONTROLS = json.loads((ENV_ROOT / "controls.json").read_text(encoding="utf-8"))
VIEWPORT = browser_smoke.observation_viewport(ENV_ROOT)
CAPTURE_SEED = "wind-tunnel-visible-observation-evidence"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ENV_ROOT / "evidence_docs" / "observations",
        help="Directory for screenshots and the observation manifest.",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def open_initial_page(page: Any, port: int, state_dir: Path, mode: str) -> None:
    """Keep the materialized task as the first rendered visible challenge."""
    current_task = state_dir / "current_task.json"
    task_text = current_task.read_text(encoding="utf-8")
    current_task.unlink()
    try:
        page.goto(
            f"http://127.0.0.1:{port}/?time_mode={mode}&start_paused={'1' if mode == 'paused' else '0'}",
            wait_until="networkidle",
        )
    finally:
        current_task.write_text(task_text, encoding="utf-8")


def clock(page: Any) -> dict[str, Any]:
    return page.evaluate("() => WeirdCaptchaTime.status()")


def screenshot_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture_window(page: Any, output: Path, mode: str) -> dict[str, Any]:
    """Record the configured number of visible samples and their actual times."""
    frame_count = int(CONTROLS["real_time"]["frames_per_observation"])
    observation_window_ms = int(CONTROLS["real_time"]["observation_window_ms"])
    if frame_count < 2 or observation_window_ms <= 0:
        raise AssertionError("wind observation configuration must have a finite multi-frame window")
    interval_ms = observation_window_ms / (frame_count - 1)
    frames: list[dict[str, Any]] = []
    for index in range(frame_count):
        path = output / f"frame-{index + 1:02d}.png"
        # The benchmark observation is the declared viewport, not the
        # scrollable document.  A viewport capture also avoids stretching an
        # observation interval with an unnecessary full-document raster.
        page.screenshot(path=str(path))
        status = clock(page)
        frames.append(
            {
                "index": index + 1,
                "file": path.name,
                "task_time_ms": float(status["task_time_ms"]),
                "status": status,
                "sha256": screenshot_hash(path),
            }
        )
        if index + 1 < frame_count:
            page.wait_for_timeout(interval_ms)

    # Keep the latest sample separately so a screenshot consumer can inspect
    # the same final-frame convention used by the evaluator without adding a
    # sixth, later rasterization point.
    shutil.copy2(output / frames[-1]["file"], output / "screen.png")
    start = float(frames[0]["task_time_ms"])
    end = float(frames[-1]["task_time_ms"])
    for frame in frames:
        frame["task_time_offset_ms"] = round(float(frame["task_time_ms"]) - start, 3)
    unique_frames = len({frame["sha256"] for frame in frames})
    if mode == "live":
        if end <= start:
            raise AssertionError("live visible samples did not advance task time")
        if unique_frames < 2:
            raise AssertionError("live observation captured no visible change")
    else:
        if abs(end - start) > 2:
            raise AssertionError(f"paused observation advanced task time: {start} -> {end}")
        if unique_frames != 1:
            raise AssertionError("paused observation did not hold one visible task frame")
    return {
        "configured_frames": frame_count,
        "configured_window_ms": observation_window_ms,
        "requested_frame_interval_ms": interval_ms,
        "task_time_delta_ms": end - start,
        "unique_visible_frames": unique_frames,
        "final_screen_is_latest_frame": (
            screenshot_hash(output / "screen.png") == frames[-1]["sha256"]
        ),
        "sampling_note": (
            "These are visible Playwright screenshot samples. Their recorded task-time offsets "
            "include rasterization time and are not presented as the production evaluator's "
            "literal 600 ms transport schedule."
        ),
        "frames": frames,
    }


def capture_variant(
    browser: Any,
    task_path: Path,
    work_root: Path,
    output: Path,
    *,
    interaction: str,
    mode: str,
) -> dict[str, Any]:
    label = f"l4-{interaction}-{mode}"
    state_dir = work_root / label
    state_dir.mkdir(parents=True, exist_ok=True)
    process, port = browser_smoke.start_server(
        task_path,
        MECHANIC,
        interaction,
        state_dir,
        f"{CAPTURE_SEED}-{interaction}-{mode}",
    )
    context = browser.new_context(viewport=VIEWPORT, device_scale_factor=1)
    page = context.new_page()
    page_errors: list[str] = []
    console_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on(
        "console",
        lambda message: console_errors.append(message.text) if message.type == "error" else None,
    )
    try:
        output.mkdir(parents=True, exist_ok=True)
        open_initial_page(page, port, state_dir, mode)
        root = page.locator(f'[data-interaction="{interaction}"]')
        expect(root).to_be_visible()
        initial_clock = clock(page)
        if mode == "paused":
            if initial_clock["state"] != "paused":
                raise AssertionError(f"paused task did not begin paused: {initial_clock}")
            page.screenshot(path=str(output / "initial.png"))
            page.wait_for_timeout(350)
            after_model_delay = clock(page)
            if abs(float(after_model_delay["task_time_ms"]) - float(initial_clock["task_time_ms"])) > 2:
                raise AssertionError("paused initial model delay advanced task time")
            page.screenshot(path=str(output / "initial-after-model-delay.png"))
            page.evaluate("() => WeirdCaptchaTime.resume()")
        else:
            if initial_clock["state"] != "running":
                raise AssertionError(f"live task did not begin running: {initial_clock}")
            page.screenshot(path=str(output / "initial.png"))
            after_model_delay = initial_clock

        page.locator("#wind-launch").click()
        page.wait_for_function("() => window.windTunnelSeedCourierModel.tick >= 5", timeout=3_000)
        if mode == "paused":
            page.evaluate("() => WeirdCaptchaTime.pause()")
            page.wait_for_function("() => WeirdCaptchaTime.status().state === 'paused'", timeout=1_000)
        flight_clock = clock(page)
        page.screenshot(path=str(output / "flight-before-observation.png"))
        observation = capture_window(page, output, mode)
        if page_errors or console_errors:
            raise AssertionError(
                f"{label}: page errors={page_errors}; console errors={console_errors}"
            )
        return {
            "condition": {
                "difficulty": 4,
                "interaction": interaction,
                "time_mode": mode,
                "configured_observation_window_ms": CONTROLS["real_time"]["observation_window_ms"],
                "configured_frames_per_observation": CONTROLS["real_time"]["frames_per_observation"],
            },
            "challenge_id": read_json(state_dir / "public_state.json")["challenge_id"],
            "initial_clock": initial_clock,
            "after_initial_model_delay": after_model_delay,
            "flight_clock": flight_clock,
            "observation": observation,
            "browser_errors": {"page": page_errors, "console": console_errors},
        }
    finally:
        page.close()
        context.close()
        process.terminate()
        try:
            process.wait(timeout=3)
        except Exception:
            process.kill()


def main() -> None:
    args = parse_args()
    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="wind-tunnel-observation-evidence-") as temporary:
        work_root = Path(temporary)
        materialized_root = work_root / "materialized"
        materializer.materialize_environment(ENV_ROOT, materialized_root)
        tasks_root = materialized_root / ENVIRONMENT / "tasks"
        tasks = {
            interaction: browser_smoke.controlled_task(tasks_root, 4, interaction)
            for interaction in ("simplified", "full")
        }
        results: dict[str, Any] = {}
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for mode in ("live", "paused"):
                    for interaction in ("simplified", "full"):
                        label = f"l4-{interaction}-{mode}"
                        results[label] = capture_variant(
                            browser,
                            tasks[interaction],
                            work_root,
                            output / label,
                            interaction=interaction,
                            mode=mode,
                        )
            finally:
                browser.close()
    summary = {
        "environment": ENVIRONMENT,
        "mechanic": MECHANIC,
        "isolation": {
            "browser": "headless Chromium",
            "context": "fresh Playwright context for each capture",
            "server": "temporary 127.0.0.1 loopback server",
            "browser_profile": "none reused",
        },
        "runs": results,
    }
    write_json(output / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
