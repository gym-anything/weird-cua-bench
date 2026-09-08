"""Visible-UI evidence solver for Tomorrow's Marble.

The solver reads the generated fixture only to choose a deterministic evidence
path.  It performs the trial through the same visible palette, timeline,
run, and certify controls as a screenshot-only agent.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import expect


MECHANIC_ID = "tomorrows_marble"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _key(node: dict[str, Any]) -> tuple[int, int, int]:
    return int(node["machine_index"]), int(node["piece_index"]), int(node["slot"])


def _center(locator):
    box = locator.bounding_box()
    assert box is not None
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def _place(page, state: dict[str, Any], node: dict[str, Any]) -> None:
    interaction = str(state.get("interaction_mode") or state.get("control_condition", {}).get("interaction") or "full")
    piece = page.locator(f'.tm-piece[data-piece-index="{int(node["piece_index"])}"]')
    cell = page.locator(
        f'.tm-cell[data-machine-index="{int(node["machine_index"])}"][data-slot="{int(node["slot"])}"]'
    )
    # Higher profiles put the lower machine rows below the 720 px observation
    # viewport.  Scrolling the visible target into view is part of the normal
    # browser interaction and keeps the evidence path from depending on a
    # particular page height.
    cell.scroll_into_view_if_needed()
    if interaction == "simplified":
        piece.click()
        cell.click()
        return
    piece.scroll_into_view_if_needed()
    page.mouse.move(*_center(piece))
    page.mouse.down()
    cell.scroll_into_view_if_needed()
    page.mouse.move(*_center(cell), steps=10)
    page.mouse.up()


def _place_schedule(page, state: dict[str, Any], schedule: list[dict[str, Any]]) -> None:
    for node in schedule:
        _place(page, state, node)


def _wrong_node(state: dict[str, Any], solution: list[dict[str, Any]]) -> dict[str, int]:
    occupied = {_key(node) for node in solution}
    for machine_index in range(len(state.get("machines") or [])):
        for piece_index in range(len(state.get("pieces") or [])):
            for slot in range(int(state["timeline_slots"])):
                candidate = {"machine_index": machine_index, "piece_index": piece_index, "slot": slot}
                if _key(candidate) not in occupied:
                    return candidate
    raise AssertionError("generated world has no empty invalid ledger cell")


def _wait_for_new_challenge(state_dir: Path, previous: str, timeout: float = 10.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = _read(state_dir / "public_state.json")
        if str(state.get("challenge_id")) != previous:
            return state
        time.sleep(0.05)
    raise AssertionError("failed certification did not issue a fresh challenge")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    """Run a deliberately open ledger, then capture the regenerated task."""

    assert mechanic == MECHANIC_ID
    out_dir.mkdir(parents=True, exist_ok=True)
    state = _read(state_dir / "public_state.json")
    truth = _read(state_dir / "ground_truth.json")
    before = str(state["challenge_id"])
    _place(page, state, _wrong_node(state, truth["solution_schedule"]))
    page.screenshot(path=str(out_dir / "failure-open-ledger.png"))
    page.locator("#tm-run").click()
    expect(page.locator("#tm-run-clock")).to_have_text("PARADOX OPEN", timeout=15000)
    page.screenshot(path=str(out_dir / "failure-paradox-open.png"))
    page.locator("#tm-certify").click()
    fresh = _wait_for_new_challenge(state_dir, before)
    expect(page.locator(".tm-readout")).to_contain_text("FRESH CONTRAPTION ISSUED", timeout=10000)
    page.screenshot(path=str(out_dir / "failure-fresh-challenge.png"))
    assert fresh["challenge_id"] != before


def solve(page, state_dir: Path, out_dir: Path, mechanic: str, *, time_mode: str = "live") -> None:
    """Schedule the generated fixed point through visible controls and certify it."""

    assert mechanic == MECHANIC_ID
    out_dir.mkdir(parents=True, exist_ok=True)
    state = _read(state_dir / "public_state.json")
    truth = _read(state_dir / "ground_truth.json")
    assert state["challenge_id"] == truth["challenge_id"]
    page.screenshot(path=str(out_dir / "initial.png"))
    _place_schedule(page, state, truth["solution_schedule"])
    expect(page.locator(".tm-arrival")).to_have_count(len(truth["solution_schedule"]))
    page.screenshot(path=str(out_dir / "constructed-ledger.png"))
    page.locator("#tm-run").click()
    if time_mode == "paused":
        # The shared paused evaluator opens a finite observation window.  The
        # harness uses the same framework clock API here so the animation can
        # be observed without adding a task-level live/paused branch.
        page.evaluate("duration => WeirdCaptchaTime.runFor(duration)", int(state["run_duration_ms"]) + 400)
    page.wait_for_timeout(min(1200, int(state["run_duration_ms"]) - 100))
    page.screenshot(path=str(out_dir / "active-physical-trace.png"))
    expect(page.locator("#tm-run-clock")).to_have_text("LOOP CLOSED", timeout=15000)
    page.screenshot(path=str(out_dir / "closed-ledger.png"))
    page.locator("#tm-certify").click()
    expect(page.locator(".tm-readout")).to_contain_text("PASS", timeout=15000)
    page.screenshot(path=str(out_dir / "certified.png"))


__all__ = ["MECHANIC_ID", "fail_once", "solve"]
