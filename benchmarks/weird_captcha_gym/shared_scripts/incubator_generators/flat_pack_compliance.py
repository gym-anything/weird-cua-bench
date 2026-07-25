from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "flat_pack_compliance"
STAGE = {"width": 900, "height": 480}


def _seed_int(seed: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode()).digest()[:8], "big")


def _local(world: tuple[float, float], center: tuple[float, float], angle: float) -> list[float]:
    dx, dy = world[0] - center[0], world[1] - center[1]
    cosine, sine = math.cos(-angle), math.sin(-angle)
    return [round(dx * cosine - dy * sine, 3), round(dx * sine + dy * cosine, 3)]


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed_int(seed))
    condition = task.get("_control_condition")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    part_order = ("core", "wing-l", "wing-r", "mast", "tip-l", "tip-r", "keel", "cap-l", "cap-r")
    active_part_ids = tuple(parameters.get("part_ids") or part_order[:7])
    if len(active_part_ids) < 3 or len(active_part_ids) > len(part_order) or len(set(active_part_ids)) != len(active_part_ids) or any(part_id not in part_order for part_id in active_part_ids):
        raise ValueError("flat-pack part_ids are outside supported limits")
    mirrored = rng.choice((False, True))
    flip = rng.choice((0.0, math.pi))
    palette = rng.choice((
        ["#f3d66a", "#f48a68", "#7de2d1", "#d7d1bb", "#92b6ff", "#e58de8", "#d9a45c", "#77d6ac", "#be8eff"],
        ["#d4ff71", "#ff8d72", "#72cfff", "#dfd2bd", "#f4c968", "#b99cff", "#8bd4af", "#f18fbe", "#73ddd0"],
        ["#ffd069", "#ff779d", "#69e5c2", "#d9d6c7", "#80b8ff", "#e6a56a", "#b3dc79", "#9c9cff", "#f08c73"],
    ))
    center_x = 450
    left_x, right_x = (590, 310) if mirrored else (310, 590)
    poses = {
        "core": [center_x, 300, flip],
        "wing-l": [left_x, 300, flip],
        "wing-r": [right_x, 300, flip],
        "mast": [center_x, 224, flip],
        "tip-l": [220 if not mirrored else 680, 300, flip],
        "tip-r": [680 if not mirrored else 220, 300, flip],
        "keel": [center_x, 362, flip],
        "cap-l": [160 if not mirrored else 740, 300, flip],
        "cap-r": [740 if not mirrored else 160, 300, flip],
    }
    worlds = {
        "joint-l": [360 if not mirrored else 540, 300],
        "joint-r": [540 if not mirrored else 360, 300],
        "joint-m": [450, 274],
        "joint-tl": [260 if not mirrored else 640, 300],
        "joint-tr": [640 if not mirrored else 260, 300],
        "joint-k": [450, 326],
        "joint-cl": [180 if not mirrored else 720, 300],
        "joint-cr": [720 if not mirrored else 180, 300],
    }
    specs = {
        "core": (180, 52, [[-90, -26], [74, -26], [90, -10], [90, 26], [-90, 26]]),
        "wing-l": (100, 34, [[-50, -17], [40, -17], [50, -7], [50, 17], [-50, 17]]),
        "wing-r": (100, 34, [[-50, -17], [50, -17], [50, 17], [-40, 17], [-50, 7]]),
        "mast": (36, 100, [[-18, -50], [18, -38], [18, 50], [-18, 50]]),
        "tip-l": (80, 30, [[-40, -15], [32, -15], [40, -7], [40, 15], [-40, 15]]),
        "tip-r": (80, 30, [[-40, -15], [40, -15], [40, 15], [-32, 15], [-40, 7]]),
        "keel": (42, 72, [[-21, -36], [21, -36], [15, 36], [-15, 36]]),
        "cap-l": (40, 26, [[-20, -13], [14, -13], [20, -7], [20, 13], [-20, 13]]),
        "cap-r": (40, 26, [[-20, -13], [20, -13], [20, 13], [-14, 13], [-20, 7]]),
    }
    initial_slots = [[125, 82], [290, 82], [420, 82], [535, 82], [630, 78], [730, 78], [810, 190], [90, 190], [810, 270]]
    parts = []
    for part_id in active_part_ids:
        index = part_order.index(part_id)
        width, height, vertices = specs[part_id]
        target = poses[part_id]
        initial_angle = (rng.randrange(4) * math.pi / 2)
        if abs(((initial_angle - flip + math.pi) % (2 * math.pi)) - math.pi) < 0.1:
            initial_angle = (initial_angle + math.pi / 2) % (2 * math.pi)
        parts.append({
            "id": part_id,
            "label": f"{index + 1:02d}",
            "color": palette[index],
            "width": width,
            "height": height,
            "vertices": vertices,
            "initial_pose": [initial_slots[index][0], initial_slots[index][1], round(initial_angle, 6)],
            "target_pose": [target[0], target[1], round(target[2], 6)],
        })
    part_map = {item["id"]: item for item in parts}
    edge_specs = [
        ("joint-l", "core", "wing-l"),
        ("joint-r", "core", "wing-r"),
        ("joint-m", "core", "mast"),
        ("joint-tl", "wing-l", "tip-l"),
        ("joint-tr", "wing-r", "tip-r"),
        ("joint-k", "core", "keel"),
        ("joint-cl", "tip-l", "cap-l"),
        ("joint-cr", "tip-r", "cap-r"),
    ]
    joints = []
    for edge_id, first, second in edge_specs:
        if first not in active_part_ids or second not in active_part_ids:
            continue
        point = worlds[edge_id]
        first_pose, second_pose = poses[first], poses[second]
        joints.append({
            "id": edge_id,
            "a": first,
            "b": second,
            "socket_a": _local(tuple(point), tuple(first_pose[:2]), first_pose[2]),
            "socket_b": _local(tuple(point), tuple(second_pose[:2]), second_pose[2]),
            "world": point,
            "max_distance": int(parameters.get("joint_max_distance", 26)),
            "max_angle_error": float(parameters.get("joint_max_angle_error", 0.14)),
            "stiffness": float(parameters.get("joint_stiffness", 0.93)),
        })
    load_step_count = int(parameters.get("load_step_count", 36))
    load_force_scale = float(parameters.get("load_force_scale", 1.0))
    if not 8 <= load_step_count <= 64 or not .4 <= load_force_scale <= 1.5:
        raise ValueError("flat-pack load parameters are outside supported limits")
    load_steps = [
        {
            "step": step,
            "force_x": round(math.sin(step * 0.73) * (0.0018 + rng.random() * 0.00025) * load_force_scale, 7),
            "force_y": round((0.0012 + math.cos(step * 0.41) * 0.0005) * load_force_scale, 7),
        }
        for step in range(1, load_step_count + 1)
    ]
    joint_factors = {"joint-l": 0.70, "joint-r": 0.85, "joint-m": 1.15, "joint-tl": 0.92, "joint-tr": 1.02, "joint-k": 1.08, "joint-cl": 1.12, "joint-cr": 1.18}
    compliance_model = {
        "force_x_scale": 9000,
        "force_y_scale": 7000,
        "joint_factors": {joint["id"]: joint_factors[joint["id"]] for joint in joints},
        "maximum_step_translation": 26,
        "maximum_step_rotation": 0.42,
        "maximum_contact_penetration": 4.0,
    }
    task_id = str(task.get("id") or "flat_pack_compliance_seed_0001@0.1")
    condition_token = f"|d{condition['difficulty']}|{task.get('id')}" if condition else ""
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}{condition_token}".encode()).hexdigest()[:12]
    public = {
        "benchmark": "weird_captcha_gym", "mechanic_id": MECHANIC_ID, "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Assemble the device correctly. It must remain intact during the compliance test.",
        "submit_label": "CERTIFY ASSEMBLY", "stage": STAGE, "parts": parts, "joints": joints,
        "load_steps": load_steps, "compliance_model": compliance_model, "mirrored": mirrored,
        "requirements": {"pose_tolerance": int(parameters.get("pose_tolerance", 22)), "angle_tolerance": float(parameters.get("angle_tolerance", 0.14)), "load_tick_count": len(load_steps), "strain_limit": int(parameters.get("strain_limit", 42))},
        "generator": {"name": "matter_keyed_flat_pack_v2", "variant_count": 68_400_000_000},
        "clearance_audit": {"target_interior_overlap": 0, "socket_gap": 0, "wall_clearance": 134, "stable_load_margin": 1.8},
        "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
    }
    truth = {**public, "seed": seed, "expected_joint_ids": [item["id"] for item in joints]}
    if condition:
        public["control_condition"] = copy.deepcopy(condition)
        truth["control_condition"] = copy.deepcopy(condition)
    assert len(parts) == len(active_part_ids) and len(joints) == len(parts) - 1
    assert all(80 < item["target_pose"][0] < 820 and 80 < item["target_pose"][1] < 410 for item in parts)
    assert set(truth["expected_joint_ids"]) == {item["id"] for item in joints}
    del part_map
    return public, truth
