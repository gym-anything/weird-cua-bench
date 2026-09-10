"""Independent replay grader for Reflected Rival."""

from __future__ import annotations

from typing import Any


MECHANIC_ID = "reflected_rival"
INTERACTION_SOURCES = {"simplified": "direction_buttons", "full": "keyboard"}


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _advance(state: dict[str, Any], board: dict[str, Any]) -> None:
    segments = int(board["segment_count"])
    player_segment = min(segments - 1, int(state["player_progress"]))
    rival_segment = min(segments - 1, int(state["rival_progress"]))
    player_cell = board["course"][player_segment]["cells"][state["player_lane"]]
    rival_cell = board["course"][rival_segment]["cells"][state["rival_lane"]]
    if state["player_finish_tick"] is None:
        state["player_progress"] += float(board["base_rate"]) * float(player_cell["multiplier"])
    if state["rival_finish_tick"] is None:
        state["rival_progress"] += float(board["base_rate"]) * float(rival_cell["multiplier"])
    state["tick"] += 1
    if state["player_finish_tick"] is None and state["player_progress"] >= segments:
        state["player_finish_tick"] = state["tick"]
    if state["rival_finish_tick"] is None and state["rival_progress"] >= segments:
        state["rival_finish_tick"] = state["tick"]


def _move(state: dict[str, Any], direction: str, board: dict[str, Any]) -> None:
    delta = -1 if direction == "left" else 1
    lanes = int(board["lane_count"])
    state["player_lane"] = max(0, min(lanes - 1, state["player_lane"] + delta))
    state["rival_lane"] = max(0, min(lanes - 1, state["rival_lane"] - delta))


def replay(board: dict[str, Any], actions: list[dict[str, Any]], final_tick: int) -> dict[str, Any]:
    state: dict[str, Any] = {
        "tick": 0,
        "player_lane": int(board["player_start_lane"]),
        "rival_lane": int(board["rival_start_lane"]),
        "player_progress": 0.0,
        "rival_progress": 0.0,
        "player_finish_tick": None,
        "rival_finish_tick": None,
    }
    for action in actions:
        action_tick = int(action["tick"])
        while state["tick"] < action_tick:
            _advance(state, board)
            if state["tick"] >= int(board["max_ticks"]):
                break
        if state["tick"] >= int(board["max_ticks"]) or (state["player_finish_tick"] is not None and state["rival_finish_tick"] is not None):
            raise ValueError("steering after race completion")
        _move(state, str(action["direction"]), board)
    while state["tick"] < final_tick and state["tick"] < int(board["max_ticks"]):
        _advance(state, board)
    return state


def grade(
    payload: dict[str, Any],
    ground_truth: dict[str, Any],
    public_state: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(ground_truth, dict) or not isinstance(public_state, dict):
        return _fail("race export is not an object")
    if payload.get("mechanic_id") != MECHANIC_ID or ground_truth.get("mechanic_id") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if not challenge_id or payload.get("challenge_id") != challenge_id or public_state.get("challenge_id") != challenge_id:
        return _fail("stale challenge")
    if payload.get("task_id") != ground_truth.get("task_id") or public_state.get("task_id") != ground_truth.get("task_id"):
        return _fail("task identity mismatch")
    board = ground_truth.get("board")
    if not isinstance(board, dict) or public_state.get("board") != board:
        return _fail("visible course differs from replay course")
    if ground_truth.get("control_condition") != public_state.get("control_condition"):
        return _fail("interaction condition differs from visible course")
    condition = ground_truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "full")
    expected_source = INTERACTION_SOURCES.get(interaction)
    if expected_source is None:
        return _fail("invalid interaction condition")

    actions = payload.get("actions")
    if not isinstance(actions, list) or len(actions) > 2400:
        return _fail("race action transcript is invalid")
    final_tick = payload.get("final_tick")
    if type(final_tick) is not int:
        return _fail("final race tick is invalid")
    if not 0 <= final_tick <= int(board["max_ticks"]):
        return _fail("final race tick is outside limits")

    normalized: list[dict[str, Any]] = []
    previous_tick = 0
    for sequence, action in enumerate(actions, start=1):
        if not isinstance(action, dict) or type(action.get("sequence")) is not int or action.get("sequence") != sequence:
            return _fail(f"action {sequence} sequence mismatch")
        if action.get("input_source") != expected_source:
            return _fail(f"action {sequence} uses the wrong interaction input")
        direction = str(action.get("direction") or "")
        if direction not in {"left", "right"}:
            return _fail(f"action {sequence} direction is invalid")
        action_tick = action.get("tick")
        if type(action_tick) is not int:
            return _fail(f"action {sequence} tick is invalid")
        if action_tick < previous_tick or action_tick > final_tick:
            return _fail(f"action {sequence} ticks are not monotonic")
        normalized.append({"tick": action_tick, "direction": direction})
        previous_tick = action_tick

    try:
        state = replay(board, normalized, final_tick)
    except (KeyError, IndexError, TypeError, ValueError, OverflowError) as exc:
        return _fail(f"course replay failed: {exc}")
    player_finish = state["player_finish_tick"]
    rival_finish = state["rival_finish_tick"]
    both_finished = player_finish is not None and rival_finish is not None
    winner = both_finished and int(player_finish) < int(rival_finish)
    at_completion = both_finished and max(player_finish, rival_finish) == final_tick
    passed = payload.get("completed") is True and winner and at_completion
    return {
        "graded": True,
        "passed": passed,
        "feedback": (
            f"white finish {player_finish}; blue finish {rival_finish}; "
            f"ticks {state['tick']}; actions {len(actions)}"
        ),
        "player_finish_tick": player_finish,
        "rival_finish_tick": rival_finish,
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    return {
        "solution_commands": ground_truth.get("solution_commands") or [],
        "constructive_replay": ground_truth.get("constructive_replay") or {},
        "instruction": "Read the visible course and steer the white racer with the visible controls.",
    }


__all__ = ["MECHANIC_ID", "grade", "replay", "cheat"]
