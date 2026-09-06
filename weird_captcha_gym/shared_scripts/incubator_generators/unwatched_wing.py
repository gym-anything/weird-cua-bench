from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "unwatched_wing"
GRID_WIDTH = 19
GRID_HEIGHT = 13

LAYOUTS: dict[str, dict[str, Any]] = {
    "introductory": {
        "route": ((1, 10), (7, 10), (7, 6), (16, 6)),
        "target_cells": ((2, 10), (6, 10), (7, 7)),
        "dock_cell": (15, 6),
        "decoy_cells": ((4, 9), (10, 7), (13, 5)),
    },
    "elbow": {
        "route": ((1, 10), (6, 10), (6, 6), (12, 6), (12, 3), (17, 3)),
        "target_cells": ((2, 10), (6, 8), (9, 6), (12, 4)),
        "dock_cell": (16, 3),
        "decoy_cells": ((4, 11), (9, 7), (14, 4)),
    },
    "zigzag": {
        "route": ((1, 10), (6, 10), (6, 7), (12, 7), (12, 3), (8, 3), (17, 3)),
        "target_cells": ((2, 10), (6, 8), (9, 7), (12, 4), (10, 3)),
        "dock_cell": (16, 3),
        "decoy_cells": ((4, 11), (9, 8), (14, 4), (6, 4)),
    },
    "current": {
        "route": ((1, 10), (6, 10), (6, 7), (12, 7), (12, 3), (8, 3), (17, 3)),
        "target_cells": ((2, 10), (6, 8), (9, 7), (12, 4), (10, 3), (15, 3)),
        "dock_cell": (17, 3),
        "decoy_cells": ((4, 11), (9, 8), (14, 4), (6, 4)),
    },
    "labyrinth": {
        "route": ((1, 11), (5, 11), (5, 8), (10, 8), (10, 4), (6, 4), (6, 1), (14, 1), (14, 5), (17, 5)),
        "target_cells": ((2, 11), (5, 9), (8, 8), (10, 5), (7, 4), (6, 2), (12, 1)),
        "dock_cell": (17, 5),
        "decoy_cells": ((3, 10), (8, 9), (11, 3), (8, 2), (15, 4)),
    },
}

EXHIBITS = (
    {"name": "GLASS HERON", "glyph": "heron", "color": "#7fe3db", "accent": "#f4d98b"},
    {"name": "CROWNED MOTH", "glyph": "moth", "color": "#d79af2", "accent": "#ffd37a"},
    {"name": "HOLLOW STAG", "glyph": "stag", "color": "#e6a36e", "accent": "#98e5c8"},
    {"name": "TWIN COMET", "glyph": "comet", "color": "#8db8ff", "accent": "#f6ecb0"},
    {"name": "SLEEPING ORRERY", "glyph": "orrery", "color": "#ee8e9f", "accent": "#b8ddff"},
    {"name": "BONE LANTERN", "glyph": "lantern", "color": "#dfcfad", "accent": "#73d5ff"},
    {"name": "VEILED IBIS", "glyph": "ibis", "color": "#91d799", "accent": "#f1b4df"},
    {"name": "SALT CROWN", "glyph": "crown", "color": "#d6b56f", "accent": "#9de9ee"},
)

PALETTES = (
    {"name": "verdigris", "void": "#050708", "wall": "#31413e", "wall_alt": "#59605a", "floor": "#171b1a", "brass": "#d8b86f", "signal": "#77e0d3"},
    {"name": "ultraviolet", "void": "#06050a", "wall": "#393646", "wall_alt": "#655d68", "floor": "#19171e", "brass": "#d5b675", "signal": "#9dd8ff"},
    {"name": "umber", "void": "#090705", "wall": "#443b32", "wall_alt": "#6d6255", "floor": "#1c1814", "brass": "#e0bd75", "signal": "#86ddc6"},
    {"name": "blue_hour", "void": "#04080b", "wall": "#2b3e49", "wall_alt": "#52626b", "floor": "#121a1e", "brass": "#d9b46b", "signal": "#75d8ff"},
)


def _seed_int(seed: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{MECHANIC_ID}|v1".encode("utf-8")).digest()[:8], "big")


def _transform(cell: tuple[int, int], mode: int) -> tuple[int, int]:
    x, y = cell
    if mode == 1:
        return GRID_WIDTH - 1 - x, y
    if mode == 2:
        return x, GRID_HEIGHT - 1 - y
    if mode == 3:
        return GRID_WIDTH - 1 - x, GRID_HEIGHT - 1 - y
    return x, y


def _cells_between(first: tuple[int, int], second: tuple[int, int]) -> list[tuple[int, int]]:
    if first[0] != second[0] and first[1] != second[1]:
        raise ValueError("museum route segment must be axis aligned")
    dx = 0 if first[0] == second[0] else (1 if second[0] > first[0] else -1)
    dy = 0 if first[1] == second[1] else (1 if second[1] > first[1] else -1)
    output: list[tuple[int, int]] = []
    current = first
    while True:
        output.append(current)
        if current == second:
            return output
        current = current[0] + dx, current[1] + dy


def _expanded_route(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    output: list[tuple[int, int]] = []
    for first, second in zip(points, points[1:]):
        segment = _cells_between(first, second)
        if output:
            segment = segment[1:]
        output.extend(segment)
    return output


def _center(cell: tuple[int, int]) -> list[float]:
    return [round(cell[0] + 0.5, 4), round(cell[1] + 0.5, 4)]


def _build_map(route: list[tuple[int, int]], feature_cells: list[tuple[int, int]]) -> list[str]:
    walkable: set[tuple[int, int]] = set()
    for cell in route:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                candidate = cell[0] + dx, cell[1] + dy
                if 0 < candidate[0] < GRID_WIDTH - 1 and 0 < candidate[1] < GRID_HEIGHT - 1:
                    walkable.add(candidate)
    for cell in feature_cells:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                candidate = cell[0] + dx, cell[1] + dy
                if 0 < candidate[0] < GRID_WIDTH - 1 and 0 < candidate[1] < GRID_HEIGHT - 1:
                    walkable.add(candidate)
    return [
        "".join("." if (x, y) in walkable else "#" for x in range(GRID_WIDTH))
        for y in range(GRID_HEIGHT)
    ]


def _heading_mdeg(first: tuple[int, int], second: tuple[int, int]) -> int:
    return round(math.degrees(math.atan2(second[1] - first[1], second[0] - first[0])) * 1000) % 360_000


def _varied_target_indices(
    rng: random.Random,
    route: list[tuple[int, int]],
    anchors: list[int],
    dock_index: int,
    required_pin_steps: list[int],
    hand_lamp_range: float,
) -> list[int]:
    """Choose ordered target sites while retaining the authored route profile."""
    last_occurrence = {cell: index for index, cell in enumerate(route)}
    ranges: list[list[int]] = []
    for index, anchor in enumerate(anchors):
        lower = 1 if index == 0 else (anchors[index - 1] + anchor) // 2 + 1
        upper = dock_index - 1 if index == len(anchors) - 1 else (anchor + anchors[index + 1]) // 2
        choices = [candidate for candidate in range(lower, upper + 1) if last_occurrence[route[candidate]] == candidate]
        ranges.append(choices or [anchor])
    for _attempt in range(512):
        selected = [rng.choice(choices) for choices in ranges]
        if all(
            math.dist(route[selected[step]], route[selected[step + 1]]) > hand_lamp_range + .5
            for step in required_pin_steps
        ):
            return selected
    # The authored anchor configuration is validated and remains a deterministic
    # safety fallback if an unusually tight future control profile is introduced.
    return anchors


def _varied_decoy_cells(
    rng: random.Random,
    route: list[tuple[int, int]],
    occupied: set[tuple[int, int]],
    protected_targets: list[tuple[int, int]],
    count: int,
) -> list[tuple[int, int]]:
    if count == 0:
        return []
    candidates = {
        (cell[0] + dx, cell[1] + dy)
        for cell in route
        for dx, dy in ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))
        if 0 < cell[0] + dx < GRID_WIDTH - 1
        and 0 < cell[1] + dy < GRID_HEIGHT - 1
        and (cell[0] + dx, cell[1] + dy) not in occupied
        and (cell[0] + dx, cell[1] + dy) not in route
        and all(
            math.dist((cell[0] + dx, cell[1] + dy), target) >= 2.25
            and cell[0] + dx != target[0]
            and cell[1] + dy != target[1]
            for target in protected_targets
        )
    }
    ordered = sorted(candidates)
    rng.shuffle(ordered)
    selected: list[tuple[int, int]] = []
    for candidate in ordered:
        if all(math.dist(candidate, existing) >= 1.5 for existing in selected):
            selected.append(candidate)
            if len(selected) == count:
                return selected
    raise ValueError("museum route does not provide enough separated decoy sites")


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed_int(seed))
    condition = task.get("_control_condition")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    layout_profile = str(parameters.get("layout_profile", "current"))
    layout = LAYOUTS.get(layout_profile)
    if layout is None:
        raise ValueError(f"unknown Unwatched Wing layout profile {layout_profile!r}")

    target_positions = int(parameters.get("target_positions", 6))
    decoy_count = int(parameters.get("decoy_count", 2))
    required_pin_steps = [int(value) for value in parameters.get("required_pin_steps", [1, 3])]
    ambient_steps = [int(value) for value in parameters.get("ambient_steps", [2, 5])]
    field_of_view_deg = float(parameters.get("field_of_view_deg", 78.0))
    hand_lamp_range = float(parameters.get("hand_lamp_range", 1.7))
    probe_range = float(parameters.get("probe_range", 5.5))
    move_step = float(parameters.get("move_step", 0.34))
    if target_positions != len(layout["target_cells"]):
        raise ValueError("target position count does not match the selected museum layout")
    if not 0 <= decoy_count <= len(layout["decoy_cells"]):
        raise ValueError("decoy count exceeds the selected museum layout")
    if any(value < 0 or value >= target_positions - 1 for value in required_pin_steps):
        raise ValueError("probe-required handoff lies outside the target path")
    if any(value < 0 or value >= target_positions for value in ambient_steps):
        raise ValueError("ambient exhibit light lies outside the target path")
    if not 58 <= field_of_view_deg <= 96 or not 1.2 <= hand_lamp_range <= 3.0 or not 3.5 <= probe_range <= 7.5:
        raise ValueError("observation controls lie outside supported bounds")
    if not .24 <= move_step <= .5:
        raise ValueError("movement step lies outside supported bounds")

    base_route = _expanded_route(list(layout["route"]))
    base_route_index = {cell: index for index, cell in enumerate(base_route)}
    base_anchors = [base_route_index[cell] for cell in layout["target_cells"]]
    base_dock_index = base_route_index[layout["dock_cell"]]
    for _placement_attempt in range(512):
        target_indices = _varied_target_indices(
            rng,
            base_route,
            base_anchors,
            base_dock_index,
            required_pin_steps,
            hand_lamp_range,
        )
        base_target_cells = [base_route[index] for index in target_indices]
        try:
            base_decoy_cells = _varied_decoy_cells(
                rng,
                base_route,
                set(base_target_cells + [layout["dock_cell"]]),
                base_target_cells,
                decoy_count,
            )
            break
        except ValueError:
            continue
    else:
        raise ValueError("museum route could not place separated target and decoy sites")
    transform_mode = rng.randrange(4)
    route_control = [_transform(cell, transform_mode) for cell in layout["route"]]
    route = _expanded_route(route_control)
    target_cells = [_transform(cell, transform_mode) for cell in base_target_cells]
    dock_cell = _transform(layout["dock_cell"], transform_mode)
    decoy_cells = [_transform(cell, transform_mode) for cell in base_decoy_cells]
    museum_map = _build_map(route, target_cells + decoy_cells + [dock_cell])

    target_plinths = []
    for index, cell in enumerate(target_cells):
        target_plinths.append({
            "id": f"plinth-{index + 1:02d}",
            "label": f"W{index + 1:02d}",
            "cell": list(cell),
            "center": _center(cell),
            "kind": "transfer",
            "probe_threshold": index in required_pin_steps,
        })
    decoy_plinths = []
    for index, cell in enumerate(decoy_cells):
        decoy_plinths.append({
            "id": f"archive-{index + 1:02d}",
            "label": f"A{index + 1:02d}",
            "cell": list(cell),
            "center": _center(cell),
            "kind": "archive",
        })
    dock = {"id": "dock-00", "label": "DOCK 00", "cell": list(dock_cell), "center": _center(dock_cell), "kind": "dock"}

    exhibit_styles = rng.sample(list(EXHIBITS), decoy_count + 1)
    target_style = copy.deepcopy(exhibit_styles[0])
    target_id = f"unstable-{hashlib.sha256(f'{seed}|target'.encode()).hexdigest()[:8]}"
    target_exhibit = {
        "id": target_id,
        **target_style,
        "unstable": True,
        "plinth_id": target_plinths[0]["id"],
    }
    decoy_exhibits = []
    for index, (style, plinth) in enumerate(zip(exhibit_styles[1:], decoy_plinths), start=1):
        decoy_exhibits.append({
            "id": f"stable-{hashlib.sha256(f'{seed}|decoy|{index}'.encode()).hexdigest()[:8]}",
            **copy.deepcopy(style),
            "unstable": False,
            "plinth_id": plinth["id"],
        })

    wall_lights = []
    for index, step in enumerate(ambient_steps, start=1):
        plinth = target_plinths[step]
        cx, cy = plinth["center"]
        wall_lights.append({
            "id": f"gallery-light-{index:02d}",
            "label": f"ISOLATOR {index:02d}",
            "plinth_id": plinth["id"],
            "center": [round(cx + (0.34 if index % 2 else -0.34), 4), round(cy - 0.34, 4)],
            "enabled": True,
            "radius": 0.86,
        })

    route_index = {cell: index for index, cell in enumerate(route)}
    if any(cell not in route_index for cell in target_cells + [dock_cell]):
        raise ValueError("a generated target pedestal is disconnected from the museum route")
    target_route_indices = [route_index[cell] for cell in target_cells]
    dock_route_index = route_index[dock_cell]
    if target_route_indices != sorted(target_route_indices) or dock_route_index < target_route_indices[-1]:
        raise ValueError("target pedestals are not ordered along the museum route")
    for step in required_pin_steps:
        if math.dist(_center(target_cells[step]), _center(target_cells[step + 1])) <= hand_lamp_range + .5:
            raise ValueError("probe handoff does not leave the hand-lamp radius")

    controls = {
        "move_step": move_step,
        "player_radius": 0.2,
        "turn_button_mdeg": 15_000,
        "field_of_view_deg": field_of_view_deg,
        "visible_range": 14.0,
        "hand_lamp_range": hand_lamp_range,
        "probe_range": probe_range,
        "probe_aim_tolerance_deg": 8.0,
        "breaker_range": 1.15,
        "entangle_radius": 0.62,
        "release_radius": 0.82,
    }
    contract = {
        "map": museum_map,
        "world": {"width": GRID_WIDTH, "height": GRID_HEIGHT},
        "initial_pose": {
            "x": _center(route[0])[0],
            "y": _center(route[0])[1],
            "angle_mdeg": _heading_mdeg(route[0], target_cells[0]),
        },
        "controls": controls,
        "plinths": target_plinths + decoy_plinths,
        "target_path": [item["id"] for item in target_plinths],
        "dock": dock,
        "wall_lights": wall_lights,
        "required_pin_steps": required_pin_steps,
        "target_exhibit": target_exhibit,
        "decoy_exhibits": decoy_exhibits,
    }

    condition_token = f"|d{condition['difficulty']}" if condition else "|baseline"
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|museum-v1{condition_token}".encode("utf-8")).hexdigest()[:14]
    task_id = str(task.get("id") or "unwatched_wing_seed_0001@0.1")
    palette = copy.deepcopy(rng.choice(PALETTES))
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "asset_manifest": "shared_runtime/assets/provenance/unwatched_wing_v0.json",
        "prompt": f"Register {target_style['name']} in Dock 00. Observation is restraint.",
        "target_dossier": target_style,
        "palette": palette,
        "generator": {
            "name": "procedural_unwatched_museum_v1",
            "variation_axes": [
                "ordered target sites along the active route",
                "decoy positions beside the route",
                "target-linked isolator positions",
                "four spatial transforms",
                "four palettes",
                "original exhibit-form assignments",
            ],
            "decision_graph_note": "Target, decoy, isolator, and probe-handoff coordinates are seed-dependent inputs to browser and server replay.",
        },
        **copy.deepcopy(contract),
        "rules": [
            "An unstable exhibit changes plinth the instant the viewport, live probe viewer, and every light all release it.",
            "A split-arrow threshold is crossed by keeping the old plinth live in the probe viewer while walking beyond the turn.",
            "Dock 00 opens only when you stand on the exhibit pedestal and remove the lamp, probe, viewer, and every visible stray light.",
        ],
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "palette": copy.deepcopy(palette),
        **copy.deepcopy(contract),
        "solution": {
            "route_points": [_center(cell) for cell in route],
            "target_route_indices": target_route_indices,
            "dock_route_index": dock_route_index,
            "target_id": target_id,
        },
        "browser_boundary": "The browser receives the geometry and deterministic observation rules required to render and simulate the wing. The server independently replays every movement, sight line, light, probe handoff, jump, and darkness condition.",
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
