from __future__ import annotations

import copy
from typing import Any


MECHANIC_ID = "collision_chimes"
SIDES = ("top", "right", "bottom", "left")
DELTAS = ((-1, 0), (0, 1), (1, 0), (0, -1))


def _fail(feedback: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": feedback}


def _canonical_cells(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [
            {
                "id": str(cell["id"]),
                "row": int(cell["row"]),
                "col": int(cell["col"]),
                "direction": int(cell["direction"]) % 4,
            }
            for cell in cells
        ],
        key=lambda cell: cell["id"],
    )


def _validate_target(target: Any, grid_size: int, beats: int) -> bool:
    if not isinstance(target, list):
        return False
    for event in target:
        if not isinstance(event, dict):
            return False
        if set(event) != {"beat", "side", "slot"}:
            return False
        if type(event['beat']) is not int or type(event['slot']) is not int:
            return False
        try:
            beat = int(event["beat"])
            slot = int(event["slot"])
        except (TypeError, ValueError):
            return False
        if not 1 <= beat <= beats or event["side"] not in SIDES or not 0 <= slot < grid_size:
            return False
    return True


def _canonical_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Simultaneous impacts preserve multiplicity without depending on cell IDs.
    return sorted(events, key=lambda event: (event['beat'], SIDES.index(event['side']), event['slot']))


def _contract(
    ground_truth: dict[str, Any], public_state: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    contract = ground_truth.get("contract")
    if not isinstance(contract, dict) or public_state.get("contract") != contract:
        return None, "public chime contract differs from grading contract"
    try:
        grid_size = int(contract["grid_size"])
        beats = int(contract["beats"])
        beat_ms = int(contract["beat_ms"])
        max_cells = int(contract["max_cells"])
        target = copy.deepcopy(contract["target_events"])
    except (KeyError, TypeError, ValueError):
        return None, "malformed chime contract"
    if not 5 <= grid_size <= 12 or not 4 <= beats <= 40 or not 120 <= beat_ms <= 900:
        return None, "chime contract is outside supported bounds"
    if not 1 <= max_cells <= 12 or not _validate_target(target, grid_size, beats):
        return None, "malformed target sequence"
    return {
        "grid_size": grid_size,
        "beats": beats,
        "max_cells": max_cells,
        "target": target,
    }, None


def _simulate(cells: list[dict[str, Any]], grid_size: int, beats: int) -> list[dict[str, int | str]]:
    state = _canonical_cells(cells)
    events: list[dict[str, int | str]] = []
    for beat in range(1, beats + 1):
        occupied = {(int(cell["row"]), int(cell["col"])) for cell in state}
        proposals: list[tuple[int, int]] = []
        for cell in state:
            direction = int(cell["direction"]) % 4
            delta_row, delta_col = DELTAS[direction]
            proposals.append((int(cell["row"]) + delta_row, int(cell["col"]) + delta_col))
        duplicate_counts: dict[tuple[int, int], int] = {}
        for proposal in proposals:
            duplicate_counts[proposal] = duplicate_counts.get(proposal, 0) + 1
        next_state: list[dict[str, Any]] = []
        for cell, proposal in zip(state, proposals):
            row = int(cell["row"])
            col = int(cell["col"])
            direction = int(cell["direction"]) % 4
            next_row, next_col = proposal
            if not (0 <= next_row < grid_size and 0 <= next_col < grid_size):
                side = SIDES[direction]
                slot = col if side in {"top", "bottom"} else row
                events.append({"beat": beat, "side": side, "slot": slot})
                next_state.append({**cell, "direction": (direction + 2) % 4})
            elif proposal in occupied or duplicate_counts[proposal] > 1:
                next_state.append({**cell, "direction": (direction + 1) % 4})
            else:
                next_state.append({**cell, "row": next_row, "col": next_col})
        state = next_state
    return events


def _replay_edits(
    events: Any,
    *,
    grid_size: int,
    max_cells: int,
    expected_sources: tuple[str, str],
) -> tuple[list[dict[str, Any]] | None, str | None]:
    if not isinstance(events, list):
        return None, "edit transcript is missing"
    cells: dict[str, dict[str, Any]] = {}
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return None, f"edit {sequence} has an invalid sequence"
        event_type = event.get("type")
        if event_type == "add":
            if event.get("input_source") != expected_sources[0]:
                return None, f"edit {sequence} uses the wrong add control"
            cell_id = str(event.get("id") or "")
            if not cell_id or len(cell_id) > 24 or cell_id in cells:
                return None, f"edit {sequence} has a duplicate cell id"
            try:
                row = int(event["row"])
                col = int(event["col"])
                direction = int(event["direction"])
            except (KeyError, TypeError, ValueError):
                return None, f"edit {sequence} add is malformed"
            if not 0 <= row < grid_size or not 0 <= col < grid_size or direction != 0:
                return None, f"edit {sequence} add is outside the visible board"
            if len(cells) >= max_cells or any((item["row"], item["col"]) == (row, col) for item in cells.values()):
                return None, f"edit {sequence} adds an unavailable square"
            cells[cell_id] = {"id": cell_id, "row": row, "col": col, "direction": direction}
        elif event_type == "cycle":
            if event.get("input_source") != expected_sources[1]:
                return None, f"edit {sequence} uses the wrong direction control"
            cell_id = str(event.get("id") or "")
            if cell_id not in cells:
                return None, f"edit {sequence} cycles an unknown cell"
            cell = cells[cell_id]
            try:
                row = int(event["row"])
                col = int(event["col"])
                before = int(event["before_direction"])
                after = int(event["after_direction"])
            except (KeyError, TypeError, ValueError):
                return None, f"edit {sequence} cycle is malformed"
            if (row, col) != (cell["row"], cell["col"]) or before != cell["direction"] or after != (before + 1) % 4:
                return None, f"edit {sequence} contradicts the direction state"
            cell["direction"] = after
        else:
            return None, f"edit {sequence} has an unknown type"
    return _canonical_cells(list(cells.values())), None


def grade(
    payload: dict[str, Any],
    ground_truth: dict[str, Any],
    public_state: dict[str, Any],
) -> dict[str, Any]:
    if payload.get("mechanic_id") != MECHANIC_ID or ground_truth.get("mechanic_id") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if not challenge_id or payload.get("challenge_id") != challenge_id or public_state.get("challenge_id") != challenge_id:
        return _fail("stale challenge")
    if payload.get("task_id") != ground_truth.get("task_id") or public_state.get("task_id") != ground_truth.get("task_id"):
        return _fail("task mismatch")
    contract, error = _contract(ground_truth, public_state)
    if contract is None:
        return _fail(error or "invalid contract")
    condition = ground_truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "simplified")
    expected_sources = {
        "simplified": ("add_button", "cycle_button"),
        "full": ("cell_drag", "cell_click"),
    }.get(interaction)
    if expected_sources is None:
        return _fail("invalid interaction condition")
    cells, error = _replay_edits(
        payload.get("edit_events"),
        grid_size=contract["grid_size"],
        max_cells=contract["max_cells"],
        expected_sources=expected_sources,
    )
    if cells is None:
        return _fail(error or "invalid edit transcript")
    if payload.get("cells") != cells:
        return _fail("final cells do not match the edit transcript")
    if payload.get("input_surface") != interaction:
        return _fail("submission used the wrong interaction surface")
    if payload.get("run_completed") is not True or payload.get("beats_run") != contract["beats"]:
        return _fail("run did not cover the requested beats")
    actual = _simulate(cells, contract["grid_size"], contract["beats"])
    claimed_events = payload.get("wall_events")
    if not _validate_target(claimed_events, contract['grid_size'], contract['beats']):
        return _fail("malformed wall-event transcript")
    if _canonical_events(claimed_events) != _canonical_events(actual):
        return _fail("wall-event transcript contradicts the moving cells")
    completed = _canonical_events(actual) == _canonical_events(contract["target"])
    if payload.get("completed") is not completed:
        return _fail("completion claim does not match the target sequence")
    if not completed:
        return _fail("target sequence not matched")
    return {
        "graded": True,
        "passed": True,
        "feedback": f"matched {len(actual)} wall chimes across {contract['beats']} beats",
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {"solution_cells": copy.deepcopy(ground_truth.get("solution_cells") or [])}
