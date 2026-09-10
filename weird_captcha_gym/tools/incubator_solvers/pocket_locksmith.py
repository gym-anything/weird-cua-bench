from __future__ import annotations

import json
import math
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "pocket_locksmith"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=True)


def _interaction(truth: dict) -> str:
    return str((truth.get("control_condition") or {}).get("interaction") or "full")


def _steps(current: float, target: float, step: float) -> int:
    value = int(round((float(target) - float(current)) / float(step)))
    if abs(value) > 60:
        raise AssertionError(f"unexpected torsion distance {current} -> {target} by {step}")
    return value


def _wait_result(state_dir: Path, passed: bool) -> dict:
    deadline = time.time() + 8
    while time.time() < deadline:
        result_path = state_dir / "result.json"
        if result_path.exists():
            result = _read(result_path)
            if bool((result.get("server_grade") or {}).get("passed")) is passed:
                return result
        time.sleep(.05)
    raise AssertionError("Pocket Locksmith result was not written")


def _wait_failed_attempt(state_dir: Path) -> dict:
    deadline = time.time() + 8
    while time.time() < deadline:
        path = state_dir / "attempts.jsonl"
        if path.exists():
            lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            if lines:
                attempt = json.loads(lines[-1])
                if bool((attempt.get("server_grade") or {}).get("passed")) is False:
                    return attempt
        time.sleep(.05)
    raise AssertionError("Pocket Locksmith failed attempt was not archived")


def _button_step(page, bond_index: int, side: int) -> None:
    page.locator(f'[data-torsion="{bond_index}"][data-side="{side}"]').click()
    page.wait_for_timeout(12)


def _solve_simplified(page, truth: dict, out_dir: Path) -> None:
    step = float(truth["torsion_step_deg"])
    for bond_index, (current, target) in enumerate(zip(truth["initial_torsions"], truth["target_torsions"], strict=True)):
        for _ in range(abs(_steps(current, target, step))):
            _button_step(page, bond_index, 1 if target > current else -1)
        current = target
        if bond_index == 0:
            _shot(page, out_dir, "active-first-torsion")


def _canvas_point(page, internal: dict[str, float]) -> tuple[float, float]:
    box = page.locator("#pl-canvas").bounding_box()
    if not box:
        raise AssertionError("Pocket Locksmith canvas is not visible")
    return (
        box["x"] + float(internal["x"]) / 780.0 * box["width"],
        box["y"] + float(internal["y"]) / 480.0 * box["height"],
    )


def _orbit_until_visible(page, bond_index: int, side: int) -> dict:
    canvas = page.locator("#pl-canvas")
    for attempt in range(32):
        handle = page.evaluate(
            "([bond, side]) => (window.pocketLocksmithModel?.handles || []).find(item => item.bondIndex === bond && item.side === side && item.visible) || null",
            [bond_index, side],
        )
        if handle:
            return handle
        box = canvas.bounding_box()
        if not box:
            raise AssertionError("Pocket Locksmith canvas is not visible")
        # Start in a quiet corner so an already-visible handle near the key
        # cannot turn the orbit gesture into an accidental torsion drag.
        center_x = box["x"] + box["width"] * .12
        center_y = box["y"] + box["height"] * .16
        # Sweep the orbit in one direction. Alternating a fixed drag would
        # revisit the same two views and could leave a depth-occluded handle
        # inaccessible forever.
        direction = 1
        page.mouse.move(center_x, center_y)
        page.mouse.down()
        page.mouse.move(center_x + direction * box["width"] * .27, center_y, steps=4)
        page.mouse.up()
        page.wait_for_timeout(24)
    raise AssertionError(f"bond {bond_index + 1} side {side} stayed hidden after camera search")


def _drag_handle(page, bond_index: int, side: int) -> None:
    handle = _orbit_until_visible(page, bond_index, side)
    start = _canvas_point(page, handle)
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move(start[0] + 24, start[1] + 12, steps=4)
    page.mouse.up()
    page.wait_for_timeout(18)


def _solve_full(page, truth: dict, out_dir: Path) -> None:
    step = float(truth["torsion_step_deg"])
    for bond_index, (current, target) in enumerate(zip(truth["initial_torsions"], truth["target_torsions"], strict=True)):
        count = _steps(current, target, step)
        side = 1 if count >= 0 else -1
        for _ in range(abs(count)):
            _drag_handle(page, bond_index, side)
        if bond_index == 0:
            _shot(page, out_dir, "active-first-handle-drag")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(mechanic)
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator("#pl-certify").click()
    page.wait_for_timeout(90)
    _wait_failed_attempt(state_dir)
    expect(page.locator(".readout")).to_contain_text("FAIL", timeout=8_000)
    _shot(page, out_dir, "fail-fresh-pocket")
    page.wait_for_timeout(2_350)
    after = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    if not after or after == before:
        raise AssertionError("failed Pocket Locksmith submission did not regenerate the challenge")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(mechanic)
    truth = _read(state_dir / "ground_truth.json")
    interaction = _interaction(truth)
    if interaction == "simplified":
        _solve_simplified(page, truth, out_dir)
    else:
        _solve_full(page, truth, out_dir)
    model_snapshot = page.evaluate(
        "() => ({torsions: window.pocketLocksmithModel?.torsions || [], camera: window.pocketLocksmithModel?.camera || {}, local: window.pocketLocksmithModel?.local || {}})"
    )
    (out_dir / "solver_model_before_certify.json").write_text(json.dumps(model_snapshot, indent=2) + "\n", encoding="utf-8")
    _shot(page, out_dir, "solved-before-certify")
    page.locator("#pl-certify").click()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=8_000)
    result = _wait_result(state_dir, True)
    grade = result.get("server_grade") or {}
    if grade.get("passed") is not True:
        raise AssertionError(f"Pocket Locksmith solver result was not accepted: {grade}")
    if not math.isfinite(float((grade.get("metrics") or {}).get("contacts", 0))):
        raise AssertionError("Pocket Locksmith result has invalid metrics")
    _shot(page, out_dir, "pass")
