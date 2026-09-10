from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "ribbon_consensus"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, label: str, *, full_page: bool = True) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=full_page)


def _wait_for_new_challenge(state_dir: Path, previous: str) -> str:
    deadline = time.time() + 8
    while time.time() < deadline:
        current = str(_read_json(state_dir / "ground_truth.json").get("challenge_id") or "")
        if current and current != previous:
            return current
        time.sleep(0.05)
    raise AssertionError("ribbon consensus did not issue a fresh challenge after failed certification")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = str(_read_json(state_dir / "ground_truth.json")["challenge_id"])
    page.locator(".ribbon-submit").click()
    _wait_for_new_challenge(state_dir, before)
    expect(page.locator(".ribbon-verdict-fail")).to_be_visible(timeout=8_000)
    expect(page.locator(".readout")).to_contain_text("FAIL")
    _screenshot(page, out_dir, "fail-refresh")


def _simplified_shift(page, action: dict[str, object]) -> None:
    page.locator("#ribbon-row-select").select_option(str(action["row_id"]))
    page.locator("#ribbon-break-select").select_option(str(action["break_index"]))
    page.locator(f".ribbon-shift-buttons button[data-shift='{int(action['delta'])}']").click()


def _full_shift(page, action: dict[str, object], cell_width: int) -> None:
    tile = page.locator(
        f".loom-tile[data-row-id='{action['row_id']}'][data-index='{int(action['break_index'])}']"
    )
    tile.scroll_into_view_if_needed()
    box = tile.bounding_box()
    if not box:
        raise AssertionError(f"tile for action {action} is not visible")
    x = box["x"] + box["width"] / 2
    y = box["y"] + box["height"] / 2
    direction = 1 if int(action["delta"]) > 0 else -1
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + direction * cell_width * 0.9, y + 1, steps=6)
    page.mouse.up()


def solve(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read_json(state_dir / "ground_truth.json")
    condition = truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "simplified")
    actions = list(truth.get("repair_actions") or [])
    if not actions:
        raise AssertionError("the generated ribbon has no repair witness")
    expect(page.locator(".ribbon-consensus")).to_be_visible(timeout=8_000)
    _screenshot(page, out_dir, "initial-loom")
    cell_width = int((truth.get("stage") or {}).get("cell_width") or 40)
    for index, action in enumerate(actions):
        if interaction == "full":
            _full_shift(page, action, cell_width)
        else:
            _simplified_shift(page, action)
        if index == max(0, len(actions) // 2 - 1):
            _screenshot(page, out_dir, "active-feedback")
    expect(page.locator(".ribbon-cert-badge[data-ready='true']")).to_be_visible(timeout=4_000)
    _screenshot(page, out_dir, "solved-threshold")
    page.locator(".ribbon-submit").click()
    expect(page.locator(".readout")).to_have_text("PASS · RIBBON CONSENSUS CERTIFIED", timeout=8_000)
    _screenshot(page, out_dir, "pass")
