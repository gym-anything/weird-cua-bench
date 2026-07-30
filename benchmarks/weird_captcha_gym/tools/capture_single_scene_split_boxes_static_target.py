#!/usr/bin/env python3
"""Exercise every controlled Split Boxes condition in target-only static play."""
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
from benchmarks.weird_captcha_gym.shared_runtime.verifier_helpers import verify_external_mechanic


ENVIRONMENT = "single_scene_split_boxes_env"
MECHANIC = "single_scene_split_boxes"
RESOLUTION = {"width": 1280, "height": 720}


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
        default=ROOT / "benchmarks" / "weird_captcha_gym" / "environments" / ENVIRONMENT / "evidence_docs" / "static_target",
    )
    return parser.parse_args()


def normalized_fingerprint(public_state: dict[str, Any]) -> str:
    normalized = copy.deepcopy(public_state)
    for key in ("task_id", "challenge_id", "control_condition"):
        normalized.pop(key, None)
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def hold_sync(page: Page, milliseconds: int) -> None:
    button = page.locator("#mosaic-sync")
    box = button.bounding_box()
    if box is None:
        raise AssertionError("visible SCENE SYNC control has no bounds")
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.wait_for_timeout(milliseconds)
    page.mouse.up()


def solve_visible(page: Page, truth: dict[str, Any], interaction: str, evidence_dir: Path) -> None:
    """Use generated truth only to choose normal visible browser inputs."""

    tiles = list(truth["tiles"])
    slots: list[str | None] = [None] * len(tiles)
    for tile in tiles:
        slots[int(tile["initial_slot"])] = str(tile["id"])
    if any(slot is None for slot in slots):
        raise AssertionError("materialized static task has an empty initial slot")
    working_slots = [str(slot) for slot in slots]
    columns = int(truth["scene"].get("columns") or 3)
    target_slots = {
        int(tile["source"]["row"]) * columns + int(tile["source"]["column"]): str(tile["id"])
        for tile in tiles
    }
    changes = 0
    for destination in range(len(working_slots)):
        tile_id = target_slots[destination]
        if working_slots[destination] == tile_id:
            continue
        origin = working_slots.index(tile_id)
        displaced = working_slots[destination]
        if interaction == "simplified":
            page.locator(f'.mosaic-tile[data-tile-id="{tile_id}"]').click()
            page.locator(f'[data-swap-slot="{destination}"]').click()
        else:
            page.locator(f'.mosaic-tile[data-tile-id="{tile_id}"]').drag_to(
                page.locator(f'.mosaic-tile[data-tile-id="{displaced}"]')
            )
        page.wait_for_timeout(24)
        working_slots[origin], working_slots[destination] = working_slots[destination], working_slots[origin]
        changes += 1
        if changes == 3:
            page.screenshot(path=str(evidence_dir / "active-spatial.png"), full_page=True)

    for tile in tiles:
        if int(tile["initial_rotation"]) == 180:
            page.locator(f'.mosaic-tile[data-tile-id="{tile["id"]}"]').click()
            page.locator("#mosaic-rotate").click()
            page.wait_for_timeout(16)

    phases = [tile for tile in tiles if int(tile["initial_phase"]) != 0]
    for index, tile in enumerate(phases):
        page.locator(f'.mosaic-tile[data-tile-id="{tile["id"]}"]').click()
        track = page.locator("#phase-track")
        box = track.bounding_box()
        if box is None:
            raise AssertionError("visible temporal scrub track has no bounds")
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_timeout(16)
        if index == min(3, len(phases) - 1):
            page.screenshot(path=str(evidence_dir / "active-temporal.png"), full_page=True)

    expect(page.locator(".mosaic-errors > div.is-clear")).to_have_count(4, timeout=5_000)
    page.screenshot(path=str(evidence_dir / "coherent.png"), full_page=True)
    hold_sync(page, int(truth["requirements"]["hold_ms"]) + 140)
    expect(page.locator(".readout")).to_have_text("PASS", timeout=90_000)


def challenge_for_page(page: Page, challenges: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    challenge_id = str(page.locator(".mosaic-captcha").get_attribute("data-challenge-id") or "")
    if challenge_id not in challenges:
        raise AssertionError(f"static browser rendered unknown challenge {challenge_id!r}")
    return challenge_id, challenges[challenge_id]


def static_result(page: Page, challenge: dict[str, Any], level: int, interaction: str) -> dict[str, Any]:
    storage_key = f"weird-cua-browser-results:{ENVIRONMENT}:d{level}:i{interaction}"
    result = page.evaluate("key => JSON.parse(localStorage.getItem(key) || 'null')", storage_key)
    if not isinstance(result, dict):
        raise AssertionError("static browser did not persist its result")
    browser_grade = result.get("browser_grade") or {}
    if browser_grade.get("passed") is not True:
        raise AssertionError(f"Pyodide rejected visible static replay: {browser_grade}")
    verifier = verify_external_mechanic(
        {"result": result, "ground_truth": challenge["ground_truth"], "public_state": challenge["public_state"]},
        MECHANIC,
    )
    if verifier.get("passed") is not True or verifier.get("score") != 100:
        raise AssertionError(f"independent verifier rejected static replay: {verifier}")
    return {"browser_result": result, "pyodide_grade": browser_grade, "independent_exported_verifier": verifier}


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="split-boxes-static-target-") as temporary_name:
        site = Path(temporary_name) / "site"
        export = _export_browser_play(site, target_catalog())
        bundle = json.loads((site / "play" / "challenges" / f"{ENVIRONMENT}.json").read_text(encoding="utf-8"))
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
                    "target_export_manifest": export,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(site)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        records: dict[str, dict[str, Any]] = {}
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport=RESOLUTION, device_scale_factor=1)
                for level in range(1, 6):
                    profile = bundle["difficulty_profiles"][str(level)]
                    for interaction in ("simplified", "full"):
                        label = f"d{level}-{interaction}"
                        evidence_dir = out_dir / label
                        evidence_dir.mkdir(parents=True, exist_ok=True)
                        challenge_by_id = {
                            str(item["ground_truth"]["challenge_id"]): item
                            for item in profile["interaction_profiles"][interaction]["challenges"]
                        }
                        page = context.new_page()
                        page.on("pageerror", lambda error, label=label: errors.append(f"{label}: {error}"))
                        try:
                            page.goto(
                                f"{base_url}/play/?environment={ENVIRONMENT}&attempt=0&difficulty={level}"
                                f"&interaction={interaction}&time_mode=live",
                                wait_until="networkidle",
                            )
                            expect(page.locator(f'.mosaic-captcha[data-interaction="{interaction}"]')).to_be_visible()
                            initial_id, initial_challenge = challenge_for_page(page, challenge_by_id)
                            page.screenshot(path=str(evidence_dir / "initial.png"), full_page=True)
                            failed_then_recovered = False
                            challenge_id, challenge = initial_id, initial_challenge
                            if level == 4 and interaction == "full":
                                hold_sync(page, 760)
                                expect(page.locator(".readout")).to_contain_text("FAIL", timeout=90_000)
                                page.screenshot(path=str(evidence_dir / "failure.png"), full_page=True)
                                page.wait_for_function(
                                    "previous => document.querySelector('.mosaic-captcha')?.dataset.challengeId !== previous",
                                    arg=initial_id,
                                    timeout=5_000,
                                )
                                challenge_id, challenge = challenge_for_page(page, challenge_by_id)
                                if challenge_id == initial_id:
                                    raise AssertionError("static failure did not issue a fresh challenge")
                                page.screenshot(path=str(evidence_dir / "fresh-retry.png"), full_page=True)
                                failed_then_recovered = True
                            solve_visible(page, challenge["ground_truth"], interaction, evidence_dir)
                            page.screenshot(path=str(evidence_dir / "pyodide-pass.png"), full_page=True)
                            result = static_result(page, challenge, level, interaction)
                            (evidence_dir / "browser-result.json").write_text(
                                json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                            )
                            records[label] = {
                                "difficulty": level,
                                "interaction": interaction,
                                "initial_challenge_id": initial_id,
                                "solved_challenge_id": challenge_id,
                                "initial_world_fingerprint": normalized_fingerprint(initial_challenge["public_state"]),
                                "failed_then_recovered": failed_then_recovered,
                                "pyodide_grade": result["pyodide_grade"],
                                "independent_exported_verifier": result["independent_exported_verifier"],
                            }
                        finally:
                            page.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
    if errors:
        raise AssertionError(f"static Split Boxes page errors: {errors}")
    for level in range(1, 6):
        simplified = records[f"d{level}-simplified"]
        full = records[f"d{level}-full"]
        if simplified["initial_world_fingerprint"] != full["initial_world_fingerprint"]:
            raise AssertionError(f"static L{level} interaction modes generated different worlds")
    output = {
        "environment": ENVIRONMENT,
        "static_export": "target-only browser-play export",
        "conditions": records,
        "all_ten_pyodide_replays": "PASS",
        "visible_failure_and_recovery": "d4-full",
        "page_errors": [],
    }
    (out_dir / "target-static-summary.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
