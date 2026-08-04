from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "bomb_manual_from_hell"
WIRE_COLORS = (
    "crimson",
    "amber",
    "cobalt",
    "ivory",
    "violet",
    "jade",
    "coral",
    "slate",
    "copper",
    "teal",
    "pewter",
)
PLATE_SPECS = (
    ("plate-cyan", "CYAN", "#63e7dc"),
    ("plate-amber", "AMBER", "#f5b94c"),
    ("plate-magenta", "MAGENTA", "#ee75bd"),
    ("plate-lime", "LIME", "#a8e76d"),
    ("plate-indigo", "INDIGO", "#8b8df2"),
    ("plate-coral", "CORAL", "#ff8b72"),
)
ANCHOR_LAYOUTS = (
    (("triangle", -142, -96), ("square", 124, -73), ("circle", -38, 112), ("diamond", 151, 77)),
    (("triangle", -126, 88), ("square", 139, 74), ("circle", 24, -116), ("diamond", -155, -48)),
    (("triangle", -151, 24), ("square", 72, 118), ("circle", 136, -91), ("diamond", -44, -119)),
    (("triangle", 138, -24), ("square", -92, 116), ("circle", -132, -88), ("diamond", 38, -121)),
    (("triangle", 38, 118), ("square", -148, -38), ("circle", 128, -102), ("diamond", 151, 42)),
    (("triangle", -137, -87), ("square", 146, -57), ("circle", -91, 119), ("diamond", 113, 105)),
)
ANGLE_STEP = 45
PLATE_WIDTH = 420
PLATE_HEIGHT = 330


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _transform(x: float, y: float, pose: dict[str, Any]) -> tuple[float, float]:
    if bool(pose["flipped"]):
        x = -x
    angle = math.radians(float(pose["angle_deg"]))
    cosine, sine = math.cos(angle), math.sin(angle)
    return (
        float(pose["x"]) + x * cosine - y * sine,
        float(pose["y"]) + x * sine + y * cosine,
    )


def _inverse_transform(x: float, y: float, pose: dict[str, Any]) -> tuple[float, float]:
    dx, dy = x - float(pose["x"]), y - float(pose["y"])
    angle = -math.radians(float(pose["angle_deg"]))
    cosine, sine = math.cos(angle), math.sin(angle)
    local_x = dx * cosine - dy * sine
    local_y = dx * sine + dy * cosine
    if bool(pose["flipped"]):
        local_x = -local_x
    return local_x, local_y


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = copy.deepcopy(task.get("_control_condition"))
    difficulty = int((condition or {}).get("difficulty") or 4)
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    plate_count = int(parameters.get("plate_count", 5))
    wire_count = int(parameters.get("wire_count", 9))
    apertures_per_plate = int(parameters.get("apertures_per_plate", 5))
    anchor_count = int(parameters.get("anchor_count", 3))
    rotation_step_deg = int(parameters.get("rotation_step_deg", ANGLE_STEP))
    rotation_offset_steps_min = int(parameters.get("rotation_offset_steps_min", 0))
    rotation_offset_steps_max = int(parameters.get("rotation_offset_steps_max", 360 // rotation_step_deg - 1))
    reflection_mismatch_count = parameters.get("reflection_mismatch_count", "legacy_random")
    snap_tolerance_px = int(parameters.get("snap_tolerance_px", 24))
    aperture_radius_px = int(parameters.get("aperture_radius_px", 21))
    if not 2 <= plate_count <= len(PLATE_SPECS):
        raise ValueError("bomb manual plate_count must be between 2 and 6")
    if not 5 <= wire_count <= len(WIRE_COLORS):
        raise ValueError("bomb manual wire_count must be between 5 and 11")
    if not 2 <= apertures_per_plate < wire_count:
        raise ValueError("bomb manual apertures_per_plate must be between 2 and wire_count - 1")
    if not 2 <= anchor_count <= 4:
        raise ValueError("bomb manual anchor_count must be between 2 and 4")
    if rotation_step_deg not in {30, 45, 90} or 360 % rotation_step_deg:
        raise ValueError("bomb manual rotation_step_deg must be 30, 45, or 90")
    maximum_rotation_steps = 360 // rotation_step_deg - 1
    if not 0 <= rotation_offset_steps_min <= rotation_offset_steps_max <= maximum_rotation_steps:
        raise ValueError("bomb manual rotation offset range is invalid")
    if reflection_mismatch_count != "legacy_random":
        reflection_mismatch_count = int(reflection_mismatch_count)
        if not 0 <= reflection_mismatch_count <= plate_count:
            raise ValueError("bomb manual reflection_mismatch_count is invalid")
    if not 12 <= snap_tolerance_px <= 40 or not 12 <= aperture_radius_px <= 30:
        raise ValueError("bomb manual tolerance or aperture radius is invalid")

    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    colors = list(WIRE_COLORS[:wire_count])
    rng.shuffle(colors)
    wires: list[dict[str, Any]] = []
    for index in range(wire_count):
        wire_id = f"wire-{index + 1}-{hashlib.sha256(f'{seed}|wire|{index}'.encode('utf-8')).hexdigest()[:7]}"
        wire_y = 75 + index * 42 if wire_count == 9 else 75 + index * 336 / (wire_count - 1)
        wires.append(
            {
                "id": wire_id,
                "slot": index,
                "y": round(wire_y, 3),
                "color": colors[index],
                "striped": bool(rng.getrandbits(1)),
            }
        )
    correct_index = rng.randrange(len(wires))
    correct_wire_id = wires[correct_index]["id"]
    decoys = [wire["id"] for wire in wires if wire["id"] != correct_wire_id]
    rng.shuffle(decoys)
    aperture_sets = tuple(
        [
            correct_wire_id,
            *(
                decoys[(index * 2 + offset) % len(decoys)]
                for offset in range(apertures_per_plate - 1)
            ),
        ]
        for index in range(plate_count)
    )
    wire_map = {wire["id"]: wire for wire in wires}
    observation_x = 392
    plates: list[dict[str, Any]] = []
    target_poses: dict[str, dict[str, Any]] = {}
    controlled_transforms = reflection_mismatch_count != "legacy_random"
    transform_rng = random.Random(_seed_int(seed, f"{MECHANIC_ID}|difficulty-{difficulty}|transforms"))
    reflection_mismatches = (
        set(transform_rng.sample(range(plate_count), int(reflection_mismatch_count)))
        if controlled_transforms
        else set()
    )
    for index, ((plate_id, label, color), anchor_layout, aperture_ids) in enumerate(
        zip(PLATE_SPECS[:plate_count], ANCHOR_LAYOUTS[:plate_count], aperture_sets)
    ):
        target_pose = {
            "x": 360 + rng.randint(-15, 15),
            "y": 250 + rng.randint(-12, 12),
            "angle_deg": rng.randrange(0, 360, rotation_step_deg),
            "flipped": bool(rng.getrandbits(1)),
        }
        target_poses[plate_id] = target_pose
        anchors = [
            {"shape": shape, "x": x, "y": y}
            for shape, x, y in anchor_layout[:anchor_count]
        ]
        pins = []
        for anchor in anchors:
            point = _transform(float(anchor["x"]), float(anchor["y"]), target_pose)
            pins.append({"shape": anchor["shape"], "x": round(point[0], 3), "y": round(point[1], 3)})
        apertures = []
        for wire_id in aperture_ids:
            wire = wire_map[wire_id]
            point = _inverse_transform(observation_x, float(wire["y"]), target_pose)
            apertures.append({"wire_id": wire_id, "x": round(point[0], 3), "y": round(point[1], 3)})
        if controlled_transforms:
            rotation_offset = transform_rng.randint(rotation_offset_steps_min, rotation_offset_steps_max)
            initial_angle = (int(target_pose["angle_deg"]) - rotation_offset * rotation_step_deg) % 360
            initial_flipped = bool(target_pose["flipped"]) ^ (index in reflection_mismatches)
        else:
            initial_angle = rng.randrange(0, 360, rotation_step_deg)
            initial_flipped = bool(rng.getrandbits(1))
        plates.append(
            {
                "id": plate_id,
                "label": label,
                "color": color,
                "width": PLATE_WIDTH,
                "height": PLATE_HEIGHT,
                "anchors": anchors,
                "pins": pins,
                "apertures": apertures,
                "initial_pose": {
                    "x": 775 + index * 5,
                    "y": 214 + index * 13,
                    "angle_deg": initial_angle,
                    "flipped": initial_flipped,
                },
            }
        )

    difficulty_identity = "" if difficulty == 4 else f"|d{difficulty}"
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}{difficulty_identity}".encode("utf-8")).hexdigest()[:12]
    task_id = str(task.get("id") or "bomb_manual_from_hell_seed_0001@0.1")
    requirements = {
        "rotation_step_deg": rotation_step_deg,
        "snap_tolerance_px": snap_tolerance_px,
        "aperture_radius_px": aperture_radius_px,
        "plate_count": len(plates),
    }
    stage = {"width": 900, "height": 500, "device": {"x": 34, "y": 36, "width": 662, "height": 428}}
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language")
        or "Register all five transparent manual plates, then cut the only wire left exposed.",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_puzzles_v1.json",
        "generator": {"name": "bomb_manual_acetate_v3", "variant_count": 98_205_696_000},
        "stage": stage,
        "wires": wires,
        "plates": plates,
        "requirements": requirements,
        "observation_x": observation_x,
        "submit_label": "CUT SELECTED WIRE",
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "stage": stage,
        "wires": wires,
        "plates": plates,
        "requirements": requirements,
        "observation_x": observation_x,
        "target_poses": target_poses,
        "correct_wire_id": correct_wire_id,
        "correct_wire_index": correct_index,
        "variant_count": 98_205_696_000,
    }
    if condition:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    assert len(plates) == plate_count and len(wires) == wire_count
    assert set.intersection(*(set(items) for items in aperture_sets)) == {correct_wire_id}
    for plate in plates:
        assert len(plate["anchors"]) == anchor_count
        assert len(plate["pins"]) == anchor_count
        assert len(plate["apertures"]) == apertures_per_plate
    return public_state, ground_truth
