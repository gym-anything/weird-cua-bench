from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "polarity_run"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{name}.png"), full_page=True)


def _set_full_dial(page, polarity: int) -> None:
    dial = page.locator(".polarity-dial")
    range_input = page.locator(".polarity-dial-range")
    box = dial.bounding_box()
    if not box:
        raise AssertionError("polarity dial is not visible")
    current = int(range_input.input_value())
    current_fraction = 0.04 if current < 0 else 0.96 if current > 0 else 0.50
    fraction = 0.04 if int(polarity) < 0 else 0.96 if int(polarity) > 0 else 0.50
    x = box["x"] + box["width"] * fraction
    y = box["y"] + box["height"] * 0.5
    # Start at the currently visible knob. The full surface is a real drag,
    # so a neutral correction must travel from the prior detent rather than
    # clicking the center of the native range track.
    page.mouse.move(box["x"] + box["width"] * current_fraction, y)
    page.mouse.down()
    page.mouse.move(x, y, steps=6)
    page.mouse.up()


def _set_polarity(page, interaction: str, polarity: int) -> None:
    if interaction == "simplified":
        page.locator(f'.polarity-button[data-polarity="{int(polarity)}"]').click()
    else:
        _set_full_dial(page, polarity)


def _run_solution(page, truth: dict, out_dir: Path) -> None:
    condition = truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "full")
    events = list(truth.get("solution_events") or [])
    if not events:
        raise AssertionError("polarity truth has no authoring route")
    started = time.monotonic()
    for index, event in enumerate(events):
        if index == 0:
            _set_polarity(page, interaction, int(event["polarity"]))
            started = time.monotonic()
            continue
        target_ms = int(event["tick"]) * 40
        remaining = target_ms - int((time.monotonic() - started) * 1000)
        if remaining > 0:
            page.wait_for_timeout(remaining)
        _set_polarity(page, interaction, int(event["polarity"]))
    expect(page.locator(".polarity-run-readout")).to_contain_text("PASS", timeout=25_000)
    _screenshot(page, out_dir, "pass")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    interaction = str((_read(state_dir / "ground_truth.json").get("control_condition") or {}).get("interaction") or "full")
    # The full dial starts at its neutral detent, so dragging to neutral would
    # emit no input event and would not start the physical clock.  A positive
    # detent is deliberately wrong but visibly starts the run in both modes.
    _set_polarity(page, interaction, 1 if interaction == "full" else 0)
    page.wait_for_timeout(18_500)
    # The browser submits asynchronously when the timeout frame is reached.
    # Give the loopback server a bounded response window before checking that
    # its rejected attempt produced the next challenge.
    deadline = time.monotonic() + 5.0
    while before == str(_read(state_dir / "ground_truth.json")["challenge_id"]) and time.monotonic() < deadline:
        page.wait_for_timeout(250)
    after = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    if before == after:
        raise AssertionError("polarity_run did not regenerate after the deliberate coasting failure")
    _screenshot(page, out_dir, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    _run_solution(page, truth, out_dir)
