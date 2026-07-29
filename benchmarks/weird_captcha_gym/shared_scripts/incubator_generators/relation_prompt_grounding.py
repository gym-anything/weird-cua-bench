from __future__ import annotations

import copy
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
BASELINE_PARAMETERS = {
    "object_count": 5,
    "settle_force_limit": 2,
    "target_tolerance_x": 11,
    "target_tolerance_y": 11,
    "target_tolerance_depth": 3,
    "carousel_tick_ms": 95,
}


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _settle_delta(component: int) -> int:
    # Match the eight browser Math.round samples used during the physical settle.
    return sum(math.floor(component * factor / SETTLE_TICKS + 0.5) for factor in range(SETTLE_TICKS, 0, -1))


def _condition(task: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    raw = task.get("_control_condition")
    if raw is None:
        return copy.deepcopy(BASELINE_PARAMETERS), None
    if not isinstance(raw, dict):
        raise ValueError("relation control condition is malformed")
    if int(raw.get("difficulty") or 0) not in {1, 2, 3, 4, 5}:
        raise ValueError("relation control difficulty is invalid")
    if str(raw.get("interaction") or "") not in {"simplified", "full"}:
        raise ValueError("relation control interaction is invalid")
    supplied = raw.get("difficulty_parameters")
    if not isinstance(supplied, dict):
        raise ValueError("relation difficulty parameters are malformed")
    parameters = copy.deepcopy(BASELINE_PARAMETERS)
    parameters.update(supplied)
    integer_keys = tuple(BASELINE_PARAMETERS)
    if any(isinstance(parameters[key], bool) or not isinstance(parameters[key], int) for key in integer_keys):
        raise ValueError("relation difficulty parameters must be integers")
    if not (
        2 <= parameters["object_count"] <= len(TEMPLATES)
        and 1 <= parameters["settle_force_limit"] <= 3
        and 4 <= parameters["target_tolerance_x"] <= 24
        and 4 <= parameters["target_tolerance_y"] <= 24
        and 1 <= parameters["target_tolerance_depth"] <= 12
        and 60 <= parameters["carousel_tick_ms"] <= 180
    ):
        raise ValueError("relation difficulty parameters are outside supported limits")
    return parameters, copy.deepcopy(raw)


def _object(seed: str, template: tuple[str, str, int, bool, str], phase: int) -> dict[str, Any]:
    shape, label, radius, container, color = template
    return {
        "id": f"object-{hashlib.sha256(f'{seed}|{shape}'.encode('utf-8')).hexdigest()[:8]}",
        "label": label,
        "shape": shape,
        "radius": radius,
        "container": container,
        "color": color,
        "carousel_phase": phase,
        "initial_depth": 50,
    }


def _legacy_generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The pre-control generator, kept byte-for-byte equivalent in behavior."""
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    templates = list(TEMPLATES)
    rng.shuffle(templates)
    phase_offset = rng.randrange(32)
    carousel_phases = [(phase_offset + slot) % 32 for slot in (0, 6, 12, 19, 25)]
    rng.shuffle(carousel_phases)
    objects = [_object(seed, template, carousel_phases[index]) for index, template in enumerate(templates)]

    frame = next(item for item in objects if item["container"])
    movable = [item for item in objects if not item["container"]]
    front_slots = [(430, 112), (585, 106), (795, 132), (515, 302)]
    rng.shuffle(front_slots)
    depths = [12, 29, 44, 71, 89]
    rng.shuffle(depths)
    positions: dict[str, dict[str, int]] = {frame["id"]: {"x": 700, "y": 292, "depth": depths.pop()}}
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
        {"id": item["id"], "shape": item["shape"], "color": item["color"], **target_states[item["id"]]}
        for item in objects
    ]
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode("utf-8")).hexdigest()[:12]
    task_id = str(task.get("id") or "relation_prompt_grounding_seed_0001@0.1")
    public_state = {
        "benchmark": "weird_captcha_gym", "mechanic_id": MECHANIC_ID, "task_id": task_id, "challenge_id": challenge_id,
        "prompt": "Reconstruct the hidden sculpture from its FRONT and SIDE projection seals, then survive the force-settle inspection.",
        "submit_label": "CERTIFY DUAL PROJECTION", "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "generator": {"name": "dual_projection_sculpture_rig_v2", "variant_count": 14_000_000_000},
        "stage": {"width": STAGE_WIDTH, "height": STAGE_HEIGHT},
        "carousel": {"center": [172, 210], "radius_x": 116, "radius_y": 128, "ticks": 32, "tick_ms": 95},
        "worktable_rect": {"x": 338, "y": 34, "width": 536, "height": 360}, "objects": objects,
        "projection_targets": projection_targets, "settle_vectors": settle_vectors, "settle_ticks": SETTLE_TICKS,
        "settle_tick_ms": 110, "target_tolerance": {"x": 11, "y": 11, "depth": 3},
        "rules": {"front_projection": "FRONT seal constrains horizontal and vertical placement.", "side_projection": "SIDE seal constrains depth and vertical placement.", "settle": "The seals describe the final sculpture after the visible force-settle drift."},
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID, "task_id": task_id, "seed": seed, "challenge_id": challenge_id,
        "stage": public_state["stage"], "carousel": public_state["carousel"], "worktable_rect": public_state["worktable_rect"],
        "objects": objects, "projection_targets": projection_targets, "settle_vectors": settle_vectors,
        "settle_ticks": SETTLE_TICKS, "target_tolerance": public_state["target_tolerance"],
        "solution_positions": positions, "variant_count": public_state["generator"]["variant_count"],
    }
    assert len(objects) == 5 and len(projection_targets) == 5
    assert len({state["depth"] for state in target_states.values()}) == 5
    assert all(math.isfinite(value) for state in positions.values() for value in state.values())
    return public_state, ground_truth


def _controlled_generate(task: dict[str, Any], seed: str, parameters: dict[str, Any], condition: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    count = int(parameters["object_count"])
    rng = random.Random(_seed_int(seed, f"{MECHANIC_ID}|d{condition['difficulty']}"))
    frame_template = next(template for template in TEMPLATES if template[3])
    movable_templates = [template for template in TEMPLATES if not template[3]]
    rng.shuffle(movable_templates)
    templates = [frame_template, *movable_templates[: count - 1]]
    rng.shuffle(templates)
    phase_offset = rng.randrange(32)
    carousel_phases = [(phase_offset + slot) % 32 for slot in (0, 6, 12, 19, 25)]
    rng.shuffle(carousel_phases)
    objects = [_object(seed, template, carousel_phases[index]) for index, template in enumerate(templates)]
    frame = next(item for item in objects if item["container"])
    movable = [item for item in objects if not item["container"]]
    front_slots = [(430, 112), (585, 106), (795, 132), (515, 302)]
    rng.shuffle(front_slots)
    depths = rng.sample([12, 29, 44, 71, 89], count)
    positions: dict[str, dict[str, int]] = {frame["id"]: {"x": 700, "y": 292, "depth": depths.pop()}}
    for item, (x, y) in zip(movable, front_slots):
        positions[item["id"]] = {"x": x + rng.randint(-7, 7), "y": y + rng.randint(-6, 6), "depth": depths.pop()}
    force = int(parameters["settle_force_limit"])
    settle_vectors: dict[str, dict[str, int]] = {}
    for item in objects:
        while True:
            vector = {"dx": rng.randint(-force, force), "dy": rng.randint(-force, force)}
            if vector != {"dx": 0, "dy": 0}:
                settle_vectors[item["id"]] = vector
                break
    target_states = {
        object_id: {"x": state["x"] + _settle_delta(settle_vectors[object_id]["dx"]), "y": state["y"] + _settle_delta(settle_vectors[object_id]["dy"]), "depth": state["depth"]}
        for object_id, state in positions.items()
    }
    projection_targets = [{"id": item["id"], "shape": item["shape"], "color": item["color"], **target_states[item["id"]]} for item in objects]
    task_id = str(task.get("id") or "relation_prompt_grounding_seed_0001@0.2")
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|d{condition['difficulty']}".encode("utf-8")).hexdigest()[:12]
    tolerance = {"x": int(parameters["target_tolerance_x"]), "y": int(parameters["target_tolerance_y"]), "depth": int(parameters["target_tolerance_depth"])}
    public_state = {
        "benchmark": "weird_captcha_gym", "mechanic_id": MECHANIC_ID, "task_id": task_id, "challenge_id": challenge_id,
        "prompt": "Reconstruct the sculpture from its FRONT and SIDE projection seals, then survive the force-settle inspection.",
        "submit_label": "CERTIFY DUAL PROJECTION", "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "generator": {"name": "dual_projection_sculpture_rig_v2", "variant_count": 14_000_000_000},
        "stage": {"width": STAGE_WIDTH, "height": STAGE_HEIGHT},
        "carousel": {"center": [172, 210], "radius_x": 116, "radius_y": 128, "ticks": 32, "tick_ms": int(parameters["carousel_tick_ms"])},
        "worktable_rect": {"x": 338, "y": 34, "width": 536, "height": 360}, "objects": objects,
        "projection_targets": projection_targets, "settle_vectors": settle_vectors, "settle_ticks": SETTLE_TICKS,
        "settle_tick_ms": 110, "target_tolerance": tolerance,
        "rules": {"front_projection": "FRONT seal constrains horizontal and vertical placement.", "side_projection": "SIDE seal constrains depth and vertical placement.", "settle": "The seals describe the final sculpture after the visible force-settle drift."},
        "control_condition": copy.deepcopy(condition),
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID, "task_id": task_id, "seed": seed, "challenge_id": challenge_id,
        "stage": public_state["stage"], "carousel": public_state["carousel"], "worktable_rect": public_state["worktable_rect"],
        "objects": objects, "projection_targets": projection_targets, "settle_vectors": settle_vectors, "settle_ticks": SETTLE_TICKS,
        "target_tolerance": tolerance, "solution_positions": positions, "variant_count": public_state["generator"]["variant_count"],
        "control_condition": copy.deepcopy(condition),
    }
    assert len(objects) == count and len({state["depth"] for state in target_states.values()}) == count
    return public_state, ground_truth


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    parameters, condition = _condition(task)
    if condition is None:
        return _legacy_generate(task, seed)
    if int(condition["difficulty"]) == 4:
        public_state, ground_truth = _legacy_generate(task, seed)
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
        return public_state, ground_truth
    return _controlled_generate(task, seed, parameters, condition)
