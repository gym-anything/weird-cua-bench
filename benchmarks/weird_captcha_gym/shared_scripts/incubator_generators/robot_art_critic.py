from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "robot_art_critic"
CANVAS_WIDTH = 760
CANVAS_HEIGHT = 470
VARIANT_COUNT = 12_441_600_000
CLASSES = ("umbrella", "sailboat", "fish", "flower", "ladder", "bicycle", "lighthouse", "locomotive")
POSES = {
    "leaning_left": {"angle_deg": -10, "label": "leaning slightly left"},
    "upright": {"angle_deg": 0, "label": "upright"},
    "leaning_right": {"angle_deg": 10, "label": "leaning slightly right"},
}
EXTENDED_POSES = {
    **POSES,
    "leaning_far_left": {"angle_deg": -16, "label": "leaning clearly left"},
    "leaning_far_right": {"angle_deg": 16, "label": "leaning clearly right"},
}
STYLES = {
    "compact": {"x_scale_milli": 860, "label": "compact"},
    "balanced": {"x_scale_milli": 1000, "label": "balanced"},
    "wide": {"x_scale_milli": 1140, "label": "broad"},
}
EXTENDED_STYLES = {
    "very_compact": {"x_scale_milli": 760, "label": "very compact"},
    **STYLES,
    "very_wide": {"x_scale_milli": 1240, "label": "very broad"},
}
EXPECTED_STROKES = {"umbrella": 10, "sailboat": 11, "fish": 10, "flower": 11, "ladder": 11, "bicycle": 11, "lighthouse": 12, "locomotive": 14}
PALETTES = (
    {"name": "gallery_after_dark", "wall": "#d9d4c2", "ink": "#172d38", "robot": "#ff7ce5", "signal": "#56ddc4", "warning": "#ef655c"},
    {"name": "oxide_museum", "wall": "#d9c9b6", "ink": "#3c2c2b", "robot": "#ff9e62", "signal": "#7bc9d4", "warning": "#d94e5b"},
    {"name": "cobalt_salon", "wall": "#cdd5d9", "ink": "#193652", "robot": "#db7bff", "signal": "#73d7a8", "warning": "#e06464"},
    {"name": "lichen_atelier", "wall": "#d2d5bc", "ink": "#293b31", "robot": "#e57ebc", "signal": "#a6d65f", "warning": "#da624e"},
)
DEFAULT_REQUIREMENTS = {
    "maximum_attempts": 5,
    "minimum_points_per_stroke": 5,
    "minimum_stroke_ms": 42,
    "maximum_sample_gap_px": 46,
    "maximum_sample_interval_ms": 180,
    "minimum_bbox_fraction_milli": 360,
    "maximum_bbox_fraction_milli": 820,
    "maximum_center_offset_milli": 165,
    "acceptance_score_milli": 740,
    "minimum_margin_milli": 90,
}


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _profile(task: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return the active task parameters without changing the uncontrolled task."""
    condition = task.get("_control_condition")
    if condition is None:
        return {
            "class_vocabulary": list(CLASSES),
            "pose_options": list(POSES),
            "style_options": list(STYLES),
            "stroke_budget_extra": 1,
            **DEFAULT_REQUIREMENTS,
        }, None
    if not isinstance(condition, dict):
        raise ValueError("robot-art control condition is malformed")
    parameters = condition.get("difficulty_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("robot-art difficulty parameters are malformed")
    return parameters, condition


def _choices(parameters: dict[str, Any], key: str, available: dict[str, Any]) -> tuple[str, ...]:
    selected = tuple(str(name) for name in parameters.get(key) or ())
    if not selected or len(set(selected)) != len(selected) or any(name not in available for name in selected):
        raise ValueError(f"robot-art {key} must select known distinct values")
    return selected


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    task_id = str(task.get("id") or "robot_art_critic_seed_0001@0.1")
    parameters, condition = _profile(task)
    vocabulary = _choices(parameters, "class_vocabulary", {name: name for name in CLASSES})
    pose_options = _choices(parameters, "pose_options", EXTENDED_POSES)
    style_options = _choices(parameters, "style_options", EXTENDED_STYLES)
    # Controlled difficulty identifies a different challenge contract, while
    # the interaction surface deliberately does not: paired inputs must expose
    # the same generated world and goal.  Leave the uncontrolled hash intact
    # so the historical task keeps its existing challenge identity.
    challenge_identity = "semantic-studio-v1"
    if condition is not None and int(condition["difficulty"]) != 4:
        challenge_identity = f"{challenge_identity}|difficulty:{int(condition['difficulty'])}"
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|{challenge_identity}".encode("utf-8")).hexdigest()[:14]
    target_class = rng.choice(vocabulary)
    pose_name = rng.choice(pose_options)
    style_name = rng.choice(style_options)
    palette = copy.deepcopy(rng.choice(PALETTES))
    expected_strokes = EXPECTED_STROKES[target_class]
    stroke_budget_extra = int(parameters.get("stroke_budget_extra", 1))
    if not 0 <= stroke_budget_extra <= 4:
        raise ValueError("robot-art stroke budget extra must be between zero and four")
    stroke_budget = expected_strokes + stroke_budget_extra
    requirements = {
        "stroke_budget": stroke_budget,
        **{key: int(parameters[key]) for key in DEFAULT_REQUIREMENTS},
    }
    pose = {"name": pose_name, **EXTENDED_POSES[pose_name]}
    style = {"name": style_name, **EXTENDED_STYLES[style_name]}
    interaction = str((condition or {}).get("interaction") or "full")
    if interaction not in {"simplified", "full"}:
        raise ValueError("robot-art interaction must be simplified or full")
    drawing_rule = (
        "Click canvas corners to plot a continuous stroke, then commit it. Dense paths are recognized; dots and teleporting segments are rejected."
        if interaction == "simplified"
        else "Draw with continuous pointer holds. Dense paths are recognized; dots and teleporting segments are rejected."
    )
    prompt_action = "plotted" if interaction == "simplified" else "continuous"
    semantic_rule = (
        "The critic compares raster occupancy, direction, moments, symmetry, endpoints, intersections, turns, and stroke topology across every class."
        if condition is None or (int(condition["difficulty"]) == 4 and interaction == "full")
        else "The critic compares raster occupancy, direction, moments, symmetry, endpoints, intersections, turns, and stroke topology across the active class vocabulary."
    )
    target = {
        "class_name": target_class,
        "display_name": target_class.upper(),
        "pose": pose,
        "style": style,
        "expected_strokes": expected_strokes,
    }
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": f"Draw a {style['label']} {target_class} {pose['label']}. Persuade the robot critic using no more than {stroke_budget} {prompt_action} strokes.",
        "submit_label": "ASK THE ROBOT CRITIC",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "generator": {
            "name": "semantic_polyline_art_studio_v2",
            "variant_count": VARIANT_COUNT,
            "variant_count_kind": "class/pose/style/palette/composition/noise construction space",
        },
        "palette": palette,
        "canvas": {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT},
        "target": target,
        "class_vocabulary": [item.upper() for item in vocabulary],
        "requirements": requirements,
        "rules": [
            drawing_rule,
            semantic_rule,
            "Undo or clear freely. A valid first drawing may pass; otherwise use coarse critique and try again within the attempt budget.",
            "No solution trace is shown. The named object, pose, and style are the complete brief.",
        ],
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "palette": palette,
        "canvas": public_state["canvas"],
        "target": copy.deepcopy(target),
        "class_vocabulary": list(vocabulary),
        "requirements": requirements,
        "variant_count": VARIANT_COUNT,
        "variant_count_kind": public_state["generator"]["variant_count_kind"],
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    assert 10 <= expected_strokes <= stroke_budget <= 15
    return public_state, ground_truth
