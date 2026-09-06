from __future__ import annotations

import copy
import math
from collections import Counter, deque
from typing import Any


MECHANIC_ID = "charter_of_the_nine_cantons"
GUILD_IDS = ("gilt", "tide", "plum")
CANTON_IDS = tuple(range(9))


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


def _connected(canton: int, assignment: dict[str, int], adjacency: dict[str, list[str]]) -> bool:
    members = {parcel_id for parcel_id, owner in assignment.items() if owner == canton}
    if not members:
        return False
    seen = {next(iter(members))}
    queue = deque(seen)
    while queue:
        current = queue.popleft()
        for neighbor in adjacency[current]:
            if neighbor in members and neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return seen == members


def evaluate_assignment(
    assignment: dict[str, int], parties: dict[str, str], adjacency: dict[str, list[str]],
    ideal_population: int, tolerance: int, target_split: dict[str, int],
) -> dict[str, Any]:
    cantons = []
    seat_split = {guild_id: 0 for guild_id in GUILD_IDS}
    for canton in CANTON_IDS:
        members = [parcel_id for parcel_id, owner in assignment.items() if owner == canton]
        counts = Counter(parties[parcel_id] for parcel_id in members)
        ordered = counts.most_common()
        winner = ordered[0][0] if ordered and (len(ordered) == 1 or ordered[0][1] > ordered[1][1]) else "tie"
        if winner != "tie":
            seat_split[winner] += 1
        cantons.append({
            "id": canton,
            "population": len(members),
            "population_ok": abs(len(members) - ideal_population) <= tolerance,
            "connected": _connected(canton, assignment, adjacency),
            "guild_counts": {guild_id: counts.get(guild_id, 0) for guild_id in GUILD_IDS},
            "winner": winner,
        })
    completed = all(item["population_ok"] and item["connected"] for item in cantons) and seat_split == target_split
    return {"cantons": cantons, "seat_split": seat_split, "completed": completed}


def _shared_edge(left: list[list[float]], right: list[list[float]]) -> bool:
    def key(point: list[float]) -> tuple[float, float]:
        return round(float(point[0]), 3), round(float(point[1]), 3)
    return len({key(point) for point in left} & {key(point) for point in right}) >= 2


def _point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    inside = False
    count = len(polygon)
    for index in range(count):
        ax, ay = map(float, polygon[index])
        bx, by = map(float, polygon[(index + 1) % count])
        cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax)
        if abs(cross) <= 0.05 and min(ax, bx) - 0.05 <= x <= max(ax, bx) + 0.05 and min(ay, by) - 0.05 <= y <= max(ay, by) + 0.05:
            return True
        intersects = (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / ((by - ay) or 1e-12) + ax
        if intersects:
            inside = not inside
    return inside


def _gesture(event: dict[str, Any], polygons: dict[str, list[list[float]]], path: list[str]) -> None:
    gesture = event.get("gesture")
    if not isinstance(gesture, dict):
        raise ValueError("brush stroke lacks pointer geometry")
    for field in ("start_u", "start_v", "end_u", "end_v", "travel_px"):
        value = gesture.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError("brush stroke has invalid pointer geometry")
    if not all(0 <= float(gesture[field]) <= 1 for field in ("start_u", "start_v", "end_u", "end_v")):
        raise ValueError("brush stroke left the visible map")
    minimum_travel = max(8.0, 12.0 * (len(set(path)) - 1))
    if float(gesture["travel_px"]) < minimum_travel:
        raise ValueError("brush stroke did not travel far enough")
    samples = gesture.get("sample_count")
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 1:
        raise ValueError("brush stroke has no delivered pointer sample")
    start = (float(gesture["start_u"]) * 1000.0, float(gesture["start_v"]) * 600.0)
    end = (float(gesture["end_u"]) * 1000.0, float(gesture["end_v"]) * 600.0)
    if not _point_in_polygon(*start, polygons[path[0]]):
        raise ValueError("brush stroke start does not land in its first parcel")
    if not _point_in_polygon(*end, polygons[path[-1]]):
        raise ValueError("brush stroke end does not land in its final parcel")


def _contract(truth: dict[str, Any], public: dict[str, Any]):
    required_equal = (
        "parcels", "adjacency", "initial_assignment", "guilds", "canton_colors",
        "target_seat_split", "ideal_population", "population_tolerance", "parameters",
    )
    for key in required_equal:
        if public.get(key) != truth.get(key):
            raise ValueError(f"public {key} differs from generated truth")
    if public.get("control_condition") != truth.get("control_condition"):
        raise ValueError("public controls differ from generated truth")
    if "target_assignment" in public or "displaced_parcels" in public:
        raise ValueError("private solution data leaked into public state")
    parcels = truth.get("parcels")
    adjacency = truth.get("adjacency")
    initial = truth.get("initial_assignment")
    target = truth.get("target_assignment")
    parameters = truth.get("parameters")
    if not isinstance(parcels, list) or not isinstance(adjacency, dict) or not isinstance(initial, dict) or not isinstance(target, dict) or not isinstance(parameters, dict):
        raise ValueError("generated charter contract is incomplete")
    parcel_map = {str(parcel.get("id") or ""): parcel for parcel in parcels if isinstance(parcel, dict)}
    if len(parcel_map) != len(parcels) or set(parcel_map) != set(adjacency) or set(initial) != set(parcel_map) or set(target) != set(parcel_map):
        raise ValueError("parcel identities disagree across the contract")
    polygons: dict[str, list[list[float]]] = {}
    parties: dict[str, str] = {}
    for parcel_id, parcel in parcel_map.items():
        polygon, guild = parcel.get("polygon"), parcel.get("guild")
        if not isinstance(polygon, list) or len(polygon) < 3 or any(not isinstance(point, list) or len(point) != 2 for point in polygon):
            raise ValueError("parcel polygon is invalid")
        if guild not in GUILD_IDS or parcel.get("households") != 1:
            raise ValueError("parcel household record is invalid")
        polygons[parcel_id] = polygon
        parties[parcel_id] = guild
    for parcel_id, neighbors in adjacency.items():
        if not isinstance(neighbors, list) or parcel_id in neighbors or len(neighbors) != len(set(neighbors)):
            raise ValueError("parcel adjacency is malformed")
        for neighbor in neighbors:
            if parcel_id not in adjacency.get(neighbor, []):
                raise ValueError("parcel adjacency is not symmetric")
            if not _shared_edge(polygons[parcel_id], polygons[neighbor]):
                raise ValueError("graded neighbors do not share a visible border")
    if any(owner not in CANTON_IDS for owner in [*initial.values(), *target.values()]):
        raise ValueError("assignment names an invalid canton")
    ideal = truth.get("ideal_population")
    tolerance = truth.get("population_tolerance")
    target_split = truth.get("target_seat_split")
    if isinstance(ideal, bool) or not isinstance(ideal, int) or not isinstance(tolerance, int) or target_split != {"gilt": 5, "tide": 2, "plum": 2}:
        raise ValueError("charter targets are invalid")
    target_stats = evaluate_assignment(target, parties, adjacency, ideal, tolerance, target_split)
    if not target_stats["completed"] or target_stats != truth.get("target_stats"):
        raise ValueError("private reference partition does not satisfy the charter")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    if interaction not in {"simplified", "full"}:
        raise ValueError("interaction mode is invalid")
    budget = parameters.get("change_budget")
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 1:
        raise ValueError("change budget is invalid")
    minimum_brush_changes = parameters.get("minimum_brush_changes", 2)
    minimum_brush_path = parameters.get("minimum_brush_path", 4)
    if (
        isinstance(minimum_brush_changes, bool) or not isinstance(minimum_brush_changes, int)
        or not 1 <= minimum_brush_changes <= budget
        or isinstance(minimum_brush_path, bool) or not isinstance(minimum_brush_path, int)
        or not 2 <= minimum_brush_path <= len(parcel_map)
    ):
        raise ValueError("full brush requirements are invalid")
    return (
        parcels, adjacency, polygons, parties, copy.deepcopy(initial), ideal,
        tolerance, target_split, interaction, budget,
        minimum_brush_changes, minimum_brush_path,
    )


def _validate_change(change: dict[str, Any], assignment: dict[str, int], parcel_ids: set[str], expected_canton: int | None = None) -> tuple[str, int]:
    if not isinstance(change, dict):
        raise ValueError("assignment change is not an object")
    parcel_id = str(change.get("parcel_id") or "")
    to_canton = change.get("to_canton")
    from_canton = change.get("from_canton")
    if parcel_id not in parcel_ids or isinstance(to_canton, bool) or not isinstance(to_canton, int) or to_canton not in CANTON_IDS:
        raise ValueError("assignment change names an invalid parcel or canton")
    if from_canton != assignment[parcel_id] or to_canton == from_canton:
        raise ValueError("assignment change disagrees with current parcel ownership")
    if expected_canton is not None and to_canton != expected_canton:
        raise ValueError("brush stroke changes parcels to more than one canton")
    return parcel_id, to_canton


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    binding = _bind(payload, truth, public)
    if binding:
        return _fail(binding)
    try:
        (
            _parcels, adjacency, polygons, parties, assignment, ideal, tolerance,
            target_split, interaction, budget, minimum_brush_changes,
            minimum_brush_path,
        ) = _contract(truth, public)
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"invalid charter contract: {exc}")
    if payload.get("interaction_mode") != interaction:
        return _fail("submitted interaction mode differs from task condition")
    events = payload.get("events")
    if not isinstance(events, list) or len(events) > budget * 3:
        return _fail("assignment transcript is too long for the task budget")
    parcel_ids = set(assignment)
    history: list[tuple[dict[str, int], int, bool]] = []
    spent = 0
    active_qualified_brushes = 0
    try:
        for sequence, event in enumerate(events, 1):
            if not isinstance(event, dict) or event.get("sequence") != sequence:
                raise ValueError(f"event {sequence} has an invalid sequence")
            event_type = event.get("type")
            if event_type == "undo":
                if event.get("input_source") != "undo_button" or not history:
                    raise ValueError(f"event {sequence} has an invalid undo")
                assignment, cost, qualified_brush = history.pop()
                spent -= cost
                if qualified_brush:
                    active_qualified_brushes -= 1
                continue
            before = copy.deepcopy(assignment)
            qualified_brush = False
            if interaction == "simplified":
                if event_type != "assign" or event.get("input_source") != "canton_proxy_button" or "gesture" in event:
                    raise ValueError(f"event {sequence} uses the wrong input surface")
                parcel_id, to_canton = _validate_change(event, assignment, parcel_ids)
                changes = [(parcel_id, to_canton)]
                cost = 1
            else:
                if event_type != "stroke" or event.get("input_source") != "map_brush_drag":
                    raise ValueError(f"event {sequence} uses the wrong input surface")
                brush_canton = event.get("brush_canton")
                path, raw_changes = event.get("path"), event.get("changes")
                if isinstance(brush_canton, bool) or not isinstance(brush_canton, int) or brush_canton not in CANTON_IDS:
                    raise ValueError("brush stroke names an invalid canton")
                if not isinstance(path, list) or not path or any(parcel_id not in parcel_ids for parcel_id in path):
                    raise ValueError("brush stroke path is invalid")
                if any(left != right and right not in adjacency[left] for left, right in zip(path, path[1:])):
                    raise ValueError("brush stroke jumps across parcels without a shared border")
                if not isinstance(raw_changes, list) or not raw_changes:
                    raise ValueError("brush stroke changes no parcels")
                if len({str(change.get("parcel_id") or "") for change in raw_changes if isinstance(change, dict)}) != len(raw_changes):
                    raise ValueError("brush stroke changes one parcel more than once")
                changes = []
                for change in raw_changes:
                    parcel_id, to_canton = _validate_change(change, assignment, parcel_ids, brush_canton)
                    if parcel_id not in path:
                        raise ValueError("brush change is absent from its visible path")
                    assignment[parcel_id] = to_canton
                    changes.append((parcel_id, to_canton))
                assignment = before
                _gesture(event, polygons, path)
                cost = len(changes)
                qualified_brush = (
                    len(set(path)) >= minimum_brush_path
                    and len(changes) >= minimum_brush_changes
                )
            if spent + cost > budget:
                raise ValueError(f"event {sequence} exceeds the parcel-change budget")
            history.append((copy.deepcopy(before), cost, qualified_brush))
            for parcel_id, to_canton in changes:
                assignment[parcel_id] = to_canton
            spent += cost
            if qualified_brush:
                active_qualified_brushes += 1
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"charter replay rejected: {exc}")
    stats = evaluate_assignment(assignment, parties, adjacency, ideal, tolerance, target_split)
    if payload.get("final_assignment") != assignment:
        return _fail("submitted partition differs from the visible-action transcript")
    if payload.get("metrics") != stats:
        return _fail("submitted charter metrics disagree with independent replay")
    if payload.get("completed") is not stats["completed"]:
        return _fail("submitted completion flag disagrees with the charter checks")
    if stats["completed"] and interaction == "full" and active_qualified_brushes < 1:
        return _fail(
            "full interaction requires one active brush stroke through at least "
            f"{minimum_brush_path} joined parcels that changes at least "
            f"{minimum_brush_changes} parcels"
        )
    population_ok = sum(1 for item in stats["cantons"] if item["population_ok"])
    connected = sum(1 for item in stats["cantons"] if item["connected"])
    split = "/".join(str(stats["seat_split"][guild_id]) for guild_id in GUILD_IDS)
    return {
        "graded": True,
        "passed": stats["completed"],
        "feedback": f"replayed {len(events)} visible actions and {spent}/{budget} active parcel changes; populations {population_ok}/9, connected {connected}/9, holdings {split} against 5/2/2; consequential brushes {active_qualified_brushes}/1" if interaction == "full" else f"replayed {len(events)} visible actions and {spent}/{budget} active parcel changes; populations {population_ok}/9, connected {connected}/9, holdings {split} against 5/2/2",
    }
