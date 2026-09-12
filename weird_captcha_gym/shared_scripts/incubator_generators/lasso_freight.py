from __future__ import annotations

import copy
import hashlib
import random
from collections import deque
from typing import Any


MECHANIC_ID = "lasso_freight"
VARIANT_COUNT = 40
BASELINE_PARAMETERS = {
    "board_width": 16,
    "board_height": 10,
    "cargo_count": 3,
    "pulls_per_cargo": 2,
    "rope_capacity": 88,
    "cargo_x": 4,
}
DELTAS = {
    "N": (0, -1),
    "E": (1, 0),
    "S": (0, 1),
    "W": (-1, 0),
}
NEIGHBOURS = (("N", (0, -1)), ("E", (1, 0)), ("S", (0, 1)), ("W", (-1, 0)))


def _seed_int(seed: str, salt: str) -> int:
    return int(hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).hexdigest()[:16], 16)


def _point(value: tuple[int, int] | list[int]) -> list[int]:
    return [int(value[0]), int(value[1])]


def _snapshot(tug: tuple[int, int], cargo: list[dict[str, Any]], rope: list[tuple[int, int]]) -> dict[str, Any]:
    return {
        "tug": _point(tug),
        "cargo": [
            {"id": str(item["id"]), "position": _point(tuple(item["position"])), "pulls": int(item["pulls"])}
            for item in cargo
        ],
        "rope_path": [_point(point) for point in rope],
        "solved": all(tuple(item["position"]) == tuple(item["pad"]) for item in cargo),
    }


def _append_rope(rope: list[tuple[int, int]], tug: tuple[int, int], capacity: int) -> None:
    rope.append(tug)
    del rope[:-capacity]


def _apply_move(
    tug: tuple[int, int],
    cargo: list[dict[str, Any]],
    rope: list[tuple[int, int]],
    walls: set[tuple[int, int]],
    width: int,
    height: int,
    direction: str,
    capacity: int,
) -> tuple[tuple[int, int], str]:
    dx, dy = DELTAS[direction]
    target = (tug[0] + dx, tug[1] + dy)
    if target in walls or not (0 <= target[0] < width and 0 <= target[1] < height):
        return tug, "blocked_wall"
    if any(tuple(item["position"]) == target for item in cargo):
        return tug, "blocked_cargo"
    tug = target
    _append_rope(rope, tug, capacity)
    return tug, "move"


def _snag(
    tug: tuple[int, int],
    cargo: list[dict[str, Any]],
    rope: list[tuple[int, int]],
) -> tuple[str, str]:
    occupied = set(rope)
    for item in cargo:
        position = tuple(item["position"])
        pad = tuple(item["pad"])
        if position == pad:
            continue
        required = {(position[0] + dx, position[1] + dy) for _, (dx, dy) in NEIGHBOURS}
        if not required <= occupied:
            continue
        nx, ny = position
        if nx != pad[0]:
            nx += 1 if pad[0] > nx else -1
        elif ny != pad[1]:
            ny += 1 if pad[1] > ny else -1
        item["position"] = [nx, ny]
        item["pulls"] = int(item["pulls"]) + 1
        return str(item["id"]), "snag"
    return "", "lasso_empty"


def _walk_route(
    start: tuple[int, int],
    goal: tuple[int, int],
    cargo: list[dict[str, Any]],
    walls: set[tuple[int, int]],
    width: int,
    height: int,
) -> list[str]:
    blocked = walls | {tuple(item["position"]) for item in cargo}
    queue: deque[tuple[tuple[int, int], tuple[str, ...]]] = deque([(start, ())])
    seen = {start}
    while queue:
        position, path = queue.popleft()
        if position == goal:
            return list(path)
        for direction, (dx, dy) in NEIGHBOURS:
            candidate = (position[0] + dx, position[1] + dy)
            if not (0 <= candidate[0] < width and 0 <= candidate[1] < height):
                continue
            if candidate in blocked or candidate in seen:
                continue
            seen.add(candidate)
            queue.append((candidate, path + (direction,)))
    raise ValueError(f"no walking route to lasso staging tile {goal}")


def _plan(
    tug: tuple[int, int],
    cargo: list[dict[str, Any]],
    walls: set[tuple[int, int]],
    width: int,
    height: int,
    capacity: int,
    pulls_per_cargo: int,
) -> list[str]:
    rope = [tug]
    commands: list[str] = []
    for item in cargo:
        for _ in range(pulls_per_cargo):
            position = tuple(item["position"])
            staging = [
                (position[0], position[1] - 1),
                (position[0] + 1, position[1]),
                (position[0], position[1] + 1),
                (position[0] - 1, position[1]),
            ]
            for target in staging:
                segment = _walk_route(tug, target, cargo, walls, width, height)
                for direction in segment:
                    tug, outcome = _apply_move(tug, cargo, rope, walls, width, height, direction, capacity)
                    if outcome != "move":
                        raise ValueError("generated lasso route contains an illegal walk")
                    commands.append(direction)
            if not all(target in set(rope) for target in staging):
                raise ValueError("generated rope never encloses cargo")
            cargo_id, outcome = _snag(tug, cargo, rope)
            if not cargo_id or outcome != "snag":
                raise ValueError("generated lasso route contains an empty snag")
            commands.append("LASSO")
    return commands


def _walls(width: int, height: int, level: int, rng: random.Random, cargo: list[dict[str, Any]], start: tuple[int, int]) -> set[tuple[int, int]]:
    walls = {
        (x, y)
        for x in range(width)
        for y in range(height)
        if x in {0, width - 1} or y in {0, height - 1}
    }
    # The fenced lanes are visual landmarks and genuine obstacles. Keep one
    # broad opening around each freight lane so the generated BFS route is
    # the same route a player can discover from the screenshot.
    if level >= 4:
        for x in (2, width - 4):
            for y in range(1, height - 1):
                if y % 3 != 0:
                    walls.add((x, y))
    forbidden = {tuple(start)} | {tuple(item["position"]) for item in cargo} | {tuple(item["pad"]) for item in cargo}
    return walls - forbidden


def _layout(level: int, parameters: dict[str, Any], rng: random.Random) -> tuple[dict[str, Any], list[str]]:
    width = int(parameters["board_width"])
    height = int(parameters["board_height"])
    count = int(parameters["cargo_count"])
    pulls = int(parameters["pulls_per_cargo"])
    capacity = int(parameters["rope_capacity"])
    x = int(parameters.get("cargo_x", 4)) + rng.randrange(2)
    rows = list(range(2, height - 1, 2))
    if count == 1:
        rows = [height // 2]
    elif len(rows) < count:
        rows = list(range(1, height - 1))
    rows = rows[:count]
    start = (1, 1)
    cargo = [
        {"id": f"cargo-{index + 1}", "position": [x, y], "pad": [x + pulls, y], "pulls": 0}
        for index, y in enumerate(rows)
    ]
    walls = _walls(width, height, level, rng, cargo, start)
    # A retry with a plain yard is preferable to emitting an unreachable
    # challenge when a seeded fence intersects a small profile.
    try:
        solution = _plan(start, copy.deepcopy(cargo), walls, width, height, capacity, pulls)
    except ValueError:
        walls = {
            (xx, yy)
            for xx in range(width)
            for yy in range(height)
            if xx in {0, width - 1} or yy in {0, height - 1}
        }
        solution = _plan(start, copy.deepcopy(cargo), walls, width, height, capacity, pulls)
    board = {
        "width": width,
        "height": height,
        "start": _point(start),
        "cargo": copy.deepcopy(cargo),
        "walls": [_point(point) for point in sorted(walls)],
        "palette": rng.choice(("copper", "teal", "plum", "ochre")),
    }
    return board, solution


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = copy.deepcopy(task.get("_control_condition"))
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    level = int((condition or {}).get("difficulty", 4))
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    # The uncontrolled seed is the approved baseline: difficulty 4, full
    # keyboard input, live synchronous schedule. Keep the same parameter
    # object for layout and the public contract so baseline state cannot
    # silently diverge from controls.json.
    baseline = parameters or BASELINE_PARAMETERS
    board, solution = _layout(level, baseline, rng)
    if parameters:
        minimum = int(parameters.get("solution_length_min", 1))
        maximum = int(parameters.get("solution_length_max", 1200))
        if not minimum <= len(solution) <= maximum:
            raise ValueError(f"generated lasso route length {len(solution)} is outside {minimum}..{maximum}")
    task_id = str(task.get("id") or "lasso_freight_seed_0001@0.1")
    condition_token = f"|d{level}|{(condition or {}).get('interaction', 'full')}|{task_id}" if condition else ""
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}{condition_token}".encode("utf-8")).hexdigest()[:16]
    task_condition = copy.deepcopy(condition)
    initial_cargo = copy.deepcopy(board["cargo"])
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Loop the rope around every freight crate, then pull it onto its marked pad.",
        "submit_label": "CERTIFY YARD",
        "asset_manifest": "shared_runtime/assets/provenance/lasso_freight_v0.json",
        "generator": {"name": "lasso_freight_v1", "variant_count": VARIANT_COUNT},
        "board": board,
        "rope_capacity": int(baseline["rope_capacity"]),
        "rules": {
            "move": "Arrow keys move the tug one yard tile and add that tile to the trailing rope.",
            "lasso": "SPACE pulls the first unsatisfied crate whose four orthogonal neighbours are in the rope path.",
            "pad": "A crate advances one tile toward its matching pad on each legal snag.",
            "reset": "R resets the yard and clears the rope path.",
        },
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "initial_state": {"board": copy.deepcopy(board), "rope_capacity": public_state["rope_capacity"]},
        "solution": solution,
        "solution_length": len(solution),
        "variant_count": VARIANT_COUNT,
        "control_condition": task_condition,
    }
    if task_condition is None:
        ground_truth.pop("control_condition")
    else:
        public_state["control_condition"] = task_condition
    return public_state, ground_truth
