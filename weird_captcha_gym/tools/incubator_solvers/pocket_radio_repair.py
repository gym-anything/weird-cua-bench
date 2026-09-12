from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "pocket_radio_repair"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=True)


def _wait_result(state_dir: Path, passed: bool) -> dict:
    deadline = time.time() + 10
    while time.time() < deadline:
        path = state_dir / "result.json"
        if path.exists():
            result = _read(path)
            if bool((result.get("server_grade") or {}).get("passed")) is passed:
                return result
        time.sleep(.05)
    raise AssertionError("Pocket Radio Repair result was not written")


def _wait_failed_attempt(state_dir: Path) -> dict:
    deadline = time.time() + 10
    while time.time() < deadline:
        path = state_dir / "attempts.jsonl"
        if path.exists():
            lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            if lines:
                attempt = json.loads(lines[-1])
                if bool((attempt.get("server_grade") or {}).get("passed")) is False:
                    return attempt
        time.sleep(.05)
    raise AssertionError("Pocket Radio Repair failed attempt was not archived")


def _truth(state_dir: Path) -> dict:
    return _read(state_dir / "ground_truth.json")


def _public(page) -> dict:
    return page.evaluate("() => window.pocketRadioRepairModel?.radio || null")


def _canvas_point(page, x: float, y: float) -> tuple[float, float]:
    box = page.locator("#pr-canvas").bounding_box()
    if not box:
        raise AssertionError("Pocket Radio Repair canvas is not visible")
    return box["x"] + x / 900 * box["width"], box["y"] + y / 560 * box["height"]


def _drag(page, start: tuple[float, float], end: tuple[float, float], steps: int = 5) -> None:
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move(*end, steps=steps)
    page.mouse.up()
    page.wait_for_timeout(14)


def _direct_tool(page, tool: dict, target: tuple[float, float]) -> None:
    _drag(page, _canvas_point(page, float(tool["x"]) + 30, float(tool["y"]) + 20), _canvas_point(page, *target), steps=6)


def _direct_screw(page, target: tuple[float, float], loops: int = 3) -> None:
    box_point = _canvas_point(page, *target)
    page.mouse.move(*box_point)
    page.mouse.down()
    points = [(target[0] + 32, target[1]), (target[0] + 20, target[1] + 28), (target[0] - 12, target[1] + 30), (target[0] - 34, target[1] + 4), (target[0] - 18, target[1] - 26), (target[0] + 16, target[1] - 28), (target[0] + 34, target[1])]
    for _ in range(loops):
        for x, y in points:
            page.mouse.move(*_canvas_point(page, x, y), steps=2)
    page.mouse.up()
    page.wait_for_timeout(18)


def _direct_clean(page, part: dict, strokes: int) -> None:
    left = _canvas_point(page, float(part["x"]) + 10, float(part["y"]) + float(part["h"]) / 2)
    right = _canvas_point(page, float(part["x"]) + float(part["w"]) - 10, float(part["y"]) + float(part["h"]) / 2)
    page.mouse.move(*left)
    page.mouse.down()
    for index in range(max(1, strokes)):
        page.mouse.move(*(right if index % 2 == 0 else left), steps=8)
    page.mouse.up()
    page.wait_for_timeout(18)


def _solve_simplified(page, truth: dict, out_dir: Path) -> None:
    for cover in sorted(truth["covers"], key=lambda item: int(item["layer"])):
        for screw in (item for item in truth["screws"] if item["cover_id"] == cover["id"]):
            page.locator(f'[data-action="select-tool"][data-tool-id="{screw["tool_id"]}"]').click()
            page.locator(f'[data-action="loosen"][data-screw-id="{screw["id"]}"]').click()
        page.locator(f'[data-action="open"][data-cover-id="{cover["id"]}"]').click()
        for part in (item for item in truth["components"] if item["cover_id"] == cover["id"]):
            if part["condition"] == "dirty":
                page.locator(f'[data-action="clean"][data-component-id="{part["id"]}"]').click()
            elif part["condition"] == "missing":
                page.locator(f'[data-action="replace"][data-component-id="{part["id"]}"]').click()
        if cover["layer"] == 0:
            _shot(page, out_dir, "active-inner-radio")
    for cover in sorted(truth["covers"], key=lambda item: int(item["layer"]), reverse=True):
        page.locator(f'[data-action="install-cover"][data-cover-id="{cover["id"]}"]').click()
        for screw in (item for item in truth["screws"] if item["cover_id"] == cover["id"]):
            page.locator(f'[data-action="select-tool"][data-tool-id="{screw["tool_id"]}"]').click()
            page.locator(f'[data-action="install-screw"][data-screw-id="{screw["id"]}"]').click()


def _solve_full(page, truth: dict, out_dir: Path) -> None:
    for cover in sorted(truth["covers"], key=lambda item: int(item["layer"])):
        for screw in (item for item in truth["screws"] if item["cover_id"] == cover["id"]):
            public = _public(page)
            tool = next(item for item in public["tools"] if item["id"] == screw["tool_id"])
            _direct_tool(page, tool, (float(screw["x"]), float(screw["y"])))
            _direct_screw(page, (float(screw["x"]), float(screw["y"])), loops=4)
        start = _canvas_point(page, float(cover["x"]) + 110, float(cover["y"]) + 100)
        _drag(page, start, (start[0], start[1] - 65), steps=6)
        public = _public(page)
        for part in (item for item in public["components"] if item["cover_id"] == cover["id"]):
            if part["condition"] == "dirty" and not part["repaired"]:
                _direct_clean(page, part, int(truth.get("clean_strokes", 1)))
            elif part["condition"] == "missing" and not part["installed"]:
                _drag(page, _canvas_point(page, float(part["tray_x"]), float(part["tray_y"])), _canvas_point(page, float(part["x"]) + float(part["w"]) / 2, float(part["y"]) + float(part["h"]) / 2), steps=8)
        if cover["layer"] == 0:
            _shot(page, out_dir, "active-inner-radio")
    for cover in sorted(truth["covers"], key=lambda item: int(item["layer"]), reverse=True):
        start = _canvas_point(page, 160, 115 + int(cover["layer"]) * 55)
        end = _canvas_point(page, float(cover["x"]) + 110, float(cover["y"]) + 100)
        _drag(page, start, end, steps=7)
        for index, screw in enumerate(item for item in truth["screws"] if item["cover_id"] == cover["id"]):
            public = _public(page)
            tool = next(item for item in public["tools"] if item["id"] == screw["tool_id"])
            loose_y = 170 + truth["screws"].index(screw) * 30
            loose = _canvas_point(page, 770, loose_y)
            _direct_tool(page, tool, (770, loose_y))
            _drag(page, loose, _canvas_point(page, float(screw["x"]), float(screw["y"])), steps=6)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(mechanic)
    before = _truth(state_dir)["challenge_id"]
    page.locator("#pr-test").click()
    _wait_failed_attempt(state_dir)
    expect(page.locator(".readout")).to_contain_text("FAIL", timeout=8_000)
    _shot(page, out_dir, "fail-fresh-radio")
    page.wait_for_timeout(2350)
    after = _truth(state_dir)["challenge_id"]
    if before == after:
        raise AssertionError("failed Pocket Radio Repair submission did not regenerate")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(mechanic)
    truth = _truth(state_dir)
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    if interaction == "simplified":
        _solve_simplified(page, truth, out_dir)
    else:
        _solve_full(page, truth, out_dir)
    _shot(page, out_dir, "solved-before-test")
    page.locator("#pr-test").click()
    expect(page.locator(".readout")).to_contain_text("PASS", timeout=8_000)
    result = _wait_result(state_dir, True)
    if (result.get("server_grade") or {}).get("passed") is not True:
        raise AssertionError(result.get("server_grade"))
    _shot(page, out_dir, "pass")
