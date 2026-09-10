from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "branch_repair"
VIEWS = ("xy", "xz", "yz")
SLICE_AXES = {"xy": (0, 1, 2), "xz": (0, 2, 1), "yz": (1, 2, 0)}


def _edge(a: Any, b: Any) -> tuple[str, str]:
    left, right = str(a), str(b)
    return (left, right) if left < right else (right, left)


def _round(value: float) -> float:
    value = round(float(value), 3)
    return 0.0 if value == 0 else value


def _close(left: Any, right: Any, tolerance: float = 0.012) -> bool:
    try:
        return abs(float(left) - float(right)) <= tolerance
    except (TypeError, ValueError):
        return False


def _same_point(left: Any, right: Any, tolerance: float = 0.035) -> bool:
    return isinstance(left, list) and isinstance(right, list) and len(left) == len(right) and all(_close(a, b, tolerance) for a, b in zip(left, right))


def _nodes(public_state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item.get("id")): item for item in public_state.get("nodes") or [] if isinstance(item, dict)}


def _slice_records(public_state: dict[str, Any], focus: list[int], view: str) -> list[dict[str, Any]]:
    contract = public_state.get("slice_contract") or {}
    count = int(contract.get("index_count") or 1)
    axes = SLICE_AXES[view]
    level = -4.0 + 8.0 * int(focus[axes[2]]) / max(1, count - 1)
    output = []
    for node in public_state.get("nodes") or []:
        point = node.get("p") or []
        if len(point) != 3 or abs(float(point[axes[2]]) - level) > 0.72:
            continue
        output.append({"id": str(node["id"]), "u": _round(point[axes[0]]), "v": _round(point[axes[1]])})
    return sorted(output, key=lambda item: item["id"])


def _slice_digest(records: list[dict[str, Any]]) -> str:
    return "|".join(f"{item['id']}:{float(item['u']):.3f}:{float(item['v']):.3f}" for item in records)


def _views_digest(public_state: dict[str, Any], focus: list[int]) -> str:
    return ";".join(f"{view}={_slice_digest(_slice_records(public_state, focus, view))}" for view in VIEWS)


def _topology_digest(public_state: dict[str, Any], focus: list[int], edges: set[tuple[str, str]]) -> str:
    visible = {view: {item["id"] for item in _slice_records(public_state, focus, view)} for view in VIEWS}
    return ";".join(
        f"{view}={','.join(sorted(f'{left}|{right}' for left, right in edges if left in visible[view] and right in visible[view]))}"
        for view in VIEWS
    )


def _project(point: list[float], yaw: float, pitch: float) -> list[float]:
    x, y, z = map(float, point)
    cy, sy = math.cos(yaw), math.sin(yaw)
    rx, rz = cy * x + sy * z, -sy * x + cy * z
    cp, sp = math.cos(pitch), math.sin(pitch)
    ry = cp * y - sp * rz
    return [_round(360.0 + rx * 34.0), _round(145.0 - ry * 34.0)]


def _slice_screen(public_state: dict[str, Any], view: str, node_id: str) -> list[float] | None:
    node = _nodes(public_state).get(node_id)
    if node is None:
        return None
    record = next((item for item in _slice_records(public_state, public_state.get("focus") or [0, 0, 0], view) if item["id"] == node_id), None)
    # The current focus is supplied by the replay caller in the main grade.
    del record
    return None


def _screen_for_record(public_state: dict[str, Any], view: str, record: dict[str, Any]) -> list[float]:
    view_spec = public_state.get("views", {}).get(view, {})
    width = float(view_spec.get("width") or 230)
    height = float(view_spec.get("height") or 154)
    scale = float(view_spec.get("scale") or 24)
    return [_round(width / 2.0 + float(record["u"]) * scale), _round(height / 2.0 - float(record["v"]) * scale)]


def _nearest_node(public_state: dict[str, Any], screen: Any, yaw: float, pitch: float) -> str | None:
    if not isinstance(screen, list) or len(screen) != 2:
        return None
    best: tuple[float, str] | None = None
    by_id = _nodes(public_state)
    for node_id, node in by_id.items():
        point = _project(node.get("p") or [], yaw, pitch)
        distance = math.dist(point, [float(screen[0]), float(screen[1])])
        if best is None or distance < best[0]:
            best = (distance, node_id)
    return best[1] if best and best[0] <= 23.0 else None


def _component(edges: set[tuple[str, str]], seed: str) -> set[str]:
    graph: dict[str, set[str]] = {}
    for left, right in edges:
        graph.setdefault(left, set()).add(right)
        graph.setdefault(right, set()).add(left)
    seen = {seed}
    pending = [seed]
    while pending:
        current = pending.pop()
        for neighbor in graph.get(current, set()):
            if neighbor not in seen:
                seen.add(neighbor)
                pending.append(neighbor)
    return seen


def _failure(feedback: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": feedback}


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or str(payload.get("mechanic_id") or "") != MECHANIC_ID:
        return _failure("mechanic mismatch")
    if str(payload.get("challenge_id") or "") != str(ground_truth.get("challenge_id") or ""):
        return _failure("stale challenge")
    if str(payload.get("task_id") or "") != str(ground_truth.get("task_id") or ""):
        return _failure("task mismatch")
    expected_interaction = str(ground_truth.get("interaction") or "full")
    if str(payload.get("interaction") or "") != expected_interaction:
        return _failure("interaction surface does not match the task")
    events = payload.get("events")
    requirements = ground_truth.get("requirements") or public_state.get("requirements") or {}
    if not isinstance(events, list) or not events:
        return _failure("no visible repair events were submitted")
    if len(events) > int(requirements.get("max_events") or 1000):
        return _failure("repair transcript exceeded the task event budget")
    node_map = _nodes(public_state)
    current_edges = {_edge(item[0], item[1]) for item in public_state.get("initial_edges") or []}
    true_edges = {_edge(item[0], item[1]) for item in ground_truth.get("true_edges") or []}
    missing_edges = {_edge(item[0], item[1]) for item in ground_truth.get("missing_edges") or []}
    false_edges = {_edge(item[0], item[1]) for item in ground_truth.get("false_edges") or []}
    focus = [int(value) for value in (public_state.get("focus") or [0, 0, 0])]
    count = int((public_state.get("slice_contract") or {}).get("index_count") or 1)
    yaw, pitch = 0.0, 0.35
    selected: set[str] = set()
    seeds: dict[str, str] = {}
    slice_observations: set[str] = set()
    post_edit_inspections = 0
    repair_actions = 0
    inspection_required = False
    orbit_actions = 0
    submitted = False
    for number, event in enumerate(events, 1):
        if not isinstance(event, dict):
            return _failure(f"event {number} is not an object")
        if int(event.get("sequence") or number) != number:
            return _failure("repair transcript sequence is not contiguous")
        kind = str(event.get("kind") or "")
        if kind == "slice_change":
            if event.get("source") != ("slice_controls" if expected_interaction == "simplified" else "slice_scroll"):
                return _failure("slice change uses the wrong interaction input")
            axis = str(event.get("axis") or "")
            if axis not in {"x", "y", "z"}:
                return _failure("slice change has an invalid axis")
            index = int(event.get("index", -1))
            if not 0 <= index < count:
                return _failure("slice change leaves the linked volume")
            before = list(focus)
            axis_index = "xyz".index(axis)
            if index == before[axis_index]:
                return _failure("slice observation did not move the linked focus")
            focus[axis_index] = index
            if event.get("before") != before or event.get("focus") != focus:
                return _failure("slice change does not match the linked focus")
            expected_views = {view: _slice_records(public_state, focus, view) for view in VIEWS}
            if event.get("views") != expected_views or str(event.get("digest") or "") != _views_digest(public_state, focus):
                return _failure("slice records do not match the submitted linked views")
            expected_topology = _topology_digest(public_state, focus, current_edges)
            if str(event.get("topology") or "") != expected_topology:
                return _failure("linked views do not show the current regenerated topology")
            expected_inspection = "after_edit" if inspection_required else "initial"
            if str(event.get("inspection") or "") != expected_inspection:
                return _failure("slice observation is not connected to the current repair state")
            if inspection_required:
                post_edit_inspections += 1
                inspection_required = False
            slice_observations.add(expected_topology)
        elif kind == "orbit":
            source = "orbit_controls" if expected_interaction == "simplified" else "orbit_drag"
            if event.get("source") != source:
                return _failure("orbit uses the wrong interaction input")
            before = [_round(yaw), _round(pitch)]
            if event.get("before") != before:
                return _failure("orbit starts from the wrong camera state")
            if expected_interaction == "simplified":
                direction = str(event.get("direction") or "")
                deltas = {"left": (-0.25, 0.0), "right": (0.25, 0.0), "up": (0.0, -0.18), "down": (0.0, 0.18)}
                if direction not in deltas:
                    return _failure("orbit control direction is invalid")
                delta_yaw, delta_pitch = deltas[direction]
            else:
                try:
                    delta_yaw, delta_pitch = float(event.get("dx")) * 0.012, float(event.get("dy")) * 0.008
                except (TypeError, ValueError):
                    return _failure("mesh orbit drag is missing movement")
                if abs(delta_yaw) + abs(delta_pitch) < 0.01:
                    return _failure("mesh orbit drag did not move the camera")
            yaw = _round(yaw + delta_yaw)
            pitch = _round(max(-1.0, min(1.0, pitch + delta_pitch)))
            if event.get("after") != [_round(yaw), _round(pitch)]:
                return _failure("orbit camera state was not replayed")
            orbit_actions += 1
        elif kind == "select_segment":
            if expected_interaction != "simplified" or event.get("source") != "segment_palette":
                return _failure("segment selection is not a simplified-surface action")
            if inspection_required:
                return _failure("inspect the regenerated topology before selecting the next repair")
            node_id = str(event.get("node_id") or "")
            if node_id not in node_map:
                return _failure("segment selection names an unknown segment")
            selected.add(node_id)
        elif kind == "merge":
            expected_source = "merge_button" if expected_interaction == "simplified" else "mesh_drag_merge"
            if event.get("source") != expected_source:
                return _failure("merge uses the wrong interaction input")
            if inspection_required:
                return _failure("inspect the regenerated topology before making another repair")
            left, right = str(event.get("a") or ""), str(event.get("b") or "")
            pair = _edge(left, right)
            if left not in node_map or right not in node_map or left == right:
                return _failure("merge names an invalid pair of segments")
            if expected_interaction == "simplified":
                if left not in selected or right not in selected:
                    return _failure("simplified merge was not made from the selected segments")
            else:
                if _nearest_node(public_state, event.get("start"), yaw, pitch) != left or _nearest_node(public_state, event.get("end"), yaw, pitch) != right:
                    return _failure("mesh merge endpoints do not hit the named visible segments")
            if pair not in missing_edges:
                return _failure("merge would make a false connection")
            if pair in current_edges:
                return _failure("merge repeats an existing connection")
            current_edges.add(pair)
            selected.clear()
            repair_actions += 1
            inspection_required = True
        elif kind == "seed":
            expected_source = "seed_palette" if expected_interaction == "simplified" else "slice_seed"
            if event.get("source") != expected_source:
                return _failure("split seed uses the wrong interaction input")
            if inspection_required:
                return _failure("inspect the regenerated topology before placing the next split seed")
            color = str(event.get("color") or "")
            node_id = str(event.get("node_id") or "")
            view = str(event.get("view") or "")
            if color not in {"red", "green"} or node_id not in node_map or view not in VIEWS:
                return _failure("split seed is incomplete")
            records = _slice_records(public_state, focus, view)
            record = next((item for item in records if item["id"] == node_id), None)
            if record is None:
                return _failure("split seed is not visible in the selected slice")
            if expected_interaction == "full" and not _same_point(event.get("screen"), _screen_for_record(public_state, view, record), 5.0):
                return _failure("slice seed coordinate misses the visible segment")
            seeds[color] = node_id
        elif kind == "split":
            if event.get("source") != "split_button":
                return _failure("split action has no visible cut control")
            red, green = str(event.get("red") or ""), str(event.get("green") or "")
            pair = _edge(red, green)
            if seeds.get("red") != red or seeds.get("green") != green:
                return _failure("split does not use the two visible opposite-colour seeds")
            if pair not in false_edges or pair not in current_edges:
                return _failure("cut does not remove a constructed false join")
            current_edges.remove(pair)
            seeds.clear()
            repair_actions += 1
            inspection_required = True
        elif kind == "submit":
            if number != len(events) or submitted:
                return _failure("certification must be the final event")
            submitted = True
            if event.get("source") != "certify_button":
                return _failure("certification was not made through the visible button")
        else:
            return _failure(f"unknown repair event: {kind}")
    if not submitted:
        return _failure("repair transcript has no certification event")
    if inspection_required:
        return _failure("inspect the regenerated topology before certification")
    if repair_actions != int(requirements.get("repair_count") or 0):
        return _failure("the repair transcript did not account for every constructed edit")
    if post_edit_inspections < repair_actions:
        return _failure("each topology edit must be followed by a linked-view inspection")
    if current_edges != true_edges:
        return _failure("certification topology does not match the labelled reconstruction")
    target_nodes = {str(item) for item in ground_truth.get("target_nodes") or []}
    if _component(current_edges, str(public_state.get("seed_segment_id") or "")) != target_nodes:
        return _failure("the marked fibre still absorbs a neighbouring component")
    if {_edge(item[0], item[1]) for item in payload.get("final_edges") or []} != current_edges:
        return _failure("submitted final topology disagrees with the replay")
    if payload.get("focus") != focus or payload.get("orbit") != [_round(yaw), _round(pitch)]:
        return _failure("submitted final view state disagrees with the replay")
    expected_summary = {
        "slice_observations": len(slice_observations),
        "post_edit_inspections": post_edit_inspections,
        "orbit_actions": orbit_actions,
        "component_size": len(target_nodes),
    }
    if payload.get("summary") != expected_summary:
        return _failure("submitted repair summary disagrees with the replay")
    return {"graded": True, "passed": True, "score": 100, "feedback": f"branch topology repaired: {len(target_nodes)} marked segments; {post_edit_inspections} post-edit inspections; {orbit_actions} orbit actions"}


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    # The endpoint is opt-in and is never used by ordinary browser play. Keep
    # it deliberately useful for local wiring checks while not putting truth
    # into the public state.
    del public_state
    return {"target_nodes": ground_truth.get("target_nodes") or [], "missing_edges": ground_truth.get("missing_edges") or [], "false_edges": ground_truth.get("false_edges") or []}
