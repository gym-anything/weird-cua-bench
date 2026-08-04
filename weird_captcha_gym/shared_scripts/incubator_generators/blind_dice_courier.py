from __future__ import annotations

import copy
import hashlib
import random
from collections import deque
from typing import Any


MECHANIC_ID = "blind_dice_courier"
VARIANT_COUNT = 8_640_000_000
FACE_NAMES = ("top", "bottom", "north", "south", "east", "west")
CANONICAL = {"top": 1, "bottom": 6, "north": 2, "south": 5, "east": 3, "west": 4}
DEFAULT_COLUMNS = 18
DEFAULT_ROWS = 11
DEFAULT_BARRIER_COLUMNS = (3, 6, 9, 12, 15)
DEFAULT_LOW_ROWS = (1, 2)
DEFAULT_HIGH_ROWS = (8, 9)
DEFAULT_SCANNER_GATE_INDICES = (0, 1, 2, 3)


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _roll(orientation: dict[str, int], direction: str) -> dict[str, int]:
    old = dict(orientation)
    if direction == "N":
        return {
            "top": old["south"],
            "bottom": old["north"],
            "north": old["top"],
            "south": old["bottom"],
            "east": old["east"],
            "west": old["west"],
        }
    if direction == "S":
        return {
            "top": old["north"],
            "bottom": old["south"],
            "north": old["bottom"],
            "south": old["top"],
            "east": old["east"],
            "west": old["west"],
        }
    if direction == "E":
        return {
            "top": old["west"],
            "bottom": old["east"],
            "north": old["north"],
            "south": old["south"],
            "east": old["top"],
            "west": old["bottom"],
        }
    if direction == "W":
        return {
            "top": old["east"],
            "bottom": old["west"],
            "north": old["north"],
            "south": old["south"],
            "east": old["bottom"],
            "west": old["top"],
        }
    raise ValueError(f"unknown roll direction {direction!r}")


def _trace(initial: dict[str, int], commands: list[str]) -> list[dict[str, Any]]:
    orientation = dict(initial)
    trace: list[dict[str, Any]] = []
    for index, command in enumerate(commands):
        orientation = _roll(orientation, command)
        trace.append({"step": index + 1, "direction": command, "orientation": dict(orientation)})
    return trace


def _gate_accepts(gate: dict[str, Any], orientation: dict[str, int]) -> bool:
    if int(orientation["top"]) != int(gate["required_top"]):
        return False
    return "required_east" not in gate or int(orientation["east"]) == int(gate["required_east"])


def _solve_course(
    initial: dict[str, int],
    start: tuple[int, int],
    goal: tuple[int, int],
    open_cells: set[tuple[int, int]],
    gates: list[dict[str, Any]],
) -> list[str]:
    gate_map = {(int(item["x"]), int(item["y"])): item for item in gates}
    initial_faces = tuple(int(initial[name]) for name in FACE_NAMES)
    queue: deque[tuple[tuple[int, int], tuple[int, ...], tuple[str, ...]]] = deque([(start, initial_faces, ())])
    seen = {(start, initial_faces)}
    deltas = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
    while queue:
        position, faces, path = queue.popleft()
        if position == goal:
            return list(path)
        orientation = dict(zip(FACE_NAMES, faces))
        for direction in ("N", "E", "S", "W"):
            dx, dy = deltas[direction]
            candidate = (position[0] + dx, position[1] + dy)
            if candidate not in open_cells:
                continue
            rolled = _roll(orientation, direction)
            gate = gate_map.get(candidate)
            if gate is not None and not _gate_accepts(gate, rolled):
                continue
            next_faces = tuple(int(rolled[name]) for name in FACE_NAMES)
            key = (candidate, next_faces)
            if key in seen:
                continue
            seen.add(key)
            queue.append((candidate, next_faces, path + (direction,)))
    raise ValueError("generated dice maze has no orientation-valid delivery route")


def _reachable_orientations_at(
    initial: dict[str, int],
    start: tuple[int, int],
    target: tuple[int, int],
    open_cells: set[tuple[int, int]],
    gates: list[dict[str, Any]],
) -> list[dict[str, int]]:
    gate_map = {(int(item["x"]), int(item["y"])): item for item in gates}
    initial_faces = tuple(int(initial[name]) for name in FACE_NAMES)
    queue: deque[tuple[tuple[int, int], tuple[int, ...]]] = deque([(start, initial_faces)])
    seen = {(start, initial_faces)}
    reached: list[dict[str, int]] = []
    deltas = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
    while queue:
        position, faces = queue.popleft()
        orientation = dict(zip(FACE_NAMES, faces))
        if position == target:
            reached.append(orientation)
            continue
        for direction in ("N", "E", "S", "W"):
            dx, dy = deltas[direction]
            candidate = (position[0] + dx, position[1] + dy)
            if candidate not in open_cells:
                continue
            rolled = _roll(orientation, direction)
            gate = gate_map.get(candidate)
            if gate is not None and not _gate_accepts(gate, rolled):
                continue
            next_faces = tuple(int(rolled[name]) for name in FACE_NAMES)
            key = (candidate, next_faces)
            if key in seen:
                continue
            seen.add(key)
            queue.append((candidate, next_faces))
    return reached


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    condition = task.get("_control_condition")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    columns = int(parameters.get("columns", DEFAULT_COLUMNS))
    rows = int(parameters.get("rows", DEFAULT_ROWS))
    barrier_columns = tuple(int(value) for value in parameters.get("barrier_columns", DEFAULT_BARRIER_COLUMNS))
    low_rows = tuple(int(value) for value in parameters.get("low_rows", DEFAULT_LOW_ROWS))
    high_rows = tuple(int(value) for value in parameters.get("high_rows", DEFAULT_HIGH_ROWS))
    scanner_gate_indices = tuple(
        int(value)
        for value in parameters.get("scanner_gate_indices", DEFAULT_SCANNER_GATE_INDICES)
    )
    scanner_offset = int(parameters.get("scanner_offset", 2))
    minimum_solution_rolls = int(parameters.get("minimum_solution_rolls", 48))
    maximum_solution_rolls = int(parameters.get("maximum_solution_rolls", 105))
    gate_face_requirements = int(parameters.get("gate_face_requirements", 1))
    orientation_visibility = str(parameters.get("orientation_visibility", "initial_and_scanners"))
    if not 7 <= columns <= 24 or not 7 <= rows <= 15:
        raise ValueError("dice warehouse dimensions are outside supported limits")
    if not 1 <= len(barrier_columns) <= 6:
        raise ValueError("dice warehouse must contain between one and six barriers")
    if (
        tuple(sorted(set(barrier_columns))) != barrier_columns
        or any(column < 2 or column > columns - 3 for column in barrier_columns)
        or any(right - left < 2 for left, right in zip(barrier_columns, barrier_columns[1:]))
    ):
        raise ValueError("dice barrier columns are malformed")
    if (
        not low_rows
        or not high_rows
        or any(row < 1 or row > rows - 2 for row in (*low_rows, *high_rows))
        or set(low_rows) & set(high_rows)
    ):
        raise ValueError("dice barrier gap bands are malformed")
    if (
        len(set(scanner_gate_indices)) != len(scanner_gate_indices)
        or any(index < 0 or index >= len(barrier_columns) for index in scanner_gate_indices)
        or not 1 <= scanner_offset <= rows - 3
    ):
        raise ValueError("dice scanner placement is malformed")
    if not 1 <= minimum_solution_rolls <= maximum_solution_rolls <= 240:
        raise ValueError("dice solution-length bounds are malformed")
    if gate_face_requirements not in {1, 2}:
        raise ValueError("dice gates may constrain one or two faces")
    if orientation_visibility not in {"always", "initial_and_scanners"}:
        raise ValueError("dice orientation visibility mode is unsupported")

    initial = dict(CANONICAL)
    for _ in range(rng.randint(9, 24)):
        initial = _roll(initial, rng.choice(("N", "S", "E", "W")))

    gaps = [rng.choice(low_rows if index % 2 == 0 else high_rows) for index in range(len(barrier_columns))]
    start = (1, rng.choice(high_rows))
    goal = (columns - 2, rng.choice(high_rows))
    walls = {
        (column, row)
        for column, gap in zip(barrier_columns, gaps)
        for row in range(1, rows - 1)
        if row != gap
    }
    open_cells = {
        (x, y)
        for y in range(1, rows - 1)
        for x in range(1, columns - 1)
        if (x, y) not in walls
    }
    tones = ("amber", "cyan", "violet", "coral", "lime", "rose")
    gate_ids = [f"gate-{tone}" for tone in tones[:len(barrier_columns)]]
    solution_path: list[str] | None = None
    gates: list[dict[str, Any]] = []

    def random_gate(index: int, column: int) -> dict[str, Any]:
        return {
            "id": gate_ids[index],
            "x": column,
            "y": gaps[index],
            "required_top": rng.randint(1, 6),
            "tone": tones[index],
        }

    if gate_face_requirements == 1:
        for _attempt in range(80):
            gates = [random_gate(index, column) for index, column in enumerate(barrier_columns)]
            try:
                candidate = _solve_course(initial, start, goal, open_cells, gates)
            except ValueError:
                continue
            if minimum_solution_rolls <= len(candidate) <= maximum_solution_rolls:
                solution_path = candidate
                break
    else:
        segment_start = start
        segment_orientation = initial
        for index, column in enumerate(barrier_columns):
            target = (column, gaps[index])
            segment_cells = {
                cell
                for cell in open_cells
                if segment_start[0] <= cell[0] <= target[0]
            }
            orientations = _reachable_orientations_at(
                segment_orientation,
                segment_start,
                target,
                segment_cells,
                [],
            )
            if not orientations:
                raise ValueError(f"could not reach dual-face gate {index + 1}")
            required = rng.choice(orientations)
            gates.append(
                {
                    "id": gate_ids[index],
                    "x": column,
                    "y": gaps[index],
                    "required_top": int(required["top"]),
                    "tone": tones[index],
                    "required_east": int(required["east"]),
                }
            )
            segment_start = target
            segment_orientation = required
        solution_path = _solve_course(initial, start, goal, open_cells, gates)
        if not minimum_solution_rolls <= len(solution_path) <= maximum_solution_rolls:
            solution_path = None
    if solution_path is None:
        raise ValueError(
            f"could not generate a {minimum_solution_rolls}-{maximum_solution_rolls} roll orientation maze"
        )
    scanners = [
        {
            "id": f"scanner-{scanner_index + 1}",
            "x": barrier_columns[gate_index] - 1,
            "y": max(
                1,
                min(
                    rows - 2,
                    gaps[gate_index] + (scanner_offset if gate_index % 2 == 0 else -scanner_offset),
                ),
            ),
        }
        for scanner_index, gate_index in enumerate(scanner_gate_indices)
    ]
    board = {
        "columns": columns,
        "rows": rows,
        "start": {"x": start[0], "y": start[1]},
        "goal": {"x": goal[0], "y": goal[1]},
        "open_cells": [{"x": x, "y": y} for x, y in sorted(open_cells, key=lambda item: (item[1], item[0]))],
        "gates": gates,
        "scanners": scanners,
    }
    condition_token = f"|d{int(condition['difficulty'])}" if condition else ""
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}{condition_token}".encode("utf-8")).hexdigest()[:12]
    task_id = str(task.get("id") or "blind_dice_courier_seed_0001@0.1")
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "asset_manifest": "shared_runtime/assets/provenance/incubator_puzzles_v1.json",
        "prompt": task.get("natural_language")
        or "Roll the sealed die-crate through all five face gates and deliver it. Sparse scanners reveal its orientation.",
        "generator": {"name": "blind_dice_courier_v2", "variant_count": VARIANT_COUNT},
        "board": board,
        "initial_orientation": initial,
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "board": board,
        "initial_orientation": initial,
        "gate_ids": gate_ids,
        "solution_path": solution_path,
        "solution_trace": _trace(initial, solution_path),
        "variant_count": VARIANT_COUNT,
    }
    if condition:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    assert len(gates) == len(barrier_columns)
    assert minimum_solution_rolls <= len(solution_path) <= maximum_solution_rolls
    return public_state, ground_truth
