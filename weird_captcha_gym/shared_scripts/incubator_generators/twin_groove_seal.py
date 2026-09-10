"""Seeded, original twin-plate groove puzzles.

The source mechanic is the polar-control model in kyp44/hanayama-solutions' Cast Laby model.  This generator keeps the useful invariant—a rigid shoe whose
two contacts are moved through two simultaneous circular constraints—while
building fresh procedural plates rather than redistributing the source's
scanned artwork or code.
"""
from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "twin_groove_seal"
PLATE_CENTERS = ((320.0, 350.0), (960.0, 350.0))
PLATE_RADIUS = 246.0
MIN_RADIUS = 60.0
RING_SPACING = 30.0
NUB_DISTANCE = 400.0
NUB_RADIUS = 9.0

BASELINE_PARAMETERS: dict[str, Any] = {
    "rings": 5,
    "sectors": 24,
    "route_steps": 18,
    "branch_count": 3,
    "branch_length": 5,
    "radial_step": 9.0,
    "angular_step_deg": 8.0,
    "rotation_step_deg": 8.0,
    "open_buffer": 1,
    "exit_tolerance_cells": 1,
    "max_actions": 60,
    "show_polar_readout": True,
    "show_grid": True,
}

ACTION_NAMES = (
    "radial_in",
    "radial_out",
    "angular_cw",
    "angular_ccw",
    "rotate_cw",
    "rotate_ccw",
)
ORIGINS = ("rear", "tip")


def _seed_int(seed: str, salt: str) -> int:
    return int.from_bytes(
        hashlib.sha256(f"{MECHANIC_ID}|{seed}|{salt}".encode("utf-8")).digest()[:8],
        "big",
    )


def _profile(task: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    condition = copy.deepcopy(task.get("_control_condition") or None)
    parameters = dict(BASELINE_PARAMETERS)
    if condition:
        parameters.update(dict(condition.get("difficulty_parameters") or {}))
    parameters["rings"] = int(parameters["rings"])
    parameters["sectors"] = int(parameters["sectors"])
    parameters["route_steps"] = int(parameters["route_steps"])
    parameters["branch_count"] = int(parameters["branch_count"])
    parameters["branch_length"] = int(parameters["branch_length"])
    parameters["radial_step"] = float(parameters["radial_step"])
    parameters["angular_step_deg"] = float(parameters["angular_step_deg"])
    parameters["rotation_step_deg"] = float(parameters["rotation_step_deg"])
    parameters["open_buffer"] = int(parameters["open_buffer"])
    parameters["exit_tolerance_cells"] = int(parameters["exit_tolerance_cells"])
    parameters["max_actions"] = int(parameters["max_actions"])
    parameters["show_polar_readout"] = bool(parameters["show_polar_readout"])
    parameters["show_grid"] = bool(parameters["show_grid"])
    if not 4 <= parameters["rings"] <= 8:
        raise ValueError("twin-groove ring count is outside supported limits")
    if not 12 <= parameters["sectors"] <= 48:
        raise ValueError("twin-groove sector count is outside supported limits")
    if not 6 <= parameters["route_steps"] <= 48:
        raise ValueError("twin-groove route length is outside supported limits")
    if not 0 <= parameters["branch_count"] <= 9 or not 2 <= parameters["branch_length"] <= 9:
        raise ValueError("twin-groove branch parameters are outside supported limits")
    if not 2.0 <= parameters["radial_step"] <= 18.0:
        raise ValueError("twin-groove radial step is outside supported limits")
    if not 2.0 <= parameters["angular_step_deg"] <= 18.0:
        raise ValueError("twin-groove angular step is outside supported limits")
    if not 2.0 <= parameters["rotation_step_deg"] <= 18.0:
        raise ValueError("twin-groove rotation step is outside supported limits")
    if not 0 <= parameters["open_buffer"] <= 2:
        raise ValueError("twin-groove open buffer is outside supported limits")
    if not 0 <= parameters["exit_tolerance_cells"] <= 2:
        raise ValueError("twin-groove exit tolerance is outside supported limits")
    if parameters["max_actions"] < parameters["route_steps"] + 3:
        raise ValueError("twin-groove action budget is too small for the route")
    return condition, parameters


def _norm_angle(angle: float) -> float:
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def _angle_delta(a: float, b: float) -> float:
    return _norm_angle(a - b)


def _polar_xy(polar: list[float], center: tuple[float, float]) -> tuple[float, float]:
    radius, angle = polar
    return center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle)


def _xy_polar(point: tuple[float, float], center: tuple[float, float]) -> list[float]:
    dx = point[0] - center[0]
    dy = point[1] - center[1]
    return [math.hypot(dx, dy), _norm_angle(math.atan2(dy, dx))]


def _copy_state(state: dict[str, list[float]]) -> dict[str, list[float]]:
    return {"rear": list(state["rear"]), "tip": list(state["tip"])}


def _valid_radius(radius: float, parameters: dict[str, Any]) -> bool:
    maximum = MIN_RADIUS + (int(parameters["rings"]) - 1) * RING_SPACING
    return MIN_RADIUS - 1e-6 <= radius <= maximum + 1e-6


def _choose_other_angle(
    active_xy: tuple[float, float],
    other: list[float],
    other_center: tuple[float, float],
) -> list[float] | None:
    other_radius = float(other[0])
    dx = active_xy[0] - other_center[0]
    dy = active_xy[1] - other_center[1]
    distance = math.hypot(dx, dy)
    if distance < 1e-6 or other_radius < 1e-6:
        return None
    cosine = (distance * distance + other_radius * other_radius - NUB_DISTANCE * NUB_DISTANCE) / (2.0 * distance * other_radius)
    if cosine < -1.000001 or cosine > 1.000001:
        return None
    base = math.atan2(dy, dx)
    offset = math.acos(max(-1.0, min(1.0, cosine)))
    candidates = [base + offset, base - offset]
    selected = min(candidates, key=lambda angle: abs(_angle_delta(angle, float(other[1]))))
    return [other_radius, _norm_angle(selected)]


def apply_action(
    state: dict[str, list[float]],
    origin: str,
    action: str,
    parameters: dict[str, Any],
) -> dict[str, list[float]] | None:
    """Apply one source-style polar move, without checking the groove maps."""
    if origin not in ORIGINS or action not in ACTION_NAMES:
        return None
    next_state = _copy_state(state)
    other_origin = "tip" if origin == "rear" else "rear"
    active = next_state[origin]
    other = next_state[other_origin]
    if action == "radial_in":
        active[0] -= float(parameters["radial_step"])
    elif action == "radial_out":
        active[0] += float(parameters["radial_step"])
    elif action == "angular_cw":
        active[1] += math.radians(float(parameters["angular_step_deg"]))
    elif action == "angular_ccw":
        active[1] -= math.radians(float(parameters["angular_step_deg"]))
    if action in {"radial_in", "radial_out", "angular_cw", "angular_ccw"}:
        active[1] = _norm_angle(active[1])
        if not _valid_radius(float(active[0]), parameters):
            return None
        active_xy = _polar_xy(active, PLATE_CENTERS[0 if origin == "rear" else 1])
        solved = _choose_other_angle(
            active_xy,
            other,
            PLATE_CENTERS[1 if origin == "rear" else 0],
        )
        if solved is None:
            return None
        other[1] = solved[1]
    else:
        active_xy = _polar_xy(active, PLATE_CENTERS[0 if origin == "rear" else 1])
        other_xy = _polar_xy(other, PLATE_CENTERS[1 if origin == "rear" else 0])
        vx = other_xy[0] - active_xy[0]
        vy = other_xy[1] - active_xy[1]
        sign = 1.0 if action == "rotate_cw" else -1.0
        theta = sign * math.radians(float(parameters["rotation_step_deg"]))
        rotated = (
            active_xy[0] + vx * math.cos(theta) - vy * math.sin(theta),
            active_xy[1] + vx * math.sin(theta) + vy * math.cos(theta),
        )
        next_state[other_origin] = _xy_polar(
            rotated,
            PLATE_CENTERS[1 if origin == "rear" else 0],
        )
    if not _valid_radius(float(next_state["rear"][0]), parameters):
        return None
    if not _valid_radius(float(next_state["tip"][0]), parameters):
        return None
    return next_state


def _cell(point: tuple[float, float], center: tuple[float, float], parameters: dict[str, Any]) -> tuple[int, int]:
    radius = math.hypot(point[0] - center[0], point[1] - center[1])
    angle = math.atan2(point[1] - center[1], point[0] - center[0])
    ring = round((radius - MIN_RADIUS) / RING_SPACING)
    sector = int(((angle + math.pi) / (2.0 * math.pi)) * int(parameters["sectors"])) % int(parameters["sectors"])
    return max(0, min(int(parameters["rings"]) - 1, ring)), sector


def _near_cells(base: tuple[int, int], parameters: dict[str, Any], buffer: int) -> set[tuple[int, int]]:
    rings = int(parameters["rings"])
    sectors = int(parameters["sectors"])
    ring, sector = base
    result: set[tuple[int, int]] = set()
    for dr in range(-buffer, buffer + 1):
        for ds in range(-buffer, buffer + 1):
            candidate_ring = ring + dr
            if 0 <= candidate_ring < rings:
                result.add((candidate_ring, (sector + ds) % sectors))
    return result


def _state_points(state: dict[str, list[float]]) -> tuple[tuple[float, float], tuple[float, float]]:
    return _polar_xy(state["rear"], PLATE_CENTERS[0]), _polar_xy(state["tip"], PLATE_CENTERS[1])


def _route(
    rng: random.Random,
    parameters: dict[str, Any],
) -> tuple[dict[str, list[float]], list[dict[str, str]], list[dict[str, list[float]]]]:
    # Avoid the -pi/pi seam: rounded exported angles must not make the
    # rigid-link branch selector choose the mirror solution on the first move.
    start_angle = rng.choice((math.pi / 12.0, -math.pi / 12.0))
    center_distance = math.dist(*PLATE_CENTERS)
    start_radius = (center_distance - NUB_DISTANCE) / (2.0 * math.cos(start_angle))
    start = {
        "rear": [start_radius, start_angle],
        "tip": [start_radius, math.pi - start_angle],
    }
    steps = int(parameters["route_steps"])
    all_candidates = [(origin, action) for origin in ORIGINS for action in ACTION_NAMES]
    for _restart in range(120):
        current = _copy_state(start)
        actions: list[dict[str, str]] = []
        states = [_copy_state(current)]
        previous: tuple[str, str] | None = None
        for index in range(steps):
            candidates = all_candidates[:]
            rng.shuffle(candidates)
            preferred_origin = ORIGINS[index % 2]
            candidates.sort(key=lambda item: 0 if item[0] == preferred_origin else 1)
            picked: tuple[str, str] | None = None
            picked_state: dict[str, list[float]] | None = None
            for origin, action in candidates:
                if previous and origin == previous[0] and action.startswith("radial_") and previous[1].startswith("radial_"):
                    if action != previous[1]:
                        continue
                candidate_state = apply_action(current, origin, action, parameters)
                if candidate_state is None:
                    continue
                before_points = _state_points(current)
                after_points = _state_points(candidate_state)
                movement = sum(math.dist(a, b) for a, b in zip(before_points, after_points))
                if movement < 2.0:
                    continue
                picked = (origin, action)
                picked_state = candidate_state
                break
            if picked is None or picked_state is None:
                break
            current = picked_state
            actions.append({"origin": picked[0], "action": picked[1]})
            states.append(_copy_state(current))
            previous = picked
        if len(actions) == steps:
            start_points = _state_points(states[0])
            end_points = _state_points(states[-1])
            total_displacement = sum(math.dist(a, b) for a, b in zip(start_points, end_points))
            tolerance = int(parameters["exit_tolerance_cells"])
            # The visible and graded start is the six-decimal export, so use
            # that value for the no-immediate-win guard as well.  This avoids
            # an angular sector seam changing cell after JSON rounding.
            exported_start_points = _state_points(_round_state(states[0]))
            starts_in_goal_neighborhood = any(
                _cell(exported_start_points[index], PLATE_CENTERS[index], parameters)
                in _near_cells(
                    _cell(end_points[index], PLATE_CENTERS[index], parameters),
                    parameters,
                    tolerance,
                )
                for index in range(2)
            )
            if total_displacement >= 24.0 and not starts_in_goal_neighborhood:
                return states[0], actions, states
    raise RuntimeError("could not construct a coupled twin-groove route")


def _branch_cells(
    rng: random.Random,
    base_cells: set[tuple[int, int]],
    parameters: dict[str, Any],
) -> set[tuple[int, int]]:
    rings = int(parameters["rings"])
    sectors = int(parameters["sectors"])
    cells = set(base_cells)
    candidates = list(base_cells)
    for _ in range(int(parameters["branch_count"])):
        if not candidates:
            break
        current = rng.choice(candidates)
        length = rng.randint(2, int(parameters["branch_length"]))
        for _step in range(length):
            ring, sector = current
            options = []
            if ring > 0:
                options.append((ring - 1, sector))
            if ring + 1 < rings:
                options.append((ring + 1, sector))
            options.extend([(ring, (sector - 1) % sectors), (ring, (sector + 1) % sectors)])
            rng.shuffle(options)
            current = options[0]
            cells.add(current)
    return cells


def _plate_cells(
    rng: random.Random,
    states: list[dict[str, list[float]]],
    plate_index: int,
    parameters: dict[str, Any],
) -> tuple[list[list[int]], list[list[int]]]:
    center = PLATE_CENTERS[plate_index]
    buffer = int(parameters["open_buffer"])
    cells: set[tuple[int, int]] = set()
    for left, right in zip(states, states[1:]):
        left_point = _state_points(left)[plate_index]
        right_point = _state_points(right)[plate_index]
        for sample in range(25):
            t = sample / 24.0
            point = (
                left_point[0] + (right_point[0] - left_point[0]) * t,
                left_point[1] + (right_point[1] - left_point[1]) * t,
            )
            cells.update(_near_cells(_cell(point, center, parameters), parameters, buffer))
    cells.update(_near_cells(_cell(_state_points(states[0])[plate_index], center, parameters), parameters, buffer))
    cells.update(_near_cells(_cell(_state_points(states[-1])[plate_index], center, parameters), parameters, buffer))
    cells = _branch_cells(rng, cells, parameters)
    goal_cell = _cell(_state_points(states[-1])[plate_index], center, parameters)
    tolerance = int(parameters["exit_tolerance_cells"])
    exit_cells = _near_cells(goal_cell, parameters, tolerance)
    return [list(cell) for cell in sorted(cells)], [list(cell) for cell in sorted(exit_cells)]


def _round_state(state: dict[str, list[float]]) -> dict[str, list[float]]:
    return {
        key: [round(float(value[0]), 6), round(_norm_angle(float(value[1])), 6)]
        for key, value in state.items()
    }


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition, parameters = _profile(task)
    rng = random.Random(_seed_int(seed, "world"))
    start, solution_actions, states = _route(rng, parameters)
    plates = []
    for plate_index in range(2):
        open_cells, exit_cells = _plate_cells(rng, states, plate_index, parameters)
        plates.append(
            {
                "id": "rear-plate" if plate_index == 0 else "tip-plate",
                "center": list(PLATE_CENTERS[plate_index]),
                "radius": PLATE_RADIUS,
                "open_cells": open_cells,
                "exit_cells": exit_cells,
                "accent": rng.randrange(5),
            }
        )
    final_state = states[-1]
    task_id = str(task.get("id") or "twin_groove_seal_seed_0001@0.1")
    difficulty = int((condition or {}).get("difficulty") or 3)
    challenge_id = hashlib.sha256(
        f"{MECHANIC_ID}|{seed}|{task_id}|d{difficulty}".encode("utf-8")
    ).hexdigest()[:14]
    prompt = (
        task.get("natural_language")
        or "Walk both linked contacts through the engraved grooves, then release the shoe only when both exit channels are clear."
    )
    map_contract = {
        "min_radius": MIN_RADIUS,
        "ring_spacing": RING_SPACING,
        "rings": int(parameters["rings"]),
        "sectors": int(parameters["sectors"]),
        "plate_radius": PLATE_RADIUS,
        "nub_radius": NUB_RADIUS,
        "shoe_length": NUB_DISTANCE,
        "radial_step": float(parameters["radial_step"]),
        "angular_step_deg": float(parameters["angular_step_deg"]),
        "rotation_step_deg": float(parameters["rotation_step_deg"]),
        "goal_tolerance_px": float(max(5.0, parameters["exit_tolerance_cells"] * RING_SPACING * 0.65)),
    }
    public_state: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": prompt,
        "submit_label": "RELEASE THE SEAL",
        "asset_manifest": "shared_runtime/assets/provenance/twin_groove_seal_v0.json",
        "generator": {
            "name": "twin_groove_seal_procedural_v1",
            "variant_count": int(parameters["sectors"]) * int(parameters["rings"]) * (1 + int(parameters["branch_count"])) * 5,
        },
        "map": map_contract,
        "plates": plates,
        "start": _round_state(start),
        "shoe_length": NUB_DISTANCE,
        "max_actions": int(parameters["max_actions"]),
        "show_polar_readout": bool(parameters["show_polar_readout"]),
        "show_grid": bool(parameters["show_grid"]),
        "controls": {
            "origins": ["rear", "tip"],
            "translation": ["radial_in", "radial_out", "angular_cw", "angular_ccw"],
            "rotation": ["rotate_cw", "rotate_ccw"],
            "full_hint": "Tab changes the active nub; ` changes translation/rotation; arrow keys make one move.",
        },
    }
    ground_truth: dict[str, Any] = {
        "benchmark": "weird_cua_bench",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "map": copy.deepcopy(map_contract),
        "plates": copy.deepcopy(plates),
        "start": _round_state(start),
        "goal": _round_state(final_state),
        "solution_actions": copy.deepcopy(solution_actions),
        "solution_states": [_round_state(state) for state in states],
        "max_actions": int(parameters["max_actions"]),
        "goal_tolerance_px": float(map_contract["goal_tolerance_px"]),
        "parameters": copy.deepcopy(parameters),
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
