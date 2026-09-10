from __future__ import annotations

import json
import time
from pathlib import Path


MECHANIC_ID = "lampwrights_program"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=False)


def _wait_run(page) -> None:
    page.wait_for_function("() => window.lampwrightsProgramModel && !window.lampwrightsProgramModel.playing", timeout=15_000)


def _place(page, panel: str, index: int, command: str, interaction: str) -> None:
    slot = page.locator(f'.lp-slot[data-panel="{panel}"][data-index="{index}"]')
    if interaction == "simplified":
        page.locator(f'.lp-token[data-command="{command}"]').click()
        slot.click()
    else:
        page.locator(f'.lp-token[data-command="{command}"]').drag_to(slot)


def _fill_solution(page, solution: dict[str, list[str]], interaction: str) -> None:
    for panel in ("main", "A", "B"):
        for index, command in enumerate(solution.get(panel) or []):
            _place(page, panel, index, command, interaction)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = _read(state_dir / "ground_truth.json")["challenge_id"]
    _place(page, "main", 0, "J", str(_read(state_dir / "ground_truth.json").get("control_condition", {}).get("interaction") or "full"))
    page.locator("#lp-run").click()
    _wait_run(page)
    if "BLOCKED" not in page.locator("#lp-status").inner_text():
        raise AssertionError("deliberately invalid program did not show a blocked execution")
    _shot(page, out_dir, "blocked-revision")
    page.locator("#lp-certify").click()
    page.wait_for_function(
        "before => window.lampwrightsProgramModel?.state.challenge_id !== before",
        arg=before, timeout=10_000,
    )
    from playwright.sync_api import expect
    expect(page.locator(".readout")).to_contain_text("FAIL")
    if _read(state_dir / "ground_truth.json")["challenge_id"] == before:
        raise AssertionError("rejected program did not issue a fresh roof")
    _shot(page, out_dir, "rejected-fresh-roof")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    _fill_solution(page, truth["program_solution"], interaction)
    page.locator("#lp-run").click()
    page.wait_for_function("() => window.lampwrightsProgramModel && window.lampwrightsProgramModel.completed && !window.lampwrightsProgramModel.playing", timeout=20_000)
    if "ROUTE COMPLETE" not in page.locator("#lp-status").inner_text():
        raise AssertionError("program did not complete visibly")
    _shot(page, out_dir, "route-complete")
    page.locator("#lp-certify").click()
    deadline = time.time() + 8
    while time.time() < deadline:
        if page.locator(".readout").inner_text().strip() == "PASS":
            _shot(page, out_dir, "certified-pass")
            return
        page.wait_for_timeout(100)
    raise AssertionError("Lampwright's Program did not certify")
