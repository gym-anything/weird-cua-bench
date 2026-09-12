from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "little_planet_mason"
STEP = math.pi / 12.0
STAGE = {"width": 900, "height": 520}
PLANET = {"x": 450, "y": 258, "radius": 116}
PROFILES = {
    1: {"block_count": 3, "decoy_count": 0, "ring_count": 1, "placement_tolerance": 42, "angle_tolerance": 0.35},
    2: {"block_count": 4, "decoy_count": 1, "ring_count": 1, "placement_tolerance": 34, "angle_tolerance": 0.28},
    3: {"block_count": 5, "decoy_count": 1, "ring_count": 2, "placement_tolerance": 28, "angle_tolerance": 0.22},
    4: {"block_count": 7, "decoy_count": 2, "ring_count": 2, "placement_tolerance": 23, "angle_tolerance": 0.18},
    5: {"block_count": 9, "decoy_count": 3, "ring_count": 3, "placement_tolerance": 18, "angle_tolerance": 0.14},
}
COLORS = ["coral", "saffron", "teal", "violet", "blue", "moss", "rose", "amber", "indigo"]


def _seed_int(seed: str, salt: str) -> int:
    return int(hashlib.sha256(f"{seed}|{salt}".encode()).hexdigest()[:16], 16)


def _condition(task: dict[str, Any]) -> tuple[dict[str, Any] | None, int, dict[str, Any]]:
    condition = copy.deepcopy(task.get("_control_condition") or (task.get("metadata") or {}).get("control_condition"))
    level = int((condition or {}).get("difficulty") or 3)
    if level not in PROFILES:
        raise ValueError(f"unsupported Little Planet Mason level {level}")
    params = dict(PROFILES[level])
    params.update((condition or {}).get("difficulty_parameters") or {})
    if int(params["block_count"]) < 3 or int(params["ring_count"]) < 1:
        raise ValueError("malformed Little Planet Mason profile")
    return condition, level, params


def _round(value: float) -> float:
    return round(float(value), 5)


def _angle(value: float) -> float:
    return ((float(value) + math.pi) % (2 * math.pi)) - math.pi


def _palette(index: int, count: int) -> tuple[float, float]:
    return (55 + (index % 5) * 47, 468 - (index // 5) * 42)


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition, level, params = _condition(task)
    count = int(params["block_count"])
    rings = int(params["ring_count"])
    decoys = int(params["decoy_count"])
    tolerance = float(params["placement_tolerance"])
    angle_tolerance = float(params["angle_tolerance"])
    rng = random.Random(_seed_int(seed, f"{MECHANIC_ID}|d{level}"))
    start_angle = rng.choice([0, 1, 2, 3]) * math.pi / 8 + rng.uniform(-0.08, 0.08)
    columns = math.ceil(count / rings)
    block_size = 38
    blocks: list[dict[str, Any]] = []
    for index in range(count):
        ring = index % rings
        column = index // rings
        orbit_angle = start_angle + column * (2 * math.pi / max(columns, 3))
        radius = PLANET["radius"] + block_size / 2 + ring * block_size * 0.98
        target_angle = round((orbit_angle + math.pi / 2) / STEP) * STEP
        tx = PLANET["x"] + math.cos(orbit_angle) * radius
        ty = PLANET["y"] + math.sin(orbit_angle) * radius
        support = "planet" if ring == 0 else f"block-{index - 1}"
        blocks.append({
            "id": f"block-{index}",
            "label": f"MASON {index + 1:02d}",
            "color": COLORS[index % len(COLORS)],
            "size": block_size,
            "palette": list(_palette(index, count + decoys)),
            "target": [_round(tx), _round(ty)],
            "target_angle": _round(target_angle),
            "ring": ring,
            "column": column,
            "support": support,
            "required": True,
        })
    for index in range(decoys):
        palette_index = count + index
        blocks.append({
            "id": f"decoy-{index + 1}",
            "label": f"SPARE {index + 1:02d}",
            "color": COLORS[(count + index + 3) % len(COLORS)],
            "size": block_size,
            "palette": list(_palette(palette_index, count + decoys)),
            "target": None,
            "target_angle": None,
            "ring": None,
            "column": None,
            "support": None,
            "required": False,
        })
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|d{level}".encode()).hexdigest()[:12]
    task_id = str(task.get("id") or f"{MECHANIC_ID}_seed_0001@0.1")
    interaction = str((condition or {}).get("interaction") or "full")
    prompt = "Build the marked ring of blocks around the little planet. Every block must settle on the planet or on its visible lower support."
    public_blocks = []
    for block in blocks:
        visible = {key: block[key] for key in ("id", "label", "color", "size", "palette", "target", "target_angle", "ring", "column", "support", "required")}
        public_blocks.append(visible)
    public: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": prompt,
        "submit_label": "CERTIFY STRUCTURE",
        "asset_manifest": "shared_runtime/assets/provenance/little_planet_mason_v0.json",
        "generator": {"name": "little_planet_mason_radial_v1", "variant_count": 5 * 2 * 10_000_000, "level": level},
        "stage": STAGE,
        "planet": {**PLANET, "theme": rng.randrange(5)},
        "block_size": block_size,
        "blocks": public_blocks,
        "requirements": {"block_count": count, "ring_count": rings, "placement_tolerance": tolerance, "angle_tolerance": angle_tolerance, "stable_settles": count},
        "settling_rule": "At release, radial gravity pulls the square inward along the planet-centre ray. Its inward face must contact the planet or the keyed block immediately below it.",
        "action_hint": "Select, rotate, and click a socket" if interaction == "simplified" else "Drag blocks around the planet; right-click a block to rotate it",
    }
    truth_blocks = copy.deepcopy(blocks)
    order = [index for ring in range(rings) for index in range(count) if index % rings == ring]
    truth: dict[str, Any] = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "level": level,
        "control_condition": condition,
        "stage": STAGE,
        "planet": PLANET,
        "block_size": block_size,
        "blocks": truth_blocks,
        "solution_order": [blocks[index]["id"] for index in order],
        "requirements": public["requirements"],
        "variant_count": 5 * 2 * 10_000_000,
    }
    if condition:
        public["control_condition"] = copy.deepcopy(condition)
    else:
        truth["control_condition"] = None
    return public, truth
