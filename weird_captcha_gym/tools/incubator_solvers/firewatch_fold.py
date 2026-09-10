from __future__ import annotations

import json
import time
from pathlib import Path


MECHANIC_ID = "firewatch_fold"
KEYS = {
    "UP": "ArrowUp",
    "RIGHT": "ArrowRight",
    "DOWN": "ArrowDown",
    "LEFT": "ArrowLeft",
}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=True)


def _issue(page, interaction: str, action: dict) -> None:
    kind = str(action.get("action") or "")
    if kind == "INSPECT":
        page.locator("#firewatch-inspect").click()
    elif kind == "MOVE":
        direction = str(action["direction"])
        if interaction == "full":
            page.keyboard.press(KEYS[direction])
        else:
            page.locator(f'[data-move="{direction}"]').click()
    elif kind == "EXTINGUISH":
        if interaction == "full":
            page.keyboard.press("Shift")
        else:
            page.locator("#firewatch-extinguish").click()
    else:
        raise AssertionError(f"unsupported Firewatch Fold solution action: {action!r}")
    page.wait_for_timeout(35)


def _wait_readout(page, token: str) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if token in page.locator(".readout").inner_text():
            return
        time.sleep(0.05)
    raise AssertionError(f"readout did not contain {token!r}")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = _read_json(state_dir / "ground_truth.json")["challenge_id"]
    page.locator("#firewatch-certify").click()
    _wait_readout(page, "FAIL")
    after = _read_json(state_dir / "ground_truth.json")["challenge_id"]
    if before == after:
        raise AssertionError("premature Firewatch Fold certification did not issue a fresh challenge")
    _screenshot(page, out_dir, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read_json(state_dir / "ground_truth.json")
    route = list(truth.get("solution_actions") or [])
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    if not route:
        raise AssertionError("generated Firewatch Fold route is empty")

    readout = page.locator(".readout").inner_text()
    initial_label = "retry-initial" if "FAIL" in readout else "initial"
    _screenshot(page, out_dir, initial_label)
    for index, action in enumerate(route):
        _issue(page, interaction, action)
        if index == 0:
            label = "after-inspection" if action.get("action") == "INSPECT" else "after-first-action"
            _screenshot(page, out_dir, label)
        elif index == min(5, len(route) - 1):
            _screenshot(page, out_dir, "active-route")

    _screenshot(page, out_dir, "solved")
    page.locator("#firewatch-certify").click()
    _wait_readout(page, "PASS")
    _screenshot(page, out_dir, "pass")
