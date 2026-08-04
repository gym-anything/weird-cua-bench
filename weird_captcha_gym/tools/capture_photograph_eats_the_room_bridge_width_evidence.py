#!/usr/bin/env python3
"""Capture profile-dependent bridge rendering and collision evidence.

This script uses only fresh local state directories, loopback servers, and a
headless Playwright browser.  It develops every profile's bridge through
visible controls, then demonstrates browser collision at either side of the
L1 and L5 width boundary.  It also records the same boundary calls against the
authoritative replay collision function.  The accepted L1 route completes the
task and retains its server-grade/exported-verifier records.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from weird_captcha_gym.tools import smoke_controlled_interaction_ui as browser_smoke


ENVIRONMENT = "photograph_eats_the_room_env"
MECHANIC = "photograph_eats_the_room"
ENV_ROOT = ROOT / "weird_captcha_gym" / "environments" / ENVIRONMENT
VIEWPORT = browser_smoke.observation_viewport(ENV_ROOT)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture profile-dependent visible bridge-width and collision-boundary evidence in an isolated headless browser."
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ENV_ROOT / "evidence_docs" / "bridge_width_boundary",
        help="Evidence output directory.",
    )
    return parser.parse_args()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def develop_bridge(page: Any, state_dir: Path, solver: Any, *, out_dir: Path, label: str) -> dict[str, Any]:
    truth = browser_smoke.read_json(state_dir / "ground_truth.json")
    expect(page.locator(".photo-room")).to_have_attribute("data-active", "true")
    capture = truth["solution"]["captures"][0]
    placement = truth["solution"]["placements"][0]
    solver._move_to(page, capture["camera"])
    solver._turn_to(page, float(capture["camera"]["yaw_deg"]))
    solver._capture(page)
    expect(page.locator(".photo-room")).to_have_attribute("data-carrying", "beam")
    solver._move_to(page, placement["camera"])
    solver._turn_to(page, float(placement["camera"]["yaw_deg"]))
    solver._place_plane(page, truth, truth["sockets"][0])
    solver._scale_to(page, float(placement["scale"]))
    solver._rotate_plane_to(page, int(placement["rotation_deg"]))
    page.locator("#photo-develop").click()
    expect(page.locator(".photo-room")).to_have_attribute("data-operation-count", "1")
    page.screenshot(path=str(out_dir / f"l{label}-bridge-developed.png"), full_page=True)
    return truth


def move_near_edge(page: Any, truth: dict[str, Any], solver: Any, *, inside: bool, out_dir: Path, label: str) -> dict[str, float | bool]:
    room = truth["room"]
    half_width = float(truth["qualification"]["bridge_half_width"])
    lane_y = float(room["lane_y"])
    # The selected values are safely either side of the exact collision edge,
    # while leaving enough tolerance for normal 70 ms browser movement samples.
    target_y = lane_y + (half_width * 0.5 if inside else half_width + 0.2)
    target_x = float(room["void"]["x1"]) - 0.35
    solver._move_to(page, {"x": target_x, "y": target_y})
    solver._turn_to(page, 0)
    before_x, before_y, _yaw = solver._camera(page)
    page.keyboard.down("w")
    page.wait_for_timeout(2_000 if inside else 750)
    page.keyboard.up("w")
    after_x, after_y, _yaw = solver._camera(page)
    void = room["void"]
    if inside:
        if after_x <= float(void["x2"]) + 0.12:
            raise AssertionError(f"valid bridge edge did not cross the void: {before_x} -> {after_x}")
    elif after_x > float(void["x1"]):
        raise AssertionError(f"outside bridge edge crossed the void: {before_x} -> {after_x}")
    suffix = "inside-edge-crossed" if inside else "outside-edge-blocked"
    page.screenshot(path=str(out_dir / f"l{label}-{suffix}.png"), full_page=True)
    return {
        "inside": inside,
        "bridge_half_width": half_width,
        "target_y": target_y,
        "before_x": before_x,
        "before_y": before_y,
        "after_x": after_x,
        "after_y": after_y,
        "crossed_void": after_x > float(void["x2"]) + 0.12,
    }


def replay_boundary(grader: Any, truth: dict[str, Any]) -> dict[str, Any]:
    """Exercise the server's replay collision primitive at both width edges."""
    room = truth["room"]
    socket = truth["sockets"][0]
    source = next(item for item in truth["sources"] if item["kind"] == socket["source_kind"])
    placement = truth["solution"]["placements"][0]
    operation = {
        "operation": socket["operation"],
        "center": socket["center"],
        "angle_deg": socket["angle_deg"],
        "length": float(source["length"]) * float(placement["scale"]),
    }
    qualification = truth["qualification"]
    half_width = float(qualification["bridge_half_width"])
    void = room["void"]
    lane_y = float(room["lane_y"])
    before_x = float(void["x1"]) - 0.15
    results: dict[str, Any] = {}
    for name, y, crosses in (
        ("inside", lane_y + half_width - 0.01, True),
        ("outside", lane_y + half_width + 0.01, False),
    ):
        before = {"x": before_x, "y": y, "yaw_deg": 0.0}
        after = grader._collision_move(before, 0.4, 0.0, room, [operation], qualification)
        crossed = float(after["x"]) > before_x
        if crossed != crosses:
            raise AssertionError(
                f"authoritative replay {name} boundary disagreed at L{truth['control_condition']['difficulty']}: {before} -> {after}"
            )
        results[name] = {"before": before, "after": after, "crossed": crossed}
    return {
        "bridge_half_width": half_width,
        "operation": operation,
        "edges": results,
    }


def run_case(
    browser: Any,
    *,
    task_json: Path,
    solver: Any,
    verifier_helpers: Any,
    grader: Any,
    level: int,
    inside: bool,
    temp_root: Path,
    out_dir: Path,
) -> dict[str, Any]:
    label = str(level)
    state_dir = temp_root / f"l{level}-{'inside' if inside else 'outside'}"
    state_dir.mkdir(parents=True, exist_ok=True)
    process, port = browser_smoke.start_server(task_json, MECHANIC, "simplified", state_dir)
    page = browser.new_page(viewport=VIEWPORT, device_scale_factor=1)
    try:
        current_task_path = state_dir / "current_task.json"
        current_task_text = current_task_path.read_text(encoding="utf-8")
        current_task_path.unlink()
        try:
            page.goto(f"http://127.0.0.1:{port}/?time_mode=live", wait_until="networkidle")
        finally:
            current_task_path.write_text(current_task_text, encoding="utf-8")
        expect(page.locator(".photo-room[data-interaction='simplified']")).to_be_visible()
        truth = develop_bridge(page, state_dir, solver, out_dir=out_dir, label=label)
        boundary = move_near_edge(page, truth, solver, inside=inside, out_dir=out_dir, label=label)
        result: dict[str, Any] = {
            "boundary": boundary,
            "authoritative_replay_boundary": replay_boundary(grader, truth),
        }
        if inside and level == 1:
            solver._move_to(page, truth["solution"]["terminal"])
            solver._turn_to(page, 0)
            page.locator("#photo-submit").click()
            expect(page.locator(".photo-foot .readout")).to_have_text("PASS", timeout=10_000)
            exported = {
                "result": browser_smoke.read_json(state_dir / "result.json"),
                "ground_truth": browser_smoke.read_json(state_dir / "ground_truth.json"),
                "public_state": browser_smoke.read_json(state_dir / "public_state.json"),
            }
            server_grade = exported["result"].get("server_grade") or {}
            verifier = verifier_helpers.verify_external_mechanic(exported, MECHANIC)
            if server_grade.get("passed") is not True or verifier.get("passed") is not True:
                raise AssertionError(f"near-edge L1 crossing did not grade: {server_grade} / {verifier}")
            write_json(out_dir / "l1-inside-edge-server-grade.json", server_grade)
            write_json(out_dir / "l1-inside-edge-verifier.json", verifier)
            write_json(out_dir / "l1-inside-edge-exported-result.json", exported)
            page.screenshot(path=str(out_dir / "l1-inside-edge-pass.png"), full_page=True)
            result["server_grade"] = server_grade
            result["verifier"] = verifier
        return result
    finally:
        page.close()
        process.terminate()
        try:
            process.wait(timeout=3)
        except Exception:  # pragma: no cover - cleanup fallback.
            process.kill()


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    materializer = browser_smoke.load_module("photo_bridge_materializer", browser_smoke.MATERIALIZER)
    solver = browser_smoke.load_module(
        "photo_bridge_solver",
        browser_smoke.BENCH_ROOT / "tools" / "incubator_solvers" / f"{MECHANIC}.py",
    )
    verifier_helpers = browser_smoke.load_module("photo_bridge_verifier_helpers", browser_smoke.HELPERS)
    grader = browser_smoke.load_module(
        "photo_bridge_authoritative_grader",
        browser_smoke.BENCH_ROOT / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py",
    )
    with tempfile.TemporaryDirectory(prefix="photo-bridge-width-evidence-") as temporary:
        temp_root = Path(temporary)
        materialized_root = temp_root / "materialized"
        materializer.materialize_environment(ENV_ROOT, materialized_root)
        tasks_root = materialized_root / ENVIRONMENT / "tasks"
        tasks = {
            level: browser_smoke.controlled_task(tasks_root, level, "simplified")
            for level in range(1, 6)
        }
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            cases: dict[str, Any] = {}
            for level in range(1, 6):
                cases[f"l{level}_inside"] = run_case(
                    browser,
                    task_json=tasks[level],
                    solver=solver,
                    verifier_helpers=verifier_helpers,
                    grader=grader,
                    level=level,
                    inside=True,
                    temp_root=temp_root,
                    out_dir=out_dir,
                )
            for level in (1, 5):
                cases[f"l{level}_outside"] = run_case(
                    browser,
                    task_json=tasks[level],
                    solver=solver,
                    verifier_helpers=verifier_helpers,
                    grader=grader,
                    level=level,
                    inside=False,
                    temp_root=temp_root,
                    out_dir=out_dir,
                )
            browser.close()
    write_json(out_dir / "summary.json", {"environment": ENVIRONMENT, "interaction": "simplified", "cases": cases})
    print(json.dumps({"environment": ENVIRONMENT, "cases": cases}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
