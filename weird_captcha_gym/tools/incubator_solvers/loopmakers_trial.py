from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "loopmakers_trial"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=True)


def _wait_for_challenge_change(state_dir: Path, before: str) -> str:
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        current = str(_read_json(state_dir / "ground_truth.json").get("challenge_id") or "")
        if current and current != before:
            return current
        time.sleep(0.05)
    raise AssertionError("Loopmaker's Trial did not issue a fresh challenge after rejection")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = str(_read_json(state_dir / "ground_truth.json")["challenge_id"])
    page.locator("#lm-run").click()
    expect(page.locator("#lm-run-status")).to_contain_text("RUN COMPLETE", timeout=15_000)
    page.locator("#lm-submit").click()
    _wait_for_challenge_change(state_dir, before)
    expect(page.locator(".readout")).to_contain_text("FAIL", timeout=8_000)
    _shot(page, out_dir, "fail-refresh")


def fail_after_edit(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    """Submit a visibly edited route whose independent replay still fails."""
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = str(_read_json(state_dir / "ground_truth.json")["challenge_id"])
    public = _read_json(state_dir / "public_state.json")
    points = {str(point["id"]): dict(point) for point in (public.get("points") or [])}
    current = points.get("p02")
    if current is None:
        raise AssertionError("expected an editable p02 control point")
    target = {"id": current["id"], "x": min(860.0, float(current["x"]) + 48.0), "y": min(420.0, float(current["y"]) + 18.0)}
    _move_full(page, current, target)
    _shot(page, out_dir, "edited-failure-geometry")
    page.locator("#lm-run").click()
    expect(page.locator("#lm-run-status")).to_contain_text("RUN COMPLETE", timeout=15_000)
    expect(page.locator(".readout")).to_contain_text("TEST FAILED", timeout=8_000)
    _shot(page, out_dir, "edited-failure")
    page.locator("#lm-submit").click()
    _wait_for_challenge_change(state_dir, before)
    expect(page.locator(".readout")).to_contain_text("FAIL", timeout=8_000)
    _shot(page, out_dir, "fail-refresh")


def _svg_target(page, point: dict[str, object]) -> tuple[float, float]:
    return tuple(page.locator("#lm-route-svg").evaluate("(svg, point) => { const p = new DOMPoint(Number(point.x), Number(point.y)).matrixTransform(svg.getScreenCTM()); return [p.x, p.y]; }", point))


def _move_full(page, current: dict[str, object], target: dict[str, object]) -> None:
    point = page.locator(f".lm-point[data-point-id='{current['id']}'] circle").first
    box = point.bounding_box()
    if not box:
        raise AssertionError(f"point {current['id']} is not visible")
    start = (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    end = _svg_target(page, target)
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move(*end, steps=8)
    page.mouse.up()


def _move_simplified(page, current: dict[str, object], target: dict[str, object], params: dict[str, object]) -> None:
    page.locator(f".lm-point[data-point-id='{current['id']}'] circle").first.click()
    height_step = float(params["height_step"])
    radius_step = float(params["radius_step"])
    dx = round((float(target["x"]) - float(current["x"])) / radius_step)
    dy = round((float(target["y"]) - float(current["y"])) / height_step)
    button_for = ("#lm-widen" if dx > 0 else "#lm-tighten")
    for _ in range(abs(dx)):
        page.locator(button_for).click()
    button_for = ("#lm-lower" if dy > 0 else "#lm-raise")
    for _ in range(abs(dy)):
        page.locator(button_for).click()


def solve(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read_json(state_dir / "ground_truth.json")
    condition = truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "full")
    params = condition.get("difficulty_parameters") or {}
    targets = {str(point["id"]): point for point in (truth.get("solution_points") or [])}
    public = _read_json(state_dir / "public_state.json")
    current_points = {str(point["id"]): dict(point) for point in (public.get("points") or [])}
    expect(page.locator(".loopmakers-trial")).to_be_visible(timeout=8_000)
    _shot(page, out_dir, "initial-route")
    movable = list(current_points.values())[1:-1]
    midpoint = max(1, len(movable) // 2)
    for index, current in enumerate(movable):
        target = targets[current["id"]]
        if interaction == "simplified":
            _move_simplified(page, current, target, params)
        else:
            _move_full(page, current, target)
        if index == midpoint - 1:
            _shot(page, out_dir, "active-feedback")
    _shot(page, out_dir, "solved-geometry")
    page.locator("#lm-run").click()
    expect(page.locator("#lm-run-status")).to_contain_text("RUN COMPLETE", timeout=18_000)
    expect(page.locator(".readout")).to_contain_text("RUN PASSED", timeout=4_000)
    arrived = page.evaluate("Math.abs(loopmakersTrialModel.runDistance - loopmakersTrialModel.runDistances.at(-1)) < 0.001")
    if not arrived:
        raise AssertionError("successful rider animation stopped before the brake")
    _shot(page, out_dir, "pass-ready")
    page.locator("#lm-submit").click()
    expect(page.locator(".readout")).to_have_attribute("data-status", "passed", timeout=12_000)
    _shot(page, out_dir, "pass")
