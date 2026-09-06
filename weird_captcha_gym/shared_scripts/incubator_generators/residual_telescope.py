from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "residual_telescope"
IMAGE = {"width": 58, "height": 58}
PARAMETERS = (
    ("disc_brightness", "DISC / LIGHT", "disc"),
    ("core_brightness", "CORE / LIGHT", "core"),
    ("disc_extent", "DISC / EXTENT", "disc"),
    ("bar_brightness", "BAR / LIGHT", "bar"),
    ("bar_boxiness", "BAR / BOXINESS", "bar"),
    ("core_concentration", "CORE / CONCENTRATION", "core"),
    ("arms_brightness", "ARMS / LIGHT", "arms"),
    ("arms_spread", "ARMS / SPREAD", "arms"),
    ("disc_falloff", "DISC / FALLOFF", "disc"),
    ("arms_falloff", "ARMS / FALLOFF", "arms"),
)

DEFAULT_PARAMETERS = {
    "component_count": 4,
    "arm_count": 2,
    "parameter_count": 8,
    "geometry_tolerance": 4,
    "angle_tolerance_deg": 12,
    "parameter_tolerance": 0,
    "residual_threshold_milli": 10,
    "move_budget": 54,
    "arm_point_count": 7,
}
CONTROL_FIELDS = frozenset(DEFAULT_PARAMETERS)


def _seed_int(seed: str, salt: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{salt}".encode()).digest()[:8], "big")


def _parameters(task: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, int]]:
    condition = task.get("_control_condition")
    if condition is None:
        return None, dict(DEFAULT_PARAMETERS)
    if not isinstance(condition, dict):
        raise ValueError("residual telescope control condition is malformed")
    supplied = dict(condition.get("difficulty_parameters") or {})
    if set(supplied) != CONTROL_FIELDS:
        raise ValueError("residual telescope difficulty profile fields do not match the generator contract")
    values = dict(DEFAULT_PARAMETERS)
    values.update(supplied)
    ranges = {
        "component_count": (2, 4),
        "arm_count": (0, 3),
        "parameter_count": (3, 10),
        "geometry_tolerance": (2, 9),
        "angle_tolerance_deg": (6, 28),
        "parameter_tolerance": (0, 2),
        "residual_threshold_milli": (5, 30),
        "move_budget": (20, 90),
        "arm_point_count": (5, 9),
    }
    for name, (low, high) in ranges.items():
        value = values[name]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"residual telescope control parameter {name} must be an integer in {low}..{high}")
    if values["component_count"] < 4 and values["arm_count"]:
        raise ValueError("arms require the fourth component stage")
    if values["component_count"] == 4 and values["arm_count"] < 1:
        raise ValueError("the arm component requires at least one arm")
    return copy.deepcopy(condition), values


def _spiral(center: list[float], radius: float, phase: float, count: int) -> list[list[float]]:
    points: list[list[float]] = []
    for index in range(count):
        amount = index / (count - 1)
        theta = phase + amount * 1.47
        distance = radius * (0.36 + amount * 0.78)
        points.append([
            round(center[0] + math.cos(theta) * distance, 2),
            round(center[1] + math.sin(theta) * distance, 2),
        ])
    return points


def _segment_distance(x: float, y: float, first: list[float], second: list[float]) -> float:
    vx, vy = second[0] - first[0], second[1] - first[1]
    length_sq = vx * vx + vy * vy
    amount = 0.0 if length_sq <= 0 else max(0.0, min(1.0, ((x - first[0]) * vx + (y - first[1]) * vy) / length_sq))
    return math.hypot(x - (first[0] + amount * vx), y - (first[1] + amount * vy))


def _polyline_distance(x: float, y: float, points: list[list[float]]) -> float:
    return min(_segment_distance(x, y, first, second) for first, second in zip(points, points[1:]))


def render_pixels(geometry: dict[str, Any], values: dict[str, int], width: int, height: int) -> list[list[float]]:
    pixels: list[list[float]] = []
    disc = geometry.get("disc")
    core = geometry.get("core")
    bar = geometry.get("bar")
    arms = geometry.get("arms") or []
    disc_center = (disc or {}).get("center") or [width / 2, height / 2]
    disc_radius = max(1.0, float((disc or {}).get("radius") or 18))
    for row in range(height):
        line: list[float] = []
        for column in range(width):
            x, y = column + 0.5, row + 0.5
            light = 0.016
            if disc:
                angle = float(disc["angle"])
                dx, dy = x - disc["center"][0], y - disc["center"][1]
                xr = math.cos(angle) * dx + math.sin(angle) * dy
                yr = -math.sin(angle) * dx + math.cos(angle) * dy
                extent = 0.76 + values["disc_extent"] * 0.052
                falloff = 1.48 - values["disc_falloff"] * 0.055
                radius = max(1.0, float(disc["radius"]) * extent)
                elliptical = math.sqrt(xr * xr + (yr / 0.61) ** 2) / radius
                light += (0.11 + values["disc_brightness"] * 0.039) * math.exp(-elliptical * 2.05 * falloff)
            if core:
                angle = float(core["angle"])
                dx, dy = x - core["center"][0], y - core["center"][1]
                xr = math.cos(angle) * dx + math.sin(angle) * dy
                yr = -math.sin(angle) * dx + math.cos(angle) * dy
                elliptical = math.sqrt(xr * xr + (yr / 0.78) ** 2) / max(1.0, float(core["radius"]))
                concentration = 1.18 + values["core_concentration"] * 0.18
                light += (0.13 + values["core_brightness"] * 0.044) * math.exp(-(elliptical ** concentration) * 1.8)
            if bar:
                angle = float(bar["angle"])
                dx, dy = x - bar["center"][0], y - bar["center"][1]
                xr = abs(math.cos(angle) * dx + math.sin(angle) * dy) / max(1.0, float(bar["length"]) / 2)
                yr = abs(-math.sin(angle) * dx + math.cos(angle) * dy) / max(1.0, float(bar["width"]))
                power = 1.45 + values["bar_boxiness"] * 0.22
                norm = (xr ** power + yr ** power) ** (1 / power)
                light += (0.08 + values["bar_brightness"] * 0.034) * math.exp(-(norm ** 3.2) * 2.2)
            if arms:
                spread = 1.05 + values["arms_spread"] * 0.25
                radial = math.hypot(x - disc_center[0], y - disc_center[1]) / disc_radius
                radial_falloff = 0.58 + values["arms_falloff"] * 0.065
                for points in arms:
                    distance = _polyline_distance(x, y, points)
                    light += (0.045 + values["arms_brightness"] * 0.018) * math.exp(-(distance ** 2) / (2 * spread ** 2)) * math.exp(-radial * radial_falloff)
            line.append(round(max(0.0, min(1.0, light)), 5))
        pixels.append(line)
    return pixels


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition, controls = _parameters(task)
    difficulty = int((condition or {}).get("difficulty") or 4)
    rng = random.Random(_seed_int(seed, f"{MECHANIC_ID}|world"))
    center = [round(28.5 + rng.uniform(-1.9, 1.9), 2), round(28.5 + rng.uniform(-1.7, 1.7), 2)]
    angle = rng.uniform(-0.72, 0.72)
    radius = rng.uniform(18.2, 21.0)
    core_center = [round(center[0] + rng.uniform(-0.8, 0.8), 2), round(center[1] + rng.uniform(-0.7, 0.7), 2)]
    bar_length = rng.uniform(23.0, 28.0)
    bar_angle = angle + rng.uniform(-0.24, 0.24)
    geometry: dict[str, Any] = {
        "disc": {"center": center, "radius": round(radius, 2), "angle": round(angle, 5)},
        "core": {"center": core_center, "radius": round(rng.uniform(6.3, 8.2), 2), "angle": round(angle, 5)},
        "bar": {
            "center": center,
            "length": round(bar_length, 2),
            "width": 2.75,
            "angle": round(bar_angle, 5),
        },
        "arms": [],
    }
    for arm_index in range(controls["arm_count"]):
        phase = angle + arm_index * (2 * math.pi / controls["arm_count"]) + rng.uniform(-0.08, 0.08)
        geometry["arms"].append(_spiral(center, radius, phase, controls["arm_point_count"]))
    if controls["component_count"] < 3:
        geometry["bar"] = None
    if controls["component_count"] < 4:
        geometry["arms"] = []

    active_ids = [item[0] for item in PARAMETERS[: controls["parameter_count"]]]
    truth_values = {item[0]: 5 for item in PARAMETERS}
    for parameter_id in active_ids:
        choices = [2, 3, 4, 6, 7, 8]
        truth_values[parameter_id] = rng.choice(choices)
    parameter_specs = [
        {"id": parameter_id, "label": label, "component": component, "minimum": 0, "maximum": 10, "initial": 5}
        for parameter_id, label, component in PARAMETERS
        if parameter_id in active_ids
    ]
    sequence = ["disc", "core"]
    if geometry["bar"]:
        sequence.append("bar")
    sequence.extend(f"arm_{index + 1}" for index in range(len(geometry["arms"])))
    target_pixels = render_pixels(geometry, truth_values, IMAGE["width"], IMAGE["height"])
    task_id = str(task.get("id") or "residual_telescope_seed_0001@0.1")
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|d{difficulty}".encode()).hexdigest()[:12]
    common = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": "Make the three plates agree.",
        "submit_label": "CERTIFY MODEL",
        "image": copy.deepcopy(IMAGE),
        "target_pixels": target_pixels,
        "component_sequence": sequence,
        "arm_point_count": controls["arm_point_count"],
        "parameter_specs": parameter_specs,
        "initial_values": {item["id"]: item["initial"] for item in parameter_specs},
        "geometry_tolerance": controls["geometry_tolerance"],
        "angle_tolerance_deg": controls["angle_tolerance_deg"],
        "parameter_tolerance": controls["parameter_tolerance"],
        "residual_threshold": controls["residual_threshold_milli"] / 1000,
        "move_budget": controls["move_budget"],
        "generator": {"name": "procedural_residual_optics_v1", "variant_count": 2147483648},
        "asset_manifest": "shared_runtime/assets/provenance/residual_telescope_v0.json",
    }
    public_state = copy.deepcopy(common)
    ground_truth = copy.deepcopy(common)
    ground_truth.update({
        "seed": seed,
        "difficulty": difficulty,
        "parameters": copy.deepcopy(controls),
        "target_geometry": geometry,
        "target_values": truth_values,
    })
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
