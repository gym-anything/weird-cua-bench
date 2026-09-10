from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "ribbon_consensus"
DEFAULT_PARAMETERS = {
    "row_count": 5,
    "sequence_length": 13,
    "target_gap_count": 2,
    "misalignment_count": 5,
    "max_edits": 8,
    "color_count": 4,
    "mutation_rate": 0.14,
    "gap_open_penalty": 5,
    "gap_extend_penalty": 1,
    "required_gain_ratio": 0.82,
}
CONTROL_FIELDS = frozenset(DEFAULT_PARAMETERS)


def _fail(feedback: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": feedback}


def _valid_shift(columns: list[int], break_index: int, delta: int, column_count: int) -> list[int] | None:
    if not 1 <= break_index < len(columns) or delta not in (-1, 1):
        return None
    shifted = list(columns)
    for index in range(break_index, len(shifted)):
        shifted[index] += delta
    if min(shifted) < 0 or max(shifted) >= column_count:
        return None
    if any(left >= right for left, right in zip(shifted, shifted[1:])):
        return None
    return shifted


def score_alignment(
    rows: list[dict[str, Any]],
    columns_by_row: dict[str, list[int]],
    gap_open_penalty: int,
    gap_extend_penalty: int,
) -> dict[str, Any]:
    lookup = {
        row["id"]: {column: index for index, column in enumerate(columns_by_row[row["id"]])}
        for row in rows
    }
    minimum = min(min(values) for values in columns_by_row.values())
    maximum = max(max(values) for values in columns_by_row.values())
    matches = 0
    mismatches = 0
    column_scores: list[int] = []
    for column in range(minimum, maximum + 1):
        tokens: list[int | None] = []
        for row in rows:
            index = lookup[row["id"]].get(column)
            tokens.append(None if index is None else int(row["colors"][index]))
        column_score = 0
        for left_index in range(len(tokens)):
            for right_index in range(left_index + 1, len(tokens)):
                left, right = tokens[left_index], tokens[right_index]
                if left is None or right is None:
                    continue
                if left == right:
                    matches += 1
                    column_score += 1
                else:
                    mismatches += 1
                    column_score -= 1
        column_scores.append(column_score)

    gap_open_runs = 0
    gap_extensions = 0
    for row in rows:
        positions = set(columns_by_row[row["id"]])
        first = min(positions)
        last = max(positions)
        inside_gap = False
        for column in range(first + 1, last):
            if column not in positions:
                if inside_gap:
                    gap_extensions += 1
                else:
                    gap_open_runs += 1
                    inside_gap = True
            else:
                inside_gap = False
    return {
        "score": int(
            matches
            - mismatches
            - gap_open_runs * int(gap_open_penalty)
            - gap_extensions * int(gap_extend_penalty)
        ),
        "matches": int(matches),
        "mismatches": int(mismatches),
        "gap_open_runs": int(gap_open_runs),
        "gap_extensions": int(gap_extensions),
        "column_scores": column_scores,
    }


def _control_contract(
    ground_truth: dict[str, Any], public_state: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    condition = ground_truth.get("control_condition")
    if condition is None:
        if public_state.get("control_condition") is not None:
            raise ValueError("public control condition is unexpected")
        return None, None, "simplified"
    if not isinstance(condition, dict) or public_state.get("control_condition") != condition:
        raise ValueError("control condition differs between public and hidden state")
    difficulty = condition.get("difficulty")
    interaction = str(condition.get("interaction") or "")
    real_time = str(condition.get("real_time") or "")
    parameters = condition.get("difficulty_parameters")
    if (
        isinstance(difficulty, bool)
        or not isinstance(difficulty, int)
        or difficulty not in {1, 2, 3, 4, 5}
        or interaction not in {"simplified", "full"}
        or real_time not in {"live", "paused"}
        or not isinstance(parameters, dict)
        or set(parameters) != CONTROL_FIELDS
    ):
        raise ValueError("control condition is malformed")
    return dict(parameters), interaction, interaction


def _same_json(left: Any, right: Any) -> bool:
    return left == right


def _pointer_path(gesture: dict[str, Any]) -> list[tuple[float, float]] | None:
    path = gesture.get("pointer_path")
    if not isinstance(path, list) or len(path) < 3:
        return None
    points: list[tuple[float, float]] = []
    for point in path:
        if not isinstance(point, dict):
            return None
        try:
            x = float(point["x"])
            y = float(point["y"])
        except (KeyError, TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(x) or not math.isfinite(y):
            return None
        points.append((x, y))
    return points


def grade(
    payload: dict[str, Any],
    ground_truth: dict[str, Any],
    public_state: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return _fail("submission is not an object")
    if str(payload.get("mechanic_id") or "") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    if str(ground_truth.get("mechanic_id") or "") != MECHANIC_ID:
        return _fail("ground-truth mechanic mismatch")
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if not challenge_id or str(payload.get("challenge_id") or "") != challenge_id:
        return _fail("stale challenge")
    if str(public_state.get("challenge_id") or "") != challenge_id:
        return _fail("public-state challenge mismatch")
    try:
        parameters, interaction, expected_interaction = _control_contract(ground_truth, public_state)
        parameters = parameters or dict(DEFAULT_PARAMETERS)
        expected_interaction = expected_interaction or "simplified"
        if ground_truth.get("parameters") != parameters or public_state.get("parameters") != parameters:
            raise ValueError("selected parameters are not bound to the generated world")
        if payload.get("task_id") != ground_truth.get("task_id"):
            raise ValueError("task identity mismatch")
        if payload.get("interaction_mode") != expected_interaction:
            raise ValueError("wrong interaction surface")
        if public_state.get("rows") != ground_truth.get("public_rows"):
            raise ValueError("public ribbon tiles differ from the replay contract")
        if public_state.get("initial_columns") != ground_truth.get("initial_columns"):
            raise ValueError("public initial columns differ from the replay contract")
        rows = [dict(row) for row in ground_truth.get("rows") or []]
        if len(rows) != int(parameters["row_count"]):
            raise ValueError("row count does not implement the selected profile")
        stage = dict(ground_truth.get("stage") or {})
        column_count = int(stage["column_count"])
        if int(stage.get("cell_width") or 0) < 24 or int(stage.get("row_height") or 0) < 32:
            raise ValueError("stage geometry is incomplete")
        columns = {
            str(row_id): [int(value) for value in values]
            for row_id, values in (ground_truth.get("initial_columns") or {}).items()
        }
        if set(columns) != {str(row["id"]) for row in rows}:
            raise ValueError("initial column rows are incomplete")
        for row in rows:
            colors = row.get("colors")
            positions = columns[row["id"]]
            if not isinstance(colors, list) or len(colors) != int(parameters["sequence_length"]):
                raise ValueError("row tile count does not implement the selected profile")
            if len(positions) != len(colors) or any(left >= right for left, right in zip(positions, positions[1:])):
                raise ValueError("row tile order is not preserved")
        expected_initial = score_alignment(
            rows,
            columns,
            int(parameters["gap_open_penalty"]),
            int(parameters["gap_extend_penalty"]),
        )
        if public_state.get("score_breakdown") != expected_initial or int(public_state.get("score") or 0) != expected_initial["score"]:
            raise ValueError("initial score is not replayable")
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return _fail(f"invalid ribbon contract: {exc}")

    events = payload.get("events")
    max_edits = int(parameters["max_edits"])
    if not isinstance(events, list) or not (1 <= len(events) <= max_edits):
        return _fail("submission has no bounded ribbon edit transcript")
    expected_source = "proxy_shift" if expected_interaction == "simplified" else "tile_run_drag"
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return _fail(f"event {sequence} sequence mismatch")
        if event.get("kind") != "shift" or event.get("input_source") != expected_source:
            return _fail("event uses the wrong input surface")
        if not isinstance(event.get("row_id"), str) or event["row_id"] not in columns:
            return _fail("event names an unknown ribbon")
        try:
            break_index = int(event["break_index"])
            delta = int(event["delta"])
        except (KeyError, TypeError, ValueError, OverflowError):
            return _fail("event shift is malformed")
        shifted = _valid_shift(columns[event["row_id"]], break_index, delta, column_count)
        if shifted is None:
            return _fail("event shifts a tile suffix out of order or off the loom")
        if expected_interaction == "full":
            gesture = event.get("gesture")
            if not isinstance(gesture, dict):
                return _fail("direct tile move has no pointer gesture evidence")
            try:
                sample_count = int(gesture["sample_count"])
                travel_px = float(gesture["travel_px"])
                start_column = int(gesture["start_column"])
                end_column = int(gesture["end_column"])
            except (KeyError, TypeError, ValueError, OverflowError):
                return _fail("pointer gesture evidence is malformed")
            pointer_path = _pointer_path(gesture)
            expected_start_column = columns[event["row_id"]][break_index]
            path_travel = (
                sum(abs(right[0] - left[0]) for left, right in zip(pointer_path, pointer_path[1:]))
                if pointer_path is not None
                else math.nan
            )
            horizontal_delta = (
                pointer_path[-1][0] - pointer_path[0][0]
                if pointer_path is not None
                else math.nan
            )
            if (
                pointer_path is None
                or sample_count != len(pointer_path)
                or sample_count < 3
                or not math.isfinite(travel_px)
                or travel_px < int(stage["cell_width"]) * 0.55
                or not math.isclose(travel_px, path_travel, rel_tol=1e-6, abs_tol=1e-6)
                or abs(horizontal_delta) < int(stage["cell_width"]) * 0.45
                or (horizontal_delta > 0) != (delta > 0)
                or start_column != expected_start_column
                or end_column != expected_start_column + delta
            ):
                return _fail("direct tile move did not contain a physical drag")
        elif event.get("gesture") is not None:
            return _fail("proxy shift includes a direct-pointer gesture")
        columns[event["row_id"]] = shifted
        expected_score = score_alignment(
            rows,
            columns,
            int(parameters["gap_open_penalty"]),
            int(parameters["gap_extend_penalty"]),
        )
        if event.get("score_after") != expected_score or event.get("breakdown_after") != expected_score:
            return _fail(f"event {sequence} score does not replay")

    final_score = score_alignment(
        rows,
        columns,
        int(parameters["gap_open_penalty"]),
        int(parameters["gap_extend_penalty"]),
    )
    try:
        score_floor = int(ground_truth["score_floor"])
        submitted_score = int(payload["final_score"])
        move_count = int(payload["move_count"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return _fail("final ribbon certificate is malformed")
    if (
        payload.get("final_columns") != columns
        or submitted_score != final_score["score"]
        or payload.get("score_breakdown") != final_score
        or move_count != len(events)
        or payload.get("completed") is not True
        or final_score["score"] < score_floor
    ):
        return _fail(
            f"alignment not certified: score {final_score['score']} / required {score_floor}; "
            f"moves {len(events)}/{max_edits}"
        )
    return {
        "graded": True,
        "passed": True,
        "score": 100,
        "feedback": f"alignment certified at score {final_score['score']} after {len(events)} suffix shifts",
        "final_score": final_score,
    }


def cheat(ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    """Development-only witness for the ordinary browser solver; never shown in task UI."""
    return {
        "mechanic_id": MECHANIC_ID,
        "challenge_id": ground_truth.get("challenge_id"),
        "interaction": (ground_truth.get("control_condition") or {}).get("interaction", "simplified"),
        "repair_actions": ground_truth.get("repair_actions") or [],
        "target_columns": ground_truth.get("target_columns") or {},
        "target_score": ground_truth.get("target_score") or {},
        "public_challenge_id": public_state.get("challenge_id"),
    }
