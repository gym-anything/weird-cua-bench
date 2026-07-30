from __future__ import annotations

import hashlib
import itertools
import math
import random
from typing import Any


MECHANIC_ID = "shadow_crime_lab"
CANVAS_WIDTH = 900
CANVAS_HEIGHT = 480
VARIANT_COUNT = 5 * 3 * 10_000_000_000
SHAPES = ("cylinder", "crate", "prism", "bust", "obelisk")
CONTROL_SHAPES = (*SHAPES, "arch")
PALETTES = ("noir-sodium", "cold-case", "red-room")
ANCHORS = ((450, 92), (690, 178), (606, 360), (294, 360), (210, 178))
CONTROL_ANCHORS = (*ANCHORS, (450, 154))
ZONE_ANCHORS = ((112, 82), (788, 82), (788, 398), (112, 398))
CONTROL_ZONE_ANCHORS = (*ZONE_ANCHORS, (450, 432))

BASELINE_PROFILE = {
    "object_count": 5,
    "probe_count": 4,
    "zone_radius": 42,
}
# ``minimum_travel`` was historically exported even though it was not part of
# the visible causal-shadow task. Keep that inert public field stable for the
# uncontrolled/L4 fixed-seed contract; the grader no longer treats it as an
# acceptance quota or a difficulty parameter.
LEGACY_REFERENCE_TRAVEL = {1: 480, 2: 710, 3: 840, 4: 1_050, 5: 1_320}


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _point(x: float, y: float) -> dict[str, float]:
    return {"x": round(x, 2), "y": round(y, 2)}


def _controlled_profile(task: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Validate the selected shared control profile.

    The legacy task remains on the exact original path.  Controlled L4 uses
    the same values and random-draw order as that path, so it reproduces the
    original fixed-seed scene rather than merely resembling it.
    """
    condition = task.get("_control_condition")
    if condition is None:
        return None, dict(BASELINE_PROFILE)
    if not isinstance(condition, dict):
        raise ValueError("shadow-lab control condition must be an object")
    parameters = condition.get("difficulty_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("shadow-lab difficulty parameters are missing")
    try:
        profile = {
            "object_count": int(parameters["object_count"]),
            "probe_count": int(parameters["probe_count"]),
            "zone_radius": int(parameters["zone_radius"]),
        }
        difficulty = int(condition["difficulty"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("shadow-lab difficulty profile is malformed") from exc
    if difficulty not in {1, 2, 3, 4, 5}:
        raise ValueError("shadow-lab difficulty is invalid")
    if str(condition.get("interaction") or "") not in {"simplified", "full"}:
        raise ValueError("shadow-lab interaction is invalid")
    if (
        not 3 <= profile["object_count"] <= len(CONTROL_ANCHORS)
        or not 2 <= profile["probe_count"] <= len(CONTROL_ZONE_ANCHORS)
        or not 34 <= profile["zone_radius"] <= 64
    ):
        raise ValueError("shadow-lab difficulty profile is outside supported limits")
    if difficulty == 4 and profile != BASELINE_PROFILE:
        raise ValueError("shadow-lab L4 must preserve the original profile")
    return dict(condition), profile


def _forge_contract(challenge_id: str, objects: list[dict[str, Any]]) -> dict[str, Any]:
    forge_index = int(challenge_id[0:2], 16) % len(objects)
    law_index = int(challenge_id[2:4], 16) % 3
    parameter_byte = int(challenge_id[4:6], 16)
    if law_index == 0:
        sign = -1 if parameter_byte % 2 else 1
        return {"object_id": objects[forge_index]["id"], "law": "wrong_pivot", "parameter": sign * (0.38 + (parameter_byte % 11) / 100)}
    if law_index == 1:
        scale = 0.54 + (parameter_byte % 8) / 100 if parameter_byte % 2 else 1.38 + (parameter_byte % 8) / 100
        return {"object_id": objects[forge_index]["id"], "law": "wrong_scale", "parameter": round(scale, 2)}
    return {"object_id": objects[forge_index]["id"], "law": "lagged", "parameter": round(0.24 + (parameter_byte % 9) / 100, 2)}


def _effective_lamp(raw: tuple[float, float], initial: tuple[float, float], contract: dict[str, Any]) -> tuple[float, float]:
    dx, dy = raw[0] - initial[0], raw[1] - initial[1]
    parameter = float(contract["parameter"])
    if contract["law"] == "wrong_pivot":
        cosine, sine = math.cos(parameter), math.sin(parameter)
        return initial[0] + dx * cosine - dy * sine, initial[1] + dx * sine + dy * cosine
    if contract["law"] == "wrong_scale":
        return initial[0] + dx * parameter, initial[1] + dy * parameter
    return initial[0] + dx * parameter, initial[1] + dy * parameter


def _shadow_polygon(obj: dict[str, Any], lamp: tuple[float, float], area_radius: float) -> list[tuple[float, float]]:
    ox, oy = float(obj["x"]), float(obj["y"])
    dx, dy = ox - lamp[0], oy - lamp[1]
    distance = max(62.0, math.hypot(dx, dy))
    ux, uy = dx / distance, dy / distance
    px, py = -uy, ux
    radius, height = float(obj["radius"]), float(obj["height"])
    length = _clamp(height * 250.0 / distance, 48.0, 158.0)
    near_width = radius * (0.88 + area_radius / max(distance, 1.0) * 0.42)
    far_width = near_width * (1.0 + height / distance * 0.82) + area_radius * 0.10
    near_x, near_y = ox + ux * radius * 0.28, oy + uy * radius * 0.28
    far_x, far_y = ox + ux * (radius * 0.55 + length), oy + uy * (radius * 0.55 + length)
    return [
        (near_x - px * near_width, near_y - py * near_width),
        (near_x + px * near_width, near_y + py * near_width),
        (far_x + px * far_width, far_y + py * far_width),
        (far_x - px * far_width, far_y - py * far_width),
    ]


def _inside(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
    inside = False
    previous = len(polygon) - 1
    for index, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[previous]
        if ((yi > y) != (yj > y)) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi:
            inside = not inside
        previous = index
    return inside


def _polygons(objects: list[dict[str, Any]], raw_lamp: tuple[float, float], initial_lamp: tuple[float, float], area_radius: float, contract: dict[str, Any]) -> list[tuple[str, list[tuple[float, float]]]]:
    forged_lamp = _effective_lamp(raw_lamp, initial_lamp, contract)
    return [
        (
            str(obj["id"]),
            _shadow_polygon(obj, forged_lamp if obj["id"] == contract["object_id"] else raw_lamp, area_radius),
        )
        for obj in objects
    ]


def _raycast(polygons: list[tuple[str, list[tuple[float, float]]]], x: float, y: float) -> str | None:
    for object_id, polygon in reversed(polygons):
        if _inside(x, y, polygon):
            return object_id
    return None


def _tag_point(polygons: list[tuple[str, list[tuple[float, float]]]], forged_id: str) -> tuple[float, float] | None:
    forged_polygon = next(polygon for object_id, polygon in polygons if object_id == forged_id)
    centroid = (
        sum(point[0] for point in forged_polygon) / len(forged_polygon),
        sum(point[1] for point in forged_polygon) / len(forged_polygon),
    )
    candidates = [centroid]
    for first, second in ((0, 3), (1, 2), (2, 3)):
        candidates.append(((forged_polygon[first][0] + forged_polygon[second][0] + centroid[0]) / 3, (forged_polygon[first][1] + forged_polygon[second][1] + centroid[1]) / 3))
    minimum_x, maximum_x = min(point[0] for point in forged_polygon), max(point[0] for point in forged_polygon)
    minimum_y, maximum_y = min(point[1] for point in forged_polygon), max(point[1] for point in forged_polygon)
    for row in range(1, 6):
        for column in range(1, 6):
            candidates.append((minimum_x + (maximum_x - minimum_x) * column / 6, minimum_y + (maximum_y - minimum_y) * row / 6))
    for x, y in candidates:
        if 14 <= x <= CANVAS_WIDTH - 14 and 14 <= y <= CANVAS_HEIGHT - 14 and _inside(x, y, forged_polygon) and _raycast(polygons, x, y) == forged_id:
            return round(x, 2), round(y, 2)
    return None


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    condition, profile = _controlled_profile(task)
    reference_travel = LEGACY_REFERENCE_TRAVEL[
        int(condition["difficulty"]) if condition is not None else 4
    ]
    challenge_salt = (
        MECHANIC_ID
        if condition is None or int(condition["difficulty"]) == 4
        else f"{MECHANIC_ID}|d{condition['difficulty']}"
    )
    challenge_id = hashlib.sha256(f"{seed}|{challenge_salt}".encode("utf-8")).hexdigest()[:12]
    task_id = str(task.get("id") or "shadow_crime_lab_seed_0001@0.1")
    # Keep the legacy L4 path's five-item shuffle and all following random
    # draws identical to the original uncontrolled generator.
    shapes = list(SHAPES if profile["object_count"] <= len(SHAPES) else CONTROL_SHAPES)
    rng.shuffle(shapes)
    objects = []
    for index, ((anchor_x, anchor_y), shape) in enumerate(
        zip(CONTROL_ANCHORS[:profile["object_count"]], shapes), start=1
    ):
        token = hashlib.sha256(f"{seed}|shadow-object|{index}".encode("utf-8")).hexdigest()[:5]
        objects.append({
            "id": f"evidence-{token}",
            "case_label": f"E-{index:02d}",
            "shape": shape,
            "x": anchor_x + rng.randint(-18, 18),
            "y": anchor_y + rng.randint(-14, 14),
            "radius": rng.randint(18, 26),
            "height": rng.randint(48, 82),
            "tone": rng.choice(("oxide", "slate", "bone", "brass", "umber")),
        })
    lamp_initial = (450 + rng.randint(-15, 15), 238 + rng.randint(-12, 12))
    lamp_type = rng.choice(("point", "area"))
    area_radius = 0.0 if lamp_type == "point" else float(rng.randint(14, 22))
    probe_zones = [
        {
            "id": f"P{index + 1}",
            "x": x + rng.randint(-10, 10),
            "y": y + rng.randint(-9, 9),
            "radius": profile["zone_radius"],
        }
        for index, (x, y) in enumerate(CONTROL_ZONE_ANCHORS[:profile["probe_count"]])
    ]
    contract = _forge_contract(challenge_id, objects)

    solution = None
    zone_permutations = list(itertools.permutations(probe_zones))
    rng.shuffle(zone_permutations)
    for ordering in zone_permutations:
        final_lamp = (float(ordering[-1]["x"]), float(ordering[-1]["y"]))
        polygons = _polygons(objects, final_lamp, lamp_initial, area_radius, contract)
        click = _tag_point(polygons, str(contract["object_id"]))
        if click is None:
            continue
        solution = {
            "probe_path": [{"zone_id": zone["id"], "x": zone["x"], "y": zone["y"]} for zone in ordering],
            "expected_tag_point": _point(*click),
        }
        break
    if solution is None:
        raise RuntimeError("could not find an unobstructed forged-shadow tag point")

    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "prompt": task.get("natural_language") or "Move the light through all probe zones. Tag the shadow that cannot be physically true.",
        "generator": {"name": "analytic_shadow_crime_lab_v1", "variant_count": VARIANT_COUNT},
        "case_number": f"SC-{challenge_id[:4].upper()}-{rng.randint(100, 999)}",
        "palette": rng.choice(PALETTES),
        "canvas": {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT},
        "objects": objects,
        "lamp": {"type": lamp_type, "x": lamp_initial[0], "y": lamp_initial[1], "area_radius": area_radius, "drag_radius": 34},
        "probe_zones": probe_zones,
        "minimum_probe_zones": profile["probe_count"],
        "minimum_travel": reference_travel,
        "submit_label": "FILE FINDING",
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "canvas": public_state["canvas"],
        "objects": objects,
        "lamp": public_state["lamp"],
        "probe_zones": probe_zones,
        "minimum_probe_zones": profile["probe_count"],
        "minimum_travel": reference_travel,
        "forged_object_id": contract["object_id"],
        "forged_law": contract["law"],
        "forged_parameter": contract["parameter"],
        "solution": solution,
        "variant_count": VARIANT_COUNT,
    }
    initial_polygons = _polygons(objects, lamp_initial, lamp_initial, area_radius, contract)
    honest_initial = [_shadow_polygon(obj, lamp_initial, area_radius) for obj in objects]
    assert all(
        all(abs(first[axis] - second[axis]) < 1e-9 for first, second in zip(polygon, honest) for axis in (0, 1))
        for (_, polygon), honest in zip(initial_polygons, honest_initial)
    )
    if condition is not None:
        public_state["control_condition"] = condition
        ground_truth["control_condition"] = condition
    return public_state, ground_truth
