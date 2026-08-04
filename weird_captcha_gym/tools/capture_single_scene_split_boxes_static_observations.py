#!/usr/bin/env python3
"""Probe native static-tab observation without synthetic media streams.

This is deliberately a negative-evidence-capable probe. It runs an exported
target through a temporary loopback server and a new headless Chromium profile.
It never replaces ``getDisplayMedia``. If Chromium cannot offer native tab
capture in that isolated configuration, the artifact records that limitation.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from weird_captcha_gym.dashboard.catalog import build_catalog
from weird_captcha_gym.dashboard.export_static import _export_browser_play


ENVIRONMENT = "single_scene_split_boxes_env"
MECHANIC = "single_scene_split_boxes"
BENCHMARK = ROOT / "weird_captcha_gym"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def target_catalog() -> dict[str, Any]:
    catalog = copy.deepcopy(build_catalog())
    catalog["environments"] = [item for item in catalog["environments"] if item.get("id") == ENVIRONMENT]
    if len(catalog["environments"]) != 1:
        raise AssertionError("target environment is not uniquely available for static export")
    return catalog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=BENCHMARK / "environments" / ENVIRONMENT / "evidence_docs" / "static_observations_headless",
    )
    return parser.parse_args()


def clock_status(page) -> dict[str, Any]:
    return page.evaluate("() => WeirdCaptchaTime.status()")


def inspect_mode(page, mode: str, out_dir: Path) -> dict[str, Any]:
    page.get_by_role("button", name="Live" if mode == "live" else "Paused").click()
    expected_state = "running" if mode == "live" else "paused"
    page.wait_for_function("expected => WeirdCaptchaTime.status().state === expected", arg=expected_state)
    before = clock_status(page)
    page.get_by_role("button", name="Capture model observation").click()
    page.wait_for_timeout(2_000)
    viewer = page.locator(".weird-demo-observation")
    if viewer.get_attribute("data-open") != "true":
        screenshot = out_dir / f"static-{mode}-native-capture-unavailable.png"
        page.screenshot(path=str(screenshot), full_page=True)
        return {
            "available": False,
            "before": before,
            "reason": page.locator("[data-demo-note]").inner_text(),
            "screenshot": screenshot.name,
        }
    expect(page.locator(".weird-demo-frame")).to_have_count(6)
    expect(page.locator("[data-demo-screen-label]")).to_contain_text("obs.screen")
    screenshot = out_dir / f"static-{mode}-observation-viewer.png"
    page.screenshot(path=str(screenshot), full_page=True)
    after = clock_status(page)
    if after["state"] != expected_state:
        raise AssertionError(f"{mode} static observation returned the wrong clock state: {after}")
    page.get_by_role("button", name="Close").click()
    return {
        "available": True,
        "before": before,
        "after": after,
        "frame_count": 6,
        "screen_label": page.locator("[data-demo-screen-label]").inner_text(),
        "viewer_screenshot": screenshot.name,
    }


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="split-boxes-static-observations-") as temporary_name:
        temporary = Path(temporary_name)
        site = temporary / "site"
        profile = temporary / "fresh-playwright-profile"
        export = _export_browser_play(site, target_catalog())
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(site)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        records: dict[str, Any] = {}
        try:
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    str(profile),
                    headless=True,
                    viewport={"width": 1280, "height": 720},
                    device_scale_factor=1,
                    args=["--auto-accept-this-tab-capture"],
                )
                for mode in ("live", "paused"):
                    page = context.new_page()
                    page.on("pageerror", lambda error, mode=mode: errors.append(f"{mode}: {error}"))
                    page.goto(
                        f"http://127.0.0.1:{server.server_port}/play/?environment={ENVIRONMENT}"
                        f"&attempt=0&difficulty=4&interaction=full&time_mode={mode}",
                        wait_until="networkidle",
                    )
                    expect(page.locator('.mosaic-captcha[data-interaction="full"]')).to_be_visible()
                    page.get_by_role("button", name="Expand observation controls").click()
                    expect(page.get_by_role("button", name="Capture model observation")).to_be_visible()
                    records[mode] = inspect_mode(page, mode, out_dir)
                    page.close()
                context.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
    if errors:
        raise AssertionError(f"static observation page errors: {errors}")
    sources = (
        BENCHMARK / "environments" / ENVIRONMENT / "controls.json",
        BENCHMARK / "shared_runtime" / "browser" / "demo_controls.js",
        BENCHMARK / "shared_runtime" / "app" / "mechanics" / f"{MECHANIC}.js",
    )
    output = {
        "environment": ENVIRONMENT,
        "difficulty": 4,
        "interaction": "full",
        "status": "available" if all(record.get("available") for record in records.values()) else "not_available",
        "public_static_observations": records,
        "capture_method": {
            "stream": "browser-native navigator.mediaDevices.getDisplayMedia selected tab",
            "browser": "isolated headless Playwright Chromium",
            "loopback_server": True,
            "fresh_temporary_profile": True,
            "synthetic_stream_override": False,
        },
        "target_export": export,
        "source_hashes": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
    }
    (out_dir / "summary.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
