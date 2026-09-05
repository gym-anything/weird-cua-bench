from __future__ import annotations

import copy
import hashlib
import itertools
import math
import random
from typing import Any


MECHANIC_ID = "four_pane_pilgrimage"
PANEL_WIDTH = 300.0
PANEL_HEIGHT = 200.0
ROUTE_SLOTS = [0, 1, 3, 2]

BASELINE_PARAMETERS: dict[str, Any] = {
    "slot_scramble": 3,
    "misaligned_panels": 4,
    "alignment_tolerance_units": 28,
    "required_layer_count": 3,
    "decoy_layer_count": 2,
    "clutter_strokes": 12,
    "zoom_choices": [0.8, 0.9, 1.0, 1.1, 1.2],
    "zoom_min": 0.7,
    "zoom_max": 1.4,
    "zoom_step": 0.1,
    "pan_limit": 190,
    "pan_step": 40,
    "offset_steps": 2,
}

PANE_NAMES = ("cedar", "belfry", "cistern", "sanctum")
SCENE_KINDS = ("terraced_garden", "bell_tower", "moon_well", "hill_shrine")
MOTIFS = ("keyhole", "split_moon", "ogive", "well", "lantern", "leaf")
ROUTE_FEATURES = {
    "terraced_garden": {"kind": "terrace_edge", "ink_key": "wash", "accent_key": "ink", "width": 3.1},
    "bell_tower": {"kind": "awning_seam", "ink_key": "night", "accent_key": "gold", "width": 2.7},
    "moon_well": {"kind": "water_channel", "ink_key": "ink", "accent_key": "wash", "width": 3.4},
    "hill_shrine": {"kind": "ridge_contour", "ink_key": "gold", "accent_key": "night", "width": 2.9},
}
PALETTES = (
    {
        "paper": "#e8dfc7",
        "paper_deep": "#d7c79d",
        "ink": "#172a2b",
        "path": "#b8523d",
        "wash": "#658e82",
        "gold": "#c69a4b",
        "night": "#263b4b",
    },
    {
        "paper": "#eadbc2",
        "paper_deep": "#ceb98e",
        "ink": "#292422",
        "path": "#a84535",
        "wash": "#71866b",
        "gold": "#b88d43",
        "night": "#33455d",
    },
    {
        "paper": "#e4ddca",
        "paper_deep": "#c9bea2",
        "ink": "#1e2926",
        "path": "#a84f45",
        "wash": "#627f77",
        "gold": "#c59a52",
        "night": "#2c4050",
    },
)


def _seed(seed: str) -> int:
    digest = hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _condition(task: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any], int]:
    condition = task.get("_control_condition")
    if condition is None:
        return None, copy.deepcopy(BASELINE_PARAMETERS), 4
    if not isinstance(condition, dict):
        raise ValueError("four pane pilgrimage control condition must be an object")
    difficulty = int(condition.get("difficulty") or 0)
    parameters = condition.get("difficulty_parameters")
    if difficulty not in {1, 2, 3, 4, 5} or not isinstance(parameters, dict):
        raise ValueError("four pane pilgrimage control condition is malformed")
    required = set(BASELINE_PARAMETERS)
    if set(parameters) != required:
        missing = sorted(required - set(parameters))
        extra = sorted(set(parameters) - required)
        raise ValueError(f"four pane pilgrimage parameters mismatch; missing={missing}, extra={extra}")
    return copy.deepcopy(condition), copy.deepcopy(parameters), difficulty


def _inverse(point: list[float], transform: dict[str, float]) -> list[float]:
    zoom = float(transform["zoom"])
    return [
        round((point[0] - 150.0 - transform["pan_x"]) / zoom + 150.0, 4),
        round((point[1] - 100.0 - transform["pan_y"]) / zoom + 100.0, 4),
    ]


def _apply(point: list[float], transform: dict[str, float]) -> list[float]:
    return [
        (point[0] - 150.0) * transform["zoom"] + 150.0 + transform["pan_x"],
        (point[1] - 100.0) * transform["zoom"] + 100.0 + transform["pan_y"],
    ]


def _desired_paths(rng: random.Random) -> tuple[list[list[list[float]]], list[dict[str, Any]]]:
    first_y = float(rng.randrange(62, 139, 8))
    second_x = float(rng.randrange(82, 219, 8))
    third_y = float(rng.randrange(62, 139, 8))
    paths = [
        [[42.0, first_y + rng.choice((-22.0, 22.0))], [92.0, first_y + 12.0], [174.0, first_y - 18.0], [250.0, first_y], [300.0, first_y]],
        [[0.0, first_y], [48.0, first_y], [124.0, 96.0], [second_x, 148.0], [second_x, 200.0]],
        [[second_x, 0.0], [second_x, 48.0], [166.0, 104.0], [56.0, third_y], [0.0, third_y]],
        [[300.0, third_y], [250.0, third_y], [188.0, 102.0], [104.0, 126.0], [62.0, 112.0]],
    ]
    joins = [
        {
            "stage": 0,
            "source_slot": 0,
            "target_slot": 1,
            "source_indices": [3, 4],
            "target_indices": [0, 1],
            "source_targets": [paths[0][3], paths[0][4]],
            "target_targets": [paths[1][0], paths[1][1]],
        },
        {
            "stage": 1,
            "source_slot": 1,
            "target_slot": 3,
            "source_indices": [3, 4],
            "target_indices": [0, 1],
            "source_targets": [paths[1][3], paths[1][4]],
            "target_targets": [paths[2][0], paths[2][1]],
        },
        {
            "stage": 2,
            "source_slot": 3,
            "target_slot": 2,
            "source_indices": [3, 4],
            "target_indices": [0, 1],
            "source_targets": [paths[2][3], paths[2][4]],
            "target_targets": [paths[3][0], paths[3][1]],
        },
    ]
    return paths, joins


def _target_transform(rng: random.Random, parameters: dict[str, Any]) -> dict[str, float]:
    zoom = float(rng.choice(list(parameters["zoom_choices"])))
    return {
        "zoom": round(zoom, 3),
        "pan_x": float(rng.choice((-40, -20, 0, 20, 40))),
        "pan_y": float(rng.choice((-30, -15, 0, 15, 30))),
    }


def _offset_transform(
    target: dict[str, float],
    parameters: dict[str, Any],
    index: int,
) -> dict[str, float]:
    limit = float(parameters["pan_limit"])
    step = float(parameters["pan_step"])
    count = max(1, int(parameters["offset_steps"]))
    signs = ((1, 1), (-1, 1), (1, -1), (-1, -1))
    sx, sy = signs[index % len(signs)]
    pan_x = max(-limit, min(limit, target["pan_x"] + sx * step * count))
    pan_y = max(-limit, min(limit, target["pan_y"] + sy * step * count))
    zoom_step = float(parameters["zoom_step"])
    zoom_min = float(parameters["zoom_min"])
    zoom_max = float(parameters["zoom_max"])
    zoom_sign = 1 if index % 2 == 0 else -1
    zoom = target["zoom"] + zoom_sign * zoom_step * min(count, 2)
    if zoom > zoom_max or zoom < zoom_min:
        zoom = target["zoom"] - zoom_sign * zoom_step * min(count, 2)
    return {"zoom": round(max(zoom_min, min(zoom_max, zoom)), 3), "pan_x": pan_x, "pan_y": pan_y}


def _slot_order(route_ids: list[str], scramble: int, rng: random.Random) -> list[str]:
    by_slot = ["", "", "", ""]
    for route_index, slot in enumerate(ROUTE_SLOTS):
        by_slot[slot] = route_ids[route_index]
    if scramble <= 0:
        return by_slot
    if scramble == 1:
        a, b = rng.sample(range(4), 2)
        by_slot[a], by_slot[b] = by_slot[b], by_slot[a]
        return by_slot
    if scramble == 2:
        chosen = rng.sample(range(4), 3)
        values = [by_slot[index] for index in chosen]
        for index, value in zip(chosen, values[1:] + values[:1]):
            by_slot[index] = value
        return by_slot
    # L4 and L5 start with every pane displaced. L4 permits both two-swap
    # double transpositions and three-swap four-cycles. L5 restricts the same
    # four-pane world to four-cycles, whose exact minimum correction is three
    # swaps. ``slot_scramble`` is an order-profile tier, not a swap count.
    candidates = []
    original = list(by_slot)
    for permutation in itertools.permutations(original):
        if all(permutation[index] != original[index] for index in range(4)):
            candidate = list(permutation)
            if scramble >= 4 and _minimum_swaps(candidate, original) != 3:
                continue
            candidates.append(candidate)
    return rng.choice(candidates)


def _minimum_swaps(current: list[str], desired: list[str]) -> int:
    destination = {value: index for index, value in enumerate(desired)}
    permutation = [destination[value] for value in current]
    visited = [False] * len(permutation)
    cycles = 0
    for start in range(len(permutation)):
        if visited[start]:
            continue
        cycles += 1
        cursor = start
        while not visited[cursor]:
            visited[cursor] = True
            cursor = permutation[cursor]
    return len(permutation) - cycles


def _scene_strokes(rng: random.Random, count: int, route_index: int) -> list[list[list[float]]]:
    strokes: list[list[list[float]]] = []
    for index in range(count):
        x = rng.uniform(16, 284)
        y = rng.uniform(18, 182)
        span = rng.uniform(14, 42)
        rise = rng.uniform(-18, 18)
        points = [
            [round(x, 2), round(y, 2)],
            [round(max(4, min(296, x + span * 0.48)), 2), round(max(4, min(196, y + rise)), 2)],
            [round(max(4, min(296, x + span)), 2), round(max(4, min(196, y + rng.uniform(-12, 12))), 2)],
        ]
        if index % 4 == route_index:
            points.reverse()
        strokes.append(points)
    return strokes


def _plate_outline(motif: str, rng: random.Random) -> dict[str, Any]:
    return {
        "motif": motif,
        "notch": round(rng.uniform(-0.22, 0.22), 3),
        "rotation_deg": int(rng.choice((-18, -9, 0, 9, 18))),
        "scale": round(rng.choice((0.86, 0.94, 1.0, 1.08, 1.16)), 2),
    }


def _target_pose(join: dict[str, Any]) -> list[float]:
    start, end = join["target_targets"]
    x = (float(start[0]) + float(end[0])) / 2.0
    y = (float(start[1]) + float(end[1])) / 2.0
    return [round(max(34.0, min(266.0, x)), 3), round(max(34.0, min(166.0, y)), 3)]


def _bridge_axis(join: dict[str, Any]) -> str:
    start, end = join["target_targets"]
    return "horizontal" if abs(float(end[0]) - float(start[0])) >= abs(float(end[1]) - float(start[1])) else "vertical"


def _fragment_profile(rng: random.Random, join: dict[str, Any]) -> dict[str, Any]:
    return {
        "axis": _bridge_axis(join),
        "line_offset": 0,
        "crossbar": rng.choice((-13, -10, 10, 13)),
        "hatch_count": rng.choice((2, 3, 4)),
        "hatch_slant": rng.choice((-1, 1)),
    }


def _near_match_outline(base: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    result = copy.deepcopy(base)
    result["rotation_deg"] = int(result["rotation_deg"] + rng.choice((-12, -8, 8, 12)))
    result["scale"] = round(max(.76, min(1.24, float(result["scale"]) + rng.choice((-.1, -.07, .07, .1)))), 2)
    result["notch"] = round(float(result["notch"]) + rng.choice((-.18, -.12, .12, .18)), 3)
    return result


def _near_match_fragment(base: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    result = copy.deepcopy(base)
    result["line_offset"] = rng.choice((-9, -7, 7, 9))
    result["crossbar"] = int(result["crossbar"] + rng.choice((-7, 7)))
    result["hatch_count"] = max(1, min(5, int(result["hatch_count"]) + rng.choice((-1, 1))))
    result["hatch_slant"] = -int(result["hatch_slant"])
    return result


def _join_error(panel: dict[str, Any], join: dict[str, Any], transform: dict[str, float], source: bool) -> float:
    indices = join["source_indices" if source else "target_indices"]
    targets = join["source_targets" if source else "target_targets"]
    squares = []
    for index, target in zip(indices, targets):
        actual = _apply(panel["path_points"][index], transform)
        squares.append((actual[0] - target[0]) ** 2 + (actual[1] - target[1]) ** 2)
    return 2.0 * math.sqrt(sum(squares) / max(1, len(squares)))


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition, parameters, difficulty = _condition(task)
    rng = random.Random(_seed(seed))
    palette = copy.deepcopy(rng.choice(PALETTES))
    route_ids = list(PANE_NAMES)
    rng.shuffle(route_ids)
    scene_by_id = dict(zip(route_ids, rng.sample(list(SCENE_KINDS), len(SCENE_KINDS))))
    desired_paths, joins = _desired_paths(rng)

    target_transforms: dict[str, dict[str, float]] = {}
    panels: list[dict[str, Any]] = []
    for route_index, panel_id in enumerate(route_ids):
        target = _target_transform(rng, parameters)
        target_transforms[panel_id] = target
        path_points = [_inverse(point, target) for point in desired_paths[route_index]]
        panels.append(
            {
                "id": panel_id,
                "scene_kind": scene_by_id[panel_id],
                "route_index": route_index,
                "path_points": path_points,
                "strokes": _scene_strokes(rng, int(parameters["clutter_strokes"]), route_index),
                "wash_offset": [rng.randint(-24, 24), rng.randint(-18, 18)],
                "landmark_variant": rng.randrange(6),
                "route_style": copy.deepcopy(ROUTE_FEATURES[scene_by_id[panel_id]]),
                "has_pilgrim": route_index == 0,
                "has_shrine": route_index == 3,
            }
        )

    misaligned_count = max(0, min(4, int(parameters["misaligned_panels"])))
    displaced_ids = set(rng.sample(route_ids, misaligned_count))
    initial_transforms: dict[str, dict[str, float]] = {}
    for index, panel_id in enumerate(route_ids):
        target = target_transforms[panel_id]
        initial_transforms[panel_id] = (
            _offset_transform(target, parameters, index) if panel_id in displaced_ids else copy.deepcopy(target)
        )

    initial_slots = _slot_order(route_ids, int(parameters["slot_scramble"]), rng)
    chosen_motifs = rng.sample(list(MOTIFS), 3)
    required_count = max(0, min(3, int(parameters["required_layer_count"])))
    plates: list[dict[str, Any]] = []
    required_by_stage: dict[int, dict[str, Any]] = {}
    for stage in range(required_count):
        plate_id = f"aperture-{stage + 1}"
        outline = _plate_outline(chosen_motifs[stage], rng)
        fragment = _fragment_profile(rng, joins[stage])
        source_anchor = copy.deepcopy(panels[stage]["path_points"][joins[stage]["source_indices"][0]])
        plate = {
            "id": plate_id,
            "source_panel_id": route_ids[stage],
            "required_for_stage": stage,
            "unlock_stage": stage,
            "outline": outline,
            "fragment": fragment,
            "source_anchor": source_anchor,
            "target_pose": _target_pose(joins[stage]),
            "kind": "route_fragment",
        }
        plates.append(plate)
        required_by_stage[stage] = plate
        joins[stage]["required_plate_id"] = plate_id
        joins[stage]["motif"] = chosen_motifs[stage]
        joins[stage]["target_pose"] = copy.deepcopy(plate["target_pose"])
    for stage in range(required_count, 3):
        joins[stage]["required_plate_id"] = None
        joins[stage]["motif"] = chosen_motifs[stage]
        joins[stage]["target_pose"] = _target_pose(joins[stage])

    decoy_ordinals: dict[int, int] = {}
    decoy_anchor_targets = {
        0: ([58.0, 46.0], [78.0, 154.0]),
        1: ([54.0, 46.0], [246.0, 154.0]),
        2: ([244.0, 46.0], [226.0, 154.0]),
    }
    for index in range(max(0, int(parameters["decoy_layer_count"]))):
        unlock_stage = index % max(1, required_count)
        required = required_by_stage[unlock_stage]
        ordinal = decoy_ordinals.get(unlock_stage, 0)
        decoy_ordinals[unlock_stage] = ordinal + 1
        anchor_target = list(decoy_anchor_targets[unlock_stage][ordinal % 2])
        plates.append(
            {
                "id": f"false-aperture-{index + 1}",
                "source_panel_id": route_ids[unlock_stage],
                "required_for_stage": None,
                "unlock_stage": unlock_stage,
                "outline": _near_match_outline(required["outline"], rng),
                "fragment": _near_match_fragment(required["fragment"], rng),
                "source_anchor": _inverse(anchor_target, target_transforms[route_ids[unlock_stage]]),
                "target_pose": copy.deepcopy(required["target_pose"]),
                "kind": "near_match_fragment",
            }
        )

    for stage, join in enumerate(joins):
        join["source_panel_id"] = route_ids[stage]
        join["target_panel_id"] = route_ids[stage + 1]

    task_id = str(task.get("id") or "four_pane_pilgrimage_seed_0001@0.1")
    condition_token = "" if condition is None or difficulty == 4 else f"|d{difficulty}"
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}{condition_token}".encode("utf-8")).hexdigest()[:12]
    public: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Guide the pilgrim through all four pictures to the shrine.",
        "display_prompt": "Lead the pilgrim through the four pictures to the shrine.",
        "submit_label": "SEAL THE PILGRIMAGE",
        "panel_size": {"width": PANEL_WIDTH, "height": PANEL_HEIGHT},
        "route_slots": list(ROUTE_SLOTS),
        "route_panel_ids": list(route_ids),
        "panels": panels,
        "joins": joins,
        "plates": plates,
        "initial_slots": initial_slots,
        "initial_transforms": initial_transforms,
        "limits": {
            "zoom_min": float(parameters["zoom_min"]),
            "zoom_max": float(parameters["zoom_max"]),
            "zoom_step": float(parameters["zoom_step"]),
            "pan_limit": float(parameters["pan_limit"]),
            "pan_step": float(parameters["pan_step"]),
            "alignment_tolerance_units": float(parameters["alignment_tolerance_units"]),
            "plate_drop_tolerance_units": max(18.0, min(36.0, float(parameters["alignment_tolerance_units"]) * .9)),
        },
        "palette": palette,
        "generator": {
            "name": "four_pane_vector_pilgrimage_v1",
            "variant_count": 12_000_000_000,
        },
        "asset_manifest": "shared_runtime/assets/provenance/four_pane_pilgrimage_v0.json",
    }
    if condition is not None:
        public["control_condition"] = copy.deepcopy(condition)

    truth = {
        **copy.deepcopy(public),
        "seed": seed,
        "solution_transforms": target_transforms,
        "difficulty": difficulty,
    }

    # A generated displaced pane must really begin outside the configured
    # continuity tolerance. Otherwise a profile could claim a correspondence
    # search while requiring only the plate click.
    panels_by_id = {panel["id"]: panel for panel in panels}
    for panel_id in displaced_ids:
        route_index = route_ids.index(panel_id)
        errors = []
        if route_index > 0:
            errors.append(_join_error(panels_by_id[panel_id], joins[route_index - 1], initial_transforms[panel_id], False))
        if route_index < 3:
            errors.append(_join_error(panels_by_id[panel_id], joins[route_index], initial_transforms[panel_id], True))
        assert errors and max(errors) > float(parameters["alignment_tolerance_units"])
    assert sorted(initial_slots) == sorted(route_ids)
    assert len({panel["scene_kind"] for panel in panels}) == 4
    assert all(join["source_panel_id"] != join["target_panel_id"] for join in joins)
    return public, truth
