from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "velvet_valet"


PROFILES = {
    1: {
        "obstacle_count": 3,
        "obstacle_clearance": 108.0,
        "max_forward_speed": 3.0,
        "max_reverse_speed": 2.0,
        "acceleration": 0.20,
        "reverse_acceleration": 0.16,
        "turn_rate": 0.065,
        "position_tolerance": 18.0,
        "heading_tolerance_deg": 16.0,
        "speed_tolerance": 0.22,
        "max_ticks": 1500,
        "bay_width": 104.0,
        "bay_length": 128.0,
    },
    2: {
        "obstacle_count": 5,
        "obstacle_clearance": 94.0,
        "max_forward_speed": 3.3,
        "max_reverse_speed": 2.2,
        "acceleration": 0.21,
        "reverse_acceleration": 0.17,
        "turn_rate": 0.070,
        "position_tolerance": 13.0,
        "heading_tolerance_deg": 12.0,
        "speed_tolerance": 0.17,
        "max_ticks": 1550,
        "bay_width": 98.0,
        "bay_length": 120.0,
    },
    3: {
        "obstacle_count": 7,
        "obstacle_clearance": 80.0,
        "max_forward_speed": 3.7,
        "max_reverse_speed": 2.4,
        "acceleration": 0.22,
        "reverse_acceleration": 0.18,
        "turn_rate": 0.075,
        "position_tolerance": 10.0,
        "heading_tolerance_deg": 9.0,
        "speed_tolerance": 0.13,
        "max_ticks": 1600,
        "bay_width": 92.0,
        "bay_length": 114.0,
    },
    4: {
        "obstacle_count": 9,
        "obstacle_clearance": 66.0,
        "max_forward_speed": 4.1,
        "max_reverse_speed": 2.65,
        "acceleration": 0.23,
        "reverse_acceleration": 0.19,
        "turn_rate": 0.080,
        "position_tolerance": 8.0,
        "heading_tolerance_deg": 6.5,
        "speed_tolerance": 0.10,
        "max_ticks": 1650,
        "bay_width": 88.0,
        "bay_length": 108.0,
    },
    5: {
        "obstacle_count": 12,
        "obstacle_clearance": 54.0,
        "max_forward_speed": 4.5,
        "max_reverse_speed": 2.9,
        "acceleration": 0.24,
        "reverse_acceleration": 0.20,
        "turn_rate": 0.086,
        "position_tolerance": 6.0,
        "heading_tolerance_deg": 4.5,
        "speed_tolerance": 0.075,
        "max_ticks": 1700,
        "bay_width": 84.0,
        "bay_length": 102.0,
    },
}


def _seed(seed: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{MECHANIC_ID}|v1".encode()).digest()[:8], "big")


def _profile(task: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    condition = task.get("_control_condition") or {}
    difficulty = int(condition.get("difficulty", 4))
    parameters = dict(condition.get("difficulty_parameters") or PROFILES[difficulty])
    expected = PROFILES[difficulty]
    for key, value in expected.items():
        parameters.setdefault(key, value)
    if difficulty not in PROFILES:
        raise ValueError("velvet valet difficulty must be 1 through 5")
    return difficulty, parameters


def _distance_to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-9:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _route(start_x: float, start_y: float, target_x: float, target_y: float) -> list[dict[str, float | str]]:
    # The last leg is deliberately a reverse entry: the visible target arrow
    # points with the car's nose toward the audience while the car backs into it.
    return [
        {"x": start_x + 180.0, "y": start_y - 2.0, "mode": "forward"},
        {"x": target_x - 300.0, "y": start_y - 95.0, "mode": "forward"},
        {"x": target_x - 125.0, "y": target_y + 190.0, "mode": "forward"},
        {"x": target_x, "y": target_y + 118.0, "mode": "forward", "heading": math.pi / 2},
        {"x": target_x, "y": target_y, "mode": "reverse", "heading": math.pi / 2},
    ]


def _obstacles(
    rng: random.Random,
    count: int,
    clearance: float,
    start: dict[str, float],
    route: list[dict[str, float | str]],
    target: dict[str, float],
) -> list[dict[str, float | str]]:
    # Keep the authored route visibly surrounded by parked-car landmarks but
    # preserve a traversable corridor. Obstacle count is scene complexity;
    # the active difficulty progression is the vehicle response and final
    # parking tolerances, not a claim that higher levels require scraping
    # through a parked-car gap.
    points = [(float(start["x"]), float(start["y"]))] + [
        (float(point["x"]), float(point["y"])) for point in route
    ]
    obstacles: list[dict[str, float | str]] = []
    for index in range(count):
        accepted = None
        for _ in range(5000):
            width = rng.uniform(66.0, 84.0)
            height = rng.uniform(34.0, 46.0)
            x = rng.uniform(95.0, 1025.0)
            y = rng.uniform(88.0, 532.0)
            route_distance = min(
                _distance_to_segment(x, y, ax, ay, bx, by)
                for (ax, ay), (bx, by) in zip(points, points[1:])
            )
            if route_distance < clearance + max(width, height) * 0.62:
                continue
            if math.hypot(x - target["x"], y - target["y"]) < 120.0:
                continue
            if any(
                math.hypot(x - float(other["x"]), y - float(other["y"]))
                < (width + float(other["width"])) * 0.62
                for other in obstacles
            ):
                continue
            accepted = {
                "id": f"parked-{index + 1}",
                "x": round(x, 2),
                "y": round(y, 2),
                "width": round(width, 2),
                "height": round(height, 2),
                "angle": 0.0,
                "shade": index % 5,
            }
            break
        if accepted is None:
            raise ValueError("could not generate separated courtyard obstacles")
        obstacles.append(accepted)
    return obstacles


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed(seed))
    difficulty, parameters = _profile(task)
    width, height = 1120.0, 620.0
    start_x = round(rng.uniform(120.0, 155.0), 2)
    start_y = round(rng.uniform(470.0, 515.0), 2)
    target_x = round(rng.uniform(830.0, 955.0), 2)
    target_y = round(rng.uniform(92.0, 132.0), 2)
    start = {"x": start_x, "y": start_y, "heading": 0.0}
    target = {
        "x": target_x,
        "y": target_y,
        "heading": math.pi / 2,
        "width": float(parameters["bay_width"]),
        "length": float(parameters["bay_length"]),
    }
    route = _route(start_x, start_y, target_x, target_y)
    obstacles = _obstacles(
        rng,
        int(parameters["obstacle_count"]),
        float(parameters["obstacle_clearance"]),
        start,
        route,
        target,
    )
    physics = {
        "tick_ms": 80,
        "car_length": 58.0,
        "car_width": 30.0,
        "max_forward_speed": float(parameters["max_forward_speed"]),
        "max_reverse_speed": float(parameters["max_reverse_speed"]),
        "acceleration": float(parameters["acceleration"]),
        "reverse_acceleration": float(parameters["reverse_acceleration"]),
        "coast_factor": 0.86,
        "brake_factor": 0.52,
        "turn_rate": float(parameters["turn_rate"]),
        "position_tolerance": float(parameters["position_tolerance"]),
        "heading_tolerance_deg": float(parameters["heading_tolerance_deg"]),
        "speed_tolerance": float(parameters["speed_tolerance"]),
        "max_ticks": int(parameters["max_ticks"]),
    }
    world = {
        "width": width,
        "height": height,
        "start": start,
        "target": target,
        "obstacles": obstacles,
        "physics": physics,
    }
    level_token = f"d{difficulty}" if task.get("_control_condition") else "baseline"
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|{level_token}".encode()).hexdigest()[:12]
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Park the velvet car in the marked bay.",
        "asset_manifest": "shared_runtime/assets/provenance/velvet_valet_v0.json",
        "generator": {"name": "nonholonomic_courtyard_v1", "variant_count": 10**12},
        "world": copy.deepcopy(world),
    }
    truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "seed": seed,
        "challenge_id": challenge_id,
        "world": copy.deepcopy(world),
        "route_waypoints": copy.deepcopy(route),
    }
    if task.get("_control_condition"):
        public["control_condition"] = copy.deepcopy(task["_control_condition"])
        truth["control_condition"] = copy.deepcopy(task["_control_condition"])
    return public, truth
