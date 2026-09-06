from __future__ import annotations

import json
import math
from pathlib import Path


MECHANIC_ID = "bandaged_rose_window"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"))


def _drag_handle(page, truth: dict, disc_id: str, direction: int, step_delay_ms: int = 0) -> None:
    disc = next(item for item in truth["rose"]["discs"] if item["id"] == disc_id)
    handle = page.locator(f'.rose-handle[data-disc="{disc_id}"]')
    box = handle.bounding_box()
    svg_box = page.locator(".current-rose .rose-svg").bounding_box()
    if box is None or svg_box is None:
        raise AssertionError(f"rose handle {disc_id} has no visible bounds")
    # The SVG uses a 640×510 viewBox beginning at (180,18) with meet scaling.
    scale = min(svg_box["width"] / 640.0, svg_box["height"] / 510.0)
    offset_x = svg_box["x"] + (svg_box["width"] - 640.0 * scale) / 2.0 - 180.0 * scale
    offset_y = svg_box["y"] + (svg_box["height"] - 510.0 * scale) / 2.0 - 18.0 * scale
    start_x = box["x"] + box["width"] / 2.0
    start_y = box["y"] + box["height"] / 2.0
    start_angle = math.atan2((start_y - offset_y) / scale - disc["center"][1], (start_x - offset_x) / scale - disc["center"][0])
    end_angle = start_angle + direction * math.radians(58)
    radius = float(disc.get("handle_radius") or disc["radius"])
    end_x = offset_x + (float(disc["center"][0]) + math.cos(end_angle) * radius) * scale
    end_y = offset_y + (float(disc["center"][1]) + math.sin(end_angle) * radius) * scale
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    for step in range(1, 13):
        angle = start_angle + (end_angle - start_angle) * step / 12.0
        x = offset_x + (float(disc["center"][0]) + math.cos(angle) * radius) * scale
        y = offset_y + (float(disc["center"][1]) + math.sin(angle) * radius) * scale
        page.mouse.move(x, y)
        if step_delay_ms:
            page.wait_for_timeout(step_delay_ms)
    page.mouse.up()


def _move(page, truth: dict, move: dict, interaction: str, step_delay_ms: int = 0) -> None:
    disc_id = str(move["disc_id"])
    direction = int(move["direction"])
    if interaction == "simplified":
        page.locator(f'.rose-turn-button[data-disc="{disc_id}"][data-direction="{direction}"]').click()
    else:
        _drag_handle(page, truth, disc_id, direction, step_delay_ms=step_delay_ms)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = _read(state_dir / "ground_truth.json")["challenge_id"]
    page.locator("#rose-certify").click()
    page.wait_for_function("() => document.querySelector('.bandaged-rose-captcha')?.dataset.failureReady === 'true'", timeout=10000)
    _shot(page, out_dir, "failed")
    page.locator("#rose-retry").click()
    page.wait_for_function("() => document.querySelector('.bandaged-rose-captcha')?.dataset.freshFailure === 'true'", timeout=10000)
    after = _read(state_dir / "ground_truth.json")["challenge_id"]
    if before == after:
        raise AssertionError("failed rose submission did not create a fresh challenge")
    status = page.evaluate("() => ({failed: document.querySelector('.bandaged-rose-captcha')?.classList.contains('is-failed'), fresh: document.querySelector('.bandaged-rose-captcha')?.dataset.freshFailure})")
    if status != {"failed": False, "fresh": "true"}:
        raise AssertionError(f"fresh rose retained stale failure state: {status}")
    _shot(page, out_dir, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    solution = truth.get("solution_moves") or []
    if len(solution) != int(truth["rose"]["optimal_distance"]):
        raise AssertionError("rose solution is not the declared exact-distance path")
    for index, move in enumerate(solution, start=1):
        _move(page, truth, move, interaction)
        page.wait_for_function("expected => window.bandagedRoseWindowModel.successful === expected", arg=index, timeout=7000)
        if index == max(1, len(solution) // 2):
            _shot(page, out_dir, "mid-restoration")
    contract = page.evaluate("() => ({ready: window.bandagedRoseWindowModel.ready, turns: window.bandagedRoseWindowModel.successful, state: window.bandagedRoseWindowModel.current})")
    if not contract["ready"] or contract["turns"] != len(solution) or contract["state"] != truth["rose"]["solved_state"]:
        raise AssertionError(f"rose solution did not visibly restore the reference: {contract}")
    _shot(page, out_dir, "solved")
    page.locator("#rose-certify").click()
    page.wait_for_function("() => document.querySelector('.bandaged-rose-captcha')?.classList.contains('is-passed')", timeout=10000)
    _shot(page, out_dir, "passed")
