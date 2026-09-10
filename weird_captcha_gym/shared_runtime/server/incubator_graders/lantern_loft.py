from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "lantern_loft"
SIDES = ("n", "e", "s", "w")
OPPOSITE = {"n": "s", "e": "w", "s": "n", "w": "e"}
DELTA = {"n": (0, -1), "e": (1, 0), "s": (0, 1), "w": (-1, 0)}


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _same_condition(ground_truth: dict[str, Any], public_state: dict[str, Any]) -> tuple[str, int]:
    truth = ground_truth.get("control_condition")
    if truth != public_state.get("control_condition"):
        raise ValueError("public interaction condition differs from the loft contract")
    if truth is None:
        return "full", 4
    interaction = str(truth.get("interaction") or "")
    difficulty = int(truth.get("difficulty") or 0)
    if interaction not in {"simplified", "full"} or not 1 <= difficulty <= 5:
        raise ValueError("invalid loft interaction condition")
    return interaction, difficulty


def _xy(slot: int, side: int) -> tuple[int, int]:
    return slot % side, slot // side


def _adjacent(a: int, b: int, side: int) -> tuple[bool, str | None]:
    ax, ay = _xy(a, side)
    bx, by = _xy(b, side)
    delta = (bx - ax, by - ay)
    for name, expected in DELTA.items():
        if delta == expected:
            return True, name
    return False, None


def _module_map(world: dict[str, Any]) -> dict[str, dict[str, Any]]:
    modules = world.get("modules")
    if not isinstance(modules, list):
        raise ValueError("loft module geometry is missing")
    result = {str(module["id"]): module for module in modules if isinstance(module, dict) and module.get("id")}
    if len(result) != len(modules):
        raise ValueError("loft module IDs are not unique")
    return result


def _connected(world: dict[str, Any], board: list[str | None], a: int, b: int) -> bool:
    side_size = int(world.get("board_side") or 0)
    adjacent, side = _adjacent(a, b, side_size)
    if not adjacent or side is None:
        return False
    ids = board[a], board[b]
    if ids[0] is None or ids[1] is None:
        return False
    modules = _module_map(world)
    first = modules.get(str(ids[0]))
    second = modules.get(str(ids[1]))
    if first is None or second is None:
        return False
    if not bool((first.get("openings") or {}).get(side)):
        return False
    opposite = OPPOSITE[side]
    if not bool((second.get("openings") or {}).get(opposite)):
        return False
    delta = abs(int(first.get("height") or 0) - int(second.get("height") or 0))
    if delta == 0:
        return True
    max_delta = int((world.get("rules") or {}).get("max_height_delta") or 1)
    return delta <= max_delta and (
        bool((first.get("stairs") or {}).get(side))
        or bool((second.get("stairs") or {}).get(opposite))
    )


def replay_events(events: list[dict[str, Any]], world: dict[str, Any], interaction: str) -> tuple[dict[str, Any], str | None]:
    side_size = int(world.get("board_side") or 0)
    if side_size != 3:
        return {}, "loft board geometry is invalid"
    board = [str(item) if item is not None else None for item in (world.get("board") or [])]
    if len(board) != side_size * side_size:
        return {}, "loft board has the wrong number of slots"
    empty = int(world.get("empty_slot"))
    carrier = int(world.get("carrier_slot"))
    exit_slot = int(world.get("exit_slot"))
    if not 0 <= empty < len(board) or board[empty] is not None:
        return {}, "loft empty rail position is invalid"
    if not 0 <= carrier < len(board) or board[carrier] is None:
        return {}, "loft carrier start is invalid"
    state = {"board": board, "empty_slot": empty, "carrier_slot": carrier, "finished": False}
    module_map = _module_map(world)
    slide_source = "drag" if interaction == "full" else "proxy_slide"
    step_source = "surface_click" if interaction == "full" else "proxy_step"
    previous_t = -1.0
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict) or int(event.get("seq", -1)) != index:
            return state, f"event {index} has invalid sequence numbering"
        try:
            t_ms = float(event.get("t_ms"))
        except (TypeError, ValueError):
            return state, f"event {index} time is invalid"
        if not math.isfinite(t_ms) or t_ms < previous_t or t_ms > 900_000:
            return state, f"event {index} time is reversed or exceeds the session bound"
        previous_t = t_ms
        if state["finished"]:
            return state, f"event {index} occurs after terminal state"
        kind = str(event.get("kind") or "")
        if kind == "slide":
            if event.get("input_source") != slide_source:
                return state, f"event {index} uses the wrong slide input surface"
            try:
                source = int(event.get("from_slot"))
                target = int(event.get("to_slot"))
            except (TypeError, ValueError):
                return state, f"event {index} has an invalid slider position"
            adjacent, _ = _adjacent(source, target, side_size)
            module_id = str(event.get("module_id") or "")
            if not adjacent or target != state["empty_slot"] or not 0 <= source < len(board):
                return state, f"event {index} does not slide into the adjacent free rail position"
            if source == state["carrier_slot"] or board[source] != module_id or module_id not in module_map:
                return state, f"event {index} moves the carrier's module or an unknown module"
            state["board"][target] = module_id
            state["board"][source] = None
            state["empty_slot"] = source
        elif kind == "step":
            if event.get("input_source") != step_source:
                return state, f"event {index} uses the wrong carrier input surface"
            try:
                source = int(event.get("from_slot"))
                target = int(event.get("to_slot"))
            except (TypeError, ValueError):
                return state, f"event {index} has an invalid carrier slot"
            if source != state["carrier_slot"] or not 0 <= target < len(board) or not _connected(world, board, source, target):
                return state, f"event {index} is not a legal same-height or stair connection"
            state["carrier_slot"] = target
        elif kind == "finish":
            if event.get("input_source") != "physical_contact" or state["carrier_slot"] != exit_slot:
                return state, f"event {index} certifies without reaching the exit landing"
            state["finished"] = True
        elif kind in {"abandon", "fail"}:
            return state, "failure or abandonment cannot be a passing transcript"
        else:
            return state, f"event {index} has an unknown kind"
    return state, None


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if str(payload.get("mechanic_id") or "") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    task_id = str(ground_truth.get("task_id") or "")
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if not task_id or str(payload.get("task_id") or "") != task_id or str(public_state.get("task_id") or "") != task_id:
        return _fail("task binding mismatch")
    if not challenge_id or str(payload.get("challenge_id") or "") != challenge_id or str(public_state.get("challenge_id") or "") != challenge_id:
        return _fail("stale or cross-seed loft")
    try:
        interaction, _difficulty = _same_condition(ground_truth, public_state)
    except (TypeError, ValueError) as exc:
        return _fail(str(exc))
    if payload.get("interaction") != interaction:
        return _fail("submitted interaction mode does not match the task")
    if payload.get("completed") is not True:
        return _fail("the lantern carrier did not reach the exit landing")
    events = payload.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 4000:
        return _fail("loft transcript is missing or outside limits")
    try:
        if ground_truth.get("world") != public_state.get("world"):
            return _fail("public loft geometry differs from verifier geometry")
        state, error = replay_events(events, ground_truth["world"], interaction)
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        return _fail(f"invalid loft transcript: {exc}")
    if error:
        return _fail(error)
    if not state.get("finished"):
        return _fail("transcript never records physical contact with the exit landing")
    return {
        "graded": True,
        "passed": True,
        "score": 100,
        "feedback": f"3D loft replay reached exit slot {ground_truth['world']['exit_slot']} after {len(events)} events",
    }


__all__ = ["grade", "replay_events"]
