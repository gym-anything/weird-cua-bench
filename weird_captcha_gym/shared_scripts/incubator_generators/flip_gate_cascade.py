from __future__ import annotations

import copy
import hashlib
import math
import random
from collections import deque
from typing import Any


MECHANIC_ID = "flip_gate_cascade"
DEFAULTS = {
    "top_chutes": 4,
    "row_count": 3,
    "target_depth": 7,
    "drop_budget": 10,
}
ANIMATION_MS = 900
PALETTES = (
    {"left": "#f1a33b", "right": "#62c6c0", "marble": "#f5d27b"},
    {"left": "#ef745f", "right": "#81b9d8", "marble": "#f2c86c"},
    {"left": "#d89545", "right": "#71b6a2", "marble": "#f0d08c"},
)


def _seed(seed: str) -> int:
    digest = hashlib.sha256(f"{seed}|{MECHANIC_ID}|v2".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def row_offsets(top_chutes: int, row_count: int) -> tuple[int, ...]:
    offsets: list[int] = []
    total = 0
    for row in range(row_count):
        offsets.append(total)
        total += top_chutes + row
    return tuple(offsets)


def transition(
    state: tuple[int, ...],
    chute: int,
    top_chutes: int,
    row_count: int,
    entry_columns: tuple[int, ...] | list[int] | None = None,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    if chute < 0 or chute >= top_chutes:
        raise ValueError("chute outside machine")
    offsets = row_offsets(top_chutes, row_count)
    result = list(state)
    column = int(entry_columns[chute]) if entry_columns is not None else chute
    path: list[int] = []
    for row in range(row_count):
        gate = offsets[row] + column
        path.append(gate)
        points_right = bool(result[gate])
        result[gate] = 0 if points_right else 1
        if points_right:
            column += 1
    return tuple(result), tuple(path)


def _shortest_frontier(
    initial: tuple[int, ...],
    top_chutes: int,
    row_count: int,
    target_depth: int,
    entry_columns: tuple[int, ...] | list[int],
) -> tuple[
    list[tuple[int, ...]],
    dict[tuple[int, ...], tuple[tuple[int, ...], int]],
]:
    distance = {initial: 0}
    parent: dict[tuple[int, ...], tuple[tuple[int, ...], int]] = {}
    queue = deque([initial])
    frontier: list[tuple[int, ...]] = []
    while queue:
        state = queue.popleft()
        depth = distance[state]
        if depth == target_depth:
            frontier.append(state)
            continue
        for chute in range(top_chutes):
            nxt, _ = transition(
                state, chute, top_chutes, row_count, entry_columns
            )
            if nxt in distance:
                continue
            distance[nxt] = depth + 1
            parent[nxt] = (state, chute)
            queue.append(nxt)
    return frontier, parent


def _solution(
    target: tuple[int, ...],
    initial: tuple[int, ...],
    parent: dict[tuple[int, ...], tuple[tuple[int, ...], int]],
) -> list[int]:
    moves: list[int] = []
    state = target
    while state != initial:
        previous, chute = parent[state]
        moves.append(chute)
        state = previous
    moves.reverse()
    return moves


def _failure_sequence(
    initial: tuple[int, ...],
    target: tuple[int, ...],
    top_chutes: int,
    row_count: int,
    budget: int,
    entry_columns: tuple[int, ...] | list[int],
) -> list[int]:
    memo: set[tuple[tuple[int, ...], int]] = set()

    def search(state: tuple[int, ...], remaining: int) -> list[int] | None:
        if remaining == 0:
            return []
        key = (state, remaining)
        if key in memo:
            return None
        memo.add(key)
        for chute in range(top_chutes):
            nxt, _ = transition(
                state, chute, top_chutes, row_count, entry_columns
            )
            if nxt == target:
                continue
            suffix = search(nxt, remaining - 1)
            if suffix is not None:
                return [chute, *suffix]
        return None

    result = search(initial, budget)
    if result is None:
        raise RuntimeError("could not construct an ordinary-input failure sequence")
    return result


def _geometry(top_chutes: int, row_count: int) -> dict[str, Any]:
    offsets = row_offsets(top_chutes, row_count)
    widest = top_chutes + row_count - 1
    spacing = min(112.0, 560.0 / max(1, widest - 1))
    if row_count == 4:
        # Keep the first full-size vane below the sealed manifold.  The generic
        # centering formula begins a four-row lattice at y=120, which places the
        # vane arms beneath the cover ending at y=133.5 including its stroke.
        # L1-L4 retain their original geometry; only the added L5 row needs the
        # denser vertical spacing.
        y_positions = [170.0, 274.0, 378.0, 482.0]
    elif row_count == 1:
        y_positions = [310.0]
    else:
        vertical = min(142.0, 360.0 / (row_count - 1))
        start_y = 300.0 - vertical * (row_count - 1) / 2.0
        y_positions = [start_y + row * vertical for row in range(row_count)]

    gates: list[dict[str, Any]] = []
    for row in range(row_count):
        count = top_chutes + row
        for column in range(count):
            x = 380.0 + (column - (count - 1) / 2.0) * spacing
            gates.append(
                {
                    "id": offsets[row] + column,
                    "row": row,
                    "column": column,
                    "center": [round(x, 3), round(y_positions[row], 3)],
                }
            )
    chutes = []
    for column in range(top_chutes):
        gate = gates[offsets[0] + column]
        chutes.append(
            {
                "id": column,
                "label": chr(ord("A") + column),
                "center": [gate["center"][0], 54.0],
            }
        )
    return {
        "row_offsets": list(offsets),
        "row_counts": [top_chutes + row for row in range(row_count)],
        "gates": gates,
        "chutes": chutes,
    }


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = task.get("_control_condition")
    parameters = {**DEFAULTS, **dict((condition or {}).get("difficulty_parameters") or {})}
    top_chutes = int(parameters["top_chutes"])
    row_count = int(parameters["row_count"])
    target_depth = int(parameters["target_depth"])
    drop_budget = int(parameters["drop_budget"])
    if not 2 <= top_chutes <= 5:
        raise ValueError("flip-gate chute count must be between two and five")
    if not 2 <= row_count <= 4:
        raise ValueError("flip-gate row count must be between two and four")
    if not 1 <= target_depth < drop_budget <= 16:
        raise ValueError("flip-gate depth and budget are inconsistent")

    rng = random.Random(_seed(seed))
    geometry = _geometry(top_chutes, row_count)
    gate_count = len(geometry["gates"])
    entry_columns = list(range(top_chutes))
    while any(chute == column for chute, column in enumerate(entry_columns)):
        rng.shuffle(entry_columns)
    initial = tuple(rng.randrange(2) for _ in range(gate_count))
    frontier, parent = _shortest_frontier(
        initial, top_chutes, row_count, target_depth, entry_columns
    )
    if not frontier:
        raise RuntimeError(f"no flip-gate states at exact depth {target_depth}")
    minimum_distinct = min(top_chutes, 1 if target_depth < 3 else 2 if target_depth < 6 else 3)
    candidates: list[tuple[tuple[int, ...], list[int]]] = []
    for target in frontier:
        solution = _solution(target, initial, parent)
        if len(set(solution)) >= minimum_distinct:
            candidates.append((target, solution))
    if not candidates:
        candidates = [(target, _solution(target, initial, parent)) for target in frontier]
    target, solution = candidates[rng.randrange(len(candidates))]
    palette = copy.deepcopy(PALETTES[rng.randrange(len(PALETTES))])
    challenge_token = f"|d{condition['difficulty']}|{task.get('id')}" if condition else ""
    challenge_id = hashlib.sha256(
        f"{seed}|{MECHANIC_ID}|challenge{challenge_token}".encode()
    ).hexdigest()[:12]
    machine = {
        "top_chutes": top_chutes,
        "row_count": row_count,
        "gate_count": gate_count,
        "gates": geometry["gates"],
        "chutes": geometry["chutes"],
        "row_offsets": geometry["row_offsets"],
        "row_counts": geometry["row_counts"],
        "entry_columns": entry_columns,
        "initial_state": list(initial),
        "target_state": list(target),
        "optimal_depth": target_depth,
        "drop_budget": drop_budget,
        "animation_ms": ANIMATION_MS,
        "palette": palette,
    }
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "challenge_id": challenge_id,
        "prompt": "Inspect the chute mouths, then match every vane to the target before the marble tray is empty.",
        "asset_manifest": "shared_runtime/assets/provenance/flip_gate_cascade_v0.json",
        "generator": {
            "name": "concealed_inlet_rotor_lattice_bfs_v2",
            "frontier_size": len(frontier),
            "candidate_count": len(candidates),
            "variant_count": len(frontier) * (2**gate_count) * math.factorial(top_chutes),
        },
        "machine": machine,
    }
    truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "seed": seed,
        "challenge_id": challenge_id,
        "machine": copy.deepcopy(machine),
        "solution_chutes": solution,
        "failure_chutes": _failure_sequence(
            initial,
            target,
            top_chutes,
            row_count,
            drop_budget,
            entry_columns,
        ),
    }
    if condition:
        public["control_condition"] = copy.deepcopy(condition)
        truth["control_condition"] = copy.deepcopy(condition)
    return public, truth
