from __future__ import annotations

import math
from pathlib import Path

from benchmarks.weird_captcha_gym.tools.incubator_solvers.reviewed_overhaul_common import (
    drag_delta, expect_fail_and_fresh, read_json, shot,
)

MECHANIC_ID = "rotate_wrong_thing_upright"


def _solve_linear(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    work = [row[:] + [rhs[index]] for index, row in enumerate(matrix)]
    size = len(matrix)
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(work[row][column]))
        work[column], work[pivot] = work[pivot], work[column]
        scale = work[column][column]
        work[column] = [value / scale for value in work[column]]
        for row in range(size):
            if row == column:
                continue
            amount = work[row][column]
            work[row] = [work[row][index] - amount * work[column][index] for index in range(size + 1)]
    return [work[index][size] for index in range(size)]


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    assert mechanic == MECHANIC_ID
    before = read_json(state_dir / "ground_truth.json")["challenge_id"]
    page.locator(".gimbal-submit").click()
    expect_fail_and_fresh(page, state_dir, before)
    shot(page, out_dir, mechanic, "real-single-view-rejection")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    assert mechanic == MECHANIC_ID
    contract = read_json(state_dir / "public_state.json")["gimbal"]
    for view in contract["views"]:
        page.locator(f'.gimbal-view[data-view="{view}"]').click()
    c = contract["coupling"]
    axes = [str(axis) for axis in contract.get("active_axes") or ("outer", "middle", "inner")]
    effects = {
        "outer": {"outer": 1.0, "middle": 0.0, "inner": float(c["outer_to_inner"])},
        "middle": {"outer": float(c["middle_to_outer"]), "middle": 1.0, "inner": 0.0},
        "inner": {"outer": 0.0, "middle": float(c["inner_to_middle"]), "inner": 1.0},
    }
    matrix = [[effects[input_axis][output_axis] for input_axis in axes] for output_axis in axes]
    initial = contract["initial"]
    deltas = _solve_linear(matrix, [-float(initial[axis]) for axis in axes])
    for axis, degrees in zip(axes, deltas):
        remaining = degrees
        maximum = float(contract["max_drag_delta"])
        while abs(remaining) > 1e-6:
            chunk = math.copysign(min(abs(remaining), maximum * 0.9), remaining)
            drag_delta(page, page.locator(f'.gimbal-control[data-axis="{axis}"]'), chunk / float(contract["degrees_per_pixel"]), 0, maximum_step=20)
            remaining -= chunk
    shot(page, out_dir, mechanic, "tri-view-coupled-alignment")
    page.locator(".gimbal-submit").click()
