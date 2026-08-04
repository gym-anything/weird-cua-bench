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


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from weird_captcha_gym.dashboard.export_static import export_dashboard


ENVIRONMENT = "domino_autopsy_env"
DIFFICULTY = 3
INTERACTION = "full"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Exercise Domino Autopsy through its exported static browser "
            "runtime and pinned Pyodide replay grader."
        )
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def canvas_point(box: dict, x: float, y: float) -> tuple[float, float]:
    return (
        float(box["x"]) + x * float(box["width"]) / 720,
        float(box["y"]) + y * float(box["height"]) / 410,
    )


def solve(page, challenge: dict) -> None:
    public = challenge["public_state"]
    truth = challenge["ground_truth"]
    box = page.locator(".domino-physics-canvas").bounding_box()
    if box is None:
        raise AssertionError("static Domino canvas has no visible bounds")
    initial_by_id = {
        str(item["id"]): item for item in public["board"]["loose"]
    }
    for index, (domino_id, target) in enumerate(
        zip(truth["loose_ids"], truth["target_slots"])
    ):
        start_item = initial_by_id[str(domino_id)]
        start = canvas_point(box, float(start_item["x"]), float(start_item["y"]))
        end = canvas_point(box, float(target["x"]), float(target["y"]))
        page.mouse.move(*start)
        page.mouse.down()
        page.mouse.move(*end, steps=12)
        page.mouse.up()
        for _ in range(14):
            angle = float(
                page.evaluate(
                    "id => dominoAxisAngle(dominoModel.bodiesById[id].angle * 180 / Math.PI)",
                    str(domino_id),
                )
            )
            if abs(angle) <= 8:
                break
            page.locator("#domino-rotate-right").click()
        else:
            raise AssertionError(f"could not level static domino {domino_id}")
        if index == 0:
            page.locator("#domino-flip").click()
    page.locator("#domino-run").click()
    page.wait_for_function("dominoModel.mode === 'result'", timeout=12_000)
    expect(page.locator(".domino-verdict")).to_contain_text("PHYSICS PASS")
    page.locator("#domino-submit").click()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=90_000)


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="domino-static-") as temporary:
        site = Path(temporary) / "site"
        manifest = export_dashboard(site, copy_media=False)
        bundle = json.loads(
            (site / "play" / "challenges" / f"{ENVIRONMENT}.json").read_text(
                encoding="utf-8"
            )
        )
        profile = bundle["difficulty_profiles"][str(DIFFICULTY)][
            "interaction_profiles"
        ][INTERACTION]
        challenges = profile["challenges"]
        challenge_by_id = {
            str(item["public_state"]["challenge_id"]): item
            for item in challenges
        }
        (args.out_dir / "target-static-export-summary.json").write_text(
            json.dumps(
                {
                    "dashboard_manifest": manifest,
                    "environment_id": bundle["environment_id"],
                    "mechanic_id": bundle["mechanic_id"],
                    "default_difficulty": bundle["default_difficulty"],
                    "default_interaction": bundle["default_interaction"],
                    "difficulty_profiles": sorted(
                        int(value) for value in bundle["difficulty_profiles"]
                    ),
                    "baseline_challenge_count": len(challenges),
                    "real_time": bundle["real_time"],
                    "grader": bundle["grader"],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
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
                    dashboard.get_by_role("heading", name="Domino Autopsy")
                ).to_be_visible()
                expect(
                    dashboard.get_by_role("button", name="Try in browser")
                ).to_be_visible()
                dashboard.screenshot(
                    path=str(args.out_dir / "dashboard-domino-browser-play.png"),
                    full_page=True,
                )

                page = context.new_page()
                page.on(
                    "pageerror",
                    lambda error: errors.append(f"puzzle: {error}"),
                )
                page.goto(
                    (
                        f"{base}/play/?environment={ENVIRONMENT}&attempt=0"
                        f"&difficulty={DIFFICULTY}&interaction={INTERACTION}"
                        "&time_mode=live"
                    ),
                    wait_until="networkidle",
                )
                expect(
                    page.locator('.domino-captcha[data-interaction="full"]')
                ).to_be_visible()
                page.screenshot(path=str(args.out_dir / "target-static-initial.png"))
                page.get_by_role(
                    "button",
                    name="Expand observation controls",
                ).click()
                expect(page.locator("[data-demo-window]")).to_have_text("1000 ms")
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

                page.locator("#domino-run").click()
                page.wait_for_function(
                    "dominoModel.mode === 'result'",
                    timeout=12_000,
                )
                expect(page.locator(".domino-verdict")).to_contain_text(
                    "PHYSICS FAIL"
                )
                page.screenshot(
                    path=str(args.out_dir / "target-static-failure.png")
                )
                page.locator("#domino-reset").click()
                expect(page.locator(".domino-trace")).to_contain_text(
                    "PHYSICS READY"
                )
                page.screenshot(
                    path=str(args.out_dir / "target-static-recovery.png")
                )

                challenge_id = str(
                    page.locator(".domino-captcha").get_attribute(
                        "data-challenge-id"
                    )
                )
                solve(page, challenge_by_id[challenge_id])
                page.screenshot(
                    path=str(args.out_dir / "target-static-pyodide-pass.png")
                )
                storage_key = (
                    f"weird-cua-browser-results:{ENVIRONMENT}:"
                    f"d{DIFFICULTY}:i{INTERACTION}"
                )
                result = page.evaluate(
                    "key => JSON.parse(localStorage.getItem(key) || 'null')",
                    storage_key,
                )
                if not isinstance(result, dict):
                    raise AssertionError(
                        "static browser did not persist the Domino result"
                    )
                grade = result.get("browser_grade") or {}
                if grade.get("passed") is not True:
                    raise AssertionError(
                        f"Pyodide replay grader rejected Domino: {grade}"
                    )
                if "independent pose replay" not in str(grade.get("feedback")):
                    raise AssertionError(
                        f"static grade did not use revised replay: {grade}"
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
        "visible_failure": True,
        "visible_recovery": True,
        "pyodide_replay_grade": "PASS",
        "observation_window_ms": 1000,
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
