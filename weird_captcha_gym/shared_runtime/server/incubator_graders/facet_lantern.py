"""Independent replay grader for Facet Lantern."""

from __future__ import annotations

import math
from itertools import combinations
from typing import Any


MECHANIC_ID = "facet_lantern"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _edge(first: Any, second: Any) -> tuple[str, str]:
    return tuple(sorted((str(first), str(second))))


def _norm(angle: float) -> float:
    return float(angle) % 360.0


def _angle_delta(first: float, second: float) -> float:
    return abs((float(first) - float(second) + 180.0) % 360.0 - 180.0)


def _visible_ids(world: dict[str, Any], yaw: float) -> set[str]:
    band = float(world.get("occlusion_band", 0.25))
    visible: set[str] = set()
    radians = math.radians(float(yaw))
    for vertex in world.get("vertices") or []:
        x = float(vertex.get("x", 0.0))
        z = float(vertex.get("z", 0.0))
        depth = x * math.sin(radians) + z * math.cos(radians)
        if depth >= -band - 1e-7:
            visible.add(str(vertex.get("id")))
    return visible


def _score(connections: set[tuple[str, str]], targets: list[dict[str, Any]], vertices: list[dict[str, Any]]) -> tuple[int, int, int]:
    completed = 0
    polygon_points = 0
    for target in targets:
        items = [str(item) for item in target.get("vertices") or []]
        required = {_edge(first, second) for first, second in zip(items, items[1:] + items[:1])}
        if required <= connections:
            completed += 1
            polygon_points += 10 * len(items)
    degree = {str(vertex.get("id")): 0 for vertex in vertices}
    for first, second in connections:
        if first in degree:
            degree[first] += 1
        if second in degree:
            degree[second] += 1
    isolated = sum(value == 0 for value in degree.values())
    return 10 * len(connections) + polygon_points - isolated, completed, isolated


def grade(payload: dict[str, Any], truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(truth, dict) or not isinstance(public_state, dict):
        return _fail("facet lantern submission is malformed")
    for key in ("mechanic_id", "task_id", "challenge_id"):
        if payload.get(key) != truth.get(key):
            return _fail(f"stale or mismatched {key}")
    if public_state.get("challenge_id") != truth.get("challenge_id"):
        return _fail("public challenge is stale")
    if payload.get("control_condition") != truth.get("control_condition"):
        return _fail("submitted control contract mismatch")
    condition = truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "full")
    if interaction not in {"full", "simplified"}:
        return _fail("invalid facet lantern interaction condition")
    expected_rotation_source = "direct_pointer" if interaction == "full" else "proxy_button"
    expected_vertex_source = "vertex_click"
    world = truth.get("world") or {}
    vertices = world.get("vertices") or []
    vertex_ids = {str(vertex.get("id")) for vertex in vertices}
    targets = truth.get("targets") or []
    required = {_edge(edge[0], edge[1]) for edge in truth.get("required_connections") or []}
    initial = {_edge(edge[0], edge[1]) for edge in world.get("connections") or []}
    if not required or not initial <= required:
        return _fail("facet lantern connection contract is malformed")
    events = payload.get("events")
    if not isinstance(events, list) or len(events) == 0 or len(events) > 2000:
        return _fail("no usable lantern interaction transcript")

    connections = set(initial)
    selected: str | None = None
    yaw = float(world.get("initial_yaw", 0.0))
    rotation_count = 0
    sequence = 0
    for event in events:
        sequence += 1
        if not isinstance(event, dict) or event.get("seq") != sequence:
            return _fail("lantern event sequence is malformed")
        event_type = str(event.get("type") or "")
        source = str(event.get("input_source") or "")
        if event_type == "rotate":
            if source != expected_rotation_source:
                return _fail("rotation uses the wrong interaction surface")
            try:
                before = float(event.get("from_yaw"))
                after = float(event.get("to_yaw"))
                delta = float(event.get("delta"))
            except (TypeError, ValueError):
                return _fail("rotation has invalid geometry")
            if _angle_delta(before, yaw) > 0.25 or abs(delta) > 180.0 or _angle_delta(after, _norm(before + delta)) > 0.25:
                return _fail("rotation does not continue from the visible lantern")
            if interaction == "full":
                path = event.get("path")
                if not isinstance(path, list) or len(path) < 2 or any(not isinstance(point, list) or len(point) != 2 for point in path):
                    return _fail("direct rotation is missing its pointer path")
            else:
                if event.get("direction") not in {"left", "right"}:
                    return _fail("proxy rotation is missing its direction")
                step = float(world.get("rotation_step_degrees", 15.0))
                if abs(abs(delta) - step) > 0.25:
                    return _fail("proxy rotation does not use the visible turn step")
            yaw = _norm(after)
            rotation_count += 1
            continue
        if event_type == "select_vertex":
            if source != expected_vertex_source:
                return _fail("vertex selection uses an unknown input surface")
            vertex_id = str(event.get("vertex_id") or "")
            if vertex_id not in vertex_ids or selected is not None:
                return _fail("vertex selection is invalid")
            if vertex_id not in _visible_ids(world, yaw):
                return _fail("a hidden vertex was selected")
            selected = vertex_id
            continue
        if event_type == "connect":
            if source != expected_vertex_source or selected is None:
                return _fail("connection was not preceded by one visible vertex click")
            other = str(event.get("vertex_id") or "")
            if other not in vertex_ids or other == selected:
                return _fail("connection endpoint is invalid")
            if other not in _visible_ids(world, yaw):
                return _fail("a hidden vertex was connected")
            edge = _edge(selected, other)
            if edge in connections:
                return _fail("duplicate connection was submitted")
            connections.add(edge)
            selected = None
            continue
        if event_type == "clear_selection":
            if source != expected_vertex_source or selected is None:
                return _fail("selection clear is invalid")
            selected = None
            continue
        if event_type == "submit":
            if source != "certify_button":
                return _fail("certification uses an unknown input surface")
            continue
        return _fail("unknown lantern event type")

    if selected is not None:
        return _fail("a vertex was selected without a completed connection")
    if rotation_count < 1:
        return _fail("the lantern was never rotated")
    if payload.get("completed") is not True:
        return _fail("lantern attempt was not certified")
    if connections != required:
        return _fail("requested facet edges are incomplete or contain extra connections")
    score, complete, isolated = _score(connections, targets, vertices)
    expected_score, expected_complete, expected_isolated = _score(required, targets, vertices)
    if complete != len(targets) or score != expected_score or score != int(truth.get("target_score", expected_score)):
        return _fail(f"score mismatch: {score} with {complete} closed facets and {isolated} isolated studs")
    reported = payload.get("reported_score")
    if reported is not None and int(reported) != score:
        return _fail("reported score disagrees with replay")
    return {
        "graded": True,
        "passed": True,
        "score": 100,
        "feedback": f"{len(vertices)} 3D studs and {len(targets)} requested facets replay to score {score}",
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    return {
        "mechanic_id": MECHANIC_ID,
        "challenge_id": ground_truth.get("challenge_id"),
        "required_connections": ground_truth.get("required_connections") or [],
        "target_score": ground_truth.get("target_score"),
        "initial_yaw": (ground_truth.get("world") or {}).get("initial_yaw"),
        "visible_initial_studs": sorted(_visible_ids(ground_truth.get("world") or {}, float((ground_truth.get("world") or {}).get("initial_yaw", 0.0)))),
    }
