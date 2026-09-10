from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "lantern_loft"
CANVAS_WIDTH = 900
CANVAS_HEIGHT = 560


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=True)


def _point(page, slot_id: int) -> tuple[float, float]:
    point = page.evaluate("slot => window.lanternLoftModel.slotPoint(slot)", slot_id)
    canvas = page.locator("#lantern-loft-canvas")
    box = canvas.bounding_box()
    if not box:
        raise AssertionError("Lantern Loft canvas is not visible")
    return box["x"] + float(point[0]) / CANVAS_WIDTH * box["width"], box["y"] + float(point[1]) / CANVAS_HEIGHT * box["height"]


def _slide(page, move: dict, interaction: str) -> None:
    source = int(move["from_slot"])
    target = int(move["to_slot"])
    if interaction == "simplified":
        page.locator(f'[data-slide-from="{source}"][data-slide-to="{target}"]').click()
    else:
        sx, sy = _point(page, source)
        tx, ty = _point(page, target)
        page.mouse.move(sx, sy)
        page.mouse.down()
        page.mouse.move(tx, ty, steps=10)
        page.mouse.up()
    page.wait_for_timeout(45)


def _step(page, target: int, interaction: str) -> None:
    if interaction == "simplified":
        page.locator(f'[data-step-slot="{target}"]').click()
    else:
        x, y = _point(page, target)
        page.mouse.click(x, y)
    page.wait_for_timeout(45)


def _wait_new_challenge(state_dir: Path, previous: str) -> None:
    deadline = time.time() + 8
    while time.time() < deadline:
        current = str(_read(state_dir / "ground_truth.json").get("challenge_id") or "")
        if current and current != previous:
            return
        time.sleep(.05)
    raise AssertionError("Lantern Loft failure did not issue a fresh challenge")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    expect(page.locator(".lantern-loft")).to_be_visible(timeout=7_000)
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    _shot(page, out_dir, "failure-before-abandon")
    page.locator("#lantern-abandon").click()
    _wait_new_challenge(state_dir, before)
    expect(page.locator(".lantern-loft")).to_be_visible(timeout=7_000)
    page.wait_for_function("() => document.querySelector('.lantern-loft')?.dataset.completed === 'false'")
    _shot(page, out_dir, "failure-recovery-new-loft")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    expect(page.locator(".lantern-loft")).to_be_visible(timeout=7_000)
    truth = _read(state_dir / "ground_truth.json")
    condition = truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "full")
    slides = list(truth.get("solution_slides") or [])
    route = [int(item) for item in truth.get("route_slots") or []]
    if not slides or len(route) < 3:
        raise AssertionError("Lantern Loft oracle route is incomplete")
    _shot(page, out_dir, "initial-isometric-loft")
    for index, move in enumerate(slides):
        _slide(page, move, interaction)
        if index in {0, len(slides) - 1}:
            _shot(page, out_dir, f"active-slide-{index + 1:02d}")
    for index, target in enumerate(route[1:], start=1):
        _step(page, target, interaction)
        if index in {1, max(1, len(route) // 2), len(route) - 1}:
            _shot(page, out_dir, f"active-walk-{index:02d}")
    expect(page.locator(".lantern-status")).to_have_text("PASS · LANTERN AT THE LOFT EXIT", timeout=10_000)
    _shot(page, out_dir, "authoritative-pass")
