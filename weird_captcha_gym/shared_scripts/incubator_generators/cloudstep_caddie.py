from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "cloudstep_caddie"

PALETTES = (
    {
        "name": "sunrise",
        "sky": "#f6d6b8",
        "cloud": "#fff5e5",
        "fairway": "#76b889",
        "fairway_dark": "#3f805f",
        "sand": "#e7bd76",
        "water": "#5ca8c2",
        "ramp": "#9ed28a",
        "cup": "#f4e8a0",
        "ink": "#243d42",
        "accent": "#ef795c",
    },
    {
        "name": "twilight",
        "sky": "#c8c4e8",
        "cloud": "#f6efff",
        "fairway": "#78b9a8",
        "fairway_dark": "#3d7b78",
        "sand": "#e9bf8c",
        "water": "#548fb8",
        "ramp": "#a2d2b0",
        "cup": "#f6df85",
        "ink": "#253552",
        "accent": "#e879a6",
    },
    {
        "name": "meadow",
        "sky": "#d9efd0",
        "cloud": "#fffbe7",
        "fairway": "#78ad68",
        "fairway_dark": "#497645",
        "sand": "#ebc879",
        "water": "#5aa2a3",
        "ramp": "#a6d789",
        "cup": "#fff0a9",
        "ink": "#28413a",
        "accent": "#db7559",
    },
    {
        "name": "candy",
        "sky": "#f4c9dc",
        "cloud": "#fff3f7",
        "fairway": "#79b89d",
        "fairway_dark": "#4a806d",
        "sand": "#eac485",
        "water": "#659bc2",
        "ramp": "#a4d0a5",
        "cup": "#ffe999",
        "ink": "#3f3450",
        "accent": "#d95f87",
    },
)


PROFILES: dict[int, dict[str, Any]] = {
    1: {
        "board_width": 7,
        "board_height": 6,
        "action_plan": [
            {"direction": "east", "distance": 2, "kind": "roll"},
            {"direction": "south", "distance": 1, "kind": "roll"},
            {"direction": "east", "distance": 1, "kind": "chip"},
        ],
        "sand_route_indices": [],
        "water_count": 1,
        "ramp_count": 1,
        "decoy_count": 4,
        "chip_clearance": 1,
    },
    2: {
        "board_width": 8,
        "board_height": 7,
        "action_plan": [
            {"direction": "east", "distance": 2, "kind": "roll"},
            {"direction": "south", "distance": 1, "kind": "roll"},
            {"direction": "east", "distance": 1, "kind": "chip"},
            {"direction": "south", "distance": 1, "kind": "roll"},
        ],
        "sand_route_indices": [2],
        "water_count": 2,
        "ramp_count": 1,
        "decoy_count": 8,
        "chip_clearance": 1,
    },
    3: {
        "board_width": 9,
        "board_height": 8,
        "action_plan": [
            {"direction": "east", "distance": 2, "kind": "roll"},
            {"direction": "south", "distance": 1, "kind": "roll"},
            {"direction": "east", "distance": 1, "kind": "chip"},
            {"direction": "south", "distance": 2, "kind": "chip"},
            {"direction": "east", "distance": 2, "kind": "roll"},
        ],
        "sand_route_indices": [2],
        "water_count": 3,
        "ramp_count": 2,
        "decoy_count": 12,
        "chip_clearance": 2,
    },
    4: {
        "board_width": 11,
        "board_height": 9,
        "action_plan": [
            {"direction": "east", "distance": 1, "kind": "roll"},
            {"direction": "south", "distance": 1, "kind": "roll"},
            {"direction": "east", "distance": 2, "kind": "roll"},
            {"direction": "south", "distance": 1, "kind": "chip"},
            {"direction": "east", "distance": 1, "kind": "roll"},
            {"direction": "south", "distance": 2, "kind": "chip"},
            {"direction": "east", "distance": 2, "kind": "roll"},
        ],
        "sand_route_indices": [2, 4],
        "water_count": 5,
        "ramp_count": 3,
        "decoy_count": 18,
        "chip_clearance": 2,
    },
    5: {
        "board_width": 12,
        "board_height": 9,
        "action_plan": [
            {"direction": "east", "distance": 2, "kind": "roll"},
            {"direction": "south", "distance": 1, "kind": "roll"},
            {"direction": "east", "distance": 1, "kind": "chip"},
            {"direction": "south", "distance": 2, "kind": "chip"},
            {"direction": "east", "distance": 2, "kind": "roll"},
            {"direction": "north", "distance": 1, "kind": "roll"},
            {"direction": "east", "distance": 2, "kind": "roll"},
            {"direction": "south", "distance": 1, "kind": "roll"},
            {"direction": "east", "distance": 1, "kind": "chip"},
        ],
        "sand_route_indices": [2, 4, 7],
        "water_count": 7,
        "ramp_count": 4,
        "decoy_count": 26,
        "chip_clearance": 2,
    },
}

VECTORS = {
    "north": (0, -1),
    "east": (1, 0),
    "south": (0, 1),
    "west": (-1, 0),
}


def _seed_int(seed: str, salt: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{salt}".encode()).digest()[:8], "big")


def _transform_point(point: tuple[int, int], width: int, height: int, transform: int) -> tuple[int, int]:
    x, y = point
    if transform & 1:
        x = width - 1 - x
    if transform & 2:
        y = height - 1 - y
    return x, y


def _transform_direction(direction: str, transform: int) -> str:
    dx, dy = VECTORS[direction]
    if transform & 1:
        dx = -dx
    if transform & 2:
        dy = -dy
    return next(name for name, vector in VECTORS.items() if vector == (dx, dy))


def _course_tile(
    x: int,
    y: int,
    z: int,
    surface: str,
    tile_id: str,
    rng: random.Random,
    *,
    ramp_direction: str | None = None,
) -> dict[str, Any]:
    return {
        "id": tile_id,
        "x": int(x),
        "y": int(y),
        "z": int(z),
        "surface": surface,
        "tone": rng.randrange(4),
        "ramp_direction": ramp_direction,
    }


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = copy.deepcopy(task.get("_control_condition"))
    difficulty = int((condition or {}).get("difficulty", 4))
    if difficulty not in PROFILES:
        raise ValueError(f"unknown Cloudstep Caddie difficulty {difficulty}")
    profile = copy.deepcopy(PROFILES[difficulty])
    if condition is not None:
        for name, value in (condition.get("difficulty_parameters") or {}).items():
            if name in profile:
                profile[name] = copy.deepcopy(value)
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    width, height = int(profile["board_width"]), int(profile["board_height"])
    transform = rng.randrange(4)
    palette = copy.deepcopy(PALETTES[rng.randrange(len(PALETTES))])
    canonical_tiles: dict[tuple[int, int], dict[str, Any]] = {}
    route_targets: list[tuple[int, int]] = []
    current = (1, 2)
    current_z = 0
    canonical_tiles[current] = _course_tile(1, 2, 0, "fairway", "tile-start", rng)
    solution: list[dict[str, Any]] = []
    cards: list[dict[str, Any]] = []
    for index, step in enumerate(profile["action_plan"]):
        direction = str(step["direction"])
        distance = int(step["distance"])
        kind = str(step["kind"])
        dx, dy = VECTORS[direction]
        target = (current[0] + dx * distance, current[1] + dy * distance)
        target_z = current_z
        if kind == "chip":
            target_z = min(2, current_z + 1)
        if kind == "roll" and target_z != current_z:
            raise ValueError("generated roll route unexpectedly changes height")
        for offset in range(1, distance + 1):
            point = (current[0] + dx * offset, current[1] + dy * offset)
            is_target = offset == distance
            if not is_target and kind == "chip":
                canonical_tiles.setdefault(point, _course_tile(point[0], point[1], current_z, "water", f"water-route-{index}", rng))
                continue
            surface = "cup" if index == len(profile["action_plan"]) - 1 and is_target else "fairway"
            if surface != "cup" and is_target and index in set(int(item) for item in profile.get("sand_route_indices", [])):
                surface = "sand"
            canonical_tiles[point] = _course_tile(point[0], point[1], target_z if is_target else current_z, surface, f"tile-route-{index}-{offset}", rng)
        current = target
        current_z = target_z
        route_targets.append(current)
        card_id = f"card-{index + 1:02d}"
        label = f"{kind.upper()} {distance}"
        card = {"id": card_id, "kind": kind, "distance": distance, "label": label, "tone": index % 4}
        cards.append(card)
        solution.append({"card_id": card_id, "direction": direction})

    occupied = set(canonical_tiles)
    candidates = [(x, y) for y in range(height) for x in range(width) if (x, y) not in occupied]
    rng.shuffle(candidates)
    water_count = int(profile["water_count"])
    ramp_count = int(profile.get("ramp_count", 0))
    for index, point in enumerate(candidates[: int(profile["decoy_count"]) + water_count + ramp_count]):
        is_water = index < water_count
        is_ramp = water_count <= index < water_count + ramp_count
        surface = "water" if is_water else ("ramp" if is_ramp else ("sand" if rng.random() < 0.52 else "fairway"))
        ramp_direction = rng.choice(tuple(VECTORS)) if is_ramp else None
        tile_z = 0 if is_water else (rng.randrange(1, 3) if is_ramp else rng.randrange(0, 3))
        canonical_tiles[point] = _course_tile(point[0], point[1], tile_z, surface, f"tile-decoy-{index + 1:02d}", rng, ramp_direction=ramp_direction)

    tiles: list[dict[str, Any]] = []
    transformed_lookup: dict[tuple[int, int], dict[str, Any]] = {}
    for (x, y), tile in canonical_tiles.items():
        tx, ty = _transform_point((x, y), width, height, transform)
        item = dict(tile)
        item["x"], item["y"] = tx, ty
        if item["ramp_direction"] is not None:
            item["ramp_direction"] = _transform_direction(item["ramp_direction"], transform)
        transformed_lookup[(tx, ty)] = item
        tiles.append(item)
    tiles.sort(key=lambda item: (int(item["x"]) + int(item["y"]), int(item["z"]), str(item["id"])))
    start_point = _transform_point((1, 2), width, height, transform)
    cup_point = _transform_point(current, width, height, transform)
    transformed_solution = [
        {"card_id": item["card_id"], "direction": _transform_direction(item["direction"], transform)}
        for item in solution
    ]
    rng.shuffle(cards)
    task_id = str(task.get("id") or f"{MECHANIC_ID}_seed_0001@0.1")
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|difficulty={difficulty}".encode()).hexdigest()[:14]
    rules = {
        "roll_max_step_height": 1,
        "chip_clearance": int(profile["chip_clearance"]),
        "sand_roll_limit": 1,
    }
    course = {
        "width": width,
        "height": height,
        "tiles": tiles,
        "transform": transform,
        "start": {"x": start_point[0], "y": start_point[1], "z": 0},
        "cup": {"x": cup_point[0], "y": cup_point[1], "z": current_z},
        "rules": rules,
    }
    public_state: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "asset_manifest": "shared_runtime/assets/provenance/cloudstep_caddie_v0.json",
        "prompt": task.get("natural_language") or "Read the raised cloud tiles, spend the exact hand, and sink the ball.",
        "generator": {
            "name": "cloudstep_caddie_procedural_v1",
            "variant_count": len(PALETTES) * 4 * 5 * 4,
        },
        "palette": palette,
        "course": course,
        "cards": cards,
        "hand_size": len(cards),
    }
    ground_truth: dict[str, Any] = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "palette": palette,
        "course": copy.deepcopy(course),
        "cards": copy.deepcopy(cards),
        "solution": transformed_solution,
        "variant_count": public_state["generator"]["variant_count"],
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth


__all__ = ["MECHANIC_ID", "PROFILES", "generate"]
