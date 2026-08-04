#!/usr/bin/env python3
"""Capture the shared live/paused observation contract for Occlusion Shell Swindle."""
from __future__ import annotations

import argparse
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
ENVIRONMENT = BENCHMARK / "environments" / "occlusion_shell_swindle_env"
MATERIALIZER = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
SMOKE = BENCHMARK / "tools" / "smoke_controlled_interaction_ui.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def viewport() -> dict[str, int]:
    screen = read_json(ENVIRONMENT / "env.json")["observation"][0]
    resolution = screen["resolution"]
    return {"width": int(resolution[0]), "height": int(resolution[1])}


def task_for_level(tasks_root: Path) -> Path:
    for candidate in tasks_root.glob("*/task.json"):
        condition = (read_json(candidate).get("metadata") or {}).get("control_condition") or {}
        if condition.get("difficulty") == 2 and condition.get("interaction") == "full":
            return candidate
    raise RuntimeError("materialized L2/full Occlusion Shell Swindle task is missing")


def image_difference(first: bytes, second: bytes) -> float:
    left = Image.open(io.BytesIO(first)).convert("RGB")
    right = Image.open(io.BytesIO(second)).convert("RGB")
    return sum(ImageStat.Stat(ImageChops.difference(left, right)).mean) / 3


def status(page) -> dict:
    return page.evaluate("() => WeirdCaptchaTime.status()")


def capture_mode(page, *, base: str, mode: str, output: Path) -> dict:
    page.goto(f"{base}/?time_mode={mode}&start_paused={'1' if mode == 'paused' else '0'}", wait_until="networkidle")
    expect(page.locator('.occlusion-shell-captcha[data-interaction="full"]')).to_be_visible()
    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.resume()")
    page.locator(".shell-start-round").click()
    page.wait_for_function("() => window.occlusionShellModel.tick >= 3", timeout=5_000)

    frames = []
    for index in range(6):
        if index:
            page.wait_for_timeout(160)
        path = output / f"{mode}-observation-frame-{index + 1:03d}.png"
        page.screenshot(path=str(path))
        frames.append({"path": path.name, "task_time_ms": status(page)["task_time_ms"], "offset_ms": index * 160})

    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.pause()")
    after_window = status(page)
    before_delay = page.screenshot(path=str(output / f"{mode}-before-model-delay.png"))
    delay_before = status(page)
    page.wait_for_timeout(900)
    after_delay = page.screenshot(path=str(output / f"{mode}-after-model-delay.png"))
    delay_after = status(page)
    task_delta = float(delay_after["task_time_ms"]) - float(delay_before["task_time_ms"])
    visual_delta = image_difference(before_delay, after_delay)
    if mode == "live" and task_delta < 700:
        raise AssertionError(f"live task time did not advance during model delay: {task_delta}")
    if mode == "paused" and (abs(task_delta) > 2 or visual_delta > 0.02):
        raise AssertionError(f"paused task changed during model delay: {task_delta}ms / {visual_delta}")

    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.resume()")
    stage = page.locator(".shell-stage").bounding_box()
    if not stage:
        raise AssertionError("shell stage is not visible for the resumed direct action")
    action_before = status(page)
    page.mouse.move(stage["x"] + stage["width"] * 0.5, stage["y"] + stage["height"] * 0.33)
    page.wait_for_timeout(180)
    action_after = status(page)
    page.screenshot(path=str(output / f"{mode}-resumed-pointer-action.png"))
    if float(action_after["task_time_ms"]) <= float(action_before["task_time_ms"]):
        raise AssertionError(f"{mode} task did not advance while the direct action ran")
    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.pause()")
    return {
        "frames": frames,
        "after_observation_window": after_window,
        "delay_before": delay_before,
        "delay_after": delay_after,
        "delay_task_delta_ms": task_delta,
        "delay_image_difference": visual_delta,
        "action_before": action_before,
        "action_after": action_after,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=ENVIRONMENT / "evidence_docs" / "realtime_observations")
    args = parser.parse_args()
    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    materializer = load_module("occlusion_shell_realtime_materializer", MATERIALIZER)
    smoke = load_module("occlusion_shell_realtime_smoke", SMOKE)
    with tempfile.TemporaryDirectory(prefix="occlusion-shell-realtime-") as temporary:
        temporary_root = Path(temporary)
        materializer.materialize_environment(ENVIRONMENT, temporary_root / "materialized")
        task_json = task_for_level(temporary_root / "materialized" / ENVIRONMENT.name / "tasks")
        records = {}
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for mode in ("live", "paused"):
                state_dir = temporary_root / mode
                state_dir.mkdir()
                process, port = smoke.start_server(task_json, "occlusion_shell_swindle", "full", state_dir)
                page = browser.new_page(viewport=viewport(), device_scale_factor=1)
                try:
                    records[mode] = capture_mode(page, base=f"http://127.0.0.1:{port}", mode=mode, output=output)
                finally:
                    page.close()
                    process.terminate()
                    process.wait(timeout=3)
            browser.close()
    summary = {
        "environment": ENVIRONMENT.name,
        "difficulty": 2,
        "interaction": "full",
        "settings": {"play_time_seconds": 120, "observation_window_ms": 800, "frames_per_observation": 6},
        "viewport": viewport(),
        "modes": records,
        "source_hashes": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                ENVIRONMENT / "controls.json",
                BENCHMARK / "shared_scripts" / "incubator_generators" / "occlusion_shell_swindle.py",
                BENCHMARK / "shared_runtime" / "app" / "mechanics" / "occlusion_shell_swindle.js",
                BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "occlusion_shell_swindle.py",
            )
        },
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
