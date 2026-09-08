"""Privileged construction solver; browser execution stays ordinary input only."""
from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "twin_groove_seal"
ARROWS = {
    "radial_in": "ArrowDown",
    "radial_out": "ArrowUp",
    "angular_cw": "ArrowRight",
    "angular_ccw": "ArrowLeft",
    "rotate_cw": "ArrowRight",
    "rotate_ccw": "ArrowLeft",
}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=True)


def _wait_action(page, expected: int) -> None:
    page.wait_for_function(
        "expected => window.twinGrooveSealModel?.actions?.length === expected",
        arg=expected,
        timeout=8000,
    )


def _set_full_mode(page, origin: str, mode: str) -> None:
    current = page.evaluate(
        "() => ({origin: window.twinGrooveSealModel.origin, mode: window.twinGrooveSealModel.mode})"
    )
    if current["origin"] != origin:
        page.keyboard.press("Tab")
        current = page.evaluate("() => ({origin: window.twinGrooveSealModel.origin, mode: window.twinGrooveSealModel.mode})")
        if current["origin"] != origin:
            page.keyboard.press("Tab")
    if current["mode"] != mode:
        page.keyboard.press("Backquote")


def _make_move(page, item: dict, interaction: str, sequence: int) -> None:
    origin = str(item["origin"])
    action = str(item["action"])
    mode = "rotate" if action.startswith("rotate_") else "translate"
    if interaction == "full":
        _set_full_mode(page, origin, mode)
        page.keyboard.press(ARROWS[action])
    else:
        page.locator(f'[data-seal-origin="{origin}"]').click()
        page.locator(f'[data-seal-mode="{mode}"]').click()
        page.locator(f'[data-seal-action="{action}"]').click()
    _wait_action(page, sequence)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = _read_json(state_dir / "ground_truth.json")["challenge_id"]
    page.locator("#seal-release").click()
    page.wait_for_function("() => document.querySelector('.readout')?.textContent.includes('FAIL')", timeout=8000)
    after = _read_json(state_dir / "ground_truth.json")["challenge_id"]
    if before == after:
        raise AssertionError("early release did not generate a fresh challenge")
    _screenshot(page, out_dir, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read_json(state_dir / "ground_truth.json")
    condition = truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "full")
    route = truth.get("solution_actions") or []
    for sequence, item in enumerate(route, start=1):
        _make_move(page, item, interaction, sequence)
        if sequence in {max(1, len(route) // 3), max(1, (2 * len(route)) // 3)}:
            _screenshot(page, out_dir, f"active-{sequence:02d}")
    contract = page.evaluate(
        """() => ({
          ready: window.twinGrooveSealModel.ready,
          actions: window.twinGrooveSealModel.actions.length,
          rearExit: window.twinGrooveSealModel.exitState.rear,
          tipExit: window.twinGrooveSealModel.exitState.tip,
        })"""
    )
    if not contract["ready"] or contract["actions"] != len(route) or not contract["rearExit"] or not contract["tipExit"]:
        raise AssertionError(f"twin-groove route did not reach both exits: {contract}")
    expect(page.locator("#seal-rear-exit")).to_have_text("CLEAR")
    expect(page.locator("#seal-tip-exit")).to_have_text("CLEAR")
    _screenshot(page, out_dir, "solved-before-release")
    page.locator("#seal-release").click()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=8000)
    expect(page.locator("#seal-rear-exit")).to_have_text("CLEAR")
    expect(page.locator("#seal-tip-exit")).to_have_text("CLEAR")
    _screenshot(page, out_dir, "pass")
