from __future__ import annotations

import json
import time
from pathlib import Path


MECHANIC_ID = "polyrhythm_customs"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, mechanic: str, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{label}.png"), full_page=True)


def _wait_new_challenge(state_dir: Path, old_challenge: str) -> None:
    deadline = time.time() + 8
    while time.time() < deadline:
        current = str(_read(state_dir / "ground_truth.json").get("challenge_id") or "")
        if current and current != old_challenge:
            return
        time.sleep(0.05)
    raise AssertionError("polyrhythm challenge did not regenerate after failure")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator(".rhythm-start").click()
    page.wait_for_selector('.rhythm-score-lane[data-active="true"]', timeout=5_000)
    page.wait_for_timeout(420)
    _screenshot(page, out_dir, mechanic, "active-single-lane-preview")
    page.wait_for_function(
        "() => document.querySelector('.polyrhythm-customs-captcha')?.dataset.phase === 'performance'",
        timeout=28_000,
    )
    page.locator(".rhythm-certify-now").click()
    _wait_new_challenge(state_dir, before)
    page.wait_for_function("() => document.querySelector('.readout')?.textContent.includes('FAIL')", timeout=8_000)
    page.wait_for_selector('.polyrhythm-customs-captcha[data-fresh-failure="true"]')
    _screenshot(page, out_dir, mechanic, "fail-refresh")


def _elapsed(page) -> float:
    return float(page.evaluate("() => performance.now() - window.polyrhythmCustomsModel.performanceStartedAt"))


def _perform(page, truth: dict, *, shorten_holds: bool = False) -> list[tuple[float, int, str, str]]:
    """Enter a visible score using only the configured browser input surface."""
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    key_by_lane = {str(lane["id"]): str(lane["key"]) for lane in truth["lanes"]}
    events: list[tuple[float, int, str, str]] = []
    for note in truth["expected_notes"]:
        lane = str(note["lane"])
        start = float(note["start_ms"])
        duration = 100.0 if shorten_holds and note["kind"] == "hold" else float(note["duration_ms"])
        events.append((start, 1, lane, "down"))
        events.append((start + duration, 0, lane, "up"))
    events.sort(key=lambda event: (event[0], event[1], event[2]))

    page.locator(".rhythm-start").click()
    page.wait_for_function(
        "() => document.querySelector('.polyrhythm-customs-captcha')?.dataset.phase === 'performance'",
        timeout=28_000,
    )
    if interaction == "simplified":
        duration = float(truth["settings"]["performance_ms"])
        for note in truth["expected_notes"]:
            lane = str(note["lane"])
            bounds = page.locator(f'.rhythm-entry-track[data-entry-track="{lane}"]').bounding_box()
            if not bounds:
                raise AssertionError(f"rhythm timing ledger {lane} has no visible bounds")
            start_x = bounds["x"] + float(note["start_ms"]) / duration * bounds["width"]
            y = bounds["y"] + bounds["height"] / 2
            note_duration = 100.0 if shorten_holds and note["kind"] == "hold" else float(note["duration_ms"])
            if note["kind"] == "hold":
                end_x = start_x + note_duration / duration * bounds["width"]
                page.mouse.move(start_x, y)
                page.mouse.down()
                page.mouse.move(end_x, y)
                page.mouse.up()
            else:
                page.mouse.click(start_x, y)
        return events
    for target_ms, _order, lane, event_type in events:
        remaining = target_ms - _elapsed(page)
        if remaining > 4:
            page.wait_for_timeout(max(1, int(remaining - 3)))
        while _elapsed(page) < target_ms - 1:
            page.wait_for_timeout(1)
        key = key_by_lane[lane]
        if event_type == "down":
            page.keyboard.down(key)
        else:
            page.keyboard.up(key)
    return events


def fail_short_holds_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    """Show that short visible taps cannot substitute for every long bar."""
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    before = str(truth["challenge_id"])
    events = _perform(page, truth, shorten_holds=True)
    _screenshot(page, out_dir, mechanic, "short-hold-performance")
    page.locator(".rhythm-certify-now").click()
    _wait_new_challenge(state_dir, before)
    page.wait_for_function("() => document.querySelector('.readout')?.textContent.includes('FAIL')", timeout=8_000)
    page.wait_for_selector('.polyrhythm-customs-captcha[data-fresh-failure="true"]')
    _screenshot(page, out_dir, mechanic, "short-hold-rejected")
    attempts = [
        json.loads(line)
        for line in (state_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not attempts or (attempts[-1].get("server_grade") or {}).get("passed") is not False:
        raise AssertionError("shortened required holds were unexpectedly accepted")
    if len(attempts[-1].get("transcript") or []) != len(events):
        raise AssertionError("short-hold probe did not record every physical input event")


def pass_short_holds_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    """Show that the unchanged baseline treats long-bar duration as a bonus."""
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    events = _perform(page, truth, shorten_holds=True)
    _screenshot(page, out_dir, mechanic, "short-hold-baseline-performance")
    page.wait_for_function("() => document.querySelector('.readout')?.textContent.startsWith('PASS')", timeout=8_000)
    _screenshot(page, out_dir, mechanic, "short-hold-baseline-pass")
    result = _read(state_dir / "result.json")
    if (result.get("server_grade") or {}).get("passed") is not True:
        raise AssertionError("baseline short-hold bonus transcript was unexpectedly rejected")
    if len(result.get("transcript") or []) != len(events):
        raise AssertionError("baseline short-hold probe did not record every physical input event")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    events = _perform(page, truth)
    if interaction == "simplified":
        page.locator(".rhythm-certify-now").click()
    page.wait_for_function("() => document.querySelector('.readout')?.textContent.startsWith('PASS')", timeout=8_000)
    _screenshot(page, out_dir, mechanic, "pass-combined-performance")
    result = _read(state_dir / "result.json")
    transcript = result.get("transcript") or []
    if len(transcript) != len(events):
        raise AssertionError(f"expected {len(events)} physical input events, captured {len(transcript)}")
    expected_source = "pointer_toggle" if interaction == "simplified" else "keyboard"
    if {str(event.get("source")) for event in transcript} != {expected_source}:
        raise AssertionError(f"polyrhythm solver did not use the {interaction} input surface")
