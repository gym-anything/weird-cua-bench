from __future__ import annotations

import json
from pathlib import Path


MECHANIC_ID = "turtle_forger"


def _state(state_dir: Path) -> dict:
    return json.loads((state_dir / "public_state.json").read_text(encoding="utf-8"))


def _truth(state_dir: Path) -> dict:
    return json.loads((state_dir / "ground_truth.json").read_text(encoding="utf-8"))


def _drag_card(page, selector: str) -> None:
    source = page.locator(selector)
    target = page.locator("#tfg-tape-zone")
    source.scroll_into_view_if_needed()
    source_box = source.bounding_box()
    target_box = target.bounding_box()
    if source_box is None or target_box is None:
        raise AssertionError(f"card drag surface is not visible: {selector}")
    start_x = source_box["x"] + source_box["width"] / 2
    start_y = source_box["y"] + source_box["height"] / 2
    end_x = target_box["x"] + target_box["width"] / 2
    end_y = target_box["y"] + target_box["height"] / 2
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(end_x, end_y, steps=6)
    page.mouse.up()


def _append_visible_card(page, key: str, interaction: str) -> None:
    selector = f'.tfg-command[data-command-key="{key}"]'
    if interaction == "full":
        _drag_card(page, selector)
    else:
        page.locator(selector).click()


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    del out_dir
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = _state(state_dir)["challenge_id"]
    interaction = str((_state(state_dir).get("control_condition") or {}).get("interaction") or "full")
    first_key = str(_state(state_dir)["command_palette"][0]["key"])
    _append_visible_card(page, first_key, interaction)
    page.locator("#tfg-proof").click()
    page.locator("#tfg-certify").click()
    page.locator(".tfg-verdict.is-fail").wait_for(state="visible")
    page.wait_for_function(
        "([oldId]) => window.fetch('/health').then(() => true) && document.querySelector('.turtle-forger')",
        arg=[before],
    )
    after = _state(state_dir)["challenge_id"]
    if before == after:
        raise AssertionError("failed submission did not issue a fresh master")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str, *, certify: bool = True) -> None:
    del out_dir
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    state = _state(state_dir)
    truth = _truth(state_dir)
    interaction = str((state.get("control_condition") or {}).get("interaction") or "full")
    for index, key in enumerate(truth["canonical_program"]):
        before = page.locator(".tfg-program-card").count()
        _append_visible_card(page, str(key), interaction)
        after = page.locator(".tfg-program-card").count()
        if after != before + 1:
            raise AssertionError(
                f"visible {interaction} card {index + 1} ({key}) did not append: {before} -> {after}"
            )
    expected_cards = len(truth["canonical_program"])
    actual_cards = page.locator(".tfg-program-card").count()
    if actual_cards != expected_cards:
        raise AssertionError(
            f"visible {interaction} program tape contains {actual_cards} cards; expected {expected_cards}"
        )
    page.locator("#tfg-proof").click()
    page.locator("#tfg-score").wait_for(state="visible")
    page.wait_for_timeout(300)
    score = page.locator("#tfg-score").inner_text().strip()
    if score != "100.00%":
        raise AssertionError(f"canonical proof rendered at {score}")
    if certify:
        page.locator("#tfg-certify").click()
        page.locator(".tfg-verdict.is-pass").wait_for(state="visible")
