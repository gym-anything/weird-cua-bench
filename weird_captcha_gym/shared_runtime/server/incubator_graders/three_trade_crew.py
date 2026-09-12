from __future__ import annotations

import copy
from typing import Any


MECHANIC_ID = "three_trade_crew"
DIRECTIONS = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}


def _fail(feedback: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": feedback}


def _bind(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> str | None:
    if payload.get("mechanic_id") != MECHANIC_ID or truth.get("mechanic_id") != MECHANIC_ID or public.get("mechanic_id") != MECHANIC_ID:
        return "mechanic binding failed"
    challenge = str(truth.get("challenge_id") or "")
    task_id = str(truth.get("task_id") or "")
    if not challenge or payload.get("challenge_id") != challenge or public.get("challenge_id") != challenge:
        return "stale challenge"
    if not task_id or payload.get("task_id") != task_id or public.get("task_id") != task_id:
        return "task binding failed"
    if truth.get("control_condition") != public.get("control_condition"):
        return "control condition mismatch"
    return None


def _point(value: Any) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2 or any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        raise ValueError("position must be an integer pair")
    return int(value[0]), int(value[1])


def _board(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("board is missing")
    result = copy.deepcopy(value)
    for key in ("rows", "columns"):
        if isinstance(result.get(key), bool) or not isinstance(result.get(key), int):
            raise ValueError(f"board {key} is invalid")
    for key in ("walls",):
        if not isinstance(result.get(key), list):
            raise ValueError(f"board {key} is invalid")
    for item in result["walls"]:
        _point(item)
    for key in ("workers", "crates", "goals", "switches", "doors"):
        if not isinstance(result.get(key), list):
            raise ValueError(f"board {key} is invalid")
    return result


def _occupied(board: dict[str, Any]) -> dict[tuple[int, int], tuple[str, str]]:
    result: dict[tuple[int, int], tuple[str, str]] = {}
    for worker in board["workers"]:
        result[_point(worker["position"])] = ("worker", str(worker["id"]))
    for crate in board["crates"]:
        result[_point(crate["position"])] = ("crate", str(crate["id"]))
    return result


def _switch_open(board: dict[str, Any], switch_id: str) -> bool:
    switch = next(item for item in board["switches"] if item["id"] == switch_id)
    point = _point(switch["position"])
    return any(_point(item["position"]) == point for item in board["workers"] + board["crates"])


def _passable(board: dict[str, Any], point: tuple[int, int], worker_id: str) -> bool:
    row, column = point
    if not 0 <= row < board["rows"] or not 0 <= column < board["columns"]:
        return False
    if point in {_point(item) for item in board["walls"]}:
        return False
    for door in board["doors"]:
        if _point(door["position"]) == point and not _switch_open(board, str(door["switch_id"])):
            return False
    occupant = _occupied(board).get(point)
    return occupant is None or occupant[0] == "crate" or occupant == ("worker", worker_id)


def _apply(board: dict[str, Any], worker_id: str, direction: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if direction not in DIRECTIONS:
        raise ValueError("unknown direction")
    current = copy.deepcopy(board)
    worker = next((item for item in current["workers"] if item["id"] == worker_id), None)
    if worker is None:
        raise ValueError("unknown worker")
    dr, dc = DIRECTIONS[direction]
    old = _point(worker["position"])
    dest = (old[0] + dr, old[1] + dc)
    if not _passable(current, dest, worker_id):
        raise ValueError("blocked by wall or closed door")
    if _occupied(current).get(dest, (None, None))[0] == "worker":
        raise ValueError("workers cannot overlap")
    crate = next((item for item in current["crates"] if _point(item["position"]) == dest), None)
    ability = "move"
    crate_id = None
    if crate is not None:
        crate_id = str(crate["id"])
        if worker["role"] == "fighter":
            beyond = (dest[0] + dr, dest[1] + dc)
            if not _passable(current, beyond, worker_id) or beyond in _occupied(current):
                raise ValueError("fighter cannot push")
            crate["position"] = [*beyond]
            ability = "push"
        elif worker["role"] in {"thief", "wizard"}:
            crate["position"] = [*old]
            ability = "pull" if worker["role"] == "thief" else "swap"
    elif worker["role"] == "thief":
        behind = (old[0] - dr, old[1] - dc)
        trailing = next((item for item in current["crates"] if _point(item["position"]) == behind), None)
        if trailing is not None:
            trailing["position"] = [*old]
            crate_id = str(trailing["id"])
            ability = "pull"
    worker["position"] = [*dest]
    return current, {
        "worker_id": worker_id,
        "direction": direction,
        "from": [*old],
        "to": [*dest],
        "ability": ability,
        "crate_id": crate_id,
        "door_states": {str(door["id"]): _switch_open(current, str(door["switch_id"])) for door in current["doors"]},
        "workers_after": copy.deepcopy(current["workers"]),
        "crates_after": copy.deepcopy(current["crates"]),
    }


def _solved(board: dict[str, Any]) -> bool:
    return all(_point(worker["position"]) == _point(next(goal["position"] for goal in board["goals"] if goal["worker_id"] == worker["id"])) for worker in board["workers"])


def _contract(truth: dict[str, Any], public: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    parameters = truth.get("parameters")
    if not isinstance(parameters, dict) or parameters != public.get("parameters"):
        raise ValueError("difficulty parameters differ")
    hidden = _board(truth.get("initial_board"))
    visible = _board((public.get("board") or {}))
    if hidden != visible:
        raise ValueError("visible board differs from generated board")
    condition = truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "")
    if interaction not in {"full", "simplified"}:
        raise ValueError("invalid interaction condition")
    return hidden, parameters, interaction


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    binding = _bind(payload, truth, public)
    if binding:
        return _fail(binding)
    try:
        board, parameters, interaction = _contract(truth, public)
    except (TypeError, ValueError) as exc:
        return _fail(f"invalid crew contract: {exc}")
    if payload.get("interaction_mode") != interaction:
        return _fail("submitted interaction surface differs from the selected condition")
    expected_action_source = "keyboard_move" if interaction == "full" else "direction_button"
    expected_select_source = "keyboard_select" if interaction == "full" else "worker_card"
    selections = payload.get("selection_events")
    events = payload.get("events")
    if not isinstance(selections, list) or not isinstance(events, list):
        return _fail("selection or movement transcript is missing")
    if len(events) > int(parameters.get("action_budget", 999)):
        return _fail("movement transcript exceeds the visible action budget")
    workers = {str(item["id"]): item for item in board["workers"]}
    selected: str | None = None
    selection_index = 0
    ordered_selections = sorted(selections, key=lambda item: int(item.get("movement_index", 0)) if isinstance(item, dict) else 0)
    selection_cursor = 0
    for selection in ordered_selections:
        if not isinstance(selection, dict) or selection.get("input_source") != expected_select_source:
            return _fail("selection uses the wrong interaction surface")
        worker_id = str(selection.get("worker_id") or "")
        if worker_id not in workers:
            return _fail("selection names an unavailable worker")
        selection_index += 1
    used = set()
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != index:
            return _fail(f"movement {index} has an invalid sequence")
        if event.get("input_source") != expected_action_source:
            return _fail(f"movement {index} uses the wrong interaction surface")
        while selection_cursor < len(ordered_selections) and int(ordered_selections[selection_cursor].get("movement_index", 0)) <= index - 1:
            selected = str(ordered_selections[selection_cursor].get("worker_id") or "")
            selection_cursor += 1
        worker_id = str(event.get("worker_id") or "")
        if selected != worker_id:
            return _fail(f"movement {index} was sent to a worker that was not selected")
        before = next(item for item in board["workers"] if item["id"] == worker_id)
        if event.get("from") != before["position"]:
            return _fail(f"movement {index} reports the wrong origin")
        try:
            board, expected = _apply(board, worker_id, str(event.get("direction") or ""))
        except (TypeError, ValueError) as exc:
            return _fail(f"movement {index} is illegal: {exc}")
        for field in ("to", "ability", "crate_id", "door_states", "workers_after", "crates_after"):
            if event.get(field) != expected[field]:
                return _fail(f"movement {index} has inconsistent {field}")
        used.add(expected["ability"])
    final = payload.get("final_board")
    if not isinstance(final, dict) or final.get("workers") != board["workers"] or final.get("crates") != board["crates"]:
        return _fail("final workshop state does not match movement replay")
    completed = payload.get("completed") is True
    passed = completed and _solved(board) and {"push", "pull", "swap"}.issubset(used)
    if completed and not passed:
        return _fail("certification was claimed before all three workers reached their bays")
    return {"graded": True, "passed": passed, "feedback": f"replayed {len(events)} movements, selected {selection_index} times, abilities={','.join(sorted(used))}"}


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    return {"solution_actions": ground_truth.get("solution_actions") or [], "instruction": "Select each worker and perform the visible crew movements in order.", "answers": []}
