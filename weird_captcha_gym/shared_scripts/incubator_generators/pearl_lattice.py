"""Deterministic original 4x4x4 gravity-board worlds for Pearl Lattice."""

from __future__ import annotations

import copy
import hashlib
import itertools
import random
from collections import deque
from typing import Any


MECHANIC_ID = "pearl_lattice"
SIZE = 4
PLAYER = 1
OPPONENT = -1
EMPTY = 0
Coord = tuple[int, int, int]
Column = tuple[int, int]

DEFAULT_PARAMETERS: dict[str, Any] = {
    "geometry": "cross_fork",
    "prefill_player": 2,
    "extra_noise": 6,
    "rotation_step_degrees": 12,
    "rotation_rate": 0.0016,
    "preview_label_detail": "coordinates",
    "opponent_policy": "threat_then_block",
    "max_player_moves": 8,
}
PARAMETER_FIELDS = frozenset(DEFAULT_PARAMETERS)


def _seed_int(seed: str, salt: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).digest()[:8], "big")


def _condition(task: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = task.get("_control_condition")
    if raw is None:
        raw = (task.get("metadata") or {}).get("control_condition")
    if raw is None:
        return {
            "difficulty": 3,
            "interaction": "full",
            "real_time": "live",
            "difficulty_parameters": copy.deepcopy(DEFAULT_PARAMETERS),
        }, copy.deepcopy(DEFAULT_PARAMETERS)
    if not isinstance(raw, dict):
        raise ValueError("pearl lattice control condition is malformed")
    values = copy.deepcopy(raw.get("difficulty_parameters") or {})
    if set(values) != PARAMETER_FIELDS:
        raise ValueError("pearl lattice difficulty profile fields do not match the generator contract")
    if values["geometry"] not in {"planar_easy", "cross_fork", "raised_fork", "spatial_fork"}:
        raise ValueError("pearl lattice geometry is invalid")
    for name in ("prefill_player", "extra_noise", "max_player_moves"):
        if not isinstance(values[name], int) or values[name] < 0:
            raise ValueError(f"pearl lattice {name} is invalid")
    if not 0 <= values["prefill_player"] <= 3:
        raise ValueError("pearl lattice prefill_player is outside the supported range")
    if not 0 <= values["extra_noise"] <= 20:
        raise ValueError("pearl lattice extra_noise is outside the supported range")
    if not 1 <= values["max_player_moves"] <= 12:
        raise ValueError("pearl lattice max_player_moves is outside the supported range")
    if not isinstance(values["rotation_step_degrees"], (int, float)) or not 5 <= values["rotation_step_degrees"] <= 30:
        raise ValueError("pearl lattice rotation step is invalid")
    if not isinstance(values["rotation_rate"], (int, float)) or not 0.0001 <= values["rotation_rate"] <= 0.01:
        raise ValueError("pearl lattice rotation rate is invalid")
    if values["preview_label_detail"] not in {"coordinates", "layer"}:
        raise ValueError("pearl lattice preview label detail is invalid")
    if values["opponent_policy"] not in {"threat_then_block", "win_then_pressure"}:
        raise ValueError("pearl lattice opponent policy is invalid")
    condition = {
        "difficulty": int(raw.get("difficulty", 3)),
        "interaction": str(raw.get("interaction") or "full"),
        "real_time": str(raw.get("real_time") or "live"),
        "difficulty_parameters": copy.deepcopy(values),
    }
    if condition["difficulty"] not in {1, 2, 3, 4, 5} or condition["interaction"] not in {"full", "simplified"}:
        raise ValueError("pearl lattice condition identity is invalid")
    if condition["real_time"] not in {"live", "paused"}:
        raise ValueError("pearl lattice real-time condition is invalid")
    return condition, values


def _line(start: Coord, direction: Coord) -> list[Coord]:
    return [tuple(start[index] + step * direction[index] for index in range(3)) for step in range(4)]


def _transform(coord: Coord, *, flip_x: bool, flip_z: bool, swap_xz: bool) -> Coord:
    x, y, z = coord
    if flip_x:
        x = SIZE - 1 - x
    if flip_z:
        z = SIZE - 1 - z
    if swap_xz:
        x, z = z, x
    return x, y, z


def _layout(parameters: dict[str, Any], seed: str) -> tuple[list[list[Coord]], list[Coord]]:
    geometry = parameters["geometry"]
    if geometry == "planar_easy":
        shared = (0, 1, 0)
        targets = [
            _line(shared, (1, 0, 0)),
        ]
        opponent = _line(shared, (0, 0, 1))
    elif geometry == "cross_fork":
        shared = (0, 1, 0)
        targets = [
            _line(shared, (1, 0, 1)),
            _line(shared, (1, 0, 0)),
        ]
        opponent = _line(shared, (0, 0, 1))
    elif geometry == "raised_fork":
        shared = (0, 2, 0)
        targets = [
            _line(shared, (1, 0, 1)),
            _line(shared, (1, 0, 0)),
        ]
        opponent = _line(shared, (0, 0, 1))
    else:
        shared = (0, 0, 0)
        targets = [
            _line(shared, (1, 1, 1)),
            _line(shared, (0, 0, 1)),
        ]
        opponent = _line(shared, (1, 0, 0))

    rng = random.Random(_seed_int(seed, "orientation"))
    flags = {
        "flip_x": rng.randrange(2) == 1,
        "flip_z": rng.randrange(2) == 1,
        "swap_xz": rng.randrange(2) == 1,
    }
    transformed_targets = [[_transform(coord, **flags) for coord in line] for line in targets]
    transformed_opponent = [_transform(coord, **flags) for coord in opponent]
    return transformed_targets, transformed_opponent


def _all_lines() -> list[list[Coord]]:
    lines: list[list[Coord]] = []
    directions = [direction for direction in itertools.product((-1, 0, 1), repeat=3) if direction != (0, 0, 0)]
    for x, y, z in itertools.product(range(SIZE), repeat=3):
        for dx, dy, dz in directions:
            end = (x + 3 * dx, y + 3 * dy, z + 3 * dz)
            if not all(0 <= value < SIZE for value in end):
                continue
            previous = (x - dx, y - dy, z - dz)
            if all(0 <= value < SIZE for value in previous):
                continue
            lines.append(_line((x, y, z), (dx, dy, dz)))
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
    x, z = column
    for y in range(SIZE):
        if board.get((x, y, z), EMPTY) == EMPTY:
            return y
    return SIZE


def _drop(board: dict[Coord, int], column: Column, mark: int) -> Coord | None:
    y = _height(board, column)
    if y >= SIZE:
        return None
    cell = (column[0], y, column[1])
    board[cell] = mark
    return cell


def _copy_board(board: dict[Coord, int]) -> dict[Coord, int]:
    return dict(board)


def _immediate_columns(board: dict[Coord, int], mark: int) -> list[Column]:
    legal = _legal_columns(board)
    if _has_line(board, mark):
        return legal
    landing_cells = {(x, _height(board, (x, z)), z) for x, z in legal}
    winning = set()
    for line in ALL_LINES:
        missing = [cell for cell in line if board.get(cell, EMPTY) != mark]
        if len(missing) == 1 and missing[0] in landing_cells:
            winning.add((missing[0][0], missing[0][2]))
    return [column for column in legal if column in winning]


def _opponent_column(board: dict[Coord, int], pressure_columns: list[Column], pressure_index: int, policy: str = "threat_then_block") -> tuple[Column | None, int]:
    own_wins = _immediate_columns(board, OPPONENT)
    if own_wins:
        return own_wins[0], pressure_index
    player_wins = _immediate_columns(board, PLAYER) if policy == "threat_then_block" else []
    if player_wins:
        return player_wins[0], pressure_index
    legal = set(_legal_columns(board))
    for offset in range(len(pressure_columns)):
        column = pressure_columns[(pressure_index + offset) % len(pressure_columns)]
        if column in legal:
            return column, pressure_index + offset + 1
    return (next((column for column in _legal_columns(board) if column in legal), None), pressure_index + 1)


def _solution_moves(
    initial: dict[Coord, int],
    pressure_columns: list[Column],
    max_moves: int,
    target_lines: list[list[Coord]],
    policy: str = "threat_then_block",
) -> list[Column]:
    target_columns = {(x, z) for line in target_lines for x, _, z in line}
    queue = deque([(initial, 0, [], 0)])
    visited: set[tuple[tuple[tuple[int, int, int], int], int]] = set()
    while queue:
        board, pressure_index, moves, depth = queue.popleft()
        if depth >= max_moves:
            continue
        legal = _legal_columns(board)
        forced = _immediate_columns(board, OPPONENT)
        preferred = [column for column in legal if column in target_columns]
        candidates = list(dict.fromkeys(forced + preferred)) or legal
        for column in candidates:
            next_board = _copy_board(board)
            placed = _drop(next_board, column, PLAYER)
            if placed is None:
                continue
            next_moves = moves + [column]
            if _has_line(next_board, PLAYER):
                return next_moves
            opponent_column, next_pressure = _opponent_column(next_board, pressure_columns, pressure_index, policy)
            if opponent_column is None:
                continue
            _drop(next_board, opponent_column, OPPONENT)
            if _has_line(next_board, OPPONENT):
                continue
            signature = (tuple(sorted(next_board.items())), next_pressure)
            if signature in visited:
                continue
            visited.add(signature)
            queue.append((next_board, next_pressure, next_moves, depth + 1))
    raise RuntimeError("pearl lattice generator could not find a winning continuation")


def _build_board(parameters: dict[str, Any], seed: str) -> tuple[dict[Coord, int], list[list[Coord]], list[Coord], list[Column], list[Column]]:
    targets, opponent_line = _layout(parameters, seed)
    target_cells = {cell for line in targets for cell in line}
    opponent_cells = set(opponent_line)
    shared = targets[0][0]
    if shared != opponent_line[0] or target_cells & opponent_cells - {shared}:
        raise RuntimeError("pearl lattice layout has inconsistent shared lines")
    prefill = int(parameters["prefill_player"])
    roles: dict[Coord, int] = {}
    if parameters["geometry"] == "planar_easy":
        prefill = 3
    for line in targets:
        for cell in line[1 : 1 + prefill]:
            roles[cell] = PLAYER
    for cell in opponent_line[1:]:
        roles[cell] = OPPONENT

    support_cells: set[Coord] = set()
    for x, y, z in target_cells | opponent_cells:
        support_cells.update((x, below, z) for below in range(y))
    if target_cells & support_cells or opponent_cells & support_cells:
        raise RuntimeError("pearl lattice line layout violates gravity")

    shared_column = (shared[0], shared[2])
    reserved_columns = {(x, z) for x, _, z in target_cells | opponent_cells}
    noise_rng = random.Random(_seed_int(seed, "noise"))
    desired_noise = int(parameters["extra_noise"])

    def fill(candidate: dict[Coord, int]) -> bool:
        # A support colouring can make the requested fillers impossible. Search
        # a bounded number of distinct partial boards, then resample supports;
        # never silently emit an under-filled configuration.
        visited = set()
        nodes = 0

        def place_noise(remaining: int) -> bool:
            nonlocal nodes
            if remaining == 0:
                return True
            signature = tuple(sorted(candidate.items()))
            if signature in visited or nodes >= 256:
                return False
            visited.add(signature)
            choices = [(column, mark) for column in _legal_columns(candidate)
                       if column not in reserved_columns for mark in (PLAYER, OPPONENT)]
            noise_rng.shuffle(choices)
            for column, mark in choices:
                nodes += 1
                if nodes > 256:
                    return False
                cell = (column[0], _height(candidate, column), column[1])
                candidate[cell] = mark
                shortcut = parameters["geometry"] != "planar_easy" and bool(_immediate_columns(candidate, PLAYER))
                if not _has_line(candidate, mark) and not shortcut and _immediate_columns(candidate, OPPONENT) == [shared_column]:
                    defended = _copy_board(candidate)
                    _drop(defended, shared_column, PLAYER)
                    if not _immediate_columns(defended, OPPONENT) and place_noise(remaining - 1):
                        return True
                candidate.pop(cell)
            return False

        return place_noise(desired_noise)

    ordered_supports = sorted(support_cells, key=lambda item: (item[1], item[2], item[0]))
    board: dict[Coord, int] | None = None
    support_rng = random.Random(_seed_int(seed, "supports"))
    for _attempt in range(4096):
        candidate_board = {
            cell: support_rng.choice((PLAYER, OPPONENT))
            for cell in ordered_supports
        }
        if any(_has_line(candidate_board, mark) for mark in (PLAYER, OPPONENT)):
            continue
        valid = True
        for cell, mark in sorted(roles.items(), key=lambda item: (item[0][1], item[0][2], item[0][0])):
            if cell in candidate_board:
                valid = False
                break
            candidate_board[cell] = mark
            if _has_line(candidate_board, mark):
                valid = False
                break
        if not valid:
            continue
        if _immediate_columns(candidate_board, OPPONENT) != [shared_column]:
            continue
        if parameters["geometry"] != "planar_easy" and _immediate_columns(candidate_board, PLAYER):
            continue
        defense_board = _copy_board(candidate_board)
        if _drop(defense_board, shared_column, PLAYER) is None or _immediate_columns(defense_board, OPPONENT):
            continue
        if not fill(candidate_board):
            continue
        board = candidate_board
        break
    if board is None:
        raise RuntimeError("pearl lattice could not construct safe supports and the exact configured filler count")

    safe_columns = [column for column in _legal_columns(board) if column not in reserved_columns]
    if not safe_columns:
        safe_columns = _legal_columns(board)
    solution = _solution_moves(board, safe_columns, int(parameters["max_player_moves"]), targets, parameters["opponent_policy"])
    return board, targets, opponent_line, safe_columns, solution


def _cells(board: dict[Coord, int]) -> list[dict[str, int]]:
    return [
        {"x": x, "y": y, "z": z, "value": int(board.get((x, y, z), EMPTY))}
        for z in range(SIZE)
        for y in range(SIZE)
        for x in range(SIZE)
    ]


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition, parameters = _condition(task)
    board, targets, opponent_line, pressure_columns, solution_moves = _build_board(parameters, seed)
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|{condition['difficulty']}".encode("utf-8")).hexdigest()[:12]
    rng = random.Random(_seed_int(seed, "presentation"))
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "challenge_id": challenge_id,
        "control_condition": copy.deepcopy(condition),
        "interaction": condition["interaction"],
        "prompt": task.get("natural_language") or task.get("description") or "Complete four pearls in a straight line before the clockwork rival.",
        "description": task.get("description") or "A transparent 4×4×4 pearl lattice uses gravity-filled columns and straight volumetric lines.",
        "submit_label": "CERTIFY WIN",
        "asset_manifest": "shared_runtime/assets/provenance/pearl_lattice_v0.json",
        "generator": {"name": "pearl_lattice_4x4x4_v1", "variant_count": 4**20},
        "world": {
            "size": SIZE,
            "cells": _cells(board),
            "initial_yaw": rng.randrange(0, 360),
            "tilt": 0.55,
            "rotation_rate": float(parameters["rotation_rate"]),
            "rotation_step_degrees": float(parameters["rotation_step_degrees"]),
            "preview_label_detail": parameters["preview_label_detail"],
            "max_player_moves": int(parameters["max_player_moves"]),
            "gravity_axis": "y",
            "palette": rng.randrange(6),
        },
        "rules": {
            "dimension": "4×4×4",
            "placement": "Pearls fall to the lowest free cell in a selected (x,z) column.",
            "cycle": "Click the lattice surface to cycle the preview through legal columns.",
            "confirm": "Click the separate confirmation area below the lattice to commit the preview.",
            "opponent": ("The rival takes an immediate win, otherwise plays its pressure routine; it does not block your threats." if parameters["opponent_policy"] == "win_then_pressure" else "The rival takes an immediate win, otherwise blocks your next winning column before playing its pressure routine."),
            "rotation": "The automatic turn advances in the configured visible degree steps.",
            "move_limit": f"The player may make at most {int(parameters['max_player_moves'])} placements before certification.",
        },
        "opponent": {
            "name": "CLOCKWORK RIVAL",
            "response": "after each confirmed placement",
            "pressure_columns": [[x, z] for x, z in pressure_columns],
        },
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "seed": seed,
        "challenge_id": challenge_id,
        "control_condition": copy.deepcopy(condition),
        "parameters": copy.deepcopy(parameters),
        "initial_board": {"%d,%d,%d" % cell: value for cell, value in board.items()},
        "target_lines": [[[x, y, z] for x, y, z in line] for line in targets],
        "opponent_line": [[x, y, z] for x, y, z in opponent_line],
        "pressure_columns": [[x, z] for x, z in pressure_columns],
        "solution_moves": [[x, z] for x, z in solution_moves],
        "variant_count": 4**20,
    }
    return public_state, ground_truth
