#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from weird_captcha_gym.dashboard.export_static import export_dashboard


ENVIRONMENT = "parallel_grillmaster_env"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exercise Parallel Grillmaster through exported static browser play and Pyodide grading."
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def pointer_drag(page, source, target) -> None:
    source_box = source.bounding_box()
    target_box = target.bounding_box()
    if not source_box or not target_box:
        raise AssertionError("drag endpoints are not visible")
    page.mouse.move(source_box["x"] + source_box["width"] / 2, source_box["y"] + source_box["height"] / 2)
    page.mouse.down()
    page.mouse.move(target_box["x"] + target_box["width"] / 2, target_box["y"] + target_box["height"] / 2)
    page.mouse.up()


def solve(page, truth: dict) -> None:
    grill = page.locator('.grill-zone[data-drop-zone="grill"]')
    tray = page.locator('.grill-zone[data-drop-zone="tray"]')
    due = []
    for food_id, target in truth["targets"].items():
        pointer_drag(page, page.locator(f'.grill-food[data-food-id="{food_id}"]'), grill)
        expect(
            grill.locator(f'.grill-food[data-food-id="{food_id}"]')
        ).to_be_visible()
        started = float(
            page.evaluate("foodId => grillModel.records[foodId].startedAt", food_id)
        )
        due.append((started + float(target["target_ms"]), food_id))
    for due_at, food_id in sorted(due):
        now = float(page.evaluate("performance.now()"))
        if due_at > now:
            page.wait_for_timeout(int(due_at - now))
        pointer_drag(page, page.locator(f'.grill-food[data-food-id="{food_id}"]'), tray)
        expect(
            tray.locator(f'.grill-food[data-food-id="{food_id}"]')
        ).to_be_visible()
    page.locator("#submit-grill").click()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=90_000)


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="parallel-grillmaster-static-") as temporary:
        site = Path(temporary) / "site"
        export_dashboard(site, copy_media=False)
        bundle = json.loads(
            (site / "play" / "challenges" / f"{ENVIRONMENT}.json").read_text(
                encoding="utf-8"
            )
        )
        challenges = bundle["difficulty_profiles"]["2"]["interaction_profiles"]["full"][
            "challenges"
        ]
        truth_by_challenge = {
            item["ground_truth"]["challenge_id"]: item["ground_truth"]
            for item in challenges
        }
        handler = partial(QuietHandler, directory=str(site))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        errors: list[str] = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 720})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(
                    f"{base}/play/?environment={ENVIRONMENT}&attempt=0&difficulty=2"
                    "&interaction=full&time_mode=live",
                    wait_until="networkidle",
                )
                page.wait_for_selector('.grill-captcha[data-interaction="full"]')
                first_challenge = page.locator(".grill-captcha").get_attribute(
                    "data-challenge-id"
                )
                page.locator("#submit-grill").click()
                expect(page.locator(".readout")).to_have_text("FAIL", timeout=90_000)
                second_challenge = page.locator(".grill-captcha").get_attribute(
                    "data-challenge-id"
                )
                if first_challenge == second_challenge:
                    raise AssertionError("static failure did not rotate to a fresh challenge")
                page.screenshot(
                    path=str(args.out_dir / "target-static-fail-refresh.png")
                )
                solve(page, truth_by_challenge[str(second_challenge)])
                page.screenshot(path=str(args.out_dir / "target-static-pyodide-pass.png"))
                storage_key = (
                    "weird-cua-browser-results:"
                    f"{ENVIRONMENT}:d2:ifull"
                )
                result = page.evaluate(
                    "key => JSON.parse(localStorage.getItem(key) || 'null')",
                    storage_key,
                )
                if not isinstance(result, dict):
                    raise AssertionError("static browser did not persist the passing result")
                if (result.get("browser_grade") or {}).get("passed") is not True:
                    raise AssertionError(
                        f"Pyodide grader rejected Grillmaster: {result.get('browser_grade')}"
                    )
                (args.out_dir / "target-static-result.json").write_text(
                    json.dumps(result, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
    if errors:
        raise AssertionError(f"browser errors: {errors}")
    summary = {
        "environment": ENVIRONMENT,
        "difficulty": 2,
        "interaction": "full",
        "fresh_failure_challenge": True,
        "pyodide_grade": "PASS",
        "page_errors": [],
    }
    (args.out_dir / "target-static-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
