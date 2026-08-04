#!/usr/bin/env python3
"""Capture visible live-versus-paused evidence for Impossible Ecology."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import io
import json
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageStat
from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "impossible_ecology_env"
MATERIALIZER = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
SMOKE = BENCHMARK / "tools" / "smoke_controlled_interaction_ui.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pixel_difference(first: bytes, second: bytes) -> float:
    left = Image.open(io.BytesIO(first)).convert("RGB")
    right = Image.open(io.BytesIO(second)).convert("RGB")
    return sum(ImageStat.Stat(ImageChops.difference(left, right)).mean) / 3


def time_status(page) -> dict:
    return page.evaluate("() => WeirdCaptchaTime.status()")


def task_for_level(tasks_root: Path) -> Path:
    for candidate in tasks_root.glob("*/task.json"):
        metadata = json.loads(candidate.read_text(encoding="utf-8")).get("metadata") or {}
        condition = metadata.get("control_condition") or {}
        if condition.get("difficulty") == 4 and condition.get("interaction") == "full":
            return candidate
    raise RuntimeError("materialized L4 full Impossible Ecology task is missing")


def observation_viewport() -> dict[str, int]:
    specification = json.loads((ENVIRONMENT / "env.json").read_text(encoding="utf-8"))
    screens = [item for item in specification.get("observation", []) if item.get("type") == "rgb_screen"]
    if len(screens) != 1:
        raise AssertionError("Impossible Ecology must declare exactly one rgb_screen observation")
    resolution = screens[0].get("resolution")
    if not isinstance(resolution, list) or len(resolution) != 2 or not all(isinstance(value, int) and value > 0 for value in resolution):
        raise AssertionError("Impossible Ecology rgb_screen resolution is malformed")
    return {"width": resolution[0], "height": resolution[1]}


def capture_mode(page, *, base: str, mode: str, out_dir: Path) -> dict:
    start_paused = mode == "paused"
    page.goto(
        f"{base}/?time_mode={mode}&start_paused={'1' if start_paused else '0'}",
        wait_until="networkidle",
    )
    expect(page.locator('.impossible-ecology-captcha[data-interaction="full"]')).to_be_visible()
    page.screenshot(path=str(out_dir / f"{mode}-initial.png"))
    initial = time_status(page)
    page.locator(".eco-calibrate").click()
    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.resume()")
    frames = []
    for index in range(6):
        if index:
            page.wait_for_timeout(160)
        frame_path = out_dir / f"{mode}-observation-frame-{index + 1}.png"
        page.screenshot(path=str(frame_path))
        frames.append({
            "path": frame_path.name,
            "offset_ms": index * 160,
            "task_time_ms": time_status(page)["task_time_ms"],
        })
    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.pause()")
    observation_end = time_status(page)
    before_delay = page.screenshot(path=str(out_dir / f"{mode}-before-model-delay.png"))
    delay_before = time_status(page)
    page.wait_for_timeout(900)
    after_delay = page.screenshot(path=str(out_dir / f"{mode}-after-model-delay.png"))
    delay_after = time_status(page)
    delay_task_delta = float(delay_after["task_time_ms"]) - float(delay_before["task_time_ms"])
    delay_difference = pixel_difference(before_delay, after_delay)
    if mode == "paused":
        if abs(delay_task_delta) > 1:
            raise AssertionError(f"paused ecology advanced during model delay: {delay_task_delta}")
        if delay_difference > 0.02:
            raise AssertionError(f"paused ecology visibly changed during model delay: {delay_difference}")
        page.evaluate("() => WeirdCaptchaTime.resume()")
    elif delay_task_delta < 700:
        raise AssertionError(f"live ecology did not advance during model delay: {delay_task_delta}")

    # Let the visible calibration film finish, then resume the world while a
    # visible field action is performed. This demonstrates that paused mode
    # does not freeze the action itself.
    page.wait_for_timeout(1250)
    page.locator('[data-field="CLIMATE"]').click()
    arena = page.locator(".eco-arena").bounding_box()
    if not arena:
        raise AssertionError("ecology arena is not visible for the resumed action")
    action_before = time_status(page)
    page.mouse.move(arena["x"] + arena["width"] * .72, arena["y"] + arena["height"] * .28)
    page.mouse.down()
    page.wait_for_timeout(180)
    page.mouse.up()
    action_after = time_status(page)
    page.screenshot(path=str(out_dir / f"{mode}-resumed-pointer-action.png"))
    if float(action_after["task_time_ms"]) <= float(action_before["task_time_ms"]):
        raise AssertionError(f"{mode} ecology action did not advance task time")
    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.pause()")
    final = time_status(page)
    return {
        "initial": initial,
        "frames": frames,
        "after_observation": observation_end,
        "delay_before": delay_before,
        "delay_after": delay_after,
        "delay_task_delta_ms": delay_task_delta,
        "delay_image_difference": delay_difference,
        "action_before": action_before,
        "action_after": action_after,
        "final": final,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ENVIRONMENT / "evidence_docs" / "realtime_observations",
    )
    args = parser.parse_args()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    materializer = load_module("impossible_ecology_materializer", MATERIALIZER)
    smoke = load_module("impossible_ecology_smoke", SMOKE)
    with tempfile.TemporaryDirectory(prefix="impossible-ecology-realtime-") as temporary:
        temporary_root = Path(temporary)
        materializer.materialize_environment(ENVIRONMENT, temporary_root / "materialized")
        task_json = task_for_level(temporary_root / "materialized" / ENVIRONMENT.name / "tasks")
        summaries = {}
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for mode in ("live", "paused"):
                state_dir = temporary_root / mode
                state_dir.mkdir()
                process, port = smoke.start_server(task_json, "impossible_ecology", "full", state_dir)
                page = browser.new_page(viewport=observation_viewport(), device_scale_factor=1)
                try:
                    summaries[mode] = capture_mode(page, base=f"http://127.0.0.1:{port}", mode=mode, out_dir=out_dir)
                finally:
                    page.close()
                    process.terminate()
                    process.wait(timeout=3)
            browser.close()
    summary = {
        "environment": ENVIRONMENT.name,
        "difficulty": 4,
        "interaction": "full",
        "settings": {"play_time_seconds": 150, "observation_window_ms": 800, "frames_per_observation": 6},
        "viewport": observation_viewport(),
        "modes": summaries,
        "source_hashes": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                ENVIRONMENT / "controls.json",
                BENCHMARK / "shared_runtime" / "app" / "mechanics" / "impossible_ecology.js",
                BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "impossible_ecology.py",
            )
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
