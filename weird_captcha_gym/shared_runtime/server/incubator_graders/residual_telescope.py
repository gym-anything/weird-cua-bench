from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "residual_telescope"
ALL_PARAMETER_IDS = (
    "disc_brightness", "core_brightness", "disc_extent", "bar_brightness",
    "bar_boxiness", "core_concentration", "arms_brightness", "arms_spread",
    "disc_falloff", "arms_falloff",
)


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _point(value: object) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    try:
        point = [float(value[0]), float(value[1])]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(item) for item in point):
        return None
    return point


def _distance(first: list[float], second: list[float]) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _angle_distance(first: float, second: float) -> float:
    difference = abs((first - second) % math.pi)
    return min(difference, math.pi - difference)


def _segment_distance(point: list[float], first: list[float], second: list[float]) -> float:
    vx, vy = second[0] - first[0], second[1] - first[1]
    length_sq = vx * vx + vy * vy
    amount = 0.0 if length_sq <= 0 else max(0.0, min(1.0, ((point[0] - first[0]) * vx + (point[1] - first[1]) * vy) / length_sq))
    return _distance(point, [first[0] + amount * vx, first[1] + amount * vy])


def _polyline_distance(point: list[float], polyline: list[list[float]]) -> float:
    return min(_segment_distance(point, first, second) for first, second in zip(polyline, polyline[1:]))


def _derive(component: str, points: list[list[float]]) -> dict[str, Any] | list[list[float]] | None:
    if component.startswith("arm_"):
        return points if len(points) >= 4 else None
    if len(points) != 2 or _distance(points[0], points[1]) < 2:
        return None
    first, second = points
    angle = math.atan2(second[1] - first[1], second[0] - first[0])
    if component in {"disc", "core"}:
        return {"center": first, "radius": _distance(first, second), "angle": angle}
    if component == "bar":
        return {
            "center": [(first[0] + second[0]) / 2, (first[1] + second[1]) / 2],
            "length": _distance(first, second), "width": 2.75, "angle": angle,
        }
    return None


def _segment_distance_xy(x: float, y: float, first: list[float], second: list[float]) -> float:
    return _segment_distance([x, y], first, second)


def _render(geometry: dict[str, Any], values: dict[str, int], width: int, height: int) -> list[list[float]]:
    pixels: list[list[float]] = []
    disc = geometry.get("disc")
    core = geometry.get("core")
    bar = geometry.get("bar")
    arms = geometry.get("arms") or []
    disc_center = (disc or {}).get("center") or [width / 2, height / 2]
    disc_radius = max(1.0, float((disc or {}).get("radius") or 18))
    for row in range(height):
        line: list[float] = []
        for column in range(width):
            x, y = column + 0.5, row + 0.5
            light = 0.016
            if disc:
                angle = float(disc["angle"])
                dx, dy = x - disc["center"][0], y - disc["center"][1]
                xr = math.cos(angle) * dx + math.sin(angle) * dy
                yr = -math.sin(angle) * dx + math.cos(angle) * dy
                extent = 0.76 + values["disc_extent"] * 0.052
                falloff = 1.48 - values["disc_falloff"] * 0.055
                radius = max(1.0, float(disc["radius"]) * extent)
                elliptical = math.sqrt(xr * xr + (yr / 0.61) ** 2) / radius
                light += (0.11 + values["disc_brightness"] * 0.039) * math.exp(-elliptical * 2.05 * falloff)
            if core:
                angle = float(core["angle"])
                dx, dy = x - core["center"][0], y - core["center"][1]
                xr = math.cos(angle) * dx + math.sin(angle) * dy
                yr = -math.sin(angle) * dx + math.cos(angle) * dy
                elliptical = math.sqrt(xr * xr + (yr / 0.78) ** 2) / max(1.0, float(core["radius"]))
                concentration = 1.18 + values["core_concentration"] * 0.18
                light += (0.13 + values["core_brightness"] * 0.044) * math.exp(-(elliptical ** concentration) * 1.8)
            if bar:
                angle = float(bar["angle"])
                dx, dy = x - bar["center"][0], y - bar["center"][1]
                xr = abs(math.cos(angle) * dx + math.sin(angle) * dy) / max(1.0, float(bar["length"]) / 2)
                yr = abs(-math.sin(angle) * dx + math.cos(angle) * dy) / max(1.0, float(bar["width"]))
                power = 1.45 + values["bar_boxiness"] * 0.22
                norm = (xr ** power + yr ** power) ** (1 / power)
                light += (0.08 + values["bar_brightness"] * 0.034) * math.exp(-(norm ** 3.2) * 2.2)
            if arms:
                spread = 1.05 + values["arms_spread"] * 0.25
                radial = math.hypot(x - disc_center[0], y - disc_center[1]) / disc_radius
                radial_falloff = 0.58 + values["arms_falloff"] * 0.065
                for points in arms:
                    distance = min(_segment_distance_xy(x, y, first, second) for first, second in zip(points, points[1:]))
                    light += (0.045 + values["arms_brightness"] * 0.018) * math.exp(-(distance ** 2) / (2 * spread ** 2)) * math.exp(-radial * radial_falloff)
            line.append(max(0.0, min(1.0, light)))
        pixels.append(line)
    return pixels


def _geometry_matches(actual: dict[str, Any], target: dict[str, Any], tolerance: float, angle_tolerance: float) -> tuple[bool, str]:
    for name in ("disc", "core", "bar"):
        expected = target.get(name)
        if expected is None:
            continue
        observed = actual.get(name)
        if not isinstance(observed, dict):
            return False, f"{name} was not constructed"
        if _distance(observed["center"], expected["center"]) > tolerance:
            return False, f"{name} center falls outside tolerance"
        size_key = "length" if name == "bar" else "radius"
        if abs(float(observed[size_key]) - float(expected[size_key])) > tolerance:
            return False, f"{name} size falls outside tolerance"
        if _angle_distance(float(observed["angle"]), float(expected["angle"])) > angle_tolerance:
            return False, f"{name} orientation falls outside tolerance"
    expected_arms = target.get("arms") or []
    observed_arms = actual.get("arms") or []
    if len(observed_arms) != len(expected_arms):
        return False, "arm count does not match the generated specimen"
    for index, (observed, expected) in enumerate(zip(observed_arms, expected_arms), start=1):
        forward = max(_polyline_distance(point, observed) for point in expected)
        reverse = max(_polyline_distance(point, expected) for point in observed)
        if max(forward, reverse) > tolerance:
            return False, f"arm {index} leaves the luminous trace"
    return True, "geometry matches"


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if payload.get("mechanic_id") != MECHANIC_ID or ground_truth.get("mechanic_id") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    if payload.get("challenge_id") != ground_truth.get("challenge_id"):
        return _fail("stale challenge")
    condition = ground_truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "full")
    if payload.get("interaction") != interaction:
        return _fail("interaction transcript does not match the assigned surface")
    if public_state.get("control_condition") != ground_truth.get("control_condition"):
        return _fail("public/private control contract mismatch")
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        return _fail("no reconstruction transcript")
    if len(events) > int(ground_truth.get("move_budget") or 0):
        return _fail("reconstruction exceeded its move budget")

    shape_sources = {"full": "direct_draw", "simplified": "proxy_points"}
    parameter_sources = {"full": "direct_slider", "simplified": "proxy_nudge"}
    sequence = list(ground_truth.get("component_sequence") or [])
    geometry: dict[str, Any] = {"arms": []}
    values = {parameter_id: 5 for parameter_id in ALL_PARAMETER_IDS}
    active_parameters = {str(item["id"]) for item in ground_truth.get("parameter_specs") or []}
    seen_parameters: set[str] = set()
    shape_cursor = 0
    for event_index, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != event_index:
            return _fail("event sequence is malformed")
        kind = str(event.get("kind") or "")
        if kind == "shape_commit":
            component = str(event.get("component") or "")
            initial_construction = shape_cursor < len(sequence) and component == sequence[shape_cursor]
            redraw = component in sequence[:shape_cursor]
            if not initial_construction and not redraw:
                return _fail("components were not constructed in the unlocked order")
            if event.get("input_source") != shape_sources[interaction]:
                return _fail("shape transcript came from the wrong interaction surface")
            raw_points = event.get("points")
            if not isinstance(raw_points, list) or len(raw_points) > 240:
                return _fail("component geometry is malformed")
            points = [_point(item) for item in raw_points]
            if any(point is None for point in points):
                return _fail("component geometry contains an invalid point")
            derived = _derive(component, [point for point in points if point is not None])
            if derived is None:
                return _fail("component geometry is incomplete")
            if component.startswith("arm_"):
                arm_index = int(component.split("_")[1]) - 1
                if not redraw:
                    geometry["arms"].append(derived)
                else:
                    geometry["arms"][arm_index] = derived
            else:
                geometry[component] = derived
            if initial_construction:
                shape_cursor += 1
        elif kind == "parameter_set":
            if shape_cursor != len(sequence):
                return _fail("a parameter was tuned before all components were constructed")
            if event.get("input_source") != parameter_sources[interaction]:
                return _fail("parameter transcript came from the wrong interaction surface")
            parameter_id = str(event.get("parameter_id") or "")
            if parameter_id not in active_parameters:
                return _fail("unknown parameter in reconstruction transcript")
            value = event.get("value")
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10:
                return _fail("parameter value is outside its calibrated rail")
            if abs(value - values[parameter_id]) != 1:
                return _fail("each optical event must move exactly one calibrated step")
            values[parameter_id] = value
            seen_parameters.add(parameter_id)
        else:
            return _fail("unknown reconstruction event")
    if shape_cursor != len(sequence):
        return _fail("not every generated component was constructed")
    if seen_parameters != active_parameters:
        return _fail("not every unlocked parameter was deliberately tuned")

    controls = ground_truth.get("parameters") or {}
    geometry_ok, message = _geometry_matches(
        geometry,
        ground_truth.get("target_geometry") or {},
        float(controls.get("geometry_tolerance") or ground_truth.get("geometry_tolerance") or 0),
        math.radians(float(controls.get("angle_tolerance_deg") or ground_truth.get("angle_tolerance_deg") or 0)),
    )
    if not geometry_ok:
        return _fail(message)
    parameter_tolerance = int(controls.get("parameter_tolerance") or 0)
    target_values = ground_truth.get("target_values") or {}
    if any(abs(values[parameter_id] - int(target_values[parameter_id])) > parameter_tolerance for parameter_id in active_parameters):
        return _fail("one or more coupled optical parameters remain outside tolerance")
    target_pixels = public_state.get("target_pixels") or []
    image = ground_truth.get("image") or {}
    rendered = _render(geometry, values, int(image.get("width") or 0), int(image.get("height") or 0))
    if not target_pixels or len(target_pixels) != len(rendered):
        return _fail("target specimen raster is malformed")
    errors = [
        (float(observed) - float(expected)) ** 2
        for observed_row, expected_row in zip(rendered, target_pixels)
        for observed, expected in zip(observed_row, expected_row)
    ]
    rms = math.sqrt(sum(errors) / max(1, len(errors)))
    threshold = float(ground_truth.get("residual_threshold") or 0)
    if rms > threshold:
        return _fail("signed residual remains above the acceptance threshold")
    if payload.get("completed") is not True:
        return _fail("client did not finish the reconstruction")
    return {
        "graded": True,
        "passed": True,
        "score": 100,
        "feedback": f"independent replay verified {len(sequence)} components, {len(active_parameters)} parameters, and residual RMS {rms:.5f}; passed",
    }
