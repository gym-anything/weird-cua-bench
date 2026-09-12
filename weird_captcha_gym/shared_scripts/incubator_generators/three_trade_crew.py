from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "three_trade_crew"
ROLES = ("fighter", "thief", "wizard")
DIRECTIONS = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}
PALETTES = ("brass-and-ink", "cobalt-workshop", "copper-night", "verdigris-hall")


def _profile(level: int) -> dict[str, Any]:
    profiles = {
        1: {"rows": 9, "columns": 13, "door_count": 0, "gate_scheme": "none", "wall_layout": "open", "top_goal_column": 8, "action_budget": 40, "decoy_switches": 0},
        2: {"rows": 9, "columns": 13, "door_count": 1, "gate_scheme": "shared", "wall_layout": "open", "top_goal_column": 8, "action_budget": 35, "decoy_switches": 0},
        # This is the original authored configuration. Keep it intact at its
        # warranted level instead of adding complexity merely to defend L4.
        3: {"rows": 9, "columns": 13, "door_count": 2, "gate_scheme": "shared", "wall_layout": "lanes", "top_goal_column": 8, "action_budget": 88, "decoy_switches": 2},
        4: {"rows": 9, "columns": 13, "door_count": 2, "gate_scheme": "sequential", "wall_layout": "lanes", "top_goal_column": 9, "action_budget": 27, "decoy_switches": 2},
        5: {"rows": 9, "columns": 13, "door_count": 3, "gate_scheme": "sequential", "wall_layout": "lanes", "top_goal_column": 10, "action_budget": 28, "decoy_switches": 2},
    }
    return copy.deepcopy(profiles.get(int(level), profiles[4]))


def _pos(row: int, column: int) -> list[int]:
    return [int(row), int(column)]


def _occupied(board: dict[str, Any]) -> dict[tuple[int, int], tuple[str, str]]:
    result: dict[tuple[int, int], tuple[str, str]] = {}
    for worker in board["workers"]:
        result[tuple(worker["position"])] = ("worker", worker["id"])
    for crate in board["crates"]:
        result[tuple(crate["position"])] = ("crate", crate["id"])
    return result


def _switch_open(board: dict[str, Any], switch_id: str) -> bool:
    switch = next(item for item in board["switches"] if item["id"] == switch_id)
    point = tuple(switch["position"])
    return any(tuple(item["position"]) == point for item in board["workers"] + board["crates"])


def _passable(board: dict[str, Any], point: tuple[int, int], moving_worker: str | None = None) -> bool:
    row, column = point
    if not 0 <= row < board["rows"] or not 0 <= column < board["columns"]:
        return False
    if point in {tuple(item) for item in board["walls"]}:
        return False
    for door in board["doors"]:
        if tuple(door["position"]) == point and not _switch_open(board, door["switch_id"]):
            return False
    occupied = _occupied(board)
    occupant = occupied.get(point)
    return occupant is None or occupant[0] == "crate" or occupant == ("worker", moving_worker)


def apply_action(board: dict[str, Any], worker_id: str, direction: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if direction not in DIRECTIONS:
        raise ValueError("unknown direction")
    current = copy.deepcopy(board)
    worker = next((item for item in current["workers"] if item["id"] == worker_id), None)
    if worker is None:
        raise ValueError("unknown worker")
    dr, dc = DIRECTIONS[direction]
    old = tuple(worker["position"])
    dest = (old[0] + dr, old[1] + dc)
    if not _passable(current, dest, worker_id):
        raise ValueError("worker hit a wall or a closed gate")
    occupied = _occupied(current)
    occupant = occupied.get(dest)
    crate = next((item for item in current["crates"] if tuple(item["position"]) == dest), None)
    ability = "move"
    crate_id: str | None = None
    if occupant and occupant[0] == "worker":
        raise ValueError("workers cannot share a bay")
    if crate is not None:
        crate_id = crate["id"]
        if worker["role"] == "fighter":
            beyond = (dest[0] + dr, dest[1] + dc)
            if not _passable(current, beyond, worker_id) or beyond in _occupied(current):
                raise ValueError("fighter cannot push the crate")
            crate["position"] = _pos(*beyond)
            ability = "push"
        elif worker["role"] in {"thief", "wizard"}:
            crate["position"] = _pos(*old)
            ability = "pull" if worker["role"] == "thief" else "swap"
    elif worker["role"] == "thief":
        behind = (old[0] - dr, old[1] - dc)
        trailing = next((item for item in current["crates"] if tuple(item["position"]) == behind), None)
        if trailing is not None:
            trailing["position"] = _pos(*old)
            crate_id = trailing["id"]
            ability = "pull"
    worker["position"] = _pos(*dest)
    return current, {
        "worker_id": worker_id,
        "direction": direction,
        "from": list(old),
        "to": list(dest),
        "ability": ability,
        "crate_id": crate_id,
        "door_states": {door["id"]: _switch_open(current, door["switch_id"]) for door in current["doors"]},
        "workers_after": copy.deepcopy(current["workers"]),
        "crates_after": copy.deepcopy(current["crates"]),
    }


def _make_board(params: dict[str, Any], variant_index: int = 0) -> dict[str, Any]:
    rows, columns = int(params["rows"]), int(params["columns"])
    offset = int(variant_index) % 2

    def shifted(row: int, column: int) -> list[int]:
        return _pos(row, column + offset)

    walls: list[list[int]] = []
    for row in range(rows):
        for column in range(columns):
            if row in {0, rows - 1} or column in {0, columns - 1}:
                walls.append(_pos(row, column))
    if params["wall_layout"] == "lanes":
        # The second seeded layout is not a translation of the first: its
        # vertical lane opening is staggered to column 5 while its Thief
        # starts one square earlier and handles a different crate alignment.
        opening = 6 if offset == 0 else 5
        for row in (1, 3, 5, 7):
            for column in range(1, columns - 1):
                if column != opening:
                    walls.append(_pos(row, column))
    switches = [
        {"id": "switch-yellow", "label": "YELLOW", "color": "yellow", "position": shifted(2, 6)},
    ]
    if params["gate_scheme"] == "sequential" and int(params["door_count"]) >= 2:
        switches.append({"id": "switch-purple", "label": "PURPLE", "color": "purple", "position": shifted(6, 6)})
    if int(params["door_count"]) >= 3:
        switches.append({"id": "switch-cyan", "label": "CYAN", "color": "cyan", "position": shifted(6, 9)})
    for index in range(int(params.get("decoy_switches", 0))):
        switches.append({"id": f"switch-decoy-{index + 1}", "label": "DECOY", "color": "purple", "position": shifted(2 if index % 2 == 0 else 6, 2 + index * 2)})
    door_specs = [
        ("door-yellow-middle", "YELLOW", "yellow", shifted(4, 7), "switch-yellow"),
        ("door-yellow-bottom", "PURPLE" if params["gate_scheme"] == "sequential" else "YELLOW", "purple" if params["gate_scheme"] == "sequential" else "yellow", shifted(6, 7), "switch-purple" if params["gate_scheme"] == "sequential" else "switch-yellow"),
        ("door-cyan-top", "CYAN", "cyan", shifted(2, 8), "switch-cyan"),
    ]
    doors = [
        {"id": item[0], "label": item[1], "color": item[2], "position": item[3], "switch_id": item[4]}
        for item in door_specs[: int(params["door_count"])]
    ]
    workers = [
        {"id": "fighter", "role": "fighter", "label": "FIGHTER", "color": "#e76f51", "position": shifted(2, 1)},
        {"id": "thief", "role": "thief", "label": "THIEF", "color": "#55b88b", "position": _pos(4, 4) if offset == 0 else _pos(4, 3)},
        {"id": "wizard", "role": "wizard", "label": "WIZARD", "color": "#5d8de8", "position": shifted(6, 2)},
    ]
    crates = [
        {"id": "crate-f", "label": "BRASS CRATE", "color": "#d59b50", "position": shifted(2, 3)},
        {"id": "crate-t", "label": "GLASS CRATE", "color": "#a5d6cf", "position": _pos(4, 5) if offset == 0 else _pos(4, 4)},
        {"id": "crate-w", "label": "BLUE CRATE", "color": "#7897e7", "position": shifted(6, 3)},
    ]
    goals = [
        {"worker_id": "fighter", "label": "F", "position": shifted(2, int(params["top_goal_column"])) if offset == 0 else _pos(2, int(params["top_goal_column"]))},
        {"worker_id": "thief", "label": "T", "position": _pos(4, 10) if offset == 0 else _pos(4, 11)},
        {"worker_id": "wizard", "label": "W", "position": shifted(6, 10)},
    ]
    board = {
        "rows": rows,
        "columns": columns,
        "walls": walls,
        "doors": doors,
        "switches": switches,
        "workers": workers,
        "crates": crates,
        "goals": goals,
        "variant_offset": offset,
        "variant_layout": "baseline-lanes" if offset == 0 else "staggered-lanes",
    }
    return board


def _solution(board: dict[str, Any], params: dict[str, Any]) -> list[dict[str, Any]]:
    current = copy.deepcopy(board)
    actions: list[dict[str, Any]] = []

    def do(worker: str, direction: str) -> None:
        nonlocal current
        current, info = apply_action(current, worker, direction)
        actions.append(info)

    for _ in range(5):
        do("fighter", "right")
    if int(board.get("variant_offset", 0)) == 1:
        do("thief", "left")
        for _ in range(9):
            do("thief", "right")
    else:
        for direction in ("left", "left", "right", "right", "right", "right"):
            do("thief", direction)
        for _ in range(4):
            do("thief", "right")
    if int(params["door_count"]) >= 3:
        for _ in range(7):
            do("wizard", "right")
        fighter = next(item for item in current["workers"] if item["id"] == "fighter")
        fighter_goal = next(item for item in current["goals"] if item["worker_id"] == "fighter")
        for _ in range(int(fighter_goal["position"][1]) - int(fighter["position"][1])):
            do("fighter", "right")
        do("wizard", "right")
    else:
        for _ in range(8):
            do("wizard", "right")
        fighter = next(item for item in current["workers"] if item["id"] == "fighter")
        fighter_goal = next(item for item in current["goals"] if item["worker_id"] == "fighter")
        for _ in range(int(fighter_goal["position"][1]) - int(fighter["position"][1])):
            do("fighter", "right")
    return actions


def _solved(board: dict[str, Any]) -> bool:
    return all(tuple(worker["position"]) == tuple(next(goal["position"] for goal in board["goals"] if goal["worker_id"] == worker["id"])) for worker in board["workers"])


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = copy.deepcopy(task.get("_control_condition"))
    difficulty = int((condition or {}).get("difficulty") or 4)
    params = _profile(difficulty)
    digest = hashlib.sha256(f"{seed}|{MECHANIC_ID}|v4|d{difficulty}".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    variant_index = int.from_bytes(digest[8:12], "big") % 2
    board = _make_board(params, variant_index)
    solution = _solution(board, params)
    if not _solved(replay_solution(board, solution)):
        raise ValueError("authored crew route did not reach all exit bays")
    task_id = str(task.get("id") or "three_trade_crew_seed_0001@0.1")
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|v4|d{difficulty}|v{variant_index}|{task_id}".encode("utf-8")).hexdigest()[:12]
    palette = PALETTES[rng.randrange(len(PALETTES))]
    parameters = copy.deepcopy(params)
    prompt = "Park the fighter, thief, and wizard in their matching exit bays. Their different crate tricks and the held switches are the only way through the workshop."
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": prompt,
        "asset_manifest": "shared_runtime/assets/provenance/three_trade_crew_v0.json",
        "palette": palette,
        "board": copy.deepcopy(board),
        "parameters": parameters,
        "rule": {
            "fighter": "steps into a crate and pushes it one square",
            "thief": "moves away from a crate to pull it, or pulls through an adjacent crate",
            "wizard": "exchanges places with an adjacent crate",
            "switches": "a worker or crate standing on a coloured switch holds its paired doors open",
            "goal": "every worker must occupy its matching marked exit bay",
        },
        "controls": {
            "full": "arrow keys move the selected worker; 1/2/3 or X selects a worker",
            "simplified": "click a worker card, then a labelled direction button",
        },
        "variant_count": len(PALETTES) * 2,
        "variant_count_kind": "two validated workshop layouts with distinct lane openings and routes × four visual palettes",
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "initial_board": copy.deepcopy(board),
        "parameters": parameters,
        "solution_actions": copy.deepcopy(solution),
        "solution_length": len(solution),
        "palette": palette,
        "variant_index": variant_index,
    }
    if condition:
        public["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    else:
        default_condition = {"difficulty": 4, "interaction": "full", "real_time": "live", "difficulty_parameters": copy.deepcopy(params)}
        public["control_condition"] = default_condition
        ground_truth["control_condition"] = default_condition
    return public, ground_truth


def replay_solution(board: dict[str, Any], actions: list[dict[str, Any]]) -> dict[str, Any]:
    current = copy.deepcopy(board)
    for action in actions:
        current, _ = apply_action(current, str(action["worker_id"]), str(action["direction"]))
    return current
