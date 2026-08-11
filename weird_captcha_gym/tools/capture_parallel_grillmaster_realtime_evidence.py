#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import tempfile
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageChops, ImageStat
from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from weird_captcha_gym.dashboard.export_static import export_dashboard


ENVIRONMENT = "parallel_grillmaster_env"
FRAME_OFFSETS_MS = (0, 160, 320, 480, 640, 800)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture live and paused model-observation evidence for Parallel Grillmaster."
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def difference(left: bytes, right: bytes) -> float:
    first = Image.open(io.BytesIO(left)).convert("RGB")
    second = Image.open(io.BytesIO(right)).convert("RGB")
    return sum(ImageStat.Stat(ImageChops.difference(first, second)).mean) / 3


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def clock_status(page) -> dict:
    return page.evaluate("WeirdCaptchaTime.status()")


def task_screenshot(page, path: Path | None = None) -> bytes:
    page.evaluate("document.documentElement.dataset.agentCapture = 'true'")
    try:
        return page.screenshot(path=str(path) if path else None)
    finally:
        page.evaluate("document.documentElement.removeAttribute('data-agent-capture')")


def pointer_drag(page, source, target) -> None:
    source_box = source.bounding_box()
    target_box = target.bounding_box()
    if not source_box or not target_box:
        raise AssertionError("drag endpoints are not visible")
    page.mouse.move(source_box["x"] + source_box["width"] / 2, source_box["y"] + source_box["height"] / 2)
    page.mouse.down()
    page.mouse.move(target_box["x"] + target_box["width"] / 2, target_box["y"] + target_box["height"] / 2)
    page.mouse.up()


def capture_observation(page, output: Path, mode: str) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    if mode == "paused":
        page.evaluate("WeirdCaptchaTime.resume()")
    start = float(clock_status(page)["task_time_ms"])
    frames = []
    wall_start = time.monotonic()
    for index, offset in enumerate(FRAME_OFFSETS_MS, start=1):
        remaining = offset / 1000 - (time.monotonic() - wall_start)
        if remaining > 0:
            time.sleep(remaining)
        if mode == "paused" and index == len(FRAME_OFFSETS_MS):
            page.evaluate("WeirdCaptchaTime.pause()")
        path = output / f"observation-frame-{index}.png"
        task_screenshot(page, path)
        frames.append({
            "index": index,
            "target_offset_ms": offset,
            "task_time_ms": float(clock_status(page)["task_time_ms"]),
            "path": path.name,
        })
    if mode == "paused":
        page.evaluate("WeirdCaptchaTime.pause()")
    return {
        "frames": frames,
        "screen": frames[-1]["path"],
        "task_time_start_ms": start,
        "task_time_end_ms": float(clock_status(page)["task_time_ms"]),
    }


def begin_all_foods(page) -> list[str]:
    food_ids = []
    while page.locator('.grill-zone[data-drop-zone="prep"] .grill-food').count():
        food = page.locator('.grill-zone[data-drop-zone="prep"] .grill-food').first
        food_id = str(food.get_attribute("data-food-id") or "")
        pointer_drag(page, food, page.locator('.grill-zone[data-drop-zone="grill"]'))
        expect(
            page.locator(
                '.grill-zone[data-drop-zone="grill"] '
                f'.grill-food[data-food-id="{food_id}"]'
            )
        ).to_be_visible()
        food_ids.append(food_id)
    return food_ids


def run_mode(context, base: str, out_dir: Path, mode: str) -> dict:
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(
        f"{base}/play/?environment={ENVIRONMENT}&attempt=0&difficulty=2&interaction=full"
        f"&time_mode={mode}&start_paused={1 if mode == 'paused' else 0}",
        wait_until="networkidle",
    )
    page.wait_for_selector('.grill-captcha[data-interaction="full"]')
    page.wait_for_function("WeirdCaptchaTime.status().ready === true")
    challenge_id = page.locator(".grill-captcha").get_attribute("data-challenge-id")
    started_foods = begin_all_foods(page)
    page.wait_for_timeout(120)
    if mode == "paused":
        page.wait_for_function("WeirdCaptchaTime.status().state === 'paused'")
        page.evaluate("WeirdCaptchaTime.resume()")
        time.sleep(2.4)
        page.evaluate("WeirdCaptchaTime.pause()")
    else:
        page.wait_for_timeout(2400)

    observation = capture_observation(page, out_dir / mode, mode)
    before_delay = clock_status(page)
    before_image = task_screenshot(page, out_dir / mode / "before-model-delay.png")
    page.wait_for_timeout(700)
    after_delay = clock_status(page)
    after_image = task_screenshot(page, out_dir / mode / "after-model-delay.png")
    delay_difference = difference(before_image, after_image)

    action_evidence = None
    if mode == "paused":
        before_action = clock_status(page)
        task_screenshot(page, out_dir / mode / "before-paused-action.png")
        ready_food = page.locator(
            '.grill-zone[data-drop-zone="grill"] .grill-food[data-cook-state="ready"]'
        ).first
        if ready_food.count() != 1:
            raise AssertionError("paused observation did not leave a visibly ready food")
        food_id = str(ready_food.get_attribute("data-food-id") or "")
        pointer_drag(page, ready_food, page.locator('.grill-zone[data-drop-zone="tray"]'))
        expect(
            page.locator(
                '.grill-zone[data-drop-zone="tray"] '
                f'.grill-food[data-food-id="{food_id}"]'
            )
        ).to_be_visible()
        page.wait_for_timeout(140)
        page.wait_for_function("WeirdCaptchaTime.status().state === 'paused'")
        after_action = clock_status(page)
        parent_zone = page.locator(
            f'.grill-food[data-food-id="{food_id}"]'
        ).evaluate("node => node.parentElement?.dataset.dropZone")
        task_screenshot(page, out_dir / mode / "after-paused-action.png")
        action_evidence = {
            "food_id": food_id,
            "visible_parent_zone": parent_zone,
            "task_time_before_ms": float(before_action["task_time_ms"]),
            "task_time_after_ms": float(after_action["task_time_ms"]),
            "clock_state_after": after_action["state"],
        }

    result = {
        "mode": mode,
        "challenge_id": challenge_id,
        "started_food_ids": started_foods,
        "pre_observation_warmup_ms": 2400,
        "observation": observation,
        "model_delay_wall_ms": 700,
        "task_time_before_model_ms": float(before_delay["task_time_ms"]),
        "task_time_after_model_ms": float(after_delay["task_time_ms"]),
        "model_delay_visual_difference": delay_difference,
        "model_delay_before_image": "before-model-delay.png",
        "model_delay_after_image": "after-model-delay.png",
        "model_delay_before_sha256": sha256_bytes(before_image),
        "model_delay_after_sha256": sha256_bytes(after_image),
        "clock_state_after_model": after_delay["state"],
        "paused_action": action_evidence,
        "page_errors": errors,
    }
    page.close()
    return result


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="parallel-grillmaster-realtime-") as temporary:
        site = Path(temporary) / "site"
        export_dashboard(site, copy_media=False)
        handler = partial(QuietHandler, directory=str(site))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1280, "height": 720})
                paused = run_mode(context, base, args.out_dir, "paused")
                live = run_mode(context, base, args.out_dir, "live")
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    if paused["challenge_id"] != live["challenge_id"]:
        raise AssertionError("live and paused evidence used different generated worlds")
    paused_delta = (
        paused["task_time_after_model_ms"] - paused["task_time_before_model_ms"]
    )
    live_delta = live["task_time_after_model_ms"] - live["task_time_before_model_ms"]
    if abs(paused_delta) > 1:
        raise AssertionError(f"paused task advanced during model delay: {paused_delta}ms")
    if live_delta < 600:
        raise AssertionError(f"live task did not advance during model delay: {live_delta}ms")
    if paused["paused_action"]["visible_parent_zone"] != "tray":
        raise AssertionError("paused action did not move the ready food onto the tray")
    if paused["paused_action"]["task_time_after_ms"] <= paused["paused_action"]["task_time_before_ms"]:
        raise AssertionError("paused task did not run while the action was applied")
    if paused["paused_action"]["clock_state_after"] != "paused":
        raise AssertionError("paused task did not freeze again after the action")
    if paused["page_errors"] or live["page_errors"]:
        raise AssertionError(f"browser errors: paused={paused['page_errors']} live={live['page_errors']}")

    summary = {
        "environment": ENVIRONMENT,
        "difficulty": 2,
        "interaction": "full",
        "settings": {
            "play_time_seconds": 120,
            "observation_window_ms": 800,
            "frames_per_observation": 6,
        },
        "same_generated_world": True,
        "paused": paused,
        "live": live,
    }
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
