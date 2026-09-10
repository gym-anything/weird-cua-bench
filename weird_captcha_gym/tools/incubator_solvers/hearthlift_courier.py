"""Ordinary-input construction witness for Hearthlift Courier."""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "hearthlift_courier"
KEYS = {"N": "w", "E": "d", "S": "s", "W": "a"}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{name}.png"), full_page=True)


def _action(page, action: dict, interaction: str) -> None:
    action_type = action["type"]
    if action_type == "camera":
        if interaction == "full":
            stage = page.locator(".hl-scene")
            box = stage.bounding_box()
            if not box:
                raise AssertionError("Hearthlift stage has no visible bounds")
            start_x = box["x"] + 220
            start_y = box["y"] + 220
            page.mouse.move(start_x, start_y)
            page.mouse.down()
            page.mouse.move(start_x + 44, start_y + 6, steps=8)
            page.mouse.up()
        else:
            page.locator('button[data-camera="0.34"]').click()
        return
    if action_type == "move":
        direction = str(action["direction"])
        if interaction == "full":
            page.keyboard.press(KEYS[direction])
        else:
            page.locator(f'button[data-direction="{direction}"]').click()
        return
    if action_type == "climb":
        if interaction == "full":
            page.keyboard.press("c")
        else:
            page.locator(".hl-climb").click()
        return
    if action_type in {"pickup", "drop"}:
        if interaction == "full":
            page.keyboard.press("e")
        else:
            page.locator("button.hl-cargo").click()
        return
    raise AssertionError(f"unknown Hearthlift oracle action {action_type}")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    previous = page.locator(".hl-shell").get_attribute("data-challenge-id")
    page.locator(".hl-abandon").click()
    page.wait_for_function(
        "previous => document.querySelector('.hl-shell')?.dataset.challengeId !== previous",
        arg=previous,
        timeout=15_000,
    )
    _shot(page, out_dir, "failure-recovery")
    current = _read(state_dir / "public_state.json").get("challenge_id")
    if current == previous:
        raise AssertionError("Hearthlift failure did not regenerate a challenge")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    condition = truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "full")
    _shot(page, out_dir, "initial")
    actions = truth.get("solution_actions") or []
    if not actions:
        raise AssertionError("Hearthlift generator did not provide a construction witness")
    for index, action in enumerate(actions, 1):
        _action(page, action, interaction)
        page.wait_for_timeout(18)
        if index in {1, len(actions) // 2, len(actions) - 1}:
            _shot(page, out_dir, f"active-{index:03d}")
    _shot(page, out_dir, "cargo-at-hearth")
    page.locator(".hl-submit").click()
    expect(page.locator(".hl-readout")).to_have_text("PASS", timeout=15_000)
    _shot(page, out_dir, "pass")


__all__ = ["solve", "fail_once"]
