from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "chain_of_appetite"
DRAG_TARGET_RADIUS_CELLS = 0.4
MIN_DRAG_TRAVEL_PX = 32.0
MIN_DRAG_SAMPLES = 3
COORDINATE_SERIALIZATION_EPSILON = 0.000001


def _fail(feedback: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": feedback}


def _bind(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> str | None:
    if str(payload.get("mechanic_id") or "") != MECHANIC_ID:
        return "payload mechanic mismatch"
    if str(truth.get("mechanic_id") or "") != MECHANIC_ID:
        return "ground-truth mechanic mismatch"
    if str(public.get("mechanic_id") or "") != MECHANIC_ID:
        return "public-state mechanic mismatch"
    challenge_id = str(truth.get("challenge_id") or "")
    if not challenge_id or str(payload.get("challenge_id") or "") != challenge_id:
        return "stale challenge"
    if str(public.get("challenge_id") or "") != challenge_id:
        return "public-state challenge mismatch"
    task_id = str(truth.get("task_id") or "")
    if not task_id or str(payload.get("task_id") or "") != task_id:
        return "payload task mismatch"
    if str(public.get("task_id") or "") != task_id:
        return "public-state task mismatch"
    return None


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _monster(value: Any, grid_size: int, colors: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("monster must be an object")
    monster_id = str(value.get("id") or "")
    if not monster_id:
        raise ValueError("monster id is missing")
    row = _integer(value.get("row"), "monster row")
    column = _integer(value.get("column"), "monster column")
    if not 0 <= row < grid_size or not 0 <= column < grid_size:
        raise ValueError("monster lies outside the tray")
    body = str(value.get("body") or "")
    mouth = str(value.get("mouth") or "")
    if body not in colors or mouth not in colors:
        raise ValueError("monster colour is outside the task palette")
    return {
        "id": monster_id,
        "row": row,
        "column": column,
        "body": body,
        "mouth": mouth,
        "shape": _integer(value.get("shape", 0), "monster shape"),
        "horns": _integer(value.get("horns", 0), "monster horns"),
        "eyes": _integer(value.get("eyes", 2), "monster eyes"),
        "mark": _integer(value.get("mark", 0), "monster mark"),
        "tilt": _integer(value.get("tilt", 0), "monster tilt"),
    }


def _monsters(value: Any, grid_size: int, colors: set[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("monster list is missing")
    monsters = [_monster(item, grid_size, colors) for item in value]
    ids = [monster["id"] for monster in monsters]
    positions = [(monster["row"], monster["column"]) for monster in monsters]
    if len(ids) != len(set(ids)):
        raise ValueError("monster ids are not unique")
    if len(positions) != len(set(positions)):
        raise ValueError("two monsters occupy one tray cell")
    return sorted(monsters, key=lambda item: item["id"])


def _clear_line(actor: dict[str, Any], victim: dict[str, Any], monsters: list[dict[str, Any]]) -> bool:
    row_a, column_a = actor["row"], actor["column"]
    row_b, column_b = victim["row"], victim["column"]
    if row_a != row_b and column_a != column_b:
        return False
    occupied = {
        (monster["row"], monster["column"])
        for monster in monsters
        if monster["id"] not in {actor["id"], victim["id"]}
    }
    if row_a == row_b:
        return not any((row_a, column) in occupied for column in range(min(column_a, column_b) + 1, max(column_a, column_b)))
    return not any((row, column_a) in occupied for row in range(min(row_a, row_b) + 1, max(row_a, row_b)))


def _legal_moves(monsters: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return sorted(
        (actor["id"], victim["id"])
        for actor in monsters
        for victim in monsters
        if actor["id"] != victim["id"]
        and actor["mouth"] == victim["body"]
        and _clear_line(actor, victim, monsters)
    )


def _apply(monsters: list[dict[str, Any]], actor_id: str, victim_id: str) -> list[dict[str, Any]]:
    if (actor_id, victim_id) not in _legal_moves(monsters):
        raise ValueError("move is not a legal mouth-to-body jump")
    copied = [dict(monster) for monster in monsters]
    actor = next(monster for monster in copied if monster["id"] == actor_id)
    victim = next(monster for monster in copied if monster["id"] == victim_id)
    actor["row"], actor["column"] = victim["row"], victim["column"]
    actor["mouth"] = victim["mouth"]
    return sorted((monster for monster in copied if monster["id"] != victim_id), key=lambda item: item["id"])


def _coordinate(value: Any, label: str, grid_size: int) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} must be a two-item list")
    row = _integer(value[0], f"{label} row")
    column = _integer(value[1], f"{label} column")
    if not 0 <= row < grid_size or not 0 <= column < grid_size:
        raise ValueError(f"{label} lies outside the tray")
    return row, column


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite")
    return float(value)


def _check_drag(
    event: dict[str, Any],
    actor: dict[str, Any],
    victim: dict[str, Any],
    grid_size: int,
    geometry: dict[str, Any],
) -> str | None:
    gesture = event.get("gesture")
    if not isinstance(gesture, dict):
        return "full interaction is missing drag geometry"
    try:
        start_u = _finite_number(gesture.get("start_u"), "drag start u")
        start_v = _finite_number(gesture.get("start_v"), "drag start v")
        end_u = _finite_number(gesture.get("end_u"), "drag end u")
        end_v = _finite_number(gesture.get("end_v"), "drag end v")
        travel_px = _finite_number(gesture.get("travel_px"), "drag travel")
        sample_count = _integer(gesture.get("sample_count"), "drag sample count")
    except ValueError as exc:
        return str(exc)
    observed = (start_u, start_v, end_u, end_v)
    if (
        not all(0 <= value <= 1 for value in observed)
        or travel_px < geometry["min_drag_travel_px"]
        or sample_count < geometry["min_drag_samples"]
    ):
        return "drag transcript is too short to represent direct manipulation"
    radius = geometry["drag_target_radius_cells"] / grid_size
    start_center = ((actor["column"] + 0.5) / grid_size, (actor["row"] + 0.5) / grid_size)
    end_center = ((victim["column"] + 0.5) / grid_size, (victim["row"] + 0.5) / grid_size)
    if (
        math.hypot(start_u - start_center[0], start_v - start_center[1])
        > radius + COORDINATE_SERIALIZATION_EPSILON
        or math.hypot(end_u - end_center[0], end_v - end_center[1])
        > radius + COORDINATE_SERIALIZATION_EPSILON
    ):
        return "drag endpoints lie outside the visible actor or victim target"
    return None


def _contract(
    truth: dict[str, Any], public: dict[str, Any]
) -> tuple[list[dict[str, Any]], int, set[str], dict[str, Any]]:
    parameters = truth.get("parameters")
    if not isinstance(parameters, dict) or parameters != public.get("parameters"):
        raise ValueError("public difficulty parameters differ from hidden contract")
    grid_size = _integer(parameters.get("grid_size"), "grid size")
    if not 3 <= grid_size <= 5:
        raise ValueError("grid size is outside limits")
    colors_value = public.get("colors")
    if not isinstance(colors_value, list) or not 3 <= len(colors_value) <= 6 or not all(isinstance(item, str) for item in colors_value):
        raise ValueError("public colour list is malformed")
    colors = set(colors_value)
    hidden = _monsters(truth.get("initial_monsters"), grid_size, colors)
    visible = _monsters(public.get("monsters"), grid_size, colors)
    if hidden != visible:
        raise ValueError("public creatures differ from hidden contract")
    if len(hidden) != _integer(parameters.get("monster_count"), "monster count"):
        raise ValueError("monster count differs from difficulty contract")
    geometry = truth.get("interaction_geometry")
    if not isinstance(geometry, dict) or geometry != public.get("interaction_geometry"):
        raise ValueError("public interaction geometry differs from hidden contract")
    if geometry.get("drag_target_shape") != "circle":
        raise ValueError("drag target shape is not supported")
    radius = _finite_number(geometry.get("drag_target_radius_cells"), "drag target radius")
    min_travel = _finite_number(geometry.get("min_drag_travel_px"), "minimum drag travel")
    min_samples = _integer(geometry.get("min_drag_samples"), "minimum drag samples")
    if (
        radius != DRAG_TARGET_RADIUS_CELLS
        or min_travel != MIN_DRAG_TRAVEL_PX
        or min_samples != MIN_DRAG_SAMPLES
    ):
        raise ValueError("interaction geometry is outside the implemented visible-target contract")
    return hidden, grid_size, colors, {
        "drag_target_radius_cells": radius,
        "min_drag_travel_px": min_travel,
        "min_drag_samples": min_samples,
    }


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    binding_error = _bind(payload, truth, public)
    if binding_error:
        return _fail(binding_error)
    truth_condition = truth.get("control_condition")
    if truth_condition != public.get("control_condition"):
        return _fail("public control condition differs from appetite contract")
    expected_interaction = str((truth_condition or {}).get("interaction") or "simplified")
    expected_source = {"simplified": "paired_clicks", "full": "creature_drag"}.get(expected_interaction)
    if expected_source is None:
        return _fail("appetite interaction condition is invalid")
    if str(payload.get("interaction_mode") or "") != expected_interaction:
        return _fail("submitted interaction mode does not match the task")
    try:
        monsters, grid_size, colors, geometry = _contract(truth, public)
    except (TypeError, ValueError) as exc:
        return _fail(f"invalid appetite contract: {exc}")

    events = payload.get("events")
    if not isinstance(events, list) or len(events) > len(monsters) - 1:
        return _fail("meal transcript is missing or outside limits")
    terminal = False
    for sequence, event in enumerate(events, start=1):
        if terminal:
            return _fail("meal transcript continues after a terminal outcome")
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return _fail(f"meal {sequence} has an invalid sequence")
        if event.get("input_source") != expected_source:
            return _fail(f"meal {sequence} uses the wrong interaction input")
        actor_id = str(event.get("actor_id") or "")
        victim_id = str(event.get("victim_id") or "")
        before = {monster["id"]: monster for monster in monsters}
        actor = before.get(actor_id)
        victim = before.get(victim_id)
        if actor is None or victim is None or actor_id == victim_id:
            return _fail(f"meal {sequence} names an unavailable creature")
        try:
            event_from = _coordinate(event.get("from"), "meal origin", grid_size)
            event_to = _coordinate(event.get("to"), "meal destination", grid_size)
        except ValueError as exc:
            return _fail(f"meal {sequence} is malformed: {exc}")
        if event_from != (actor["row"], actor["column"]) or event_to != (victim["row"], victim["column"]):
            return _fail(f"meal {sequence} coordinates do not match replay")
        if expected_source == "creature_drag":
            drag_error = _check_drag(event, actor, victim, grid_size, geometry)
            if drag_error:
                return _fail(f"meal {sequence}: {drag_error}")
        expected_visual = {
            "actor_body": actor["body"],
            "mouth_before": actor["mouth"],
            "victim_body": victim["body"],
            "inherited_mouth": victim["mouth"],
        }
        for field, value in expected_visual.items():
            if event.get(field) != value:
                return _fail(f"meal {sequence} has inconsistent {field}")
        try:
            monsters = _apply(monsters, actor_id, victim_id)
        except ValueError as exc:
            return _fail(f"meal {sequence} is illegal: {exc}")
        legal_after = _legal_moves(monsters)
        outcome = "solved" if len(monsters) == 1 else "deadlock" if not legal_after else "running"
        if event.get("remaining_after") != len(monsters) or event.get("outcome") != outcome:
            return _fail(f"meal {sequence} reports the wrong resulting state")
        terminal = outcome != "running"

    try:
        submitted_final = _monsters(payload.get("final_monsters"), grid_size, colors)
    except (TypeError, ValueError) as exc:
        return _fail(f"submitted final tray is malformed: {exc}")
    if submitted_final != monsters:
        return _fail("submitted final tray does not match meal replay")
    if payload.get("remaining") != len(monsters):
        return _fail("submitted survivor count does not match replay")
    completed = payload.get("completed") is True
    passed = completed and len(monsters) == 1 and len(events) == len((truth.get("initial_monsters") or [])) - 1
    if completed and not passed:
        return _fail("completion was claimed without exactly one replayed survivor")
    status = "one survivor" if len(monsters) == 1 else "deadlock" if not _legal_moves(monsters) else "chain still active"
    return {
        "graded": True,
        "passed": passed,
        "feedback": f"replayed {len(events)} meal(s); {len(monsters)} creature(s) remain; {status}",
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    return {
        "solution_moves": ground_truth.get("solution_moves") or [],
        "failure_moves": ground_truth.get("failure_moves") or [],
        "instruction": "Perform the listed actor/victim meals in order, then seal the lone survivor.",
        "answers": [],
    }
