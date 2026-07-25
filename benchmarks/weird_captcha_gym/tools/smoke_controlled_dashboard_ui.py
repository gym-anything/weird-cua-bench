#!/usr/bin/env python3
from __future__ import annotations

import argparse

from playwright.sync_api import expect, sync_playwright


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify dashboard difficulty and interaction selection through browser play.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8769")
    parser.add_argument("--screenshot")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(f"dashboard: {error}"))
        page.goto(f"{args.base_url}/#/environments", wait_until="networkidle")
        page.locator('[data-open-env="rotating_keyboard_env"] .card-media').click()
        expect(page.locator(".detail-title")).to_have_text("Rotating On-Screen Keyboard")
        expect(page.locator("[data-interaction-mode]")).to_have_count(2)

        page.locator('[data-difficulty-level="1"]').click()
        page.locator('[data-interaction-mode="simplified"]').click()
        expect(page.locator('[data-interaction-mode="simplified"]')).to_have_class("is-active")
        if args.screenshot:
            page.screenshot(path=args.screenshot, full_page=True)
        with page.expect_popup() as popup_info:
            page.locator('.launch-console [data-quick-launch="rotating_keyboard_env"]').click()
        simplified = popup_info.value
        simplified.on("pageerror", lambda error: errors.append(f"simplified puzzle: {error}"))
        simplified.wait_for_load_state("networkidle")
        expect(simplified.locator('[data-interaction="simplified"]')).to_be_visible(timeout=15_000)
        assert "difficulty=1" in simplified.url and "interaction=simplified" in simplified.url
        simplified.close()

        page.locator('[data-interaction-mode="full"]').click()
        expect(page.locator('[data-interaction-mode="full"]')).to_have_class("is-active")
        with page.expect_popup() as popup_info:
            page.locator('.launch-console [data-quick-launch="rotating_keyboard_env"]').click()
        full = popup_info.value
        full.on("pageerror", lambda error: errors.append(f"full puzzle: {error}"))
        full.wait_for_load_state("networkidle")
        expect(full.locator('[data-interaction="full"]')).to_be_visible(timeout=15_000)
        assert "difficulty=1" in full.url and "interaction=full" in full.url
        full.close()

        if errors:
            raise AssertionError(errors)
        browser.close()
    print("dashboard selected and opened L1 simplified plus L1 full browser tasks")


if __name__ == "__main__":
    main()
