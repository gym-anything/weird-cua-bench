from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "crackglaze_crossing"


def _fail(message: str, score: int = 0) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": score, "feedback": message}


def _identity(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> str | None:
    if any(str(value.get("mechanic_id") or "") != MECHANIC_ID for value in (payload, truth, public)):
        return "mechanic mismatch"
    for key in ("task_id", "challenge_id"):
        expected = str(truth.get(key) or "")
        if not expected or str(payload.get(key) or "") != expected or str(public.get(key) or "") != expected:
            return f"stale or mismatched {key}"
    return None


def _finite(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))


def _point(value: Any) -> list[float]:
    if not isinstance(value, list) or len(value) != 2 or any(not _finite(item) for item in value):
        raise ValueError("tile click point is malformed")
    point = [float(value[0]), float(value[1])]
    if any(item < -0.02 or item > 1.02 for item in point):
        raise ValueError("tile click point is outside the board")
    return point


def _cell_rect(cell: dict[str, Any], rows: int, columns: int) -> list[float]:
    return [
        float(cell["column"]) / columns,
        float(cell["row"]) / rows,
        1.0 / columns,
        1.0 / rows,
    ]


def _inside(point: list[float], rect: list[float], tolerance: float = 0.008) -> bool:
    x, y, width, height = rect
    return x - tolerance <= point[0] <= x + width + tolerance and y - tolerance <= point[1] <= y + height + tolerance


def _direction(first: dict[str, Any], second: dict[str, Any]) -> str:
    delta = (int(second["row"]) - int(first["row"]), int(second["column"]) - int(first["column"]))
    return {(-1, 0): "up", (1, 0): "down", (0, -1): "left", (0, 1): "right"}.get(delta, "")


def _contract(truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    shared_keys = (
        "rows", "columns", "cells", "neighbors", "start_id", "exit_id", "lantern_ids",
        "glazes", "fuse_lengths", "parameters", "board_region",
    )
    for key in shared_keys:
        if truth.get(key) != public.get(key):
            raise ValueError(f"public and hidden {key} disagree")
    if truth.get("control_condition") != public.get("control_condition"):
        raise ValueError("control condition disagrees")
    parameters = truth.get("parameters")
    condition = truth.get("control_condition")
    if not isinstance(parameters, dict):
        raise ValueError("difficulty parameters are missing")
    if condition is not None and condition.get("difficulty_parameters") != parameters:
        raise ValueError("condition parameters disagree")
    interaction = str((condition or {}).get("interaction") or "full")
    if interaction not in {"simplified", "full"}:
        raise ValueError("interaction mode is invalid")
    rows, columns = truth.get("rows"), truth.get("columns")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in (rows, columns)) or not (8 <= rows <= 10 and 5 <= columns <= 7):
        raise ValueError("board dimensions are malformed")
    cells_value = truth.get("cells")
    if not isinstance(cells_value, list) or len(cells_value) < 7:
        raise ValueError("floor cells are missing")
    cells: dict[str, dict[str, Any]] = {}
    coordinates: set[tuple[int, int]] = set()
    glaze_ids = {str(item.get("id") or "") for item in truth.get("glazes") or [] if isinstance(item, dict)}
    fuses = truth.get("fuse_lengths")
    if not glaze_ids or not isinstance(fuses, dict) or set(fuses) != glaze_ids:
        raise ValueError("glaze fuse contract is malformed")
    for glaze_id, length in fuses.items():
        if isinstance(length, bool) or not isinstance(length, int) or length < 3:
            raise ValueError(f"glaze {glaze_id} has an invalid fuse")
    for cell in cells_value:
        if not isinstance(cell, dict):
            raise ValueError("floor cell is malformed")
        cell_id = str(cell.get("id") or "")
        row, column = cell.get("row"), cell.get("column")
        if (
            not cell_id or cell_id in cells
            or isinstance(row, bool) or not isinstance(row, int) or not 0 <= row < rows
            or isinstance(column, bool) or not isinstance(column, int) or not 0 <= column < columns
            or (row, column) in coordinates
            or cell.get("glaze") not in glaze_ids
            or any(not isinstance(cell.get(flag), bool) for flag in ("under_gallery", "lantern", "start", "exit"))
        ):
            raise ValueError("floor cell identity or geometry is malformed")
        cells[cell_id] = cell
        coordinates.add((row, column))
    start_id, exit_id = str(truth.get("start_id") or ""), str(truth.get("exit_id") or "")
    lantern_ids = truth.get("lantern_ids")
    if start_id not in cells or exit_id not in cells or start_id == exit_id:
        raise ValueError("start or exit is malformed")
    if [cell_id for cell_id, cell in cells.items() if cell["start"]] != [start_id]:
        raise ValueError("visible start marker disagrees")
    if [cell_id for cell_id, cell in cells.items() if cell["exit"]] != [exit_id]:
        raise ValueError("visible exit marker disagrees")
    if not isinstance(lantern_ids, list) or not lantern_ids or len(lantern_ids) != len(set(lantern_ids)):
        raise ValueError("lantern set is malformed")
    if set(lantern_ids) != {cell_id for cell_id, cell in cells.items() if cell["lantern"]}:
        raise ValueError("visible lanterns disagree")
    neighbors = truth.get("neighbors")
    if not isinstance(neighbors, dict) or set(neighbors) != set(cells):
        raise ValueError("floor adjacency is malformed")
    for cell_id, values in neighbors.items():
        if not isinstance(values, list) or len(values) != len(set(values)):
            raise ValueError("floor adjacency list is malformed")
        for other in values:
            if other not in cells or cell_id not in neighbors.get(other, []):
                raise ValueError("floor adjacency is not symmetric")
            if abs(cells[cell_id]["row"] - cells[other]["row"]) + abs(cells[cell_id]["column"] - cells[other]["column"]) != 1:
                raise ValueError("floor adjacency crosses non-neighboring geometry")
    return {
        "interaction": interaction,
        "rows": rows,
        "columns": columns,
        "cells": cells,
        "neighbors": neighbors,
        "start_id": start_id,
        "exit_id": exit_id,
        "lantern_ids": lantern_ids,
        "fuses": {cell_id: int(fuses[cell["glaze"]]) for cell_id, cell in cells.items()},
    }


def _snapshot(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "position": state["position"],
        "step_count": state["step"],
        "collected_lantern_ids": sorted(state["collected"]),
        "lit_at": {key: value for key, value in sorted(state["lit_at"].items())},
        "shattered_cell_ids": sorted(state["shattered"]),
        "status": state["status"],
    }


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    identity_error = _identity(payload, truth, public)
    if identity_error:
        return _fail(identity_error)
    try:
        contract = _contract(truth, public)
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"invalid Crackglaze contract: {exc}")
    interaction = contract["interaction"]
    if payload.get("interaction_mode") != interaction:
        return _fail("submitted interaction mode differs from task condition")
    events = payload.get("events")
    if not isinstance(events, list) or not events or len(events) > 160:
        return _fail("movement transcript is missing or oversized")
    state = {
        "position": contract["start_id"], "step": 0, "collected": set(), "lit_at": {},
        "shattered": set(), "status": "active",
    }
    if state["position"] in contract["lantern_ids"]:
        state["collected"].add(state["position"])
    terminal = False
    try:
        for sequence, event in enumerate(events, 1):
            if not isinstance(event, dict) or event.get("sequence") != sequence:
                raise ValueError(f"event {sequence} has an invalid sequence")
            if terminal:
                raise ValueError(f"event {sequence} occurs after a terminal state")
            if event.get("type") != "move":
                raise ValueError(f"event {sequence} has unknown type")
            origin = str(event.get("from") or "")
            destination = str(event.get("to") or "")
            if origin != state["position"] or destination not in contract["neighbors"].get(origin, []):
                raise ValueError(f"event {sequence} is not an adjacent move from the current tile")
            direction = _direction(contract["cells"][origin], contract["cells"][destination])
            if event.get("direction") != direction:
                raise ValueError(f"event {sequence} reports the wrong direction")
            if interaction == "full":
                if event.get("input_source") != "tile_click" or not _inside(
                    _point(event.get("point")),
                    _cell_rect(contract["cells"][destination], contract["rows"], contract["columns"]),
                ):
                    raise ValueError(f"event {sequence} misses the visible destination tile")
            elif event.get("input_source") != "direction_button" or "point" in event:
                raise ValueError(f"event {sequence} uses the wrong simplified input surface")

            next_step = state["step"] + 1
            if origin not in state["lit_at"]:
                state["lit_at"][origin] = next_step
            state["step"] = next_step
            state["shattered"] = {
                cell_id for cell_id, lit_step in state["lit_at"].items()
                if next_step - lit_step >= contract["fuses"][cell_id]
            }
            expired = destination in state["shattered"]
            if event.get("step_index") != next_step or event.get("accepted") is (expired):
                raise ValueError(f"event {sequence} forges its movement outcome")
            if expired:
                if event.get("failure") != "expired_destination":
                    raise ValueError(f"event {sequence} hides an expired-tile fall")
                state["position"] = destination
                state["status"] = "failed"
                terminal = True
                continue
            if event.get("failure") is not None:
                raise ValueError(f"event {sequence} invents a movement failure")
            state["position"] = destination
            if destination in contract["lantern_ids"]:
                state["collected"].add(destination)
            if destination == contract["exit_id"] and state["collected"] == set(contract["lantern_ids"]):
                state["status"] = "passed"
                terminal = True
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"Crackglaze replay rejected: {exc}")

    if payload.get("final_state") != _snapshot(state):
        return _fail("submitted final floor state does not match replay")
    completed = state["status"] == "passed"
    if payload.get("completed") is not completed:
        return _fail("submitted completion flag does not match replay")
    passed = completed
    collected = len(state["collected"])
    total = len(contract["lantern_ids"])
    score = 100 if passed else round(75 * collected / total)
    return {
        "graded": True,
        "passed": passed,
        "score": score,
        "feedback": (
            f"replayed {state['step']} moves; lanterns {collected}/{total}; "
            f"position {state['position']}; shattered {len(state['shattered'])}; {state['status']}"
        ),
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {
        "certified_solution": ground_truth.get("certified_solution"),
        "fuse_lengths": ground_truth.get("fuse_lengths"),
        "search_certificate": ground_truth.get("search_certificate"),
    }
