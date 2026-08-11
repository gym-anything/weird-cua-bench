from __future__ import annotations

import json
from pathlib import Path


MECHANIC_ID = "motion_only_ghost_jigsaw"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, mechanic: str, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{label}.png"), full_page=True)


def _pointer_drag(page, source, target) -> None:
    source_box = source.bounding_box()
    target_box = target.bounding_box()
    if not source_box or not target_box:
        raise AssertionError("ghost drag endpoints are not visible")
    page.mouse.move(source_box["x"] + source_box["width"] / 2, source_box["y"] + source_box["height"] / 2)
    page.mouse.down()
    page.mouse.move(target_box["x"] + target_box["width"] / 2, target_box["y"] + target_box["height"] / 2, steps=1)
    page.mouse.up()


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = _read(state_dir / "ground_truth.json")["challenge_id"]
    page.locator("#submit-ghost").click()
    page.wait_for_function("() => document.querySelector('.readout')?.textContent === 'FAIL'", timeout=5_000)
    after = _read(state_dir / "ground_truth.json")["challenge_id"]
    if before == after:
        raise AssertionError("ghost-jigsaw failure did not issue a fresh challenge")
    _shot(page, out_dir, mechanic, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    expected = truth["expected_positions"]
    for index, (piece_id, slot_index) in enumerate(expected.items()):
        piece = page.locator(f'.ghost-piece[data-piece-id="{piece_id}"]')
        slot = page.locator(f'.ghost-slot[data-slot-index="{slot_index}"]')
        if interaction == "full":
            _pointer_drag(page, piece, slot)
        else:
            piece.click()
            slot.click()
        if index == 3:
            _shot(page, out_dir, mechanic, "active")
    if page.locator(".ghost-slot .ghost-piece").count() != len(expected):
        raise AssertionError("ghost jigsaw did not place every piece")
    page.locator("#submit-ghost").click()
    page.wait_for_function("() => document.querySelector('.readout')?.textContent === 'PASS'", timeout=5_000)
