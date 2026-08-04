#!/usr/bin/env python3
"""Capture every Tomographic Baggage Surgery control pair in static Pyodide play.

The script uses only a temporary static export, a 127.0.0.1 server, and
headless Chromium with a new browser context.  Ground truth chooses normal
visible pointer and button inputs solely to exercise browser/Pyodide wiring;
it is not a screenshot-only-agent evaluation.
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


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from weird_captcha_gym.dashboard.catalog import build_catalog
from weird_captcha_gym.dashboard.export_static import _export_browser_play
from weird_captcha_gym.shared_runtime.verifier_helpers import verify_external_mechanic


ENVIRONMENT = "tomographic_baggage_surgery_env"
MECHANIC = "tomographic_baggage_surgery"
VIEWPORT = {"width": 1280, "height": 720}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "weird_captcha_gym" / "environments" / ENVIRONMENT / "evidence_docs" / "static",
    )
    return parser.parse_args()


def target_catalog() -> dict[str, Any]:
    catalog = copy.deepcopy(build_catalog())
    catalog["environments"] = [item for item in catalog["environments"] if item.get("id") == ENVIRONMENT]
    if len(catalog["environments"]) != 1:
        raise AssertionError("target environment is not uniquely available for static export")
    return catalog


def world_fingerprint(public_state: dict[str, Any]) -> str:
    normalized = copy.deepcopy(public_state)
    for key in ("task_id", "challenge_id", "control_condition", "prompt", "rules"):
        normalized.pop(key, None)
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def challenge_for_page(page: Page, challenges: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    challenge_id = str(page.locator(".tomo-captcha").get_attribute("data-challenge-id") or "")
    if challenge_id not in challenges:
        raise AssertionError(f"static browser rendered unknown tomography challenge {challenge_id!r}")
    return challenge_id, challenges[challenge_id]


def set_offset(page: Page, target: float) -> None:
    target = max(-3.0, min(3.0, round(target / .25) * .25))
    for _ in range(30):
        current = float(page.evaluate("() => window.tomographicBaggageSurgeryModel.offset"))
        if abs(current - target) < .01:
            return
        selector = ".tomo-offset[data-delta='.25']" if target > current else ".tomo-offset[data-delta='-.25']"
        page.locator(selector).click()
    raise AssertionError("static tomography slice offset did not settle")


def direct_sweep_x(page: Page, offset: float) -> None:
    canvas = page.locator(".tomo-slice")
    box = canvas.bounding_box()
    if box is None:
        raise AssertionError("static direct tomography canvas has no bounds")
    center_x = box["x"] + box["width"] / 2
    center_y = box["y"] + box["height"] / 2
    target_x = box["x"] + (max(-3.0, min(3.0, offset)) + 3.0) / 6.0 * box["width"]
    page.mouse.move(center_x, center_y)
    page.mouse.down()
    page.mouse.move(target_x, center_y, steps=8)
    page.mouse.up()
    page.wait_for_timeout(35)


def direct_sweep_y(page: Page, offset: float) -> None:
    canvas = page.locator(".tomo-slice")
    box = canvas.bounding_box()
    if box is None:
        raise AssertionError("static direct tomography Y-depth rail has no bounds")
    # Mirrors the visible x=28..492, y=218..234 Y-depth rail in the 520x245
    # source canvas.  Starting at -2.75 guarantees a direct Y event even if
    # the target happens to be centered at zero.
    rail_left, rail_width, rail_y = 28, 464, 226
    start_x = box["x"] + (rail_left + rail_width / 24) / 520 * box["width"]
    target_x = box["x"] + (rail_left + (max(-3.0, min(3.0, offset)) + 3.0) / 6.0 * rail_width) / 520 * box["width"]
    target_y = box["y"] + rail_y / 245 * box["height"]
    page.mouse.move(start_x, target_y)
    page.mouse.down()
    page.mouse.move(target_x, target_y, steps=8)
    page.mouse.up()
    page.wait_for_timeout(35)


def direct_rotate_case(page: Page) -> None:
    canvas = page.locator(".tomo-slice")
    box = canvas.bounding_box()
    if box is None:
        raise AssertionError("static tomography case handle has no bounds")
    start_x = box["x"] + 470 / 520 * box["width"]
    start_y = box["y"] + 35 / 245 * box["height"]
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(start_x - 12, start_y + 26, steps=6)
    page.mouse.up()
    page.wait_for_timeout(35)


def target_x_at_rotation(target: list[float], rotation: int) -> float:
    x, _, z = target
    return (x, z, -x, -z)[rotation % 4]


def scan_and_lock(page: Page, truth: dict[str, Any], evidence_dir: Path) -> None:
    interaction = str(truth["control_condition"]["interaction"])
    if interaction == "full":
        page.locator(".tomo-fresh").wait_for(state="hidden", timeout=4_000)
    target = [float(value) for value in truth["solver"]["target"]]
    requirements = truth["requirements"]
    rotations = max(int(requirements["min_rotations"]), int(requirements["min_target_observations"]))

    if interaction == "simplified":
        page.locator(".tomo-axis-buttons button[data-axis='y']").click()
        set_offset(page, target[1])
    else:
        direct_sweep_y(page, target[1])
    evidence_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(evidence_dir / "y-depth-slice.png"), full_page=True)

    if interaction == "simplified":
        page.locator(".tomo-axis-buttons button[data-axis='x']").click()
        set_offset(page, target_x_at_rotation(target, 0))
    else:
        direct_sweep_x(page, target_x_at_rotation(target, 0))
    evidence_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(evidence_dir / "hot-slice.png"), full_page=True)

    if interaction == "simplified":
        set_offset(page, -2.5)
    else:
        direct_sweep_x(page, -2.5)
    for rotation in range(1, rotations):
        if interaction == "simplified":
            page.locator(".tomo-rotate").click()
            page.locator(".tomo-axis-buttons button[data-axis='x']").click()
            set_offset(page, target_x_at_rotation(target, rotation))
        else:
            direct_rotate_case(page)
            direct_sweep_x(page, target_x_at_rotation(target, rotation))
        if rotation < rotations - 1:
            if interaction == "simplified":
                set_offset(page, 2.5)
            else:
                direct_sweep_x(page, 2.5)
    while int(page.evaluate("() => window.tomographicBaggageSurgeryModel.observations")) < int(requirements["min_observations"]):
        if interaction == "simplified":
            set_offset(page, -2.5)
        else:
            direct_sweep_x(page, -2.5)
    page.locator(".tomo-lock").click()
    expect(page.locator(".tomo-slicer[data-locked='true']")).to_be_visible()


def screen_coordinate(box: dict[str, float], view: dict[str, Any], coordinate: list[float]) -> tuple[float, float]:
    index = {"x": 0, "y": 1, "z": 2}
    local = [
        float(view["center"][screen_index])
        + float(view["scale"]) * float(view["signs"][screen_index]) * coordinate[index[axis]]
        for screen_index, axis in enumerate(view["axes"])
    ]
    return (
        box["x"] + local[0] / float(view["width"]) * box["width"],
        box["y"] + local[1] / float(view["height"]) * box["height"],
    )


def drag_view(page: Page, truth: dict[str, Any], view_id: str, coordinate: list[float], steps: int = 28) -> None:
    canvas = page.locator(f".tomo-probe[data-view='{view_id}']")
    box = canvas.bounding_box()
    if box is None:
        raise AssertionError(f"static {view_id} probe canvas has no bounds")
    current = page.evaluate("() => [...window.tomographicBaggageSurgeryModel.probe]")
    view = truth["views"][view_id]
    page.mouse.move(*screen_coordinate(box, view, current))
    page.mouse.down()
    page.mouse.move(*screen_coordinate(box, view, coordinate), steps=steps)
    page.mouse.up()
    page.wait_for_timeout(50)


def solve_visible(page: Page, truth: dict[str, Any], evidence_dir: Path) -> None:
    scan_and_lock(page, truth, evidence_dir)
    target = [float(value) for value in truth["solver"]["target"]]
    safe_y = float(truth["solver"]["safe_y"])
    drag_view(page, truth, "top", [target[0], safe_y, target[2]])
    drag_view(page, truth, "front", target)
    if int(truth["requirements"].get("min_moving_views", 0)) >= 3:
        drag_view(page, truth, "side", [target[0], safe_y, target[2]])
        drag_view(page, truth, "side", target)
    elif int(truth["requirements"].get("min_views", 2)) >= 3:
        drag_view(page, truth, "side", target)
    page.screenshot(path=str(evidence_dir / "probe-registered.png"), full_page=True)
    page.locator(".tomo-capture").click()
    expect(page.locator(".tomo-probe-state")).to_have_text("TARGET HELD")
    drag_view(page, truth, "front", [target[0], safe_y, target[2]], steps=36)
    expect(page.locator(".tomo-complete[data-visible='true']")).to_be_visible()
    page.locator(".tomo-submit").click()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=90_000)


def static_result(page: Page, challenge: dict[str, Any], level: int, interaction: str) -> dict[str, Any]:
    storage_key = f"weird-cua-browser-results:{ENVIRONMENT}:d{level}:i{interaction}"
    result = page.evaluate("key => JSON.parse(localStorage.getItem(key) || 'null')", storage_key)
    if not isinstance(result, dict):
        raise AssertionError("static browser did not persist its tomography result")
    grade = result.get("browser_grade") or {}
    if grade.get("passed") is not True or grade.get("score") != 100:
        raise AssertionError(f"Pyodide rejected static tomography replay: {grade}")
    verifier = verify_external_mechanic(
        {"result": result, "ground_truth": challenge["ground_truth"], "public_state": challenge["public_state"]},
        MECHANIC,
    )
    if verifier.get("passed") is not True or verifier.get("score") != 100:
        raise AssertionError(f"exported verifier rejected static tomography replay: {verifier}")
    return {"browser_result": result, "pyodide_grade": grade, "independent_exported_verifier": verifier}


def target_y_observation(result: dict[str, Any]) -> dict[str, Any]:
    events = result["browser_result"]["events"]
    y_events = [item for item in events if item.get("kind") == "slice_observation" and item.get("axis") == "y"]
    event = y_events[-1] if y_events else None
    if not isinstance(event, dict):
        raise AssertionError("visible solve did not record a Y-plane observation")
    return copy.deepcopy(event)


def comparable_y_observation(event: dict[str, Any]) -> dict[str, Any]:
    return {key: event[key] for key in ("axis", "offset", "rotation", "records", "digest")}


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="tomography-static-target-") as temporary_name:
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
                context = browser.new_context(viewport=VIEWPORT, device_scale_factor=1)
                for level in range(1, 6):
                    profile = bundle["difficulty_profiles"][str(level)]
                    for interaction in ("simplified", "full"):
                        label = f"d{level}-{interaction}"
                        evidence_dir = out_dir / label
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
                            expect(page.locator(f'.tomo-captcha[data-interaction="{interaction}"]')).to_be_visible()
                            initial_id, initial_challenge = challenge_for_page(page, challenge_by_id)
                            evidence_dir.mkdir(parents=True, exist_ok=True)
                            page.screenshot(path=str(evidence_dir / "initial.png"), full_page=True)
                            solved_id, solved_challenge = initial_id, initial_challenge
                            failed_then_recovered = False
                            if level == 4 and interaction == "full":
                                page.locator(".tomo-submit").click()
                                expect(page.locator(".readout")).to_contain_text("FAIL", timeout=90_000)
                                page.screenshot(path=str(evidence_dir / "failure-fresh-volume.png"), full_page=True)
                                page.wait_for_function(
                                    "previous => document.querySelector('.tomo-captcha')?.dataset.challengeId !== previous",
                                    arg=initial_id,
                                    timeout=8_000,
                                )
                                solved_id, solved_challenge = challenge_for_page(page, challenge_by_id)
                                if solved_id == initial_id:
                                    raise AssertionError("static tomography failure did not issue a fresh challenge")
                                page.screenshot(path=str(evidence_dir / "fresh-retry.png"), full_page=True)
                                failed_then_recovered = True
                            solve_visible(page, solved_challenge["ground_truth"], evidence_dir)
                            page.screenshot(path=str(evidence_dir / "pyodide-pass.png"), full_page=True)
                            result = static_result(page, solved_challenge, level, interaction)
                            requirements = solved_challenge["ground_truth"]["requirements"]
                            browser_result = result["browser_result"]
                            if "min_target_rotations" in requirements:
                                if len(browser_result.get("target_rotations") or []) < int(requirements["min_target_rotations"]):
                                    raise AssertionError("static solve omitted required hot target rotations")
                            if "min_moving_views" in requirements:
                                if len(browser_result.get("moving_views") or []) < int(requirements["min_moving_views"]):
                                    raise AssertionError("static solve omitted required moving probe views")
                            (evidence_dir / "browser-result.json").write_text(
                                json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                            )
                            records[label] = {
                                "difficulty": level,
                                "interaction": interaction,
                                "initial_challenge_id": initial_id,
                                "solved_challenge_id": solved_id,
                                "initial_world_fingerprint": world_fingerprint(initial_challenge["public_state"]),
                                "failed_then_recovered": failed_then_recovered,
                                "pyodide_grade": result["pyodide_grade"],
                                "independent_exported_verifier": result["independent_exported_verifier"],
                                "target_y_plane_observation": target_y_observation(result),
                                "active_reconstruction_contract": {
                                    "min_target_rotations": requirements.get("min_target_rotations"),
                                    "recorded_target_rotations": browser_result.get("target_rotations"),
                                    "min_moving_views": requirements.get("min_moving_views"),
                                    "recorded_moving_views": browser_result.get("moving_views"),
                                },
                            }
                        finally:
                            page.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
    if errors:
        raise AssertionError(f"static tomography page errors: {errors}")
    for level in range(1, 6):
        simplified = records[f"d{level}-simplified"]
        full = records[f"d{level}-full"]
        if simplified["initial_world_fingerprint"] != full["initial_world_fingerprint"]:
            raise AssertionError(f"static L{level} interaction modes generated different worlds")
    y_equivalence = {
        "difficulty": 2,
        "simplified": records["d2-simplified"]["target_y_plane_observation"],
        "full": records["d2-full"]["target_y_plane_observation"],
    }
    if comparable_y_observation(y_equivalence["simplified"]) != comparable_y_observation(y_equivalence["full"]):
        raise AssertionError("same static L2 world produced different simplified/full Y-plane records")
    (out_dir / "y-plane-equivalence.json").write_text(
        json.dumps(y_equivalence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = {
        "environment": ENVIRONMENT,
        "static_export": "target-only browser-play export",
        "conditions": records,
        "all_ten_pyodide_replays": "PASS",
        "visible_failure_and_recovery": "d4-full",
        "shared_y_plane_equivalence": "d2 simplified/full records match except interaction input source",
        "page_errors": [],
    }
    (out_dir / "target-static-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
