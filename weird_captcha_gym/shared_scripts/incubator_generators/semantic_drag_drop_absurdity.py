from __future__ import annotations

import hashlib
import random
import copy
from typing import Any


MECHANIC_ID = "semantic_drag_drop_absurdity"
SIGNATURES = (
    {"thermal": "bloom", "polarity": "left"},
    {"thermal": "bloom", "polarity": "right"},
    {"thermal": "contract", "polarity": "left"},
    {"thermal": "contract", "polarity": "right"},
)
BASE_GLYPHS = ("△", "○", "◇", "□", "⌁", "✦", "⊙", "⬡")
CONTROL_GLYPHS = BASE_GLYPHS + ("✣", "☍", "◈", "◌")


def _seed(seed: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{MECHANIC_ID}|v2".encode()).digest()[:8], "big")


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed(seed))
    condition = task.get("_control_condition")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    specimen_count = int(parameters.get("specimen_count", len(SIGNATURES)))
    thermal_responses = tuple(parameters.get("thermal_responses", ("bloom", "contract")))
    polarity_responses = tuple(parameters.get("polarity_responses", ("left", "right")))
    if not 2 <= specimen_count <= 6:
        raise ValueError("semantic probe laboratory supports two through six specimens")
    if not thermal_responses or not polarity_responses or specimen_count > len(thermal_responses) * len(polarity_responses):
        raise ValueError("semantic probe laboratory needs one unique response conjunction per specimen")
    signatures = [
        {"thermal": thermal, "polarity": polarity}
        for thermal in thermal_responses
        for polarity in polarity_responses
    ]
    rng.shuffle(signatures)
    signatures = signatures[:specimen_count]
    objects = []
    receivers = []
    expected = {}
    glyph_catalog = BASE_GLYPHS if specimen_count == len(SIGNATURES) and thermal_responses == ("bloom", "contract") and polarity_responses == ("left", "right") else CONTROL_GLYPHS
    glyphs = rng.sample(glyph_catalog, specimen_count * 2)
    for index, signature in enumerate(signatures):
        object_id = f"specimen-{hashlib.sha256(f'{seed}|specimen|{index}'.encode()).hexdigest()[:8]}"
        receiver_id = f"receiver-{hashlib.sha256(f'{seed}|receiver|{index}'.encode()).hexdigest()[:8]}"
        objects.append({
            "id": object_id,
            "glyph": glyphs[index],
            "runtime_signature": signature,
            "x": 44 + (index % 2) * 126 + rng.randint(-6, 6),
            "y": 64 + (index // 2) * 118 + rng.randint(-6, 6),
        })
        receivers.append({
            "id": receiver_id,
            "glyph": glyphs[index + specimen_count],
            "signature": signature,
            "x": 424 + (index % 2) * 126 + rng.randint(-6, 6),
            "y": 58 + (index // 2) * 118 + rng.randint(-6, 6),
        })
        expected[object_id] = receiver_id
    rng.shuffle(objects)
    rng.shuffle(receivers)
    condition_token = (
        f"|d{condition['difficulty']}"
        if condition is not None and int(condition["difficulty"]) != 3
        else ""
    )
    challenge_id = hashlib.sha256(
        f"{seed}|{MECHANIC_ID}|challenge{condition_token}".encode()
    ).hexdigest()[:12]
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "challenge_id": challenge_id,
        "prompt": "Probe the specimens. Route each response to its twin.",
        "asset_manifest": "shared_runtime/assets/provenance/reviewed_overhaul_v1.json",
        "generator": {"name": "causal_probe_lab_v2", "variant_count": 24 * 40320 * 4096},
        "objects": objects,
        "receivers": receivers,
        "probe_hold_ms": int(parameters.get("probe_hold_ms", 420)),
        "response_ms": int(parameters.get("response_ms", 950)),
    }
    truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "seed": seed,
        "challenge_id": challenge_id,
        "expected_assignments": expected,
        "signatures": {item["id"]: item["runtime_signature"] for item in objects},
    }
    if condition is not None:
        public["control_condition"] = copy.deepcopy(condition)
        truth["control_condition"] = copy.deepcopy(condition)
    return public, truth
