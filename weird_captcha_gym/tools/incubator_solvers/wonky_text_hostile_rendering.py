from __future__ import annotations

from pathlib import Path

from weird_captcha_gym.tools.incubator_solvers.reviewed_overhaul_common import (
    center, expect_fail_and_fresh, read_json, shot,
)

MECHANIC_ID = "wonky_text_hostile_rendering"


def _short_delta(target: float, initial: float) -> float:
    return (target - initial + 180) % 360 - 180


def _lock_all(page, press: dict) -> None:
    for plate in press["plates"]:
        page.locator(f'.plate-lock[data-plate-id="{plate["id"]}"]').click()


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    assert mechanic == MECHANIC_ID
    state = read_json(state_dir / "public_state.json")
    before = state["challenge_id"]
    _lock_all(page, state["press"])
    page.locator(".registration-press").click()
    expect_fail_and_fresh(page, state_dir, before)
    shot(page, out_dir, mechanic, "real-misaligned-press-rejection")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    assert mechanic == MECHANIC_ID
    state = read_json(state_dir / "public_state.json")
    press = state["press"]
    condition = state.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "full")
    parameters = condition.get("difficulty_parameters") or {}
    for plate in press["plates"]:
        degrees = _short_delta(float(plate["target"]), float(plate["initial"]))
        if interaction == "simplified":
            available = sorted({
                float(parameters.get("proxy_step_degrees") or 5),
                float(parameters.get("proxy_coarse_step_degrees") or 0),
            } - {0.0}, reverse=True)
            remaining = degrees
            while abs(remaining) > 0.001:
                step = next(value for value in available if value <= abs(remaining) + 0.001)
                signed = step if remaining > 0 else -step
                page.locator(f'.plate-step[data-plate-id="{plate["id"]}"][data-delta="{signed:g}"]').click()
                remaining -= signed
        else:
            remaining = degrees / float(press["degrees_per_pixel"])
            while abs(remaining) > 0.001:
                movement = max(-100.0, min(100.0, remaining))
                start = center(page.locator(f'.registration-wheel[data-plate-id="{plate["id"]}"]'))
                page.mouse.move(*start); page.mouse.down()
                # Every gesture uses one move event, including displacements
                # far beyond the old 28-pixel per-event clipping threshold.
                page.mouse.move(start[0] + movement, start[1]); page.mouse.up()
                remaining -= movement
        page.locator(f'.plate-lock[data-plate-id="{plate["id"]}"]').click()
    shot(page, out_dir, mechanic, "registered-three-plate-image")
    page.locator(".registration-press").click()
