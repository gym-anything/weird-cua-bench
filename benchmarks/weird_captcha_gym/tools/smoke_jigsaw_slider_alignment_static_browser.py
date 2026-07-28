#!/usr/bin/env python3
"""Exercise Jigsaw Slider Alignment through exported static browser play."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from benchmarks.weird_captcha_gym.dashboard.export_static import export_dashboard
from benchmarks.weird_captcha_gym.shared_runtime.verifier_helpers import verify_external_mechanic


ENVIRONMENT = "jigsaw_slider_alignment_env"
MECHANIC = "jigsaw_slider_alignment"
TITLE = "Parallax / Inertial Jigsaw Alignment"
DIFFICULTY = 4
RESOLUTION = {"width": 1280, "height": 720}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return

    def copyfile(self, source, outputfile) -> None:
        try:
            super().copyfile(source, outputfile)
        except BrokenPipeError:
            # Browser shutdown can cancel a background static-asset fetch.
            return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def center(locator) -> tuple[float, float]:
    box = locator.bounding_box()
    if box is None:
        raise AssertionError("visible control has no bounding box")
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def rail(page) -> int:
    return int(page.evaluate("() => window.jigsawSliderAlignmentModel.rail"))


def depth(page) -> int:
    return int(page.evaluate("() => window.jigsawSliderAlignmentModel.depth"))


def wait_for_settle(page) -> None:
    page.wait_for_function("() => window.jigsawSliderAlignmentModel.inertia === null", timeout=5_000)


def set_depth(page, interaction: str, target: int) -> None:
    if interaction == "simplified":
        for _ in range(100):
            delta = target - depth(page)
            if abs(delta) <= 9:
                return
            amount = 100 if abs(delta) >= 100 else 10
            page.locator(f'[data-depth-nudge="{amount if delta > 0 else -amount}"]').click()
        raise AssertionError(f"simplified depth did not reach {target}; current={depth(page)}")
    for _ in range(8):
        delta = target - depth(page)
        if abs(delta) <= 2:
            return
        grip = page.locator("#alignment-depth-grip")
        track = page.locator("#alignment-depth-track")
        grip_box = grip.bounding_box()
        track_box = track.bounding_box()
        if grip_box is None or track_box is None:
            raise AssertionError("direct depth controls are not visible")
        start_x = grip_box["x"] + grip_box["width"] / 2
        start_y = grip_box["y"] + grip_box["height"] / 2
        target_y = start_y - delta * track_box["height"] / 1000
        page.mouse.move(start_x, start_y)
        page.mouse.down()
        page.mouse.move(start_x, target_y)
        page.mouse.up()
        page.wait_for_function("() => window.jigsawSliderAlignmentModel.depthDrag === null")
    raise AssertionError(f"direct depth did not reach {target}; current={depth(page)}")


def set_rail(page, interaction: str, target: int) -> None:
    if interaction == "simplified":
        for _ in range(90):
            wait_for_settle(page)
            delta = target - rail(page)
            if abs(delta) <= 3_000:
                return
            # Fine static buttons are the visible slow-release path. Coarse
            # buttons visibly coast and are independently captured below.
            page.locator(f'[data-rail-nudge="{5_000 if delta > 0 else -5_000}"]').click()
        raise AssertionError(f"simplified rail did not reach {target}; current={rail(page)}")
    for _ in range(8):
        wait_for_settle(page)
        delta = target - rail(page)
        if abs(delta) <= 2_000:
            return
        carriage = page.locator("#alignment-carriage")
        start_x, start_y = center(carriage)
        tail = 1 if delta > 0 else -1
        page.mouse.move(start_x, start_y)
        page.mouse.down()
        page.mouse.move(start_x + delta / 1000 - tail, start_y)
        page.wait_for_timeout(175)
        page.mouse.move(start_x + delta / 1000, start_y)
        page.mouse.up()
        wait_for_settle(page)
    raise AssertionError(f"direct rail did not reach {target}; current={rail(page)}")


def rotate_to_target(page, truth: dict[str, Any]) -> None:
    piece = truth["scene"]["piece"]
    current = int(piece["initial_rotation_deg"])
    target = int(piece["target_rotation_deg"])
    step = int(piece["rotation_step_deg"])
    clockwise = ((target - current) % 360) // step
    counterclockwise = ((current - target) % 360) // step
    selector = "#alignment-rotate-right" if clockwise <= counterclockwise else "#alignment-rotate-left"
    for _ in range(min(clockwise, counterclockwise)):
        page.locator(selector).click()


def hold_lock(page, milliseconds: int) -> None:
    x, y = center(page.locator("#alignment-scan"))
    page.mouse.move(x, y)
    page.mouse.down()
    page.wait_for_timeout(milliseconds)
    page.mouse.up()


def challenge_for_page(page, challenges: dict[str, dict[str, Any]]) -> dict[str, Any]:
    challenge_id = page.locator(".alignment-captcha").get_attribute("data-challenge-id")
    if not challenge_id or challenge_id not in challenges:
        raise AssertionError(f"static page selected an unknown challenge: {challenge_id}")
    return challenges[challenge_id]


def solve(page, interaction: str, truth: dict[str, Any], out_dir: Path) -> None:
    set_depth(page, interaction, int(truth["target_depth_milli"]))
    set_rail(page, interaction, int(truth["target_rail_milli"]))
    rotate_to_target(page, truth)
    page.wait_for_function("() => document.querySelectorAll('.alignment-axis-pair > div.is-locked').length === 3")
    page.screenshot(path=str(out_dir / f"target-static-d4-{interaction}-aligned.png"))
    hold_lock(page, int(truth["tolerances"]["hold_ms"]) + 100)
    expect(page.locator(".readout")).to_have_text("PASS", timeout=90_000)
    page.screenshot(path=str(out_dir / f"target-static-d4-{interaction}-pyodide-pass.png"))


def static_result(page, interaction: str, challenge: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    storage_key = f"weird-cua-browser-results:{ENVIRONMENT}:d{DIFFICULTY}:i{interaction}"
    result = page.evaluate("key => JSON.parse(localStorage.getItem(key) || 'null')", storage_key)
    if not isinstance(result, dict):
        raise AssertionError(f"static browser did not save a result for {interaction}")
    browser_grade = result.get("browser_grade") or {}
    if browser_grade.get("passed") is not True:
        raise AssertionError(f"Pyodide rejected {interaction}: {browser_grade}")
    verifier = verify_external_mechanic(
        {
            "result": result,
            "ground_truth": challenge["ground_truth"],
            "public_state": challenge["public_state"],
        },
        MECHANIC,
    )
    if verifier.get("passed") is not True or verifier.get("score") != 100:
        raise AssertionError(f"independent exported verifier rejected {interaction}: {verifier}")
    record = {
        "browser_result": result,
        "pyodide_grade": browser_grade,
        "independent_exported_verifier": verifier,
    }
    (out_dir / f"target-static-d4-{interaction}-result.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return record


def exercise_interaction(page, interaction: str, challenges: dict[str, dict[str, Any]], out_dir: Path) -> dict[str, Any]:
    expect(page.locator(f'.alignment-captcha[data-interaction="{interaction}"]')).to_be_visible()
    if interaction == "full":
        expect(page.locator("#alignment-carriage")).to_be_visible()
        expect(page.locator("#alignment-depth-grip")).to_be_visible()
        expect(page.locator("[data-rail-nudge]")).to_have_count(0)
    else:
        expect(page.locator("#alignment-carriage")).to_have_count(0)
        expect(page.locator("#alignment-depth-grip")).to_have_count(0)
        expect(page.locator("[data-rail-nudge]")).to_have_count(4)
        expect(page.locator("[data-depth-nudge]")).to_have_count(4)
    initial = challenge_for_page(page, challenges)
    page.screenshot(path=str(out_dir / f"target-static-d4-{interaction}-initial.png"))
    initial_id = str(initial["ground_truth"]["challenge_id"])
    hold_lock(page, 760)
    expect(page.locator(".readout")).to_contain_text("FAIL", timeout=90_000)
    page.screenshot(path=str(out_dir / f"target-static-d4-{interaction}-failure.png"))
    fresh = challenge_for_page(page, challenges)
    if fresh["ground_truth"]["challenge_id"] == initial_id:
        raise AssertionError(f"static failure did not refresh {interaction}")
    page.screenshot(path=str(out_dir / f"target-static-d4-{interaction}-fresh-retry.png"))
    solve(page, interaction, fresh["ground_truth"], out_dir)
    return static_result(page, interaction, fresh, out_dir)


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="jigsaw-static-browser-") as temporary_name:
        site = Path(temporary_name) / "site"
        manifest = export_dashboard(site, copy_media=False)
        bundle = json.loads((site / "play" / "challenges" / f"{ENVIRONMENT}.json").read_text(encoding="utf-8"))
        profile = bundle["difficulty_profiles"][str(DIFFICULTY)]
        records: dict[str, Any] = {}
        handler = partial(QuietHandler, directory=str(site))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport=RESOLUTION, device_scale_factor=1)
                context.add_init_script(
                    """(() => {
                      const canvas = document.createElement('canvas');
                      canvas.width = 1280;
                      canvas.height = 720;
                      const context = canvas.getContext('2d');
                      let frame = 0;
                      setInterval(() => {
                        frame += 1;
                        context.fillStyle = frame % 2 ? '#102418' : '#182d3a';
                        context.fillRect(0, 0, canvas.width, canvas.height);
                        context.fillStyle = '#c7ff35';
                        context.font = '48px monospace';
                        context.fillText(`CAPTURE ${frame}`, 80, 120);
                      }, 32);
                      const mediaDevices = navigator.mediaDevices || {};
                      Object.defineProperty(mediaDevices, 'getDisplayMedia', {
                        configurable: true,
                        value: async () => canvas.captureStream(30),
                      });
                      if (!navigator.mediaDevices) {
                        Object.defineProperty(navigator, 'mediaDevices', {configurable: true, value: mediaDevices});
                      }
                    })()"""
                )
                dashboard = context.new_page()
                dashboard.on("pageerror", lambda error: errors.append(f"dashboard: {error}"))
                dashboard.goto(f"{base}/#/environment/{ENVIRONMENT}", wait_until="networkidle")
                expect(dashboard.get_by_role("heading", name=TITLE)).to_be_visible()
                expect(dashboard.get_by_role("button", name="Try in browser")).to_be_visible()
                dashboard.screenshot(path=str(args.out_dir / "dashboard-browser-play.png"), full_page=True)
                with context.expect_page() as opened:
                    dashboard.get_by_role("button", name="Try in browser").click()
                page = opened.value
                if f"environment={ENVIRONMENT}" not in page.url:
                    raise AssertionError(f"target dashboard opened the wrong static play URL: {page.url}")
                for interaction in ("full", "simplified"):
                    challenges = {
                        str(item["ground_truth"]["challenge_id"]): item
                        for item in profile["interaction_profiles"][interaction]["challenges"]
                    }
                    if interaction == "full":
                        active_page = page
                    else:
                        active_page = context.new_page()
                    active_page.on("pageerror", lambda error, mode=interaction: errors.append(f"{mode}: {error}"))
                    active_page.goto(
                        f"{base}/play/?environment={ENVIRONMENT}&attempt=0&difficulty={DIFFICULTY}"
                        f"&interaction={interaction}&time_mode=live",
                        wait_until="networkidle",
                    )
                    if interaction == "full":
                        active_page.get_by_role("button", name="Expand observation controls").click()
                        active_page.get_by_role("button", name="Paused").click()
                        active_page.wait_for_function("WeirdCaptchaTime.status().state === 'paused'")
                        active_page.get_by_role("button", name="Capture model observation").click()
                        expect(active_page.locator(".weird-demo-observation")).to_have_attribute("data-open", "true", timeout=10_000)
                        expect(active_page.locator(".weird-demo-frame")).to_have_count(4)
                        active_page.screenshot(path=str(args.out_dir / "browser-observation-viewer.png"), full_page=True)
                        active_page.get_by_role("button", name="Close").click()
                        active_page.get_by_role("button", name="Live").click()
                        active_page.wait_for_function("WeirdCaptchaTime.status().state === 'running'")
                        active_page.get_by_role("button", name="Collapse observation controls").click()
                    records[interaction] = exercise_interaction(active_page, interaction, challenges, args.out_dir)
                    if interaction == "full":
                        active_page.screenshot(path=str(args.out_dir / "browser-play-pyodide-pass.png"), full_page=True)
                    else:
                        active_page.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
    if errors:
        raise AssertionError(f"static browser errors: {errors}")
    summary = {
        "environment": ENVIRONMENT,
        "title": TITLE,
        "difficulty": DIFFICULTY,
        "interactions": ["full", "simplified"],
        "observation_resolution": [RESOLUTION["width"], RESOLUTION["height"]],
        "dashboard_one_click": True,
        "visible_failure_and_fresh_retry": True,
        "static_pyodide_grade": "PASS",
        "independent_exported_verifier": "PASS / 100",
        "dashboard_manifest": manifest["browser_play"],
        "result_records": {
            interaction: {
                "pyodide_passed": record["pyodide_grade"].get("passed"),
                "verifier_score": record["independent_exported_verifier"].get("score"),
            }
            for interaction, record in records.items()
        },
        "page_errors": [],
    }
    (args.out_dir / "target-static-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
