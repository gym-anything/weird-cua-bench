from __future__ import annotations

import hashlib
import copy
import random
from typing import Any


MECHANIC_ID = "rotate_wrong_thing_upright"


def _seed(seed: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{MECHANIC_ID}|v2".encode()).digest()[:8], "big")


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed(seed))
    condition = task.get("_control_condition")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    active_axes = [str(axis) for axis in parameters.get("active_axes", ["outer", "middle", "inner"])]
    if not active_axes or len(set(active_axes)) != len(active_axes) or not set(active_axes) <= {"outer", "middle", "inner"}:
        raise ValueError("gimbal active axes are invalid")
    angle_min = int(parameters.get("initial_angle_min", 30))
    angle_max = int(parameters.get("initial_angle_max", 115))
    if condition and int(condition["difficulty"]) != 4:
        def angle(axis: str) -> int:
            if axis not in active_axes:
                return 0
            return rng.choice((-1, 1)) * rng.randrange(angle_min, angle_max + 1, 5)
    else:
        def angle(axis: str) -> int:
            del axis
            value = rng.randrange(-115, 116, 5)
            return value if abs(value) >= 30 else value + (45 if value >= 0 else -45)
    initial = {axis: angle(axis) for axis in ("outer", "middle", "inner")}
    view_count = int(parameters.get("view_count", 3))
    if not 1 <= view_count <= 3:
        raise ValueError("gimbal view count is invalid")
    views = rng.sample(["front", "side", "top"], view_count)
    condition_token = f"|d{condition['difficulty']}|{task.get('id')}" if condition else ""
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|challenge{condition_token}".encode()).hexdigest()[:12]
    coupling = dict(parameters.get("coupling") or {"outer_to_inner": 0.17, "middle_to_outer": -0.13, "inner_to_middle": 0.11})
    contract = {
        "initial": initial,
        "target": {"outer": 0.0, "middle": 0.0, "inner": 0.0},
        "tolerance": float(parameters.get("tolerance", 6.0)),
        "views": views,
        "degrees_per_pixel": float(parameters.get("degrees_per_pixel", 0.42)),
        "max_drag_delta": 180,
        "coupling": coupling,
    }
    if condition:
        contract["active_axes"] = active_axes
        contract["target_needle_width"] = int(parameters.get("target_needle_width", 4))
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "challenge_id": challenge_id,
        "prompt": "Bring the inner mark into world plumb.",
        "asset_manifest": "shared_runtime/assets/provenance/reviewed_overhaul_v1.json",
        "generator": {"name": "tri_axis_gimbal_v2", "variant_count": 47**3 * 6},
        "gimbal": contract,
    }
    truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "seed": seed,
        "challenge_id": challenge_id,
        "gimbal": contract,
    }
    if condition:
        public["control_condition"] = copy.deepcopy(condition)
        truth["control_condition"] = copy.deepcopy(condition)
    return public, truth
