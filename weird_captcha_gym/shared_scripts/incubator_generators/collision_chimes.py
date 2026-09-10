from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "collision_chimes"
DEFAULT_PARAMETERS: dict[str, Any] = {
    "grid_size": 9,
    "solution_cells": 5,
    "max_cells": 6,
    "beats": 18,
    "beat_ms": 260,
    "minimum_events": 7,
    "minimum_walls": 3,
    "minimum_beats": 6,
    "minimum_collisions": 2,
}

SIDES = ("top", "right", "bottom", "left")
DIRECTION_LABELS = ("up", "right", "down", "left")
DELTAS = ((-1, 0), (0, 1), (1, 0), (0, -1))
PALETTES = (
    {"ink": "#152938", "paper": "#f7f1df", "coral": "#e77858", "mint": "#8fc9bd", "gold": "#e9bd67"},
    {"ink": "#20253d", "paper": "#f5efe5", "coral": "#ed836d", "mint": "#9ab8d5", "gold": "#e5bd69"},
    {"ink": "#1f2b25", "paper": "#f3f0dc", "coral": "#d87564", "mint": "#a8c8a1", "gold": "#e6c27b"},
)


def _seed_int(seed: str) -> int:
    digest = hashlib.sha256(f"{seed}|{MECHANIC_ID}|v3".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _challenge_id(seed: str, parameters: dict[str, Any], condition: dict[str, Any] | None) -> str:
    difficulty = int((condition or {}).get("difficulty", 4))
    normalized = "|".join(f"{key}={parameters[key]}" for key in sorted(parameters))
    raw = f"{seed}|{MECHANIC_ID}|d{difficulty}|{normalized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _normal_cell(cell: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(cell["id"]),
        "row": int(cell["row"]),
        "col": int(cell["col"]),
        "direction": int(cell["direction"]) % 4,
    }


def simulate(cells: list[dict[str, Any]], grid_size: int, beats: int) -> list[dict[str, int | str]]:
    """Replay the visible cellular rules and return only wall events.

    All destinations are decided from the state at the start of a beat. A wall
    impact has priority over a cell encounter. Encountering an occupied start
    square or a duplicate destination leaves a cell in place and turns it
    clockwise. Otherwise it advances one square.
    """
    state = [_normal_cell(cell) for cell in cells]
    events: list[dict[str, int | str]] = []
    for beat in range(1, beats + 1):
        occupied = {(int(cell["row"]), int(cell["col"])) for cell in state}
        proposals: list[tuple[int, int] | None] = []
        for cell in state:
            direction = int(cell["direction"]) % 4
            dr, dc = DELTAS[direction]
            proposals.append((int(cell["row"]) + dr, int(cell["col"]) + dc))
        duplicate_counts: dict[tuple[int, int], int] = {}
        for proposal in proposals:
            if proposal is not None:
                duplicate_counts[proposal] = duplicate_counts.get(proposal, 0) + 1
        next_state: list[dict[str, Any]] = []
        for cell, proposal in zip(state, proposals):
            row = int(cell["row"])
            col = int(cell["col"])
            direction = int(cell["direction"]) % 4
            assert proposal is not None
            next_row, next_col = proposal
            if not (0 <= next_row < grid_size and 0 <= next_col < grid_size):
                side = SIDES[direction]
                slot = col if side in {"top", "bottom"} else row
                events.append({"beat": beat, "side": side, "slot": slot})
                next_state.append({**cell, "direction": (direction + 2) % 4})
            elif proposal in occupied or duplicate_counts.get(proposal, 0) > 1:
                next_state.append({**cell, "direction": (direction + 1) % 4})
            else:
                next_state.append({**cell, "row": next_row, "col": next_col})
        state = next_state
    return events


def _random_cells(rng: random.Random, grid_size: int, count: int) -> list[dict[str, Any]]:
    positions = rng.sample([(row, col) for row in range(grid_size) for col in range(grid_size)], count)
    return [
        {"id": f"c{index}", "row": row, "col": col, "direction": rng.randrange(4)}
        for index, (row, col) in enumerate(positions)
    ]


def _quality(events: list[dict[str, int | str]], parameters: dict[str, Any]) -> bool:
    if len(events) < int(parameters["minimum_events"]):
        return False
    if len({event["side"] for event in events}) < int(parameters["minimum_walls"]):
        return False
    if len({event["beat"] for event in events}) < int(parameters["minimum_beats"]):
        return False
    # Keep the target legible as a sequence rather than a single repeated chime.
    if len({(event["side"], event["slot"]) for event in events}) < max(2, int(parameters["minimum_walls"])):
        return False
    return True


def _collision_count(cells: list[dict[str, Any]], grid_size: int, beats: int) -> int:
    state = [_normal_cell(cell) for cell in cells]
    collisions = 0
    for _beat in range(1, beats + 1):
        occupied = {(int(cell["row"]), int(cell["col"])) for cell in state}
        proposals: list[tuple[int, int]] = []
        for cell in state:
            delta_row, delta_col = DELTAS[int(cell["direction"]) % 4]
            proposals.append((int(cell["row"]) + delta_row, int(cell["col"]) + delta_col))
        duplicate_counts: dict[tuple[int, int], int] = {}
        for proposal in proposals:
            duplicate_counts[proposal] = duplicate_counts.get(proposal, 0) + 1
        next_state: list[dict[str, Any]] = []
        for cell, proposal in zip(state, proposals):
            direction = int(cell["direction"]) % 4
            if not (0 <= proposal[0] < grid_size and 0 <= proposal[1] < grid_size):
                next_state.append({**cell, "direction": (direction + 2) % 4})
            elif proposal in occupied or duplicate_counts[proposal] > 1:
                collisions += 1
                next_state.append({**cell, "direction": (direction + 1) % 4})
            else:
                next_state.append({**cell, "row": proposal[0], "col": proposal[1]})
        state = next_state
    return collisions


def _find_candidate(rng: random.Random, parameters: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, int | str]]]:
    grid_size = int(parameters["grid_size"])
    cell_count = int(parameters["solution_cells"])
    beats = int(parameters["beats"])
    for _ in range(6000):
        cells = _random_cells(rng, grid_size, cell_count)
        events = simulate(cells, grid_size, beats)
        if _quality(events, parameters) and _collision_count(cells, grid_size, beats) >= int(parameters.get("minimum_collisions", 1)):
            return cells, events
    # A deterministic fallback still produces a valid task if a future profile
    # is tightened. Prefer perimeter starts so the target contains visible
    # chimes even when the richness threshold cannot be met.
    cells = [
        {"id": f"c{index}", "row": 0, "col": min(index, grid_size - 1), "direction": 0}
        for index in range(cell_count)
    ]
    return cells, simulate(cells, grid_size, beats)


def _failure_cells(solution: list[dict[str, Any]], grid_size: int, beats: int, target: list[dict[str, int | str]]) -> list[dict[str, Any]]:
    for index in range(len(solution)):
        for delta in (1, 2, 3):
            candidate = copy.deepcopy(solution)
            candidate[index]["direction"] = (int(candidate[index]["direction"]) + delta) % 4
            if simulate(candidate, grid_size, beats) != target:
                return candidate
    candidate = copy.deepcopy(solution)
    candidate[0]["row"] = (int(candidate[0]["row"]) + 1) % grid_size
    return candidate


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = task.get("_control_condition")
    parameters = {**DEFAULT_PARAMETERS, **dict((condition or {}).get("difficulty_parameters") or {})}
    grid_size = int(parameters["grid_size"])
    solution_cells = int(parameters["solution_cells"])
    max_cells = int(parameters["max_cells"])
    beats = int(parameters["beats"])
    beat_ms = int(parameters["beat_ms"])
    if not 5 <= grid_size <= 12:
        raise ValueError("collision-chimes grid must be between five and twelve")
    if not 1 <= solution_cells <= max_cells <= 12:
        raise ValueError("collision-chimes cell counts are inconsistent")
    if not 4 <= beats <= 40 or not 120 <= beat_ms <= 900:
        raise ValueError("collision-chimes timing is outside the supported range")

    rng = random.Random(_seed_int(seed))
    solution, target_events = _find_candidate(rng, parameters)
    failure = _failure_cells(solution, grid_size, beats, target_events)
    palette = copy.deepcopy(PALETTES[rng.randrange(len(PALETTES))])
    challenge_id = _challenge_id(seed, parameters, condition)
    contract = {
        "grid_size": grid_size,
        "beats": beats,
        "beat_ms": beat_ms,
        "max_cells": max_cells,
        "target_events": copy.deepcopy(target_events),
        "direction_labels": list(DIRECTION_LABELS),
        "wall_sides": list(SIDES),
        "palette": palette,
    }
    rules = [
        "Each arrow advances one square per beat.",
        "A wall impact flashes that wall slot and reverses the arrow.",
        "An occupied or duplicate destination turns the arrow clockwise.",
        "All arrows decide from the positions at the start of the beat.",
    ]
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "challenge_id": challenge_id,
        "prompt": "Build a moving chime pattern whose wall flashes match the target sequence.",
        "asset_manifest": "shared_runtime/assets/provenance/collision_chimes_v0.json",
        "generator": {
            "name": "collision_chimes_cellular_reimplementation_v1",
            "variant_count": max(1, grid_size * grid_size * 4) ** solution_cells,
            "source_anchor": "ART-271",
        },
        "contract": contract,
        "rules": rules,
        "control_condition": copy.deepcopy(condition) if condition else None,
    }
    truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "seed": seed,
        "challenge_id": challenge_id,
        "contract": copy.deepcopy(contract),
        "solution_cells": copy.deepcopy(solution),
        "failure_cells": copy.deepcopy(failure),
        "control_condition": copy.deepcopy(condition) if condition else None,
    }
    if condition is None:
        public.pop("control_condition")
        truth.pop("control_condition")
    return public, truth
