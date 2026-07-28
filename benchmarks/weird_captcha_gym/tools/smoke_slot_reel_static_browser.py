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

from PIL import Image, ImageDraw
from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from benchmarks.weird_captcha_gym.dashboard.export_static import export_dashboard


ENVIRONMENT = "slot_reel_capture_env"
DIFFICULTY = 4
INTERACTION = "full"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Exercise Slot-Reel Character Capture through exported static "
            "browser play and its pinned Pyodide grader."
        )
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def wait_for_target(page, reel_id: str, target: str) -> None:
    page.wait_for_function(
        """({reelId, target}) => {
          const reel = document.querySelector(
            `.slot-reel[data-reel-id="${CSS.escape(reelId)}"]`
          );
          if (!reel) return false;
          const data = slotModel.state.reels.find((item) => item.id === reelId);
          if (!data) return false;
          const symbol = reel.querySelector(".slot-symbol")?.textContent || "";
          const elapsed = performance.now() - slotModel.startedAt;
          const actualIndex = (
            Math.floor(elapsed / data.interval_ms) + Number(data.phase || 0)
          ) % data.tokens.length;
          const position = (elapsed % data.interval_ms) / data.interval_ms;
          const remaining = data.interval_ms - (elapsed % data.interval_ms);
          const ratio = Number(slotModel.state.capture_window_ratio || 1);
          const safelyTimed = ratio < 1
            ? Math.abs(position - 0.5) < ratio * 0.12
            : remaining > Math.max(160, data.interval_ms * 0.70);
          return reel.dataset.active === "true"
            && reel.dataset.captureReady !== "false"
            && Number(reel.dataset.tokenIndex) === actualIndex
            && safelyTimed
            && symbol === target
            && data.tokens[actualIndex] === target;
        }""",
        arg={"reelId": reel_id, "target": target},
        timeout=15_000,
        polling=8,
    )


def solve(page, truth: dict, *, recovered_path: Path | None = None) -> None:
    for index, (reel_id, target) in enumerate(
        zip(truth["reel_ids"], truth["sequence"]),
        start=1,
    ):
        wait_for_target(page, str(reel_id), str(target))
        page.keyboard.press(str(target))
        expect(page.locator('.slot-reel[data-frozen="true"]')).to_have_count(
            index,
            timeout=2000,
        )
        if index == 1 and recovered_path is not None:
            expect(page.locator(".readout")).to_have_attribute(
                "data-status",
                "idle",
            )
            page.screenshot(path=str(recovered_path))
    page.locator("#submit-slot").click()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=90_000)


def fail_and_refresh(page, truth: dict) -> tuple[str, str]:
    before = str(truth["challenge_id"])
    max_strikes = int(truth["max_strikes"])
    for _ in range(max_strikes):
        page.keyboard.press("1")
    expect(page.locator(".readout")).to_have_text("FAIL", timeout=90_000)
    after = str(
        page.locator(".slot-captcha").get_attribute("data-challenge-id")
    )
    if after == before:
        raise AssertionError("static failure did not rotate to a fresh challenge")
    expect(page.locator(".slot-strikes-count")).to_have_text(
        f"0/{max_strikes}"
    )
    return before, after


def make_contact_sheet(out_dir: Path) -> None:
    selected = [
        ("DASHBOARD", "dashboard-slot-reel-browser-play.png"),
        ("L4 ORIGINAL", "target-static-initial.png"),
        (
            "PAUSED OBSERVATION CONTROLS",
            "target-static-paused-observation-controls.png",
        ),
        ("RAPID FAILURE / FRESH TASK", "target-static-fail-refresh.png"),
        ("RECOVERED KEY ACTION", "target-static-recovered-action.png"),
        ("PYODIDE PASS", "target-static-pyodide-pass.png"),
    ]
    width, height = 480, 300
    label_height = 32
    sheet = Image.new(
        "RGB",
        (width * 3, (height + label_height) * 2),
        "#12080a",
    )
    draw = ImageDraw.Draw(sheet)
    for index, (label, name) in enumerate(selected):
        row, column = divmod(index, 3)
        left = column * width
        top = row * (height + label_height)
        draw.text((left + 10, top + 9), label, fill="#ffe7a2")
        with Image.open(out_dir / name).convert("RGB") as frame:
            frame.thumbnail((width, height))
            tile = Image.new("RGB", (width, height), "#090405")
            tile.paste(
                frame,
                ((width - frame.width) // 2, (height - frame.height) // 2),
            )
        sheet.paste(tile, (left, top + label_height))
    sheet.save(out_dir / "contact_sheet.png")


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="slot-reel-static-") as temporary:
        site = Path(temporary) / "site"
        manifest = export_dashboard(site, copy_media=False)
        bundle_path = site / "play" / "challenges" / f"{ENVIRONMENT}.json"
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        profile = bundle["difficulty_profiles"][str(DIFFICULTY)][
            "interaction_profiles"
        ][INTERACTION]
        challenges = profile["challenges"]
        truth_by_challenge = {
            item["ground_truth"]["challenge_id"]: item["ground_truth"]
            for item in challenges
        }
        export_summary = {
            "dashboard_manifest": manifest,
            "environment_id": bundle["environment_id"],
            "mechanic_id": bundle["mechanic_id"],
            "default_difficulty": bundle["default_difficulty"],
            "default_interaction": bundle["default_interaction"],
            "difficulty_profiles": sorted(
                int(value) for value in bundle["difficulty_profiles"]
            ),
            "interaction_profiles_at_baseline": sorted(
                bundle["difficulty_profiles"][str(DIFFICULTY)][
                    "interaction_profiles"
                ]
            ),
            "baseline_challenge_count": len(challenges),
            "real_time": bundle["real_time"],
            "grader": bundle["grader"],
        }
        (args.out_dir / "target-static-export-summary.json").write_text(
            json.dumps(export_summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        handler = partial(QuietHandler, directory=str(site))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={"width": 1440, "height": 1000}
                )
                dashboard = context.new_page()
                dashboard.on(
                    "pageerror",
                    lambda error: errors.append(f"dashboard: {error}"),
                )
                dashboard.goto(
                    f"{base}/#/environment/{ENVIRONMENT}",
                    wait_until="networkidle",
                )
                expect(
                    dashboard.get_by_role("button", name="Try in browser")
                ).to_be_visible()
                dashboard.screenshot(
                    path=str(
                        args.out_dir / "dashboard-slot-reel-browser-play.png"
                    ),
                    full_page=True,
                )
                with context.expect_page() as opened:
                    dashboard.get_by_role(
                        "button",
                        name="Try in browser",
                    ).click()
                page = opened.value
                page.on(
                    "pageerror",
                    lambda error: errors.append(f"puzzle: {error}"),
                )
                page.goto(
                    (
                        f"{base}/play/?environment={ENVIRONMENT}&attempt=0"
                        f"&difficulty={DIFFICULTY}"
                        f"&interaction={INTERACTION}&time_mode=live"
                    ),
                    wait_until="networkidle",
                )
                page.wait_for_selector(
                    '.slot-captcha[data-interaction="full"]'
                )
                page.screenshot(
                    path=str(args.out_dir / "target-static-initial.png")
                )
                page.get_by_role(
                    "button",
                    name="Expand observation controls",
                ).click()
                expect(
                    page.get_by_role(
                        "button",
                        name="Capture model observation",
                    )
                ).to_be_visible()
                expect(page.locator("[data-demo-window]")).to_have_text(
                    "800 ms"
                )
                expect(page.locator("[data-demo-frames]")).to_have_text("6")
                page.get_by_role("button", name="Paused").click()
                page.wait_for_function(
                    "WeirdCaptchaTime.status().state === 'paused'"
                )
                page.screenshot(
                    path=str(
                        args.out_dir
                        / "target-static-paused-observation-controls.png"
                    )
                )
                page.get_by_role("button", name="Live").click()
                page.wait_for_function(
                    "WeirdCaptchaTime.status().state === 'running'"
                )

                first_challenge = str(
                    page.locator(".slot-captcha").get_attribute(
                        "data-challenge-id"
                    )
                )
                first_truth = truth_by_challenge[first_challenge]
                before, after = fail_and_refresh(page, first_truth)
                page.screenshot(
                    path=str(
                        args.out_dir / "target-static-fail-refresh.png"
                    )
                )
                second_truth = truth_by_challenge[after]
                solve(
                    page,
                    second_truth,
                    recovered_path=(
                        args.out_dir / "target-static-recovered-action.png"
                    ),
                )
                page.screenshot(
                    path=str(args.out_dir / "target-static-pyodide-pass.png")
                )

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
                        "static browser did not persist the passing result"
                    )
                grade = result.get("browser_grade") or {}
                if grade.get("passed") is not True:
                    raise AssertionError(
                        f"Pyodide grader rejected Slot Reel: {grade}"
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
    make_contact_sheet(args.out_dir)
    summary = {
        "environment": ENVIRONMENT,
        "difficulty": DIFFICULTY,
        "interaction": INTERACTION,
        "first_failed_challenge_id": before,
        "fresh_challenge_id": after,
        "fresh_failure_challenge": before != after,
        "rapid_keyboard_inputs_dispatched": 3,
        "rapid_keyboard_failure_recovered": True,
        "pyodide_grade": "PASS",
        "observation_window_ms": 800,
        "frames_per_observation": 6,
        "page_errors": [],
    }
    (args.out_dir / "target-static-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
