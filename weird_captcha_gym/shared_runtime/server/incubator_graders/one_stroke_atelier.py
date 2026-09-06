from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "one_stroke_atelier"
KINDS = ("stroke_start", "gate_cross", "motif_sample", "stroke_end")


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


def _segment_distance(point: list[float], first: list[float], second: list[float]) -> float:
    vx, vy = second[0] - first[0], second[1] - first[1]
    length_sq = vx * vx + vy * vy
    amount = 0.0 if length_sq <= 0 else max(0.0, min(1.0, ((point[0] - first[0]) * vx + (point[1] - first[1]) * vy) / length_sq))
    return _distance(point, [first[0] + vx * amount, first[1] + vy * amount])


def _polyline_distance(point: list[float], polyline: list[list[float]]) -> float:
    return min(_segment_distance(point, first, second) for first, second in zip(polyline, polyline[1:]))


def _key(phase: int, prefix: list[str]) -> str:
    return f"{phase}|{'/'.join(prefix)}"


def _hit_half_length(gate: dict[str, Any]) -> float:
    expected = float(gate["half_length"]) + float(gate["tolerance"])
    actual = float(gate.get("hit_half_length", expected))
    return actual if math.isclose(actual, expected, abs_tol=1e-9) else -1.0


def _crossing_amount(before: list[float], after: list[float], gate: dict[str, Any]) -> float | None:
    x, y = (float(item) for item in gate["center"])
    half = _hit_half_length(gate)
    if half < 0:
        return None
    direction = str(gate["direction"])
    if gate["orientation"] == "vertical":
        delta = after[0] - before[0]
        if (direction == "right" and delta <= 0) or (direction == "left" and delta >= 0) or delta == 0:
            return None
        if not (min(before[0], after[0]) <= x <= max(before[0], after[0])):
            return None
        amount = (x - before[0]) / delta
        intersection = before[1] + amount * (after[1] - before[1])
        return amount if abs(intersection - y) <= half else None
    delta = after[1] - before[1]
    if (direction == "down" and delta <= 0) or (direction == "up" and delta >= 0) or delta == 0:
        return None
    if not (min(before[1], after[1]) <= y <= max(before[1], after[1])):
        return None
    amount = (y - before[1]) / delta
    intersection = before[0] + amount * (after[0] - before[0])
    return amount if abs(intersection - x) <= half else None


def _crosses(before: list[float], after: list[float], gate: dict[str, Any]) -> bool:
    return _crossing_amount(before, after, gate) is not None


def _segment_intersects_locked_bar(first: list[float], second: list[float], gate: dict[str, Any]) -> bool:
    """Return whether a path segment touches the exact rendered 18px bar body."""
    x, y = (float(item) for item in gate["center"])
    along = _hit_half_length(gate)
    if along < 0:
        return True
    half_x, half_y = (9.0, along) if gate["orientation"] == "vertical" else (along, 9.0)
    left, right, top, bottom = x - half_x, x + half_x, y - half_y, y + half_y
    dx, dy = second[0] - first[0], second[1] - first[1]
    low, high = 0.0, 1.0
    for origin, delta, minimum, maximum in (
        (first[0], dx, left, right),
        (first[1], dy, top, bottom),
    ):
        if abs(delta) < 1e-12:
            if origin < minimum or origin > maximum:
                return False
            continue
        enter, leave = (minimum - origin) / delta, (maximum - origin) / delta
        if enter > leave:
            enter, leave = leave, enter
        low, high = max(low, enter), min(high, leave)
        if low > high:
            return False
    return True


def _first_locked_hit(
    geometry: list[list[float]],
    start_segment: int,
    end_segment: int,
    gates: list[dict[str, Any]],
) -> tuple[int, dict[str, Any]] | None:
    if not gates or end_segment < start_segment:
        return None
    for segment in range(start_segment, end_segment + 1):
        for gate in gates:
            if _segment_intersects_locked_bar(geometry[segment], geometry[segment + 1], gate):
                return segment, gate
    return None


def _path_segment(event: dict[str, Any], geometry: list[list[float]]) -> int | None:
    value = event.get("path_segment")
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < len(geometry) - 1:
        return None
    return value


def _first_gate_hit(
    geometry: list[list[float]],
    start_segment: int,
    end_segment: int,
    gates: list[dict[str, Any]],
) -> tuple[int, dict[str, Any]] | None:
    for segment in range(start_segment, end_segment + 1):
        hits = [
            (amount, gate)
            for gate in gates
            if (amount := _crossing_amount(geometry[segment], geometry[segment + 1], gate)) is not None
        ]
        if hits:
            return segment, min(hits, key=lambda item: item[0])[1]
    return None


def _first_point_hit(
    geometry: list[list[float]],
    start_segment: int,
    end_segment: int,
    point: list[float],
    tolerance: float,
) -> int | None:
    for segment in range(start_segment, end_segment + 1):
        if _segment_distance(point, geometry[segment], geometry[segment + 1]) <= tolerance:
            return segment
    return None


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if payload.get("mechanic_id") != MECHANIC_ID or ground_truth.get("mechanic_id") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    if payload.get("challenge_id") != ground_truth.get("challenge_id"):
        return _fail("stale challenge")
    condition = ground_truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "full")
    if payload.get("interaction") != interaction:
        return _fail("interaction transcript does not match the assigned surface")
    public_condition = public_state.get("control_condition")
    if public_condition != ground_truth.get("control_condition"):
        return _fail("public/private control contract mismatch")

    interruptions = payload.get("interruptions")
    if not isinstance(interruptions, list) or len(interruptions) > 8:
        return _fail("interrupted-stroke record is malformed")
    if interaction != "full" and interruptions:
        return _fail("proxy interaction cannot report native pointer interruption")
    for index, interruption in enumerate(interruptions, start=1):
        if (
            not isinstance(interruption, dict)
            or interruption.get("sequence") != index
            or interruption.get("kind") != "stroke_cancel"
            or interruption.get("input_source") != "direct_stroke"
            or interruption.get("termination") not in {"pointercancel", "lostpointercapture"}
            or interruption.get("complete") is not False
        ):
            return _fail("interrupted-stroke record is malformed")
    route_violations = payload.get("route_violations")
    if not isinstance(route_violations, list) or len(route_violations) > 8:
        return _fail("route-violation record is malformed")
    if route_violations:
        return _fail("the continuous stroke crossed a locked spent bar")

    events = payload.get("events")
    if not isinstance(events, list) or not events:
        return _fail("no atelier stroke record")
    if len(events) > 40:
        return _fail("atelier stroke record is unexpectedly long")
    expected_sources = {
        "full": {kind: "direct_stroke" for kind in KINDS},
        "simplified": {
            "stroke_start": "proxy_stroke", "gate_cross": "proxy_gate",
            "motif_sample": "proxy_motif", "stroke_end": "proxy_stroke",
        },
    }[interaction]
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != index:
            return _fail("event sequence is malformed")
        kind = str(event.get("kind") or "")
        if kind not in expected_sources or event.get("input_source") != expected_sources[kind]:
            return _fail("wrong interaction input source in stroke record")

    cursor = 0
    first = events[cursor]
    stroke_number = int(first.get("stroke", 0))
    stroke_budget = int(ground_truth.get("stroke_budget") or 1)
    if first.get("kind") != "stroke_start" or not 1 <= stroke_number <= stroke_budget:
        return _fail("the badge stroke number exceeds its budget")
    start = _point(first.get("point"))
    if start is None or _distance(start, [float(item) for item in ground_truth["start"]]) > 38:
        return _fail("stroke did not begin on the brass start seal")
    stroke_geometry: list[list[float]] = []
    path_cursor = 0
    raw_stroke_geometry = payload.get("stroke_geometry")
    if not isinstance(raw_stroke_geometry, list) or not 2 <= len(raw_stroke_geometry) <= 2000:
        return _fail("continuous stroke geometry is missing or malformed")
    parsed_stroke_geometry = [_point(item) for item in raw_stroke_geometry]
    if any(item is None for item in parsed_stroke_geometry):
        return _fail("continuous stroke geometry contains an invalid point")
    stroke_geometry = [item for item in parsed_stroke_geometry if item is not None]
    width = float(ground_truth["stage"]["width"])
    height = float(ground_truth["stage"]["height"])
    if any(not 0 <= point[0] <= width or not 0 <= point[1] <= height for point in stroke_geometry):
        return _fail("continuous stroke geometry left the visible bench")
    if first.get("path_index") != 0 or _distance(stroke_geometry[0], start) > 1.5:
        return _fail("continuous stroke geometry does not begin with the recorded press")
    cursor += 1

    prefix: list[str] = []
    selected: dict[str, str] = {}
    locked_gates: list[dict[str, Any]] = []
    locked_gate_memory = int(ground_truth.get("locked_gate_memory") or 0)
    for phase, field in enumerate(ground_truth["active_fields"]):
        if cursor >= len(events) or events[cursor].get("kind") != "gate_cross":
            return _fail(f"missing {field} command crossing")
        event = events[cursor]
        gates = ground_truth["gate_sets"].get(_key(phase, prefix)) or []
        gate = next((item for item in gates if item["id"] == event.get("gate_id")), None)
        if gate is None:
            return _fail(f"{field} crossing does not belong to the revealed command bank")
        if event.get("field") != field or event.get("value") != gate["value"]:
            return _fail(f"{field} crossing record does not match the revealed bar")
        if event.get("direction") != gate["direction"]:
            return _fail(f"{field} bar was crossed in the wrong direction")
        before, after = _point(event.get("before")), _point(event.get("after"))
        if before is None or after is None or not _crosses(before, after, gate):
            return _fail(f"{field} crossing geometry is invalid")
        segment = _path_segment(event, stroke_geometry)
        if segment is None or segment < path_cursor:
            return _fail(f"{field} crossing is not ordered on one continuous stroke")
        if _distance(stroke_geometry[segment], before) > 1.5 or _distance(stroke_geometry[segment + 1], after) > 1.5:
            return _fail(f"{field} crossing is detached from the continuous stroke")
        if _first_locked_hit(stroke_geometry, path_cursor, segment, locked_gates) is not None:
            return _fail("the continuous stroke crossed a locked spent bar")
        first_hit = _first_gate_hit(stroke_geometry, path_cursor, segment, gates)
        if first_hit is None or first_hit[0] != segment or first_hit[1]["id"] != gate["id"]:
            return _fail(f"{field} crossing does not match the first physical bar hit")
        path_cursor = segment + 1
        selected[field] = str(gate["value"])
        prefix.append(str(gate["value"]))
        if locked_gate_memory:
            locked_gates.append(gate)
            locked_gates = locked_gates[-locked_gate_memory:]
        cursor += 1

    motif_points = ground_truth["motif"]["points"]
    tolerance = float(ground_truth["motif"]["tolerance"])
    for motif_index, expected in enumerate(motif_points):
        if cursor >= len(events) or events[cursor].get("kind") != "motif_sample":
            return _fail(f"motif point {motif_index + 1} was not reached in order")
        event = events[cursor]
        if int(event.get("checkpoint", -1)) != motif_index:
            return _fail("motif checkpoints are out of order")
        point = _point(event.get("point"))
        if point is None or _distance(point, [float(item) for item in expected]) > tolerance:
            return _fail(f"motif point {motif_index + 1} falls outside the drawing tolerance")
        segment = _path_segment(event, stroke_geometry)
        if segment is None or segment < path_cursor:
            return _fail(f"motif point {motif_index + 1} is not ordered on the continuous stroke")
        if _first_locked_hit(stroke_geometry, path_cursor, segment, locked_gates) is not None:
            return _fail("the continuous stroke crossed a locked spent bar")
        first_hit = _first_point_hit(
            stroke_geometry,
            path_cursor,
            segment,
            [float(item) for item in expected],
            tolerance,
        )
        if first_hit != segment or _segment_distance(point, stroke_geometry[segment], stroke_geometry[segment + 1]) > 1.5:
            return _fail(f"motif point {motif_index + 1} is detached from the continuous stroke")
        path_cursor = segment + 1
        cursor += 1

    if cursor >= len(events) or events[cursor].get("kind") != "stroke_end" or events[cursor].get("complete") is not True:
        return _fail("the continuous stroke did not end on FINISH")
    final_point = _point(events[cursor].get("point"))
    if final_point is None or _distance(final_point, [float(item) for item in motif_points[-1]]) > tolerance:
        return _fail("stroke release missed FINISH")
    if _first_locked_hit(stroke_geometry, path_cursor, len(stroke_geometry) - 2, locked_gates) is not None:
        return _fail("the continuous stroke crossed a locked spent bar")
    if events[cursor].get("path_index") != len(stroke_geometry) - 1:
        return _fail("stroke release is detached from the continuous stroke")
    if _distance(stroke_geometry[-1], final_point) > 1.5:
        return _fail("continuous stroke geometry does not end at the recorded release")
    if interaction == "full":
        if events[cursor].get("termination") != "pointerup":
            return _fail("the direct stroke did not end with a normal pointer release")
    elif events[cursor].get("termination") != "proxy_end":
        return _fail("the proxy stroke did not use its END control")
    cursor += 1
    if cursor != len(events):
        return _fail("events occurred after the badge stroke ended")
    if any(int(event.get("stroke", 0)) != stroke_number for event in events):
        return _fail("multiple physical strokes were spliced into one record")

    expected_fields = {item["field"]: item["value"] for item in ground_truth["target"]}
    correct = sum(selected.get(field) == value for field, value in expected_fields.items())
    if selected != expected_fields:
        return _fail(f"badge fields {correct}/{len(expected_fields)} match the target plate")
    if payload.get("completed") is not True or int(payload.get("stroke_count", 0)) != stroke_number:
        return _fail("badge was not completed within the declared stroke budget")
    claimed = payload.get("selected_fields")
    if claimed != selected:
        return _fail("reported badge fields do not match the replayed crossings")
    drawn = payload.get("drawn_geometry")
    if not isinstance(drawn, list) or not len(motif_points) <= len(drawn) <= 1000:
        return _fail("drawn badge geometry is missing or malformed")
    geometry = [_point(item) for item in drawn]
    if any(item is None for item in geometry):
        return _fail("drawn badge geometry contains an invalid point")
    geometry = [item for item in geometry if item is not None]
    expected_polyline = [[float(value) for value in item] for item in motif_points]
    if _distance(geometry[0], expected_polyline[0]) > tolerance or _distance(geometry[-1], expected_polyline[-1]) > tolerance:
        return _fail("drawn badge geometry misses its endpoints")
    for first, second in zip(geometry, geometry[1:]):
        for index in range(9):
            amount = index / 8
            sample = [first[0] + (second[0] - first[0]) * amount, first[1] + (second[1] - first[1]) * amount]
            if _polyline_distance(sample, expected_polyline) > tolerance:
                return _fail("drawn badge geometry left the visible motif corridor")
    return {
        "graded": True, "passed": True, "score": 100,
        "feedback": f"replayed stroke {stroke_number}/{stroke_budget}; fields {correct}/{len(expected_fields)}; motif {len(motif_points)}/{len(motif_points)}; passed",
    }
