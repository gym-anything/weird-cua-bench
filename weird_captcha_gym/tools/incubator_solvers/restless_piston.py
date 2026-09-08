from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "restless_piston"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"restless_piston-{label}.png"), full_page=True)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator("#rp-abandon").click()
    expect(page.locator(".rp-verdict.is-fresh")).to_be_visible(timeout=8_000)
    deadline = time.time() + 8
    while time.time() < deadline:
        if str(_read(state_dir / "ground_truth.json")["challenge_id"]) != before:
            break
        time.sleep(.05)
    else:
        raise AssertionError("restless piston failure did not issue a fresh chamber")
    _shot(page, out_dir, "fail-fresh")
    expect(page.locator(".rp-verdict.is-fresh")).to_be_hidden(timeout=4_000)


def _canvas_point(page, x: float, y: float) -> tuple[float, float]:
    box = page.locator("#rp-canvas").bounding_box()
    if not box:
        raise AssertionError("restless piston canvas has no physical geometry")
    scale = min(box["width"] / 900.0, box["height"] / 500.0)
    return (box["x"] + (box["width"] - 900 * scale) / 2 + x * scale,
            box["y"] + (box["height"] - 500 * scale) / 2 + y * scale)


def _direct_action(page, action: str, direction: int) -> None:
    if action == "pump":
        start = _canvas_point(page, 788, 205)
        finish = _canvas_point(page, 788, 205 - 34 * direction)
    elif action == "heat":
        start = _canvas_point(page, 788, 391)
        finish = _canvas_point(page, 788 + 34 * direction, 391)
    elif action == "wall":
        wall_x = page.evaluate(
            "() => { const m = window.restlessPistonModel; const p = m.state.physics; return 76 + m.volume / Number(p.max_volume) * 620; }"
        )
        start = _canvas_point(page, float(wall_x), 240)
        finish = _canvas_point(page, float(wall_x) + 34 * direction, 240)
    else:
        raise AssertionError(f"unknown piston action {action!r}")
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move(*finish)
    page.mouse.up()


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "simplified")
    expect(page.locator(".rp-root")).to_be_visible(timeout=6_000)
    _shot(page, out_dir, "initial")
    mode = str(truth["goal"]["required_mode"])
    page.locator("#rp-mode").select_option(mode)
    # Mode selection is the first event; each physical action adds one more.
    expected_events = 1
    for index, item in enumerate(truth["planned_actions"]):
        action = str(item["action"])
        direction = int(item["direction"])
        if interaction == "simplified":
            page.locator(f'[data-action="{action}"][data-dir="{direction}"]').click()
        else:
            _direct_action(page, action, direction)
        expected_events += 1
        page.wait_for_function("n => (window.restlessPistonModel?.events.length || 0) >= n", arg=expected_events, polling=10, timeout=8_000)
        if index == 1:
            _shot(page, out_dir, "active-closed-loop")
    settle = int(truth["physics"]["settle_ticks"])
    page.wait_for_function("n => (window.restlessPistonModel?.stable || 0) >= n", arg=settle, polling=10, timeout=30_000)
    _shot(page, out_dir, "settled-before-certify")
    page.locator("#rp-certify").click()
    expect(page.locator(".rp-verdict.is-pass")).to_be_visible(timeout=12_000)
    expect(page.locator(".readout")).to_contain_text("PASS")
    _shot(page, out_dir, "pass")
