from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "borrowed_tiles"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=True)


def _drop(page, action: dict, interaction: str) -> None:
    tile = page.locator(f'.borrowed-tile[data-tile-id="{action["tile_id"]}"]')
    target = action["to"]
    if target["zone"] == "rack":
        drop = page.locator('[data-drop-zone="rack"]')
    elif target["zone"] == "table":
        drop = page.locator(f'.borrow-dropzone[data-drop-zone="table"][data-set-id="{target["set_id"]}"]')
    else:
        raise AssertionError(f"unsupported solution destination {target!r}")
    if interaction == "full":
        source_box, target_box = tile.bounding_box(), drop.bounding_box()
        if not source_box or not target_box:
            raise AssertionError("solution endpoints have no visible bounds")
        page.mouse.move(source_box["x"] + source_box["width"] / 2, source_box["y"] + source_box["height"] / 2)
        page.mouse.down()
        page.mouse.move(target_box["x"] + target_box["width"] / 2, target_box["y"] + target_box["height"] / 2, steps=8)
        page.mouse.up()
    else:
        tile.click()
        drop.click()


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    state = _read(state_dir / "public_state.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    before = str(truth["challenge_id"])
    # Committing the untouched deal is a visible, recoverable failure.
    page.locator("#borrow-commit").click()
    expect(page.locator(".borrow-footer .readout")).to_have_text("FAIL · FRESH DEAL", timeout=8_000)
    after = _read(state_dir / "ground_truth.json")
    if before == str(after["challenge_id"]):
        raise AssertionError("invalid table did not regenerate a fresh challenge")
    if str(after.get("challenge_id")) == str(state.get("challenge_id")):
        raise AssertionError("fresh challenge id did not change")
    _shot(page, out_dir, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    actions = truth.get("solution_actions") or []
    if not actions:
        raise AssertionError("borrowed tile challenge has no solution actions")
    _shot(page, out_dir, "initial")
    for index, action in enumerate(actions, start=1):
        _drop(page, action, interaction)
        expect(page.locator("#borrow-move-count")).to_have_text(f"{index:02d}")
        if index == max(1, len(actions) // 2):
            _shot(page, out_dir, "active-reassembly")
    _shot(page, out_dir, "solved-precommit")
    page.locator("#borrow-commit").click()
    expect(page.locator(".borrow-footer .readout")).to_have_text("PASS", timeout=8_000)
    _shot(page, out_dir, "pass")
