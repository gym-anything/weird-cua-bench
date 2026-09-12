"""Oracle browser driver for Three-Trade Crew wiring and evidence capture."""
from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "three_trade_crew"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _select(page, worker_id: str, interaction: str) -> None:
    if interaction == "simplified":
        page.locator(f'.ttc-worker-card[data-worker-id="{worker_id}"]').click()
        return
    key = {"fighter": "1", "thief": "2", "wizard": "3"}[worker_id]
    page.keyboard.press(key)


def _move(page, direction: str, interaction: str) -> None:
    if interaction == "simplified":
        page.locator(f'.ttc-direction-pad button[data-direction="{direction}"]').click()
    else:
        page.keyboard.press({"up": "ArrowUp", "down": "ArrowDown", "left": "ArrowLeft", "right": "ArrowRight"}[direction])


def _wait_for_events(page, count: int) -> None:
    page.wait_for_function("n => (window.threeTradeCrewModel?.events?.length || 0) >= n", arg=int(count), timeout=5_000)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    out_dir.mkdir(parents=True, exist_ok=True)
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.screenshot(path=str(out_dir / "three_trade_crew-failure-before-certify.png"), full_page=True)
    page.locator("#ttc-certify").click()
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        current = str(_read(state_dir / "ground_truth.json").get("challenge_id") or "")
        if current and current != before:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("failed Three-Trade Crew certification did not generate a fresh challenge")
    expect(page.locator(".ttc-fail")).to_be_visible(timeout=5_000)
    page.screenshot(path=str(out_dir / "three_trade_crew-failure-fresh-workshop.png"), full_page=True)


def solve(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    actions = list(truth.get("solution_actions") or [])
    if not actions:
        raise AssertionError("generated crew route is empty")
    out_dir.mkdir(parents=True, exist_ok=True)
    current_worker = None
    for index, action in enumerate(actions, start=1):
        worker_id = str(action["worker_id"])
        if worker_id != current_worker:
            _select(page, worker_id, interaction)
            current_worker = worker_id
        _move(page, str(action["direction"]), interaction)
        _wait_for_events(page, index)
        if index == max(1, len(actions) // 2):
            page.screenshot(path=str(out_dir / "three_trade_crew-mid-route.png"), full_page=True)
    expect(page.locator(".readout")).to_contain_text("ALL BAYS READY", timeout=5_000)
    page.screenshot(path=str(out_dir / "three_trade_crew-ready-to-certify.png"), full_page=True)
    page.locator("#ttc-certify").click()
    expect(page.locator(".readout")).to_contain_text("PASS", timeout=8_000)
    expect(page.locator(".readout")).to_have_attribute("data-status", "passed")
    page.screenshot(path=str(out_dir / "three_trade_crew-pass.png"), full_page=True)
