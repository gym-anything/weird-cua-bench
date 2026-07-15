from __future__ import annotations

import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "relation_prompt_grounding"
STAGE_WIDTH = 900
STAGE_HEIGHT = 430
SETTLE_TICKS = 8
TEMPLATES = (
    ("orb", "BRASS ORB", 30, False, "amber"),
    ("prism", "CYAN PRISM", 34, False, "cyan"),
    ("disk", "RED DISK", 31, False, "red"),
    ("star", "BLACK STAR", 32, False, "black"),
    ("frame", "IVORY FRAME", 72, True, "ivory"),
)


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _settle_delta(component: int) -> int:
    # Match the eight browser Math.round samples used during the physical settle.
    return sum(math.floor(component * factor / SETTLE_TICKS + 0.5) for factor in range(SETTLE_TICKS, 0, -1))


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    templates = list(TEMPLATES)
    rng.shuffle(templates)
    phase_offset = rng.randrange(32)
    carousel_phases = [(phase_offset + slot) % 32 for slot in (0, 6, 12, 19, 25)]
    rng.shuffle(carousel_phases)
    objects: list[dict[str, Any]] = []
    for index, (shape, label, radius, container, color) in enumerate(templates):
        object_id = f"object-{hashlib.sha256(f'{seed}|{shape}'.encode('utf-8')).hexdigest()[:8]}"
        objects.append({
            "id": object_id,
            "label": label,
            "shape": shape,
            "radius": radius,
            "container": container,
            "color": color,
            "carousel_phase": carousel_phases[index],
            "initial_depth": 50,
        })

    frame = next(item for item in objects if item["container"])
    movable = [item for item in objects if not item["container"]]
    front_slots = [(430, 112), (585, 106), (795, 132), (515, 302)]
    rng.shuffle(front_slots)
    depths = [12, 29, 44, 71, 89]
    rng.shuffle(depths)
    positions: dict[str, dict[str, int]] = {
        frame["id"]: {"x": 700, "y": 292, "depth": depths.pop()},
    }
    for item, (x, y) in zip(movable, front_slots):
        positions[item["id"]] = {"x": x + rng.randint(-7, 7), "y": y + rng.randint(-6, 6), "depth": depths.pop()}

    settle_vectors: dict[str, dict[str, int]] = {}
    for item in objects:
        while True:
            vector = {"dx": rng.randint(-2, 2), "dy": rng.randint(-2, 2)}
            if vector != {"dx": 0, "dy": 0}:
                settle_vectors[item["id"]] = vector
                break
    target_states = {
        object_id: {
            "x": state["x"] + _settle_delta(settle_vectors[object_id]["dx"]),
            "y": state["y"] + _settle_delta(settle_vectors[object_id]["dy"]),
            "depth": state["depth"],
        }
        for object_id, state in positions.items()
    }
    projection_targets = [
        {
            "id": item["id"],
            "shape": item["shape"],
            "color": item["color"],
            **target_states[item["id"]],
        }
        for item in objects
    ]

    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode("utf-8")).hexdigest()[:12]
    task_id = str(task.get("id") or "relation_prompt_grounding_seed_0001@0.1")
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": "Reconstruct the hidden sculpture from its FRONT and SIDE projection seals, then survive the force-settle inspection.",
        "submit_label": "CERTIFY DUAL PROJECTION",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "generator": {"name": "dual_projection_sculpture_rig_v2", "variant_count": 14_000_000_000},
        "stage": {"width": STAGE_WIDTH, "height": STAGE_HEIGHT},
        "carousel": {"center": [172, 210], "radius_x": 116, "radius_y": 128, "ticks": 32, "tick_ms": 95},
        "worktable_rect": {"x": 338, "y": 34, "width": 536, "height": 360},
        "objects": objects,
        "projection_targets": projection_targets,
        "settle_vectors": settle_vectors,
        "settle_ticks": SETTLE_TICKS,
        "settle_tick_ms": 110,
        "target_tolerance": {"x": 11, "y": 11, "depth": 3},
        "rules": {
            "front_projection": "FRONT seal constrains horizontal and vertical placement.",
            "side_projection": "SIDE seal constrains depth and vertical placement.",
            "settle": "The seals describe the final sculpture after the visible force-settle drift.",
        },
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "stage": public_state["stage"],
        "carousel": public_state["carousel"],
        "worktable_rect": public_state["worktable_rect"],
        "objects": objects,
        "projection_targets": projection_targets,
        "settle_vectors": settle_vectors,
        "settle_ticks": SETTLE_TICKS,
        "target_tolerance": public_state["target_tolerance"],
        "solution_positions": positions,
        "variant_count": public_state["generator"]["variant_count"],
    }
    assert len(objects) == 5 and len(projection_targets) == 5
    assert len({state["depth"] for state in target_states.values()}) == 5
    assert all(math.isfinite(value) for state in positions.values() for value in state.values())
    return public_state, ground_truth
