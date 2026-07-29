from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "trace_shape_without_walls"
STAGE_WIDTH = 1000
STAGE_HEIGHT = 440
DEFAULT_XS = (72, 178, 292, 408, 530, 650, 770, 928)

# These are the uncontrolled v1 values.  Keeping them here makes the L4
# profile an exact fixed-seed reproduction rather than a near approximation.
DEFAULT_PARAMETERS = {
    "main_control_count": 8,
    "curve_delta": 94,
    "path_y_min": 92,
    "path_y_max": 348,
    "initial_y_min": 150,
    "initial_y_max": 290,
    "exit_y_min": 145,
    "exit_y_max": 295,
    "branch_count_min": 3,
    "branch_count_max": 4,
    "checkpoint_count": 11,
    "corridor_radius_min": 36,
    "corridor_radius_max": 41,
    "sonar_radius_min": 71,
    "sonar_radius_max": 79,
    "sonar_fade_ms": 780,
    "drift_amplitude_x_min": 10,
    "drift_amplitude_x_max": 14,
    "drift_amplitude_y_min": 8,
    "drift_amplitude_y_max": 12,
    "drift_rate_x_min": 0.060,
    "drift_rate_x_max": 0.078,
    "drift_rate_y_min": 0.047,
    "drift_rate_y_max": 0.066,
    "min_probe_samples": 24,
    "min_probe_cells": 14,
    "main_coverage_ratio": 0.62,
    "main_coverage_cap": 58,
    "min_trace_samples": 62,
    "trace_coverage_ratio": 0.78,
    "trace_distance_ratio": 0.83,
    "min_trace_ms": 620,
    "max_raw_step": 58,
}


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _catmull_rom(control: list[tuple[float, float]], samples_per_segment: int) -> list[list[int]]:
    if len(control) < 2:
        raise ValueError("a spline requires at least two control points")
    padded = [control[0], *control, control[-1]]
    points: list[list[int]] = []
    for segment in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[segment - 1 : segment + 3]
        for sample in range(samples_per_segment):
            t = sample / samples_per_segment
            t2, t3 = t * t, t * t * t
            x = 0.5 * (
                2 * p1[0]
                + (-p0[0] + p2[0]) * t
                + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
            )
            y = 0.5 * (
                2 * p1[1]
                + (-p0[1] + p2[1]) * t
                + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
            )
            point = [round(x), round(y)]
            if not points or point != points[-1]:
                points.append(point)
    endpoint = [round(control[-1][0]), round(control[-1][1])]
    if points[-1] != endpoint:
        points.append(endpoint)
    return points


def _path_length(points: list[list[int]]) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))


def _control_parameters(task: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    condition = task.get("_control_condition")
    if condition is None:
        return None, dict(DEFAULT_PARAMETERS)
    parameters = dict(condition.get("difficulty_parameters") or {})
    missing = sorted(set(DEFAULT_PARAMETERS) - set(parameters))
    if missing:
        raise ValueError(f"trace-shape control profile is missing parameters: {', '.join(missing)}")
    merged = dict(DEFAULT_PARAMETERS)
    merged.update(parameters)
    integer_ranges = {
        "main_control_count": (8, 10),
        "curve_delta": (1, 160),
        "path_y_min": (40, 250),
        "path_y_max": (190, 400),
        "initial_y_min": (40, 360),
        "initial_y_max": (40, 360),
        "exit_y_min": (40, 360),
        "exit_y_max": (40, 360),
        "branch_count_min": (0, 5),
        "branch_count_max": (0, 5),
        "checkpoint_count": (4, 18),
        "corridor_radius_min": (18, 90),
        "corridor_radius_max": (18, 90),
        "sonar_radius_min": (40, 180),
        "sonar_radius_max": (40, 180),
        "sonar_fade_ms": (160, 3000),
        "drift_amplitude_x_min": (0, 30),
        "drift_amplitude_x_max": (0, 30),
        "drift_amplitude_y_min": (0, 30),
        "drift_amplitude_y_max": (0, 30),
        "min_probe_samples": (1, 120),
        "min_probe_cells": (1, 80),
        "main_coverage_cap": (1, 200),
        "min_trace_samples": (1, 200),
        "min_trace_ms": (0, 20_000),
        "max_raw_step": (4, 120),
    }
    for name, (low, high) in integer_ranges.items():
        value = merged[name]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"trace-shape parameter {name} must be an integer in {low}..{high}")
    for name in ("drift_rate_x_min", "drift_rate_x_max", "drift_rate_y_min", "drift_rate_y_max", "main_coverage_ratio", "trace_coverage_ratio", "trace_distance_ratio"):
        value = merged[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"trace-shape parameter {name} must be finite")
    if not (
        merged["path_y_min"] < merged["path_y_max"]
        and merged["initial_y_min"] <= merged["initial_y_max"]
        and merged["exit_y_min"] <= merged["exit_y_max"]
        and merged["branch_count_min"] <= merged["branch_count_max"]
        and merged["corridor_radius_min"] <= merged["corridor_radius_max"]
        and merged["sonar_radius_min"] <= merged["sonar_radius_max"]
        and merged["drift_amplitude_x_min"] <= merged["drift_amplitude_x_max"]
        and merged["drift_amplitude_y_min"] <= merged["drift_amplitude_y_max"]
        and merged["drift_rate_x_min"] <= merged["drift_rate_x_max"]
        and merged["drift_rate_y_min"] <= merged["drift_rate_y_max"]
    ):
        raise ValueError("trace-shape control parameter ranges are invalid")
    for name in ("main_coverage_ratio", "trace_coverage_ratio", "trace_distance_ratio"):
        if not 0 < float(merged[name]) <= 1:
            raise ValueError(f"trace-shape parameter {name} must be in (0, 1]")
    return copy.deepcopy(condition), merged


def _x_controls(count: int) -> tuple[int, ...]:
    if count == len(DEFAULT_XS):
        return DEFAULT_XS
    return tuple(round(72 + index * (928 - 72) / (count - 1)) for index in range(count))


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    condition, parameters = _control_parameters(task)
    xs = _x_controls(parameters["main_control_count"])
    y = rng.randint(parameters["initial_y_min"], parameters["initial_y_max"])
    controls: list[tuple[float, float]] = []
    for index, x in enumerate(xs):
        if index == 0:
            current = y
        elif index == len(xs) - 1:
            current = rng.randint(parameters["exit_y_min"], parameters["exit_y_max"])
        else:
            current = max(
                parameters["path_y_min"],
                min(parameters["path_y_max"], y + rng.randint(-parameters["curve_delta"], parameters["curve_delta"])),
            )
            y = current
        controls.append((x, current))
    main_path = _catmull_rom(controls, 13)

    if parameters["branch_count_min"] == 3 and parameters["branch_count_max"] == 4:
        branch_count = rng.choice((3, 4))
    else:
        branch_count = rng.randint(parameters["branch_count_min"], parameters["branch_count_max"])
    attach_fractions = rng.sample((0.24, 0.38, 0.53, 0.68, 0.79), branch_count)
    attach_fractions.sort()
    branches: list[dict[str, Any]] = []
    for number, fraction in enumerate(attach_fractions, start=1):
        attach_index = round((len(main_path) - 1) * fraction)
        attach = main_path[attach_index]
        room_above = attach[1] - 46
        room_below = STAGE_HEIGHT - 46 - attach[1]
        if abs(room_above - room_below) < 35:
            direction = -1 if (number + rng.randrange(2)) % 2 else 1
        else:
            direction = -1 if room_above > room_below else 1
        vertical = min(145, max(92, (room_above if direction < 0 else room_below) - 8))
        bend = rng.choice((-1, 1))
        branch_control = [
            (attach[0], attach[1]),
            (attach[0] + rng.randint(24, 52), attach[1] + direction * 45),
            (attach[0] + bend * rng.randint(18, 54), attach[1] + direction * int(vertical * 0.78)),
            (max(54, min(946, attach[0] + bend * rng.randint(58, 105))), attach[1] + direction * vertical),
        ]
        branch_points = _catmull_rom(branch_control, 9)
        branches.append({
            "id": f"echo-{number}-{hashlib.sha256(f'{seed}|branch|{number}'.encode()).hexdigest()[:5]}",
            "attach_index": attach_index,
            "points": branch_points,
        })

    checkpoint_count = parameters["checkpoint_count"]
    checkpoint_indices = sorted({round(index * (len(main_path) - 1) / (checkpoint_count - 1)) for index in range(checkpoint_count)})
    if checkpoint_indices[0] != 0:
        checkpoint_indices.insert(0, 0)
    if checkpoint_indices[-1] != len(main_path) - 1:
        checkpoint_indices.append(len(main_path) - 1)

    corridor_radius = rng.randint(parameters["corridor_radius_min"], parameters["corridor_radius_max"])
    sonar_radius = rng.randint(parameters["sonar_radius_min"], parameters["sonar_radius_max"])
    path_length = _path_length(main_path)
    drift = {
        "amplitude_x": rng.randint(parameters["drift_amplitude_x_min"], parameters["drift_amplitude_x_max"]),
        "amplitude_y": rng.randint(parameters["drift_amplitude_y_min"], parameters["drift_amplitude_y_max"]),
        "rate_x": round(rng.uniform(parameters["drift_rate_x_min"], parameters["drift_rate_x_max"]), 5),
        "rate_y": round(rng.uniform(parameters["drift_rate_y_min"], parameters["drift_rate_y_max"]), 5),
        "phase_x": round(rng.uniform(0.1, math.pi * 1.8), 5),
        "phase_y": round(rng.uniform(0.1, math.pi * 1.8), 5),
    }
    requirements = {
        "min_probe_samples": parameters["min_probe_samples"],
        "min_probe_cells": parameters["min_probe_cells"],
        "min_main_coverage": min(parameters["main_coverage_cap"], round(len(main_path) * parameters["main_coverage_ratio"])),
        # False echoes are discoverable and useful, but exploring them is not a
        # ceremonial pass quota once the real corridor has been mapped.
        "min_branch_coverage": 0,
        "min_trace_samples": max(parameters["min_trace_samples"], round(len(main_path) * parameters["trace_coverage_ratio"])),
        "min_trace_distance": round(path_length * parameters["trace_distance_ratio"]),
        "min_trace_ms": parameters["min_trace_ms"],
        "max_raw_step": parameters["max_raw_step"],
    }
    task_id = str(task.get("id") or "trace_shape_without_walls_seed_0001@0.1")
    condition_token = f"|d{int(condition['difficulty'])}" if condition else ""
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}{condition_token}".encode("utf-8")).hexdigest()[:12]
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Map the hidden corridor with sonar, then hold from START and trace continuously to EXIT.",
        "submit_label": "CERTIFY TRACE RECORD",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "generator": {"name": "blind_corridor_oscilloscope_v1", "variant_count": 8_600_000_000},
        "stage": {"width": STAGE_WIDTH, "height": STAGE_HEIGHT},
        "main_path": main_path,
        "branches": branches,
        "start": main_path[0],
        "exit": main_path[-1],
        "checkpoint_indices": checkpoint_indices,
        "corridor_radius": corridor_radius,
        "sonar_radius": sonar_radius,
        "sonar_fade_ms": parameters["sonar_fade_ms"],
        "drift": drift,
        "requirements": requirements,
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "stage": public_state["stage"],
        "main_path": main_path,
        "branches": branches,
        "start": public_state["start"],
        "exit": public_state["exit"],
        "checkpoint_indices": checkpoint_indices,
        "corridor_radius": corridor_radius,
        "sonar_radius": sonar_radius,
        "drift": drift,
        "requirements": requirements,
        "path_length": path_length,
        "variant_count": public_state["generator"]["variant_count"],
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    assert 0 <= len(branches) <= 5
    assert len(main_path) >= 80
    assert all(38 <= x <= STAGE_WIDTH - 38 and 38 <= y <= STAGE_HEIGHT - 38 for x, y in main_path)
    assert all(34 <= x <= STAGE_WIDTH - 34 and 34 <= y <= STAGE_HEIGHT - 34 for branch in branches for x, y in branch["points"])
    return public_state, ground_truth
