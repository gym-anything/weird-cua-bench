#!/usr/bin/env python3
"""Exercise Code-to-Diagram's isolated static browser export.

The full static-site smoke deliberately exports every environment.  This
targeted companion is useful when an unrelated generator prevents that broad
export from reaching this environment: it uses the same browser-play exporter,
then drives every controlled Code-to-Diagram condition through visible browser
controls and the exported Pyodide grader.
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

from playwright.sync_api import Page, expect, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from benchmarks.weird_captcha_gym.dashboard.catalog import build_catalog
from benchmarks.weird_captcha_gym.dashboard.export_static import _export_browser_play


ENVIRONMENT = "code_to_diagram_captcha_env"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Exercise every Code-to-Diagram controlled condition through its "
            "isolated static export and Pyodide replay grader."
        )
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def _drag(page: Page, source_selector: str, target_selector: str) -> None:
    source = page.locator(source_selector)
    target = page.locator(target_selector)
    source.scroll_into_view_if_needed()
    target.scroll_into_view_if_needed()
    start = source.bounding_box()
    end = target.bounding_box()
    if not start or not end:
        raise AssertionError(f"missing drag geometry: {source_selector} -> {target_selector}")
    start_x = start["x"] + start["width"] / 2
    start_y = start["y"] + start["height"] / 2
    end_x = end["x"] + end["width"] / 2
    end_y = end["y"] + end["height"] / 2
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move((start_x + end_x) / 2, (start_y + end_y) / 2, steps=8)
    page.mouse.move(end_x, end_y, steps=8)
    page.mouse.up()


def _solve_visible(page: Page, challenge: dict[str, Any], interaction: str) -> None:
    """Replay a known generated instance only through visible task controls."""

    public = challenge["public_state"]
    truth = challenge["ground_truth"]
    probe_indices = {int(value): index for index, value in enumerate(public["probe_inputs"])}
    for expected_run in truth["expected_probe_runs"]:
        probe = int(expected_run["input"])
        page.locator(f'[data-probe-index="{probe_indices[probe]}"]').click()
        for _step in expected_run["steps"]:
            page.locator("#flow-step").click()
            page.wait_for_timeout(22)

    for edge in truth["expected_edges"]:
        source = f'[data-port-id="{edge["from_port"]}"]'
        target = f'.flow-port-in[data-node-id="{edge["to_node"]}"]'
        if interaction == "simplified":
            page.locator(source).click()
            page.locator(target).click()
        else:
            _drag(page, source, target)
        page.wait_for_timeout(18)

    page.locator("#flow-certify").click()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=90_000)


def _world_fingerprint(public_state: dict[str, Any]) -> str:
    value = copy.deepcopy(public_state)
    for key in ("task_id", "challenge_id", "control_condition"):
        value.pop(key, None)
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _target_catalog() -> dict[str, Any]:
    catalog = copy.deepcopy(build_catalog())
    environments = [
        environment
        for environment in catalog["environments"]
        if str(environment.get("id")) == ENVIRONMENT
    ]
    if len(environments) != 1:
        raise AssertionError(f"could not select exactly one target environment: {environments}")
    catalog["environments"] = environments
    return catalog


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    conditions: dict[str, dict[str, Any]] = {}

    with tempfile.TemporaryDirectory(prefix="code-to-diagram-static-") as temporary:
        site = Path(temporary) / "site"
        export_manifest = _export_browser_play(site, _target_catalog())
        bundle = json.loads(
            (site / "play" / "challenges" / f"{ENVIRONMENT}.json").read_text(encoding="utf-8")
        )
        (out_dir / "target-static-export-summary.json").write_text(
            json.dumps(
                {
                    "environment_id": bundle["environment_id"],
                    "mechanic_id": bundle["mechanic_id"],
                    "default_difficulty": bundle["default_difficulty"],
                    "default_interaction": bundle["default_interaction"],
                    "difficulty_profiles": sorted(int(level) for level in bundle["difficulty_profiles"]),
                    "real_time": bundle["real_time"],
                    "grader": bundle["grader"],
                    "target_export_manifest": export_manifest,
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
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1280, "height": 720})
                for difficulty in range(1, 6):
                    profile = bundle["difficulty_profiles"][str(difficulty)]
                    for interaction in ("simplified", "full"):
                        label = f"d{difficulty}-{interaction}"
                        evidence_dir = out_dir / label
                        evidence_dir.mkdir(parents=True, exist_ok=True)
                        challenge_profile = profile["interaction_profiles"][interaction]
                        challenge_by_id = {
                            str(item["public_state"]["challenge_id"]): item
                            for item in challenge_profile["challenges"]
                        }
                        page = context.new_page()
                        page.on("pageerror", lambda error, label=label: errors.append(f"{label}: {error}"))
                        try:
                            page.goto(
                                f"{base_url}/play/?environment={ENVIRONMENT}&attempt=0"
                                f"&difficulty={difficulty}&interaction={interaction}&time_mode=live",
                                wait_until="networkidle",
                            )
                            root = page.locator(f'.flow-lab[data-interaction="{interaction}"]')
                            expect(root).to_be_visible()
                            initial_id = str(root.get_attribute("data-challenge-id") or "")
                            if initial_id not in challenge_by_id:
                                raise AssertionError(f"{label} rendered an unknown challenge {initial_id!r}")
                            page.screenshot(path=str(evidence_dir / "initial.png"), full_page=True)

                            challenge_id = initial_id
                            fresh_failure = False
                            if difficulty == 4 and interaction == "full":
                                page.locator("#flow-certify").click()
                                expect(page.locator(".flow-fail-stamp")).to_be_visible(timeout=90_000)
                                challenge_id = str(
                                    page.locator(".flow-lab").get_attribute("data-challenge-id") or ""
                                )
                                if not challenge_id or challenge_id == initial_id:
                                    raise AssertionError("static failure did not issue a fresh controller")
                                if challenge_id not in challenge_by_id:
                                    raise AssertionError("fresh static controller is not in its export pool")
                                fresh_failure = True
                                page.screenshot(path=str(evidence_dir / "fail-refresh.png"), full_page=True)

                            _solve_visible(page, challenge_by_id[challenge_id], interaction)
                            page.screenshot(path=str(evidence_dir / "pyodide-pass.png"), full_page=True)
                            storage_key = (
                                f"weird-cua-browser-results:{ENVIRONMENT}:"
                                f"d{difficulty}:i{interaction}"
                            )
                            result = page.evaluate(
                                "key => JSON.parse(localStorage.getItem(key) || 'null')",
                                storage_key,
                            )
                            if not isinstance(result, dict):
                                raise AssertionError(f"{label} did not persist its browser result")
                            grade = result.get("browser_grade") or {}
                            if grade.get("passed") is not True:
                                raise AssertionError(f"{label} Pyodide grader rejected the replay: {grade}")
                            (evidence_dir / "browser-result.json").write_text(
                                json.dumps(result, indent=2, sort_keys=True) + "\n",
                                encoding="utf-8",
                            )
                            conditions[label] = {
                                "challenge_id_before_failure": initial_id,
                                "solved_challenge_id": challenge_id,
                                "initial_world_fingerprint": _world_fingerprint(
                                    challenge_by_id[initial_id]["public_state"]
                                ),
                                "interaction": interaction,
                                "difficulty": difficulty,
                                "fresh_failure_and_recovery": fresh_failure,
                                "pyodide_grade": grade,
                            }
                        finally:
                            page.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    if errors:
        raise AssertionError(f"browser errors: {errors}")
    summary = {
        "environment": ENVIRONMENT,
        "static_export": "target-only browser-play export",
        "conditions": conditions,
        "all_ten_pyodide_replays": "PASS",
        "visible_failure_and_recovery": "d4-full",
        "page_errors": [],
    }
    (out_dir / "target-static-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
