from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "temporal_memory_first_change"


def _seed(seed: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{MECHANIC_ID}|v3".encode()).digest()[:8], "big")


def _position(item: dict[str, Any], elapsed_ms: float) -> tuple[float, float]:
    return (
        float(item["x0"]) + math.sin(float(item["phase"]) + elapsed_ms * float(item["rate_x"])) * float(item["amp_x"]),
        float(item["y0"]) + math.cos(float(item["phase"]) * .83 + elapsed_ms * float(item["rate_y"])) * float(item["amp_y"]),
    )


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed(seed))
    condition = task.get("_control_condition")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    object_count = int(parameters.get("object_count", 9))
    decoy_event_count = int(parameters.get("decoy_event_count", 4))
    first_change_duration_ms = int(parameters.get("first_change_duration_ms", 620))
    lens_radius = int(parameters.get("lens_radius", 62))
    minimum_pre_hits = int(parameters.get("minimum_pre_hits", 1))
    minimum_change_hits = int(parameters.get("minimum_change_hits", 2))
    raw_occluders = parameters.get("occluders", ((236, 286), (468, 522)))
    if (
        not 3 <= object_count <= 9
        or not 0 <= decoy_event_count <= object_count - 1
        or not 420 <= first_change_duration_ms <= 1200
        or not 42 <= lens_radius <= 90
        or not 1 <= minimum_pre_hits <= 3
        or not 1 <= minimum_change_hits <= 4
        or not isinstance(raw_occluders, (list, tuple))
    ):
        raise ValueError("first-change control parameters are outside supported limits")
    try:
        occluders = tuple((int(item[0]), int(item[1])) for item in raw_occluders)
    except (IndexError, TypeError, ValueError) as exc:
        raise ValueError("first-change occluders are malformed") from exc
    if any(not 0 <= left < right <= 700 for left, right in occluders):
        raise ValueError("first-change occluders leave the field")

    glyphs = rng.sample(["△", "○", "□", "◇", "✦", "⌁", "⊙", "⬡", "✣", "◐", "⌘", "♢"], object_count)
    objects = []
    for index in range(object_count):
        objects.append(
            {
                "id": f"tracker-{hashlib.sha256(f'{seed}|tracker|{index}'.encode()).hexdigest()[:8]}",
                "glyph": glyphs[index],
                "x0": 62 + index * 72 + rng.randint(-9, 9),
                "y0": rng.randint(72, 258),
                "amp_x": rng.randint(30, 48),
                "amp_y": rng.randint(24, 55),
                "rate_x": round(rng.uniform(0.00058, 0.00094), 7),
                "rate_y": round(rng.uniform(0.00051, 0.00088), 7),
                "phase": round(rng.uniform(0, math.tau), 6),
            }
        )
    first_change_ms = rng.randrange(2700, 3500, 100)
    visible = [
        item
        for item in objects
        if not any(left - 28 <= _position(item, first_change_ms)[0] <= right + 28 for left, right in occluders)
    ]
    target = rng.choice(visible or objects)
    decoys = [item for item in objects if item["id"] != target["id"]]
    rng.shuffle(decoys)
    effects = ["invert", "quarter-turn", "split", "blink", "mirror"]
    events = [
        {
            "object_id": target["id"],
            "at_ms": first_change_ms,
            "duration_ms": first_change_duration_ms,
            "effect": effects[0],
        }
    ]
    cursor = first_change_ms + 900
    for index, item in enumerate(decoys[:decoy_event_count], start=1):
        duration = rng.choice((480, 520, 560))
        events.append(
            {
                "object_id": item["id"],
                "at_ms": cursor,
                "duration_ms": duration,
                "effect": effects[index % len(effects)],
            }
        )
        cursor += rng.choice((690, 760, 830))
    settle_ms = int(events[-1]["at_ms"] + events[-1]["duration_ms"] + 850)
    settle_order = [item["id"] for item in objects]
    rng.shuffle(settle_order)
    contract = {
        "stage": {"width": 700, "height": 330},
        "objects": objects,
        "events": events,
        "first_change_ms": first_change_ms,
        "lens_radius": lens_radius,
        "occluders": [list(item) for item in occluders],
        "settle_ms": settle_ms,
        "review_end_ms": settle_ms - 120,
        "review_step_ms": 40,
        "settle_order": settle_order,
        "settle_grid": {"x0": 160, "y0": 75, "dx": 190, "dy": 95, "columns": 3},
        "proof": {
            "pre_window_ms": 360,
            "minimum_pre_hits": minimum_pre_hits,
            "minimum_change_hits": minimum_change_hits,
        },
    }
    condition_token = f"|d{condition['difficulty']}" if condition is not None else ""
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|challenge-v3{condition_token}".encode()).hexdigest()[:12]
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "challenge_id": challenge_id,
        "prompt": "Find the first reversible change. Mark its carrier after the field settles.",
        "asset_manifest": "shared_runtime/assets/provenance/reviewed_overhaul_v1.json",
        "generator": {"name": "lens_review_spool_v3", "variant_count": 10**15},
        "timeline": contract,
    }
    truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "seed": seed,
        "challenge_id": challenge_id,
        "target_object_id": target["id"],
        "timeline": contract,
    }
    if condition is not None:
        public["control_condition"] = copy.deepcopy(condition)
        truth["control_condition"] = copy.deepcopy(condition)
    return public, truth
