from __future__ import annotations

import json
import math
from pathlib import Path


MECHANIC_ID = "little_planet_mason"
STEP_DEGREES = 15


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path | None, label: str) -> None:
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=True)


def _wait_events(page, expected: int) -> None:
    page.wait_for_function("expected => window.littlePlanetMasonModel?.events.length === expected", arg=expected, timeout=6_000)


def _turn_count(target: float) -> int:
    normalized = ((float(target) + math.pi) % (2 * math.pi)) - math.pi
    return int(round(normalized / (math.pi / 12)))


def _turn_count_for_surface(target: float, interaction: str) -> int:
    turns = _turn_count(target)
    if interaction == "full" and turns < 0:
        turns += 24
    return turns


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator("#planet-mason-certify").click()
    page.wait_for_function("() => document.querySelector('.readout')?.textContent.includes('NEW PLANET')", timeout=8_000)
    after = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    if before == after:
        raise AssertionError("Little Planet Mason did not regenerate after deliberate failure")
    _shot(page, out_dir, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path | None, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    blocks = {str(block["id"]): block for block in truth.get("blocks") or []}
    events = 0
    for index, block_id in enumerate(truth.get("solution_order") or [], start=1):
        block = blocks[str(block_id)]
        current_angle = 0
        if interaction == "simplified":
            page.locator(f'[data-block-id="{block_id}"]').click()
            events += 1
            _wait_events(page, events)
            turns = _turn_count_for_surface(float(block["target_angle"]), interaction)
            button = "#planet-mason-right" if turns >= 0 else "#planet-mason-left"
            for _ in range(abs(turns)):
                page.locator(button).click()
                events += 1
                _wait_events(page, events)
            page.locator(f'[data-socket-id="{block_id}"]').click()
            events += 1
            _wait_events(page, events)
        else:
            turns = _turn_count_for_surface(float(block["target_angle"]), interaction)
            locator = page.locator(f'[data-block-id="{block_id}"]')
            for _ in range(abs(turns)):
                locator.click(button="right")
                events += 1
                _wait_events(page, events)
                locator = page.locator(f'[data-block-id="{block_id}"]')
            svg = page.locator("#planet-mason-svg").bounding_box()
            if not svg:
                raise AssertionError("Little Planet Mason SVG has no layout box")
            start = locator.bounding_box()
            if not start:
                raise AssertionError(f"palette block {block_id} has no layout box")
            target = block["target"]
            end = (svg["x"] + float(target[0]) * svg["width"] / 900, svg["y"] + float(target[1]) * svg["height"] / 520)
            page.mouse.move(start["x"] + start["width"] / 2, start["y"] + start["height"] / 2)
            page.mouse.down()
            page.mouse.move(end[0], end[1], steps=5)
            page.mouse.up()
            events += 1
            _wait_events(page, events)
        if index == max(1, len(truth.get("solution_order") or []) // 2):
            _shot(page, out_dir, "active")
    page.wait_for_function("expected => Object.keys(window.littlePlanetMasonModel?.placed || {}).length === expected", arg=len(truth.get("solution_order") or []), timeout=8_000)
    _shot(page, out_dir, "solved")
    page.locator("#planet-mason-certify").click()
    page.wait_for_function("() => document.querySelector('.readout')?.textContent.includes('PASS')", timeout=8_000)
    _shot(page, out_dir, "pass")
