#!/usr/bin/env python3
"""Probe native static-tab observation without leaving isolated headless Playwright.

The probe never replaces ``getDisplayMedia`` with a canvas or a synthetic
MediaStream.  If native tab capture is unavailable headlessly, it writes a
negative evidence record instead of opening a visible browser.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageChops, ImageStat
from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from weird_captcha_gym.dashboard.export_static import export_dashboard


BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "occlusion_shell_swindle_env"
class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def image_difference(first: bytes, second: bytes) -> float:
    left = Image.open(io.BytesIO(first)).convert("RGB")
    right = Image.open(io.BytesIO(second)).convert("RGB")
    return sum(ImageStat.Stat(ImageChops.difference(left, right)).mean) / 3


def status(page) -> dict:
    return page.evaluate("() => WeirdCaptchaTime.status()")


def inspect_mode(page, *, mode: str, output: Path) -> dict:
    if mode == "live":
        page.get_by_role("button", name="Live").click()
        page.wait_for_function("WeirdCaptchaTime.status().state === 'running'")
    else:
        page.get_by_role("button", name="Paused").click()
        page.wait_for_function("WeirdCaptchaTime.status().state === 'paused'")

    before = status(page)
    page.get_by_role("button", name="Capture model observation").click()
    page.wait_for_timeout(2_000)
    if page.locator(".weird-demo-observation").get_attribute("data-open") != "true":
        screenshot = output / f"static-{mode}-native-capture-unavailable.png"
        page.screenshot(path=str(screenshot), full_page=True)
        return {
            "available": False,
            "before": before,
            "reason": page.locator("[data-demo-note]").inner_text(),
            "screenshot": screenshot.name,
        }
    expect(page.locator(".weird-demo-frame")).to_have_count(6)
    screen_label = page.locator("[data-demo-screen-label]").inner_text()
    expect(page.locator("[data-demo-screen-label]")).to_contain_text("obs.screen")
    viewer_screenshot = output / f"static-{mode}-observation-viewer.png"
    model_screen_screenshot = output / f"static-{mode}-obs-screen.png"
    first_frame_screenshot = output / f"static-{mode}-first-obs-screen.png"
    page.screenshot(path=str(viewer_screenshot), full_page=True)
    page.locator(".weird-demo-frame").first.click()
    page.wait_for_timeout(100)
    first_screen_image = page.locator("[data-demo-screen]").screenshot(path=str(first_frame_screenshot))
    first_screen_label = page.locator("[data-demo-screen-label]").inner_text()
    page.locator(".weird-demo-frame").last.click()
    page.wait_for_timeout(100)
    latest_screen_image = page.locator("[data-demo-screen]").screenshot(path=str(model_screen_screenshot))
    observation_difference = image_difference(first_screen_image, latest_screen_image)
    if observation_difference <= 0.02:
        raise AssertionError(f"public static observation frames did not visibly change: {observation_difference}")
    after = status(page)
    if mode == "paused" and after["state"] != "paused":
        raise AssertionError("public static paused observation did not pause after capture")
    if mode == "live" and after["state"] != "running":
        raise AssertionError("public static live observation did not resume after capture")
    page.get_by_role("button", name="Close").click()

    before_delay_screenshot = output / f"static-{mode}-after-capture-before-model-delay.png"
    after_delay_screenshot = output / f"static-{mode}-after-capture-after-model-delay.png"
    before_delay_image = page.screenshot(path=str(before_delay_screenshot))
    before_delay_status = status(page)
    page.wait_for_timeout(900)
    after_delay_image = page.screenshot(path=str(after_delay_screenshot))
    after_delay_status = status(page)
    delay_delta = float(after_delay_status["task_time_ms"]) - float(before_delay_status["task_time_ms"])
    delay_difference = image_difference(before_delay_image, after_delay_image)
    if mode == "paused" and (abs(delay_delta) > 2 or delay_difference > 0.02):
        raise AssertionError(f"public static paused model delay advanced task time: {delay_delta} ms / {delay_difference}")
    if mode == "live" and (delay_delta <= 100 or delay_difference <= 0.02):
        raise AssertionError(f"public static live model delay did not advance task time: {delay_delta} ms / {delay_difference}")

    return {
        "available": True,
        "before": before,
        "after": after,
        "screen_label": screen_label,
        "first_screen_label": first_screen_label,
        "frame_count": 6,
        "viewer_screenshot": viewer_screenshot.name,
        "obs_screen_screenshot": model_screen_screenshot.name,
        "first_frame_screenshot": first_frame_screenshot.name,
        "first_to_last_obs_screen_difference": observation_difference,
        "after_capture_before_model_delay": before_delay_screenshot.name,
        "after_capture_after_model_delay": after_delay_screenshot.name,
        "model_delay_task_time_delta_ms": delay_delta,
        "model_delay_image_difference": delay_difference,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=ENVIRONMENT / "evidence_docs" / "static_observations_headless")
    args = parser.parse_args()
    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    with tempfile.TemporaryDirectory(prefix="occlusion-shell-static-observations-") as temporary:
        site = Path(temporary) / "site"
        profile = Path(temporary) / "fresh-playwright-profile"
        manifest = export_dashboard(site, copy_media=False)
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(site)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                # A fresh, private profile and headless browser are required
                # for repository validation.  The auto-accept switch only
                # chooses the current tab; it does not synthesize a stream.
                context = playwright.chromium.launch_persistent_context(
                    str(profile),
                    headless=True,
                    viewport={"width": 1920, "height": 1080},
                    device_scale_factor=1,
                    args=["--auto-accept-this-tab-capture"],
                )
                records = {}
                for mode in ("live", "paused"):
                    page = context.new_page()
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(
                        f"http://127.0.0.1:{server.server_port}/play/?environment=occlusion_shell_swindle_env&attempt=0&difficulty=2",
                        wait_until="networkidle",
                    )
                    expect(page.locator('.occlusion-shell-captcha[data-interaction="full"]')).to_be_visible()
                    page.locator(".shell-start-round").click()
                    page.wait_for_function("() => window.occlusionShellModel.tick >= 3", timeout=8_000)
                    page.get_by_role("button", name="Expand observation controls").click()
                    expect(page.get_by_role("button", name="Capture model observation")).to_be_visible()
                    records[mode] = inspect_mode(page, mode=mode, output=output)
                    page.close()
                context.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    if errors:
        raise AssertionError(f"static observation inspector reported browser errors: {errors}")
    source_paths = (
        ENVIRONMENT / "controls.json",
        BENCHMARK / "shared_runtime" / "app" / "mechanics" / "occlusion_shell_swindle.js",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "occlusion_shell_swindle.py",
    )
    result = {
        "environment": ENVIRONMENT.name,
        "difficulty": 2,
        "interaction": "full",
        "status": "available" if all(record.get("available") for record in records.values()) else "not_available",
        "public_static_observations": records,
        "capture_method": {
            "stream": "browser-native navigator.mediaDevices.getDisplayMedia selected tab",
            "selected_surface": "the isolated headless Playwright tab hosting Occlusion Shell Swindle",
            "picker_automation": "Chromium auto-accept-this-tab-capture",
            "browser": "isolated headless Playwright Chromium",
            "fresh_temporary_profile": True,
            "synthetic_stream_override": False,
        },
        "browser_play_environments": manifest["browser_play"]["environments"],
        "source_hashes": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths},
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
