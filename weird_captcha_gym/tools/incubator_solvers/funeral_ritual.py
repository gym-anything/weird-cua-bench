from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "funeral_ritual"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _required(state: dict) -> set[str]:
    parameters = (state.get("control_condition") or {}).get("difficulty_parameters") or {}
    return {str(value) for value in parameters.get("required_events") or []}


def _flower_ids(state: dict) -> list[str]:
    by_kind = {str(flower["kind"]): str(flower["id"]) for flower in state.get("flowers") or []}
    order = [str(kind) for kind in state.get("tribute_order") or []]
    return [by_kind[kind] for kind in order] if order else [str(flower["id"]) for flower in state.get("flowers") or []]


def _prepare(page, state: dict, interaction: str) -> None:
    required = _required(state)
    if interaction == "simplified":
        page.locator('[data-proxy-action="inspect"]').click()
        if "brush" in required:
            page.locator('[data-proxy-action="brush"]').click()
        page.locator('[data-proxy-action="light"]').click()
    else:
        page.locator(".tombstone").click(position={"x": 110, "y": 60})
        if "brush" in required:
            for index in range(int(state.get("brush_threshold") or 0)):
                page.locator(f'.moss-cell[data-moss-index="{index}"]').click(force=True)
        page.locator(".grave-candle").click()


def _gather(page, flower_id: str, interaction: str) -> None:
    selector = (
        f'[data-proxy-flower-id="{flower_id}"]'
        if interaction == "simplified"
        else f'.ritual-flower[data-flower-id="{flower_id}"]'
    )
    page.locator(selector).click()


def _offer(page, interaction: str) -> None:
    if interaction == "simplified":
        page.locator('[data-proxy-action="offer"]').click()
        return
    bouquet = page.locator(".ritual-bouquet")
    grave = page.locator(".grave-bed")
    source = bouquet.bounding_box()
    target = grave.bounding_box()
    if source is None or target is None:
        raise AssertionError("funeral bouquet transfer endpoints have no visible bounds")
    page.mouse.move(source["x"] + source["width"] / 2, source["y"] + source["height"] / 2)
    page.mouse.down()
    page.mouse.move(target["x"] + target["width"] / 2, target["y"] + target["height"] / 2)
    page.mouse.up()


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    state = _read(state_dir / "public_state.json")
    interaction = str((state.get("control_condition") or {}).get("interaction") or "full")
    ordered = _flower_ids(state)
    if len(ordered) < 2 or not state.get("tribute_order"):
        raise AssertionError("funeral failure smoke requires an ordered tribute profile")
    before = str(state["challenge_id"])
    _prepare(page, state, interaction)
    _gather(page, ordered[1], interaction)
    expect(page.locator(".readout")).to_have_text("FAIL", timeout=5_000)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if str(_read(state_dir / "public_state.json").get("challenge_id") or "") != before:
            page.screenshot(path=str(out_dir / f"{mechanic}-fail-refresh.png"), full_page=True)
            return
        time.sleep(.05)
    raise AssertionError("wrong funeral tribute did not issue a fresh challenge")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    state = _read(state_dir / "public_state.json")
    interaction = str((state.get("control_condition") or {}).get("interaction") or "full")
    required = _required(state)
    _prepare(page, state, interaction)
    if "gather" in required:
        for flower_id in _flower_ids(state):
            _gather(page, flower_id, interaction)
    page.screenshot(path=str(out_dir / f"{mechanic}-bouquet-ready.png"), full_page=True)
    _offer(page, interaction)
    expect(page.locator(".readout")).to_have_text("PASS", timeout=5_000)
