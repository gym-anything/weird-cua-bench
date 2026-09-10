"""Deterministic particle-field worlds for Ember Mosaic.

The browser and the independent grader both implement the small, deliberately
auditable cellular automaton described by this generator.  The public grid is
the visible world; the hidden copy additionally records the target predicate
and the seeded replay inputs used by the verifier.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from typing import Any


MECHANIC_ID = "ember_mosaic"
WIDTH = 72
HEIGHT = 42

BASELINE = {
    "width": WIDTH,
    "height": HEIGHT,
    "target_region_count": 3,
    "patch_radius": 4,
    "oil_pocket_count": 3,
    "fire_source_count": 2,
    "brush_radius": 1,
    "tick_ms": 200,
    "fire_lifetime": 6,
    "stone_erosion_ticks": 5,
    "flow_bias": 1,
    "oil_heat_ticks": 3,
}


def _seed_int(seed: str) -> int:
    return int(hashlib.sha256(f"{seed}|ember-mosaic-v1".encode()).hexdigest()[:16], 16)


def _idx(x: int, y: int, width: int = WIDTH) -> int:
    return y * width + x


def _inside(x: int, y: int, width: int, height: int) -> bool:
    return 1 <= x < width - 1 and 1 <= y < height - 1


def _path_y(x: int, phase: float, height: int) -> int:
    return int(round(height / 2 + 4 * math.sin(x / 6.1 + phase) + 1.5 * math.sin(x / 2.9 + phase * 0.4)))


def _paint_cell(grid: list[str], x: int, y: int, value: str, width: int, height: int) -> None:
    if _inside(x, y, width, height):
        grid[_idx(x, y, width)] = value


def _patch_cells(cx: int, cy: int, radius: int, rng: random.Random) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius - 1, radius + 2):
            ellipse = (dx / max(1.0, radius + 1.0)) ** 2 + (dy / max(1.0, radius)) ** 2
            if ellipse <= 1.0:
                cells.append((cx + dx, cy + dy))
    return cells


def _add_oil(grid: list[str], cx: int, cy: int, width: int, height: int) -> list[int]:
    coords: list[tuple[int, int]] = []
    for dy in range(-1, 2):
        for dx in range(-1, 2):
            x, y = cx + dx, cy + dy
            if not _inside(x, y, width, height) or grid[_idx(x, y, width)] not in {".", "a"}:
                return []
            coords.append((x, y))
    for x, y in coords:
        _paint_cell(grid, x, y, "o", width, height)
    return [_idx(x, y, width) for x, y in coords]


def _params(task: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    condition = task.get("_control_condition") or (task.get("metadata") or {}).get("control_condition")
    params = dict(BASELINE)
    params.update((condition or {}).get("difficulty_parameters") or {})
    expected = {
        "target_region_count": {1, 2, 3, 4},
        "patch_radius": {2, 3, 4, 5},
        "oil_pocket_count": {1, 2, 3, 4},
        "fire_source_count": {1, 2, 3},
        "brush_radius": {1, 2, 3},
        "tick_ms": {170, 200, 240, 260, 320},
        "fire_lifetime": {5, 6, 7, 8},
        "stone_erosion_ticks": {4, 5, 6, 8, 10},
        "flow_bias": {-1, 1},
        "oil_heat_ticks": {3},
    }
    for key, values in expected.items():
        if params.get(key) not in values:
            raise ValueError(f"unsupported Ember Mosaic parameter {key}={params.get(key)!r}")
    if params.get("width") != WIDTH or params.get("height") != HEIGHT:
        raise ValueError("Ember Mosaic uses its fixed visible canvas grid")
    return params, copy.deepcopy(condition) if condition else None


def _world(task: dict[str, Any], seed: str) -> dict[str, Any]:
    params, condition = _params(task)
    width, height = int(params["width"]), int(params["height"])
    rng = random.Random(_seed_int(seed))
    grid = ["."] * (width * height)
    for y in range(height):
        for x in range(width):
            if x in {0, width - 1} or y in {0, height - 1}:
                grid[_idx(x, y, width)] = "#"

    phase = rng.uniform(-1.2, 1.2)
    path = [(x, _path_y(x, phase, height)) for x in range(4, width - 4)]
    for x, y in path:
        for dy in (-1, 0, 1):
            _paint_cell(grid, x, y + dy, "p", width, height)
        # A few roots make the connected patches look grown rather than tiled.
        if x % 5 == 0:
            _paint_cell(grid, x, y + 2, "p", width, height)

    target_count = int(params["target_region_count"])
    radius = int(params["patch_radius"])
    patch_centers: list[tuple[int, int]] = []
    region_cells: dict[str, list[int]] = {}
    usable_start, usable_end = 12, width - 13
    for region_index in range(target_count):
        fraction = region_index / max(1, target_count - 1)
        cx = int(round(usable_start + fraction * (usable_end - usable_start)))
        cy = _path_y(cx, phase, height)
        patch_centers.append((cx, cy))
        region_id = f"ember-{region_index + 1}"
        cells: list[int] = []
        for x, y in _patch_cells(cx, cy, radius, rng):
            if not _inside(x, y, width, height) or grid[_idx(x, y, width)] == "#":
                continue
            _paint_cell(grid, x, y, "p", width, height)
            cells.append(_idx(x, y, width))
        region_cells[region_id] = sorted(set(cells))

    # Place protected oil off the connected target route.  Each pocket has one
    # plant spur and a visible gate cell between that spur and the oil.  A gate
    # is deliberately non-target plant: replacing it with a real solid brush
    # blocks the hazard without erasing a target region.
    candidates = list(range(6, width - 6, 2))
    rng.shuffle(candidates)
    oil_pockets: list[dict[str, Any]] = []
    gate_cells: list[int] = []
    hot_branch_cells: list[int] = []
    chosen_x: list[int] = []
    for x in candidates:
        if len(oil_pockets) >= int(params["oil_pocket_count"]):
            break
        if any(abs(x - other) < 3 for other in chosen_x):
            continue
        main_y = _path_y(x, phase, height)
        # Keep the baffle off the three-cell-wide main route even when the
        # broad L1 brush is used.  The spur continues one cell beyond the
        # gate, so an unprotected pocket remains causally reachable while a
        # correctly placed baffle still isolates it.
        gate_distance = int(params["brush_radius"]) + 3
        preferred_side = -1 if len(oil_pockets) % 2 == 0 else 1
        for side in (preferred_side, -preferred_side):
            gate_y = main_y + side * gate_distance
            oil_y = main_y + side * (gate_distance + 3)
            if not _inside(x, oil_y, width, height):
                continue
            gate_index = _idx(x, gate_y, width)
            if grid[gate_index] == "#" or any(gate_index in cells for cells in region_cells.values()):
                continue
            if any(
                (branch_cell % width - x) ** 2 + (branch_cell // width - gate_y) ** 2
                <= int(params["brush_radius"]) ** 2
                for branch_cell in hot_branch_cells
            ):
                # Later gates must not accidentally seal the deliberately
                # ungated hot branch with their own brush footprint.
                continue
            spur_distances = range(1, gate_distance + 2)
            spur = [_idx(x, main_y + side * distance, width) for distance in spur_distances]
            if any(not _inside(x, main_y + side * distance, width, height) for distance in spur_distances):
                continue
            if any(grid[cell] == "#" or any(cell in cells for cells in region_cells.values()) for cell in spur):
                continue
            oil_coords = [(x + dx, oil_y + dy) for dy in range(-1, 2) for dx in range(-1, 2)]
            oil_touches_existing_plant = False
            for ox, oy in oil_coords:
                for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                    nx, ny = ox + dx, oy + dy
                    if _inside(nx, ny, width, height) and grid[_idx(nx, ny, width)] == "p":
                        oil_touches_existing_plant = True
            if oil_touches_existing_plant:
                continue
            bypass_cells: list[int] = []
            if not oil_pockets:
                # The first pocket has a visible, ungated hot branch.  It is
                # deliberately one cell beside the pocket, so fire can heat
                # the oil through a real plant path instead of being stopped
                # by the visible gate.  A short heat window gives an operator
                # time to cool the adjacent flame with water.
                brush_radius = int(params["brush_radius"])
                for side_offset in (-1, 1):
                    near_x = x + side_offset * 2
                    outer_x = x + side_offset * (brush_radius + 4)
                    if not (1 <= near_x < width - 1 and 4 <= outer_x <= width - 5):
                        continue
                    branch_y = _path_y(outer_x, phase, height)
                    branch_step = 1 if branch_y >= oil_y else -1
                    horizontal = range(near_x, outer_x + side_offset, side_offset)
                    vertical = range(oil_y, branch_y + branch_step, branch_step)
                    candidate_coords = [(column, oil_y) for column in horizontal]
                    candidate_coords.extend((outer_x, row) for row in vertical)
                    candidate_branch = [_idx(column, row, width) for column, row in candidate_coords]
                    gate_positions = [
                        (gate % width, gate // width)
                        for gate in (*gate_cells, gate_index)
                    ]
                    if any(
                        (column - gate_x) ** 2 + (row - gate_y) ** 2 <= brush_radius ** 2
                        for column, row in candidate_coords
                        for gate_x, gate_y in gate_positions
                    ):
                        continue
                    if any(
                        not _inside(column, row, width, height)
                        or grid[cell] == "#"
                        or grid[cell] == "o"
                        or any(cell in cells for cells in region_cells.values())
                        for (column, row), cell in zip(candidate_coords, candidate_branch)
                    ):
                        continue
                    bypass_cells = candidate_branch
                    break
                if not bypass_cells:
                    continue
            oil_cells = _add_oil(grid, x, oil_y, width, height)
            if len(oil_cells) != 9:
                continue
            for cell in spur:
                grid[cell] = "p"
            for cell in bypass_cells:
                grid[cell] = "p"
            hot_branch_cells.extend(bypass_cells)
            pocket_id = f"oil-{len(oil_pockets) + 1}"
            oil_pockets.append({
                "id": pocket_id,
                "center": [x, oil_y],
                "cells": oil_cells,
                "side": side,
                "hot_branch": bool(bypass_cells),
            })
            gate_cells.append(gate_index)
            chosen_x.append(x)
            break

    if len(oil_pockets) != int(params["oil_pocket_count"]):
        raise ValueError("could not place the requested oil pockets")

    # Sources are on the route, but kept out of the visible target patches so
    # every target must be reached through a changing front.
    source_candidates = [x for x, _ in path if 5 <= x <= width - 8]
    rng.shuffle(source_candidates)
    fire_sources: list[int] = []
    for x in source_candidates:
        y = _path_y(x, phase, height)
        index = _idx(x, y, width)
        if index in gate_cells or any(index in cells for cells in region_cells.values()):
            continue
        if grid[index] == "p":
            grid[index] = "f"
            fire_sources.append(index)
        if len(fire_sources) >= int(params["fire_source_count"]):
            break
    if len(fire_sources) != int(params["fire_source_count"]):
        raise ValueError("could not place the requested fire sources")

    target_regions = list(region_cells)
    target_cells = sorted({cell for region in target_regions for cell in region_cells[region]})
    # A small empty basin makes the movement of water and sand visible without
    # changing the target route.  It is public geometry, not a hidden hint.
    basin = {"x": width - 9, "y": height - 5, "w": 6, "h": 3}
    for y in range(basin["y"], basin["y"] + basin["h"]):
        for x in range(basin["x"], basin["x"] + basin["w"]):
            if _inside(x, y, width, height) and grid[_idx(x, y, width)] == ".":
                grid[_idx(x, y, width)] = "a"

    return {
        "width": width,
        "height": height,
        "grid": grid,
        "region_grid": {
            str(index): region_id
            for region_id, cells in region_cells.items()
            for index in cells
        },
        "region_cells": region_cells,
        "target_regions": target_regions,
        "target_cells": target_cells,
        "oil_pockets": oil_pockets,
        "gate_cells": gate_cells,
        "hot_branch_cells": sorted(set(hot_branch_cells)),
        "fire_sources": fire_sources,
        "basin": basin,
        "phase": round(phase, 6),
        "flow_bias": int(params["flow_bias"]),
        "parameters": params,
        "seed_fingerprint": hashlib.sha256(f"{seed}|ember-world".encode()).hexdigest()[:12],
        "control_condition": condition,
    }


def generate(task: dict[str, Any], seed: str):
    world = _world(task, seed)
    condition = world["control_condition"]
    challenge_id = hashlib.sha256(
        (str(seed) + str(task["id"]) + json.dumps(condition, sort_keys=True, separators=(",", ":"))).encode()
    ).hexdigest()[:20]
    identity = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "challenge_id": challenge_id,
        "control_condition": copy.deepcopy(condition),
    }
    public_world = copy.deepcopy(world)
    public_world.pop("control_condition", None)
    public = {
        **identity,
        **public_world,
        "title": "Ember Mosaic",
        "prompt": "Burn every marked plant patch. Keep every protected oil pocket unlit.",
        "asset_manifest": "shared_runtime/assets/provenance/ember_mosaic_v0.json",
        "generator": {
            "name": "ember_mosaic_cellular_field_v1",
            "variant_count": 2**48,
            "world_fingerprint": world["seed_fingerprint"],
        },
    }
    truth = {
        **identity,
        "world": copy.deepcopy(world),
        "target_cells": list(world["target_cells"]),
        "gate_cells": list(world["gate_cells"]),
        "oil_cells": [cell for pocket in world["oil_pockets"] for cell in pocket["cells"]],
        "replay_contract": {
            "materials": ["water", "sand", "stone"],
            "sources": {"full": "freehand_brush", "simplified": "stamp_controls"},
            "submit_source": "certify_button",
        },
    }
    return public, truth
