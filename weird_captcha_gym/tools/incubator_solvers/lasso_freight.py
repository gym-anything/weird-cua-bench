#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "lasso_freight"
KEYS = {"N": "ArrowUp", "E": "ArrowRight", "S": "ArrowDown", "W": "ArrowLeft", "LASSO": "Space", "RESET": "r"}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=True)


def _issue(page, interaction: str, command: str) -> None:
    if interaction == "full":
        page.keyboard.press(KEYS[command])
    else:
        page.locator(f'[data-command="{command}"]').click()


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = _read_json(state_dir / "ground_truth.json")["challenge_id"]
    page.locator("#lasso-certify").click()
    # Paused observation freezes the page's timers and animation frames. A
    # host-side locator assertion observes the DOM without depending on task
    # time progressing.
    expect(page.locator(".readout")).to_contain_text("FAIL", timeout=10000)
    after = _read_json(state_dir / "ground_truth.json")["challenge_id"]
    if before == after:
        raise AssertionError("premature yard certification did not issue a fresh challenge")
    _screenshot(page, out_dir, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read_json(state_dir / "ground_truth.json")
    route = [str(command) for command in truth.get("solution") or []]
    condition = truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "full")
    if not route or "LASSO" not in route:
        raise AssertionError("generated lasso route is empty or has no snag")
    _screenshot(page, out_dir, "initial")
    for index, command in enumerate(route):
        _issue(page, interaction, command)
        page.wait_for_timeout(35)
        if index in {min(4, len(route) - 1), len(route) // 2}:
            _screenshot(page, out_dir, f"active-{index + 1:03d}")
    state = page.evaluate("""() => ({
        solved: window.lassoFreightModel?.cargo.every((item) => item.position[0] === item.pad[0] && item.position[1] === item.pad[1]),
        snags: window.lassoFreightModel?.events.filter((event) => event.issued === 'LASSO' && event.outcome.startsWith('snag:')).length,
        rope: window.lassoFreightModel?.rope.length,
    })""")
    if not state["solved"] or not state["snags"]:
        raise AssertionError(f"oracle route did not complete the visible yard: {state}")
    _screenshot(page, out_dir, "solved")
    page.locator("#lasso-certify").click()
    expect(page.locator(".readout")).to_contain_text("PASS", timeout=10000)
