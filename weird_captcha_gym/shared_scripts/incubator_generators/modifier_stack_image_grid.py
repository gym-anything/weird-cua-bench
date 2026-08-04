from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "modifier_stack_image_grid"
STAGE = {"width": 940, "height": 500}
VARIANT_COUNT = 31_000_000_000


MODIFIERS = {
    "rotate": ((45, -45), (90, -90)),
    "slice": ((28, -28), (38, -38)),
    "scale": ((75, 133), (125, 80)),
    "mirror": ((1, 1),),
}

BASELINE_PROFILE = {
    "artifact_count": 3,
    "modifier_count": 3,
    "playback_ms": 3150,
    "playback_minimum_ms": 2900,
    "replay_limit": 1,
    "minimum_chip_moves": 4,
    "minimum_chip_drag_ms": 80,
    "minimum_rail_samples": 24,
    "minimum_rail_ms": 680,
    "maximum_rail_step": 54,
    "rail_gate_x": [310, 510, 710],
    # These are presentation-only controls.  Their true values are part of
    # the untouched historical task; controlled L4/L5 deliberately hide the
    # shortcut after the film so the film remains the source of the order.
    "show_inverse_template": True,
    "show_arrangement_oracle": True,
}


def _public_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    public = copy.deepcopy(artifact)
    for token in public["stack"]:
        token.pop("inverse", None)
    return public


def _seed(seed: str) -> int:
    return int(hashlib.sha256(f"{seed}|{MECHANIC_ID}|restoration-v2".encode()).hexdigest()[:16], 16)


def _profile(task: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Load a controlled profile without perturbing the original L3 task.

    The uncontrolled task takes the exact values that existed before controls.
    The L3 profile supplies those same values, so its seeded random draws and
    resulting restoration world remain byte-for-byte equivalent after the
    control identity itself is removed.
    """

    condition = task.get("_control_condition")
    if condition is None:
        return None, dict(BASELINE_PROFILE)
    if not isinstance(condition, dict):
        raise ValueError("restoration control condition must be an object")
    parameters = condition.get("difficulty_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("restoration difficulty parameters are missing")
    try:
        profile = {
            key: int(parameters[key])
            for key in (
                "artifact_count",
                "modifier_count",
                "playback_ms",
                "playback_minimum_ms",
                "replay_limit",
                "minimum_chip_moves",
                "minimum_chip_drag_ms",
                "minimum_rail_samples",
                "minimum_rail_ms",
                "maximum_rail_step",
            )
        }
        profile["rail_gate_x"] = [int(value) for value in parameters["rail_gate_x"]]
        for key in ("show_inverse_template", "show_arrangement_oracle"):
            if not isinstance(parameters[key], bool):
                raise ValueError(f"restoration {key} must be boolean")
            profile[key] = parameters[key]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("restoration difficulty parameters are incomplete") from exc
    if (
        not 1 <= profile["artifact_count"] <= 3
        or not 2 <= profile["modifier_count"] <= len(MODIFIERS)
        or not 1 <= profile["replay_limit"] <= 3
        or not 2_000 <= profile["playback_ms"] <= 5_000
        or not 1_800 <= profile["playback_minimum_ms"] <= profile["playback_ms"]
        or not 1 <= profile["minimum_chip_moves"] <= 8
        or not 40 <= profile["minimum_chip_drag_ms"] <= 200
        or not 8 <= profile["minimum_rail_samples"] <= 48
        or not 400 <= profile["minimum_rail_ms"] <= 1_200
        or not 24 <= profile["maximum_rail_step"] <= 120
        or not 1 <= len(profile["rail_gate_x"]) <= 4
        or any(not 118 < gate < 822 for gate in profile["rail_gate_x"])
        or profile["rail_gate_x"] != sorted(set(profile["rail_gate_x"]))
    ):
        raise ValueError("restoration difficulty profile is outside the supported contract")
    return copy.deepcopy(condition), profile


def _layout(modifier_count: int) -> tuple[list[dict[str, int]], list[dict[str, int]]]:
    """Return visible rack and inverse-slot geometry for one stack width."""

    if modifier_count == 3:
        # Historical baseline geometry. Keep this literal to preserve the original
        # implementation exactly at its baseline.
        rack_layout = [
            {"x": 205 + index * 190, "y": 234, "width": 150, "height": 56}
            for index in range(3)
        ]
        slots = [
            {"index": index, "x": 252 + index * 190, "y": 324, "width": 142, "height": 60}
            for index in range(3)
        ]
        return rack_layout, slots
    if modifier_count == 2:
        return (
            [
                {"x": 285 + index * 190, "y": 234, "width": 150, "height": 56}
                for index in range(2)
            ],
            [
                {"index": index, "x": 300 + index * 190, "y": 324, "width": 142, "height": 60}
                for index in range(2)
            ],
        )
    return (
        [
            {"x": 125 + index * 170, "y": 234, "width": 140, "height": 56}
            for index in range(4)
        ],
        [
            {"index": index, "x": 150 + index * 160, "y": 324, "width": 130, "height": 60}
            for index in range(4)
        ],
    )


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition, profile = _profile(task)
    rng = random.Random(_seed(seed))
    task_id = str(task.get("id") or "modifier_stack_image_grid_seed_0001@0.1")
    # The uncontrolled task and its L3 pair retain the historical identifier.
    # Other difficulty profiles are distinct challenge contracts even where a
    # shared seed happens to produce overlapping visible tokens.
    difficulty_identity = (
        f"|d{int(condition['difficulty'])}"
        if condition is not None and int(condition.get("difficulty") or 0) != 3
        else ""
    )
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}{difficulty_identity}".encode()).hexdigest()[:13]
    kinds = ["gear", "signal_kite", "forked_key"]
    rng.shuffle(kinds)
    rack_layout, slots = _layout(profile["modifier_count"])
    artifacts: list[dict[str, Any]] = []
    for round_index, artifact_kind in enumerate(kinds[:profile["artifact_count"]]):
        modifier_kinds = rng.sample(tuple(MODIFIERS), profile["modifier_count"])
        stack: list[dict[str, Any]] = []
        for stack_index, modifier_kind in enumerate(modifier_kinds):
            applied, inverse = rng.choice(MODIFIERS[modifier_kind])
            stack.append({
                "id": f"mod-{hashlib.sha256(f'{seed}|{round_index}|{stack_index}'.encode()).hexdigest()[:7]}",
                "kind": modifier_kind,
                "applied": applied,
                "inverse": inverse,
                "sequence": stack_index,
            })
        rack_order = [item["id"] for item in stack]
        rng.shuffle(rack_order)
        rack_rects = [dict(rack_layout[rack_index], token_id=token_id) for rack_index, token_id in enumerate(rack_order)]
        artifacts.append({
            "id": f"artifact-{hashlib.sha256(f'{seed}|artifact|{round_index}'.encode()).hexdigest()[:7]}",
            "sequence": round_index,
            "kind": artifact_kind,
            "ink": rng.choice(("#f0ce72", "#75d9d3", "#e996b4")),
            "stack": stack,
            "rack_order": rack_order,
            "rack_rects": rack_rects,
            "playback_ms": profile["playback_ms"],
            "replay_limit": profile["replay_limit"],
        })
    rail = {
        "start": [118, 414],
        "end": [822, 414],
        "gate_x": profile["rail_gate_x"],
        "half_height": 34,
    }
    requirements = {
        "minimum_chip_moves": profile["minimum_chip_moves"],
        "minimum_chip_drag_ms": profile["minimum_chip_drag_ms"],
        "minimum_rail_samples": profile["minimum_rail_samples"],
        "minimum_rail_ms": profile["minimum_rail_ms"],
        "maximum_rail_step": profile["maximum_rail_step"],
        "playback_minimum_ms": profile["playback_minimum_ms"],
        "maximum_event_time_ms": 240_000,
    }
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": str(task.get("natural_language") or "Watch each corruption stack. Build its inverse in reverse order, then pull the artifact through without breaking contact."),
        "submit_label": "STAMP RESTORATION LOG",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "generator": {"name": "kinetic_modifier_restoration_press_v2", "variant_count": VARIANT_COUNT},
        "stage": STAGE,
        "artifacts": [_public_artifact(artifact) for artifact in artifacts],
        "rail": rail,
        "slots": slots,
        "requirements": requirements,
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "stage": STAGE,
        "artifacts": copy.deepcopy(artifacts),
        "rail": rail,
        "slots": slots,
        "requirements": requirements,
        "variant_count": VARIANT_COUNT,
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    for artifact in artifacts:
        assert len(artifact["stack"]) == profile["modifier_count"] and len(set(artifact["rack_order"])) == profile["modifier_count"]
    return public_state, ground_truth
