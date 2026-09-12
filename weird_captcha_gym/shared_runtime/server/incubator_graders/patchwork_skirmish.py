from __future__ import annotations

import copy
import heapq
import itertools
from typing import Any


MECHANIC_ID = "patchwork_skirmish"
PLAYER = 0
ENEMY = 1
DIRS = {
    "north": (-1, 0),
    "south": (1, 0),
    "west": (0, -1),
    "east": (0, 1),
}


def _live(units: dict[str, dict[str, Any]], owner: int | None = None) -> list[dict[str, Any]]:
    return [
        unit for unit in units.values()
        if unit["cells"] and (owner is None or int(unit["owner"]) == owner)
    ]


def _distance(cells_a: list[list[int]], cells_b: list[list[int]]) -> int:
    return min(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a in cells_a for b in cells_b)


def _adjacent(cells_a: list[list[int]], cells_b: list[list[int]]) -> bool:
    return _distance(cells_a, cells_b) == 1


def _occupied(units: dict[str, dict[str, Any]], skip: str | None = None) -> set[tuple[int, int]]:
    return {
        (int(row), int(col))
        for unit_id, unit in units.items()
        if unit_id != skip and unit["cells"]
        for row, col in unit["cells"]
    }


def _translated(cells: list[list[int]], direction: str) -> list[list[int]]:
    dr, dc = DIRS[direction]
    return [[int(row) + dr, int(col) + dc] for row, col in cells]


def _valid_translation(
    units: dict[str, dict[str, Any]], unit_id: str, direction: str, width: int, height: int
) -> list[list[int]] | None:
    if direction not in DIRS:
        return None
    cells = _translated(units[unit_id]["cells"], direction)
    if any(row < 0 or row >= height or col < 0 or col >= width for row, col in cells):
        return None
    occupied = _occupied(units, skip=unit_id)
    if any((row, col) in occupied for row, col in cells):
        return None
    return cells


def _remove_edge_cell(unit: dict[str, Any], power: int) -> int:
    removed = min(max(0, int(power)), len(unit["cells"]))
    if removed:
        del unit["cells"][-removed:]
    return removed


def initial_state(world: dict[str, Any]) -> dict[str, Any]:
    units = {}
    for raw in world.get("units") or []:
        unit = copy.deepcopy(raw)
        unit["cells"] = [[int(cell[0]), int(cell[1])] for cell in unit["cells"]]
        unit["moves_left"] = int(world["movement_points"])
        unit["attacks_left"] = 1
        units[str(unit["id"])] = unit
    return {
        "turn": 0,
        "units": units,
        "terminal": False,
        "won": False,
        "action_count": 0,
        "enemy_actions": 0,
        "last_response": "RIVALS WAIT IN THEIR STITCHES",
    }


def _nearest_enemy(units: dict[str, dict[str, Any]], unit: dict[str, Any]) -> dict[str, Any] | None:
    candidates = _live(units, ENEMY if int(unit["owner"]) == PLAYER else PLAYER)
    if not candidates:
        return None
    return min(candidates, key=lambda other: (_distance(unit["cells"], other["cells"]), str(other["id"])))


def _enemy_response(state: dict[str, Any], world: dict[str, Any]) -> None:
    notes: list[str] = []
    width, height = int(world["width"]), int(world["height"])
    for enemy in sorted(_live(state["units"], ENEMY), key=lambda item: str(item["id"])):
        if not enemy["cells"]:
            continue
        target = _nearest_enemy(state["units"], enemy)
        if target is None:
            break
        if _adjacent(enemy["cells"], target["cells"]):
            removed = _remove_edge_cell(target, 1)
            state["enemy_actions"] += 1
            notes.append(f"{enemy['id']} chips {target['id']} ({removed} cell)")
            continue
        steps = int(world["enemy_movement_points"])
        for _ in range(steps):
            target = _nearest_enemy(state["units"], enemy)
            if target is None or not enemy["cells"]:
                break
            choices = []
            for direction in DIRS:
                cells = _valid_translation(state["units"], str(enemy["id"]), direction, width, height)
                if cells is not None:
                    choices.append((_distance(cells, target["cells"]), direction, cells))
            if not choices:
                break
            choices.sort(key=lambda item: (item[0], ("north", "west", "south", "east").index(item[1])))
            _, direction, cells = choices[0]
            enemy["cells"] = cells
            state["enemy_actions"] += 1
            notes.append(f"{enemy['id']} drifts {direction}")
    state["last_response"] = "; ".join(notes) if notes else "RIVALS HAVE NO LEGAL RESPONSE"


def apply_event(state: dict[str, Any], world: dict[str, Any], event: dict[str, Any]) -> None:
    if state["terminal"]:
        raise ValueError("the skirmish is already over")
    event_type = str(event.get("type") or "")
    units = state["units"]
    if event_type == "move":
        unit_id = str(event.get("unit_id") or "")
        direction = str(event.get("direction") or "")
        unit = units.get(unit_id)
        if unit is None or int(unit["owner"]) != PLAYER or not unit["cells"]:
            raise ValueError("move must select a living player patch")
        if int(unit["moves_left"]) <= 0:
            raise ValueError("that patch has spent its movement")
        cells = _valid_translation(units, unit_id, direction, int(world["width"]), int(world["height"]))
        if cells is None:
            raise ValueError("move collides with the board or another patch")
        unit["cells"] = cells
        unit["moves_left"] -= 1
    elif event_type == "attack":
        unit_id = str(event.get("unit_id") or "")
        target_id = str(event.get("target_id") or "")
        unit = units.get(unit_id)
        target = units.get(target_id)
        if unit is None or target is None or int(unit["owner"]) != PLAYER or int(target["owner"]) != ENEMY:
            raise ValueError("attack must select a player and rival patch")
        if not unit["cells"] or not target["cells"] or int(unit["attacks_left"]) <= 0:
            raise ValueError("that patch cannot attack now")
        if not _adjacent(unit["cells"], target["cells"]):
            raise ValueError("the rival patch is not neighboring")
        _remove_edge_cell(target, int(world["attack_power"]))
        unit["attacks_left"] -= 1
    elif event_type == "end_turn":
        if not _live(units, ENEMY):
            state["terminal"] = True
            state["won"] = bool(_live(units, PLAYER))
            return
        _enemy_response(state, world)
        state["turn"] += 1
        for unit in _live(units):
            if int(unit["owner"]) == PLAYER:
                unit["moves_left"] = int(world["movement_points"])
                unit["attacks_left"] = 1
        if not _live(units, PLAYER) or state["turn"] >= int(world["max_turns"]):
            state["terminal"] = True
            state["won"] = False
    else:
        raise ValueError("unknown patchwork action")
    state["action_count"] += 1


def summary(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "turn": int(state["turn"]),
        "units": {
            unit_id: {
                "cells": copy.deepcopy(unit["cells"]),
                "moves_left": int(unit["moves_left"]),
                "attacks_left": int(unit["attacks_left"]),
            }
            for unit_id, unit in sorted(state["units"].items())
        },
        "terminal": bool(state["terminal"]),
        "won": bool(state["won"]),
        "action_count": int(state["action_count"]),
        "enemy_actions": int(state["enemy_actions"]),
        "last_response": str(state["last_response"]),
    }


def _search_key(state: dict[str, Any]) -> tuple[Any, ...]:
    """Return the future-relevant portion of a replay state."""
    return (
        int(state["turn"]),
        bool(state["terminal"]),
        bool(state["won"]),
        tuple(
            (
                unit_id,
                tuple(tuple(cell) for cell in unit["cells"]),
                int(unit["moves_left"]),
                int(unit["attacks_left"]),
            )
            for unit_id, unit in sorted(state["units"].items())
        ),
    )


def _search_score(state: dict[str, Any], depth: int) -> float:
    """Prefer damage, adjacency, and surviving area during oracle search."""
    if state["terminal"]:
        return -100000.0 if state["won"] else 100000.0
    players = _live(state["units"], PLAYER)
    enemies = _live(state["units"], ENEMY)
    enemy_cells = sum(len(unit["cells"]) for unit in enemies)
    player_cells = sum(len(unit["cells"]) for unit in players)
    distances = (
        sum(_distance(player["cells"], enemy["cells"]) for player in players for enemy in enemies)
        if players and enemies
        else 0
    )
    adjacent_pairs = sum(
        1 for player in players for enemy in enemies if _adjacent(player["cells"], enemy["cells"])
    )
    fragile = sum(max(0, 2 - len(unit["cells"])) for unit in players)
    return enemy_cells * 30 - player_cells * 2 + distances * 0.5 - adjacent_pairs * 20 + fragile * 40 + depth * 0.01


def _search_actions(state: dict[str, Any], world: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for unit_id, unit in sorted(state["units"].items()):
        if int(unit["owner"]) != PLAYER or not unit["cells"]:
            continue
        if int(unit["attacks_left"]) > 0:
            for target_id, target in sorted(state["units"].items()):
                if int(target["owner"]) == ENEMY and target["cells"] and _adjacent(unit["cells"], target["cells"]):
                    actions.append({"type": "attack", "input_source": "board_direct", "unit_id": unit_id, "target_id": target_id})
        if int(unit["moves_left"]) > 0:
            for direction in ("north", "west", "south", "east"):
                if _valid_translation(state["units"], unit_id, direction, int(world["width"]), int(world["height"])) is not None:
                    actions.append({"type": "move", "input_source": "board_direct", "unit_id": unit_id, "direction": direction})
    actions.append({"type": "end_turn", "input_source": "turn_button"})
    return actions


def _search_plan(world: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Find a bounded winning replay when the greedy oracle is unsafe."""
    initial = initial_state(world)
    counter = itertools.count()
    queue: list[tuple[float, int, dict[str, Any], list[dict[str, Any]]]] = [
        (_search_score(initial, 0), next(counter), initial, [])
    ]
    best_depth = {_search_key(initial): 0}
    expanded = 0
    max_depth = int(world["max_turns"]) * 5 + 20
    while queue and expanded < 20000:
        _, _, state, path = heapq.heappop(queue)
        expanded += 1
        if state["terminal"]:
            if state["won"]:
                return path
            continue
        if len(path) >= max_depth:
            continue
        for action in _search_actions(state, world):
            next_state = copy.deepcopy(state)
            try:
                apply_event(next_state, world, action)
            except (KeyError, TypeError, ValueError):
                continue
            depth = len(path) + 1
            key = _search_key(next_state)
            if key in best_depth and best_depth[key] <= depth:
                continue
            best_depth[key] = depth
            next_event = {"sequence": depth, **action}
            heapq.heappush(
                queue,
                (_search_score(next_state, depth), next(counter), next_state, path + [next_event]),
            )
    return None


def _failure(feedback: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": feedback}


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if payload.get("mechanic_id") != MECHANIC_ID or ground_truth.get("mechanic_id") != MECHANIC_ID or public_state.get("mechanic_id") != MECHANIC_ID:
        return _failure("mechanic mismatch")
    challenge_id = str(ground_truth.get("challenge_id") or "")
    task_id = str(ground_truth.get("task_id") or "")
    if payload.get("challenge_id") != challenge_id or public_state.get("challenge_id") != challenge_id:
        return _failure("stale challenge")
    if payload.get("task_id") != task_id or public_state.get("task_id") != task_id:
        return _failure("task identity mismatch")
    if public_state.get("world") != ground_truth.get("world"):
        return _failure("public world does not match replay world")
    if public_state.get("control_condition") != ground_truth.get("control_condition"):
        return _failure("public condition does not match replay condition")
    world = ground_truth.get("world")
    if not isinstance(world, dict):
        return _failure("missing world")
    interaction = str((ground_truth.get("control_condition") or {}).get("interaction") or "full")
    expected_source = "board_direct" if interaction == "full" else "command_panel"
    events = payload.get("events")
    if not isinstance(events, list) or not events or len(events) > 500:
        return _failure("missing or oversized action transcript")
    state = initial_state(world)
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict) or int(event.get("sequence", -1)) != index:
            return _failure(f"action {index} has an invalid sequence")
        event_type = str(event.get("type") or "")
        expected_event_source = "turn_button" if event_type == "end_turn" else expected_source
        if event.get("input_source") != expected_event_source:
            return _failure(f"action {index} used the wrong interaction surface")
        try:
            apply_event(state, world, event)
        except (KeyError, TypeError, ValueError) as exc:
            return _failure(f"action {index} is invalid: {exc}")
    expected = summary(state)
    if payload.get("final_state") != expected:
        return _failure("submitted final state does not match deterministic replay")
    passed = bool(state["terminal"] and state["won"] and _live(state["units"], PLAYER) and not _live(state["units"], ENEMY))
    return {
        "graded": True,
        "passed": passed,
        "score": 100 if passed else 0,
        "feedback": f"turn {state['turn']}; player patches {len(_live(state['units'], PLAYER))}; rival patches {len(_live(state['units'], ENEMY))}; enemy responses {state['enemy_actions']}",
    }


def plan(world: dict[str, Any]) -> list[dict[str, Any]]:
    """Find a robust ordinary-input plan for evidence and unit tests."""
    state = initial_state(world)
    events: list[dict[str, Any]] = []
    source = "board_direct"

    def issue(event_type: str, **details: Any) -> None:
        event_source = "turn_button" if event_type == "end_turn" else source
        event = {"sequence": len(events) + 1, "type": event_type, "input_source": event_source, **details}
        apply_event(state, world, event)
        events.append(event)

    # A bounded greedy controller uses the same visible cells that a human
    # reads. It closes on the nearest rival, chips it, then reuses the patch.
    for _ in range(int(world["max_turns"]) + 2):
        if state["terminal"]:
            break
        for unit in sorted(_live(state["units"], PLAYER), key=lambda item: str(item["id"])):
            unit_id = str(unit["id"])
            if not unit["cells"]:
                continue
            while int(unit["moves_left"]) > 0 and _live(state["units"], ENEMY):
                target = _nearest_enemy(state["units"], unit)
                if target is None or _adjacent(unit["cells"], target["cells"]):
                    break
                choices = []
                for direction in DIRS:
                    cells = _valid_translation(state["units"], unit_id, direction, int(world["width"]), int(world["height"]))
                    if cells is not None:
                        choices.append((_distance(cells, target["cells"]), direction))
                if not choices:
                    break
                choices.sort(key=lambda item: (item[0], ("north", "west", "south", "east").index(item[1])))
                issue("move", unit_id=unit_id, direction=choices[0][1])
            target = _nearest_enemy(state["units"], unit)
            if target is not None and int(unit["attacks_left"]) > 0 and _adjacent(unit["cells"], target["cells"]):
                issue("attack", unit_id=unit_id, target_id=str(target["id"]))
        issue("end_turn")
        if state["terminal"]:
            break
    if state["terminal"] and state["won"]:
        return events
    searched = _search_plan(world)
    if searched is None:
        raise ValueError("patchwork oracle could not find a winning plan")
    return searched


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    return {
        "instruction": "Select a patch, translate its whole footprint toward a neighboring rival, chip one edge cell, and end each turn to read the response.",
        "plan_length": len(plan(ground_truth["world"])),
    }
