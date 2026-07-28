#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from benchmarks.weird_captcha_gym.dashboard.export_static import export_dashboard


ENVIRONMENT = "popup_exorcist_env"
DIFFICULTY = 2
INTERACTION = "full"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Exercise Popup Exorcist through exported static browser play and "
            "the bundled Python grader running in Pyodide."
        )
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def center(locator) -> tuple[float, float]:
    box = locator.bounding_box()
    if box is None:
        raise AssertionError("visible Popup Exorcist target has no bounding box")
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def close_window(page, window_id: str) -> None:
    page.locator(f'[data-window-id="{window_id}"] .parasite-close').click()


def provoke(page, challenge: dict) -> None:
    public = challenge["public_state"]
    truth = challenge["ground_truth"]
    parasite = str(truth["parasite_id"])
    parasite_z = next(
        int(item["z"]) for item in public["popups"] if item["id"] == parasite
    )
    for popup in sorted(
        public["popups"],
        key=lambda item: int(item["z"]),
        reverse=True,
    ):
        if int(popup["z"]) > parasite_z:
            close_window(page, str(popup["id"]))
    close_window(page, parasite)
    expect(page.locator(".containment-well[data-active='true']")).to_be_visible()


def fail_and_refresh(page, challenge: dict, out_dir: Path) -> str:
    truth = challenge["ground_truth"]
    parasite = str(truth["parasite_id"])
    initial_challenge = str(truth["challenge_id"])
    provoke(page, challenge)
    close = page.locator(f'[data-window-id="{parasite}"] .parasite-close')
    for _ in range(int(truth.get("maximum_resistance_strikes") or 3)):
        close.click()
    expect(page.locator(".readout")).to_have_text("FAIL", timeout=90_000)
    page.screenshot(path=str(out_dir / "target-static-failure-visible.png"))
    expect(page.locator(".parasite-captcha")).not_to_have_attribute(
        "data-challenge-id",
        initial_challenge,
        timeout=90_000,
    )
    fresh = page.locator(".parasite-captcha").get_attribute("data-challenge-id")
    if not fresh or fresh == initial_challenge:
        raise AssertionError("static failure did not rotate to a fresh challenge")
    page.screenshot(path=str(out_dir / "target-static-fresh-retry.png"))
    return fresh


def solve(page, challenge: dict, out_dir: Path) -> None:
    truth = challenge["ground_truth"]
    provoke(page, challenge)
    page.screenshot(path=str(out_dir / "target-static-replication-visible.png"))
    echo_id = str(truth["echo_ids"][-1])
    echo = page.locator(f'[data-window-id="{echo_id}"]')
    header = echo.locator("header")
    well = page.locator(".containment-well")
    sx, sy = center(header)
    wx, wy = center(well)
    echo_box = echo.bounding_box()
    if echo_box is None:
        raise AssertionError("infected echo has no visible bounding box")
    end = (
        wx + (sx - (echo_box["x"] + echo_box["width"] / 2)),
        wy + (sy - (echo_box["y"] + echo_box["height"] / 2)),
    )
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.mouse.move(*end, steps=12)
    page.screenshot(path=str(out_dir / "target-static-contained-before-release.png"))
    page.mouse.up()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=90_000)
    page.screenshot(path=str(out_dir / "target-static-pyodide-pass.png"))


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="popup-exorcist-static-") as temporary:
        site = Path(temporary) / "site"
        export_dashboard(site, copy_media=False)
        bundle = json.loads(
            (site / "play" / "challenges" / f"{ENVIRONMENT}.json").read_text(
                encoding="utf-8"
            )
        )
        challenges = bundle["difficulty_profiles"][str(DIFFICULTY)][
            "interaction_profiles"
        ][INTERACTION]["challenges"]
        challenge_by_id = {
            str(item["ground_truth"]["challenge_id"]): item
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
                page = browser.new_page(
                    viewport={"width": 1280, "height": 720},
                    device_scale_factor=1,
                )
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(
                    f"{base}/play/?environment={ENVIRONMENT}&attempt=0"
                    f"&difficulty={DIFFICULTY}&interaction={INTERACTION}"
                    "&time_mode=live",
                    wait_until="networkidle",
                )
                expect(
                    page.locator(
                        f'.parasite-captcha[data-interaction="{INTERACTION}"]'
                    )
                ).to_be_visible()
                first_id = page.locator(".parasite-captcha").get_attribute(
                    "data-challenge-id"
                )
                if first_id not in challenge_by_id:
                    raise AssertionError(
                        f"unknown first static Popup Exorcist challenge {first_id}"
                    )
                page.screenshot(path=str(args.out_dir / "target-static-initial.png"))
                fresh_id = fail_and_refresh(
                    page,
                    challenge_by_id[str(first_id)],
                    args.out_dir,
                )
                if fresh_id not in challenge_by_id:
                    raise AssertionError(
                        f"unknown fresh static Popup Exorcist challenge {fresh_id}"
                    )
                solve(page, challenge_by_id[fresh_id], args.out_dir)
                storage_key = (
                    "weird-cua-browser-results:"
                    f"{ENVIRONMENT}:d{DIFFICULTY}:i{INTERACTION}"
                )
                result = page.evaluate(
                    "key => JSON.parse(localStorage.getItem(key) || 'null')",
                    storage_key,
                )
                if not isinstance(result, dict):
                    raise AssertionError(
                        "static browser did not persist the Popup Exorcist result"
                    )
                if (result.get("browser_grade") or {}).get("passed") is not True:
                    raise AssertionError(
                        f"Pyodide rejected Popup Exorcist: {result.get('browser_grade')}"
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
        "difficulty": DIFFICULTY,
        "interaction": INTERACTION,
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
