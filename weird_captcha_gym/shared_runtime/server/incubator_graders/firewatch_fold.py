from __future__ import annotations

from typing import Any


MECHANIC_ID = "firewatch_fold"
DIRECTIONS = {
    "UP": (0, 1),
    "RIGHT": (1, 0),
    "DOWN": (0, -1),
    "LEFT": (-1, 0),
}


def _point(value: Any) -> tuple[int, int, int]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("player position is malformed")
    if any(isinstance(item, bool) for item in value):
        raise ValueError("boolean position is invalid")
    return int(value[0]), int(value[1]), int(value[2])


def _tower(truth: dict[str, Any]) -> dict[str, Any]:
    tower = truth.get("initial_tower")
    if not isinstance(tower, dict):
        raise ValueError("missing tower")
    return tower


def _index(
    tower: dict[str, Any],
) -> tuple[
    set[tuple[int, int, int]],
    set[tuple[int, int, int]],
    set[tuple[int, int, int]],
    dict[str, set[tuple[int, int, int]]],
]:
    walls: set[tuple[int, int, int]] = set()
    ladders: set[tuple[int, int, int]] = set()
    fires: dict[str, set[tuple[int, int, int]]] = {}
    faces = tower.get("faces")
    if not isinstance(faces, list) or len(faces) != 2:
        raise ValueError("tower must have two faces")
    for face_index, face in enumerate(faces):
        floors = face.get("floors") if isinstance(face, dict) else None
        if not isinstance(floors, list):
            raise ValueError("tower face floors are malformed")
        for floor_index, floor in enumerate(floors):
            if not isinstance(floor, dict):
                raise ValueError("tower floor is malformed")
            for x in floor.get("walls") or []:
                walls.add((face_index, floor_index, int(x)))
            for x in floor.get("ladders") or []:
                ladders.add((face_index, floor_index, int(x)))
            for fire in floor.get("fires") or []:
                if not isinstance(fire, dict):
                    raise ValueError("fire is malformed")
                fire_id = str(fire.get("id") or "")
                if not fire_id:
                    raise ValueError("fire has no id")
                cells = fire.get("cells")
                if not isinstance(cells, list) or not cells:
                    cells = [fire.get("x")]
                for x in cells:
                    fires.setdefault(fire_id, set()).add(
                        (face_index, floor_index, int(x))
                    )
    fire_cells = {point for points in fires.values() for point in points}
    return walls, ladders, fire_cells, fires


def _target(position: tuple[int, int, int], direction: str, width: int) -> tuple[int, int, int]:
    face, floor, x = position
    dx, dy = DIRECTIONS[direction]
    if direction == "RIGHT" and x == width - 1:
        return 1 - face, floor, 0
    if direction == "LEFT" and x == 0:
        return 1 - face, floor, width - 1
    return face, floor + dy, x + dx


def _snapshot(
    position: tuple[int, int, int],
    facing: str,
    cleared: set[str],
    extinguishers_left: int,
    inspection_face: int,
) -> dict[str, Any]:
    return {
        "player": [position[0], position[1], position[2]],
        "facing": facing,
        "cleared_fires": sorted(cleared),
        "extinguishers_left": int(extinguishers_left),
        "inspection_face": int(inspection_face),
    }


def _mismatch(index: int, field: str, expected: Any, actual: Any) -> dict[str, Any]:
    return {
        "graded": True,
        "passed": False,
        "feedback": f"action {index} has inconsistent {field}: expected {expected!r}, got {actual!r}",
    }


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if str(payload.get("mechanic_id") or "") != MECHANIC_ID:
        return {"graded": True, "passed": False, "feedback": "mechanic mismatch"}
    if str(ground_truth.get("mechanic_id") or "") != MECHANIC_ID:
        return {"graded": True, "passed": False, "feedback": "ground-truth mechanic mismatch"}
    if str(public_state.get("mechanic_id") or "") != MECHANIC_ID:
        return {"graded": True, "passed": False, "feedback": "public-state mechanic mismatch"}
    challenge_id = str(ground_truth.get("challenge_id") or "")
    task_id = str(ground_truth.get("task_id") or "")
    if not challenge_id or str(payload.get("challenge_id") or "") != challenge_id:
        return {"graded": True, "passed": False, "feedback": "stale challenge"}
    if str(public_state.get("challenge_id") or "") != challenge_id:
        return {"graded": True, "passed": False, "feedback": "public-state challenge mismatch"}
    if not task_id or str(payload.get("task_id") or "") != task_id or str(public_state.get("task_id") or "") != task_id:
        return {"graded": True, "passed": False, "feedback": "task identity mismatch"}
    if public_state.get("tower") != ground_truth.get("initial_tower"):
        return {"graded": True, "passed": False, "feedback": "visible and replay tower geometry differ"}
    if public_state.get("extinguisher_count") != ground_truth.get("extinguisher_count"):
        return {"graded": True, "passed": False, "feedback": "extinguisher stock differs from replay"}

    condition = ground_truth.get("control_condition")
    if condition != public_state.get("control_condition"):
        return {"graded": True, "passed": False, "feedback": "interaction condition differs between public and hidden state"}
    interaction = str((condition or {}).get("interaction") or ground_truth.get("interaction") or "full")
    expected_sources = {
        "MOVE": "keyboard" if interaction == "full" else "control_buttons",
        "EXTINGUISH": "keyboard" if interaction == "full" else "extinguish_button",
        "INSPECT": "eye_button",
    }
    if interaction not in {"full", "simplified"}:
        return {"graded": True, "passed": False, "feedback": "invalid interaction condition"}

    try:
        tower = _tower(ground_truth)
        walls, ladder_cells, fire_cells, fire_positions = _index(tower)
        position = _point(tower.get("start"))
        resident = _point(tower.get("resident"))
        width = int(tower.get("floor_width"))
        floor_count = int(tower.get("floor_count"))
        stock = int(ground_truth.get("extinguisher_count"))
    except (TypeError, ValueError, KeyError) as exc:
        return {"graded": True, "passed": False, "feedback": f"invalid tower contract: {exc}"}

    actions = payload.get("actions")
    if not isinstance(actions, list) or not (1 <= len(actions) <= 900):
        return {"graded": True, "passed": False, "feedback": "action transcript is missing or outside limits"}

    facing = "RIGHT"
    inspection_face = position[0]
    cleared: set[str] = set()
    movement_count = 0
    extinguish_count = 0
    inspection_count = 0

    for index, event in enumerate(actions, start=1):
        if not isinstance(event, dict):
            return {"graded": True, "passed": False, "feedback": f"action {index} is not an object"}
        if event.get("sequence") != index:
            return _mismatch(index, "sequence", index, event.get("sequence"))
        action = str(event.get("action") or "")
        if action not in expected_sources:
            return {"graded": True, "passed": False, "feedback": f"action {index} has invalid type"}
        if event.get("input_source") != expected_sources[action]:
            return {
                "graded": True,
                "passed": False,
                "feedback": f"action {index} used {event.get('input_source')!r}, expected {expected_sources[action]!r}",
            }
        before = _snapshot(position, facing, cleared, stock, inspection_face)
        outcome = ""
        direction = event.get("direction")
        if action == "MOVE":
            movement_count += 1
            if not isinstance(direction, str) or direction not in DIRECTIONS:
                return {"graded": True, "passed": False, "feedback": f"action {index} has invalid movement direction"}
            facing = str(direction)
            target = _target(position, facing, width)
            if target in walls:
                outcome = "blocked_wall"
            elif target in fire_cells and next(
                (
                    fire_id
                    for fire_id, points in fire_positions.items()
                    if target in points
                ),
                None,
            ) not in cleared:
                outcome = "blocked_fire"
            elif direction in {"UP", "DOWN"}:
                ladder_position = position if direction == "UP" else target
                if ladder_position not in ladder_cells or not (0 <= target[1] < floor_count):
                    outcome = "blocked_ladder"
                else:
                    position = target
                    outcome = "climbed"
            else:
                position = target
                outcome = "seam_crossed" if target[0] != before["player"][0] else "walked"
        elif action == "EXTINGUISH":
            if direction != facing:
                return _mismatch(index, "direction", facing, direction)
            target = _target(position, facing, width)
            fire_id = next(
                (
                    item
                    for item, points in fire_positions.items()
                    if target in points
                ),
                None,
            )
            if fire_id is None or fire_id in cleared:
                outcome = "no_fire"
            elif stock <= 0:
                outcome = "stock_empty"
            else:
                extinguish_count += 1
                cleared.add(fire_id)
                stock -= 1
                outcome = "extinguished"
        else:
            inspection_count += 1
            expected_face = 1 - position[0]
            if event.get("face") != expected_face:
                return _mismatch(index, "face", expected_face, event.get("face"))
            inspection_face = expected_face
            outcome = "inspected"

        after = _snapshot(position, facing, cleared, stock, inspection_face)
        expected = {
            "sequence": index,
            "action": action,
            "input_source": expected_sources[action],
            "before": before,
            "after": after,
            "outcome": outcome,
        }
        if action in {"MOVE", "EXTINGUISH"}:
            expected["direction"] = direction
        if action == "INSPECT":
            expected["face"] = inspection_face
        for field, expected_value in expected.items():
            if event.get(field) != expected_value:
                return _mismatch(index, field, expected_value, event.get(field))

    expected_final = _snapshot(position, facing, cleared, stock, inspection_face)
    if payload.get("final_state") != expected_final:
        return {"graded": True, "passed": False, "feedback": "submitted final state does not match replay"}
    try:
        submitted_used = int(payload.get("extinguishers_used"))
    except (TypeError, ValueError):
        return {"graded": True, "passed": False, "feedback": "extinguisher usage is invalid"}
    if submitted_used != extinguish_count or submitted_used != int(ground_truth.get("extinguisher_count")) - stock:
        return {"graded": True, "passed": False, "feedback": "extinguisher usage does not match replay"}
    completed = payload.get("completed") is True
    passed = completed and position == resident and movement_count > 0 and stock >= 0
    return {
        "graded": True,
        "passed": passed,
        "feedback": (
            f"resident {'reached' if position == resident else 'not reached'}; "
            f"face inspections {inspection_count}; fires cleared {len(cleared)}; "
            f"extinguishers left {stock}; actions {len(actions)}"
        ),
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    return {
        "route": ground_truth.get("solution_actions") or [],
        "instruction": "Choose a route whose fire cost fits the stock, walk the ladders, and reach the resident.",
        "answers": [],
    }
