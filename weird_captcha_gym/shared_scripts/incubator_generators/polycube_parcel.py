"""Seeded 3-D polycube packing worlds for Polycube Parcel.

The seven shapes are the small Soma family recorded by the cited open-source
reference.  The benchmark owns the generated colors, presentation, initial
state, and acceptance contract; no source artwork or level data is reused.
"""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
import random
from typing import Any, Iterable


MECHANIC_ID = "polycube_parcel"

SHAPES: dict[str, list[list[int]]] = {
    "V": [[0, 0, 0], [0, 1, 0], [1, 0, 0]],
    "L": [[0, 0, 0], [0, 1, 0], [0, 2, 0], [1, 0, 0]],
    "T": [[0, 1, 0], [0, 0, 0], [1, 0, 0], [2, 0, 0]],
    "Z": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [2, 1, 0]],
    "A": [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 1]],
    "B": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [1, 1, 1]],
    "P": [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 1, 1]],
}
PIECE_ORDER = ("V", "L", "T", "Z", "A", "B", "P")
COLORS = ("#ffbd69", "#67d7ca", "#a88cff", "#ff789d", "#65b9ff", "#f1da68", "#e58bff")

# One exact cover of the 3x3x3 parcel.  Other covers are accepted by the
# grader; this cover certifies that every generated instance is attainable.
BASE_SOLUTION: dict[str, list[list[int]]] = {
    "V": [[2, 0, 1], [2, 0, 2], [2, 1, 2]],
    "L": [[1, 2, 0], [2, 2, 0], [2, 2, 1], [2, 2, 2]],
    "T": [[0, 0, 0], [0, 1, 0], [1, 0, 0], [2, 0, 0]],
    "A": [[1, 0, 1], [1, 1, 0], [2, 1, 0], [2, 1, 1]],
    "Z": [[0, 1, 1], [0, 1, 2], [0, 2, 0], [0, 2, 1]],
    "P": [[0, 2, 2], [1, 1, 1], [1, 2, 1], [1, 2, 2]],
    "B": [[0, 0, 1], [0, 0, 2], [1, 0, 2], [1, 1, 2]],
}

PROFILES: dict[int, dict[str, Any]] = {
    1: {"preplaced_count": 5, "camera_yaw": 0, "camera_pitch": 0.42, "piece_opacity": 0.80, "parcel_opacity": 0.25, "rack_spacing": 1.22},
    2: {"preplaced_count": 4, "camera_yaw": 16, "camera_pitch": 0.44, "piece_opacity": 0.84, "parcel_opacity": 0.22, "rack_spacing": 1.16},
    3: {"preplaced_count": 2, "camera_yaw": 31, "camera_pitch": 0.46, "piece_opacity": 0.88, "parcel_opacity": 0.19, "rack_spacing": 1.08},
    4: {"preplaced_count": 0, "camera_yaw": 37, "camera_pitch": 0.48, "piece_opacity": 0.93, "parcel_opacity": 0.15, "rack_spacing": 1.00},
    5: {"preplaced_count": 0, "camera_yaw": 67, "camera_pitch": 0.55, "piece_opacity": 1.00, "parcel_opacity": 0.09, "rack_spacing": 0.86},
}
PARAMETER_FIELDS = frozenset(PROFILES[4])


def _seed_int(seed: str, salt: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).digest()[:8], "big")


def _mat_mul(a: list[list[int]], b: list[list[int]]) -> list[list[int]]:
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _mat_vec(m: list[list[int]], v: Iterable[int]) -> list[int]:
    values = list(v)
    return [sum(m[i][j] * values[j] for j in range(3)) for i in range(3)]


def _det(m: list[list[int]]) -> int:
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


def _orientations() -> list[list[list[int]]]:
    result: list[list[list[int]]] = []
    for permutation in itertools.permutations(range(3)):
        for signs in itertools.product((-1, 1), repeat=3):
            matrix = [[0, 0, 0] for _ in range(3)]
            for row in range(3):
                matrix[row][permutation[row]] = signs[row]
            if _det(matrix) == 1:
                result.append(matrix)
    return result


ORIENTATIONS = _orientations()
IDENTITY = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


def _normalize_shape(cells: Iterable[Iterable[int]]) -> list[list[int]]:
    values = [list(map(int, cell)) for cell in cells]
    minimum = [min(cell[axis] for cell in values) for axis in range(3)]
    return sorted([[cell[axis] - minimum[axis] for axis in range(3)] for cell in values])


def _fit_shape(piece_id: str, cells: Iterable[Iterable[int]]) -> tuple[list[list[int]], list[int]]:
    target = {tuple(map(int, cell)) for cell in cells}
    target_minimum = [min(cell[axis] for cell in target) for axis in range(3)]
    for orientation in ORIENTATIONS:
        rotated = [_mat_vec(orientation, cell) for cell in SHAPES[piece_id]]
        minimum = [min(cell[axis] for cell in rotated) for axis in range(3)]
        normalized = {tuple(cell[axis] - minimum[axis] for axis in range(3)) for cell in rotated}
        target_normalized = {tuple(cell[axis] - target_minimum[axis] for axis in range(3)) for cell in target}
        if normalized == target_normalized:
            return copy.deepcopy(orientation), [target_minimum[axis] - minimum[axis] for axis in range(3)]
    raise ValueError(f"cannot fit {piece_id} to target cells")


def _covered_cells(piece_id: str, orientation: list[list[int]], origin: list[int]) -> list[list[int]]:
    return sorted([[_mat_vec(orientation, cell)[axis] + int(origin[axis]) for axis in range(3)] for cell in SHAPES[piece_id]])


def _certify_cover(placements: dict[str, dict[str, Any]]) -> None:
    cells: list[tuple[int, int, int]] = []
    for piece_id in PIECE_ORDER:
        cells.extend(tuple(cell) for cell in placements[piece_id]["cells"])
    expected = set(itertools.product(range(3), repeat=3))
    if len(cells) != 27 or len(set(cells)) != 27 or set(cells) != expected:
        raise ValueError("generated polycube cover is not an exact 3x3x3 cover")


def _condition(task: dict[str, Any]) -> tuple[dict[str, Any] | None, int, dict[str, Any]]:
    raw = task.get("_control_condition") or (task.get("metadata") or {}).get("control_condition")
    if raw is None:
        return None, 4, copy.deepcopy(PROFILES[4])
    if not isinstance(raw, dict):
        raise ValueError("polycube parcel control condition is malformed")
    difficulty = int(raw.get("difficulty"))
    if difficulty not in PROFILES:
        raise ValueError("polycube parcel difficulty must be 1 through 5")
    parameters = copy.deepcopy(raw.get("difficulty_parameters") or {})
    if set(parameters) != PARAMETER_FIELDS:
        raise ValueError("polycube parcel difficulty fields do not match controls.json")
    profile = copy.deepcopy(PROFILES[difficulty])
    profile.update(parameters)
    if not 0 <= int(profile["preplaced_count"]) <= 5:
        raise ValueError("preplaced_count is outside the supported range")
    return copy.deepcopy(raw), difficulty, profile


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition, difficulty, profile = _condition(task)
    rng = random.Random(_seed_int(seed, "polycube-parcel-v1"))
    global_orientation = ORIENTATIONS[rng.randrange(len(ORIENTATIONS))]
    base_placements: dict[str, dict[str, Any]] = {}
    for piece_id in PIECE_ORDER:
        orientation, origin = _fit_shape(piece_id, BASE_SOLUTION[piece_id])
        transformed_orientation = _mat_mul(global_orientation, orientation)
        centered_origin = [int(origin[axis]) - 1 for axis in range(3)]
        transformed_origin = [value + 1 for value in _mat_vec(global_orientation, centered_origin)]
        cells = _covered_cells(piece_id, transformed_orientation, transformed_origin)
        base_placements[piece_id] = {
            "orientation": transformed_orientation,
            "origin": transformed_origin,
            "cells": cells,
        }
    _certify_cover(base_placements)

    preplaced = set(PIECE_ORDER[: int(profile["preplaced_count"])])
    rng.shuffle(PIECE_ORDER_LIST := list(PIECE_ORDER))
    # Keep low levels as readable partial assemblies but vary which piece is
    # free at each seed.  The choice never changes the exact cover.
    preplaced = set(PIECE_ORDER_LIST[: int(profile["preplaced_count"])])
    pieces: list[dict[str, Any]] = []
    for index, piece_id in enumerate(PIECE_ORDER):
        target = base_placements[piece_id]
        placed = piece_id in preplaced
        initial_orientation = copy.deepcopy(target["orientation"]) if placed else copy.deepcopy(ORIENTATIONS[rng.randrange(len(ORIENTATIONS))])
        if placed:
            origin = list(target["origin"])
        else:
            origin = [-5 + (index % 4) * float(profile["rack_spacing"]), 0, -2.25 + (index // 4) * 1.1]
        pieces.append({
            "id": piece_id,
            "label": {"V": "V-CUT", "L": "L-BEND", "T": "T-BRACE", "Z": "ZIG", "A": "LEFT ARM", "B": "RIGHT ARM", "P": "HOOK"}[piece_id],
            "shape": copy.deepcopy(SHAPES[piece_id]),
            "color": COLORS[index % len(COLORS)],
            "orientation": initial_orientation,
            "origin": [round(float(value), 3) for value in origin],
            "placed": placed,
            "locked": placed,
        })

    task_id = str(task.get("id") or f"{MECHANIC_ID}_seed_0001@0.1")
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|parcel-v1|{json.dumps(profile, sort_keys=True)}".encode("utf-8")).hexdigest()[:14]
    interaction = str((condition or {}).get("interaction") or "full")
    world = {
        "grid_size": 3,
        "canvas": {"width": 920, "height": 560},
        "camera": {"yaw": float(profile["camera_yaw"]), "pitch": float(profile["camera_pitch"])},
        "piece_opacity": float(profile["piece_opacity"]),
        "parcel_opacity": float(profile["parcel_opacity"]),
        "rack_spacing": float(profile["rack_spacing"]),
        "pieces": pieces,
        "palette": {"backdrop": ["#16182a", "#19172b", "#1c1b30", "#151d2d"][rng.randrange(4)], "accent": ["#ffcf77", "#7be1d1", "#b99cff"][rng.randrange(3)]},
    }
    prompt = task.get("natural_language") or "Orbit the parcel, rotate each polycube in 3D, and place every piece so the 3×3×3 parcel is filled exactly once."
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": prompt,
        "submit_label": "CERTIFY PARCEL",
        "asset_manifest": "shared_runtime/assets/provenance/polycube_parcel_v0.json",
        "generator": {"name": "polycube_parcel_exact_cover_v1", "variant_count": 24 * 5040 * 64},
        "interaction": interaction,
        "control_condition": copy.deepcopy(condition) if condition is not None else {"interaction": "full"},
        "world": copy.deepcopy(world),
        "parcel": {"size": [3, 3, 3], "cells": list(itertools.product(range(3), repeat=3))},
        "piece_count": len(pieces),
        "preplaced_count": len(preplaced),
    }
    solution = {
        piece_id: {"orientation": copy.deepcopy(base_placements[piece_id]["orientation"]), "origin": list(base_placements[piece_id]["origin"]), "cells": copy.deepcopy(base_placements[piece_id]["cells"])}
        for piece_id in PIECE_ORDER
    }
    truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "control_condition": copy.deepcopy(condition) if condition is not None else {"interaction": "full"},
        "world": copy.deepcopy(world),
        "solution_placements": solution,
        "valid_piece_ids": list(PIECE_ORDER),
        "exact_cover_cells": [list(cell) for cell in sorted(set(tuple(cell) for item in solution.values() for cell in item["cells"]))],
        "difficulty": difficulty,
    }
    return public, truth


__all__ = ["MECHANIC_ID", "PROFILES", "SHAPES", "ORIENTATIONS", "generate"]
