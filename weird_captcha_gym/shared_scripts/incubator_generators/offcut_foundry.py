"""Procedural, no-waste polyomino cutting boards for Offcut Foundry."""
from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "offcut_foundry"
VARIANT_COUNT = 2_176_782_336

PROFILES: dict[int, dict[str, Any]] = {
    1: {
        "rows": 5,
        "columns": 5,
        "piece_count": 3,
        "minimum_piece_size": 6,
        "decoy_count": 0,
        "undo_budget": 4,
        "texture_variation": 1,
        "exposure_rule": "edge_or_previous_cut",
    },
    2: {
        "rows": 6,
        "columns": 6,
        "piece_count": 4,
        "minimum_piece_size": 6,
        "decoy_count": 2,
        "undo_budget": 3,
        "texture_variation": 2,
        "exposure_rule": "edge_or_previous_cut",
    },
    3: {
        "rows": 7,
        "columns": 7,
        "piece_count": 5,
        "minimum_piece_size": 6,
        "decoy_count": 4,
        "undo_budget": 2,
        "texture_variation": 3,
        "exposure_rule": "edge_or_previous_cut",
    },
    4: {
        "rows": 8,
        "columns": 8,
        "piece_count": 6,
        "minimum_piece_size": 6,
        "decoy_count": 6,
        "undo_budget": 1,
        "texture_variation": 4,
        "exposure_rule": "edge_or_previous_cut",
    },
    5: {
        "rows": 9,
        "columns": 9,
        "piece_count": 8,
        "minimum_piece_size": 5,
        "decoy_count": 10,
        "undo_budget": 1,
        "texture_variation": 5,
        "exposure_rule": "edge_or_previous_cut",
    },
}

PALETTES = (
    {"name": "copper dusk", "board": "#17252b", "cell": "#c37b4d", "light": "#f0bf72", "ink": "#3a1e22"},
    {"name": "moss enamel", "board": "#142b2b", "cell": "#69a17b", "light": "#b9d889", "ink": "#173a35"},
    {"name": "violet slag", "board": "#211a32", "cell": "#9b73c8", "light": "#e0b5e8", "ink": "#301c44"},
    {"name": "signal blue", "board": "#132a3c", "cell": "#4c9fc0", "light": "#a8e3df", "ink": "#122943"},
)


def _condition(task: dict[str, Any]) -> dict[str, Any] | None:
    return copy.deepcopy(
        task.get("_control_condition")
        or (task.get("metadata") or {}).get("control_condition")
        or None
    )


def _normalise(cells: list[tuple[int, int]]) -> list[list[int]]:
    min_row = min(row for row, _ in cells)
    min_column = min(column for _, column in cells)
    return [
        [row - min_row, column - min_column]
        for row, column in sorted(cells)
    ]


def _shape_key(shape: list[list[int]]) -> tuple[tuple[int, int], ...]:
    return tuple((int(row), int(column)) for row, column in shape)


def _snake(rows: int, columns: int) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    for row in range(rows):
        columns_in_row = range(columns) if row % 2 == 0 else range(columns - 1, -1, -1)
        cells.extend((row, column) for column in columns_in_row)
    return cells


def _composition(rng: random.Random, total: int, count: int, minimum: int) -> list[int]:
    remaining = total
    lengths: list[int] = []
    for index in range(count - 1):
        high = remaining - minimum * (count - index - 1)
        length = rng.randint(minimum, high)
        lengths.append(length)
        remaining -= length
    lengths.append(remaining)
    return lengths


def _partition(
    rng: random.Random,
    rows: int,
    columns: int,
    count: int,
    minimum: int,
) -> list[list[tuple[int, int]]]:
    path = _snake(rows, columns)
    for _attempt in range(2000):
        lengths = _composition(rng, len(path), count, minimum)
        pieces: list[list[tuple[int, int]]] = []
        cursor = 0
        for length in lengths:
            pieces.append(path[cursor : cursor + length])
            cursor += length
        shapes = [_normalise(piece) for piece in pieces]
        keys = [_shape_key(shape) for shape in shapes]
        if len(set(keys)) != count:
            continue
        # Keep the first and last pieces visually anchored to the stock edges,
        # and reject pathological one-cell-wide slivers at the highest level.
        if len({column for _, column in pieces[0]}) == 1 and len(pieces[0]) > columns:
            continue
        if count >= 6 and any(len({row for row, _ in piece}) == 1 and len(piece) >= columns - 1 for piece in pieces):
            continue
        return pieces
    raise ValueError("could not construct distinct connected offcuts")


def _int_parameter(parameters: dict[str, Any], name: str, default: int) -> int:
    value = parameters.get(name, default)
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    return int(value)


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = _condition(task)
    difficulty = int((condition or {}).get("difficulty") or 4)
    parameters = dict((condition or {}).get("difficulty_parameters") or PROFILES[difficulty])
    rows = _int_parameter(parameters, "rows", PROFILES[4]["rows"])
    columns = _int_parameter(parameters, "columns", PROFILES[4]["columns"])
    piece_count = _int_parameter(parameters, "piece_count", PROFILES[4]["piece_count"])
    minimum_piece_size = _int_parameter(parameters, "minimum_piece_size", PROFILES[4]["minimum_piece_size"])
    decoy_count = _int_parameter(parameters, "decoy_count", PROFILES[4]["decoy_count"])
    undo_budget = _int_parameter(parameters, "undo_budget", PROFILES[4]["undo_budget"])
    texture_variation = _int_parameter(parameters, "texture_variation", PROFILES[4]["texture_variation"])
    if not 4 <= rows <= 10 or not 4 <= columns <= 10:
        raise ValueError("Offcut Foundry boards must be between four and ten cells wide")
    total = rows * columns
    if not 2 <= piece_count < total or minimum_piece_size < 2:
        raise ValueError("invalid Offcut Foundry piece profile")
    if minimum_piece_size * piece_count > total or decoy_count < 0 or undo_budget < 0:
        raise ValueError("invalid Offcut Foundry profile budget")
    if not 1 <= texture_variation <= 6:
        raise ValueError("texture_variation must be between one and six")

    digest = hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    partition = _partition(rng, rows, columns, piece_count, minimum_piece_size)
    palette = copy.deepcopy(PALETTES[rng.randrange(len(PALETTES))])
    board_cells: list[dict[str, Any]] = []
    for row in range(rows):
        for column in range(columns):
            cell_id = f"cell-{row:02d}-{column:02d}"
            board_cells.append(
                {
                    "id": cell_id,
                    "row": row,
                    "column": column,
                    "tone": rng.randrange(texture_variation),
                    "grain": rng.randrange(4),
                }
            )
    decoy_cells = rng.sample([cell["id"] for cell in board_cells], min(decoy_count, total))
    decoy_marks = [
        {"cell_id": cell_id, "mark": rng.choice(("hairline", "rivet", "chalk", "spark"))}
        for cell_id in decoy_cells
    ]

    pieces: list[dict[str, Any]] = []
    placements: dict[str, list[str]] = {}
    for index, cells in enumerate(partition, start=1):
        piece_id = f"piece-{index:02d}"
        shape = _normalise(cells)
        placement = [f"cell-{row:02d}-{column:02d}" for row, column in cells]
        placements[piece_id] = placement
        pieces.append(
            {
                "id": piece_id,
                "label": f"OFFCUT {index:02d}",
                "shape": shape,
                "area": len(shape),
                "finish": rng.randrange(4),
                "accent": rng.choice(("arc", "notch", "bolt", "stripe")),
            }
        )

    task_id = str(task.get("id") or "offcut_foundry_seed_0001@0.1")
    condition_token = "" if not condition or difficulty == 4 else f"|d{difficulty}"
    challenge_id = hashlib.sha256(
        f"{seed}|{MECHANIC_ID}{condition_token}".encode("utf-8")
    ).hexdigest()[:12]
    prompt = task.get("natural_language") or (
        "Trace each requested offcut on the board, extract it, and leave no material behind. "
        "Use UNDO to recover from a bad partition before certifying."
    )
    common = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": prompt,
        "submit_label": "CERTIFY CUTS",
        "asset_manifest": "shared_runtime/assets/provenance/offcut_foundry_v0.json",
        "generator": {
            "name": "patterned_offcut_partition_v1",
            "variant_count": VARIANT_COUNT,
            "variant_count_kind": "seeded connected partitions, palettes, textures and cut-list silhouettes",
        },
        "board": {
            "rows": rows,
            "columns": columns,
            "cells": board_cells,
            "decoy_marks": decoy_marks,
            "palette": palette,
        },
        "pieces": copy.deepcopy(pieces),
        "requirements": {
            "piece_count": piece_count,
            "material_cells": total,
            "undo_budget": undo_budget,
            "exposure_rule": "A cut must touch the stock edge or the empty edge left by a previous cut.",
            "no_waste": "every original cell must belong to exactly one requested offcut",
        },
        "rules": {
            "direct": "Hold and trace through every cell of a connected requested silhouette, then release to cut it.",
            "proxy": "Select a requested silhouette, click its cells, then use EXTRACT SELECTED.",
            "recovery": "UNDO restores the most recent cut and consumes one recovery token.",
        },
    }
    public_state = copy.deepcopy(common)
    public_state["interaction"] = (condition or {}).get("interaction", "full")
    ground_truth = copy.deepcopy(common)
    ground_truth.update(
        {
            "seed": seed,
            "difficulty": difficulty,
            "parameters": copy.deepcopy(parameters),
            "placements": placements,
            "initial_cells": [cell["id"] for cell in board_cells],
            "solution_order": [piece["id"] for piece in pieces],
        }
    )
    if condition:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
