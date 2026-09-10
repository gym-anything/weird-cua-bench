"""Original deterministic 3D foothold-transfer world for Crater Walker.

The source-grounded idea is the quadruped escape task, not a copied MuJoCo
model.  The browser and grader independently use the same small contact
geometry: each leg's three signed channels place a foot in world x/y/z, and a
settle is legal only when at least three feet remain on actual generated pads.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from typing import Any


MECHANIC_ID = "crater_walker"
LEGS = ("front_left", "front_right", "rear_left", "rear_right")
BASE_X = {"front_left": 0.84, "front_right": 0.84, "rear_left": -0.84, "rear_right": -0.84}
BASE_Y = {"front_left": -0.64, "front_right": 0.64, "rear_left": -0.64, "rear_right": 0.64}
ACTUATOR_LIMIT = 5
LIFT_RAISED = 3
LIFT_SCALE = 0.45
EXTEND_SCALE = 0.30
YAW_SCALE = 0.18
DEFAULT_PARAMETERS = {
    "stage_count": 5,
    "decoy_count": 3,
    "contact_tolerance": 0.30,
    "elevation_step": 0.56,
    "lateral_variation": 0.23,
    "terrain_detail": 6,
    "posture_limit": 0.36,
}
VARIANT_COUNT = 4 * 10_000_000


def _rng(seed: str, salt: str = MECHANIC_ID) -> random.Random:
    raw = hashlib.sha256(f"{seed}|{salt}|v1".encode("utf-8")).digest()
    return random.Random(int.from_bytes(raw[:8], "big"))


def _round(value: float) -> float:
    return round(float(value), 4)


def _pose(x: float, y: float, z: float) -> dict[str, float]:
    return {"x": _round(x), "y": _round(y), "z": _round(z), "roll": 0.0, "pitch": 0.0}


def _foot_from(pose: dict[str, float], leg: str, controls: dict[str, int]) -> dict[str, float]:
    return {
        "x": _round(float(pose["x"]) + BASE_X[leg] + int(controls["extend"]) * EXTEND_SCALE),
        "y": _round(float(pose["y"]) + BASE_Y[leg] + int(controls["yaw"]) * YAW_SCALE),
        "z": _round(float(pose["z"]) - 1.28 + int(controls["lift"]) * LIFT_SCALE),
    }


def _inverse_controls(pose: dict[str, float], leg: str, foot: dict[str, float]) -> dict[str, int]:
    controls = {
        "yaw": int(round((float(foot["y"]) - float(pose["y"]) - BASE_Y[leg]) / YAW_SCALE)),
        "lift": int(round((float(foot["z"]) - float(pose["z"]) + 1.28) / LIFT_SCALE)),
        "extend": int(round((float(foot["x"]) - float(pose["x"]) - BASE_X[leg]) / EXTEND_SCALE)),
    }
    return controls


def _posture(pads: dict[str, dict[str, Any]], contacts: dict[str, str | None]) -> tuple[float, float]:
    points = [pads[pad_id] for pad_id in contacts.values() if pad_id in pads]
    if len(points) < 2:
        return 1.0, 1.0
    left = [pads[pad_id] for leg, pad_id in contacts.items() if leg.endswith("left") and pad_id in pads]
    right = [pads[pad_id] for leg, pad_id in contacts.items() if leg.endswith("right") and pad_id in pads]
    front = [pads[pad_id] for leg, pad_id in contacts.items() if leg.startswith("front") and pad_id in pads]
    rear = [pads[pad_id] for leg, pad_id in contacts.items() if leg.startswith("rear") and pad_id in pads]
    left_z = sum(float(p["z"]) for p in left) / len(left) if left else sum(float(p["z"]) for p in points) / len(points)
    right_z = sum(float(p["z"]) for p in right) / len(right) if right else sum(float(p["z"]) for p in points) / len(points)
    front_z = sum(float(p["z"]) for p in front) / len(front) if front else sum(float(p["z"]) for p in points) / len(points)
    rear_z = sum(float(p["z"]) for p in rear) / len(rear) if rear else sum(float(p["z"]) for p in points) / len(points)
    return _round((left_z - right_z) * 0.75), _round((front_z - rear_z) * 0.75)


def _terrain_quads(
    rng: random.Random,
    escape_x: float,
    detail: int,
    pads: list[dict[str, Any]],
    contact_tolerance: float,
) -> list[dict[str, Any]]:
    columns = max(6, int(detail) + 3)
    rows = 6
    x_values = [-1.7 + i * (escape_x + 3.4) / columns for i in range(columns + 1)]
    y_values = [-2.7 + i * 5.4 / rows for i in range(rows + 1)]
    heights: dict[tuple[int, int], float] = {}
    for ix, x in enumerate(x_values):
        for iy, y in enumerate(y_values):
            bowl = 0.16 * (abs(y) / 2.7) ** 1.7
            undulation = 0.035 * math.sin(x * 1.9 + y * 2.3) + 0.02 * math.cos(x * 3.1 - y)
            heights[(ix, iy)] = _round(-0.08 + bowl + undulation + (0.02 * x))
    quads = []
    for ix in range(columns):
        for iy in range(rows):
            quads.append({
                "id": f"terrain-{ix}-{iy}",
                "vertices": [
                    {"x": _round(x_values[ix]), "y": _round(y_values[iy]), "z": heights[(ix, iy)]},
                    {"x": _round(x_values[ix + 1]), "y": _round(y_values[iy]), "z": heights[(ix + 1, iy)]},
                    {"x": _round(x_values[ix + 1]), "y": _round(y_values[iy + 1]), "z": heights[(ix + 1, iy + 1)]},
                    {"x": _round(x_values[ix]), "y": _round(y_values[iy + 1]), "z": heights[(ix, iy + 1)]},
                ],
            })
    # Every visible foothold is also a raised, finite terrain patch.  The
    # contact routines query these quads, rather than treating pad markers as
    # floating points above an unrelated floor mesh.
    for pad in pads:
        # The support footprint is deliberately finite.  It covers the
        # contact tolerance without making a distant ledge an artificial wall
        # across the body's transit corridor.
        half_extent = _round(max(float(pad["radius"]), contact_tolerance))
        x = float(pad["x"])
        y = float(pad["y"])
        z = float(pad["z"])
        quads.append({
            "id": f"support-surface-{pad['id']}",
            "kind": "support_surface",
            "pad_id": str(pad["id"]),
            "vertices": [
                {"x": _round(x - half_extent), "y": _round(y), "z": _round(z)},
                {"x": _round(x), "y": _round(y - half_extent), "z": _round(z)},
                {"x": _round(x + half_extent), "y": _round(y), "z": _round(z)},
                {"x": _round(x), "y": _round(y + half_extent), "z": _round(z)},
            ],
        })
    return quads


def _body_path(previous: dict[str, float], destination: dict[str, float], steps: int = 4) -> list[dict[str, float]]:
    """Finite kinematic integration path used after a valid foot landing."""
    path = []
    for step in range(1, steps + 1):
        fraction = step / steps
        path.append(_pose(
            float(previous["x"]) + (float(destination["x"]) - float(previous["x"])) * fraction,
            float(previous["y"]) + (float(destination["y"]) - float(previous["y"])) * fraction,
            float(previous["z"]) + (float(destination["z"]) - float(previous["z"])) * fraction,
        ))
    return path


def _make_world(seed: str, parameters: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rng = _rng(seed)
    stage_count = int(parameters.get("stage_count", DEFAULT_PARAMETERS["stage_count"]))
    decoy_count = int(parameters.get("decoy_count", DEFAULT_PARAMETERS["decoy_count"]))
    tolerance = float(parameters.get("contact_tolerance", DEFAULT_PARAMETERS["contact_tolerance"]))
    elevation = float(parameters.get("elevation_step", DEFAULT_PARAMETERS["elevation_step"]))
    lateral = float(parameters.get("lateral_variation", DEFAULT_PARAMETERS["lateral_variation"]))
    detail = int(parameters.get("terrain_detail", DEFAULT_PARAMETERS["terrain_detail"]))
    posture_limit = float(parameters.get("posture_limit", DEFAULT_PARAMETERS["posture_limit"]))
    if not 2 <= stage_count <= 6 or not 0 <= decoy_count <= 5:
        raise ValueError("crater walker stage or decoy count is outside supported limits")
    if not 0.20 <= tolerance <= 0.55 or not 0.25 <= elevation <= 0.72:
        raise ValueError("crater walker contact or elevation parameter is outside supported limits")
    if not 0.02 <= lateral <= 0.36 or not 3 <= detail <= 8:
        raise ValueError("crater walker terrain parameter is outside supported limits")

    step_x = 0.50 + elevation * 0.10
    base_z = 1.82
    stages: list[dict[str, Any]] = []
    pads: list[dict[str, Any]] = []
    pads_by_id: dict[str, dict[str, Any]] = {}
    for stage_index in range(stage_count):
        side = -1 if stage_index % 2 else 1
        y = side * lateral * (0.55 + 0.25 * rng.random())
        pose = _pose(stage_index * step_x, y, base_z + stage_index * elevation)
        stance: dict[str, dict[str, int]] = {}
        support_ids: dict[str, str] = {}
        for leg_index, leg in enumerate(LEGS):
            controls = {
                "yaw": rng.choice((-1, 0, 1)),
                "lift": 0,
                "extend": rng.choice((-1, 0, 1)),
            }
            stance[leg] = controls
            foot = _foot_from(pose, leg, controls)
            foot["z"] = _round(float(foot["z"]) + rng.uniform(-0.075, 0.075))
            pad_id = f"ledge-{stage_index + 1}-{leg_index + 1}"
            pad = {
                "id": pad_id,
                "x": foot["x"],
                "y": foot["y"],
                "z": foot["z"],
                "radius": _round(max(0.28, tolerance * 0.88)),
                "material": ("ochre", "teal", "plum", "coral")[leg_index],
            }
            pads.append(pad)
            pads_by_id[pad_id] = pad
            support_ids[leg] = pad_id
        stages.append({
            "index": stage_index,
            "body_pose": pose,
            "body_path_from_previous": [],
            "stance_controls": stance,
            "support_pad_ids": support_ids,
            "transfer_leg": LEGS[(stage_index - 1) % len(LEGS)] if stage_index else None,
        })

    # Decoys sit near the route in depth or at a tempting but unusable height.
    for index in range(decoy_count):
        stage_index = 1 + (index % max(1, stage_count - 1))
        anchor = pads_by_id[stages[stage_index]["support_pad_ids"][LEGS[(index + 2) % len(LEGS)]]]
        stage_y = float(stages[stage_index]["body_pose"]["y"])
        # Keep decoys close to a visible ledge while placing their raised
        # collision patch on the outside of the walker path.  They remain
        # tempting footholds, but cannot silently occupy the body corridor.
        outward = 1.0 if float(anchor["y"]) >= stage_y else -1.0
        angle = outward * (0.35 + rng.random() * 0.22)
        pad = {
            "id": f"decoy-{index + 1}",
            "x": _round(float(anchor["x"]) + rng.uniform(-0.20, 0.20)),
            "y": _round(float(anchor["y"]) + angle),
            "z": _round(float(anchor["z"]) + rng.choice((-0.22, 0.18, 0.30))),
            "radius": _round(max(0.22, tolerance * 0.76)),
            "material": "smoke",
        }
        pads.append(pad)
        pads_by_id[pad["id"]] = pad

    for stage_index in range(1, stage_count):
        stages[stage_index]["body_path_from_previous"] = _body_path(
            stages[stage_index - 1]["body_pose"],
            stages[stage_index]["body_pose"],
        )

    # The generated transfer values are the ordinary actuator settings a
    # scripted oracle uses; they are intentionally not included in public UI.
    transfer_controls: list[dict[str, Any]] = []
    for stage_index in range(1, stage_count):
        stage = stages[stage_index]
        leg = str(stage["transfer_leg"])
        previous_pose = stages[stage_index - 1]["body_pose"]
        pad = pads_by_id[stage["support_pad_ids"][leg]]
        controls = _inverse_controls(previous_pose, leg, pad)
        if any(abs(value) > ACTUATOR_LIMIT for value in controls.values()) or controls["lift"] >= LIFT_RAISED:
            raise ValueError("generated transfer is outside the actuator envelope")
        transfer_controls.append({"stage": stage_index, "leg": leg, "controls": controls})

    # The final body's reference point is visibly just beyond this rim marker.
    escape_x = _round(stages[-1]["body_pose"]["x"] - 0.20)
    world = {
        "version": "crater-world-v1",
        "dimensions": {"width": _round(escape_x + 2.2), "depth": 5.4, "height": _round(base_z + stage_count * elevation + 0.4)},
        "terrain_quads": _terrain_quads(rng, escape_x, detail, pads, tolerance),
        "pads": pads,
        "stages": stages,
        "initial_stage": 0,
        "escape_x": escape_x,
        "contact_tolerance": _round(tolerance),
        "posture_limit": _round(posture_limit),
        "actuator_limit": ACTUATOR_LIMIT,
        "lift_raised": LIFT_RAISED,
        "tick_ms": 240,
        "body_motion_steps": 4,
        "collision_geometry": "terrain_quads_with_support_surfaces",
        "camera": {"yaw": -0.66, "pitch": 0.44},
    }
    return world, transfer_controls


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = copy.deepcopy(task.get("_control_condition"))
    parameters = {**DEFAULT_PARAMETERS, **((condition or {}).get("difficulty_parameters") or {})}
    world, transfers = _make_world(seed, parameters)
    task_id = str(task.get("id") or "crater_walker_seed_0001@0.1")
    condition_token = json.dumps(condition, sort_keys=True, separators=(",", ":")) if condition else "baseline"
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|{condition_token}".encode("utf-8")).hexdigest()[:14]
    prompt = task.get("natural_language") or "Guide the brass walker out of the crater by transferring three-point support across the visible ledges."
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": prompt,
        "submit_label": "CERTIFY ESCAPE",
        "asset_manifest": "shared_runtime/assets/provenance/crater_walker_v0.json",
        "generator": {"name": "crater_walker_contact_v1", "variant_count": VARIANT_COUNT},
        "difficulty_level": int((condition or {}).get("difficulty", 4)),
        "world": copy.deepcopy(world),
        "rules": {
            "channels": "Each leg has signed YAW, LIFT, and EXTEND controls. A high lift releases a foot; a low lift can contact a visible pad.",
            "support": "A settle is safe only with at least three distinct load-bearing feet. A released leg must land on the next terrace's support pad to advance.",
            "transfer_marker": "The next transfer leg is visibly named in the TRANSFER LEG banner and highlighted on its leg card.",
            "transit": "A valid landing starts a four-settle body transit over the raised support terrain; the body advances one visible pose per settle.",
            "posture": "The brass body tilts from the 3D height relationship among its contacting feet; an excessive roll or pitch fails the attempt.",
            "camera": "Orbit the viewport to inspect near and far feet. Camera motion changes only the view, not the world or success condition.",
            "finish": "The whole body must reach the outside ledge with four supporting contacts and an upright posture.",
        },
    }
    truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "world": copy.deepcopy(world),
        "transfer_controls": transfers,
        "variant_count": VARIANT_COUNT,
    }
    if condition:
        public["control_condition"] = copy.deepcopy(condition)
        truth["control_condition"] = copy.deepcopy(condition)
    return public, truth


__all__ = ["MECHANIC_ID", "generate", "_foot_from", "_inverse_controls", "_posture"]
