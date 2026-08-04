#!/usr/bin/env python3
from __future__ import annotations

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
from playwright.sync_api import sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from weird_captcha_gym.dashboard.export_static import export_dashboard


ENVIRONMENTS = (
    "blind_dice_courier_env",
    "clockwork_clutch_safe_env",
    "rotating_keyboard_env",
    "parallel_grillmaster_env",
    "motion_only_ghost_jigsaw_env",
    "slime_commute_env",
    "slot_reel_capture_env",
    "lidar_blacksite_env",
    "domino_autopsy_env",
)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def difference(left: bytes, right: bytes) -> float:
    first = Image.open(io.BytesIO(left)).convert("RGB")
    second = Image.open(io.BytesIO(right)).convert("RGB")
    return sum(ImageStat.Stat(ImageChops.difference(first, second)).mean) / 3


def main() -> None:
    results = []
    with tempfile.TemporaryDirectory(prefix="weird-cua-realtime-envs-") as temporary:
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
                page = browser.new_page(viewport={"width": 1280, "height": 720})
                for environment in ENVIRONMENTS:
                    page.goto(
                        f"{base}/play/?environment={environment}&attempt=0&time_mode=paused&start_paused=1",
                        wait_until="domcontentloaded",
                    )
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        loaded = page.evaluate(
                            "document.body.dataset.mechanic && document.body.dataset.mechanic !== 'waiting'"
                        )
                        if loaded:
                            break
                        time.sleep(.05)
                    else:
                        raise TimeoutError(f"{environment} did not finish rendering while initially paused")
                    if environment == "rotating_keyboard_env":
                        page.locator(".rotating-key:not(.rotating-delete)").first.click()
                    elif environment == "blind_dice_courier_env":
                        page.keyboard.press("ArrowUp")
                    elif environment == "clockwork_clutch_safe_env":
                        page.locator("#clutch-drive").click()
                    elif environment == "lidar_blacksite_env":
                        page.locator("#lidar-scan").click()
                    elif environment == "domino_autopsy_env":
                        page.locator("#domino-run").click()
                    page.wait_for_timeout(150)
                    before = page.screenshot()
                    page.wait_for_timeout(300)
                    frozen = page.screenshot()
                    frozen_difference = difference(before, frozen)
                    if frozen_difference > 0.02:
                        raise AssertionError(f"{environment} changed while paused: {frozen_difference}")

                    page.evaluate("WeirdCaptchaTime.resume()")
                    page.wait_for_timeout(700)
                    page.evaluate("WeirdCaptchaTime.pause()")
                    page.wait_for_timeout(50)
                    advanced = page.screenshot()
                    advanced_difference = difference(frozen, advanced)
                    if advanced_difference <= 0.02:
                        raise AssertionError(f"{environment} did not change while running: {advanced_difference}")
                    results.append({
                        "environment": environment,
                        "paused_difference": frozen_difference,
                        "running_difference": advanced_difference,
                    })
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
    print(json.dumps({"ok": True, "environments": results}, indent=2))


if __name__ == "__main__":
    main()
