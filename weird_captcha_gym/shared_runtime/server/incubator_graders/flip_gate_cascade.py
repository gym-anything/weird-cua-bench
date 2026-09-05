from __future__ import annotations

from typing import Any


MECHANIC_ID = "flip_gate_cascade"


def _fail(feedback: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": feedback}


def _row_offsets(top_chutes: int, row_count: int) -> tuple[int, ...]:
    offsets: list[int] = []
    total = 0
    for row in range(row_count):
        offsets.append(total)
        total += top_chutes + row
    return tuple(offsets)


def _transition(
    state: tuple[int, ...],
    chute: int,
    top_chutes: int,
    row_count: int,
    entry_columns: tuple[int, ...],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    offsets = _row_offsets(top_chutes, row_count)
    result = list(state)
    column = entry_columns[chute]
    path: list[int] = []
    for row in range(row_count):
        gate = offsets[row] + column
        path.append(gate)
        points_right = bool(result[gate])
        result[gate] = 0 if points_right else 1
        if points_right:
            column += 1
    return tuple(result), tuple(path)


def _contract(
    ground_truth: dict[str, Any], public_state: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    machine = ground_truth.get("machine")
    if not isinstance(machine, dict) or public_state.get("machine") != machine:
        return None, "public machine differs from grading contract"
    if public_state.get("control_condition") != ground_truth.get("control_condition"):
        return None, "control condition mismatch"
    try:
        top_chutes = int(machine["top_chutes"])
        row_count = int(machine["row_count"])
        gate_count = int(machine["gate_count"])
        budget = int(machine["drop_budget"])
        entry_columns = tuple(int(value) for value in machine["entry_columns"])
        initial = tuple(int(value) for value in machine["initial_state"])
        target = tuple(int(value) for value in machine["target_state"])
    except (KeyError, TypeError, ValueError):
        return None, "invalid machine contract"
    expected_gate_count = sum(top_chutes + row for row in range(row_count))
    if (
        not 2 <= top_chutes <= 5
        or not 2 <= row_count <= 4
        or gate_count != expected_gate_count
        or len(initial) != gate_count
        or len(target) != gate_count
        or sorted(entry_columns) != list(range(top_chutes))
        or any(chute == column for chute, column in enumerate(entry_columns))
        or any(value not in (0, 1) for value in (*initial, *target))
        or not 1 <= budget <= 16
    ):
        return None, "malformed machine geometry or state"
    return {
        "top_chutes": top_chutes,
        "row_count": row_count,
        "budget": budget,
        "entry_columns": entry_columns,
        "initial": initial,
        "target": target,
    }, None


def grade(
    payload: dict[str, Any],
    ground_truth: dict[str, Any],
    public_state: dict[str, Any],
) -> dict[str, Any]:
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if payload.get("mechanic_id") != MECHANIC_ID or ground_truth.get("mechanic_id") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    if not challenge_id or payload.get("challenge_id") != challenge_id or public_state.get("challenge_id") != challenge_id:
        return _fail("stale challenge")
    if payload.get("task_id") != ground_truth.get("task_id") or public_state.get("task_id") != ground_truth.get("task_id"):
        return _fail("task mismatch")
    contract, error = _contract(ground_truth, public_state)
    if error or contract is None:
        return _fail(error or "invalid contract")
    interaction = str((ground_truth.get("control_condition") or {}).get("interaction") or "simplified")
    expected_source = {"simplified": "chute_click", "full": "marble_drag"}.get(interaction)
    if expected_source is None:
        return _fail("invalid interaction condition")

    events = payload.get("events")
    if not isinstance(events, list) or len(events) > contract["budget"]:
        return _fail("drop transcript is missing or exceeds the tray budget")
    state = contract["initial"]
    reached_at: int | None = None
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return _fail(f"drop {sequence} sequence mismatch")
        if event.get("input_source") != expected_source:
            return _fail(f"drop {sequence} uses the wrong interaction input")
        try:
            chute = int(event.get("chute"))
            before = tuple(int(value) for value in event.get("before_state", []))
            after = tuple(int(value) for value in event.get("after_state", []))
            path = tuple(int(value) for value in event.get("path", []))
            drops_after = int(event.get("drops_after"))
        except (TypeError, ValueError):
            return _fail(f"drop {sequence} is malformed")
        if reached_at is not None:
            return _fail("transcript continues after the target was reached")
        if chute < 0 or chute >= contract["top_chutes"] or before != state:
            return _fail(f"drop {sequence} has an invalid chute or before-state")
        expected_after, expected_path = _transition(
            state,
            chute,
            contract["top_chutes"],
            contract["row_count"],
            contract["entry_columns"],
        )
        if (
            after != expected_after
            or path != expected_path
            or drops_after != sequence
            or event.get("settled") is not True
        ):
            return _fail(f"drop {sequence} contradicts flip-gate physics")
        state = expected_after
        if state == contract["target"]:
            reached_at = sequence

    completed = reached_at is not None and reached_at <= contract["budget"]
    claims_match = (
        payload.get("final_state") == list(state)
        and payload.get("drops_used") == len(events)
        and payload.get("completed") is completed
        and payload.get("budget_exhausted") is (len(events) >= contract["budget"] and not completed)
    )
    if not claims_match:
        return _fail("final machine claims do not match replay")
    return {
        "graded": True,
        "passed": completed,
        "feedback": (
            f"target matched after {reached_at} settled drops"
            if completed
            else f"target not matched after {len(events)} of {contract['budget']} drops"
        ),
    }


def cheat(ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {"solution_chutes": ground_truth.get("solution_chutes") or []}
