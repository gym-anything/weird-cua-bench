from __future__ import annotations

import math
from typing import Any, Iterable


MECHANIC_ID = "einstein_loop"
EDGE_STATES = {"clear": 0, "loop": 1, "cross": -1}


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _bind(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> str | None:
    if any(str(item.get("mechanic_id") or "") != MECHANIC_ID for item in (payload, truth, public)):
        return "mechanic mismatch"
    for key in ("task_id", "challenge_id"):
        expected = str(truth.get(key) or "")
        if not expected or str(payload.get(key) or "") != expected or str(public.get(key) or "") != expected:
            return f"stale or mismatched {key}"
    return None


def _integer_suffix(identifier: str, prefix: str) -> int:
    if not identifier.startswith(prefix) or not identifier[len(prefix):].isdigit():
        raise ValueError(f"invalid {prefix} identifier")
    return int(identifier[len(prefix):])


def _single_cycle(edge_ids: Iterable[str], puzzle: dict[str, Any]) -> bool:
    selected = set(edge_ids)
    if len(selected) < 3:
        return False
    graph: dict[str, list[str]] = {}
    for edge in puzzle["edges"]:
        if edge["id"] not in selected:
            continue
        start, end = edge["vertices"]
        graph.setdefault(start, []).append(end)
        graph.setdefault(end, []).append(start)
    if not graph or any(len(neighbours) != 2 for neighbours in graph.values()):
        return False
    seen = set()
    stack = [next(iter(graph))]
    while stack:
        vertex = stack.pop()
        if vertex in seen:
            continue
        seen.add(vertex)
        stack.extend(graph[vertex])
    return len(seen) == len(graph)


def _cyclic_equal(left: list[float], right: list[float], tolerance: float = 0.002) -> bool:
    if len(left) != len(right):
        return False
    for candidate in (right, list(reversed(right))):
        for offset in range(len(candidate)):
            if all(abs(left[index] - candidate[(index + offset) % len(candidate)]) <= tolerance for index in range(len(left))):
                return True
    return False


def _contract(truth: dict[str, Any], public: dict[str, Any]) -> tuple[dict[str, Any], set[str], str]:
    puzzle = truth.get("puzzle")
    if not isinstance(puzzle, dict) or public.get("puzzle") != puzzle:
        raise ValueError("public tiling differs from the replay contract")
    parameters = truth.get("parameters")
    if not isinstance(parameters, dict) or public.get("parameters") != parameters:
        raise ValueError("difficulty parameters differ from the replay contract")
    condition = truth.get("control_condition")
    if condition != public.get("control_condition"):
        raise ValueError("public control condition differs from replay truth")
    if condition is not None and condition.get("difficulty_parameters") != parameters:
        raise ValueError("condition parameters differ from the generated puzzle")
    interaction = str((condition or {}).get("interaction") or "full")
    if interaction not in {"simplified", "full"}:
        raise ValueError("interaction mode is invalid")

    vertices = puzzle.get("vertices")
    edges = puzzle.get("edges")
    faces = puzzle.get("faces")
    clues = puzzle.get("clues")
    if not isinstance(vertices, list) or not isinstance(edges, list) or not isinstance(faces, list) or not isinstance(clues, list):
        raise ValueError("tiling arrays are missing")
    if len(faces) != parameters.get("tile_count") or not 6 <= len(faces) <= 24:
        raise ValueError("tile count differs from the profile")
    if puzzle.get("view_width") != 960 or puzzle.get("view_height") != 610:
        raise ValueError("board viewport is invalid")

    vertex_points: dict[str, tuple[float, float]] = {}
    for index, vertex in enumerate(vertices):
        if not isinstance(vertex, dict) or vertex.get("id") != f"v{index}":
            raise ValueError("vertices are not canonical")
        x, y = vertex.get("x"), vertex.get("y")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in (x, y)):
            raise ValueError("vertex coordinate is invalid")
        if not 0 <= float(x) <= 960 or not 0 <= float(y) <= 610:
            raise ValueError("vertex leaves the visible board")
        vertex_points[vertex["id"]] = (float(x), float(y))

    edge_by_key: dict[tuple[str, str], str] = {}
    edge_faces: dict[str, list[str]] = {}
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict) or edge.get("id") != f"e{index}":
            raise ValueError("edges are not canonical")
        endpoints = edge.get("vertices")
        owners = edge.get("faces")
        if not isinstance(endpoints, list) or len(endpoints) != 2 or endpoints[0] == endpoints[1] or any(point not in vertex_points for point in endpoints):
            raise ValueError("edge endpoints are invalid")
        if not isinstance(owners, list) or not 1 <= len(owners) <= 2 or len(set(owners)) != len(owners):
            raise ValueError("edge ownership is invalid")
        key = tuple(sorted(endpoints))
        if key in edge_by_key:
            raise ValueError("duplicate geometric edge")
        edge_by_key[key] = edge["id"]
        edge_faces[edge["id"]] = owners

    face_edges: dict[str, list[str]] = {}
    reference_lengths: list[float] | None = None
    for index, face in enumerate(faces):
        if not isinstance(face, dict) or face.get("id") != f"f{index}":
            raise ValueError("faces are not canonical")
        vertex_ids = face.get("vertices")
        listed_edges = face.get("edge_ids")
        label_point = face.get("label_point")
        if not isinstance(vertex_ids, list) or len(vertex_ids) != 14 or len(set(vertex_ids)) != 14 or any(vertex not in vertex_points for vertex in vertex_ids):
            raise ValueError("face is not a subdivided hat outline")
        if not isinstance(listed_edges, list) or len(listed_edges) != 14:
            raise ValueError("face edge list is invalid")
        reconstructed = [
            edge_by_key.get(tuple(sorted((vertex_ids[item], vertex_ids[(item + 1) % 14]))))
            for item in range(14)
        ]
        if reconstructed != listed_edges or any(face["id"] not in edge_faces[edge_id] for edge_id in listed_edges):
            raise ValueError("face boundary and edge ownership disagree")
        if not isinstance(label_point, dict) or any(
            isinstance(label_point.get(axis), bool)
            or not isinstance(label_point.get(axis), (int, float))
            or not math.isfinite(float(label_point[axis]))
            for axis in ("x", "y")
        ):
            raise ValueError("face label point is invalid")
        lengths = [
            math.dist(vertex_points[vertex_ids[item]], vertex_points[vertex_ids[(item + 1) % 14]])
            for item in range(14)
        ]
        scale = min(lengths)
        normalised = [round(length / scale, 5) for length in lengths]
        if reference_lengths is None:
            reference_lengths = normalised
        elif not _cyclic_equal(reference_lengths, normalised):
            raise ValueError("faces are not congruent hat outlines")
        face_edges[face["id"]] = listed_edges

    clue_map: dict[str, int] = {}
    for clue in clues:
        if not isinstance(clue, dict) or clue.get("face_id") not in face_edges:
            raise ValueError("clue references an invalid face")
        value = clue.get("value")
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 14:
            raise ValueError("clue value is invalid")
        if clue["face_id"] in clue_map:
            raise ValueError("duplicate face clue")
        clue_map[clue["face_id"]] = value
    expected_clues = max(3, math.ceil(len(faces) * float(parameters.get("clue_fraction"))))
    if len(clue_map) != expected_clues:
        raise ValueError("clue count differs from the profile")

    solution_raw = truth.get("solution_edge_ids")
    if not isinstance(solution_raw, list) or len(set(solution_raw)) != len(solution_raw) or any(edge_id not in edge_faces for edge_id in solution_raw):
        raise ValueError("private solution edge set is invalid")
    solution = set(solution_raw)
    if not _single_cycle(solution, puzzle):
        raise ValueError("private solution is not one closed loop")
    for face_id, clue in clue_map.items():
        if sum(edge_id in solution for edge_id in face_edges[face_id]) != clue:
            raise ValueError("visible clue disagrees with the solution")
    internal = sum(1 for edge_id in solution if len(edge_faces[edge_id]) == 2)
    if internal < parameters.get("minimum_internal_loop_edges", 0):
        raise ValueError("solution does not cross enough internal tile boundaries")
    return puzzle, solution, interaction


def _gesture_path(event: dict[str, Any], puzzle: dict[str, Any], edge_ids: list[str]) -> None:
    gesture = event.get("gesture")
    if not isinstance(gesture, dict):
        raise ValueError("direct loop stroke lacks gesture proof")
    start = str(gesture.get("start_vertex_id") or "")
    end = str(gesture.get("end_vertex_id") or "")
    travel = gesture.get("travel_px")
    samples = gesture.get("sample_count")
    if (
        isinstance(travel, bool)
        or not isinstance(travel, (int, float))
        or not math.isfinite(float(travel))
        or isinstance(samples, bool)
        or not isinstance(samples, int)
        or samples < len(edge_ids) + 1
    ):
        raise ValueError("direct loop stroke is too short or sparsely sampled")
    edge_map = {edge["id"]: edge for edge in puzzle["edges"]}
    current = start
    expected_travel = 0.0
    vertex_map = {vertex["id"]: (float(vertex["x"]), float(vertex["y"])) for vertex in puzzle["vertices"]}
    seen = set()
    for edge_id in edge_ids:
        if edge_id in seen:
            raise ValueError("direct loop stroke repeats an edge")
        seen.add(edge_id)
        first, second = edge_map[edge_id]["vertices"]
        if current == first:
            following = second
        elif current == second:
            following = first
        else:
            raise ValueError("direct loop stroke is not a contiguous path")
        expected_travel += math.dist(vertex_map[current], vertex_map[following])
        current = following
    if current != end or float(travel) < expected_travel * 0.7:
        raise ValueError("direct loop stroke endpoints or travel disagree with geometry")


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    binding = _bind(payload, truth, public)
    if binding:
        return _fail(binding)
    try:
        puzzle, solution, interaction = _contract(truth, public)
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"invalid Einstein Loop contract: {exc}")
    if payload.get("interaction_mode") != interaction:
        return _fail("submitted interaction mode differs from task condition")
    events = payload.get("events")
    edge_ids = {edge["id"] for edge in puzzle["edges"]}
    if not isinstance(events, list) or not 1 <= len(events) <= len(edge_ids) * 4 + 20:
        return _fail("edge transcript is missing or outside limits")

    state = {edge_id: 0 for edge_id in edge_ids}
    update_count = 0
    try:
        for sequence, event in enumerate(events, 1):
            if not isinstance(event, dict) or event.get("sequence") != sequence:
                raise ValueError(f"event {sequence} has an invalid sequence")
            event_type = event.get("type")
            if event_type == "reset":
                if event.get("input_source") != "reset_button":
                    raise ValueError(f"event {sequence} uses an invalid reset surface")
                state = {edge_id: 0 for edge_id in edge_ids}
                continue
            if event_type != "edge_update":
                raise ValueError(f"event {sequence} has an unknown type")
            mode = str(event.get("mode") or "")
            if mode not in EDGE_STATES:
                raise ValueError(f"event {sequence} has an invalid edge mode")
            updates = event.get("edges")
            if not isinstance(updates, list) or not updates:
                raise ValueError(f"event {sequence} has no edge updates")
            input_source = event.get("input_source")
            if interaction == "simplified":
                if input_source != "edge_proxy_button" or len(updates) != 1:
                    raise ValueError(f"event {sequence} uses the wrong simplified input surface")
            else:
                if input_source == "direct_edge_drag":
                    if mode not in {"loop", "clear"}:
                        raise ValueError(f"event {sequence} drags an invalid mark")
                    _gesture_path(event, puzzle, [str(update.get("id") or "") for update in updates])
                elif input_source == "direct_edge_context":
                    if len(updates) != 1 or mode not in {"cross", "clear"}:
                        raise ValueError(f"event {sequence} has an invalid context mark")
                else:
                    raise ValueError(f"event {sequence} uses the wrong full input surface")
            for update in updates:
                if not isinstance(update, dict):
                    raise ValueError(f"event {sequence} contains an invalid edge update")
                edge_id = str(update.get("id") or "")
                before = update.get("before")
                after = update.get("after")
                if edge_id not in state or before != state[edge_id] or after != EDGE_STATES[mode]:
                    raise ValueError(f"event {sequence} starts from stale edge state")
                state[edge_id] = after
            update_count += len(updates)
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"Einstein Loop replay rejected: {exc}")

    final_loop = sorted((edge_id for edge_id, value in state.items() if value == 1), key=lambda value: _integer_suffix(value, "e"))
    final_crosses = sorted((edge_id for edge_id, value in state.items() if value == -1), key=lambda value: _integer_suffix(value, "e"))
    if payload.get("final_loop_edge_ids") != final_loop or payload.get("final_crossed_edge_ids") != final_crosses:
        return _fail("submitted edge sets do not match transcript replay")
    passed = payload.get("completed") is True and set(final_loop) == solution
    if not passed:
        return _fail("loop rejected: topology or clue counts differ")
    return {
        "graded": True,
        "passed": True,
        "feedback": f"one exact loop; {len(final_loop)} loop edges; {update_count} replayed edge updates",
    }


__all__ = ["MECHANIC_ID", "grade"]
