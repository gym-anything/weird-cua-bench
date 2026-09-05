from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


MECHANIC_ID = "circle_limit_twist"
Matrix = tuple[complex, complex, complex, complex]


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"))


def _multiply(left: Matrix, right: Matrix) -> Matrix:
    a, b, c, d = left
    e, f, g, h = right
    return (a * e + b * g, a * f + b * h, c * e + d * g, c * f + d * h)


def _apply(matrix: Matrix, point: complex) -> complex:
    a, b, c, d = matrix
    return (a * point + b) / (c * point + d)


def _phi(point: complex) -> Matrix:
    return (1 + 0j, -point, -point.conjugate(), 1 + 0j)


def _inverse_phi(point: complex) -> Matrix:
    return (1 + 0j, point, point.conjugate(), 1 + 0j)


def _translation(start: complex, end: complex) -> Matrix:
    return _multiply(_inverse_phi(end), _phi(start))


def _canvas_box(page) -> dict[str, float]:
    box = page.locator("#circle-disc").bounding_box()
    if box is None or box["width"] <= 0 or box["height"] <= 0:
        raise AssertionError("Poincare disc has no visible geometry")
    return box


def _screen(box: dict[str, float], point: complex) -> tuple[float, float]:
    return (
        box["x"] + box["width"] * (450.0 + point.real * 420.0) / 900.0,
        box["y"] + box["height"] * (450.0 + point.imag * 420.0) / 900.0,
    )


def _focus_full(page, matrix: Matrix, point: complex) -> Matrix:
    current = _apply(matrix, point)
    if abs(current) < 0.001:
        return matrix
    if abs(current) >= 0.98:
        # Pull the same radial direction inward using background geometry, then
        # finish by dragging the actual face center to the aperture center.
        radial = current / abs(current) * 0.90
        box = _canvas_box(page)
        start, end = _screen(box, radial), _screen(box, 0j)
        page.mouse.move(*start)
        page.mouse.down()
        page.mouse.move(*end)
        page.mouse.up()
        matrix = _multiply(_translation(radial, 0j), matrix)
        current = _apply(matrix, point)
    if abs(current) >= 0.98:
        raise AssertionError(f"face remained outside draggable disc: {abs(current):.5f}")
    box = _canvas_box(page)
    start, end = _screen(box, current), _screen(box, 0j)
    before = page.evaluate("() => window.circleLimitTwistModel.viewEvents")
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move(*end)
    page.mouse.up()
    page.wait_for_function("before => window.circleLimitTwistModel.viewEvents > before", arg=before, timeout=5000)
    return _multiply(_translation(current, 0j), matrix)


def _focus_simplified(page, matrix: Matrix, point: complex) -> Matrix:
    current = _apply(matrix, point)
    if abs(current) >= 0.985:
        raise AssertionError(f"target face is outside the visible focus surface: {abs(current):.5f}")
    box = _canvas_box(page)
    before = page.evaluate("() => window.circleLimitTwistModel.viewEvents")
    page.mouse.click(*_screen(box, current))
    page.wait_for_function("before => window.circleLimitTwistModel.viewEvents > before", arg=before, timeout=5000)
    return _multiply(_phi(current), matrix)


def _turn(page, direction: int, interaction: str) -> None:
    if interaction == "simplified":
        page.locator(f'.twist-proxy button[data-direction="{direction}"]').click()
    else:
        box = _canvas_box(page)
        page.mouse.click(*_screen(box, 0j), button="right" if direction == 1 else "left")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    if interaction == "simplified":
        page.locator('.twist-proxy button[data-direction="1"]').click()
        expected_readout = "NO FACE CENTERED"
    else:
        candidate = next(
            complex(*face["center"])
            for face in truth["puzzle"]["faces"]
            if truth["puzzle"]["activation_radius"] + .05 < abs(complex(*face["center"])) < .95
        )
        page.mouse.click(*_screen(_canvas_box(page), candidate))
        expected_readout = "NO CHANGE"
    invalid_state = page.evaluate(
        "() => ({readout: document.querySelector('.readout')?.textContent, twists: window.circleLimitTwistModel.twists})"
    )
    if invalid_state != {"readout": expected_readout, "twists": 0}:
        raise AssertionError(f"invalid action produced unexpected state: {invalid_state}")
    _shot(page, out_dir, "invalid-action")
    before = _read(state_dir / "ground_truth.json")["challenge_id"]
    page.locator("#circle-certify").click()
    page.wait_for_function("() => document.querySelector('.circle-limit-twist')?.dataset.failureReady === 'true'", timeout=10000)
    _shot(page, out_dir, "failed")
    page.locator("#circle-retry").click()
    page.wait_for_function("() => document.querySelector('.circle-limit-twist')?.dataset.freshFailure === 'true'", timeout=10000)
    after = _read(state_dir / "ground_truth.json")["challenge_id"]
    if before == after:
        raise AssertionError("failed circle-limit submission did not create a fresh challenge")
    status = page.evaluate("() => ({failed: document.querySelector('.circle-limit-twist')?.classList.contains('is-failed'), fresh: document.querySelector('.circle-limit-twist')?.dataset.freshFailure})")
    if status != {"failed": False, "fresh": "true"}:
        raise AssertionError(f"fresh circle-limit task retained stale failure state: {status}")
    _shot(page, out_dir, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    puzzle = truth["puzzle"]
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    faces = {int(face["id"]): complex(*face["center"]) for face in puzzle["faces"]}
    solution = truth.get("solution_moves") or []
    if len(solution) != int(puzzle["scramble_length"]):
        raise AssertionError("solution length does not invert the recorded scramble")
    if len(solution) > int(puzzle["move_budget"]):
        raise AssertionError("solution exceeds the visible move budget")
    matrix: Matrix = (1 + 0j, 0j, 0j, 1 + 0j)
    for index, move in enumerate(solution, start=1):
        face_id = int(move["face_id"])
        direction = int(move["direction"])
        matrix = (
            _focus_simplified(page, matrix, faces[face_id])
            if interaction == "simplified"
            else _focus_full(page, matrix, faces[face_id])
        )
        _turn(page, direction, interaction)
        page.wait_for_function("expected => window.circleLimitTwistModel.twists === expected", arg=index, timeout=5000)
        if index == max(1, math.ceil(len(solution) / 2)):
            _shot(page, out_dir, "mid-restoration")
    contract = page.evaluate("() => ({state: window.circleLimitTwistModel.current, twists: window.circleLimitTwistModel.twists, monochrome: window.circleLimitTwistModel.current.every(face => new Set(face).size === 1)})")
    if not contract["monochrome"] or contract["twists"] != len(solution):
        raise AssertionError(f"visible circle-limit state did not solve: {contract}")
    _shot(page, out_dir, "solved")
    page.locator("#circle-certify").click()
    page.wait_for_function("() => document.querySelector('.circle-limit-twist')?.classList.contains('is-passed')", timeout=10000)
    _shot(page, out_dir, "passed")
