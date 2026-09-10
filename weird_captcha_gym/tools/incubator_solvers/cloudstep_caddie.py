from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "cloudstep_caddie"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"cloudstep-caddie-{name}.png"), full_page=True)


def _wait_new(state_dir: Path, previous: str) -> None:
    deadline = time.time() + 8
    while time.time() < deadline:
        if str(_read(state_dir / "ground_truth.json").get("challenge_id")) != previous:
            return
        time.sleep(0.05)
    raise AssertionError("Cloudstep Caddie did not generate a fresh challenge after rejection")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(mechanic)
    before = str(_read(state_dir / "ground_truth.json").get("challenge_id"))
    page.locator("#cloudstep-submit").click()
    expect(page.locator(".readout")).to_contain_text("FAIL", timeout=8_000)
    _wait_new(state_dir, before)
    expect(page.locator(".cloudstep-caddie")).to_be_visible()
    _shot(page, out_dir, "fail-fresh-course")


def _stroke_simplified(page, item: dict) -> None:
    page.locator(f'[data-card-id="{item["card_id"]}"]').click()
    page.locator(f'[data-direction="{item["direction"]}"]').click()


def _stroke_full(page, item: dict) -> None:
    card = page.locator(f'[data-card-id="{item["card_id"]}"]')
    direction = page.locator(f'[data-direction="{item["direction"]}"]')
    card_box = card.bounding_box()
    direction_box = direction.bounding_box()
    if not card_box or not direction_box:
        raise AssertionError("Cloudstep Caddie drag surface is not visible")
    page.mouse.move(card_box["x"] + card_box["width"] / 2, card_box["y"] + card_box["height"] / 2)
    page.mouse.down()
    page.mouse.move(direction_box["x"] + direction_box["width"] / 2, direction_box["y"] + direction_box["height"] / 2)
    page.mouse.up()


def solve(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(mechanic)
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "simplified")
    _shot(page, out_dir, "initial-course")
    solution = list(truth.get("solution") or [])
    if not solution:
        raise AssertionError("Cloudstep Caddie oracle has no solution")
    for index, item in enumerate(solution):
        if interaction == "full":
            _stroke_full(page, item)
        else:
            _stroke_simplified(page, item)
        expect(page.locator("#cloudstep-counter")).to_have_text(f"{index + 1} / {len(solution)}")
        page.wait_for_timeout(120)
        if index == 0:
            _shot(page, out_dir, "active-after-first-stroke")
    _shot(page, out_dir, "solved-pre-submit")
    with page.expect_response(lambda response: response.url.endswith("/result")) as response_info:
        page.locator("#cloudstep-submit").click()
    outcome = response_info.value.json()
    if outcome.get("passed") is not True:
        raise AssertionError(f"Cloudstep Caddie server rejected the solved UI path: {outcome}")
    expect(page.locator(".readout")).to_have_text("PASS", timeout=8_000)
    _shot(page, out_dir, "pass")


__all__ = ["MECHANIC_ID", "fail_once", "solve"]
