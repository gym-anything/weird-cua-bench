from __future__ import annotations

from typing import Any


MECHANIC_ID = "bandaged_rose_window"
DISC_IDS = ("north", "southwest", "southeast")
DISC_SLOTS = (
    (3, 7, 6, 0, 5, 4),
    (3, 10, 9, 1, 8, 7),
    (3, 4, 12, 2, 11, 10),
)


def _fail(feedback: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": feedback}


def _legal(state: tuple[int, ...], disc: int) -> bool:
    slots = DISC_SLOTS[disc]
    return state.index(3) in slots and all(point == disc or state.index(point) not in slots for point in range(3))


def _turn(state: tuple[int, ...], disc: int, direction: int) -> tuple[int, ...]:
    slots = DISC_SLOTS[disc]
    values = [state[index] for index in slots]
    values = values[-1:] + values[:-1] if direction == 1 else values[1:] + values[:1]
    result = list(state)
    for slot, value in zip(slots, values):
        result[slot] = value
    return tuple(result)


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if payload.get("mechanic_id") != MECHANIC_ID or ground_truth.get("mechanic_id") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    if not challenge_id or payload.get("challenge_id") != challenge_id or public_state.get("challenge_id") != challenge_id:
        return _fail("stale challenge")
    if payload.get("task_id") != ground_truth.get("task_id") or public_state.get("task_id") != ground_truth.get("task_id"):
        return _fail("task mismatch")
    truth_rose = ground_truth.get("rose") or {}
    if public_state.get("rose") != truth_rose or public_state.get("control_condition") != ground_truth.get("control_condition"):
        return _fail("public rose differs from grading contract")
    condition = ground_truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "full")
    expected_source = {"simplified": "proxy_buttons", "full": "rim_drag"}.get(interaction)
    if expected_source is None:
        return _fail("invalid interaction condition")
    try:
        state = tuple(int(value) for value in truth_rose["initial_state"])
        solved = tuple(int(value) for value in truth_rose["solved_state"])
    except (KeyError, TypeError, ValueError):
        return _fail("invalid rose contract")
    if sorted(state) != list(range(13)) or solved != tuple(range(13)):
        return _fail("malformed rose state")
    events = payload.get("events")
    if not isinstance(events, list) or len(events) > 200:
        return _fail("turn transcript is missing or outside limits")
    successful = 0
    refused = 0
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return _fail(f"event {sequence} sequence mismatch")
        if event.get("input_source") != expected_source:
            return _fail(f"event {sequence} uses the wrong interaction input")
        try:
            disc = DISC_IDS.index(str(event.get("disc_id")))
            direction = int(event.get("direction"))
            before = tuple(int(value) for value in event.get("before_state", []))
            after = tuple(int(value) for value in event.get("after_state", []))
            turns_after = int(event.get("turns_after"))
        except (TypeError, ValueError):
            return _fail(f"event {sequence} is malformed")
        if direction not in (-1, 1) or before != state:
            return _fail(f"event {sequence} has an invalid direction or before-state")
        can_turn = _legal(state, disc)
        expected_after = _turn(state, disc, direction) if can_turn else state
        expected_outcome = "turned" if can_turn else "refused"
        if event.get("outcome") != expected_outcome or after != expected_after:
            return _fail(f"event {sequence} contradicts bandaged-disc physics")
        if can_turn:
            successful += 1
        else:
            refused += 1
        if turns_after != successful:
            return _fail(f"event {sequence} has a forged successful-turn count")
        state = expected_after
    if payload.get("final_state") != list(state):
        return _fail("claimed final rose does not match replay")
    if payload.get("successful_turns") != successful or payload.get("refused_turns") != refused:
        return _fail("claimed turn totals do not match replay")
    completed = state == solved
    if payload.get("completed") is not completed:
        return _fail("claimed completion does not match replay")
    return {
        "graded": True,
        "passed": completed,
        "feedback": f"rose replay {'restored' if completed else 'incomplete'} after {successful} successful and {refused} refused turns",
    }


def cheat(ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {"solution_moves": ground_truth.get("solution_moves") or []}
