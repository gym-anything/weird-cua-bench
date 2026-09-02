from __future__ import annotations

import copy
import math
from typing import Any, Iterable


MECHANIC_ID = "nonogram_denouement"
DIRECTIONS = {
    (-1, 0): "NORTH",
    (0, 1): "EAST",
    (1, 0): "SOUTH",
    (0, -1): "WEST",
}
CELL_VALUES = {"ink": 1, "clear": -1, "reset": 0}


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _bind(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> str | None:
    if any(str(item.get("mechanic_id") or "") != MECHANIC_ID for item in (payload, truth, public)):
        return "mechanic mismatch"
    for key in ("task_id", "challenge_id"):
        expected = str(truth.get(key) or "")
        if not expected or str(payload.get(key) or "") != expected or str(public.get(key) or "") != expected:
            return f"stale or mismatched {key}"
    return None


def _line_clues(line: Iterable[int]) -> list[int]:
    clues: list[int] = []
    run = 0
    for value in [*line, 0]:
        if value == 1:
            run += 1
        elif run:
            clues.append(run)
            run = 0
    return clues


def _direction(start: dict[str, Any], end: dict[str, Any]) -> str:
    delta = (int(end["row"]) - int(start["row"]), int(end["col"]) - int(start["col"]))
    if delta not in DIRECTIONS:
        raise ValueError("proof route contains a non-cardinal segment")
    return DIRECTIONS[delta]


def _contract(truth: dict[str, Any], public: dict[str, Any]) -> tuple[dict[str, Any], list[list[int]], str, str]:
    puzzle = truth.get("puzzle")
    if not isinstance(puzzle, dict) or public.get("puzzle") != puzzle:
        raise ValueError("public proof plate differs from replay contract")
    parameters = truth.get("parameters")
    if not isinstance(parameters, dict) or public.get("parameters") != parameters:
        raise ValueError("difficulty parameters differ from replay contract")
    condition = truth.get("control_condition")
    if condition != public.get("control_condition"):
        raise ValueError("public control condition differs from replay contract")
    if condition is not None and condition.get("difficulty_parameters") != parameters:
        raise ValueError("condition parameters differ from generated plate")
    interaction = str((condition or {}).get("interaction") or "full")
    if interaction not in {"simplified", "full"}:
        raise ValueError("interaction mode is invalid")

    size = puzzle.get("size")
    solution = truth.get("solution")
    if isinstance(size, bool) or not isinstance(size, int) or not 5 <= size <= 10:
        raise ValueError("plate size is invalid")
    if parameters.get("grid_size") != size:
        raise ValueError("grid_size does not match the plate")
    if (
        not isinstance(solution, list)
        or len(solution) != size
        or any(not isinstance(row, list) or len(row) != size for row in solution)
        or any(value not in {0, 1} for row in solution for value in row)
    ):
        raise ValueError("solution matrix is invalid")
    row_clues = [_line_clues(row) for row in solution]
    col_clues = [_line_clues(solution[row][col] for row in range(size)) for col in range(size)]
    if puzzle.get("row_clues") != row_clues or puzzle.get("col_clues") != col_clues:
        raise ValueError("visible clues do not describe the solution")

    route = puzzle.get("route")
    if not isinstance(route, list) or len(route) != parameters.get("route_steps"):
        raise ValueError("proof route length differs from the profile")
    for index, point in enumerate(route):
        if not isinstance(point, dict):
            raise ValueError("proof route point is invalid")
        row, col = point.get("row"), point.get("col")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in (row, col)):
            raise ValueError("proof route coordinates are invalid")
        if not 0 <= row < size or not 0 <= col < size or solution[row][col] != 1:
            raise ValueError("proof route leaves the developed ink")
        if index:
            _direction(route[index - 1], point)
    question_index = truth.get("question_route_index")
    if isinstance(question_index, bool) or not isinstance(question_index, int) or not 1 <= question_index < len(route) - 1:
        raise ValueError("question route index is invalid")
    correct_direction = _direction(route[question_index], route[question_index + 1])
    if truth.get("correct_direction") != correct_direction:
        raise ValueError("answer direction differs from the proof route")
    markers = puzzle.get("markers")
    if not isinstance(markers, list) or len(markers) != parameters.get("marker_count"):
        raise ValueError("marker count differs from the profile")
    target_marker_id = str(puzzle.get("target_marker_id") or "")
    target = next((item for item in markers if isinstance(item, dict) and item.get("id") == target_marker_id), None)
    if target is None or target.get("row") != route[question_index]["row"] or target.get("col") != route[question_index]["col"]:
        raise ValueError("question marker is not on the audited route point")
    options = puzzle.get("answer_options")
    if (
        not isinstance(options, list)
        or len(options) != parameters.get("answer_direction_count")
        or len(set(options)) != len(options)
        or correct_direction not in options
        or any(option not in DIRECTIONS.values() for option in options)
    ):
        raise ValueError("answer options are invalid")
    return puzzle, copy.deepcopy(solution), interaction, correct_direction


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _straight_contiguous(cells: list[dict[str, Any]]) -> bool:
    points = [(cell["row"], cell["col"]) for cell in cells]
    if len(set(points)) != len(points):
        return False
    rows = {point[0] for point in points}
    cols = {point[1] for point in points}
    if len(rows) == 1:
        ordered = sorted(point[1] for point in points)
    elif len(cols) == 1:
        ordered = sorted(point[0] for point in points)
    else:
        return False
    return ordered == list(range(ordered[0], ordered[-1] + 1))


def _validate_answer_gesture(event: dict[str, Any], direction: str) -> None:
    gesture = event.get("gesture")
    if not isinstance(gesture, dict):
        raise ValueError("direct answer lacks drag proof")
    if gesture.get("start_direction") != direction or gesture.get("dropped_in_well") is not True:
        raise ValueError("direct answer drag endpoints are invalid")
    travel = gesture.get("travel_px")
    samples = gesture.get("sample_count")
    if (
        isinstance(travel, bool)
        or not isinstance(travel, (int, float))
        or not math.isfinite(float(travel))
        or float(travel) < 40
        or isinstance(samples, bool)
        or not isinstance(samples, int)
        or samples < 2
    ):
        raise ValueError("direct answer drag is too short or sparsely sampled")


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    binding = _bind(payload, truth, public)
    if binding:
        return _fail(binding)
    try:
        puzzle, solution, interaction, correct_direction = _contract(truth, public)
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"invalid nonogram contract: {exc}")
    if payload.get("interaction_mode") != interaction:
        return _fail("submitted interaction mode differs from task condition")
    events = payload.get("events")
    size = puzzle["size"]
    if not isinstance(events, list) or not 3 <= len(events) <= size * size * 5 + 20:
        return _fail("interaction transcript is missing or outside limits")

    board = [[0] * size for _ in range(size)]
    developed = False
    answer: str | None = None
    mark_sources = {"full": "direct_grid_stroke", "simplified": "proxy_mark_button"}
    answer_sources = {"full": "direction_slug_drag", "simplified": "direction_proxy_button"}
    mark_count = 0
    try:
        for sequence, event in enumerate(events, 1):
            if not isinstance(event, dict) or event.get("sequence") != sequence:
                raise ValueError(f"event {sequence} has an invalid sequence")
            event_type = event.get("type")
            if event_type == "mark":
                if developed:
                    raise ValueError(f"event {sequence} edits a developed plate")
                if event.get("input_source") != mark_sources[interaction]:
                    raise ValueError(f"event {sequence} uses the wrong mark input surface")
                mode = str(event.get("mode") or "")
                if mode not in CELL_VALUES:
                    raise ValueError(f"event {sequence} has an invalid mark mode")
                cells = event.get("cells")
                if not isinstance(cells, list) or not 1 <= len(cells) <= size:
                    raise ValueError(f"event {sequence} has an invalid mark span")
                if interaction == "simplified" and len(cells) != 1:
                    raise ValueError(f"event {sequence} batches proxy marks")
                if interaction == "full":
                    if not _straight_contiguous(cells):
                        raise ValueError(f"event {sequence} is not a straight contiguous stroke")
                    expected_button = {"ink": "left", "clear": "right", "reset": "shift"}[mode]
                    if event.get("pointer_button") != expected_button:
                        raise ValueError(f"event {sequence} disagrees with its pointer button")
                for cell in cells:
                    if not isinstance(cell, dict):
                        raise ValueError(f"event {sequence} contains an invalid cell")
                    row = _integer(cell.get("row"), "cell row")
                    col = _integer(cell.get("col"), "cell col")
                    before = _integer(cell.get("before"), "cell before")
                    after = _integer(cell.get("after"), "cell after")
                    if not 0 <= row < size or not 0 <= col < size:
                        raise ValueError(f"event {sequence} leaves the plate")
                    if before != board[row][col] or after != CELL_VALUES[mode]:
                        raise ValueError(f"event {sequence} starts from stale cell state")
                    board[row][col] = after
                mark_count += 1
            elif event_type == "develop":
                if developed or event.get("input_source") != "develop_button":
                    raise ValueError(f"event {sequence} has an invalid develop transition")
                if any(value == 0 for row in board for value in row):
                    raise ValueError(f"event {sequence} develops an undecided plate")
                ink = [[1 if value == 1 else 0 for value in row] for row in board]
                if ink != solution:
                    raise ValueError(f"event {sequence} develops a clue-inconsistent plate")
                developed = True
            elif event_type == "answer":
                if not developed or event.get("input_source") != answer_sources[interaction]:
                    raise ValueError(f"event {sequence} uses an invalid answer surface or phase")
                direction = str(event.get("direction") or "")
                if direction not in puzzle["answer_options"]:
                    raise ValueError(f"event {sequence} chooses an unavailable direction")
                if interaction == "full":
                    _validate_answer_gesture(event, direction)
                answer = direction
            else:
                raise ValueError(f"event {sequence} has an unknown type")
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"nonogram replay rejected: {exc}")

    if payload.get("final_grid") != board:
        return _fail("submitted plate does not match transcript replay")
    if payload.get("final_answer") != answer:
        return _fail("submitted direction does not match transcript replay")
    complete = payload.get("completed") is True and developed and answer is not None
    passed = complete and answer == correct_direction
    return {
        "graded": True,
        "passed": passed,
        "feedback": f"plate {size}×{size} exact; {mark_count} replayed mark strokes; developed={developed}; direction {answer or 'NONE'}",
    }
