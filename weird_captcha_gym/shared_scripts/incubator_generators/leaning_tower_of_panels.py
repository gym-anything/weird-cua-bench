from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from collections import deque
from typing import Any


MECHANIC_ID = "leaning_tower_of_panels"
BASELINE_DIFFICULTY = 4

# Puzzle Tower's original four-floor, six-sided configuration is the reference
# construction.  This benchmark version adds a deterministic scramble, mural
# continuity, and an independently checked shortest-path budget.
DEFAULT_PROFILE = {
    "floor_count": 4,
    "sector_count": 6,
    "visible_arc_degrees": 120,
    "scramble_distance_min": 11,
    "scramble_distance_max": 12,
    "move_allowance": 2,
    "mural_band_count": 2,
}


def _profile(task: dict[str, Any]) -> tuple[dict[str, int], dict[str, Any] | None]:
    condition = task.get("_control_condition")
    if condition is None:
        return dict(DEFAULT_PROFILE), None
    if not isinstance(condition, dict):
        raise ValueError("leaning-tower control condition is malformed")
    raw = condition.get("difficulty_parameters")
    if not isinstance(raw, dict) or set(raw) != set(DEFAULT_PROFILE):
        raise ValueError("leaning-tower difficulty parameters do not match the profile schema")
    try:
        profile = {key: int(raw[key]) for key in DEFAULT_PROFILE}
    except (TypeError, ValueError) as exc:
        raise ValueError("leaning-tower difficulty parameters must be integers") from exc
    if (
        not 2 <= profile["floor_count"] <= 5
        or not 6 <= profile["sector_count"] <= 8
        or not 105 <= profile["visible_arc_degrees"] <= 135
        or not 2 <= profile["scramble_distance_min"] <= profile["scramble_distance_max"] <= 18
        or not 0 <= profile["move_allowance"] <= 6
        or not 1 <= profile["mural_band_count"] <= 3
    ):
        raise ValueError("leaning-tower difficulty profile is outside supported limits")
    return profile, copy.deepcopy(condition)


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _neighbors(blank: int, rows: int, sectors: int) -> tuple[int, ...]:
    row, sector = divmod(blank, sectors)
    result = [row * sectors + (sector - 1) % sectors, row * sectors + (sector + 1) % sectors]
    if row:
        result.append((row - 1) * sectors + sector)
    if row + 1 < rows:
        result.append((row + 1) * sectors + sector)
    return tuple(dict.fromkeys(result))


def _swap(state: tuple[str | None, ...], first: int, second: int) -> tuple[str | None, ...]:
    values = list(state)
    values[first], values[second] = values[second], values[first]
    return tuple(values)


def _shortest_solution(
    start: tuple[str | None, ...],
    goal: tuple[str | None, ...],
    rows: int,
    sectors: int,
) -> list[str]:
    """Return an exact shortest tile-id solution using bidirectional BFS."""

    if start == goal:
        return []
    from_start: dict[tuple[str | None, ...], tuple[tuple[str | None, ...] | None, int | None]] = {
        start: (None, None)
    }
    toward_goal: dict[tuple[str | None, ...], tuple[tuple[str | None, ...] | None, int | None]] = {
        goal: (None, None)
    }
    start_frontier = {start}
    goal_frontier = {goal}
    meeting: tuple[str | None, ...] | None = None

    while start_frontier and goal_frontier and meeting is None:
        if len(start_frontier) <= len(goal_frontier):
            next_frontier: set[tuple[str | None, ...]] = set()
            for state in start_frontier:
                blank = state.index(None)
                for clicked in _neighbors(blank, rows, sectors):
                    child = _swap(state, blank, clicked)
                    if child in from_start:
                        continue
                    from_start[child] = (state, clicked)
                    if child in toward_goal:
                        meeting = child
                        break
                    next_frontier.add(child)
                if meeting is not None:
                    break
            start_frontier = next_frontier
        else:
            next_frontier = set()
            for state in goal_frontier:
                blank = state.index(None)
                for clicked in _neighbors(blank, rows, sectors):
                    child = _swap(state, blank, clicked)
                    if child in toward_goal:
                        continue
                    # In child, the tile that returns to state occupies state's
                    # former blank position.
                    toward_goal[child] = (state, blank)
                    if child in from_start:
                        meeting = child
                        break
                    next_frontier.add(child)
                if meeting is not None:
                    break
            goal_frontier = next_frontier

    if meeting is None:
        raise ValueError("leaning-tower puzzle graph unexpectedly disconnected")

    click_indices: list[int] = []
    cursor = meeting
    reverse_prefix: list[int] = []
    while cursor != start:
        parent, clicked = from_start[cursor]
        if parent is None or clicked is None:
            raise AssertionError("broken start-side BFS chain")
        reverse_prefix.append(clicked)
        cursor = parent
    click_indices.extend(reversed(reverse_prefix))
    cursor = meeting
    while cursor != goal:
        next_state, clicked = toward_goal[cursor]
        if next_state is None or clicked is None:
            raise AssertionError("broken goal-side BFS chain")
        click_indices.append(clicked)
        cursor = next_state

    solution: list[str] = []
    cursor = start
    for clicked in click_indices:
        tile_id = cursor[clicked]
        if tile_id is None:
            raise AssertionError("BFS solution clicked the opening")
        solution.append(tile_id)
        blank = cursor.index(None)
        cursor = _swap(cursor, blank, clicked)
    if cursor != goal:
        raise AssertionError("BFS solution does not reach the target")
    return solution


def _scramble(
    rng: random.Random,
    goal: tuple[str | None, ...],
    rows: int,
    sectors: int,
    minimum: int,
    maximum: int,
) -> tuple[tuple[str | None, ...], list[str]]:
    for attempt in range(280):
        state = goal
        previous_blank: int | None = None
        visited = {goal}
        # A short non-backtracking walk usually has its true distance close to
        # its length.  The small overrun allows cycles without making shallow
        # profiles almost impossible to sample.
        walk_length = rng.randint(minimum, maximum + 3)
        for _ in range(walk_length):
            blank = state.index(None)
            candidates = [item for item in _neighbors(blank, rows, sectors) if item != previous_blank]
            rng.shuffle(candidates)
            clicked = candidates[0]
            for candidate in candidates:
                if _swap(state, blank, candidate) not in visited:
                    clicked = candidate
                    break
            previous_blank = blank
            state = _swap(state, blank, clicked)
            visited.add(state)
        solution = _shortest_solution(state, goal, rows, sectors)
        if minimum <= len(solution) <= maximum:
            return state, solution
    raise ValueError(
        f"could not generate a {minimum}-{maximum} move leaning-tower scramble"
    )


def _fingerprint(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    profile, condition = _profile(task)
    difficulty = int(condition["difficulty"]) if condition is not None else BASELINE_DIFFICULTY
    salt = MECHANIC_ID if difficulty == BASELINE_DIFFICULTY else f"{MECHANIC_ID}|d{difficulty}"
    rng = random.Random(_seed_int(seed, salt))
    rows = profile["floor_count"]
    sectors = profile["sector_count"]
    cell_count = rows * sectors

    tiles: list[dict[str, Any]] = []
    palette_base = rng.randrange(360)
    row_phases = [round(rng.uniform(-math.pi, math.pi), 6) for _ in range(rows)]
    band_phases = [round(rng.uniform(-0.34, 0.34), 6) for _ in range(profile["mural_band_count"])]
    for row in range(rows):
        for sector in range(sectors):
            if row == rows - 1 and sector == sectors - 1:
                continue
            tiles.append(
                {
                    "id": f"panel-{row + 1}-{sector + 1}",
                    "floor": row + 1,
                    "mural_sector": sector,
                    "hue": (palette_base + row * 47 + sector * 7) % 360,
                }
            )
    goal = tuple([tile["id"] for tile in tiles] + [None])
    start, solution = _scramble(
        rng,
        goal,
        rows,
        sectors,
        profile["scramble_distance_min"],
        profile["scramble_distance_max"],
    )
    optimal = len(solution)
    allowed_moves = optimal + profile["move_allowance"]
    task_id = str(task.get("id") or "leaning_tower_of_panels_seed_0001@0.1")
    challenge_id = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).hexdigest()[:12]
    mural = {
        "band_count": profile["mural_band_count"],
        "row_phases": row_phases,
        "band_phases": band_phases,
        "palette_base": palette_base,
    }
    world = {
        "floor_count": rows,
        "sector_count": sectors,
        "visible_arc_degrees": profile["visible_arc_degrees"],
        "tiles": tiles,
        "start_grid": list(start),
        "mural": mural,
        "opening_target_index": cell_count - 1,
        "optimal_move_count": optimal,
        "allowed_moves": allowed_moves,
    }
    public_state: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "world_fingerprint": _fingerprint(world),
        "prompt": task.get("natural_language")
        or "Rotate the tower, restore every numbered mural ring, and leave the opening in the brass foundation bay.",
        "asset_manifest": "shared_runtime/assets/provenance/leaning_tower_of_panels_v0.json",
        "generator": {
            "name": "cylindrical_shortest_path_panels_v1",
            "variant_count": 9_600_000_000,
        },
        **world,
    }
    ground_truth: dict[str, Any] = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "world_fingerprint": public_state["world_fingerprint"],
        **copy.deepcopy(world),
        "goal_grid": list(goal),
        "optimal_solution": solution,
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {
        "optimal_solution": list(ground_truth.get("optimal_solution") or []),
        "optimal_move_count": int(ground_truth.get("optimal_move_count") or 0),
    }
