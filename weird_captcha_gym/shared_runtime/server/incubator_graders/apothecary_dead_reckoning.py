from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "apothecary_dead_reckoning"
SHARED_KEYS = (
    "stage", "origin", "ingredients", "effects", "route_gates", "bones", "vortices",
    "parameters", "mechanics", "interaction_geometry", "order",
)


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _finite(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))


def _number(value: Any, label: str) -> float:
    if not _finite(value):
        raise ValueError(f"{label} is not finite")
    return float(value)


def _point(value: Any, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} is malformed")
    return [_number(value[0], f"{label} x"), _number(value[1], f"{label} y")]


def _close_point(first: Any, second: list[float], label: str, tolerance: float = 0.08) -> None:
    point = _point(first, label)
    if math.dist(point, second) > tolerance:
        raise ValueError(f"{label} disagrees with replayed geometry")


def _inside_rect(point: list[float], rect: list[float], tolerance: float = 0.0) -> bool:
    x, y, width, height = [float(item) for item in rect]
    return x - tolerance <= point[0] <= x + width + tolerance and y - tolerance <= point[1] <= y + height + tolerance


def _inside_polygon(point: list[float], polygon: list[list[float]]) -> bool:
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > point[1]) != (yj > point[1]):
            crossing = (xj - xi) * (point[1] - yi) / (yj - yi) + xi
            if point[0] < crossing:
                inside = not inside
        j = i
    return inside


def _path_points(
    start: list[float], ingredient: dict[str, Any], grind_step: int, grind_notches: int, samples: int
) -> list[list[float]]:
    fraction = grind_step / max(1, grind_notches - 1)
    angle = math.radians(float(ingredient["angle_deg"]))
    turn = math.radians(float(ingredient["curve_degrees"]) * fraction * int(ingredient["turn"]))
    length = float(ingredient["length"])
    points: list[list[float]] = []
    for index in range(samples + 1):
        t = index / samples
        if abs(turn) < 1e-9:
            x = start[0] + length * t * math.cos(angle)
            y = start[1] + length * t * math.sin(angle)
        else:
            radius = length / turn
            x = start[0] + radius * (math.sin(angle + turn * t) - math.sin(angle))
            y = start[1] - radius * (math.cos(angle + turn * t) - math.cos(angle))
        points.append([round(x, 4), round(y, 4)])
    return points


def _heading(ingredient: dict[str, Any], grind_step: int, grind_notches: int, path_index: int, samples: int) -> float:
    fraction = grind_step / max(1, grind_notches - 1)
    return (
        float(ingredient["angle_deg"])
        + float(ingredient["curve_degrees"])
        * fraction
        * int(ingredient["turn"])
        * path_index
        / samples
    ) % 360


def _gate_alignment(
    start: list[float],
    ingredient: dict[str, Any],
    grind_step: int,
    grind_notches: int,
    samples: int,
    gate: dict[str, Any],
    center_tolerance: float,
    heading_tolerance: float,
) -> bool:
    points = _path_points(start, ingredient, grind_step, grind_notches, samples)
    gate_center = [float(item) for item in gate["center"]]
    nearest_index = min(
        range(len(points)),
        key=lambda candidate: math.dist(points[candidate], gate_center),
    )
    center_error = math.dist(points[nearest_index], gate_center)
    heading_error = abs(
        (
            _heading(ingredient, grind_step, grind_notches, nearest_index, samples)
            - float(gate["heading_deg"])
            + 180
        )
        % 360
        - 180
    )
    return center_error <= center_tolerance and heading_error <= heading_tolerance


def _gate_matching_choices(
    start: list[float],
    ingredients: dict[str, dict[str, Any]],
    grind_notches: int,
    samples: int,
    gate: dict[str, Any],
    center_tolerance: float,
    heading_tolerance: float,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for ingredient_id, ingredient in ingredients.items():
        for grind_step in range(grind_notches):
            if _gate_alignment(
                start,
                ingredient,
                grind_step,
                grind_notches,
                samples,
                gate,
                center_tolerance,
                heading_tolerance,
            ):
                matches.append(
                    {"ingredient_id": ingredient_id, "grind_step": grind_step}
                )
    return matches


def _line(first: list[float], second: list[float], samples: int = 8) -> list[list[float]]:
    return [
        [
            round(first[0] + (second[0] - first[0]) * index / samples, 4),
            round(first[1] + (second[1] - first[1]) * index / samples, 4),
        ]
        for index in range(samples + 1)
    ]


def _resolve_motion(
    points: list[list[float]],
    bones: list[dict[str, Any]],
    vortices: list[dict[str, Any]],
    contacted_bones: set[str],
    contacted_vortices: set[str],
) -> tuple[list[float], list[str], str | None, int]:
    new_bones: list[str] = []
    for point in points[1:]:
        for bone in bones:
            bone_id = str(bone["id"])
            if bone_id not in contacted_bones and _inside_polygon(point, bone["polygon"]):
                contacted_bones.add(bone_id)
                new_bones.append(bone_id)
        for vortex in vortices:
            vortex_id = str(vortex["id"])
            if vortex_id in contacted_vortices:
                continue
            center = [float(item) for item in vortex["center"]]
            if math.dist(point, center) <= float(vortex["radius"]):
                contacted_vortices.add(vortex_id)
                spin = int(vortex["spin"])
                dx, dy = point[0] - center[0], point[1] - center[1]
                warped = (
                    [center[0] - dy, center[1] + dx]
                    if spin > 0
                    else [center[0] + dy, center[1] - dx]
                )
                return [round(warped[0], 4), round(warped[1], 4)], sorted(new_bones), vortex_id, spin
    return points[-1][:], sorted(new_bones), None, 0


def _identity(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> str | None:
    if any(str(item.get("mechanic_id") or "") != MECHANIC_ID for item in (payload, truth, public)):
        return "mechanic mismatch"
    for key in ("task_id", "challenge_id"):
        expected = str(truth.get(key) or "")
        if not expected or str(payload.get(key) or "") != expected or str(public.get(key) or "") != expected:
            return f"stale or mismatched {key}"
    return None


def _contract(truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    for key in SHARED_KEYS:
        if public.get(key) != truth.get(key):
            raise ValueError(f"public and hidden {key} disagree")
    condition = truth.get("control_condition")
    if public.get("control_condition") != condition:
        raise ValueError("control condition disagrees")
    parameters = truth.get("parameters")
    if not isinstance(parameters, dict):
        raise ValueError("difficulty parameters are missing")
    if condition is not None and condition.get("difficulty_parameters") != parameters:
        raise ValueError("condition parameters disagree")
    interaction = str((condition or {}).get("interaction") or "full")
    if interaction not in {"simplified", "full"}:
        raise ValueError("interaction mode is invalid")

    stage = truth.get("stage")
    origin = _point(truth.get("origin"), "origin")
    if stage != {"width": 820, "height": 510} or not (0 < origin[0] < 820 and 0 < origin[1] < 510):
        raise ValueError("map geometry is malformed")
    ingredients_value = truth.get("ingredients")
    if not isinstance(ingredients_value, list) or len(ingredients_value) != parameters.get("ingredient_count"):
        raise ValueError("ingredient inventory disagrees with difficulty")
    ingredients: dict[str, dict[str, Any]] = {}
    for ingredient in ingredients_value:
        if not isinstance(ingredient, dict):
            raise ValueError("ingredient record is malformed")
        ingredient_id = str(ingredient.get("id") or "")
        if not ingredient_id or ingredient_id in ingredients:
            raise ValueError("ingredient identity is missing or duplicated")
        for key in ("angle_deg", "length", "curve_degrees", "turn"):
            _number(ingredient.get(key), f"ingredient {ingredient_id} {key}")
        if int(ingredient["turn"]) not in {-1, 1}:
            raise ValueError("ingredient curvature direction is invalid")
        ingredients[ingredient_id] = ingredient

    effects_value = truth.get("effects")
    if not isinstance(effects_value, list) or len(effects_value) != parameters.get("effect_count"):
        raise ValueError("effect field disagrees with difficulty")
    effects: dict[str, dict[str, Any]] = {}
    for effect in effects_value:
        if not isinstance(effect, dict):
            raise ValueError("effect record is malformed")
        effect_id = str(effect.get("id") or "")
        center = _point(effect.get("center"), f"effect {effect_id}")
        radius = _number(effect.get("radius"), f"effect {effect_id} radius")
        if not effect_id or effect_id in effects or not 12 <= radius <= 50 or not (0 <= center[0] <= 820 and 0 <= center[1] <= 510):
            raise ValueError("effect geometry is invalid")
        effects[effect_id] = effect
    target_id = str(truth.get("target_effect_id") or "")
    if target_id not in effects:
        raise ValueError("requested effect is absent")
    order = truth.get("order")
    target = effects[target_id]
    if not isinstance(order, dict) or any(
        order.get(key) != target.get(key) for key in ("name", "glyph", "color")
    ):
        raise ValueError("visible order does not identify the hidden target")
    route_gates = truth.get("route_gates")
    if not isinstance(route_gates, list) or len(route_gates) != parameters.get("route_commits"):
        raise ValueError("route-ring count disagrees with difficulty")
    gate_ids: set[str] = set()
    for gate in route_gates:
        gate_id = str(gate.get("id") or "") if isinstance(gate, dict) else ""
        center = _point(gate.get("center"), f"route ring {gate_id}") if isinstance(gate, dict) else []
        radius = _number(gate.get("radius"), f"route ring {gate_id} radius") if isinstance(gate, dict) else 0
        _number(gate.get("heading_deg"), f"route ring {gate_id} heading") if isinstance(gate, dict) else 0
        if (
            not gate_id
            or gate_id in gate_ids
            or not 8 <= radius <= 22
            or not (0 <= center[0] <= 820 and 0 <= center[1] <= 510)
        ):
            raise ValueError("route-ring geometry is malformed")
        gate_ids.add(gate_id)

    bones = truth.get("bones")
    vortices = truth.get("vortices")
    if not isinstance(bones, list) or len(bones) != parameters.get("bone_count"):
        raise ValueError("bone field disagrees with difficulty")
    if not isinstance(vortices, list) or len(vortices) != parameters.get("vortex_count"):
        raise ValueError("vortex field disagrees with difficulty")
    bone_ids: set[str] = set()
    for bone in bones:
        bone_id = str(bone.get("id") or "") if isinstance(bone, dict) else ""
        polygon = bone.get("polygon") if isinstance(bone, dict) else None
        if not bone_id or bone_id in bone_ids or not isinstance(polygon, list) or not 5 <= len(polygon) <= 6:
            raise ValueError("bone geometry is malformed")
        [_point(point, f"bone {bone_id} vertex") for point in polygon]
        bone_ids.add(bone_id)
    vortex_ids: set[str] = set()
    for vortex in vortices:
        vortex_id = str(vortex.get("id") or "") if isinstance(vortex, dict) else ""
        if not vortex_id or vortex_id in vortex_ids:
            raise ValueError("vortex identity is missing or duplicated")
        _point(vortex.get("center"), f"vortex {vortex_id}")
        if not 12 <= _number(vortex.get("radius"), f"vortex {vortex_id} radius") <= 35 or vortex.get("spin") not in {-1, 1}:
            raise ValueError("vortex geometry is malformed")
        vortex_ids.add(vortex_id)

    mechanics = truth.get("mechanics")
    if (
        not isinstance(mechanics, dict)
        or mechanics.get("path_samples") != 24
        or mechanics.get("stir_stride") != 6
        or mechanics.get("grind_tick_ms") != 240
        or mechanics.get("gate_reveal_factor") != 0.92
        or mechanics.get("gate_center_tolerance") != 2.25
        or mechanics.get("gate_heading_tolerance_degrees") != 2.0
        or mechanics.get("route_feedback") != "post_commit_only"
    ):
        raise ValueError("movement mechanics are malformed")
    geometry = truth.get("interaction_geometry")
    if not isinstance(geometry, dict) or set(geometry.get("jar_rects") or {}) != set(ingredients):
        raise ValueError("jar interaction geometry is malformed")
    for ingredient_id, rect in geometry["jar_rects"].items():
        if not isinstance(rect, list) or len(rect) != 4 or not all(_finite(item) for item in rect):
            raise ValueError(f"jar {ingredient_id} rectangle is malformed")
    mortar = geometry.get("mortar_rect")
    if not isinstance(mortar, list) or len(mortar) != 4 or not all(_finite(item) for item in mortar):
        raise ValueError("mortar rectangle is malformed")

    solution = truth.get("solution")
    if not isinstance(solution, list) or len(solution) != parameters.get("route_commits"):
        raise ValueError("hidden route length disagrees with difficulty")
    position = origin[:]
    solution_bones: set[str] = set()
    solution_vortices: set[str] = set()
    grind_notches = int(parameters["grind_notches"])
    samples = int(mechanics["path_samples"])
    for index, (commit, gate) in enumerate(zip(solution, route_gates), start=1):
        if not isinstance(commit, dict):
            raise ValueError(f"hidden route step {index} is malformed")
        ingredient_id = str(commit.get("ingredient_id") or "")
        grind_step = commit.get("grind_step")
        if (
            ingredient_id not in ingredients
            or isinstance(grind_step, bool)
            or not isinstance(grind_step, int)
            or not 0 <= grind_step < grind_notches
        ):
            raise ValueError(f"hidden route step {index} is invalid")
        expected = {"ingredient_id": ingredient_id, "grind_step": grind_step}
        matches = _gate_matching_choices(
            position,
            ingredients,
            grind_notches,
            samples,
            gate,
            float(mechanics["gate_center_tolerance"]),
            float(mechanics["gate_heading_tolerance_degrees"]),
        )
        if matches != [expected]:
            raise ValueError(f"route ring {index} does not uniquely identify its visible path")
        points = _path_points(
            position,
            ingredients[ingredient_id],
            grind_step,
            grind_notches,
            samples,
        )
        destination, new_bones, vortex_id, _spin = _resolve_motion(
            points,
            bones,
            vortices,
            solution_bones,
            solution_vortices,
        )
        if new_bones or vortex_id is not None or math.dist(destination, points[-1]) > 0.01:
            raise ValueError(f"hidden route step {index} is obstructed")
        position = destination
    if math.dist(position, [float(item) for item in target["center"]]) > 0.01:
        raise ValueError("hidden route does not terminate in the requested effect")
    return {
        "interaction": interaction,
        "parameters": parameters,
        "origin": origin,
        "ingredients": ingredients,
        "effects": effects,
        "target_id": target_id,
        "route_gates": route_gates,
        "bones": bones,
        "vortices": vortices,
        "mechanics": mechanics,
        "geometry": geometry,
    }


def _load_gesture(event: dict[str, Any], ingredient_id: str, geometry: dict[str, Any]) -> None:
    gesture = event.get("gesture")
    if not isinstance(gesture, dict):
        raise ValueError("jar drag lacks physical proof")
    start = _point(gesture.get("start_root"), "jar drag start")
    end = _point(gesture.get("end_root"), "jar drag end")
    travel = _number(gesture.get("travel_px"), "jar drag travel")
    samples = gesture.get("sample_count")
    if not isinstance(samples, int) or isinstance(samples, bool) or samples < 2 or travel < 24:
        raise ValueError("jar drag is stationary or undersampled")
    if not _inside_rect(start, geometry["jar_rects"][ingredient_id], 0.006):
        raise ValueError("jar drag does not start on the claimed visible jar")
    if not _inside_rect(end, geometry["mortar_rect"], 0.012):
        raise ValueError("jar drag does not end in the visible mortar")


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    identity_error = _identity(payload, truth, public)
    if identity_error:
        return _fail(identity_error)
    try:
        contract = _contract(truth, public)
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"invalid apothecary contract: {exc}")

    events = payload.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 2200:
        return _fail("apothecary transcript is missing or outside limits")

    parameters = contract["parameters"]
    mechanics = contract["mechanics"]
    notches = int(parameters["grind_notches"])
    position = contract["origin"][:]
    heading = 0.0
    active_id: str | None = None
    grind_step = 0
    grinding = False
    path: list[list[float]] | None = None
    path_index = 0
    path_aligned = False
    route_progress = 0
    ingredient_spend = water_spend = bellows_spend = seal_count = 0
    contacted_bones: set[str] = set()
    contacted_vortices: set[str] = set()
    sealed_effect: str | None = None

    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return _fail(f"event {sequence} has invalid sequence")
        kind = str(event.get("type") or "")
        try:
            if kind in {"load_ingredient", "replace_ingredient"}:
                replacing = kind == "replace_ingredient"
                if grinding or path is not None or replacing != (active_id is not None):
                    raise ValueError("ingredient load or replacement disagrees with mortar state")
                ingredient_id = str(event.get("ingredient_id") or "")
                if ingredient_id not in contract["ingredients"]:
                    raise ValueError("unknown ingredient was loaded")
                if ingredient_spend >= int(parameters["ingredient_budget"]):
                    raise ValueError("ingredient budget was exceeded")
                expected_source = "jar_drag" if contract["interaction"] == "full" else "jar_select"
                if event.get("input_source") != expected_source:
                    raise ValueError("ingredient was loaded through the wrong interaction surface")
                if contract["interaction"] == "full":
                    _load_gesture(event, ingredient_id, contract["geometry"])
                if replacing and event.get("previous_ingredient_id") != active_id:
                    raise ValueError("ingredient replacement reports the wrong discarded jar")
                active_id = ingredient_id
                grind_step = 0
            elif kind == "grind_start":
                if contract["interaction"] != "full" or event.get("input_source") != "pestle_hold":
                    raise ValueError("grinding used the wrong interaction surface")
                if active_id is None or grinding or path is not None or event.get("grind_step") != grind_step:
                    raise ValueError("pestle hold starts from stale mortar state")
                grinding = True
            elif kind == "grind_tick":
                if contract["interaction"] != "full" or event.get("input_source") != "pestle_hold" or not grinding:
                    raise ValueError("grind tick occurred without a full-interface hold")
                if grind_step >= notches - 1 or event.get("grind_step") != grind_step + 1:
                    raise ValueError("grind tick skips or exceeds a visible notch")
                grind_step += 1
            elif kind == "grind_release":
                if contract["interaction"] != "full" or event.get("input_source") != "pestle_hold" or not grinding:
                    raise ValueError("pestle release has no matching hold")
                if event.get("grind_step") != grind_step:
                    raise ValueError("pestle release reports the wrong grind notch")
                grinding = False
            elif kind == "grind_set":
                if contract["interaction"] != "simplified" or event.get("input_source") != "curve_notches":
                    raise ValueError("grind proxy used the wrong interaction surface")
                if active_id is None or grinding or path is not None:
                    raise ValueError("grind proxy changed a committed or empty mortar")
                step = event.get("grind_step")
                if isinstance(step, bool) or not isinstance(step, int) or not 0 <= step < notches:
                    raise ValueError("grind proxy chose an invalid notch")
                grind_step = step
            elif kind == "stir":
                if event.get("input_source") != "ladle_click" or active_id is None or grinding:
                    raise ValueError("stir occurred without a prepared ingredient")
                if path is None:
                    gate = (
                        contract["route_gates"][route_progress]
                        if route_progress < len(contract["route_gates"])
                        else None
                    )
                    path_aligned = bool(
                        gate
                        and _gate_alignment(
                            position,
                            contract["ingredients"][active_id],
                            grind_step,
                            notches,
                            int(mechanics["path_samples"]),
                            gate,
                            float(mechanics["gate_center_tolerance"]),
                            float(mechanics["gate_heading_tolerance_degrees"]),
                        )
                    )
                    path = _path_points(
                        position,
                        contract["ingredients"][active_id],
                        grind_step,
                        notches,
                        int(mechanics["path_samples"]),
                    )
                    path_index = 0
                if str(event.get("ingredient_id") or "") != active_id or event.get("grind_step") != grind_step:
                    raise ValueError("stir reports the wrong committed ingredient")
                if event.get("path_index_before") != path_index:
                    raise ValueError("stir begins at a stale path index")
                _close_point(event.get("from"), position, "stir origin")
                next_index = min(len(path) - 1, path_index + int(mechanics["stir_stride"]))
                segment = [position[:], *path[path_index + 1 : next_index + 1]]
                destination, new_bones, vortex_id, vortex_spin = _resolve_motion(
                    segment,
                    contract["bones"],
                    contract["vortices"],
                    contacted_bones,
                    contacted_vortices,
                )
                if sorted(event.get("contact_ids") or []) != new_bones:
                    raise ValueError("stir bone contacts disagree with map geometry")
                if (event.get("vortex_id") or None) != vortex_id:
                    raise ValueError("stir vortex contact disagrees with map geometry")
                _close_point(event.get("to"), destination, "stir destination")
                position = destination
                heading = _heading(
                    contract["ingredients"][active_id],
                    grind_step,
                    notches,
                    next_index,
                    int(mechanics["path_samples"]),
                )
                path_index = next_index
                finished = path_index == len(path) - 1 or vortex_id is not None
                if event.get("path_index_after") != path_index or bool(event.get("path_finished")) != finished:
                    raise ValueError("stir completion disagrees with committed path")
                if vortex_id is not None:
                    heading = (heading + vortex_spin * float(mechanics["vortex_turn_degrees"])) % 360
                if finished:
                    ingredient_spend += 1
                    if path_aligned and vortex_id is None:
                        route_progress += 1
                    active_id = None
                    path = None
                    path_index = 0
                    grind_step = 0
                    path_aligned = False
            elif kind in {"water", "bellows"}:
                expected_source = "water_button" if kind == "water" else "bellows_button"
                if event.get("input_source") != expected_source or active_id is not None or grinding or path is not None:
                    raise ValueError(f"{kind} cannot act during an ingredient path")
                _close_point(event.get("from"), position, f"{kind} origin")
                if kind == "water":
                    if water_spend >= int(parameters["water_budget"]):
                        raise ValueError("water budget was exceeded")
                    dx = contract["origin"][0] - position[0]
                    dy = contract["origin"][1] - position[1]
                    distance = math.hypot(dx, dy)
                    step = min(distance, float(parameters["water_step"]))
                    destination = position[:] if distance < 1e-9 else [position[0] + dx / distance * step, position[1] + dy / distance * step]
                    if distance >= 1e-9:
                        heading = math.degrees(math.atan2(dy, dx)) % 360
                    water_spend += 1
                else:
                    if bellows_spend >= int(parameters["bellows_budget"]):
                        raise ValueError("bellows budget was exceeded")
                    radians = math.radians(heading)
                    raw = [
                        position[0] + math.cos(radians) * float(parameters["bellows_step"]),
                        position[1] + math.sin(radians) * float(parameters["bellows_step"]),
                    ]
                    margin = float(mechanics["map_margin"])
                    destination = [
                        min(820 - margin, max(margin, raw[0])),
                        min(510 - margin, max(margin, raw[1])),
                    ]
                    bellows_spend += 1
                motion = _line(position, destination)
                destination, new_bones, vortex_id, vortex_spin = _resolve_motion(
                    motion,
                    contract["bones"],
                    contract["vortices"],
                    contacted_bones,
                    contacted_vortices,
                )
                if sorted(event.get("contact_ids") or []) != new_bones or (event.get("vortex_id") or None) != vortex_id:
                    raise ValueError(f"{kind} contacts disagree with map geometry")
                if vortex_id is not None:
                    heading = (heading + vortex_spin * float(mechanics["vortex_turn_degrees"])) % 360
                _close_point(event.get("to"), destination, f"{kind} destination")
                position = destination
            elif kind == "seal":
                if event.get("input_source") != "seal_button" or grinding:
                    raise ValueError("seal used the wrong surface or interrupted the pestle")
                _close_point(event.get("position"), position, "sealed position")
                seal_count += 1
                matches = [
                    effect_id
                    for effect_id, effect in contract["effects"].items()
                    if math.dist(position, [float(item) for item in effect["center"]]) <= float(effect["radius"])
                ]
                sealed_effect = matches[0] if len(matches) == 1 else None
                if (event.get("effect_id") or None) != sealed_effect:
                    raise ValueError("reported sealed effect disagrees with the visible effect disc")
            else:
                raise ValueError(f"unknown event type {kind!r}")
        except (KeyError, TypeError, ValueError) as exc:
            return _fail(f"event {sequence}: {exc}")

    target = contract["effects"][contract["target_id"]]
    target_distance = round(math.dist(position, [float(item) for item in target["center"]]), 3)
    potency = max(0, round(100 * (1 - target_distance / max(1.0, float(target["radius"])))) )
    try:
        _close_point(payload.get("final_position"), position, "submitted final position", .002)
        submitted_heading = _number(payload.get("heading_deg"), "submitted heading")
        heading_delta = abs((submitted_heading - heading + 180) % 360 - 180)
        if heading_delta > .002:
            raise ValueError("submitted heading does not match apothecary replay")
    except (TypeError, ValueError) as exc:
        return _fail(str(exc))
    expected = {
        "ingredient_spend": ingredient_spend,
        "water_spend": water_spend,
        "bellows_spend": bellows_spend,
        "hazard_contacts": sorted(contacted_bones),
        "vortex_contacts": sorted(contacted_vortices),
        "sealed_effect_id": sealed_effect,
        "seal_count": seal_count,
        "route_progress": route_progress,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            return _fail(f"submitted {key} does not match apothecary replay")
    passed = (
        payload.get("completed") is True
        and seal_count == 1
        and not grinding
        and sealed_effect == contract["target_id"]
        and route_progress == len(contract["route_gates"])
        and len(contacted_bones) <= int(parameters["max_hazard_contacts"])
        and ingredient_spend <= int(parameters["ingredient_budget"])
        and water_spend <= int(parameters["water_budget"])
        and bellows_spend <= int(parameters["bellows_budget"])
    )
    return {
        "graded": True,
        "passed": passed,
        "score": 100 if passed else 0,
        "feedback": (
            f"dead-reckoning replay: effect {sealed_effect or 'none'}; distance {target_distance:.1f}px; "
            f"potency {potency}%; ingredients {ingredient_spend}/{parameters['ingredient_budget']}; "
            f"water {water_spend}/{parameters['water_budget']}; bellows {bellows_spend}/{parameters['bellows_budget']}; "
            f"rings {route_progress}/{len(contract['route_gates'])}; "
            f"bone contacts {len(contacted_bones)}/{parameters['max_hazard_contacts']}; vortices {len(contacted_vortices)}"
        ),
        "metrics": {
            "target_distance_px": target_distance,
            "potency_percent": potency,
            "ingredient_spend": ingredient_spend,
            "water_spend": water_spend,
            "bellows_spend": bellows_spend,
            "route_progress": route_progress,
            "hazard_contact_count": len(contacted_bones),
            "vortex_contact_count": len(contacted_vortices),
        },
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {
        "target_effect_id": ground_truth.get("target_effect_id"),
        "solution": ground_truth.get("solution") or [],
        "answers": [],
    }
