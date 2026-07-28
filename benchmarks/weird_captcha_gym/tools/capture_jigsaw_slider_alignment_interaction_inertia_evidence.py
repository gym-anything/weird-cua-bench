#!/usr/bin/env python3
"""Capture the shared rail-release physics for both Jigsaw input surfaces."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from smoke_controlled_interaction_ui import BENCH_ROOT, controlled_task, start_server


ROOT = Path(__file__).resolve().parents[3]
ENVIRONMENT = BENCH_ROOT / "environments" / "jigsaw_slider_alignment_env"
MECHANIC = "jigsaw_slider_alignment"
MATERIALIZER_PATH = BENCH_ROOT / "tools" / "materialize_controlled_tasks.py"
RESOLUTION = [1280, 720]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def clock(page) -> dict[str, Any]:
    return page.evaluate("() => WeirdCaptchaTime.status()")


def png_resolution(image: bytes) -> list[int]:
    if image[:8] != b"\x89PNG\r\n\x1a\n" or image[12:16] != b"IHDR":
        raise AssertionError("expected a PNG screenshot")
    return [int.from_bytes(image[16:20], "big"), int.from_bytes(image[20:24], "big")]


def release_rail(page, interaction: str) -> None:
    if interaction == "full":
        carriage = page.locator("#alignment-carriage")
        box = carriage.bounding_box()
        if box is None:
            raise AssertionError("full rail carriage has no visible bounds")
        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] / 2
        direction = int(page.evaluate("""() => {
          const rail = window.jigsawSliderAlignmentModel.rail;
          const limits = window.jigsawSliderAlignmentModel.state.scene.rail;
          return rail <= (Number(limits.minimum_milli) + Number(limits.maximum_milli)) / 2 ? 1 : -1;
        }"""))
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + direction * 120, y)
        page.mouse.up()
    else:
        direction = int(page.evaluate("""() => {
          const rail = window.jigsawSliderAlignmentModel.rail;
          const limits = window.jigsawSliderAlignmentModel.state.scene.rail;
          return rail <= (Number(limits.minimum_milli) + Number(limits.maximum_milli)) / 2 ? 1 : -1;
        }"""))
        page.locator(f'[data-rail-nudge="{50_000 * direction}"]').click()
    page.wait_for_function("() => window.jigsawSliderAlignmentModel.inertia !== null", timeout=3_000)


def capture_case(page, interaction: str, mode: str, out_dir: Path) -> dict[str, Any]:
    if mode == "live":
        page.evaluate("() => WeirdCaptchaTime.resume()")
        release_rail(page, interaction)
    else:
        if clock(page)["state"] != "paused":
            page.evaluate("() => WeirdCaptchaTime.pause()")
        before_action = clock(page)
        page.evaluate("() => WeirdCaptchaTime.resume()")
        release_rail(page, interaction)
        page.wait_for_timeout(120)
        page.evaluate("() => WeirdCaptchaTime.pause()")
        after_action = clock(page)
        if after_action["task_time_ms"] <= before_action["task_time_ms"]:
            raise AssertionError(f"{interaction}/{mode} action did not advance task time")
    page.wait_for_timeout(80)
    before_delay = clock(page)
    before_image = page.screenshot(path=str(out_dir / f"d4-{interaction}-{mode}-before-delay.png"))
    page.wait_for_timeout(800)
    after_delay = clock(page)
    after_image = page.screenshot(path=str(out_dir / f"d4-{interaction}-{mode}-after-delay.png"))
    events = page.evaluate("() => window.jigsawSliderAlignmentModel.events")
    event_types = [str(event.get("type")) for event in events]
    input_sources = sorted({str(event["input_source"]) for event in events if event.get("input_source")})
    if "inertia_sample" not in event_types:
        raise AssertionError(f"{interaction}/{mode} did not emit a friction sample")
    expected_source = "direct_rail_drag" if interaction == "full" else "rail_nudge_button"
    if expected_source not in input_sources:
        raise AssertionError(f"{interaction}/{mode} omitted its expected rail source")
    if interaction == "simplified" and "rail_nudge" not in event_types:
        raise AssertionError("simplified rail release did not record its proxy source")
    if png_resolution(before_image) != RESOLUTION or png_resolution(after_image) != RESOLUTION:
        raise AssertionError(f"{interaction}/{mode} did not retain the 1280x720 observation surface")
    delta = float(after_delay["task_time_ms"] - before_delay["task_time_ms"])
    if mode == "live":
        if delta < 700 or before_image == after_image:
            raise AssertionError(f"{interaction}/live did not visibly coast during the model delay")
    elif abs(delta) > 2 or before_image != after_image:
        raise AssertionError(f"{interaction}/paused changed during the model delay")
    return {
        "before_image": f"d4-{interaction}-{mode}-before-delay.png",
        "after_image": f"d4-{interaction}-{mode}-after-delay.png",
        "before_image_sha256": hashlib.sha256(before_image).hexdigest(),
        "after_image_sha256": hashlib.sha256(after_image).hexdigest(),
        "screenshot_resolution": RESOLUTION,
        "before_model_delay": before_delay,
        "after_model_delay": after_delay,
        "delay_task_time_delta_ms": delta,
        "event_types": event_types,
        "input_sources": input_sources,
        "inertia_sample_count": event_types.count("inertia_sample"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ENVIRONMENT / "evidence_docs" / "interaction_inertia",
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    materializer = load_module("jigsaw_interaction_inertia_materializer", MATERIALIZER_PATH)
    evidence: dict[str, Any] = {
        "environment": ENVIRONMENT.name,
        "difficulty": 4,
        "observation_resolution": RESOLUTION,
        "claim": "Both rail surfaces enter the same timer-driven friction replay after their respective visible release procedures.",
        "interactions": {},
    }
    with tempfile.TemporaryDirectory(prefix="jigsaw-interaction-inertia-") as temporary_name:
        temporary = Path(temporary_name)
        materializer.materialize_environment(ENVIRONMENT, temporary / "materialized")
        tasks_root = temporary / "materialized" / ENVIRONMENT.name / "tasks"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for interaction in ("full", "simplified"):
                task = controlled_task(tasks_root, 4, interaction)
                evidence["interactions"][interaction] = {}
                for mode in ("live", "paused"):
                    state_dir = temporary / f"{interaction}-{mode}"
                    state_dir.mkdir()
                    process, port = start_server(task, MECHANIC, interaction, state_dir)
                    page = browser.new_page(
                        viewport={"width": RESOLUTION[0], "height": RESOLUTION[1]},
                        device_scale_factor=1,
                    )
                    errors: list[str] = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    try:
                        page.goto(
                            f"http://127.0.0.1:{port}/?time_mode={mode}&start_paused=1",
                            wait_until="networkidle",
                        )
                        page.wait_for_function("() => document.querySelector('.alignment-captcha') !== null")
                        if page.locator(".alignment-captcha").get_attribute("data-interaction") != interaction:
                            raise AssertionError(f"rendered the wrong interaction surface: {interaction}")
                        page.screenshot(path=str(args.out_dir / f"d4-{interaction}-{mode}-initial.png"))
                        evidence["interactions"][interaction][mode] = capture_case(
                            page, interaction, mode, args.out_dir
                        )
                        if errors:
                            raise AssertionError(f"{interaction}/{mode} browser errors: {errors}")
                    finally:
                        page.close()
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except Exception:
                            process.kill()
            browser.close()
    path = args.out_dir / "interaction-inertia.json"
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
