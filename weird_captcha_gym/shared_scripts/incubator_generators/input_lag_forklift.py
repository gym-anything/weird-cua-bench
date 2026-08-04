from __future__ import annotations

from collections import deque
import copy
import heapq
import hashlib
import itertools
import random
from typing import Any


MECHANIC_ID = "input_lag_forklift"
WIDTH = 9
HEIGHT = 7
DIRECTIONS: tuple[tuple[str, tuple[int, int]], ...] = (
    ("UP", (0, -1)),
    ("RIGHT", (1, 0)),
    ("DOWN", (0, 1)),
    ("LEFT", (-1, 0)),
)
TRANSFORMS = ("identity", "mirror_x", "mirror_y", "rotate_180")
PALETTES = ("amber", "oxide", "mint", "cobalt")
LAYOUTS: tuple[dict[str, Any], ...] = (
    {"player": (3, 2), "crates": ((4, 1), (4, 4)), "goals": ((7, 3), (6, 1)), "racks": ((4, 2), (5, 3), (7, 5))},
    {"player": (5, 1), "crates": ((6, 2), (6, 3)), "goals": ((2, 3), (1, 3)), "racks": ((2, 2), (3, 3), (4, 3))},
    {"player": (1, 2), "crates": ((6, 4), (2, 2)), "goals": ((1, 5), (7, 2)), "racks": ((1, 1), (2, 3), (3, 5), (4, 5), (6, 1), (7, 3))},
    {"player": (4, 5), "crates": ((6, 2), (2, 3)), "goals": ((7, 5), (5, 3)), "racks": ((1, 3), (2, 5), (4, 1), (4, 2))},
    {"player": (7, 3), "crates": ((6, 2), (2, 3)), "goals": ((1, 5), (5, 1)), "racks": ((1, 3), (3, 1), (5, 5), (7, 2))},
    {"player": (7, 5), "crates": ((6, 3), (2, 3)), "goals": ((3, 2), (4, 4)), "racks": ((1, 1), (2, 1), (2, 2), (4, 3), (6, 4))},
    {"player": (7, 4), "crates": ((4, 2), (3, 2)), "goals": ((5, 2), (7, 1)), "racks": ((1, 4), (4, 1), (6, 1), (6, 4))},
    {"player": (4, 3), "crates": ((3, 5), (3, 4)), "goals": ((7, 5), (7, 2)), "racks": ((1, 3), (3, 3), (4, 2), (5, 2), (5, 3), (6, 2))},
    {"player": (1, 1), "crates": ((6, 2), (6, 4)), "goals": ((1, 3), (2, 5)), "racks": ((1, 5), (2, 2), (4, 3), (7, 1))},
    {"player": (5, 5), "crates": ((2, 3), (4, 2)), "goals": ((2, 1), (7, 4)), "racks": ((1, 1), (2, 4), (5, 2), (6, 3))},
    {"player": (7, 3), "crates": ((2, 3), (2, 4)), "goals": ((3, 5), (4, 1)), "racks": ((1, 1), (2, 1), (3, 1), (3, 3), (6, 2), (6, 5))},
    {"player": (5, 4), "crates": ((1, 4), (2, 3)), "goals": ((1, 3), (6, 5)), "racks": ((3, 3), (4, 4), (5, 3), (7, 2))},
)

CONTROLLED_LAYOUTS: dict[int, tuple[dict[str, Any], ...]] = {
    1: (
        {"player": (2, 2), "crates": ((4, 1),), "goals": ((2, 1),), "racks": ((5, 3),)},
        {"player": (3, 3), "crates": ((2, 2),), "goals": ((4, 1),), "racks": ((4, 3),)},
        {"player": (5, 2), "crates": ((3, 2),), "goals": ((3, 1),), "racks": ((4, 3),)},
        {"player": (4, 3), "crates": ((4, 2),), "goals": ((5, 1),), "racks": ((3, 1),)},
        {"player": (2, 3), "crates": ((4, 2),), "goals": ((1, 3),), "racks": ((1, 1),)},
    ),
    2: (
        {"player": (4, 2), "crates": ((5, 2),), "goals": ((3, 3),), "racks": ((2, 2), (6, 2))},
        {"player": (5, 2), "crates": ((2, 2),), "goals": ((6, 4),), "racks": ((2, 4), (1, 4))},
        {"player": (6, 3), "crates": ((2, 3),), "goals": ((5, 2),), "racks": ((6, 1), (5, 4))},
        {"player": (2, 1), "crates": ((5, 3),), "goals": ((1, 4),), "racks": ((2, 3), (4, 3))},
        {"player": (2, 1), "crates": ((5, 2),), "goals": ((1, 3),), "racks": ((6, 3), (3, 4))},
    ),
    3: (
        {"player": (5, 4), "crates": ((4, 2), (6, 4)), "goals": ((3, 5), (7, 5)), "racks": ((5, 3), (5, 5), (3, 1), (2, 2))},
        {"player": (6, 1), "crates": ((3, 3), (4, 3)), "goals": ((2, 1), (7, 2)), "racks": ((6, 2), (5, 4), (7, 1), (4, 5))},
        {"player": (5, 4), "crates": ((2, 2), (6, 4)), "goals": ((2, 1), (2, 3)), "racks": ((1, 5), (2, 5), (7, 5), (5, 5))},
        {"player": (7, 4), "crates": ((2, 2), (6, 3)), "goals": ((6, 1), (3, 4)), "racks": ((3, 1), (4, 5), (5, 5), (1, 4))},
        {"player": (3, 4), "crates": ((5, 2), (4, 3)), "goals": ((5, 5), (2, 4)), "racks": ((1, 2), (5, 3), (7, 2), (6, 5))},
    ),
    5: (
        {"player": (2, 6), "crates": ((7, 4), (3, 3), (5, 3)), "goals": ((7, 5), (8, 2), (8, 5)), "racks": ((4, 2), (9, 3), (7, 6), (5, 2), (3, 4), (7, 2), (1, 4)), "solution": ("UP", "RIGHT", "RIGHT", "UP", "UP", "RIGHT", "RIGHT", "RIGHT", "DOWN", "LEFT", "DOWN", "LEFT", "LEFT", "LEFT", "LEFT", "UP", "UP", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "UP", "UP", "RIGHT", "RIGHT", "DOWN", "DOWN", "DOWN", "LEFT", "LEFT", "UP", "RIGHT", "DOWN", "RIGHT", "UP")},
        {"player": (6, 7), "crates": ((6, 3), (6, 6), (6, 4)), "goals": ((3, 1), (1, 2), (2, 5)), "racks": ((5, 7), (9, 5), (5, 4), (1, 1), (4, 2), (2, 3), (1, 6)), "solution": ("UP", "RIGHT", "UP", "LEFT", "LEFT", "LEFT", "DOWN", "LEFT", "UP", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "UP", "UP", "LEFT", "LEFT", "LEFT", "DOWN", "LEFT", "LEFT", "DOWN", "LEFT", "UP", "UP", "DOWN", "RIGHT", "RIGHT", "UP", "UP", "DOWN", "RIGHT", "RIGHT", "RIGHT", "DOWN", "RIGHT", "DOWN", "LEFT", "LEFT", "LEFT", "LEFT")},
    ),
}


def _transform(point: tuple[int, int], variant: str, width: int = WIDTH, height: int = HEIGHT) -> tuple[int, int]:
    x, y = point
    if variant == "mirror_x":
        return width - 1 - x, y
    if variant == "mirror_y":
        return x, height - 1 - y
    if variant == "rotate_180":
        return width - 1 - x, height - 1 - y
    return x, y


def _initial_layout(
    layout_index: int,
    variant: str,
    *,
    layouts: tuple[dict[str, Any], ...] = LAYOUTS,
    width: int = WIDTH,
    height: int = HEIGHT,
) -> dict[str, Any]:
    outer = {
        (x, y)
        for y in range(height)
        for x in range(width)
        if x in {0, width - 1} or y in {0, height - 1}
    }
    template = layouts[layout_index]
    walls = outer | set(template["racks"])
    player = template["player"]
    crates = tuple(template["crates"])
    goals = tuple(template["goals"])
    return {
        "width": width,
        "height": height,
        "player": list(_transform(player, variant, width, height)),
        "crates": [list(_transform(point, variant, width, height)) for point in crates],
        "goals": [list(_transform(point, variant, width, height)) for point in goals],
        "walls": [list(point) for point in sorted(_transform(point, variant, width, height) for point in walls)],
    }


def _transform_solution(solution: tuple[str, ...], variant: str) -> list[str]:
    mapping = {
        "identity": {},
        "mirror_x": {"LEFT": "RIGHT", "RIGHT": "LEFT"},
        "mirror_y": {"UP": "DOWN", "DOWN": "UP"},
        "rotate_180": {"LEFT": "RIGHT", "RIGHT": "LEFT", "UP": "DOWN", "DOWN": "UP"},
    }[variant]
    return [mapping.get(command, command) for command in solution]


def _step(
    player: tuple[int, int],
    crates: tuple[tuple[int, int], ...],
    walls: frozenset[tuple[int, int]],
    direction: str,
) -> tuple[tuple[int, int], tuple[tuple[int, int], ...]] | None:
    delta = dict(DIRECTIONS).get(direction)
    if delta is None:
        return None
    target = (player[0] + delta[0], player[1] + delta[1])
    crate_set = set(crates)
    if target in walls:
        return None
    if target not in crate_set:
        return target, crates
    beyond = (target[0] + delta[0], target[1] + delta[1])
    if beyond in walls or beyond in crate_set:
        return None
    crate_set.remove(target)
    crate_set.add(beyond)
    return target, tuple(sorted(crate_set))


def _solve(layout: dict[str, Any]) -> list[str]:
    player = tuple(int(value) for value in layout["player"])
    crates = tuple(sorted(tuple(int(value) for value in point) for point in layout["crates"]))
    walls = frozenset(tuple(int(value) for value in point) for point in layout["walls"])
    goals = frozenset(tuple(int(value) for value in point) for point in layout["goals"])
    goal_points = tuple(goals)

    def remaining_distance(current: tuple[tuple[int, int], ...]) -> int:
        return min(
            sum(abs(crate[0] - goal[0]) + abs(crate[1] - goal[1]) for crate, goal in zip(current, order))
            for order in itertools.permutations(goal_points)
        )

    queue: list[tuple[int, int, tuple[str, ...], tuple[int, int], tuple[tuple[int, int], ...]]] = [
        (remaining_distance(crates), 0, (), player, crates)
    ]
    best = {(player, crates): 0}
    while queue:
        _estimate, cost, path, current_player, current_crates = heapq.heappop(queue)
        if cost != best.get((current_player, current_crates)):
            continue
        if set(current_crates) == goals:
            return list(path)
        crate_set = set(current_crates)
        reachable: dict[tuple[int, int], tuple[str, ...]] = {current_player: ()}
        walking = deque([current_player])
        while walking:
            point = walking.popleft()
            for direction, delta in DIRECTIONS:
                target = (point[0] + delta[0], point[1] + delta[1])
                if target in walls or target in crate_set or target in reachable:
                    continue
                reachable[target] = reachable[point] + (direction,)
                walking.append(target)
        for crate in current_crates:
            for direction, delta in DIRECTIONS:
                behind = (crate[0] - delta[0], crate[1] - delta[1])
                beyond = (crate[0] + delta[0], crate[1] + delta[1])
                if behind not in reachable or beyond in walls or beyond in crate_set:
                    continue
                next_crates = tuple(sorted((crate_set - {crate}) | {beyond}))
                next_player = crate
                next_path = path + reachable[behind] + (direction,)
                next_cost = len(next_path)
                state = (next_player, next_crates)
                if next_cost >= best.get(state, 1 << 60):
                    continue
                best[state] = next_cost
                heapq.heappush(
                    queue,
                    (next_cost + remaining_distance(next_crates), next_cost, next_path, next_player, next_crates),
                )
    raise ValueError("generated forklift warehouse is not solvable")


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    digest = hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    condition = task.get("_control_condition")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    level = int((condition or {}).get("difficulty", 4))
    layouts = LAYOUTS if level == 4 else CONTROLLED_LAYOUTS[level]
    width = int(parameters.get("board_width", WIDTH))
    height = int(parameters.get("board_height", HEIGHT))
    layout_index = rng.randrange(len(layouts))
    transform = TRANSFORMS[rng.randrange(len(TRANSFORMS))]
    palette = PALETTES[rng.randrange(len(PALETTES))]
    layout = _initial_layout(layout_index, transform, layouts=layouts, width=width, height=height)
    authored_solution = layouts[layout_index].get("solution")
    solution = _transform_solution(tuple(authored_solution), transform) if authored_solution else _solve(layout)
    task_id = str(task.get("id") or "input_lag_forklift_seed_0001@0.1")
    condition_token = f"|d{level}|{task_id}" if condition else ""
    challenge_id = hashlib.sha256(f"{seed}|input-lag-forklift{condition_token}".encode("utf-8")).hexdigest()[:12]
    control_lag = int(parameters.get("control_lag", 1))
    queue_visibility = str(parameters.get("queue_visibility", "directions"))
    variant_count = len(layouts) * len(TRANSFORMS) * len(PALETTES)
    if control_lag == 1:
        direction_rule = "A direction executes the previously queued direction, then enters the queue."
        flush_rule = "EXECUTE QUEUE runs the pending direction without adding another."
    else:
        direction_rule = (
            f"A direction executes the direction queued {control_lag} inputs earlier, then enters the queue."
        )
        flush_rule = "EXECUTE QUEUE runs the oldest queued direction without adding another."
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Dock both crates. Every direction executes one command late.",
        "submit_label": "CERTIFY LOAD",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_puzzles_v1.json",
        "generator": {
            "name": "input_lag_forklift_v2",
            "variant_count": variant_count,
        },
        "warehouse": layout,
        "control_lag": control_lag,
        "palette": palette,
        "rules": {
            "direction": direction_rule,
            "flush": flush_rule,
            "reset": "RECALIBRATE restores the warehouse and clears the queue.",
        },
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "initial_state": layout,
        "control_lag": control_lag,
        "solution": solution,
        "solution_issued_commands": solution + ["FLUSH"] * control_lag,
        "layout_index": layout_index,
        "transform": transform,
        "palette": palette,
        "variant_count": variant_count,
    }
    minimum = int(parameters.get("solution_length_min", 22))
    maximum = int(parameters.get("solution_length_max", 36))
    crate_count = int(parameters.get("crate_count", 2))
    assert minimum <= len(solution) <= maximum
    assert len(layout["crates"]) == len(layout["goals"]) == crate_count
    if condition:
        public_state["queue_visibility"] = queue_visibility
        ground_truth["queue_visibility"] = queue_visibility
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
