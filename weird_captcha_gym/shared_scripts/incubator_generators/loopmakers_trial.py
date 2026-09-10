"""Procedural state for Loopmaker's Trial.

The browser is intentionally only a view and input surface.  The public
document contains the route, marked measurements, and the equations needed
to understand a run.  The solution route never crosses the browser boundary;
the server grader replays the public geometry independently.
"""

from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "loopmakers_trial"
ASSET_MANIFEST = "shared_runtime/assets/provenance/loopmakers_trial_v0.json"
CANVAS = {"width": 900, "height": 470}
SOURCE_ANCHORS = ["XUIF-261", "XUIF-229"]
_TARGET_VARIATION_INDICES = (3, 4, 5, 7, 8, 10)

_PROFILES: dict[int, dict[str, Any]] = {
    1: {
        "point_count": 11,
        "feature_count": 3,
        "height_step": 14,
        "radius_step": 18,
        "initial_offset_steps": 1,
        "sample_steps": 20,
        "friction": 0.0005,
        "max_force_g": 8.8,
        "min_loop_speed": 7.0,
        "max_speed": 18.0,
    },
    2: {
        "point_count": 12,
        "feature_count": 4,
        "height_step": 12,
        "radius_step": 16,
        "initial_offset_steps": 1,
        "sample_steps": 22,
        "friction": 0.0007,
        "max_force_g": 8.5,
        "min_loop_speed": 7.5,
        "max_speed": 18.0,
    },
    3: {
        "point_count": 13,
        "feature_count": 5,
        "height_step": 10,
        "radius_step": 15,
        "initial_offset_steps": 2,
        "sample_steps": 24,
        "friction": 0.0009,
        "max_force_g": 8.2,
        "min_loop_speed": 8.0,
        "max_speed": 17.5,
    },
    4: {
        "point_count": 14,
        "feature_count": 6,
        "height_step": 9,
        "radius_step": 13,
        "initial_offset_steps": 2,
        "sample_steps": 26,
        "friction": 0.0011,
        "max_force_g": 8.0,
        "min_loop_speed": 8.4,
        "max_speed": 17.5,
    },
    5: {
        "point_count": 15,
        "feature_count": 7,
        "height_step": 8,
        "radius_step": 12,
        "initial_offset_steps": 3,
        "sample_steps": 28,
        "friction": 0.0013,
        "max_force_g": 7.8,
        "min_loop_speed": 8.8,
        "max_speed": 17.0,
    },
}


def profile_for(difficulty: int) -> dict[str, Any]:
    profile = copy.deepcopy(_PROFILES[int(difficulty)])
    profile["difficulty"] = int(difficulty)
    return profile


def _condition(task: dict[str, Any]) -> dict[str, Any] | None:
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition"))
    if not condition:
        return None
    return condition


def _difficulty(task: dict[str, Any], condition: dict[str, Any] | None) -> int:
    if condition:
        return int(condition["difficulty"])
    return 3


def _seed_int(seed: str, salt: str = "route") -> int:
    return int(hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).hexdigest()[:16], 16)


def _route_template() -> list[tuple[float, float]]:
    # The middle nine points make a deliberately readable loop.  The final
    # four points are rolling dips whose force readings expose upstream edits.
    # Keep the first downstream dip away from the loop's lower return point so
    # the two visible control handles never share a hit region.
    return [
        (55, 382),
        (118, 210),
        (202, 338),
        (294, 338),
        (354, 258),
        (330, 164),
        (250, 104),
        (170, 164),
        (146, 258),
        (320, 360),
        (360, 354),
        (410, 292),
        (520, 386),
        (650, 300),
        (850, 342),
    ]


def _route_for_count(point_count: int) -> list[tuple[float, float]]:
    template = _route_template()
    return template[: int(point_count)]


def _target_route_pairs(point_count: int, params: dict[str, Any], seed: str) -> list[tuple[float, float]]:
    """Make the hidden safe route seed-dependent without changing its profile."""
    values = [list(pair) for pair in _route_for_count(point_count)]
    rng = random.Random(_seed_int(seed, "loopmaker-target-variation"))
    radius_step = float(params["radius_step"])
    height_step = float(params["height_step"])
    for index in _TARGET_VARIATION_INDICES:
        if 0 < index < len(values) - 1:
            values[index][0] += rng.choice((-1, 0, 1)) * radius_step
            values[index][1] += rng.choice((-1, 0, 1)) * height_step
    return [(float(x), float(y)) for x, y in values]


def _feature_indices(point_count: int, feature_count: int) -> list[int]:
    candidates = [1, 2, 6, 9, 11, 12, 13]
    usable = [index for index in candidates if index < point_count - 1]
    return usable[:feature_count]


def _feature_definition(index: int, ordinal: int, params: dict[str, Any]) -> dict[str, Any]:
    names = {
        1: ("hill crest", "hill_top"),
        2: ("loop entry", "loop_entry"),
        6: ("loop crown", "loop_top"),
        9: ("loop exit", "loop_exit"),
    }
    label, kind = names.get(index, (f"dip {ordinal - 3}", "dip"))
    max_speed = float(params["max_speed"])
    max_force = float(params["max_force_g"])
    if kind == "hill_top":
        constraints = {
            "min_speed": 0.0,
            "max_speed": max_speed,
            "min_force_g": 0.0,
            "max_force_g": max_force,
            "require_contact": False,
        }
    elif kind == "loop_entry":
        constraints = {
            "min_speed": 5.0,
            "max_speed": max_speed,
            "min_force_g": 0.0,
            "max_force_g": max_force,
            "require_contact": True,
        }
    elif kind == "loop_top":
        constraints = {
            "min_speed": float(params["min_loop_speed"]),
            "max_speed": max_speed,
            "min_force_g": 0.30,
            "max_force_g": max_force,
            "require_contact": True,
        }
    elif kind == "loop_exit":
        constraints = {
            "min_speed": 4.5,
            "max_speed": max_speed,
            "min_force_g": 0.0,
            "max_force_g": max_force,
            "require_contact": True,
        }
    else:
        constraints = {
            "min_speed": 2.0,
            "max_speed": max_speed,
            "min_force_g": 0.0,
            "max_force_g": max_force,
            "require_contact": True,
        }
    return {
        "id": f"feature_{ordinal}",
        "label": label,
        "kind": kind,
        "point_index": index,
        "constraints": constraints,
    }


def _physics(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "gravity": 9.8,
        "pixels_per_meter": 30.0,
        "initial_speed_mps": 3.5,
        "friction_per_pixel": float(params["friction"]),
        "sample_steps": int(params["sample_steps"]),
        "stall_speed_mps": 1.25,
        "minimum_radius_px": 90.0,
        "run_duration_ms": 6200,
        "height_reference_y": 382.0,
    }


def _points(values: list[tuple[float, float]], rng: random.Random, params: dict[str, Any], initial: bool) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for index, (x, y) in enumerate(values):
        if initial and 0 < index < len(values) - 1:
            offset = int(params["initial_offset_steps"])
            x += rng.choice((-1, 1)) * rng.randint(1, offset) * float(params["radius_step"])
            y += rng.choice((-1, 1)) * rng.randint(1, offset) * float(params["height_step"])
            # The trial opens with a deliberately low recovery dip. Its
            # height is an exact number of proxy increments, so the visible
            # simplified surface can repair it without a hidden offset.
            if index == 9:
                # Leave the status ribbon below the handle while preserving
                # an integer number of proxy steps from the canonical route.
                maximum_y = float(CANVAS["height"] - 60)
                steps = max(1, math.floor((maximum_y - float(values[index][1])) / float(params["height_step"])))
                y = float(values[index][1]) + steps * float(params["height_step"])
            if index == 6:
                y -= float(params["height_step"]) * (5 + int(params["difficulty"]) - 1)
            x = _grid_coordinate(float(values[index][0]), x, float(params["radius_step"]), 18.0, float(CANVAS["width"] - 18))
            y = _grid_coordinate(float(values[index][1]), y, float(params["height_step"]), 14.0, float(CANVAS["height"] - 26))
        points.append({"id": f"p{index + 1:02d}", "x": round(x, 2), "y": round(y, 2)})
    return points


def _world_hash(points: list[dict[str, Any]]) -> str:
    stable = ";".join(f"{p['id']}:{float(p['x']):.2f}:{float(p['y']):.2f}" for p in points)
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16]


def _grid_coordinate(base: float, candidate: float, step: float, lower: float, upper: float) -> float:
    """Keep an initial point visible while preserving proxy-step reachability."""
    if step <= 0:
        return round(max(lower, min(upper, candidate)), 2)
    requested = int(round((candidate - base) / step))
    minimum = math.ceil((lower - base) / step - 1e-9)
    maximum = math.floor((upper - base) / step + 1e-9)
    requested = max(minimum, min(maximum, requested))
    return round(base + requested * step, 2)


def _has_control_clearance(points: list[dict[str, Any]], minimum: float = 24.0) -> bool:
    for left_index, left in enumerate(points):
        for right in points[left_index + 1:]:
            if math.dist((float(left["x"]), float(left["y"])), (float(right["x"]), float(right["y"]))) < minimum:
                return False
    return True


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = _condition(task)
    difficulty = _difficulty(task, condition)
    params = profile_for(difficulty)
    rng = random.Random(_seed_int(seed, "loopmaker-route"))
    target_pairs = _target_route_pairs(int(params["point_count"]), params, seed)
    target = _points(target_pairs, rng, params, initial=False)
    initial: list[dict[str, Any]] = []
    for _attempt in range(512):
        candidate = _points(target_pairs, rng, params, initial=True)
        if _has_control_clearance(candidate):
            initial = candidate
            break
    if not initial:
        raise RuntimeError("could not generate a visible, non-overlapping initial route")
    feature_indices = _feature_indices(len(target), int(params["feature_count"]))
    features = [_feature_definition(index, ordinal, params) for ordinal, index in enumerate(feature_indices, 1)]
    physics = _physics(params)
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|d{difficulty}".encode("utf-8")).hexdigest()[:16]
    interaction = str((condition or {}).get("interaction") or "full")
    real_time = str((condition or {}).get("real_time") or "live")
    public_params = copy.deepcopy(params)
    public_params.pop("difficulty", None)
    control = {
        "difficulty": difficulty,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": public_params,
    }
    public: dict[str, Any] = {
        "mechanic_id": MECHANIC_ID,
        "public_name": "Loopmaker's Trial",
        "asset_manifest": ASSET_MANIFEST,
        "task_id": str(task.get("id") or "loopmakers_trial_base@0.2"),
        "challenge_id": challenge_id,
        "seed_label": str(seed),
        "canvas": copy.deepcopy(CANVAS),
        "points": initial,
        "features": copy.deepcopy(features),
        "physics": physics,
        "control_contract": {
            "full": "Drag the amber control points directly; x spacing changes the local radius.",
            "simplified": "Select a point, then use RAISE/LOWER/WIDEN/TIGHTEN proxy controls.",
        },
        "interaction_mode": interaction,
        "real_time_mode": real_time,
        "geometry_hash": _world_hash(initial),
        "route_caption": "Energy enters at the launch hill, climbs the loop, then survives the downstream dips.",
        "prompt": "Tune one continuous route until the rider completes every marked feature inside the safety envelope.",
        "source_anchors": list(SOURCE_ANCHORS),
        "status": "prototype_visual_candidate",
    }
    if condition is not None:
        public["control_condition"] = copy.deepcopy(control)
    truth: dict[str, Any] = {
        "mechanic_id": MECHANIC_ID,
        "public_name": "Loopmaker's Trial",
        "task_id": str(task.get("id") or "loopmakers_trial_base@0.2"),
        "challenge_id": challenge_id,
        "seed_label": str(seed),
        "solution_points": target,
        "initial_points": initial,
        "features": copy.deepcopy(features),
        "physics": physics,
        "control_condition": copy.deepcopy(control) if condition is not None else None,
        "world_hash": _world_hash(target),
        "source_anchors": list(SOURCE_ANCHORS),
    }
    return public, truth


def sample_path(points: list[dict[str, Any]], sample_steps: int) -> tuple[list[dict[str, float]], list[float]]:
    path: list[dict[str, float]] = []
    feature_positions: list[float] = []
    for index in range(len(points) - 1):
        first, second = points[index], points[index + 1]
        for step in range(sample_steps):
            t = step / sample_steps
            path.append({
                "x": float(first["x"]) + (float(second["x"]) - float(first["x"])) * t,
                "y": float(first["y"]) + (float(second["y"]) - float(first["y"])) * t,
            })
    last = points[-1]
    path.append({"x": float(last["x"]), "y": float(last["y"])})
    for index in range(len(points)):
        feature_positions.append(float(index * sample_steps))
    return path, feature_positions


def _radius(path: list[dict[str, float]], index: int, minimum: float) -> float:
    if index <= 0 or index >= len(path) - 1:
        return 1000000.0
    first, middle, last = path[index - 1], path[index], path[index + 1]
    a = math.dist((first["x"], first["y"]), (middle["x"], middle["y"]))
    b = math.dist((middle["x"], middle["y"]), (last["x"], last["y"]))
    c = math.dist((first["x"], first["y"]), (last["x"], last["y"]))
    cross = abs((middle["x"] - first["x"]) * (last["y"] - first["y"]) - (middle["y"] - first["y"]) * (last["x"] - first["x"]))
    if cross < 1e-6:
        return 1000000.0
    return max(minimum, a * b * c / (2.0 * cross))


def simulate(points: list[dict[str, Any]], features: list[dict[str, Any]], physics: dict[str, Any]) -> dict[str, Any]:
    sample_steps = int(physics["sample_steps"])
    path, feature_positions = sample_path(points, sample_steps)
    distances = [0.0]
    for first, second in zip(path, path[1:]):
        distances.append(distances[-1] + math.dist((first["x"], first["y"]), (second["x"], second["y"])))
    start_y = float(points[0]["y"])
    speeds: list[float] = []
    forces: list[float] = []
    for index, item in enumerate(path):
        height_gain = (start_y - float(item["y"])) / float(physics["pixels_per_meter"])
        energy = float(physics["initial_speed_mps"]) ** 2 + 2 * float(physics["gravity"]) * height_gain - float(physics["friction_per_pixel"]) * distances[index]
        speed = math.sqrt(max(0.0, energy))
        if index == 0:
            tangent_x = path[1]["x"] - path[0]["x"]
            tangent_y = path[1]["y"] - path[0]["y"]
        else:
            tangent_x = item["x"] - path[index - 1]["x"]
            tangent_y = item["y"] - path[index - 1]["y"]
        angle = math.atan2(tangent_y, tangent_x)
        radius = _radius(path, index, float(physics["minimum_radius_px"]))
        centripetal = 0.0 if radius > 900000 else speed * speed / (float(physics["gravity"]) * (radius / float(physics["pixels_per_meter"])))
        speeds.append(speed)
        forces.append(centripetal + abs(math.cos(angle)))
    feature_metrics: list[dict[str, Any]] = []
    for feature in features:
        index = min(len(path) - 1, int(feature["point_index"]) * sample_steps)
        constraints = feature["constraints"]
        speed = speeds[index]
        force = forces[index]
        contact = force >= float(constraints["min_force_g"])
        reasons: list[str] = []
        if speed < float(constraints["min_speed"]):
            reasons.append("speed below thrill minimum")
        if speed > float(constraints["max_speed"]):
            reasons.append("speed above envelope")
        if force < float(constraints["min_force_g"]):
            reasons.append("normal force below contact minimum")
        if force > float(constraints["max_force_g"]):
            reasons.append("normal force above envelope")
        if constraints.get("require_contact") and not contact:
            reasons.append("rider lost contact")
        feature_metrics.append({
            "id": feature["id"],
            "label": feature["label"],
            "point_index": feature["point_index"],
            "speed_mps": round(speed, 4),
            "force_g": round(force, 4),
            "contact": contact,
            "ok": not reasons,
            "reasons": reasons,
        })
    stalled_indices = [index for index, speed in enumerate(speeds) if speed < float(physics["stall_speed_mps"])]
    stalled = bool(stalled_indices)
    completed = bool(path) and not stalled and speeds[-1] >= float(physics["stall_speed_mps"])
    passed = completed and all(item["ok"] for item in feature_metrics)
    return {
        "completed": completed,
        "passed": passed,
        "stalled": stalled,
        "stalled_at_sample": stalled_indices[0] if stalled_indices else None,
        "distance_px": round(distances[-1], 4),
        "duration_ms": int(float(physics["run_duration_ms"])),
        "feature_metrics": feature_metrics,
        "end_speed_mps": round(speeds[-1], 4) if speeds else 0.0,
        "sample_count": len(path),
    }


__all__ = ["MECHANIC_ID", "SOURCE_ANCHORS", "profile_for", "generate", "sample_path", "simulate"]
