from __future__ import annotations

import copy
import hashlib
import random
from functools import lru_cache
from typing import Any, Iterable


MECHANIC_ID = "nonogram_denouement"
DIRECTIONS = {
    (-1, 0): "NORTH",
    (0, 1): "EAST",
    (1, 0): "SOUTH",
    (0, -1): "WEST",
}
RING_LABELS = ("RING A", "RING B", "RING C", "RING D")


def _condition(task: dict[str, Any]) -> dict[str, Any] | None:
    value = task.get("_control_condition")
    return copy.deepcopy(value) if isinstance(value, dict) else None


def _parameters(task: dict[str, Any]) -> dict[str, Any]:
    condition = _condition(task)
    if condition:
        return copy.deepcopy(condition["difficulty_parameters"])
    return {
        "grid_size": 8,
        "density": 0.42,
        "logic_round_min": 3,
        "logic_round_max": 6,
        "route_steps": 10,
        "marker_count": 2,
        "answer_direction_count": 4,
        "pulse_segment_ms": 560,
    }


def _validate(parameters: dict[str, Any]) -> None:
    integer_bounds = {
        "grid_size": (5, 10),
        "logic_round_min": (1, 10),
        "logic_round_max": (1, 10),
        "route_steps": (5, 20),
        "marker_count": (1, 4),
        "answer_direction_count": (2, 4),
        "pulse_segment_ms": (250, 1200),
    }
    for key, (low, high) in integer_bounds.items():
        value = parameters.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"{key} must be an integer in [{low}, {high}]")
    density = parameters.get("density")
    if isinstance(density, bool) or not isinstance(density, (int, float)) or not 0.25 <= float(density) <= 0.65:
        raise ValueError("density must be a finite number in [0.25, 0.65]")
    if parameters["logic_round_min"] > parameters["logic_round_max"]:
        raise ValueError("logic round bounds are reversed")
    if parameters["route_steps"] > parameters["grid_size"] ** 2:
        raise ValueError("route_steps exceeds the grid")
    if parameters["marker_count"] > parameters["route_steps"] - 2:
        raise ValueError("marker_count exceeds internal route positions")


def line_clues(line: Iterable[int]) -> tuple[int, ...]:
    clues: list[int] = []
    run = 0
    for value in [*line, 0]:
        if value:
            run += 1
        elif run:
            clues.append(run)
            run = 0
    return tuple(clues)


@lru_cache(maxsize=None)
def line_options(length: int, clues: tuple[int, ...]) -> tuple[tuple[int, ...], ...]:
    if not clues:
        return ((0,) * length,)
    options: list[tuple[int, ...]] = []

    def place(clue_index: int, position: int, prefix: list[int]) -> None:
        if clue_index == len(clues):
            options.append(tuple(prefix + [0] * (length - len(prefix))))
            return
        run = clues[clue_index]
        remaining = sum(clues[clue_index + 1 :]) + max(0, len(clues) - clue_index - 1)
        last_start = length - run - remaining
        for start in range(position, last_start + 1):
            row = prefix + [0] * (start - len(prefix)) + [1] * run
            if clue_index < len(clues) - 1:
                row.append(0)
            place(clue_index + 1, len(row), row)

    place(0, 0, [])
    return tuple(options)


def propagation_profile(solution: list[list[int]]) -> dict[str, Any]:
    size = len(solution)
    row_clues = [line_clues(row) for row in solution]
    col_clues = [line_clues(solution[row][col] for row in range(size)) for col in range(size)]
    row_candidates = [list(line_options(size, clues)) for clues in row_clues]
    col_candidates = [list(line_options(size, clues)) for clues in col_clues]
    known: list[list[int | None]] = [[None] * size for _ in range(size)]
    rounds = 0

    while rounds <= size * 2:
        rounds += 1
        changed = False
        for row in range(size):
            row_candidates[row] = [
                option
                for option in row_candidates[row]
                if all(known[row][col] is None or known[row][col] == option[col] for col in range(size))
            ]
            if not row_candidates[row]:
                return {"solved": False, "rounds": rounds, "average_line_candidates": 0.0}
            for col in range(size):
                values = {option[col] for option in row_candidates[row]}
                if len(values) == 1 and known[row][col] is None:
                    known[row][col] = values.pop()
                    changed = True
        for col in range(size):
            col_candidates[col] = [
                option
                for option in col_candidates[col]
                if all(known[row][col] is None or known[row][col] == option[row] for row in range(size))
            ]
            if not col_candidates[col]:
                return {"solved": False, "rounds": rounds, "average_line_candidates": 0.0}
            for row in range(size):
                values = {option[row] for option in col_candidates[col]}
                if len(values) == 1 and known[row][col] is None:
                    known[row][col] = values.pop()
                    changed = True
        if all(known[row][col] is not None for row in range(size) for col in range(size)) or not changed:
            break

    solved = all(known[row][col] == solution[row][col] for row in range(size) for col in range(size))
    candidate_count = sum(len(line_options(size, clues)) for clues in row_clues + col_clues)
    return {
        "solved": solved,
        "rounds": rounds,
        "average_line_candidates": round(candidate_count / (size * 2), 3),
    }


def _random_path(rng: random.Random, size: int, length: int) -> list[tuple[int, int]]:
    for _ in range(240):
        path = [(rng.randrange(1, size - 1), rng.randrange(1, size - 1))]
        visited = {path[0]}
        while len(path) < length:
            row, col = path[-1]
            candidates = [
                (row + delta_row, col + delta_col)
                for delta_row, delta_col in DIRECTIONS
                if 0 <= row + delta_row < size
                and 0 <= col + delta_col < size
                and (row + delta_row, col + delta_col) not in visited
            ]
            if not candidates:
                break
            previous_delta = None
            if len(path) > 1:
                previous_delta = (row - path[-2][0], col - path[-2][1])
            rng.shuffle(candidates)
            candidates.sort(
                key=lambda point: sum(
                    1
                    for dr, dc in DIRECTIONS
                    if 0 <= point[0] + dr < size
                    and 0 <= point[1] + dc < size
                    and (point[0] + dr, point[1] + dc) not in visited
                ),
                reverse=True,
            )
            # Keep several high-degree continuations in play. Always taking
            # the straightest branch makes compact paths hit an edge before
            # they acquire the turn needed by the denouement question.
            point = rng.choice(candidates[: min(3, len(candidates))])
            path.append(point)
            visited.add(point)
        turns = [
            index
            for index in range(1, len(path) - 1)
            if (path[index][0] - path[index - 1][0], path[index][1] - path[index - 1][1])
            != (path[index + 1][0] - path[index][0], path[index + 1][1] - path[index][1])
        ]
        required_turns = 1 if length <= 6 else 2
        if len(path) == length and len(turns) >= required_turns:
            return path
    raise RuntimeError("could not generate a routed proof-light path")


def _candidate(rng: random.Random, parameters: dict[str, Any]) -> tuple[list[list[int]], list[tuple[int, int]]]:
    size = parameters["grid_size"]
    path = _random_path(rng, size, parameters["route_steps"])
    solution = [[0] * size for _ in range(size)]
    for row, col in path:
        solution[row][col] = 1
    target_ink = max(len(path) + 1, round(size * size * float(parameters["density"])))
    candidates = [
        (row, col)
        for row in range(size)
        for col in range(size)
        if not solution[row][col]
    ]
    rng.shuffle(candidates)
    for row, col in candidates[: max(0, target_ink - len(path))]:
        solution[row][col] = 1
    return solution, path


def _build_puzzle(rng: random.Random, parameters: dict[str, Any]) -> tuple[list[list[int]], list[tuple[int, int]], dict[str, Any]]:
    for _ in range(6000):
        solution, path = _candidate(rng, parameters)
        profile = propagation_profile(solution)
        if profile["solved"] and parameters["logic_round_min"] <= profile["rounds"] <= parameters["logic_round_max"]:
            return solution, path, profile
    raise RuntimeError("could not generate a line-solvable plate inside the requested profile")


def _direction(start: tuple[int, int], end: tuple[int, int]) -> str:
    try:
        return DIRECTIONS[(end[0] - start[0], end[1] - start[1])]
    except KeyError as exc:
        raise ValueError("route contains a non-cardinal segment") from exc


def generate(task: dict[str, Any], seed: str):
    parameters = _parameters(task)
    _validate(parameters)
    stable = hashlib.sha256(f"{MECHANIC_ID}:{seed}:{parameters}".encode("utf-8")).hexdigest()
    rng = random.Random(int(stable[:16], 16))
    challenge_id = f"nd-{stable[:18]}"
    task_id = str(task.get("id") or "nonogram_denouement")
    solution, path, logic_profile = _build_puzzle(rng, parameters)
    size = parameters["grid_size"]
    row_clues = [list(line_clues(row)) for row in solution]
    col_clues = [list(line_clues(solution[row][col] for row in range(size))) for col in range(size)]

    turn_indices = [
        index
        for index in range(1, len(path) - 1)
        if _direction(path[index - 1], path[index]) != _direction(path[index], path[index + 1])
    ]
    question_index = rng.choice(turn_indices)
    other_indices = [index for index in range(1, len(path) - 1) if index != question_index]
    rng.shuffle(other_indices)
    marker_indices = [question_index, *other_indices[: parameters["marker_count"] - 1]]
    rng.shuffle(marker_indices)
    markers = []
    target_marker_id = ""
    for label, route_index in zip(RING_LABELS, marker_indices):
        marker_id = label.lower().replace(" ", "-")
        row, col = path[route_index]
        markers.append({"id": marker_id, "label": label, "row": row, "col": col})
        if route_index == question_index:
            target_marker_id = marker_id

    correct_direction = _direction(path[question_index], path[question_index + 1])
    alternatives = [value for value in DIRECTIONS.values() if value != correct_direction]
    rng.shuffle(alternatives)
    answer_options = [correct_direction, *alternatives[: parameters["answer_direction_count"] - 1]]
    rng.shuffle(answer_options)
    public_puzzle = {
        "size": size,
        "row_clues": row_clues,
        "col_clues": col_clues,
        "route": [{"row": row, "col": col} for row, col in path],
        "markers": markers,
        "target_marker_id": target_marker_id,
        "question": f"When the bright proof-light crosses {next(item['label'] for item in markers if item['id'] == target_marker_id)}, which direction does it leave?",
        "answer_options": answer_options,
        "pulse_segment_ms": parameters["pulse_segment_ms"],
    }
    condition = _condition(task)
    public_state = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": "Ink the plate. Develop the motion. Read your own proof.",
        "puzzle": copy.deepcopy(public_puzzle),
        "parameters": copy.deepcopy(parameters),
        "asset_manifest": str((task.get("metadata") or {}).get("asset_manifest") or "shared_runtime/assets/provenance/nonogram_denouement_v0.json"),
        "status": "ready",
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "puzzle": copy.deepcopy(public_puzzle),
        "solution": copy.deepcopy(solution),
        "correct_direction": correct_direction,
        "question_route_index": question_index,
        "logic_profile": logic_profile,
        "parameters": copy.deepcopy(parameters),
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
