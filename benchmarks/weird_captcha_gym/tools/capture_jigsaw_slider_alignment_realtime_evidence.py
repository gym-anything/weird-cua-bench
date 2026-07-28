#!/usr/bin/env python3
"""Capture live-versus-paused inertial observations for Jigsaw Slider Alignment."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

from smoke_controlled_interaction_ui import BENCH_ROOT, controlled_task, read_json, start_server


ROOT = Path(__file__).resolve().parents[3]
ENVIRONMENT = BENCH_ROOT / "environments" / "jigsaw_slider_alignment_env"
MECHANIC = "jigsaw_slider_alignment"
MATERIALIZER_PATH = BENCH_ROOT / "tools" / "materialize_controlled_tasks.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def clock(page) -> dict:
    return page.evaluate("() => WeirdCaptchaTime.status()")


def png_resolution(image: bytes) -> list[int]:
    if image[:8] != b"\x89PNG\r\n\x1a\n" or image[12:16] != b"IHDR":
        raise AssertionError("expected a PNG browser screenshot")
    return [int.from_bytes(image[16:20], "big"), int.from_bytes(image[20:24], "big")]


def fast_release(page) -> None:
    carriage = page.locator("#alignment-carriage")
    box = carriage.bounding_box()
    if box is None:
        raise AssertionError("rail carriage has no visible bounds")
    x = box["x"] + box["width"] / 2
    y = box["y"] + box["height"] / 2
    direction = int(page.evaluate("""() => {
      const scene = window.jigsawSliderAlignmentModel.state.scene;
      const rail = window.jigsawSliderAlignmentModel.rail;
      return rail < (Number(scene.rail.minimum_milli) + Number(scene.rail.maximum_milli)) / 2 ? 1 : -1;
    }"""))
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + direction * 120, y)
    page.mouse.up()
    page.wait_for_function("() => window.jigsawSliderAlignmentModel.inertia !== null", timeout=3_000)


def capture_mode(page, mode: str, out_dir: Path) -> dict:
    if mode == "live":
        page.evaluate("() => WeirdCaptchaTime.resume()")
    else:
        if clock(page)["state"] != "paused":
            page.evaluate("() => WeirdCaptchaTime.pause()")
        before_action = clock(page)
        page.evaluate("() => WeirdCaptchaTime.resume()")
        fast_release(page)
        page.wait_for_timeout(120)
        page.evaluate("() => WeirdCaptchaTime.pause()")
        after_action = clock(page)
        if after_action["task_time_ms"] <= before_action["task_time_ms"]:
            raise AssertionError("paused task did not advance while the drag action was applied")
    if mode == "live":
        fast_release(page)
    page.wait_for_timeout(80)
    before_delay = clock(page)
    before_image = page.screenshot(path=str(out_dir / f"{mode}-before-model-delay.png"))
    page.wait_for_timeout(800)
    after_delay = clock(page)
    after_image = page.screenshot(path=str(out_dir / f"{mode}-after-model-delay.png"))
    screenshot_resolution = png_resolution(before_image)
    if screenshot_resolution != [1280, 720] or png_resolution(after_image) != screenshot_resolution:
        raise AssertionError(f"unexpected screenshot surface: {screenshot_resolution}")
    if mode == "paused":
        if abs(after_delay["task_time_ms"] - before_delay["task_time_ms"]) > 2:
            raise AssertionError("paused task advanced during artificial model delay")
        if before_image != after_image:
            raise AssertionError("paused inertial observation changed during artificial model delay")
    else:
        if after_delay["task_time_ms"] - before_delay["task_time_ms"] < 700:
            raise AssertionError("live task did not advance during artificial model delay")
        if before_image == after_image:
            raise AssertionError("live inertial observation did not change during artificial model delay")
    return {
        "before_model_delay": before_delay,
        "after_model_delay": after_delay,
        "delay_task_time_delta_ms": after_delay["task_time_ms"] - before_delay["task_time_ms"],
        "before_image": f"{mode}-before-model-delay.png",
        "after_image": f"{mode}-after-model-delay.png",
        "before_image_sha256": hashlib.sha256(before_image).hexdigest(),
        "after_image_sha256": hashlib.sha256(after_image).hexdigest(),
        "screenshot_resolution": screenshot_resolution,
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
    environment = read_json(ENVIRONMENT / "env.json")
    screens = [item for item in environment.get("observation") or [] if item.get("type") == "rgb_screen"]
    if len(screens) != 1 or screens[0].get("resolution") != [1280, 720]:
        raise AssertionError("the timing capture must use the original 1280x720 observation surface")
    resolution = screens[0]["resolution"]
    materializer = load_module("jigsaw_alignment_realtime_materializer", MATERIALIZER_PATH)
    with tempfile.TemporaryDirectory(prefix="jigsaw-alignment-realtime-") as temporary:
        temporary_root = Path(temporary)
        materializer.materialize_environment(ENVIRONMENT, temporary_root / "materialized")
        tasks_root = temporary_root / "materialized" / ENVIRONMENT.name / "tasks"
        task = controlled_task(tasks_root, 4, "full")
        evidence: dict[str, object] = {
            "environment": ENVIRONMENT.name,
            "observation_resolution": resolution,
            "task": task.parent.name,
            "modes": {},
        }
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for mode in ("live", "paused"):
                state_dir = temporary_root / mode
                state_dir.mkdir()
                process, port = start_server(task, MECHANIC, "full", state_dir)
                page = browser.new_page(viewport={"width": resolution[0], "height": resolution[1]}, device_scale_factor=1)
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                try:
                    page.goto(f"http://127.0.0.1:{port}/?time_mode={mode}&start_paused=1", wait_until="networkidle")
                    page.wait_for_function("() => document.querySelector('.alignment-captcha') !== null")
                    page.screenshot(path=str(args.out_dir / f"{mode}-initial-observation.png"))
                    evidence["modes"][mode] = capture_mode(page, mode, args.out_dir)
                    if errors:
                        raise AssertionError(f"{mode} browser errors: {errors}")
                finally:
                    page.close()
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except Exception:
                        process.kill()
            browser.close()
    live_delta = float(evidence["modes"]["live"]["delay_task_time_delta_ms"])
    paused_delta = float(evidence["modes"]["paused"]["delay_task_time_delta_ms"])
    if live_delta < 700 or abs(paused_delta) > 2:
        raise AssertionError(f"unexpected model-delay contract: live={live_delta}; paused={paused_delta}")
    (args.out_dir / "realtime-delay.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
