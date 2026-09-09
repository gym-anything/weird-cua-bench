from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "lantern_loft"
BOARD_SIDE = 3
CANONICAL_PATH = (0, 1, 2, 5, 8, 7, 6, 3)
SIDES = ("n", "e", "s", "w")
OPPOSITE = {"n": "s", "e": "w", "s": "n", "w": "e"}


PROFILES: dict[int, dict[str, Any]] = {
    1: {
        "route_count": 3,
        "slide_count": 1,
        "elevation_changes": 1,
        "decoy_openings": 0,
        "stair_count": 1,
    },
    2: {
        "route_count": 4,
        "slide_count": 2,
        "elevation_changes": 1,
        "decoy_openings": 1,
        "stair_count": 1,
    },
    3: {
        "route_count": 5,
        "slide_count": 3,
        "elevation_changes": 2,
        "decoy_openings": 1,
        "stair_count": 2,
    },
    4: {
        "route_count": 7,
        "slide_count": 4,
        "elevation_changes": 3,
        "decoy_openings": 2,
        "stair_count": 3,
    },
    5: {
        "route_count": 8,
        "slide_count": 6,
        "elevation_changes": 5,
        "decoy_openings": 3,
        "stair_count": 5,
    },
}

PALETTES = (
    {"name": "ember", "paper": "#fff4dc", "ink": "#2f2439", "wood": "#c47c4f", "edge": "#744230", "glow": "#ffd56b", "accent": "#5f73bd"},
    {"name": "moss", "paper": "#eef4df", "ink": "#24352d", "wood": "#a97a50", "edge": "#5e4931", "glow": "#f4d477", "accent": "#5c9c83"},
    {"name": "plum", "paper": "#f4eafa", "ink": "#30253b", "wood": "#aa7194", "edge": "#633e5e", "glow": "#ffe18b", "accent": "#7186c8"},
)


def _seed_int(seed: str, salt: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).digest()[:8], "big")


def _xy(slot: int) -> tuple[int, int]:
    return slot % BOARD_SIDE, slot // BOARD_SIDE


def _slot(x: int, y: int) -> int:
    return y * BOARD_SIDE + x


def _transform_slot(slot: int, rotation: int, mirror: bool) -> int:
    x, y = _xy(slot)
    if mirror:
        x = BOARD_SIDE - 1 - x
    for _ in range(rotation % 4):
        x, y = BOARD_SIDE - 1 - y, x
    return _slot(x, y)


def _direction(a: int, b: int) -> str:
    ax, ay = _xy(a)
    bx, by = _xy(b)
    delta = (bx - ax, by - ay)
    return {(0, -1): "n", (1, 0): "e", (0, 1): "s", (-1, 0): "w"}[delta]


def _adjacent(a: int, b: int) -> bool:
    ax, ay = _xy(a)
    bx, by = _xy(b)
    return abs(ax - bx) + abs(ay - by) == 1


def _module(module_id: str, index: int, height: int, rng: random.Random) -> dict[str, Any]:
    openings = {side: False for side in SIDES}
    stairs = {side: False for side in SIDES}
    return {
        "id": module_id,
        "label": f"LOFT-{index + 1:02d}",
        "height": int(height),
        "tone": rng.randrange(5),
        "grain": rng.randrange(4),
        "openings": openings,
        "stairs": stairs,
    }


def _set_connection(modules: dict[str, dict[str, Any]], slot_to_module: dict[int, str | None], a: int, b: int, stair: bool) -> None:
    module_a = modules[str(slot_to_module[a])]
    module_b = modules[str(slot_to_module[b])]
    side_a = _direction(a, b)
    side_b = OPPOSITE[side_a]
    module_a["openings"][side_a] = True
    module_b["openings"][side_b] = True
    if stair:
        module_a["stairs"][side_a] = True
        module_b["stairs"][side_b] = True


def _choose_scramble(board: list[str | None], empty: int, start_slot: int, rng: random.Random, turn_count: int) -> tuple[list[str | None], int, list[dict[str, Any]]]:
    moves: list[dict[str, Any]] = []
    previous: tuple[int, int] | None = None
    for _ in range(max(1, int(turn_count))):
        candidates = [
            slot
            for slot in range(9)
            if board[slot] is not None and _adjacent(slot, empty) and slot != start_slot
            and (previous is None or slot != previous[1])
        ]
        if not candidates:
            candidates = [slot for slot in range(9) if board[slot] is not None and _adjacent(slot, empty) and slot != start_slot]
        if not candidates:
            break
        source = rng.choice(candidates)
        module_id = board[source]
        assert module_id is not None
        moves.append({"module_id": module_id, "from_slot": source, "to_slot": empty})
        board[empty] = module_id
        board[source] = None
        previous = (source, empty)
        empty = source
    return board, empty, moves


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = copy.deepcopy(task.get("_control_condition"))
    difficulty = int((condition or {}).get("difficulty", 4))
    if difficulty not in PROFILES:
        raise ValueError(f"unknown Lantern Loft difficulty {difficulty}")
    profile = copy.deepcopy(PROFILES[difficulty])
    if condition is not None:
        for name, value in (condition.get("difficulty_parameters") or {}).items():
            if name in profile:
                profile[name] = copy.deepcopy(value)

    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    palette = copy.deepcopy(PALETTES[rng.randrange(len(PALETTES))])
    rotation = rng.randrange(4)
    mirror = bool(rng.randrange(2))
    route_slots = [_transform_slot(slot, rotation, mirror) for slot in CANONICAL_PATH[: int(profile["route_count"])] ]
    empty_target = _transform_slot(4, rotation, mirror)
    start_slot = route_slots[0]
    exit_slot = route_slots[-1]

    heights = [0] * int(profile["route_count"])
    change_indices = set(rng.sample(range(1, len(heights)), min(int(profile["elevation_changes"]), len(heights) - 1)))
    for index in range(1, len(heights)):
        heights[index] = heights[index - 1] + (1 if index in change_indices and heights[index - 1] < 2 else 0)
        if index not in change_indices and rng.random() < 0.22 and heights[index - 1] > 0:
            heights[index] = heights[index - 1] - 1

    modules: dict[str, dict[str, Any]] = {}
    route_module_ids: list[str] = []
    for index, height in enumerate(heights):
        module_id = f"module-{index:02d}"
        route_module_ids.append(module_id)
        modules[module_id] = _module(module_id, index, height, rng)
    decoy_count = 8 - len(route_module_ids)
    for index in range(decoy_count):
        module_id = f"decoy-{index:02d}"
        modules[module_id] = _module(module_id, len(route_module_ids) + index, rng.randrange(3), rng)

    target_board: list[str | None] = [None] * 9
    route_slot_to_module: dict[int, str | None] = {}
    for module_id, slot in zip(route_module_ids, route_slots):
        target_board[slot] = module_id
        route_slot_to_module[slot] = module_id
    remaining_slots = [slot for slot in range(9) if target_board[slot] is None and slot != empty_target]
    for module_id, slot in zip((f"decoy-{i:02d}" for i in range(decoy_count)), remaining_slots):
        target_board[slot] = module_id
    target_board[empty_target] = None

    route_edges: list[tuple[int, int, str]] = []
    for a, b in zip(route_slots, route_slots[1:]):
        if not _adjacent(a, b):
            raise ValueError("Lantern Loft route is not grid-adjacent")
        stair = modules[route_slot_to_module[a]]["height"] != modules[route_slot_to_module[b]]["height"]
        _set_connection(modules, route_slot_to_module, a, b, stair)
        route_edges.append((a, b, _direction(a, b)))

    # The stair budget is visible geometry as well as a route parameter. Some
    # same-height joins carry a shallow decorative stair, which makes a
    # projected opening ambiguous until the agent reads the elevation labels.
    stair_budget = min(int(profile["stair_count"]), len(route_edges))
    for a, b, side in route_edges[:stair_budget]:
        first = modules[str(route_slot_to_module[a])]
        second = modules[str(route_slot_to_module[b])]
        first["stairs"][side] = True
        second["stairs"][OPPOSITE[side]] = True

    decoy_slots = [slot for slot, module_id in enumerate(target_board) if module_id and module_id.startswith("decoy-")]
    for slot in decoy_slots:
        module_id = str(target_board[slot])
        module = modules[module_id]
        for side in SIDES:
            if rng.random() < float(profile["decoy_openings"]) / 5.0:
                module["openings"][side] = True
        if rng.random() < 0.4:
            module["stairs"][rng.choice(SIDES)] = True

    board = list(target_board)
    board, empty_slot, scrambled_moves = _choose_scramble(board, empty_target, start_slot, rng, int(profile["slide_count"]))
    solution_slides = [
        {"module_id": move["module_id"], "from_slot": move["to_slot"], "to_slot": move["from_slot"]}
        for move in reversed(scrambled_moves)
    ]
    rules = {
        "board_side": BOARD_SIDE,
        "max_height_delta": 1,
        "route_step_count": len(route_slots) - 1,
    }
    task_id = str(task.get("id") or "lantern_loft_seed_0001@0.1")
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|lantern-v1|d={difficulty}".encode("utf-8")).hexdigest()[:14]
    public_state: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "asset_manifest": "shared_runtime/assets/provenance/lantern_loft_v0.json",
        "prompt": task.get("natural_language") or "Rebuild the loft path and carry the lantern to the exit landing.",
        "generator": {"name": "lantern_loft_procedural_v1", "variant_count": 3 * 8 * 2},
        "palette": palette,
        "world": {
            "board_side": BOARD_SIDE,
            "board": board,
            "empty_slot": empty_slot,
            "modules": list(modules.values()),
            "start_slot": start_slot,
            "exit_slot": exit_slot,
            "carrier_slot": start_slot,
            "rules": rules,
        },
    }
    ground_truth: dict[str, Any] = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "world": copy.deepcopy(public_state["world"]),
        "route_slots": route_slots,
        "route_module_ids": route_module_ids,
        "solution_slides": solution_slides,
        "variant_count": public_state["generator"]["variant_count"],
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth


__all__ = ["MECHANIC_ID", "PROFILES", "generate"]
