from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "lasso_freight"
DELTAS = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
NEIGHBOURS = ((0, -1), (1, 0), (0, 1), (-1, 0))


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _coord(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        return int(value[0]), int(value[1])
    except (TypeError, ValueError):
        return None


def _coords(value: Any) -> list[tuple[int, int]] | None:
    if not isinstance(value, list):
        return None
    result = [_coord(item) for item in value]
    return result if all(item is not None for item in result) else None


def _snapshot(tug: tuple[int, int], cargo: list[dict[str, Any]], rope: list[tuple[int, int]]) -> dict[str, Any]:
    return {
        "tug": [tug[0], tug[1]],
        "cargo": [
            {"id": str(item["id"]), "position": [*map(int, item["position"])], "pulls": int(item["pulls"])}
            for item in cargo
        ],
        "rope_path": [[x, y] for x, y in rope],
        "solved": all(tuple(item["position"]) == tuple(item["pad"]) for item in cargo),
    }


def _initial(ground_truth: dict[str, Any]) -> tuple[dict[str, Any], int, set[tuple[int, int]]]:
    source = ground_truth.get("initial_state")
    if not isinstance(source, dict) or not isinstance(source.get("board"), dict):
        raise ValueError("missing initial freight yard")
    board = source["board"]
    width = int(board["width"])
    height = int(board["height"])
    if not 7 <= width <= 32 or not 7 <= height <= 20:
        raise ValueError("yard dimensions are outside supported bounds")
    start = _coord(board.get("start"))
    walls = _coords(board.get("walls"))
    cargo = board.get("cargo")
    if start is None or walls is None or not isinstance(cargo, list) or not 1 <= len(cargo) <= 6:
        raise ValueError("yard geometry is malformed")
    normalized: list[dict[str, Any]] = []
    ids: set[str] = set()
    for item in cargo:
        if not isinstance(item, dict):
            raise ValueError("cargo record is malformed")
        ident = str(item.get("id") or "")
        position = _coord(item.get("position"))
        pad = _coord(item.get("pad"))
        if not ident or ident in ids or position is None or pad is None or position in walls or pad in walls:
            raise ValueError("cargo record is invalid")
        ids.add(ident)
        normalized.append({"id": ident, "position": [position[0], position[1]], "pad": [pad[0], pad[1]], "pulls": 0})
    if start in walls or len({tuple(item["position"]) for item in normalized}) != len(normalized):
        raise ValueError("yard start or cargo overlaps an obstacle")
    capacity = int(source.get("rope_capacity"))
    if not 8 <= capacity <= 300:
        raise ValueError("rope capacity is outside supported bounds")
    return {"width": width, "height": height, "start": start, "cargo": normalized, "walls": set(walls)}, capacity, set(walls)


def _replay_move(
    tug: tuple[int, int],
    cargo: list[dict[str, Any]],
    rope: list[tuple[int, int]],
    yard: dict[str, Any],
    direction: str,
    capacity: int,
) -> tuple[tuple[int, int], str]:
    dx, dy = DELTAS[direction]
    target = (tug[0] + dx, tug[1] + dy)
    if target in yard["walls"] or not (0 <= target[0] < yard["width"] and 0 <= target[1] < yard["height"]):
        return tug, "blocked_wall"
    if any(tuple(item["position"]) == target for item in cargo):
        return tug, "blocked_cargo"
    tug = target
    rope.append(tug)
    del rope[:-capacity]
    return tug, "move"


def _replay_lasso(cargo: list[dict[str, Any]], rope: list[tuple[int, int]]) -> tuple[str, str]:
    occupied = set(rope)
    for item in cargo:
        position = tuple(item["position"])
        pad = tuple(item["pad"])
        if position == pad:
            continue
        required = {(position[0] + dx, position[1] + dy) for dx, dy in NEIGHBOURS}
        if not required <= occupied:
            continue
        x, y = position
        if x != pad[0]:
            x += 1 if pad[0] > x else -1
        elif y != pad[1]:
            y += 1 if pad[1] > y else -1
        item["position"] = [x, y]
        item["pulls"] += 1
        return str(item["id"]), "snag"
    return "", "lasso_empty"


def _finite_time(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and 0 <= number <= 3_600_000


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return _fail("result payload is not an object")
    if payload.get("mechanic_id") != MECHANIC_ID or ground_truth.get("mechanic_id") != MECHANIC_ID or public_state.get("mechanic_id") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    challenge_id = str(ground_truth.get("challenge_id") or "")
    task_id = str(ground_truth.get("task_id") or "")
    if not challenge_id or payload.get("challenge_id") != challenge_id or public_state.get("challenge_id") != challenge_id:
        return _fail("stale or mismatched challenge")
    if not task_id or payload.get("task_id") != task_id or public_state.get("task_id") != task_id:
        return _fail("task identity mismatch")
    if public_state.get("board") != (ground_truth.get("initial_state") or {}).get("board"):
        return _fail("public/private yard geometry differs")
    if public_state.get("rope_capacity") != (ground_truth.get("initial_state") or {}).get("rope_capacity"):
        return _fail("public/private rope contract differs")
    condition = ground_truth.get("control_condition")
    if public_state.get("control_condition") != condition:
        return _fail("public/private control condition differs")
    expected_source = {"simplified": "control_buttons", "full": "keyboard"}.get(str((condition or {}).get("interaction") or ""))
    if condition is not None and expected_source is None:
        return _fail("invalid lasso interaction condition")
    try:
        yard, capacity, _ = _initial(ground_truth)
    except (TypeError, ValueError, KeyError) as exc:
        return _fail(f"invalid yard contract: {exc}")
    actions = payload.get("actions")
    if not isinstance(actions, list) or not 1 <= len(actions) <= 1200:
        return _fail("missing or oversized action transcript")
    tug = yard["start"]
    cargo = [dict(item, position=list(item["position"])) for item in yard["cargo"]]
    rope = [tug]
    resets = 0
    lassos = 0
    previous_t = -1.0
    for index, action in enumerate(actions, start=1):
        if not isinstance(action, dict) or action.get("sequence") != index:
            return _fail(f"action {index} has a non-contiguous sequence")
        if expected_source is not None and action.get("input_source") != expected_source:
            return _fail(f"action {index} uses the wrong interaction input")
        if not _finite_time(action.get("t_ms")) or float(action["t_ms"]) < previous_t:
            return _fail(f"action {index} timestamp is invalid")
        previous_t = float(action["t_ms"])
        before = _snapshot(tug, cargo, rope)
        if action.get("before") != before:
            return _fail(f"action {index} before-state does not replay")
        issued = str(action.get("issued") or "")
        if issued in DELTAS:
            action_type = "move"
            tug, outcome = _replay_move(tug, cargo, rope, yard, issued, capacity)
        elif issued == "LASSO":
            action_type = "lasso"
            cargo_id, outcome = _replay_lasso(cargo, rope)
            if cargo_id:
                outcome = f"snag:{cargo_id}"
                lassos += 1
        elif issued == "RESET":
            action_type = "reset"
            tug = yard["start"]
            cargo = [dict(item, position=list(item["position"]), pulls=0) for item in yard["cargo"]]
            rope = [tug]
            outcome = "reset"
            resets += 1
        else:
            return _fail(f"action {index} has an unknown command")
        after = _snapshot(tug, cargo, rope)
        if action.get("type") != action_type or action.get("outcome") != outcome or action.get("after") != after:
            return _fail(f"action {index} disagrees with the visible transition")
    final_state = _snapshot(tug, cargo, rope)
    if payload.get("final_state") != final_state:
        return _fail("final state does not match the replay")
    if payload.get("completed") is not True or not final_state["solved"]:
        return _fail("yard was certified before every crate reached its pad")
    required_lassos = sum(
        abs(int(item["pad"][0]) - int(item["position"][0])) + abs(int(item["pad"][1]) - int(item["position"][1]))
        for item in yard["cargo"]
    )
    if lassos < required_lassos:
        return _fail("cargo reached pads without enough legal snag transitions")
    return {
        "graded": True,
        "passed": True,
        "score": 100,
        "feedback": f"replayed {len(actions)} visible actions, {lassos} legal snags, {resets} reset(s)",
    }
