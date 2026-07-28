#!/usr/bin/env python3
"""Capture Magnetic Stripe Purgatory's own static-browser UI and Pyodide grade."""

from __future__ import annotations

import argparse
import json
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from typing import Any

from playwright.sync_api import Page, expect, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from benchmarks.weird_captcha_gym.dashboard.export_static import export_dashboard


ENVIRONMENT = "magnetic_stripe_purgatory_env"
PROFILE_DURATIONS = {
    "flicker": 490,
    "quartz_narrow": 630,
    "pendulum_narrow": 860,
    "glacier_narrow": 1140,
}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def public_state(page: Page) -> dict[str, Any]:
    # The renderer retains the current public challenge object. Reading this
    # test fixture avoids issuing a second /state request while documenting the
    # exact surface already visible in the static browser.
    return page.evaluate("() => magneticStripePurgatoryModel.state")


def matching_reader(state: dict[str, Any], card: dict[str, Any]) -> dict[str, Any]:
    return next(reader for reader in state["readers"] if reader["badge"]["code"] == card["badge"]["code"])


def load(page: Page, base_url: str, interaction: str) -> dict[str, Any]:
    page.goto(
        f"{base_url}/play/?environment={ENVIRONMENT}&attempt=0&difficulty=5&interaction={interaction}",
        wait_until="networkidle",
    )
    page.wait_for_selector(".stripe-purgatory")
    if page.locator(".stripe-purgatory").get_attribute("data-interaction") != interaction:
        raise AssertionError(f"static browser rendered the wrong interaction surface for {interaction}")
    state = public_state(page)
    if state["control_condition"]["difficulty"] != 5 or state["control_condition"]["interaction"] != interaction:
        raise AssertionError("static browser did not retain the requested controlled condition")
    if len(state["readers"]) != 4 or any(not reader["interference_zones"] for reader in state["readers"]):
        raise AssertionError("static browser did not render the L5 lane-blocking field profile")
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    with tempfile.TemporaryDirectory(prefix="magnetic-stripe-static-browser-") as temporary:
        site = Path(temporary) / "site"
        export_dashboard(site, copy_media=False)
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(site)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1280, "height": 720})
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))

                full_state = load(page, base_url, "full")
                page.screenshot(path=str(out_dir / "l5-full-physical-surface.png"), full_page=True)

                simplified_state = load(page, base_url, "simplified")
                page.screenshot(path=str(out_dir / "l5-simplified-initial.png"), full_page=True)
                first_card = simplified_state["cards"][0]
                first_reader = matching_reader(simplified_state, first_card)
                page.locator(f'.mag-card-select[data-card-id="{first_card["id"]}"]').click()
                expect(page.locator(f'.mag-card-select[data-card-id="{first_card["id"]}"]')).to_have_attribute("aria-pressed", "true")
                page.screenshot(path=str(out_dir / "l5-simplified-selected.png"), full_page=True)
                page.locator(f'.stripe-insert-proxy[data-reader-id="{first_reader["id"]}"]').click()
                expect(page.locator(".stripe-proxy-execute")).to_have_text("EXECUTE CLEARANCE SWIPE")
                page.screenshot(path=str(out_dir / "l5-simplified-clearance-control.png"), full_page=True)

                inserted = {str(first_card["id"])}
                for card in simplified_state["cards"]:
                    reader = matching_reader(simplified_state, card)
                    if str(card["id"]) not in inserted:
                        page.locator(f'.mag-card-select[data-card-id="{card["id"]}"]').click()
                        page.locator(f'.stripe-insert-proxy[data-reader-id="{reader["id"]}"]').click()
                    duration = PROFILE_DURATIONS[str(reader["profile_token"])]
                    page.locator(f'.stripe-proxy-duration[data-reader-id="{reader["id"]}"]').fill(str(duration))
                    page.locator(f'.stripe-proxy-execute[data-reader-id="{reader["id"]}"]').click()
                    page.wait_for_function("readerId => magneticStripePurgatoryModel.readerLocked[readerId] === true", arg=reader["id"], timeout=15_000)
                page.locator("#stripe-audit").click()
                page.wait_for_function("() => document.querySelector('.readout')?.textContent === 'PASS'", timeout=30_000)
                page.screenshot(path=str(out_dir / "l5-simplified-pyodide-pass.png"), full_page=True)
                if errors:
                    raise AssertionError(f"static browser errors: {errors}")
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    summary = {
        "environment": ENVIRONMENT,
        "difficulty": 5,
        "viewport": [1280, 720],
        "static_browser_full_surface": "PASS",
        "static_browser_simplified_surface": "PASS",
        "static_browser_pyodide_grade": "PASS",
        "artifacts": [
            "l5-full-physical-surface.png",
            "l5-simplified-initial.png",
            "l5-simplified-selected.png",
            "l5-simplified-clearance-control.png",
            "l5-simplified-pyodide-pass.png",
        ],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
