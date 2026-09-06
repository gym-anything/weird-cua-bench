from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MECHANIC_ID = "chain_of_appetite"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=True)


def _drag(page, source, destination) -> None:
    source_box = source.bounding_box()
    destination_box = destination.bounding_box()
    if source_box is None or destination_box is None:
        raise AssertionError("visible appetite drag endpoint is missing")
    start_x = source_box["x"] + source_box["width"] / 2
    start_y = source_box["y"] + source_box["height"] / 2
    end_x = destination_box["x"] + destination_box["width"] / 2
    end_y = destination_box["y"] + destination_box["height"] / 2
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(end_x, end_y, steps=8)
    page.mouse.up()


def _perform(page, move: dict[str, Any], interaction: str) -> None:
    actor = page.locator(f'.coa-monster[data-monster-id="{move["actor_id"]}"]')
    victim = page.locator(f'.coa-monster[data-monster-id="{move["victim_id"]}"]')
    if actor.count() != 1 or victim.count() != 1:
        raise AssertionError(f"solution creature is not visible: {move}")
    if interaction == "full":
        _drag(page, actor, victim)
    else:
        actor.click()
        victim.click()


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "simplified")
    failure_moves = truth.get("failure_moves") or []
    if not failure_moves:
        raise AssertionError("generator did not provide a replayed deadlock route")
    challenge_before = str(truth["challenge_id"])
    for index, move in enumerate(failure_moves, start=1):
        _perform(page, move, interaction)
        if index < len(failure_moves):
            page.wait_for_function(
                "expected => window.chainOfAppetiteModel.events.length === expected && !window.chainOfAppetiteModel.busy",
                arg=index,
                timeout=6000,
            )
    page.locator(".coa-fresh-failure").wait_for(state="visible", timeout=10000)
    challenge_after = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    if challenge_after == challenge_before:
        raise AssertionError("deadlock failure did not generate a fresh challenge")
    _screenshot(page, out_dir, "deadlock-fresh-tray")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str, *, certify: bool = True) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "simplified")
    solution_moves = truth.get("solution_moves") or []
    expected = len(truth.get("initial_monsters") or []) - 1
    if len(solution_moves) != expected:
        raise AssertionError(f"expected {expected} solution meals, got {len(solution_moves)}")
    for index, move in enumerate(solution_moves, start=1):
        _perform(page, move, interaction)
        page.wait_for_function(
            "expectedCount => window.chainOfAppetiteModel.events.length === expectedCount && !window.chainOfAppetiteModel.busy",
            arg=index,
            timeout=6000,
        )
        if index == max(1, expected // 2):
            _screenshot(page, out_dir, "active-chain")
    contract = page.evaluate(
        """() => ({
          remaining: window.chainOfAppetiteModel.monsters.length,
          events: window.chainOfAppetiteModel.events.length,
          terminal: window.chainOfAppetiteModel.terminal,
          busy: window.chainOfAppetiteModel.busy,
        })"""
    )
    if contract != {"remaining": 1, "events": expected, "terminal": False, "busy": False}:
        raise AssertionError(f"visible chain did not end at one sealable survivor: {contract}")
    _screenshot(page, out_dir, "solved-before-seal")
    if certify:
        page.locator("#coa-certify").click()
        page.wait_for_function("() => document.querySelector('.readout')?.textContent === 'PASS'", timeout=8000)

