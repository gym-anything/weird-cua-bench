"""Independent server replay for Loopmaker's Trial."""

from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "loopmakers_trial"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _close(first: Any, second: Any, tolerance: float = 0.025) -> bool:
    left, right = _number(first), _number(second)
    return left is not None and right is not None and abs(left - right) <= tolerance


def _copy_points(points: Any) -> list[dict[str, Any]] | None:
    if not isinstance(points, list) or not points:
        return None
    copied: list[dict[str, Any]] = []
    for item in points:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            return None
        x, y = _number(item.get("x")), _number(item.get("y"))
        if x is None or y is None:
            return None
        copied.append({"id": item["id"], "x": x, "y": y})
    return copied


def _sample_path(points: list[dict[str, Any]], sample_steps: int) -> list[dict[str, float]]:
    path: list[dict[str, float]] = []
    for index in range(len(points) - 1):
        first, second = points[index], points[index + 1]
        for step in range(sample_steps):
            ratio = step / sample_steps
            path.append({
                "x": float(first["x"]) + (float(second["x"]) - float(first["x"])) * ratio,
                "y": float(first["y"]) + (float(second["y"]) - float(first["y"])) * ratio,
            })
    path.append({"x": float(points[-1]["x"]), "y": float(points[-1]["y"])})
    return path


def _radius(path: list[dict[str, float]], index: int, minimum: float) -> float:
    if index <= 0 or index >= len(path) - 1:
        return 1000000.0
    first, middle, last = path[index - 1], path[index], path[index + 1]
    a = math.dist((first["x"], first["y"]), (middle["x"], middle["y"]))
    b = math.dist((middle["x"], middle["y"]), (last["x"], last["y"]))
    c = math.dist((first["x"], first["y"]), (last["x"], last["y"]))
    cross = abs((middle["x"] - first["x"]) * (last["y"] - first["y"]) - (middle["y"] - first["y"]) * (last["x"] - first["x"]))
    if cross < 1e-6:
        return 1000000.0
    return max(minimum, a * b * c / (2.0 * cross))


def _replay(points: list[dict[str, Any]], features: list[dict[str, Any]], physics: dict[str, Any]) -> dict[str, Any]:
    sample_steps = int(physics["sample_steps"])
    path = _sample_path(points, sample_steps)
    distances = [0.0]
    for first, second in zip(path, path[1:]):
        distances.append(distances[-1] + math.dist((first["x"], first["y"]), (second["x"], second["y"])))
    speeds: list[float] = []
    forces: list[float] = []
    start_y = float(points[0]["y"])
    for index, item in enumerate(path):
        height_gain = (start_y - float(item["y"])) / float(physics["pixels_per_meter"])
        energy = float(physics["initial_speed_mps"]) ** 2 + 2 * float(physics["gravity"]) * height_gain - float(physics["friction_per_pixel"]) * distances[index]
        speed = math.sqrt(max(0.0, energy))
        if index == 0:
            tangent_x = path[1]["x"] - path[0]["x"]
            tangent_y = path[1]["y"] - path[0]["y"]
        else:
            tangent_x = item["x"] - path[index - 1]["x"]
            tangent_y = item["y"] - path[index - 1]["y"]
        radius = _radius(path, index, float(physics["minimum_radius_px"]))
        centripetal = 0.0 if radius > 900000 else speed * speed / (float(physics["gravity"]) * (radius / float(physics["pixels_per_meter"])))
        speeds.append(speed)
        forces.append(centripetal + abs(math.cos(math.atan2(tangent_y, tangent_x))))
    metrics: list[dict[str, Any]] = []
    for feature in features:
        index = min(len(path) - 1, int(feature["point_index"]) * sample_steps)
        constraints = feature["constraints"]
        speed = speeds[index]
        force = forces[index]
        contact = force >= float(constraints["min_force_g"])
        reasons: list[str] = []
        if speed < float(constraints["min_speed"]):
            reasons.append("speed below thrill minimum")
        if speed > float(constraints["max_speed"]):
            reasons.append("speed above envelope")
        if force < float(constraints["min_force_g"]):
            reasons.append("normal force below contact minimum")
        if force > float(constraints["max_force_g"]):
            reasons.append("normal force above envelope")
        if constraints.get("require_contact") and not contact:
            reasons.append("rider lost contact")
        metrics.append({
            "id": feature["id"],
            "label": feature["label"],
            "point_index": feature["point_index"],
            "speed_mps": round(speed, 4),
            "force_g": round(force, 4),
            "contact": contact,
            "ok": not reasons,
            "reasons": reasons,
        })
    stalled_at = next((index for index, speed in enumerate(speeds) if speed < float(physics["stall_speed_mps"])), None)
    completed = stalled_at is None and bool(path) and speeds[-1] >= float(physics["stall_speed_mps"])
    return {
        "completed": completed,
        "passed": completed and all(item["ok"] for item in metrics),
        "stalled": stalled_at is not None,
        "stalled_at_sample": stalled_at,
        "distance_px": round(distances[-1], 4),
        "duration_ms": int(float(physics["run_duration_ms"])),
        "feature_metrics": metrics,
        "end_speed_mps": round(speeds[-1], 4) if speeds else 0.0,
        "sample_count": len(path),
    }


def _same_summary(reported: Any, actual: dict[str, Any]) -> bool:
    if not isinstance(reported, dict):
        return False
    for key in ("completed", "passed", "stalled", "stalled_at_sample", "sample_count"):
        if reported.get(key) != actual.get(key):
            return False
    for key in ("distance_px", "end_speed_mps"):
        if not _close(reported.get(key), actual.get(key), 0.03):
            return False
    reported_metrics = reported.get("feature_metrics")
    actual_metrics = actual.get("feature_metrics") or []
    if not isinstance(reported_metrics, list) or len(reported_metrics) != len(actual_metrics):
        return False
    for given, expected in zip(reported_metrics, actual_metrics):
        if not isinstance(given, dict):
            return False
        for key in ("id", "point_index", "contact", "ok"):
            if given.get(key) != expected.get(key):
                return False
        if not _close(given.get("speed_mps"), expected.get("speed_mps"), 0.03) or not _close(given.get("force_g"), expected.get("force_g"), 0.03):
            return False
    return True


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    if payload.get("mechanic_id") != MECHANIC_ID or truth.get("mechanic_id") != MECHANIC_ID or public.get("mechanic_id") != MECHANIC_ID:
        return _fail("mechanic identity mismatch")
    if payload.get("task_id") != truth.get("task_id") or payload.get("challenge_id") != truth.get("challenge_id") or public.get("challenge_id") != truth.get("challenge_id"):
        return _fail("stale trial or challenge identity")
    condition = truth.get("control_condition")
    if condition is not None and public.get("control_condition") != condition:
        return _fail("public interaction condition differs from trial contract")
    interaction = str((condition or {}).get("interaction") or "full")
    expected_source = {"simplified": "proxy_controls", "full": "point_drag"}.get(interaction)
    if expected_source is None:
        return _fail("invalid interaction contract")
    points = _copy_points(public.get("points"))
    features = public.get("features")
    physics = public.get("physics")
    if points is None or not isinstance(features, list) or not isinstance(physics, dict):
        return _fail("public route state is malformed")
    point_by_id = {item["id"]: item for item in points}
    events = payload.get("events")
    if not isinstance(events, list) or not events or len(events) > 5000:
        return _fail("route transcript is empty or malformed")
    adjustment_count = 0
    successful_runs: list[dict[str, Any]] = []
    for sequence, event in enumerate(events, 1):
        if not isinstance(event, dict) or event.get("seq") != sequence:
            return _fail(f"event {sequence} sequence invalid")
        kind = event.get("type")
        if kind == "adjust":
            adjustment_count += 1
            if event.get("input_source") != expected_source or event.get("action") not in {"raise", "lower", "widen", "tighten", "drag"}:
                return _fail("route edit used the wrong interaction input")
            point = point_by_id.get(event.get("point_id"))
            if point is None:
                return _fail("route edit names an unknown control point")
            if point is points[0] or point is points[-1]:
                return _fail("launch and brake control points are locked")
            before = event.get("before") or {}
            after = event.get("after") or {}
            if not isinstance(before, dict) or not isinstance(after, dict):
                return _fail("route edit coordinates are malformed")
            if not _close(before.get("x"), point["x"]) or not _close(before.get("y"), point["y"]):
                return _fail("route edit starts from stale geometry")
            new_x, new_y = _number(after.get("x")), _number(after.get("y"))
            if new_x is None or new_y is None or not (18 <= new_x <= 882 and 14 <= new_y <= 444):
                return _fail("route edit leaves the visible design board")
            dx, dy = new_x - point["x"], new_y - point["y"]
            if interaction == "simplified":
                params = ((condition or {}).get("difficulty_parameters") or {})
                height_step, radius_step = float(params.get("height_step", 10)), float(params.get("radius_step", 15))
                expected_delta = {
                    "raise": (0.0, -height_step),
                    "lower": (0.0, height_step),
                    "widen": (radius_step, 0.0),
                    "tighten": (-radius_step, 0.0),
                }.get(event.get("action"))
                if expected_delta is None:
                    return _fail("proxy edit moved a point by an impossible increment")
                expected_x = max(18, min(882, point["x"] + expected_delta[0]))
                expected_y = max(14, min(444, point["y"] + expected_delta[1]))
                if not _close(new_x, expected_x, 0.03) or not _close(new_y, expected_y, 0.03):
                    return _fail("proxy edit moved a point by an impossible increment")
            elif event.get("action") != "drag":
                return _fail("direct route edit is not a point drag")
            point["x"], point["y"] = new_x, new_y
            successful_runs.clear()
        elif kind == "test_run":
            if event.get("input_source") != "test_button" or not isinstance(event.get("points"), list):
                return _fail("test run is not bound to the visible test control")
            reported_points = _copy_points(event.get("points"))
            if reported_points is None or len(reported_points) != len(points) or any(
                left["id"] != right["id"] or not _close(left["x"], right["x"]) or not _close(left["y"], right["y"])
                for left, right in zip(reported_points, points)
            ):
                return _fail("test run reports geometry different from the edited route")
            actual = _replay(points, features, physics)
            if not _same_summary(event.get("summary"), actual):
                return _fail("reported rider telemetry disagrees with independent replay")
            successful_runs.append(actual)
        else:
            return _fail(f"unknown route event {kind!r}")
    if adjustment_count < 1:
        return _fail("the route must be edited and tested before certification")
    if payload.get("interaction_mode") not in {None, interaction}:
        return _fail("payload interaction mode disagrees with the trial contract")
    if payload.get("completed") is not True or not successful_runs:
        return _fail("no completed physical test run was submitted")
    final = successful_runs[-1]
    if not final["passed"]:
        failing = [item["label"] for item in final["feature_metrics"] if not item["ok"]]
        return {"graded": True, "passed": False, "feedback": f"rider failed at {', '.join(failing) or 'the route'}"}
    return {
        "graded": True,
        "passed": True,
        "feedback": f"independent replay completed {len(features)} marked features with contact and force limits",
        "replay": final,
        "edit_count": adjustment_count,
    }


__all__ = ["MECHANIC_ID", "grade"]
