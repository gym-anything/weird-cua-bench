from __future__ import annotations

import json
from pathlib import Path


MECHANIC_ID = "elemental_wayfarer"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path | None, label: str) -> None:
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=True)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator("#wayfarer-certify").click()
    page.wait_for_function("() => document.querySelector('.readout')?.textContent.includes('NEW CHAMBER')", timeout=8_000)
    after = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    if before == after:
        raise AssertionError("Elemental Wayfarer did not regenerate after deliberate failure")
    _shot(page, out_dir, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path | None, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    actions = [str(action) for action in truth.get("solution_actions") or []]
    for index, action in enumerate(actions, start=1):
        if interaction == "full":
            page.keyboard.press({"UP": "ArrowUp", "DOWN": "ArrowDown", "LEFT": "ArrowLeft", "RIGHT": "ArrowRight"}[action])
        else:
            page.locator(f'[data-action="{action}"]').click()
        page.wait_for_function("expected => window.elementalWayfarerModel?.actions.length === expected", arg=index, timeout=4_000)
        if index == max(1, len(actions) // 2):
            _shot(page, out_dir, "active")
    page.wait_for_function("() => window.elementalWayfarerModel?.ready === true", timeout=8_000)
    _shot(page, out_dir, "solved")
    page.locator("#wayfarer-certify").click()
    page.wait_for_function("() => document.querySelector('.readout')?.textContent.includes('PASS')", timeout=8_000)
    _shot(page, out_dir, "pass")
