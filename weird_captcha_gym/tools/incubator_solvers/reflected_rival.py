"""Ordinary-input solver used for deterministic browser evidence.

The solver reads the private witness only to choose a route for wiring tests;
it still drives the visible keyboard or proxy buttons and waits on the visible
race state before every steering decision.
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "reflected_rival"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{name}.png"), full_page=True)


def _steer(page, direction: int, interaction: str) -> None:
    if direction == 0:
        return
    if interaction == "simplified":
        page.locator(f'[data-rr-direction="{"left" if direction < 0 else "right"}"]').click()
    else:
        page.keyboard.press("ArrowLeft" if direction < 0 else "ArrowRight")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    assert mechanic == MECHANIC_ID
    before = str(_read(state_dir / "public_state.json")["challenge_id"])
    page.locator("[data-rr-abandon]").click()
    expect(page.locator(".readout")).to_contain_text("FRESH COURSE", timeout=6_000)
    # The server's state file is the authoritative retry boundary.  The
    # browser receives the fresh state in the same response, so wait for the
    # file write as well as the transient visible readout before comparing
    # challenge identities.
    after = before
    for _attempt in range(60):
        after = str(_read(state_dir / "public_state.json")["challenge_id"])
        if after != before:
            break
        page.wait_for_timeout(100)
    if before == after:
        raise AssertionError("abandon did not regenerate a fresh reflected-rival course")
    expect(page.locator(".rr-footer")).to_contain_text(after[:8].upper(), timeout=6_000)
    _shot(page, out_dir, "fail-fresh-course")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    assert mechanic == MECHANIC_ID
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    commands = [int(value) for value in truth["solution_commands"]]
    if len(commands) != int(truth["board"]["segment_count"]):
        raise AssertionError("constructive route length does not match the visible course")
    for segment, direction in enumerate(commands[1:], start=1):
        page.wait_for_function(
            "target => Number(document.querySelector('.rr-shell')?.dataset.playerSegment) >= target",
            arg=segment,
            timeout=30_000,
        )
        _steer(page, direction, interaction)
        if segment == len(commands) // 2:
            _shot(page, out_dir, "active-dual-race")
    expect(page.locator(".readout")).to_contain_text("PASS", timeout=45_000)
    expect(page.locator(".readout")).to_have_attribute("data-status", "passed")
    _shot(page, out_dir, "pass")


__all__ = ["fail_once", "solve"]
