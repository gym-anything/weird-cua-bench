from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "surveyors_toybox"
FIELDS = {"cx", "cy", "cz", "hx", "hy", "hz", "yaw"}
VIEWS = ("overhead", "front", "side")


def _finite(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _box_from_annotation(annotation: dict[str, Any]) -> tuple[list[float], list[float], float]:
    center = [float(value) for value in annotation["center"]]
    half = [float(value) for value in annotation["half"]]
    return center, half, float(annotation["yaw"])


def _corners(center: list[float], half: list[float], yaw: float) -> list[tuple[float, float]]:
    angle = math.radians(yaw)
    cosine, sine = math.cos(angle), math.sin(angle)
    result = []
    for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        lx, lz = sx * half[0], sz * half[2]
        result.append((center[0] + lx * cosine - lz * sine, center[2] + lx * sine + lz * cosine))
    return result


def _cross(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _clip(subject: list[tuple[float, float]], edge_a: tuple[float, float], edge_b: tuple[float, float]) -> list[tuple[float, float]]:
    if not subject:
        return []
    result: list[tuple[float, float]] = []
    previous = subject[-1]
    previous_inside = _cross(edge_a, edge_b, previous) >= -1e-9
    for current in subject:
        current_inside = _cross(edge_a, edge_b, current) >= -1e-9
        if current_inside != previous_inside:
            dx, dy = current[0] - previous[0], current[1] - previous[1]
            ex, ey = edge_b[0] - edge_a[0], edge_b[1] - edge_a[1]
            denominator = dx * ey - dy * ex
            if abs(denominator) > 1e-12:
                t = ((edge_a[0] - previous[0]) * ey - (edge_a[1] - previous[1]) * ex) / denominator
                result.append((previous[0] + t * dx, previous[1] + t * dy))
        if current_inside:
            result.append(current)
        previous, previous_inside = current, current_inside
    return result


def _area(polygon: list[tuple[float, float]]) -> float:
    return abs(sum(polygon[i][0] * polygon[(i + 1) % len(polygon)][1] - polygon[(i + 1) % len(polygon)][0] * polygon[i][1] for i in range(len(polygon))) / 2) if polygon else 0.0


def _box_iou(first: dict[str, Any], second: dict[str, Any]) -> float:
    center_a, half_a, yaw_a = _box_from_annotation(first)
    center_b, half_b, yaw_b = _box_from_annotation(second)
    polygon = _corners(center_a, half_a, yaw_a)
    clip_polygon = _corners(center_b, half_b, yaw_b)
    for index in range(len(clip_polygon)):
        polygon = _clip(polygon, clip_polygon[index], clip_polygon[(index + 1) % len(clip_polygon)])
    y_overlap = max(0.0, min(center_a[1] + half_a[1], center_b[1] + half_b[1]) - max(center_a[1] - half_a[1], center_b[1] - half_b[1]))
    intersection = _area(polygon) * y_overlap
    volume_a = 8 * half_a[0] * half_a[1] * half_a[2]
    volume_b = 8 * half_b[0] * half_b[1] * half_b[2]
    union = volume_a + volume_b - intersection
    return intersection / union if union > 1e-9 else 0.0


def _angle_delta(first: float, second: float) -> float:
    return abs((first - second + 180.0) % 360.0 - 180.0)


def _normal_annotation(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "center": [round(float(v), 4) for v in value["center"]],
        "half": [round(float(v), 4) for v in value["half"]],
        "yaw": round(float(value["yaw"]), 4),
    }


def _normal_links(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if payload.get("mechanic_id") != MECHANIC_ID or ground_truth.get("mechanic_id") != MECHANIC_ID:
        return {"graded": True, "passed": False, "feedback": "mechanic mismatch"}
    challenge = str(ground_truth.get("challenge_id") or "")
    if not challenge or payload.get("challenge_id") != challenge or public_state.get("challenge_id") != challenge:
        return {"graded": True, "passed": False, "feedback": "stale challenge"}
    if payload.get("task_id") != ground_truth.get("task_id"):
        return {"graded": True, "passed": False, "feedback": "task identity mismatch"}
    for field in ("task_id", "targets", "point_cloud", "views", "camera_frames", "initial_annotations", "world", "requirements"):
        if public_state.get(field) != ground_truth.get(field):
            return {"graded": True, "passed": False, "feedback": f"public/private survey {field} contract skew"}
    if public_state.get("control_condition") != ground_truth.get("control_condition"):
        return {"graded": True, "passed": False, "feedback": "public interaction condition differs from survey contract"}
    interaction = str(ground_truth.get("interaction_mode") or "full")
    if interaction not in {"simplified", "full"} or payload.get("interaction_mode") != interaction:
        return {"graded": True, "passed": False, "feedback": "survey transcript declares the wrong interaction mode"}
    expected_adjust_source = "direct_drag" if interaction == "full" else "proxy_controls"
    expected_link_source = "direct_mark" if interaction == "full" else "proxy_controls"
    events = payload.get("events")
    requirements = ground_truth["requirements"]
    if not isinstance(events, list) or not (1 <= len(events) <= int(requirements["max_events"])):
        return {"graded": True, "passed": False, "feedback": "survey transcript missing or outside limits"}

    annotations = {key: _normal_annotation(value) for key, value in ground_truth["initial_annotations"].items()}
    links: dict[str, str] = {}
    target_ids = set(str(value) for value in ground_truth["target_ids"])
    frame_count = int(requirements["frame_count"])
    valid_marks = {
        (frame, view, str(mark["id"]))
        for frame_info in ground_truth["camera_frames"]
        for frame in [int(frame_info["frame_index"])]
        for view in VIEWS
        for mark in frame_info["views"][view]["marks"]
    }
    for sequence, event in enumerate(events, 1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return {"graded": True, "passed": False, "feedback": f"event {sequence} sequence mismatch"}
        kind = str(event.get("kind") or "")
        if kind == "adjust_box":
            if event.get("input_source") != expected_adjust_source:
                return {"graded": True, "passed": False, "feedback": f"event {sequence} uses the wrong interaction input"}
            target_id, field = str(event.get("target_id") or ""), str(event.get("field") or "")
            delta = event.get("delta")
            if target_id not in target_ids or field not in FIELDS or not _finite(delta):
                return {"graded": True, "passed": False, "feedback": "invalid cuboid adjustment"}
            delta_value = float(delta)
            if (interaction == "simplified" and abs(delta_value) > (5.2 if field == "yaw" else 0.101)) or (interaction == "full" and abs(delta_value) > (50 if field == "yaw" else 1.7)):
                return {"graded": True, "passed": False, "feedback": "cuboid drag exceeded one visible manipulation"}
            item = annotations[target_id]
            if field == "cx": item["center"][0] += delta_value
            elif field == "cy": item["center"][1] += delta_value
            elif field == "cz": item["center"][2] += delta_value
            elif field == "hx": item["half"][0] = max(0.18, item["half"][0] + delta_value)
            elif field == "hy": item["half"][1] = max(0.18, item["half"][1] + delta_value)
            elif field == "hz": item["half"][2] = max(0.18, item["half"][2] + delta_value)
            elif field == "yaw": item["yaw"] += delta_value
            annotations[target_id] = _normal_annotation(item)
        elif kind == "frame_select":
            try:
                if not 0 <= int(event.get("frame")) < frame_count:
                    raise ValueError
            except (TypeError, ValueError):
                return {"graded": True, "passed": False, "feedback": "invalid synchronized frame"}
        elif kind == "orbit":
            if not _finite(event.get("delta", 0)) or abs(float(event.get("delta", 0))) > 360:
                return {"graded": True, "passed": False, "feedback": "invalid point-cloud orbit"}
        elif kind == "pan":
            if event.get("input_source") != expected_adjust_source:
                return {"graded": True, "passed": False, "feedback": f"event {sequence} uses the wrong view input"}
            if not _finite(event.get("delta_x", 0)) or not _finite(event.get("delta_y", 0)):
                return {"graded": True, "passed": False, "feedback": "invalid point-cloud pan"}
            if abs(float(event.get("delta_x", 0))) > 180 or abs(float(event.get("delta_y", 0))) > 140:
                return {"graded": True, "passed": False, "feedback": "point-cloud pan exceeded one visible manipulation"}
        elif kind == "zoom":
            if event.get("input_source") != expected_adjust_source or not _finite(event.get("delta", 0)):
                return {"graded": True, "passed": False, "feedback": "invalid point-cloud zoom"}
            if abs(float(event.get("delta", 0))) > 0.2:
                return {"graded": True, "passed": False, "feedback": "point-cloud zoom exceeded one visible manipulation"}
        elif kind == "link":
            if event.get("input_source") != expected_link_source:
                return {"graded": True, "passed": False, "feedback": f"event {sequence} uses the wrong link input"}
            target_id, view, mark_id = str(event.get("target_id") or ""), str(event.get("view") or ""), str(event.get("mark_id") or "")
            try:
                frame = int(event.get("frame"))
            except (TypeError, ValueError):
                frame = -1
            if target_id not in target_ids or view not in VIEWS or not 0 <= frame < frame_count or (frame, view, mark_id) not in valid_marks:
                return {"graded": True, "passed": False, "feedback": "link points to a mark outside the visible frame"}
            links[f"{frame}:{view}:{target_id}"] = mark_id
        else:
            return {"graded": True, "passed": False, "feedback": f"unknown survey event {kind}"}

    submitted_annotations = payload.get("annotations")
    if not isinstance(submitted_annotations, dict) or {str(k): _normal_annotation(v) for k, v in submitted_annotations.items() if isinstance(v, dict)} != annotations:
        return {"graded": True, "passed": False, "feedback": "submitted cuboids disagree with replay"}
    if _normal_links(payload.get("links")) != links:
        return {"graded": True, "passed": False, "feedback": "submitted image links disagree with replay"}
    fit_count = 0
    fit_details: dict[str, Any] = {}
    tolerance = float(requirements["fit_tolerance"])
    yaw_tolerance = float(requirements["yaw_tolerance"])
    for target_id in target_ids:
        actual, expected = annotations[target_id], ground_truth["target_boxes"][target_id]
        center_error = math.dist([float(v) for v in actual["center"]], [float(v) for v in expected["center"]])
        extent_error = max(abs(float(a) - float(b)) for a, b in zip(actual["half"], expected["half"]))
        yaw_error = _angle_delta(float(actual["yaw"]), float(expected["yaw"]))
        iou = _box_iou(actual, {"center": expected["center"], "half": expected["half"], "yaw": expected["yaw"]})
        fit = center_error <= tolerance and extent_error <= tolerance and yaw_error <= yaw_tolerance and iou >= 0.62
        fit_count += int(fit)
        fit_details[target_id] = {"center_error": round(center_error, 3), "extent_error": round(extent_error, 3), "yaw_error": round(yaw_error, 2), "iou3d": round(iou, 3)}
    expected_links = {str(key): str(value) for key, value in ground_truth["expected_links"].items()}
    link_count = sum(links.get(key) == value for key, value in expected_links.items())
    passed = fit_count == len(target_ids) and links == expected_links
    return {
        "graded": True, "passed": passed, "score": 100 if passed else 0,
        "feedback": f"cuboids {fit_count}/{len(target_ids)}; links {link_count}/{len(expected_links)}; 3D IoU and cross-view identity replay",
        "fit_details": fit_details,
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {"target_boxes": ground_truth.get("target_boxes") or {}, "expected_links": ground_truth.get("expected_links") or {}}
