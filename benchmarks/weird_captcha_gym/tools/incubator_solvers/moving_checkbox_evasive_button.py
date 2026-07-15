from __future__ import annotations

import json
import math
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "moving_checkbox_evasive_button"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, mechanic: str, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{label}.png"), full_page=True)


def _body(page) -> dict:
    return page.evaluate(
        """() => {
            const model = window.scrollCageModel;
            return model ? {...model.body, tick: model.tick} : null;
        }"""
    )


def _cursor_screen(page, x: float, y: float) -> tuple[float, float]:
    arena = page.locator("#scroll-cage-arena").bounding_box()
    if not arena:
        raise AssertionError("scroll cage arena has no bounds")
    return (
        arena["x"] + max(0.0, min(1000.0, x)) / 1000.0 * arena["width"],
        arena["y"] + max(0.0, min(520.0, y)) / 520.0 * arena["height"],
    )


def _drive(page, goal_x: float, goal_y: float, *, tolerance: float = 8.0, timeout_ticks: int = 650) -> None:
    """Closed-loop motor control using only visible pointer-field actions.

    The state read is telemetry exposed by the UI; every state change still comes
    from real pointer motion and is independently replayed by the grader.
    """
    for _ in range(timeout_ticks):
        body = _body(page)
        if body["captured"]:
            return
        ex = goal_x - float(body["x"])
        ey = goal_y - float(body["y"])
        if math.hypot(ex, ey) <= tolerance and abs(body["vx"]) <= 2 and abs(body["vy"]) <= 2:
            return

        # Ask for a slow, damped approach. A cursor behind the requested
        # acceleration is the only actuator the challenge provides.
        desired_vx = max(-5.0, min(5.0, ex * 0.12))
        desired_vy = max(-5.0, min(5.0, ey * 0.12))
        ax = desired_vx - float(body["vx"]) * 0.92
        ay = desired_vy - float(body["vy"]) * 0.92
        if abs(ax) < 0.45 and abs(ay) < 0.45:
            # Keep the pointer field visible but outside force range.
            cursor_x = 1000.0 if body["x"] < 500 else 0.0
            cursor_y = 520.0 if body["y"] < 260 else 0.0
        else:
            sx = 0 if abs(ax) < 0.45 else (1 if ax > 0 else -1)
            sy = 0 if abs(ay) < 0.45 else (1 if ay > 0 else -1)
            distance = 58.0 if sx and sy else 70.0
            cursor_x = float(body["x"]) - sx * distance
            cursor_y = float(body["y"]) - sy * distance
        page.mouse.move(*_cursor_screen(page, cursor_x, cursor_y), steps=2)
        page.wait_for_timeout(55)
    body = _body(page)
    raise AssertionError(f"pointer controller did not reach ({goal_x}, {goal_y}); body={body}")


def _set_offsets(page, truth: dict) -> None:
    initial = list(truth["scene"]["initial_offsets"])
    target = list(truth["solution_offsets"])
    step = int(truth["scene"]["offset_step"])
    for shaft, (before, after) in enumerate(zip(initial, target)):
        selector = f'[data-shaft-down="{shaft}"]' if after > before else f'[data-shaft-up="{shaft}"]'
        for _ in range(abs(after - before) // step):
            page.locator(selector).click()
    observed = page.evaluate("() => [...window.scrollCageModel.offsets]")
    if observed != target:
        raise AssertionError(f"scroll offsets did not reach physical alignment: {observed} != {target}")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator("#scroll-cage-submit").click()
    expect(page.locator(".scroll-cage[data-fresh-failure='true']")).to_be_visible(timeout=7_000)
    expect(page.locator(".scroll-cage-foot .readout")).to_contain_text("FAIL", timeout=7_000)
    after = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    if before == after:
        raise AssertionError("failed scroll-cage transcript did not issue a fresh challenge")
    _screenshot(page, out_dir, mechanic, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    scene = truth["scene"]
    route = list(truth["route_screen_y"])
    _set_offsets(page, truth)
    _screenshot(page, out_dir, mechanic, "portals-aligned")

    # Settle vertically before each narrow opening, then push through it. The
    # intermediate waypoints are inside the real collision compartments.
    for index, boundary in enumerate(scene["boundaries"]):
        x = float(boundary["x"])
        _drive(page, x - 48, float(route[index]), tolerance=7)
        _drive(page, x + 49, float(route[index]), tolerance=8)
        if index == 0:
            _screenshot(page, out_dir, mechanic, "gate-one-crossed")

    clamp = scene["clamp"]
    _drive(page, float(clamp["x"]), float(clamp["y"]), tolerance=6, timeout_ticks=900)
    expect(page.locator("#scroll-cage-target")).to_have_attribute("data-captured", "true", timeout=5_000)
    _screenshot(page, out_dir, mechanic, "captured")
    page.locator("#scroll-cage-check").click()
    expect(page.locator("#scroll-cage-check")).to_have_attribute("data-checked", "true")
    page.locator("#scroll-cage-submit").click()
    expect(page.locator(".scroll-cage-foot .readout")).to_have_text("PASS", timeout=8_000)
    expect(page.locator(".scroll-cage-foot .readout")).to_have_attribute("data-status", "passed")
