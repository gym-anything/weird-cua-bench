#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
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


ENVIRONMENT = "consequences_boss_env"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Exercise Consequences Boss through exported static browser play "
            "and its pinned Pyodide grader."
        )
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def center(locator) -> tuple[float, float]:
    box = locator.bounding_box()
    if box is None:
        raise AssertionError("visible interaction target has no bounding box")
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def drag_relic(page, socket: str) -> None:
    relic = page.locator(".covenant-relic")
    target = page.locator(f'.covenant-socket[data-socket="{socket}"]')
    start = center(relic)
    end = center(target)
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move(*end, steps=12)
    page.mouse.up()


def set_seal(page, value: int, positions: int = 4) -> None:
    seal = page.locator(".covenant-seal")
    cx, cy = center(seal)
    angle = -0.5 * math.pi + value * (2 * math.pi / positions)
    point = (cx + 32 * math.cos(angle), cy + 32 * math.sin(angle))
    page.mouse.move(*point)
    page.mouse.down()
    page.mouse.move(*point, steps=2)
    page.mouse.up()


def answer(page, socket: str, seal: int) -> None:
    drag_relic(page, socket)
    set_seal(page, seal)
    page.locator(".covenant-bind").click()


def make_commitments(page, public_state: dict) -> dict[str, tuple[str, int]]:
    parameters = (
        (public_state.get("control_condition") or {}).get(
            "difficulty_parameters"
        )
        or {}
    )
    sockets = [str(value) for value in parameters.get(
        "socket_options",
        ["left", "right"],
    )]
    positions = int(parameters.get("seal_positions", 4))
    minimum_distinct = int(parameters.get("minimum_distinct_states", 1))
    states = [
        (socket, seal)
        for socket in sockets
        for seal in range(positions)
    ]
    choices = {}
    for index, scene in enumerate(public_state["scenes"]):
        choices[str(scene["id"])] = (
            states[index] if index < minimum_distinct else states[0]
        )
        answer(page, *choices[str(scene["id"])])
    expect(page.locator(".covenant-phase")).to_contain_text(
        "RECKONING",
        timeout=8_000,
    )
    return choices


def finish(page, public_state: dict, *, wrong_first: bool = False) -> None:
    choices = make_commitments(page, public_state)
    for index, scene_id in enumerate(public_state["boss_order"]):
        socket, seal = choices[str(scene_id)]
        if wrong_first and index == 0:
            socket = "right"
        answer(page, socket, seal)


def challenge_by_id(challenges: list[dict], challenge_id: str) -> dict:
    for challenge in challenges:
        if str(challenge["public_state"]["challenge_id"]) == challenge_id:
            return challenge
    raise AssertionError(f"static challenge pool is missing {challenge_id}")


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="consequences-boss-static-") as temporary:
        site = Path(temporary) / "site"
        export_dashboard(site, copy_media=False)
        bundle = json.loads(
            (site / "play" / "challenges" / f"{ENVIRONMENT}.json").read_text(
                encoding="utf-8"
            )
        )
        challenges = bundle["difficulty_profiles"]["1"]["interaction_profiles"][
            "full"
        ]["challenges"]
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
                    f"{base}/play/?environment={ENVIRONMENT}&attempt=0"
                    "&difficulty=1&interaction=full&time_mode=live",
                    wait_until="networkidle",
                )
                expect(
                    page.locator('.covenant-captcha[data-interaction="full"]')
                ).to_be_visible()
                layout = page.evaluate(
                    """() => ({
                      viewport: [innerWidth, innerHeight],
                      document: [
                        document.documentElement.scrollWidth,
                        document.documentElement.scrollHeight,
                      ],
                    })"""
                )
                if layout["document"] != [1290, 740]:
                    raise AssertionError(
                        "static target differs from the preserved pre-control "
                        f"document geometry: {layout}"
                    )
                first_id = str(
                    page.locator(".covenant-captcha").get_attribute(
                        "data-challenge-id"
                    )
                )
                first = challenge_by_id(challenges, first_id)
                finish(page, first["public_state"], wrong_first=True)
                verdict = page.locator(".covenant-verdict")
                expect(verdict).to_be_visible(timeout=90_000)
                expect(verdict.locator("strong")).to_have_text("FAIL")
                page.screenshot(
                    path=str(args.out_dir / "target-static-failure.png")
                )
                page.wait_for_timeout(1_200)
                expect(verdict).to_be_visible()
                expect(verdict.locator(".covenant-retry")).to_be_enabled()
                verdict.locator(".covenant-retry").click()
                page.wait_for_function(
                    """previous => {
                      const node = document.querySelector(".covenant-captcha");
                      return node && node.dataset.challengeId !== previous;
                    }""",
                    arg=first_id,
                    timeout=10_000,
                )
                second_id = str(
                    page.locator(".covenant-captcha").get_attribute(
                        "data-challenge-id"
                    )
                )
                if first_id == second_id:
                    raise AssertionError(
                        "static failure did not rotate to a fresh challenge"
                    )
                page.screenshot(
                    path=str(args.out_dir / "target-static-recovery.png")
                )
                second = challenge_by_id(challenges, second_id)
                finish(page, second["public_state"])
                expect(page.locator(".readout")).to_have_text(
                    "PASS",
                    timeout=90_000,
                )
                page.screenshot(
                    path=str(args.out_dir / "target-static-pyodide-pass.png")
                )
                storage_key = (
                    f"weird-cua-browser-results:{ENVIRONMENT}:d1:ifull"
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
                        f"Pyodide grader rejected Consequences Boss: {grade}"
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
        "difficulty": 1,
        "interaction": "full",
        "fresh_failure_challenge": True,
        "persistent_failure_after_1200_ms": True,
        "explicit_visible_retry": True,
        "pyodide_grade": "PASS",
        "page_errors": [],
        "viewport": [1280, 720],
        "document_extent": [1290, 740],
    }
    (args.out_dir / "target-static-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
