"""Visible-input Playwright solver used only as an implementation witness.

The generated files choose a deterministic legal route for evidence capture;
the browser actions themselves use the same visible card, research, map, and
certification controls available to an evaluated screenshot-only agent.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "last_carbon_isles"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{name}.png"), full_page=True)


def _drag(page, card_id: str, region_id: str) -> None:
    card = page.locator(f'.carbon-card[data-card-id="{card_id}"]')
    region = page.locator(f'.carbon-isle[data-region-id="{region_id}"]')
    expect(card).to_be_visible(timeout=4_000)
    expect(region).to_be_visible(timeout=4_000)
    card.scroll_into_view_if_needed()
    source = card.bounding_box()
    target = region.bounding_box()
    if not source or not target:
        raise AssertionError("visible policy or isle bounds are unavailable")
    page.mouse.move(source["x"] + source["width"] / 2, source["y"] + source["height"] / 2)
    page.mouse.down()
    page.mouse.move(target["x"] + target["width"] / 2, target["y"] + target["height"] / 2, steps=12)
    page.mouse.up()


def _place(page, interaction: str, card_id: str, region_id: str) -> None:
    if interaction == "simplified":
        card = page.locator(f'.carbon-card[data-card-id="{card_id}"]')
        card.click()
        expect(page.locator(f'.carbon-card[data-card-id="{card_id}"].is-selected')).to_be_visible(timeout=2_000)
        page.locator(f'.carbon-isle[data-region-id="{region_id}"]').click()
    else:
        _drag(page, card_id, region_id)
    page.wait_for_timeout(120)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator(".certify-button").click()
    expect(page.locator(".carbon-verdict.is-fail")).to_be_visible(timeout=8_000)
    _shot(page, out_dir, "failure")
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        after = str(_read(state_dir / "ground_truth.json")["challenge_id"])
        if after != before:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("failed certification did not regenerate the challenge")
    page.locator(".carbon-verdict.is-fail button").click()
    expect(page.locator(".carbon-captcha[data-challenge-id]")).to_be_visible(timeout=8_000)
    _shot(page, out_dir, "recovery")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID, **_kwargs) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    state = _read(state_dir / "public_state.json")
    truth = _read(state_dir / "ground_truth.json")
    condition = truth.get("control_condition") or state.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "full")
    cards = {str(card["id"]): card for card in truth["cards"]}
    target_ids = {str(card_id) for card_id in truth["target_card_ids"]}
    _shot(page, out_dir, "initial")

    if truth.get('witness_route'):
        page.locator('.atlas-open').click()
        _shot(page, out_dir, 'policy-atlas')
        page.locator('.carbon-atlas-dialog button').click()
        route = truth['witness_route']
        for track in truth['research_tracks']:
            card_id = next(c['id'] for c in track['offers'] if c['id'] in route)
            page.locator(f'.research-card[data-research-id="{card_id}"]').click()
        for index, card_id in enumerate(route):
            _place(page, interaction, card_id, cards[card_id]['home_region'])
            if index in (0, 1):
                _shot(page, out_dir, f'crew-transfer-{index}')
        expect(page.locator('.carbon-isle.is-clear')).to_have_count(len(truth['regions']))
        _shot(page, out_dir, 'pre-certify')
        page.locator('.certify-button').click()
        expect(page.locator('.carbon-verdict.is-pass')).to_be_visible(timeout=8000)
        _shot(page, out_dir, 'pass')
        return

    for card_id in truth["initial_hand_ids"]:
        card_id = str(card_id)
        if card_id in target_ids:
            _place(page, interaction, card_id, str(cards[card_id]["home_region"]))
    if truth["research_tracks"]:
        _shot(page, out_dir, "after-initial-policies")
    for track in truth["research_tracks"]:
        card_id = next(
            str(offer["id"])
            for offer in track["offers"]
            if str(offer["id"]) in target_ids
        )
        page.locator(f'.research-card[data-research-id="{card_id}"]').click()
        page.wait_for_timeout(120)
        _place(page, interaction, card_id, str(cards[card_id]["home_region"]))

    expect(page.locator(".carbon-isle.is-clear")).to_have_count(len(truth["regions"]), timeout=4_000)
    _shot(page, out_dir, "pre-certify")
    page.locator(".certify-button").click()
    expect(page.locator(".carbon-verdict.is-pass")).to_be_visible(timeout=8_000)
    _shot(page, out_dir, "pass")


__all__ = ["MECHANIC_ID", "fail_once", "solve"]
