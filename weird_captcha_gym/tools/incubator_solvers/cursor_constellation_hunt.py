from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "cursor_constellation_hunt"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, mechanic: str, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{label}.png"), full_page=True)


def _wait_for_new_challenge(state_dir: Path, previous: str) -> None:
    deadline = time.time() + 8
    while time.time() < deadline:
        current = str(_read(state_dir / "ground_truth.json").get("challenge_id") or "")
        if current and current != previous:
            return
        time.sleep(0.05)
    raise AssertionError("constellation challenge did not regenerate after failure")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    previous = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator("#submit-constellation").click()
    _wait_for_new_challenge(state_dir, previous)
    expect(page.locator(".readout")).to_contain_text("FAIL", timeout=8_000)
    _shot(page, out_dir, mechanic, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    public = _read(state_dir / "public_state.json")
    truth = _read(state_dir / "ground_truth.json")
    expected = truth["expected_click"]
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    decoys = public["surface"]["decoys"]
    probe = decoys[0] if decoys else {"x": 48, "y": 48}
    if interaction == "simplified":
        for point in (probe, expected):
            page.locator("#constellation-x").fill(str(point["x"]))
            page.locator("#constellation-y").fill(str(point["y"]))
            page.locator("#move-constellation-lens").click()
            page.wait_for_timeout(300)
        page.locator("#select-constellation-point").click()
    else:
        canvas = page.locator(".constellation-canvas")
        box = canvas.bounding_box()
        if not box:
            raise AssertionError("constellation canvas has no visible geometry")
        page.mouse.move(
            box["x"] + float(probe["x"]) * box["width"] / 680,
            box["y"] + float(probe["y"]) * box["height"] / 410,
        )
        page.wait_for_timeout(300)
        x = box["x"] + float(expected["x"]) * box["width"] / 680
        y = box["y"] + float(expected["y"]) * box["height"] / 410
        page.mouse.move(x, y)
        page.wait_for_timeout(350)
        page.mouse.click(x, y)
    _shot(page, out_dir, mechanic, "solved-state")
    page.locator("#submit-constellation").click()
    expect(page.locator(".readout")).to_have_attribute("data-status", "passed", timeout=8_000)
