#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = "portal_freight_oversized_parcel_env"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def install_rendered_screen_capture(page) -> None:
    """Feed the real viewer through its video path when headless tab capture is unavailable.

    Chromium's native ``getDisplayMedia`` chooser cannot select the current tab
    in an isolated headless profile.  This helper first takes a screenshot of
    the already-rendered exported page (with the inspector hidden by its own
    capture CSS), then supplies that bitmap as a short-lived video stream.  It
    does not alter the generated task, its UI, the clock, or grading; it only
    lets the existing observation-viewer path render a frame in headless CI.
    The native-capture result is recorded separately in the evidence summary.
    """
    page.evaluate("document.documentElement.dataset.agentCapture = 'true'")
    png = page.screenshot()
    page.evaluate("delete document.documentElement.dataset.agentCapture")
    encoded = base64.b64encode(png).decode("ascii")
    page.evaluate(
        """async encoded => {
          const image = new Image();
          await new Promise((resolve, reject) => {
            image.onload = resolve;
            image.onerror = reject;
            image.src = `data:image/png;base64,${encoded}`;
          });
          const canvas = document.createElement('canvas');
          canvas.width = 1280;
          canvas.height = 720;
          const context = canvas.getContext('2d');
          context.drawImage(image, 0, 0, canvas.width, canvas.height);
          let pulse = false;
          const native = window.WeirdCaptchaTime?.native || window;
          native.setInterval(() => {
            pulse = !pulse;
            context.fillStyle = pulse ? '#000001' : '#000000';
            context.fillRect(canvas.width - 1, canvas.height - 1, 1, 1);
          }, 32);
          const mediaDevices = navigator.mediaDevices || {};
          Object.defineProperty(mediaDevices, 'getDisplayMedia', {
            configurable: true,
            value: async () => canvas.captureStream(30),
          });
          if (!navigator.mediaDevices) {
            Object.defineProperty(navigator, 'mediaDevices', {configurable: true, value: mediaDevices});
          }
        }""",
        encoded,
    )


def try_native_tab_capture(page, mode: str, out_dir: Path) -> dict[str, object]:
    """Record whether native current-tab capture is available without replacing it."""
    page.get_by_role("button", name="Capture model observation").click()
    page.wait_for_timeout(800)
    viewer = page.locator(".weird-demo-observation")
    if viewer.get_attribute("data-open") == "true":
        screenshot = out_dir / f"{mode}-native-observation.png"
        page.screenshot(path=str(screenshot), full_page=True)
        frames = page.locator(".weird-demo-frame").count()
        page.get_by_role("button", name="Close", exact=True).click()
        return {
            "available": True,
            "frames": frames,
            "screenshot": screenshot.name,
        }
    screenshot = out_dir / f"{mode}-native-capture-unavailable.png"
    page.screenshot(path=str(screenshot), full_page=True)
    return {
        "available": False,
        "reason": page.locator("[data-demo-note]").inner_text(),
        "screenshot": screenshot.name,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture Portal Freight live and paused static-browser observations.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=BENCHMARK / "environments" / "portal_freight_oversized_parcel_env" / "evidence_docs" / "static_observations",
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    from weird_captcha_gym.dashboard.export_static import export_dashboard

    with tempfile.TemporaryDirectory(prefix="portal-freight-static-export-") as temporary_name:
        site = Path(temporary_name) / "site"
        manifest = export_dashboard(site, copy_media=False)
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(site)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
                page = context.new_page()
                errors: list[str] = []
                page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                page.on("pageerror", lambda error: errors.append(str(error)))
                base = f"http://127.0.0.1:{server.server_port}/play/?environment={ENVIRONMENT}&attempt=0&difficulty=4&interaction=simplified"
                page.goto(base, wait_until="networkidle")
                expect(page.locator(".portal-freight")).to_be_visible()
                page.get_by_role("button", name="Expand observation controls").click()
                page.get_by_role("button", name="Paused").click()
                page.wait_for_function("WeirdCaptchaTime.status().state === 'paused'")
                paused_before = page.evaluate("WeirdCaptchaTime.status().task_time_ms")
                page.wait_for_timeout(180)
                paused_after = page.evaluate("WeirdCaptchaTime.status().task_time_ms")
                paused_native = try_native_tab_capture(page, "paused", args.out_dir)
                if not paused_native["available"]:
                    install_rendered_screen_capture(page)
                page.get_by_role("button", name="Capture model observation").click()
                expect(page.locator(".weird-demo-observation")).to_have_attribute("data-open", "true", timeout=10_000)
                paused_frames = page.locator(".weird-demo-frame").count()
                page.screenshot(path=str(args.out_dir / "paused-observation.png"), full_page=True)
                page.get_by_role("button", name="Close", exact=True).click()
                page.get_by_role("button", name="Live").click()
                page.wait_for_function("WeirdCaptchaTime.status().state === 'running'")
                live_before = page.evaluate("WeirdCaptchaTime.status().task_time_ms")
                page.wait_for_timeout(180)
                live_after = page.evaluate("WeirdCaptchaTime.status().task_time_ms")
                # A fresh exported page keeps the native-capture probe and its
                # result independent from the synthetic headless viewer probe.
                page.goto(base, wait_until="networkidle")
                expect(page.locator(".portal-freight")).to_be_visible()
                page.get_by_role("button", name="Expand observation controls").click()
                page.get_by_role("button", name="Live").click()
                page.wait_for_function("WeirdCaptchaTime.status().state === 'running'")
                live_native = try_native_tab_capture(page, "live", args.out_dir)
                if not live_native["available"]:
                    install_rendered_screen_capture(page)
                page.get_by_role("button", name="Capture model observation").click()
                expect(page.locator(".weird-demo-observation")).to_have_attribute("data-open", "true", timeout=10_000)
                live_frames = page.locator(".weird-demo-frame").count()
                page.screenshot(path=str(args.out_dir / "live-observation.png"), full_page=True)
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    summary = {
        "headless_isolated": True,
        "loopback_only": True,
        "environment": ENVIRONMENT,
        "condition": {"difficulty": 4, "interaction": "simplified"},
        "shared_real_time": {"play_time_seconds": 180, "observation_window_ms": 0, "frames_per_observation": 1},
        "native_target_tab_capture": {"paused": paused_native, "live": live_native},
        "headless_viewer_capture": {
            "method": "rendered exported page screenshot through canvas.captureStream only after native tab capture was unavailable",
            "affects_task_or_grading": False,
        },
        "paused": {"task_time_before_delay_ms": paused_before, "task_time_after_delay_ms": paused_after, "frames": paused_frames},
        "live": {"task_time_before_delay_ms": live_before, "task_time_after_delay_ms": live_after, "frames": live_frames},
        "console_errors": errors,
        "static_export_environments": manifest["browser_play"]["environments"],
    }
    if errors:
        raise AssertionError(f"static browser errors: {errors}")
    if paused_after - paused_before > 1:
        raise AssertionError(f"paused task clock advanced: {paused_before} -> {paused_after}")
    if live_after <= live_before:
        raise AssertionError(f"live task clock did not advance: {live_before} -> {live_after}")
    if paused_frames != 1 or live_frames != 1:
        raise AssertionError(f"static Portal Freight must expose one frame, got paused={paused_frames}, live={live_frames}")
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
