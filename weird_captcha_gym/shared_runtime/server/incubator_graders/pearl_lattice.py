"""Independent replay grader for the Pearl Lattice 4x4x4 board."""

from __future__ import annotations

import itertools
from typing import Any


MECHANIC_ID = "pearl_lattice"
SIZE = 4
PLAYER = 1
OPPONENT = -1
EMPTY = 0
Coord = tuple[int, int, int]
Column = tuple[int, int]


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _line(start: Coord, direction: Coord) -> list[Coord]:
    return [tuple(start[i] + step * direction[i] for i in range(3)) for step in range(4)]


def _all_lines() -> list[list[Coord]]:
    lines: list[list[Coord]] = []
    for start in itertools.product(range(SIZE), repeat=3):
        for direction in itertools.product((-1, 0, 1), repeat=3):
            if direction == (0, 0, 0):
                continue
            end = tuple(start[i] + 3 * direction[i] for i in range(3))
            previous = tuple(start[i] - direction[i] for i in range(3))
            if not all(0 <= value < SIZE for value in end):
                continue
            if all(0 <= value < SIZE for value in previous):
                continue
            lines.append(_line(start, direction))
    return lines


ALL_LINES = _all_lines()


def _has_line(board: dict[Coord, int], mark: int) -> bool:
    return any(all(board.get(cell, EMPTY) == mark for cell in line) for line in ALL_LINES)


def _legal_columns(board: dict[Coord, int]) -> list[Column]:
    return [
        (x, z)
        for z in range(SIZE)
        for x in range(SIZE)
        if board.get((x, SIZE - 1, z), EMPTY) == EMPTY
    ]


def _height(board: dict[Coord, int], column: Column) -> int:
    for y in range(SIZE):
        if board.get((column[0], y, column[1]), EMPTY) == EMPTY:
            return y
    return SIZE


def _drop(board: dict[Coord, int], column: Column, mark: int) -> Coord | None:
    height = _height(board, column)
    if height >= SIZE:
        return None
    cell = (column[0], height, column[1])
    board[cell] = mark
    return cell


def _immediate_columns(board: dict[Coord, int], mark: int) -> list[Column]:
    result: list[Column] = []
    for column in _legal_columns(board):
        candidate = dict(board)
        _drop(candidate, column, mark)
        if _has_line(candidate, mark):
            result.append(column)
    return result


def _opponent_column(board: dict[Coord, int], pressure: list[Column], pressure_index: int, policy: str = "threat_then_block") -> tuple[Column | None, int]:
    own_wins = _immediate_columns(board, OPPONENT)
    if own_wins:
        return own_wins[0], pressure_index
    player_wins = _immediate_columns(board, PLAYER) if policy == "threat_then_block" else []
    if player_wins:
        return player_wins[0], pressure_index
    legal = set(_legal_columns(board))
    for offset in range(len(pressure)):
        column = tuple(int(value) for value in pressure[(pressure_index + offset) % len(pressure)])
        if column in legal:
            return column, pressure_index + offset + 1
    return (next((column for column in _legal_columns(board) if column in legal), None), pressure_index + 1)


def _parse_board(truth: dict[str, Any]) -> dict[Coord, int] | None:
    raw = truth.get("initial_board")
    if not isinstance(raw, dict):
        return None
    board: dict[Coord, int] = {}
    for raw_key, raw_value in raw.items():
        try:
            x, y, z = (int(value) for value in str(raw_key).split(","))
            value = int(raw_value)
        except (TypeError, ValueError):
            return None
        if not all(0 <= coord < SIZE for coord in (x, y, z)) or value not in {PLAYER, OPPONENT}:
            return None
        board[(x, y, z)] = value
    return board


def _column(value: Any) -> Column | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        result = (int(value[0]), int(value[1]))
    except (TypeError, ValueError):
        return None
    return result if all(0 <= item < SIZE for item in result) else None


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(truth, dict) or not isinstance(public, dict):
        return _fail("pearl lattice submission is malformed")
    for key in ("mechanic_id", "task_id", "challenge_id"):
        if payload.get(key) != truth.get(key):
            return _fail(f"stale or mismatched {key}")
    if public.get("challenge_id") != truth.get("challenge_id"):
        return _fail("public lattice is stale")
    if payload.get("control_condition") != truth.get("control_condition"):
        return _fail("submitted control condition differs from the lattice contract")
    condition = truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "")
    if interaction not in {"full", "simplified"}:
        return _fail("lattice interaction condition is invalid")
    cycle_source = "board_surface" if interaction == "full" else "proxy_next"
    confirm_source = "confirm_area" if interaction == "full" else "confirm_button"
    parameters = condition.get("difficulty_parameters") or {}
    policy = parameters.get("opponent_policy")
    if policy not in {"threat_then_block", "win_then_pressure"}:
        return _fail("lattice opponent policy is invalid")
    max_player_moves = parameters.get("max_player_moves")
    if isinstance(max_player_moves, bool) or not isinstance(max_player_moves, int) or max_player_moves < 1:
        return _fail("lattice player move ceiling is invalid")
    events = payload.get("events")
    board = _parse_board(truth)
    if not isinstance(events, list) or not events or len(events) > 4000 or board is None:
        return _fail("no usable pearl lattice transcript")
    pressure = [_column(value) for value in truth.get("pressure_columns") or []]
    if any(column is None for column in pressure) or not pressure:
        return _fail("lattice pressure columns are malformed")
    pressure_columns = [column for column in pressure if column is not None]
    legal = _legal_columns(board)
    if not legal:
        return _fail("initial lattice has no legal column")
    preview = legal[0]
    pressure_index = 0
    cycle_count = 0
    player_moves = 0
    player_won = False
    opponent_won = False
    submitted = False
    submitted_completed = False
    awaiting_rival = False
    move_ceiling_reached = False
    expected_rival: Column | None = None
    expected_pressure_index = 0
    sequence = 0
    for event in events:
        sequence += 1
        if not isinstance(event, dict) or event.get("seq") != sequence:
            return _fail("lattice event sequence is malformed")
        event_type = str(event.get("type") or "")
        if submitted:
            return _fail("lattice transcript continues after certification")
        if awaiting_rival:
            if event_type != "opponent_place":
                return _fail("missing clockwork rival response")
            if event.get("input_source") != "opponent_ai" or event.get("mark") != OPPONENT:
                return _fail("opponent response is not an authored clockwork move")
            rival_column = _column(event.get("column"))
            if rival_column != expected_rival:
                return _fail("clockwork rival response disagrees with independent replay")
            expected_height = _height(board, rival_column)
            try:
                reported_height = int(event.get("height"))
            except (TypeError, ValueError):
                return _fail("opponent response height is missing")
            if reported_height != expected_height or _drop(board, rival_column, OPPONENT) is None:
                return _fail("opponent response violates gravity")
            pressure_index = expected_pressure_index
            awaiting_rival = False
            opponent_won = _has_line(board, OPPONENT)
            if not opponent_won:
                legal = _legal_columns(board)
                if not legal:
                    return _fail("lattice filled before certification")
                if preview not in legal:
                    preview = legal[0]
            continue
        if event_type == "cycle_preview":
            if event.get("input_source") != cycle_source or player_won or opponent_won:
                return _fail("preview cycling used the wrong interaction surface or occurred after terminal state")
            before = _column(event.get("from_column"))
            after = _column(event.get("to_column"))
            if before != preview or after is None:
                return _fail("preview cycle does not continue from the visible column")
            legal = _legal_columns(board)
            if preview not in legal or after != legal[(legal.index(preview) + 1) % len(legal)]:
                return _fail("preview cycle skipped a legal column")
            preview = after
            cycle_count += 1
            continue
        if event_type == "place":
            if event.get("input_source") != confirm_source or event.get("mark") != PLAYER or player_won or opponent_won:
                return _fail("placement used the wrong confirmation surface or occurred after terminal state")
            if player_moves >= max_player_moves:
                return _fail("player move ceiling exceeded")
            column = _column(event.get("column"))
            if column != preview or column not in _legal_columns(board):
                return _fail("confirmed column differs from the visible legal preview")
            expected_height = _height(board, column)
            try:
                reported_height = int(event.get("height"))
            except (TypeError, ValueError):
                return _fail("placement height is missing")
            if reported_height != expected_height or _drop(board, column, PLAYER) is None:
                return _fail("placement violates gravity")
            player_moves += 1
            player_won = _has_line(board, PLAYER)
            if not player_won:
                if player_moves >= max_player_moves:
                    move_ceiling_reached = True
                    continue
                expected_rival, expected_pressure_index = _opponent_column(board, pressure_columns, pressure_index, policy)
                if expected_rival is None:
                    return _fail("clockwork rival has no legal response")
                awaiting_rival = True
            continue
        if event_type == "submit":
            if awaiting_rival or event.get("input_source") != "certify_button" or not isinstance(event.get("completed"), bool):
                return _fail("lattice certification is incomplete")
            submitted = True
            submitted_completed = bool(event.get("completed"))
            continue
        if event_type == "opponent_place":
            if move_ceiling_reached:
                return _fail("player move ceiling exceeded")
            return _fail("orphaned clockwork rival response")
        return _fail(f"unknown pearl lattice event {event_type!r}")

    if cycle_count < 1:
        return _fail("the two-stage preview interaction was never exercised")
    if not submitted or submitted_completed is not player_won or not player_won or opponent_won:
        return _fail(f"lattice did not finish with a player line after {player_moves} placements")
    final_board = payload.get("final_board")
    if final_board is not None:
        expected_board = {"%d,%d,%d" % cell: value for cell, value in board.items()}
        if final_board != expected_board:
            return _fail("reported final lattice disagrees with replay")
    return {
        "graded": True,
        "passed": True,
        "score": 100,
        "feedback": f"independently replayed a 4×4×4 gravity lattice and {player_moves} player placements",
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    return {
        "mechanic_id": MECHANIC_ID,
        "challenge_id": ground_truth.get("challenge_id"),
        "note": "The construction solver uses ordinary preview and confirmation controls; this record is not part of task play.",
        "solution_moves": ground_truth.get("solution_moves") or [],
    }
