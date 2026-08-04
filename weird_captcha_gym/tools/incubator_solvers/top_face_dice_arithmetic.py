from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "top_face_dice_arithmetic"
OPPOSITE = {"N": "S", "E": "W", "S": "N", "W": "E"}
KEYS = {"N": "ArrowUp", "E": "ArrowRight", "S": "ArrowDown", "W": "ArrowLeft"}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, mechanic: str, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{label}.png"), full_page=True)


def _wait_fresh(state_dir: Path, previous: str) -> str:
    deadline = time.time() + 8
    while time.time() < deadline:
        current = str(_read(state_dir / "ground_truth.json").get("challenge_id") or "")
        if current and current != previous:
            return current
        time.sleep(0.05)
    raise AssertionError("foundry failure did not issue a fresh challenge")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator("#foundry-weigh").click()
    _wait_fresh(state_dir, before)
    page.wait_for_selector('.foundry-scale[data-fresh-failure="true"]', timeout=7_000)
    page.wait_for_function("() => document.querySelector('.foundry-foot .readout')?.textContent.includes('FAIL')")
    _shot(page, out_dir, mechanic, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    page.wait_for_function("() => !document.querySelector('.foundry-scale')?.classList.contains('is-failed')", timeout=4_000)
    truth = _read(state_dir / "ground_truth.json")
    public = _read(state_dir / "public_state.json")
    interaction = str((public.get("control_condition") or {}).get("interaction") or "simplified")
    captured_hidden = False
    captured_scanner = False
    move_index = 0
    for plan in truth["solution_plans"]:
        die_id = str(plan["die_id"])
        token = page.locator(f'[data-foundry-token="{die_id}"]')
        if interaction == "simplified":
            page.locator(f'[data-die-select="{die_id}"]').click()
        for command_index, world_direction in enumerate(plan["world_directions"]):
            screen_direction = str(world_direction)
            if interaction == "full":
                step = plan["trace"][command_index]
                destination = step["position"]
                target = page.locator(
                    f'[data-foundry-lane="{die_id}"] '
                    f'.foundry-cell[data-world-x="{destination["x"]}"][data-world-y="{destination["y"]}"]'
                )
                start_box = token.bounding_box()
                destination_box = target.bounding_box()
                if start_box is None or destination_box is None:
                    raise AssertionError("full foundry drag lost its visible rail target")
                page.mouse.move(start_box["x"] + start_box["width"] / 2, start_box["y"] + start_box["height"] / 2)
                page.mouse.down()
                page.mouse.move(
                    destination_box["x"] + destination_box["width"] / 2,
                    destination_box["y"] + destination_box["height"] / 2,
                    steps=8,
                )
                page.mouse.up()
            elif move_index % 2 == 0:
                page.keyboard.press(KEYS[screen_direction])
            else:
                page.locator(f'#foundry-roll-{screen_direction.lower()}').click()
            page.wait_for_timeout(320 if interaction == "full" else 45)
            move_index += 1
            if not captured_hidden and command_index >= 1 and token.get_attribute("data-visible") == "false":
                _shot(page, out_dir, mechanic, "active-occluding-housing")
                captured_hidden = True
            if not captured_scanner and command_index >= 2 and token.get_attribute("data-visible") == "true" and token.get_attribute("data-docked") == "false":
                _shot(page, out_dir, mechanic, "active-scanner-reveal")
                captured_scanner = True
        expect(token).to_have_attribute("data-docked", "true")

    if page.locator('.foundry-die-token[data-docked="true"]').count() != len(truth["solution_plans"]):
        raise AssertionError("not every foundry die reached its scale dock")
    clean = page.evaluate("() => ({events: window.topFaceDiceModel?.events || [], resets: window.topFaceDiceModel?.resetCount || 0})")
    if clean["resets"] != 0 or any(event.get("type") == "reset" or (event.get("type") == "roll" and not event.get("accepted")) for event in clean["events"]):
        raise AssertionError(f"foundry solution contains a contaminated action: {clean}")
    page.wait_for_timeout(340)
    _shot(page, out_dir, mechanic, "solved-docks")
    page.locator("#foundry-weigh").click()
    expect(page.locator(".foundry-scale")).to_have_attribute("data-settling", "true")
    page.wait_for_timeout(280)
    _shot(page, out_dir, mechanic, "active-balance-settle")
    expect(page.locator(".foundry-foot .readout")).to_have_text("PASS", timeout=10_000)
