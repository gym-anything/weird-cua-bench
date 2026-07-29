#!/usr/bin/env python3
"""Exercise Relation Prompt Grounding through the exported static browser runtime."""

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

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from benchmarks.weird_captcha_gym.dashboard.export_static import export_dashboard
from benchmarks.weird_captcha_gym.shared_runtime.verifier_helpers import verify_external_mechanic


ENVIRONMENT = "relation_prompt_grounding_env"
MECHANIC = "relation_prompt_grounding"
TITLE = "Dual-Projection Sculpture Rig"
DIFFICULTY = 4
RESOLUTION = {"width": 1920, "height": 1080}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return

    def copyfile(self, source, outputfile) -> None:
        try:
            super().copyfile(source, outputfile)
        except BrokenPipeError:
            return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def stage_target(page, target: dict[str, Any], stage: dict[str, Any]) -> tuple[float, float]:
    box = page.locator(".rel-stage").bounding_box()
    if box is None:
        raise AssertionError("relation assembly stage is not visible")
    return (
        box["x"] + int(target["x"]) / int(stage["width"]) * box["width"],
        box["y"] + int(target["y"]) / int(stage["height"]) * box["height"],
    )


def direct_place(page, object_id: str, target: dict[str, Any], stage: dict[str, Any]) -> None:
    object_node = page.locator(f'.rel-object[data-object-id="{object_id}"]')
    box = object_node.bounding_box()
    if box is None:
        raise AssertionError(f"full object {object_id} is not visible")
    destination = stage_target(page, target, stage)
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(*destination, steps=9)
    page.mouse.up()


def proxy_place(page, object_id: str, target: dict[str, Any], stage: dict[str, Any]) -> None:
    object_node = page.locator(f'.rel-object[data-object-id="{object_id}"]')
    box = object_node.bounding_box()
    if box is None:
        raise AssertionError(f"simplified object {object_id} is not visible")
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.click(*stage_target(page, target, stage))


def direct_depth(page, object_id: str, depth: int) -> None:
    page.locator(f'.rel-console .rel-select[data-object-id="{object_id}"]').click()
    track = page.locator(".rel-depth-track").bounding_box()
    knob = page.locator(".rel-depth-knob").bounding_box()
    if track is None or knob is None:
        raise AssertionError("full depth rail is not visible")
    x = track["x"] + track["width"] / 2
    target_y = track["y"] + (100 - depth) / 100 * track["height"]
    page.mouse.move(knob["x"] + knob["width"] / 2, knob["y"] + knob["height"] / 2)
    page.mouse.down()
    page.mouse.move(x, target_y, steps=7)
    page.mouse.up()


def proxy_depth(page, object_id: str, depth: int) -> None:
    page.locator(f'.rel-console .rel-select[data-object-id="{object_id}"]').click()
    current = 50
    while abs(depth - current) >= 10:
        delta = 10 if depth > current else -10
        page.locator(f'.rel-depth-proxies button[data-delta="{delta}"]').click()
        current += delta
    while current != depth:
        delta = 1 if depth > current else -1
        page.locator(f'.rel-depth-proxies button[data-delta="{delta}"]').click()
        current += delta


def solve(page, interaction: str, truth: dict[str, Any], out_dir: Path) -> None:
    ordered = [item["id"] for item in truth["objects"] if item.get("container")]
    ordered.extend(item["id"] for item in truth["objects"] if not item.get("container"))
    place = direct_place if interaction == "full" else proxy_place
    depth = direct_depth if interaction == "full" else proxy_depth
    for object_id in ordered:
        place(page, object_id, truth["solution_positions"][object_id], truth["stage"])
    expect(page.locator(".rel-placed-count[data-ready='true']")).to_contain_text(f"{len(ordered)}/{len(ordered)}")
    for object_id, target in truth["solution_positions"].items():
        if int(target["depth"]) != 50:
            depth(page, object_id, int(target["depth"]))
    page.locator(".rel-settle").click()
    page.wait_for_timeout(300)
    page.screenshot(path=str(out_dir / f"target-static-d4-{interaction}-settling.png"))
    page.wait_for_function("() => window.relationAssemblyModel.settled === true", timeout=5_000)
    page.screenshot(path=str(out_dir / f"target-static-d4-{interaction}-settled.png"))
    page.locator(".rel-submit").click()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=90_000)
    page.screenshot(path=str(out_dir / f"target-static-d4-{interaction}-pyodide-pass.png"))


def selected_challenge(page, challenges: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    challenge_id = page.locator(".relation-assembly-captcha").get_attribute("data-challenge-id")
    if not challenge_id or challenge_id not in challenges:
        raise AssertionError(f"static runtime selected an unknown challenge: {challenge_id}")
    return challenge_id, challenges[challenge_id]


def world_fingerprint(item: dict[str, Any]) -> str:
    state = copy.deepcopy(item["public_state"])
    for key in ("task_id", "challenge_id", "control_condition"):
        state.pop(key, None)
    return hashlib.sha256(json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def exercise(page, interaction: str, challenges: dict[str, dict[str, Any]], out_dir: Path) -> dict[str, Any]:
    expect(page.locator(f'.relation-assembly-captcha[data-interaction="{interaction}"]')).to_be_visible()
    if interaction == "full":
        expect(page.locator(".rel-depth-track")).to_be_visible()
        expect(page.locator(".rel-depth-proxies button")).to_have_count(0)
    else:
        expect(page.locator(".rel-depth-track")).to_have_count(0)
        expect(page.locator(".rel-depth-proxies button")).to_have_count(4)
    first_id, first = selected_challenge(page, challenges)
    page.screenshot(path=str(out_dir / f"target-static-d4-{interaction}-initial.png"))
    page.locator(".rel-submit").click()
    expect(page.locator(".readout")).to_contain_text("FAIL", timeout=90_000)
    page.screenshot(path=str(out_dir / f"target-static-d4-{interaction}-failure.png"))
    fresh_id, fresh = selected_challenge(page, challenges)
    if fresh_id == first_id:
        raise AssertionError(f"static {interaction} failure did not issue a fresh challenge")
    page.screenshot(path=str(out_dir / f"target-static-d4-{interaction}-fresh-retry.png"))
    solve(page, interaction, fresh["ground_truth"], out_dir)
    storage_key = f"weird-cua-browser-results:{ENVIRONMENT}:d{DIFFICULTY}:i{interaction}"
    result = page.evaluate("key => JSON.parse(localStorage.getItem(key) || 'null')", storage_key)
    if not isinstance(result, dict):
        raise AssertionError(f"static {interaction} runtime did not persist its result")
    pyodide_grade = result.get("browser_grade") or {}
    if pyodide_grade.get("passed") is not True:
        raise AssertionError(f"static Pyodide rejected {interaction}: {pyodide_grade}")
    verifier = verify_external_mechanic(
        {"result": result, "ground_truth": fresh["ground_truth"], "public_state": fresh["public_state"]},
        MECHANIC,
    )
    if verifier.get("passed") is not True or verifier.get("score") != 100:
        raise AssertionError(f"independent exported verifier rejected {interaction}: {verifier}")
    record = {
        "first_challenge_id": first_id,
        "fresh_challenge_id": fresh_id,
        "initial_world_fingerprint": world_fingerprint(first),
        "fresh_world_fingerprint": world_fingerprint(fresh),
        "browser_result": result,
        "pyodide_grade": pyodide_grade,
        "independent_exported_verifier": verifier,
    }
    (out_dir / f"target-static-d4-{interaction}-result.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return record


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="relation-prompt-grounding-static-") as temporary_name:
        site = Path(temporary_name) / "site"
        manifest = export_dashboard(site, copy_media=False)
        bundle = json.loads((site / "play" / "challenges" / f"{ENVIRONMENT}.json").read_text(encoding="utf-8"))
        profile = bundle["difficulty_profiles"][str(DIFFICULTY)]
        handler = partial(QuietHandler, directory=str(site))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        records: dict[str, dict[str, Any]] = {}
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport=RESOLUTION, device_scale_factor=1)
                dashboard = context.new_page()
                dashboard.on("pageerror", lambda error: errors.append(f"dashboard: {error}"))
                dashboard.goto(f"{base}/#/environment/{ENVIRONMENT}", wait_until="networkidle")
                expect(dashboard.get_by_role("heading", name=TITLE)).to_be_visible()
                expect(dashboard.get_by_role("button", name="Try in browser")).to_be_visible()
                dashboard.screenshot(path=str(args.out_dir / "dashboard-browser-play.png"), full_page=True)
                for interaction in ("full", "simplified"):
                    challenges = {
                        str(item["ground_truth"]["challenge_id"]): item
                        for item in profile["interaction_profiles"][interaction]["challenges"]
                    }
                    page = context.new_page()
                    page.on("pageerror", lambda error, mode=interaction: errors.append(f"{mode}: {error}"))
                    page.goto(
                        f"{base}/play/?environment={ENVIRONMENT}&attempt=0&difficulty={DIFFICULTY}"
                        f"&interaction={interaction}&time_mode=live",
                        wait_until="networkidle",
                    )
                    records[interaction] = exercise(page, interaction, challenges, args.out_dir)
                    page.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
    if errors:
        raise AssertionError(f"static browser errors: {errors}")
    if records["full"]["initial_world_fingerprint"] != records["simplified"]["initial_world_fingerprint"]:
        raise AssertionError("static full and simplified initial worlds differ")
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
        "paired_initial_world": True,
        "dashboard_manifest": manifest["browser_play"],
        "result_records": {
            interaction: {
                "first_challenge_id": record["first_challenge_id"],
                "fresh_challenge_id": record["fresh_challenge_id"],
                "pyodide_passed": record["pyodide_grade"].get("passed"),
                "verifier_score": record["independent_exported_verifier"].get("score"),
            }
            for interaction, record in records.items()
        },
        "page_errors": [],
    }
    (args.out_dir / "target-static-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
