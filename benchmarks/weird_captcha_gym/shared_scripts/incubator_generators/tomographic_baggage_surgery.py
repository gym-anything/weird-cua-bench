from __future__ import annotations

import hashlib
import math
import random
import copy
from typing import Any


MECHANIC_ID = "tomographic_baggage_surgery"


def _seed(seed: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode()).digest()[:8], "big")


def _distance_xz(a: list[float], b: list[float]) -> float:
    return math.hypot(a[0] - b[0], a[2] - b[2])


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed(seed)); mirror = rng.choice((-1, 1)); target_slot = rng.randrange(4)
    condition = task.get("_control_condition")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    neutral_count = int(parameters.get("neutral_count", 3))
    target_radius = float(parameters.get("target_radius", .56))
    probe_radius = float(parameters.get("probe_radius", .18))
    required_views = int(parameters.get("minimum_views", 2))
    target_rotations = parameters.get("min_target_rotations")
    moving_views = parameters.get("min_moving_views")
    if not 1 <= neutral_count <= 5:
        raise ValueError("tomography neutral_count must be between one and five")
    if not .45 <= target_radius <= .75 or not .14 <= probe_radius <= .24:
        raise ValueError("tomography target or probe radius is outside the supported range")
    if required_views not in {1, 2, 3}:
        raise ValueError("tomography requires one, two, or three registered views")
    if target_rotations is not None and not 1 <= int(target_rotations) <= 4:
        raise ValueError("tomography target rotations must be between one and four")
    if moving_views is not None and not 1 <= int(moving_views) <= required_views:
        raise ValueError("tomography moving views must be within the registered-view requirement")
    palettes = (
        {"paper": "#e9e2d2", "ink": "#16252a", "scan": "#6ff4db", "target": "#ff78a9", "warning": "#ff534f"},
        {"paper": "#dfebea", "ink": "#11232a", "scan": "#75d8ff", "target": "#ff8d70", "warning": "#ef445d"},
        {"paper": "#eee4d3", "ink": "#211d2b", "scan": "#b4ed72", "target": "#f783bd", "warning": "#f0544f"},
    )
    palette = rng.choice(palettes)
    target_center = [round(mirror * (1.35 + rng.uniform(-.18, .18)), 3), round(.1 + rng.uniform(-.25, .25), 3), round(-.45 + rng.uniform(-.2, .2), 3)]
    raw = [
        {"kind": "sphere", "center": target_center, "radius": target_radius, "material": "hot"},
        {"kind": "sphere", "center": [round(-mirror * 2.25, 3), -1.15, 1.25], "radius": .66, "material": "neutral"},
        {"kind": "box", "center": [0, -1.35, -1.9], "half": [.72, .5, .4], "material": "neutral"},
        {"kind": "capsule", "center": [round(-mirror * 1.7, 3), 1.2, 1.4], "radius": .43, "half_segment": .72, "material": "neutral"},
    ]
    neutral_candidates = [
        {"kind": "box", "center": [round(mirror * 2.55, 3), 1.62, -1.6], "half": [.44, .42, .36], "material": "neutral"},
        {"kind": "capsule", "center": [round(mirror * .65, 3), -1.75, 1.55], "radius": .34, "half_segment": .52, "material": "neutral"},
    ]
    raw.extend(neutral_candidates[:max(0, neutral_count - 3)])
    raw = [raw[0], *raw[1:neutral_count + 1]]
    # Rotate presentation IDs/order without changing the private semantic target.
    ordered = raw[target_slot:] + raw[:target_slot]
    solids = []
    target_id = ""
    for index, solid in enumerate(ordered):
        item = {"id": f"volume-{chr(65 + index)}", **solid}; solids.append(item)
        if solid is raw[0]: target_id = item["id"]
    bounds = {"x": [-4, 4], "y": [-3, 3], "z": [-2.5, 2.5]}
    probe = {"initial": [0, 4.35, 0], "radius": probe_radius, "exit_y": 4.05, "sweep_step": .07}
    views = {
        "top": {"axes": ["x", "z"], "signs": [1, 1], "width": 330, "height": 224, "scale": 34, "center": [165, 112]},
        "front": {"axes": ["x", "y"], "signs": [1, -1], "width": 330, "height": 224, "scale": 25, "center": [165, 150]},
        "side": {"axes": ["z", "y"], "signs": [1, -1], "width": 330, "height": 224, "scale": 25, "center": [165, 150]},
    }
    task_id = str(task.get("id") or "tomographic_baggage_surgery_seed_0001@0.1")
    condition_token = f"|difficulty={condition['difficulty']}" if condition else ""
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}{condition_token}".encode()).hexdigest()[:12]
    requirements = {
        "min_observations": int(parameters.get("min_observations", 4)),
        "min_rotations": int(parameters.get("min_rotations", 2)),
        "min_offset_span": float(parameters.get("min_offset_span", 1.0)),
        "min_target_observations": int(parameters.get("min_target_observations", 2)),
        "max_events": 1600,
    }
    if required_views != 2:
        requirements["min_views"] = required_views
    if target_rotations is not None:
        requirements["min_target_rotations"] = int(target_rotations)
    if moving_views is not None:
        requirements["min_moving_views"] = int(moving_views)
    if requirements["min_observations"] < 2 or not 1 <= requirements["min_rotations"] <= 4:
        raise ValueError("tomography observation or rotation requirement is invalid")
    if requirements["min_offset_span"] <= 0 or requirements["min_target_observations"] < 1:
        raise ValueError("tomography observation span or target requirement is invalid")
    public = {
        "benchmark": "weird_captcha_gym", "mechanic_id": MECHANIC_ID, "task_id": task_id, "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Locate and extract the marked contraband without damaging any innocent object.",
        "submit_label": "SEAL SURGICAL REPORT", "bounds": bounds, "solids": solids, "probe": probe, "views": views,
        "slice": {"axes": ["x", "y", "z"], "minimum": -3.0, "maximum": 3.0, "step": .25, "rotations": [0, 1, 2, 3]},
        "requirements": requirements,
        "palette": palette,
        "generator": {"name": "rigid_local_volume_tomography_v1", "variant_count": 1_740_606_264,
                      "variant_count_kind": "2 mirrors × 4 primitive-order rotations × 3 palettes × 361×501×401 rounded target coordinates"},
        "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "render_boundary": "The browser necessarily receives primitive geometry and the hot/neutral material classes used by its renderer, so page internals can identify the target. The ordinary benchmark surface reveals the hot material only when a real slice intersects it; no route or solver coordinates are provided.",
    }
    truth = {**public, "seed": seed, "mirror": mirror, "target_id": target_id,
             "solver": {"target": target_center, "collision": next(s["center"] for s in solids if s["material"] == "neutral" and s["kind"] == "sphere"), "safe_y": 4.35}}
    target = next(s for s in solids if s["id"] == target_id)
    for other in solids:
        if other["id"] == target_id: continue
        if other["kind"] in {"sphere", "capsule"}:
            clearance = _distance_xz(target["center"], other["center"]) - other["radius"]
        else:
            dx = max(0, abs(target["center"][0] - other["center"][0]) - other["half"][0])
            dz = max(0, abs(target["center"][2] - other["center"][2]) - other["half"][2])
            clearance = math.hypot(dx, dz)
        assert clearance > target["radius"] + .24
    assert probe["initial"][1] > bounds["y"][1] and target_center[1] < bounds["y"][1]
    if condition:
        public["control_condition"] = copy.deepcopy(condition)
        truth["control_condition"] = copy.deepcopy(condition)
    return public, truth
