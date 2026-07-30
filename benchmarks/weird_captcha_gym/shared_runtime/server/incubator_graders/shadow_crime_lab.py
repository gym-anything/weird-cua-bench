from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "shadow_crime_lab"
INTERACTION_SURFACES = {
    "simplified": {"probe": "probe_zone_button", "tag_arm": "armed_tag_button", "tag_place": "armed_tag_click"},
    "full": {"lamp": "direct_lamp_drag", "tag": "direct_tag_drag"},
}


def _failure(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _point(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, dict):
        return None
    try:
        x, y = float(value["x"]), float(value["y"])
    except (KeyError, TypeError, ValueError):
        return None
    return (x, y) if math.isfinite(x) and math.isfinite(y) else None


def _point_dict(value: tuple[float, float]) -> dict[str, float]:
    return {"x": round(value[0], 2), "y": round(value[1], 2)}


def _close(first: Any, second: Any, tolerance: float = 0.08) -> bool:
    try:
        return abs(float(first) - float(second)) <= tolerance
    except (TypeError, ValueError):
        return False


def _time(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and 0 <= result <= 3_600_000 else None


def _derive_contract(challenge_id: str, objects: list[dict[str, Any]]) -> dict[str, Any]:
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


def _polygon_area(polygon: list[tuple[float, float]]) -> float:
    return abs(sum(polygon[index][0] * polygon[(index + 1) % len(polygon)][1] - polygon[(index + 1) % len(polygon)][0] * polygon[index][1] for index in range(len(polygon))) / 2)


def _centroid(polygon: list[tuple[float, float]]) -> tuple[float, float]:
    return sum(point[0] for point in polygon) / len(polygon), sum(point[1] for point in polygon) / len(polygon)


def _polygons(objects: list[dict[str, Any]], raw_lamp: tuple[float, float], initial_lamp: tuple[float, float], area_radius: float, contract: dict[str, Any]) -> list[tuple[str, list[tuple[float, float]]]]:
    forged_lamp = _effective_lamp(raw_lamp, initial_lamp, contract)
    return [
        (str(obj["id"]), _shadow_polygon(obj, forged_lamp if obj["id"] == contract["object_id"] else raw_lamp, area_radius))
        for obj in objects
    ]


def _raycast(polygons: list[tuple[str, list[tuple[float, float]]]], x: float, y: float) -> str | None:
    for object_id, polygon in reversed(polygons):
        if _inside(x, y, polygon):
            return object_id
    return None


def _zone_at(position: tuple[float, float], zones: list[dict[str, Any]]) -> str | None:
    for zone in zones:
        if math.hypot(position[0] - float(zone["x"]), position[1] - float(zone["y"])) <= float(zone["radius"]):
            return str(zone["id"])
    return None


def _validate_responses(value: Any, polygons: list[tuple[str, list[tuple[float, float]]]]) -> bool:
    if not isinstance(value, list) or len(value) != len(polygons):
        return False
    for response, (object_id, polygon) in zip(value, polygons):
        if not isinstance(response, dict) or str(response.get("object_id") or "") != object_id:
            return False
        centroid = _point(response.get("centroid"))
        expected_centroid = _centroid(polygon)
        if centroid is None or not _close(centroid[0], expected_centroid[0]) or not _close(centroid[1], expected_centroid[1]):
            return False
        if not _close(response.get("area"), _polygon_area(polygon), 0.16):
            return False
    return True


def _control_contract(
    ground_truth: dict[str, Any],
    public_state: dict[str, Any],
    objects: list[dict[str, Any]],
    zones: list[dict[str, Any]],
) -> tuple[str, dict[str, int] | None, str | None]:
    """Bind controlled profiles to the generated scene and input surface."""
    truth_condition = ground_truth.get("control_condition")
    public_condition = public_state.get("control_condition")
    if truth_condition is None and public_condition is None:
        return "full", None, None
    if not isinstance(truth_condition, dict) or public_condition != truth_condition:
        return "", None, "public shadow-lab control condition differs from the hidden contract"
    interaction = str(truth_condition.get("interaction") or "")
    parameters = truth_condition.get("difficulty_parameters")
    try:
        profile = {
            "object_count": int(parameters["object_count"]),
            "probe_count": int(parameters["probe_count"]),
            "zone_radius": int(parameters["zone_radius"]),
        }
        difficulty = int(truth_condition["difficulty"])
    except (KeyError, TypeError, ValueError):
        return "", None, "shadow-lab difficulty profile is malformed"
    if (
        interaction not in INTERACTION_SURFACES
        or difficulty not in {1, 2, 3, 4, 5}
        or not 3 <= profile["object_count"] <= 6
        or not 2 <= profile["probe_count"] <= 5
        or not 34 <= profile["zone_radius"] <= 64
    ):
        return "", None, "shadow-lab difficulty profile is invalid"
    if difficulty == 4 and profile != {
        "object_count": 5,
        "probe_count": 4,
        "zone_radius": 42,
    }:
        return "", None, "shadow-lab L4 profile does not preserve the original scene"
    if (
        len(objects) != profile["object_count"]
        or len(zones) != profile["probe_count"]
        or any(int(zone.get("radius") or 0) != profile["zone_radius"] for zone in zones)
        or int(ground_truth.get("minimum_probe_zones") or 0) != profile["probe_count"]
    ):
        return "", None, "shadow-lab generated scene differs from the selected profile"
    return interaction, profile, None


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if str(payload.get("mechanic_id") or "") != MECHANIC_ID or str(ground_truth.get("mechanic_id") or "") != MECHANIC_ID:
        return _failure("mechanic mismatch")
    task_id = str(ground_truth.get("task_id") or "")
    if not task_id or str(payload.get("task_id") or "") != task_id or str(public_state.get("task_id") or "") != task_id:
        return _failure("task identity mismatch")
    if not challenge_id or str(payload.get("challenge_id") or "") != challenge_id:
        return _failure("stale challenge")
    if str(public_state.get("challenge_id") or "") != challenge_id or str(public_state.get("mechanic_id") or "") != MECHANIC_ID:
        return _failure("public crime scene does not match hidden state")
    objects = ground_truth.get("objects")
    zones = ground_truth.get("probe_zones")
    lamp_manifest = ground_truth.get("lamp")
    if not isinstance(objects, list) or not 3 <= len(objects) <= 6 or not isinstance(zones, list) or not 2 <= len(zones) <= 5 or not isinstance(lamp_manifest, dict):
        return _failure("hidden analytic scene is malformed")
    if (
        public_state.get("objects") != objects
        or public_state.get("probe_zones") != zones
        or public_state.get("lamp") != lamp_manifest
        or public_state.get("minimum_probe_zones") != ground_truth.get("minimum_probe_zones")
        or public_state.get("minimum_travel") != ground_truth.get("minimum_travel")
    ):
        return _failure("public analytic geometry disagrees with hidden state")
    object_ids = [str(obj.get("id") or "") for obj in objects]
    if "" in object_ids or len(set(object_ids)) != len(objects):
        return _failure("evidence object identities are malformed")
    initial_lamp = _point(lamp_manifest)
    if initial_lamp is None:
        return _failure("initial lamp position is malformed")
    area_radius = float(lamp_manifest.get("area_radius") or 0)
    drag_radius = float(lamp_manifest.get("drag_radius") or 0)
    width = float((ground_truth.get("canvas") or {}).get("width") or 0)
    height = float((ground_truth.get("canvas") or {}).get("height") or 0)
    if width <= 0 or height <= 0 or drag_radius < 20:
        return _failure("hidden light table dimensions are invalid")
    contract = _derive_contract(challenge_id, objects)
    if str(ground_truth.get("forged_object_id") or "") != contract["object_id"] or str(ground_truth.get("forged_law") or "") != contract["law"] or not _close(ground_truth.get("forged_parameter"), contract["parameter"], 1e-9):
        return _failure("hidden forged response does not match challenge derivation")
    interaction, profile, control_error = _control_contract(ground_truth, public_state, objects, zones)
    if control_error:
        return _failure(control_error)
    if ground_truth.get("control_condition") is not None and payload.get("interaction_mode") != interaction:
        return _failure("wrong interaction mode")

    events = payload.get("events")
    if not isinstance(events, list) or not events or len(events) > 520:
        return _failure("light-lab transcript is missing or too long")
    lamp = initial_lamp
    drag_offset = (0.0, 0.0)
    dragging = False
    visited: list[str] = []
    sampled: list[str] = []
    sample_centroids: dict[str, list[tuple[float, float]]] = {object_id: [] for object_id in object_ids}
    travel = 0.0
    move_count = 0
    tagged: str | None = None
    tag_drag: dict[str, Any] | None = None
    proxy_tag_armed = False
    resets = 0
    previous_time = -1.0

    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("seq") != sequence:
            return _failure(f"lab event {sequence} has invalid sequence")
        event_time = _time(event.get("t_ms"))
        if event_time is None or event_time < previous_time:
            return _failure(f"lab event {sequence} has invalid timing")
        previous_time = event_time
        action = str(event.get("type") or "")
        if interaction == "simplified":
            if action == "proxy_probe":
                zone_id = str(event.get("zone_id") or "")
                claimed_lamp = _point(event.get("lamp"))
                if (
                    event.get("input_surface") != INTERACTION_SURFACES["simplified"]["probe"]
                    or dragging
                    or tag_drag is not None
                    or not zone_id
                    or zone_id in sampled
                ):
                    return _failure(f"proxy probe {sequence} uses the wrong interaction input")
                zone = next((candidate for candidate in zones if str(candidate.get("id") or "") == zone_id), None)
                if zone is None or claimed_lamp is None:
                    return _failure(f"proxy probe {sequence} is malformed")
                expected_lamp = (round(float(zone["x"]), 2), round(float(zone["y"]), 2))
                if not _close(claimed_lamp[0], expected_lamp[0]) or not _close(claimed_lamp[1], expected_lamp[1]):
                    return _failure(f"proxy probe {sequence} does not land on its visible zone")
                polygons = _polygons(objects, expected_lamp, initial_lamp, area_radius, contract)
                if not _validate_responses(event.get("responses"), polygons):
                    return _failure(f"proxy probe {sequence} disagrees with analytic projection")
                lamp = expected_lamp
                visited.append(zone_id)
                sampled.append(zone_id)
                for object_id, polygon in polygons:
                    sample_centroids[object_id].append(_centroid(polygon))
                continue
            if action == "proxy_tag_arm":
                if (
                    event.get("input_surface") != INTERACTION_SURFACES["simplified"]["tag_arm"]
                    or proxy_tag_armed
                    or len(sampled) < len(zones)
                ):
                    return _failure(f"proxy evidence tag {sequence} uses the wrong interaction input")
                if event.get("dock") != "evidence_tag":
                    return _failure(f"proxy evidence tag {sequence} did not leave its visible dock")
                proxy_tag_armed = True
                continue
            if action == "proxy_tag_place":
                click = _point(event.get("point"))
                if (
                    event.get("input_surface") != INTERACTION_SURFACES["simplified"]["tag_place"]
                    or not proxy_tag_armed
                    or click is None
                    or not (0 <= click[0] <= width and 0 <= click[1] <= height)
                ):
                    return _failure(f"proxy shadow tag {sequence} uses the wrong interaction input")
                hit = _raycast(_polygons(objects, lamp, initial_lamp, area_radius, contract), click[0], click[1])
                claimed = event.get("object_id")
                if (str(claimed) if claimed is not None else None) != hit:
                    return _failure(f"proxy shadow tag {sequence} violates physical polygon hit testing")
                tagged = hit
                proxy_tag_armed = False
                continue
            if action == "reset":
                if event.get("input_surface") != "reset_button" or proxy_tag_armed:
                    return _failure("proxy scene reset uses the wrong interaction input")
            else:
                return _failure(f"lab event {sequence} uses the wrong interaction input")
        elif action in {"lamp_start", "lamp_move", "probe_sample", "lamp_end"} and event.get("input_surface") not in {None, INTERACTION_SURFACES["full"]["lamp"]}:
            return _failure(f"lamp action {sequence} uses the wrong interaction input")
        elif action in {"tag_start", "tag_move", "tag_end"} and event.get("input_surface") not in {None, INTERACTION_SURFACES["full"]["tag"]}:
            return _failure(f"evidence-tag action {sequence} uses the wrong interaction input")
        elif action == "reset" and event.get("input_surface") not in {None, "reset_button"}:
            return _failure(f"scene reset {sequence} uses the wrong interaction input")
        if action == "lamp_start":
            pointer = _point(event.get("pointer"))
            claimed_lamp = _point(event.get("lamp"))
            if dragging or pointer is None or claimed_lamp is None or math.hypot(pointer[0] - lamp[0], pointer[1] - lamp[1]) > drag_radius:
                return _failure(f"lamp grab {sequence} misses the physical lamp")
            if not _close(claimed_lamp[0], lamp[0]) or not _close(claimed_lamp[1], lamp[1]):
                return _failure(f"lamp grab {sequence} reports stale geometry")
            drag_offset = (pointer[0] - lamp[0], pointer[1] - lamp[1])
            claimed_offset = _point(event.get("drag_offset"))
            if claimed_offset is None or not _close(claimed_offset[0], drag_offset[0]) or not _close(claimed_offset[1], drag_offset[1]):
                return _failure(f"lamp grab {sequence} reports a false drag offset")
            dragging = True
            continue
        if action == "lamp_move":
            pointer = _point(event.get("pointer"))
            claimed_from = _point(event.get("from"))
            claimed_to = _point(event.get("to"))
            if not dragging or pointer is None or claimed_from is None or claimed_to is None:
                return _failure(f"lamp move {sequence} occurs outside a drag")
            if not _close(claimed_from[0], lamp[0]) or not _close(claimed_from[1], lamp[1]):
                return _failure(f"lamp move {sequence} has a stale origin")
            next_lamp = (
                round(_clamp(pointer[0] - drag_offset[0], 20.0, width - 20.0), 2),
                round(_clamp(pointer[1] - drag_offset[1], 20.0, height - 20.0), 2),
            )
            if not _close(claimed_to[0], next_lamp[0]) or not _close(claimed_to[1], next_lamp[1]):
                return _failure(f"lamp move {sequence} reports a false destination")
            travel += math.hypot(next_lamp[0] - lamp[0], next_lamp[1] - lamp[1])
            lamp = next_lamp
            move_count += 1
            zone_id = _zone_at(lamp, zones)
            claimed_zone = event.get("zone_id")
            if (str(claimed_zone) if claimed_zone is not None else None) != zone_id:
                return _failure(f"lamp move {sequence} reports a false probe zone")
            if zone_id and zone_id not in visited:
                visited.append(zone_id)
            continue
        if action == "probe_sample":
            zone_id = str(event.get("zone_id") or "")
            claimed_lamp = _point(event.get("lamp"))
            if dragging is False or not zone_id or zone_id != _zone_at(lamp, zones) or zone_id not in visited or zone_id in sampled:
                return _failure(f"probe sample {sequence} is not bound to a fresh zone entry")
            if claimed_lamp is None or not _close(claimed_lamp[0], lamp[0]) or not _close(claimed_lamp[1], lamp[1]):
                return _failure(f"probe sample {sequence} reports a false lamp position")
            polygons = _polygons(objects, lamp, initial_lamp, area_radius, contract)
            if not _validate_responses(event.get("responses"), polygons):
                return _failure(f"probe sample {sequence} disagrees with analytic projection")
            sampled.append(zone_id)
            for object_id, polygon in polygons:
                sample_centroids[object_id].append(_centroid(polygon))
            continue
        if action == "lamp_end":
            pointer = _point(event.get("pointer"))
            claimed_lamp = _point(event.get("lamp"))
            if not dragging or pointer is None or claimed_lamp is None or not _close(claimed_lamp[0], lamp[0]) or not _close(claimed_lamp[1], lamp[1]):
                return _failure(f"lamp release {sequence} is malformed")
            dragging = False
            continue
        if action == "reset":
            if dragging:
                return _failure("scene reset occurred during a lamp drag")
            lamp = initial_lamp
            drag_offset = (0.0, 0.0)
            visited = []
            sampled = []
            sample_centroids = {object_id: [] for object_id in object_ids}
            travel = 0.0
            move_count = 0
            tagged = None
            tag_drag = None
            proxy_tag_armed = False
            resets += 1
            claimed_lamp = _point(event.get("lamp_after"))
            if claimed_lamp is None or not _close(claimed_lamp[0], lamp[0]) or not _close(claimed_lamp[1], lamp[1]):
                return _failure("scene reset does not restore the manifest lamp")
            continue
        if action == "tag_start":
            if dragging or tag_drag is not None or len(sampled) < int(ground_truth.get("minimum_probe_zones") or 4):
                return _failure(f"evidence tag {sequence} was lifted before causal probing completed")
            if event.get("dock") != "evidence_tag":
                return _failure(f"evidence tag {sequence} did not leave its visible dock")
            tag_drag = {}
            continue
        if action == "tag_move":
            click = _point(event.get("point"))
            if dragging or tag_drag is None or click is None:
                return _failure(f"evidence tag move {sequence} has no physical drag")
            continue
        if action == "tag_end":
            click = _point(event.get("point"))
            if dragging or tag_drag is None or click is None or not (0 <= click[0] <= width and 0 <= click[1] <= height):
                return _failure(f"shadow tag {sequence} has no valid dock-to-polygon drop")
            hit = _raycast(_polygons(objects, lamp, initial_lamp, area_radius, contract), click[0], click[1])
            claimed = event.get("object_id")
            if (str(claimed) if claimed is not None else None) != hit:
                return _failure(f"shadow tag {sequence} violates physical polygon hit testing")
            tagged = hit
            tag_drag = None
            continue
        return _failure(f"lab event {sequence} has invalid action {action!r}")

    if dragging or tag_drag is not None or proxy_tag_armed:
        return _failure("a physical tool remained grabbed at submission")
    expected_state = {
        "lamp_position": _point_dict(lamp),
        "visited_zone_ids": visited,
        "sample_count": len(sampled),
        "tagged_object_id": tagged,
        "reset_count": resets,
        "proxy_tag_armed": False,
    }
    if payload.get("final_state") != expected_state:
        return _failure("claimed lab state does not match transcript replay")
    required_zones = {str(zone["id"]) for zone in zones}
    honest_responsive = all(
        len(points) >= len(zones) and max(math.hypot(point[0] - points[0][0], point[1] - points[0][1]) for point in points[1:]) >= 20
        for object_id, points in sample_centroids.items()
        if object_id != contract["object_id"]
    )
    forged_replayed = len(sample_centroids[contract["object_id"]]) >= len(zones)
    passed = (
        set(visited) == required_zones
        and set(sampled) == required_zones
        and len(sampled) >= len(zones)
        and honest_responsive
        and forged_replayed
        and tagged == contract["object_id"]
    )
    return {
        "graded": True,
        "passed": passed,
        "score": 100 if passed else 0,
        "feedback": f"replayed {move_count} lamp updates across {len(sampled)}/{len(zones)} analytic probes; path {travel:.1f}; tagged response {tagged or 'none'}; resets {resets}",
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {
        "forged_object_id": ground_truth.get("forged_object_id"),
        "forged_law": ground_truth.get("forged_law"),
        "forged_parameter": ground_truth.get("forged_parameter"),
        "solution": ground_truth.get("solution") or {},
        "answers": [],
    }
