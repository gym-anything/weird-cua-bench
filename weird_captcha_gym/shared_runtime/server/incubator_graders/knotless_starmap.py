"""Independent replay grader for Knotless Starmap."""

from __future__ import annotations

import math
from itertools import combinations
from typing import Any


MECHANIC_ID = "knotless_starmap"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _point(value: object) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        parsed = (float(value[0]), float(value[1]))
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(item) for item in parsed):
        return None
    return parsed


def _orient(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> bool:
    return (
        min(a[0], b[0]) - 1e-7 <= p[0] <= max(a[0], b[0]) + 1e-7
        and min(a[1], b[1]) - 1e-7 <= p[1] <= max(a[1], b[1]) + 1e-7
        and abs(_orient(a, b, p)) <= 1e-7
    )


def _segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    ab_c, ab_d = _orient(a, b, c), _orient(a, b, d)
    cd_a, cd_b = _orient(c, d, a), _orient(c, d, b)
    proper = (
        ((ab_c > 1e-7 and ab_d < -1e-7) or (ab_c < -1e-7 and ab_d > 1e-7))
        and ((cd_a > 1e-7 and cd_b < -1e-7) or (cd_a < -1e-7 and cd_b > 1e-7))
    )
    return proper or _on_segment(a, b, c) or _on_segment(a, b, d) or _on_segment(c, d, a) or _on_segment(c, d, b)


def _positions_from_truth(truth: dict[str, Any]) -> dict[str, tuple[float, float]] | None:
    world = truth.get("world")
    vertices = world.get("vertices") if isinstance(world, dict) else None
    if not isinstance(vertices, list) or not vertices:
        return None
    positions: dict[str, tuple[float, float]] = {}
    for vertex in vertices:
        if not isinstance(vertex, dict):
            return None
        vertex_id = str(vertex.get("id") or "")
        point = _point([vertex.get("x"), vertex.get("y")])
        if not vertex_id or point is None or vertex_id in positions:
            return None
        positions[vertex_id] = point
    return positions


def _edge_overlap_at_shared_vertex(
    first: tuple[str, str],
    second: tuple[str, str],
    positions: dict[str, tuple[float, float]],
) -> bool:
    shared = set(first) & set(second)
    if len(shared) != 1:
        return False
    shared_id = next(iter(shared))
    first_other = first[0] if first[1] == shared_id else first[1]
    second_other = second[0] if second[1] == shared_id else second[1]
    origin = positions[shared_id]
    first_point, second_point = positions[first_other], positions[second_other]
    if abs(_orient(origin, first_point, second_point)) > 1e-7:
        return False
    first_vector = (first_point[0] - origin[0], first_point[1] - origin[1])
    second_vector = (second_point[0] - origin[0], second_point[1] - origin[1])
    return first_vector[0] * second_vector[0] + first_vector[1] * second_vector[1] > 1e-7


def _crossings(edges: list[tuple[str, str]], positions: dict[str, tuple[float, float]]) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    crossings: list[tuple[int, int]] = []
    overlaps: list[tuple[int, int]] = []
    for first, second in combinations(range(len(edges)), 2):
        edge_a, edge_b = edges[first], edges[second]
        shared = set(edge_a) & set(edge_b)
        if shared:
            if _edge_overlap_at_shared_vertex(edge_a, edge_b, positions):
                overlaps.append((first, second))
            continue
        if _segments_intersect(positions[edge_a[0]], positions[edge_a[1]], positions[edge_b[0]], positions[edge_b[1]]):
            crossings.append((first, second))
    return crossings, overlaps


def grade(payload: dict[str, Any], truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(truth, dict) or not isinstance(public_state, dict):
        return _fail("starmap submission is not an object")
    if payload.get("mechanic_id") != MECHANIC_ID or truth.get("mechanic_id") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    if payload.get("task_id") != truth.get("task_id") or payload.get("challenge_id") != truth.get("challenge_id"):
        return _fail("stale task or challenge")
    if public_state.get("challenge_id") != truth.get("challenge_id"):
        return _fail("public challenge is stale")
    if public_state.get("control_condition") != truth.get("control_condition"):
        return _fail("public/private control contract mismatch")
    if payload.get("control_condition") != truth.get("control_condition"):
        return _fail("submitted control contract mismatch")

    condition = truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "full")
    if interaction not in {"full", "simplified"}:
        return _fail("invalid starmap interaction condition")
    expected_source = "direct_drag" if interaction == "full" else "proxy_click"

    positions = _positions_from_truth(truth)
    world = truth.get("world")
    if positions is None or not isinstance(world, dict):
        return _fail("starmap world is malformed")
    vertex_ids = set(positions)
    raw_edges = world.get("edges")
    if not isinstance(raw_edges, list) or not raw_edges:
        return _fail("starmap edge set is missing")
    edges: list[tuple[str, str]] = []
    for raw_edge in raw_edges:
        if not isinstance(raw_edge, list) or len(raw_edge) != 2:
            return _fail("starmap edge set is malformed")
        edge = (str(raw_edge[0]), str(raw_edge[1]))
        if edge[0] == edge[1] or edge[0] not in vertex_ids or edge[1] not in vertex_ids:
            return _fail("starmap edge references an invalid vertex")
        edges.append(edge)
    if len(set(edges)) != len(edges):
        return _fail("starmap changed or duplicated an original edge")

    events = payload.get("events")
    if not isinstance(events, list) or not events or len(events) > 5000:
        return _fail("no usable starmap movement transcript")
    selected: str | None = None
    movement_count = 0
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("seq") != sequence:
            return _fail("starmap event sequence is malformed")
        event_type = str(event.get("type") or "")
        source = event.get("input_source")
        if event_type == "select":
            if interaction != "simplified" or source != expected_source:
                return _fail("selection uses the wrong interaction surface")
            vertex_id = str(event.get("vertex_id") or "")
            if vertex_id not in vertex_ids or selected is not None:
                return _fail("proxy selection is invalid")
            selected = vertex_id
            continue
        if event_type != "vertex_move" or source != expected_source:
            return _fail("starmap event uses the wrong interaction input")
        vertex_id = str(event.get("vertex_id") or "")
        if vertex_id not in vertex_ids:
            return _fail("movement references an unknown star")
        if interaction == "simplified" and selected != vertex_id:
            return _fail("proxy move was not preceded by its star selection")
        if interaction == "full" and selected is not None:
            return _fail("direct drag contains a proxy selection")
        before, after = _point(event.get("before")), _point(event.get("after"))
        if before is None or after is None:
            return _fail("starmap movement has invalid geometry")
        current = positions[vertex_id]
        if math.dist(before, current) > 0.75:
            return _fail("starmap movement starts from stale visible geometry")
        width = float((world.get("canvas") or {}).get("width", 0))
        height = float((world.get("canvas") or {}).get("height", 0))
        if not (0 <= after[0] <= width and 0 <= after[1] <= height):
            return _fail("star was moved outside the visible canvas")
        if interaction == "full":
            path = event.get("path")
            if not isinstance(path, list) or len(path) < 2 or any(_point(item) is None for item in path):
                return _fail("direct drag is missing its pointer path")
            if math.dist(_point(path[0]) or (0, 0), before) > 1.5 or math.dist(_point(path[-1]) or (0, 0), after) > 1.5:
                return _fail("direct drag path does not match its movement")
        else:
            if "path" in event:
                return _fail("proxy move must not report a native drag path")
        positions[vertex_id] = after
        selected = None
        movement_count += 1

    if selected is not None:
        return _fail("proxy star was selected without a destination")
    if payload.get("completed") is not True or movement_count < 1:
        return _fail("starmap was not submitted as a completed plan")

    separation = float(world.get("minimum_vertex_separation", 24))
    for first, second in combinations(sorted(vertex_ids), 2):
        if math.dist(positions[first], positions[second]) < separation - 0.25:
            return _fail("collapsed vertices are not a valid embedding")
    crossings, overlaps = _crossings(edges, positions)
    if overlaps:
        return _fail("overlapping edge segments are not a valid embedding")
    if crossings:
        return _fail(f"{len(crossings)} nonincident edge crossings remain")
    reported = payload.get("reported_crossings")
    if reported is not None and reported != 0:
        return _fail("submitted crossing count disagrees with the replay")
    return {
        "graded": True,
        "passed": True,
        "score": 100,
        "feedback": f"{len(vertex_ids)} stars and {len(edges)} fixed edges replay to a crossing-free embedding",
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    """Expose only to the opt-in local cheat route, never to normal UI state."""

    return {
        "mechanic_id": MECHANIC_ID,
        "challenge_id": ground_truth.get("challenge_id"),
        "solution_positions": ground_truth.get("solution_positions") or {},
        "initial_crossings": (public_state.get("world") or {}).get("initial_crossings"),
    }

