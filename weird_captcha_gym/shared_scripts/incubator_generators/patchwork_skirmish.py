from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "patchwork_skirmish"


def _rng(seed: str) -> random.Random:
    digest = hashlib.sha256(f"{seed}|{MECHANIC_ID}|v1".encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


SHAPES: dict[int, tuple[tuple[tuple[int, int], ...], ...]] = {
    2: (
        ((0, 0), (0, 1)),
        ((0, 0), (1, 0)),
    ),
    3: (
        ((0, 0), (0, 1), (0, 2)),
        ((0, 0), (1, 0), (1, 1)),
    ),
    4: (
        ((0, 0), (0, 1), (1, 0), (1, 1)),
        ((0, 0), (0, 1), (0, 2), (0, 3)),
    ),
    5: (
        ((0, 0), (0, 1), (0, 2), (0, 3), (0, 4)),
        ((0, 0), (0, 1), (0, 2), (1, 2), (1, 3)),
    ),
}


PROFILES: dict[int, dict[str, Any]] = {
    1: {
        "board_width": 8,
        "board_height": 6,
        "player_areas": [2, 2],
        "enemy_areas": [2],
        "movement_points": 3,
        "enemy_movement_points": 1,
        "attack_power": 1,
        "max_turns": 12,
    },
    2: {
        "board_width": 9,
        "board_height": 6,
        "player_areas": [3, 2],
        "enemy_areas": [3, 2],
        "movement_points": 3,
        "enemy_movement_points": 1,
        "attack_power": 1,
        "max_turns": 14,
    },
    3: {
        "board_width": 10,
        "board_height": 7,
        "player_areas": [3, 3, 2],
        "enemy_areas": [3, 2],
        "movement_points": 2,
        "enemy_movement_points": 1,
        "attack_power": 1,
        "max_turns": 15,
    },
    4: {
        "board_width": 11,
        "board_height": 7,
        "player_areas": [4, 3, 3],
        "enemy_areas": [4, 3, 3],
        "movement_points": 2,
        "enemy_movement_points": 1,
        "attack_power": 1,
        "max_turns": 18,
    },
    5: {
        "board_width": 12,
        "board_height": 8,
        "player_areas": [5, 4, 3, 3],
        "enemy_areas": [5, 4, 3],
        "movement_points": 2,
        "enemy_movement_points": 2,
        "attack_power": 1,
        "max_turns": 20,
    },
}


def _cells_for(area: int, variant: int, row: int, col: int) -> list[list[int]]:
    shape = SHAPES[area][variant % len(SHAPES[area])]
    return [[row + dr, col + dc] for dr, dc in shape]


def _unit(
    unit_id: str,
    owner: int,
    area: int,
    variant: int,
    row: int,
    col: int,
    palette: str,
    label: str,
) -> dict[str, Any]:
    shape = [list(point) for point in SHAPES[area][variant % len(SHAPES[area])]]
    return {
        "id": unit_id,
        "owner": owner,
        "label": label,
        "area": area,
        "shape": shape,
        "cells": _cells_for(area, variant, row, col),
        "palette": palette,
    }


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = _rng(seed)
    condition = copy.deepcopy(task.get("_control_condition") or {})
    level = int(condition.get("difficulty", 4))
    if level not in PROFILES:
        raise ValueError("patchwork difficulty must be 1 through 5")
    parameters = copy.deepcopy(condition.get("difficulty_parameters") or PROFILES[level])
    for key, value in PROFILES[level].items():
        parameters.setdefault(key, copy.deepcopy(value))

    width = int(parameters["board_width"])
    height = int(parameters["board_height"])
    player_areas = [int(value) for value in parameters["player_areas"]]
    enemy_areas = [int(value) for value in parameters["enemy_areas"]]
    if not (8 <= width <= 14 and 6 <= height <= 10):
        raise ValueError("patchwork board bounds are invalid")
    if not (1 <= len(player_areas) <= 5 and 1 <= len(enemy_areas) <= 4):
        raise ValueError("patchwork unit counts are invalid")
    if any(area not in SHAPES for area in player_areas + enemy_areas):
        raise ValueError("patchwork area has no connected shape")

    task_id = str(task.get("id") or "patchwork_skirmish_seed_0001@0.1")
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|d{level}".encode("utf-8")).hexdigest()[:13]
    theme = rng.choice(("indigo_quilt", "copper_quilt", "moss_quilt", "violet_quilt"))
    player_palette = ("citrine", "lagoon", "rose", "lichen", "saffron")
    enemy_palette = ("vermilion", "plum", "ember", "ink")

    units: list[dict[str, Any]] = []
    # Lanes and orientations vary by seed. Candidate placement is checked
    # against already placed footprints so the exported board never starts with
    # overlapping patches, even when a footprint spans two rows.
    lane_pool = list(range(height))
    rng.shuffle(lane_pool)
    occupied: set[tuple[int, int]] = set()

    def place(owner: int, areas: list[int], prefix: str, palettes: tuple[str, ...], label: str) -> None:
        side = range(0, width // 2) if owner == 0 else range(width // 2, width)
        columns = list(side)
        rng.shuffle(columns)
        for index, area in enumerate(areas):
            variants = list(range(len(SHAPES[area])))
            rng.shuffle(variants)
            placed = None
            for variant in variants:
                shape = SHAPES[area][variant]
                max_col = max(point[1] for point in shape)
                max_row = max(point[0] for point in shape)
                rows = sorted(range(max(0, height - max_row)), key=lambda row: (abs(row - lane_pool[(index + row) % len(lane_pool)]), row))
                for row in rows:
                    for col in columns:
                        cells = _cells_for(area, variant, row, col)
                        cell_set = {(r, c) for r, c in cells}
                        if any(c < min(side) or c >= max(side) + 1 for _, c in cells):
                            continue
                        if cell_set & occupied:
                            continue
                        placed = (variant, row, col, cells)
                        break
                    if placed:
                        break
                if placed:
                    break
            if placed is None:
                raise ValueError("could not place non-overlapping patchwork footprints")
            variant, row, col, cells = placed
            occupied.update((r, c) for r, c in cells)
            units.append(_unit(f"{prefix}{index + 1}", owner, area, variant, row, col, palettes[index % len(palettes)], f"{label} {index + 1}"))

    place(0, player_areas, "P", player_palette, "PATCH")
    place(1, enemy_areas, "E", enemy_palette, "RIVAL")

    seam_seed = rng.randrange(1 << 30)
    seams = []
    seam_rng = random.Random(seam_seed)
    for row in range(height):
        seams.append({"row": row, "offset": seam_rng.randrange(0, 4), "tone": seam_rng.choice(("gold", "blue", "white"))})

    world = {
        "width": width,
        "height": height,
        "units": units,
        "seams": seams,
        "theme": theme,
        "movement_points": int(parameters["movement_points"]),
        "enemy_movement_points": int(parameters["enemy_movement_points"]),
        "attack_power": int(parameters["attack_power"]),
        "max_turns": int(parameters["max_turns"]),
        "variant": seam_seed,
    }
    prompt = task.get("natural_language") or (
        "Keep your patches alive and remove every rival patch. Select a patch, move or strike, then end the turn to face the response. "
        "Each patch's health is its visible occupied area."
    )
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": prompt,
        "submit_label": "CERTIFY SKIRMISH",
        "asset_manifest": "shared_runtime/assets/provenance/patchwork_skirmish_v0.json",
        "generator": {"name": "deterministic_patchwork_battle_v1", "variant_count": 4 * (1 << 30)},
        "difficulty_level": level,
        "world": copy.deepcopy(world),
        "rules": {
            "area_health": "A patch's health is the number of colored cells it occupies.",
            "movement": "A move translates every cell of one connected patch by one square and leaves its area unchanged.",
            "attack": "A neighboring patch can strike once per turn and removes one visible edge cell from its footprint.",
            "response": "After END TURN, each rival moves toward the nearest player patch or removes one cell from an adjacent player patch.",
            "victory": "End a turn with all rival patches removed and at least one player cell remaining.",
        },
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "difficulty_level": level,
        "world": copy.deepcopy(world),
    }
    if condition:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
