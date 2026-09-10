"""Ordinary-input construction witness for Pearl Lattice.

The witness reads the generated oracle only to select its next visible target;
all state-changing operations use the same board-cycle and confirmation
controls exposed to a screenshot-only player.
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "pearl_lattice"
SIZE = 4


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=True)


def _legal_columns(initial_board: dict[str, int]) -> list[tuple[int, int]]:
    return [
        (x, z)
        for z in range(SIZE)
        for x in range(SIZE)
        if initial_board.get(f"{x},3,{z}", 0) == 0
    ]


def _preview(page) -> tuple[int, int]:
    root = page.locator(".pl-shell")
    return int(root.get_attribute("data-preview-x") or -1), int(root.get_attribute("data-preview-z") or -1)


def _cycle_to(page, target: tuple[int, int], interaction: str) -> None:
    first_cycle = True
    for _ in range(64):
        if _preview(page) == target:
            if not first_cycle:
                return
            # The independent grader requires the two-stage control to be
            # exercised even when the authored target is initially selected.
        first_cycle = False
        if interaction == "full":
            page.locator(".pl-board-surface").click(position={"x": 375, "y": 258})
        else:
            page.locator(".pl-next").click()
        page.wait_for_timeout(20)
        if _preview(page) == target:
            return
    raise AssertionError(f"{MECHANIC_ID} could not cycle to visible column {target}")


def _confirm(page, interaction: str) -> None:
    page.locator(".pl-confirm-zone" if interaction == "full" else ".pl-confirm").click()
    page.wait_for_timeout(80)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    board = truth["initial_board"]
    legal = _legal_columns(board)
    solution = tuple(truth["solution_moves"][0])
    wrong = next(column for column in legal if column != solution)
    old_challenge = truth["challenge_id"]
    _cycle_to(page, wrong, interaction)
    _confirm(page, interaction)
    expect(page.locator(".pl-shell")).to_have_attribute("data-status", "lost", timeout=5000)
    page.locator(".pl-abandon").click()
    expect(page.locator(".pl-readout")).to_contain_text("FRESH LATTICE", timeout=15000)
    _shot(page, out_dir, "failure-recovery")
    new_challenge = _read(state_dir / "public_state.json")["challenge_id"]
    if new_challenge == old_challenge:
        raise AssertionError("Pearl Lattice retry did not issue a fresh challenge")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID, advance=None) -> None:
    del advance
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    _shot(page, out_dir, "initial")
    for index, raw_column in enumerate(truth["solution_moves"], start=1):
        _cycle_to(page, tuple(raw_column), interaction)
        _confirm(page, interaction)
        _shot(page, out_dir, f"placement-{index:02d}")
    expect(page.locator(".pl-shell")).to_have_attribute("data-status", "won", timeout=5000)
    page.locator(".pl-submit").click()
    expect(page.locator(".pl-readout")).to_have_attribute("data-status", "passed", timeout=15000)
    _shot(page, out_dir, "pass")
