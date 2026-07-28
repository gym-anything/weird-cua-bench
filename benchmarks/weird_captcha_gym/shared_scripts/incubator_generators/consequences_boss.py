from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "consequences_boss"
SCENES = (
    ("lantern", "✦"),
    ("seed", "❋"),
    ("moth", "◈"),
    ("root", "⌁"),
    ("mirror", "◇"),
    ("tide", "≈"),
    ("crown", "♢"),
    ("feather", "⌇"),
)
LEGACY_PALETTE = ("ember", "violet", "moss", "azure", "ivory")
EXTENDED_PALETTE = (*LEGACY_PALETTE, "coral", "silver", "ochre")
SOCKETS = ("left", "right")


def _seed(seed: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{MECHANIC_ID}|v2".encode()).digest()[:8], "big")


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed(seed))
    condition = task.get("_control_condition")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    scene_count = int(parameters.get("scene_count", 5))
    seal_positions = int(parameters.get("seal_positions", 4))
    socket_options = tuple(
        str(item) for item in parameters.get("socket_options", SOCKETS)
    )
    minimum_distinct_states = int(parameters.get("minimum_distinct_states", 1))
    shuffle_judgment = parameters.get("shuffle_judgment", True)
    if not 1 <= scene_count <= len(SCENES):
        raise ValueError("covenant scene count is outside supported limits")
    if seal_positions not in {1, 2, 4}:
        raise ValueError("covenant seal positions must be 1, 2, or 4")
    if not socket_options or len(set(socket_options)) != len(socket_options) or any(
        option not in SOCKETS for option in socket_options
    ):
        raise ValueError("covenant socket options are invalid")
    state_count = len(socket_options) * seal_positions
    if not 1 <= minimum_distinct_states <= min(scene_count, state_count):
        raise ValueError("covenant distinct-state requirement is impossible")
    if not isinstance(shuffle_judgment, bool):
        raise ValueError("covenant shuffle_judgment must be boolean")

    palette = list(
        LEGACY_PALETTE
        if scene_count <= len(LEGACY_PALETTE)
        else EXTENDED_PALETTE
    )
    rng.shuffle(palette)
    scenes = []
    for index, (kind, glyph) in enumerate(SCENES[:scene_count]):
        scene_id = f"covenant-{hashlib.sha256(f'{seed}|{kind}'.encode()).hexdigest()[:9]}"
        scenes.append({
            "id": scene_id,
            "kind": kind,
            "glyph": glyph,
            "color": palette[index],
            "socket_glyphs": rng.sample(
                ["◐", "◒", "△", "▽", "⊂", "⊃"],
                len(socket_options),
            ),
            "initial_seal": rng.randrange(seal_positions),
        })
    boss_order = [scene["id"] for scene in scenes]
    if shuffle_judgment:
        rng.shuffle(boss_order)
    difficulty = int(condition["difficulty"]) if condition else None
    condition_token = "" if difficulty in {None, 1} else f"|d{difficulty}"
    challenge_id = hashlib.sha256(
        f"{seed}|{MECHANIC_ID}|challenge{condition_token}".encode()
    ).hexdigest()[:12]
    prompt = (
        task.get("natural_language")
        or "Make five covenants. Rebuild them when judgment returns."
    )
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "challenge_id": challenge_id,
        "prompt": prompt,
        "asset_manifest": "shared_runtime/assets/provenance/reviewed_overhaul_v1.json",
        "generator": {
            "name": (
                "covenant_reconstruction_v2"
                if difficulty in {None, 1}
                else "covenant_reconstruction_v3_controlled"
            ),
            "variant_count": scene_count * state_count * state_count * 24,
        },
        "scenes": scenes,
        "boss_order": boss_order,
        "storm_ms": 1500,
    }
    truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "seed": seed,
        "challenge_id": challenge_id,
        "scene_ids": [scene["id"] for scene in scenes],
        "boss_order": boss_order,
        "storm_ms": 1500,
    }
    if condition:
        public["control_condition"] = copy.deepcopy(condition)
        truth["control_condition"] = copy.deepcopy(condition)
    return public, truth
