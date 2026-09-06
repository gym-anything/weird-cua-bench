from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MECHANIC_ID = "after_hours_at_the_reliquary"


def _state(state_dir: Path) -> dict[str, Any]:
    return json.loads((state_dir / "public_state.json").read_text(encoding="utf-8"))


def _interaction(state: dict[str, Any]) -> str:
    return str((state.get("control_condition") or {}).get("interaction") or "full")


def _view_for(state: dict[str, Any], target_id: str) -> int:
    return int(next(item["view_id"] for item in state["targets"] if item["id"] == target_id))


def _turn_to(page, state: dict[str, Any], view_id: int) -> None:
    count = len(state["views"])
    while int(page.locator(".rel-scene").get_attribute("data-view-id")) != view_id:
        current = int(page.locator(".rel-scene").get_attribute("data-view-id"))
        right_steps = (view_id - current) % count
        left_steps = (current - view_id) % count
        direction = "right" if right_steps <= left_steps else "left"
        if _interaction(state) == "full":
            page.locator(f'.rel-turn.edge.{direction}').click()
        else:
            page.locator(f'.rel-turn-controls [data-direction="{direction}"]').click()


def _hotspot(page, state: dict[str, Any], target_id: str) -> None:
    _turn_to(page, state, _view_for(state, target_id))
    page.locator(f'[data-hotspot-id="{target_id}"]').click()


def _drag(page, source, destination) -> None:
    source_box = source.bounding_box()
    destination_box = destination.bounding_box()
    if source_box is None or destination_box is None:
        raise AssertionError("visible object or room destination is missing")
    start_x = source_box["x"] + source_box["width"] / 2
    start_y = source_box["y"] + source_box["height"] / 2
    end_x = destination_box["x"] + destination_box["width"] / 2
    end_y = destination_box["y"] + destination_box["height"] / 2
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(end_x, end_y, steps=10)
    page.mouse.up()


def _combine(page, state: dict[str, Any], first: str, second: str) -> None:
    first_card = page.locator(f'[data-item-id="{first}"]')
    second_card = page.locator(f'[data-item-id="{second}"]')
    if _interaction(state) == "full":
        _drag(page, first_card, second_card)
    else:
        first_card.click()
        page.locator(f'[data-item-id="{second}"]').click()


def _use(page, state: dict[str, Any], item_id: str, target_id: str) -> None:
    _turn_to(page, state, _view_for(state, target_id))
    card = page.locator(f'[data-item-id="{item_id}"]')
    destination = page.locator(f'[data-hotspot-id="{target_id}"]')
    if _interaction(state) == "full":
        _drag(page, card, destination)
    else:
        card.click()
        page.locator(f'[data-hotspot-id="{target_id}"]').click()


def _uncover_digit_clue(page, state: dict[str, Any]) -> None:
    _hotspot(page, state, "label_frame")
    _hotspot(page, state, "empty_frame")
    _hotspot(page, state, "lens_drawer")
    _hotspot(page, state, "lens")
    _combine(page, state, "empty_frame", "lens")
    _use(page, state, "loupe", "label_code")


def _submit_digit(page, answer: str) -> None:
    page.locator('[data-lock-panel="digit"]').click()
    for index, digit in enumerate(answer):
        for _ in range(int(digit)):
            page.locator(f'[data-digit-index="{index}"]').click()
    page.locator("#rel-submit-digit").click()


def _submit_color(page, answer: list[str]) -> None:
    page.locator('[data-lock-panel="color"]').click()
    for color in answer:
        page.locator(f'[data-color-key="{color}"]').click()
    page.locator("#rel-submit-color").click()


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    state = _state(state_dir)
    _uncover_digit_clue(page, state)
    if state["parameters"]["cross_view_order"]:
        _hotspot(page, state, "order_drawer")
    _turn_to(page, state, 0)
    page.screenshot(path=str(out_dir / "before-three-strike-failure.png"))
    page.locator('[data-lock-panel="digit"]').click()
    for _ in range(int(state["parameters"]["max_wrong_entries"])):
        page.locator("#rel-submit-digit").click()
    page.locator(".rel-fresh-failure").wait_for(state="visible")
    page.screenshot(path=str(out_dir / "fresh-failure.png"))


def solve(page, state_dir: Path, out_dir: Path, mechanic: str, *, certify: bool = True) -> None:
    del certify
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    state = _state(state_dir)
    page.screenshot(path=str(out_dir / "initial-door.png"))

    _uncover_digit_clue(page, state)
    page.screenshot(path=str(out_dir / "digit-clue-and-loupe.png"))

    if "color" in state["active_locks"]:
        _hotspot(page, state, "dust_sheet")
        page.screenshot(path=str(out_dir / "color-clue.png"))

    if "key" in state["active_locks"]:
        if state["parameters"]["hook_mode"] == "ready":
            _hotspot(page, state, "ready_hook")
        else:
            _hotspot(page, state, "floor_tile")
            _hotspot(page, state, "handle")
            _hotspot(page, state, "radiator_wire")
            _combine(page, state, "handle", "wire")
        if state["parameters"]["cross_view_order"]:
            _hotspot(page, state, "order_drawer")
            page.screenshot(path=str(out_dir / "cross-view-order-card.png"))
        _use(page, state, "hook", "grate")
        page.screenshot(path=str(out_dir / "recovered-ward-key.png"))

    _turn_to(page, state, 0)
    if "digit" in state["active_locks"]:
        _submit_digit(page, str(state["runtime_lock_answers"]["digit"]))
    if "color" in state["active_locks"]:
        _submit_color(page, list(state["runtime_lock_answers"]["color"]))
    if "key" in state["active_locks"]:
        _use(page, state, "ward_key", "keyhole")

    page.screenshot(path=str(out_dir / "all-wards-released.png"))
    _hotspot(page, state, "door_handle")
    page.locator('.readout[data-status="passed"]').wait_for(state="visible")
    page.screenshot(path=str(out_dir / "passed.png"))
