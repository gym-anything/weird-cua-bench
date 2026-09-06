from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect


KEYS = {"UP": "ArrowUp", "RIGHT": "ArrowRight", "DOWN": "ArrowDown", "LEFT": "ArrowLeft"}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, mechanic: str, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{name}.png"), full_page=True)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator(".yard-seal").click()
    expect(page.locator(".statute-foot .readout")).to_contain_text("FAIL", timeout=6000)
    after = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    if before == after:
        raise AssertionError("statute_yard did not regenerate after deliberate failure")
    _screenshot(page, out_dir, mechanic, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    truth = _read(state_dir / "ground_truth.json")
    route = [str(item) for item in truth["solution"]]
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    trace = truth.get("solution_trace") or {}
    capture_steps = {
        int(step)
        for step in (trace.get("deadly_break_step"), trace.get("exit_make_step"), trace.get("stop_break_step"))
        if isinstance(step, int)
    }
    capture_steps.update(
        int(item["step"])
        for item in trace.get("transfers") or []
        if isinstance(item, dict) and isinstance(item.get("step"), int)
    )
    captured = 0
    for index, direction in enumerate(route, start=1):
        if interaction == "simplified":
            page.locator(f'.yard-direction[data-direction="{direction}"]').click()
        else:
            page.keyboard.press(KEYS[direction])
        page.wait_for_timeout(70)
        if index in capture_steps and captured < 2:
            captured += 1
            _screenshot(page, out_dir, mechanic, f"law-shift-{captured}")
    expect(page.locator(".statute-foot .readout")).to_contain_text("EXIT PREDICATE TRUE", timeout=4000)
    _screenshot(page, out_dir, mechanic, "solved-before-seal")
    page.locator(".yard-seal").click()
    # Static browser play may initialize Pyodide on the first verdict. The live
    # server normally responds immediately, but both surfaces use the same
    # solver and should tolerate that one-time browser-local startup.
    expect(page.locator(".statute-foot .readout")).to_contain_text("PASS", timeout=95000)
    expect(page.locator(".statute-verdict")).to_contain_text("RATIFIED", timeout=4000)
    _screenshot(page, out_dir, mechanic, "pass")
