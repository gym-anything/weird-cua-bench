"""Independent replay grader for Hearthlift Courier."""

from __future__ import annotations

import copy
import math
from typing import Any


MECHANIC_ID = "hearthlift_courier"
DIRECTIONS = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _key(x: int, y: int) -> str:
    return f"{int(x)},{int(y)}"


def _snapshot(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "avatar": copy.deepcopy(state["avatar"]),
        "boxes": copy.deepcopy(state["boxes"]),
        "held": state.get("held"),
        "delivered": bool(state.get("delivered")),
    }


def _box_at(state: dict[str, Any], x: int, y: int) -> dict[str, Any] | None:
    for box in state["boxes"]:
        if int(box["x"]) == int(x) and int(box["y"]) == int(y):
            return box
    return None


def _cell(world: dict[str, Any], x: int, y: int) -> dict[str, Any] | None:
    return (world.get("cell_map") or {}).get(_key(x, y))


def _apply_action(world: dict[str, Any], state: dict[str, Any], event: dict[str, Any]) -> str | None:
    event_type = str(event.get("type") or "")
    if event_type == "camera":
        delta = float(event.get("delta"))
        if not math.isfinite(delta) or abs(delta) > 5:
            raise ValueError("camera orbit delta is invalid")
        before = float(state.get("camera_yaw", 0.0))
        if abs(float(event.get("camera_before")) - before) > 1e-4:
            raise ValueError("camera event starts from stale yaw")
        state["camera_yaw"] = round(before + delta, 4)
        if abs(float(event.get("camera_after")) - state["camera_yaw"]) > 1e-4:
            raise ValueError("camera event reports false yaw")
        return None
    if event_type == "move":
        direction = str(event.get("direction") or "")
        if direction not in DIRECTIONS:
            raise ValueError("move direction is invalid")
        dx, dy = DIRECTIONS[direction]
        avatar = state["avatar"]
        tx, ty = int(avatar["x"]) + dx, int(avatar["y"]) + dy
        cell = _cell(world, tx, ty)
        if cell is None:
            raise ValueError("movement left the visible voxel garden")
        box = _box_at(state, tx, ty)
        if box is not None:
            top = int(cell["height"]) + 1
            if 0 <= int(avatar["z"]) - top <= 1:
                avatar.update({"x": tx, "y": ty, "z": top})
                return None
            dest = _cell(world, tx + dx, ty + dy)
            if (
                state.get("held") is not None
                or dest is None
                or _box_at(state, tx + dx, ty + dy) is not None
                or int(cell["height"]) != int(avatar["z"])
                or int(dest["height"]) != int(avatar["z"])
                or str(box.get("kind")) == "cargo"
            ):
                raise ValueError("box push is not legal")
            box.update({"x": tx + dx, "y": ty + dy, "base_z": int(dest["height"])})
            avatar.update({"x": tx, "y": ty, "z": int(cell["height"])})
            return str(box.get("id"))
        if abs(int(cell["height"]) - int(avatar["z"])) > 1:
            raise ValueError("movement climbed more than one voxel")
        avatar.update({"x": tx, "y": ty, "z": int(cell["height"])})
        return None
    if event_type == "climb":
        direction = str(event.get("direction") or "")
        if direction not in DIRECTIONS:
            raise ValueError("climb direction is invalid")
        dx, dy = DIRECTIONS[direction]
        avatar = state["avatar"]
        tx, ty = int(avatar["x"]) + dx, int(avatar["y"]) + dy
        cell = _cell(world, tx, ty)
        box = _box_at(state, tx, ty)
        if cell is None or box is None or int(cell["height"]) != int(avatar["z"]):
            raise ValueError("climb requires an adjacent same-level box")
        avatar.update({"x": tx, "y": ty, "z": int(cell["height"]) + 1})
        return str(box.get("id"))
    if event_type == "pickup":
        if state.get("held") is not None:
            raise ValueError("already carrying cargo")
        avatar = state["avatar"]
        cargo = next((box for box in state["boxes"] if box.get("kind") == "cargo"), None)
        if cargo is None or abs(int(cargo["x"]) - int(avatar["x"])) + abs(int(cargo["y"]) - int(avatar["y"])) != 1 or int(cargo["base_z"]) != int(avatar["z"]):
            raise ValueError("cargo is not adjacent at the current height")
        state["held"] = str(cargo["id"])
        state["boxes"] = [box for box in state["boxes"] if box is not cargo]
        return str(cargo.get("id"))
    if event_type == "drop":
        avatar = state["avatar"]
        hearth = world["hearth"]
        if state.get("held") is None or [int(avatar["x"]), int(avatar["y"])] != [int(hearth["x"]), int(hearth["y"])] or int(avatar["z"]) != int(hearth["height"]):
            raise ValueError("cargo was not dropped on the hearth")
        state["held"] = None
        state["delivered"] = True
        return "marked-cargo"
    raise ValueError(f"unknown event type {event_type!r}")


def _expected_source(interaction: str, event_type: str) -> str:
    if event_type == "camera":
        return "camera_drag" if interaction == "full" else "camera_button"
    if event_type == "move":
        return "keyboard_move" if interaction == "full" else "proxy_move"
    if event_type in {"climb", "pickup", "drop"}:
        return "keyboard_action" if interaction == "full" else "proxy_action"
    return "certify_button"


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    if payload.get("mechanic_id") != MECHANIC_ID or truth.get("mechanic_id") != MECHANIC_ID or public.get("mechanic_id") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    if payload.get("task_id") != truth.get("task_id") or payload.get("challenge_id") != truth.get("challenge_id") or public.get("challenge_id") != truth.get("challenge_id"):
        return _fail("stale task or challenge")
    expected_public_world = copy.deepcopy(truth.get("world") or {})
    expected_public_world.pop("cell_map", None)
    expected_public_world.pop("route", None)
    expected_public_world.pop("stages", None)
    if public.get("world") != expected_public_world:
        return _fail("visible voxel geometry differs from the replay geometry")
    condition = truth.get("control_condition")
    if public.get("control_condition") != condition:
        return _fail("interaction condition is not bound to the challenge")
    interaction = str((condition or {}).get("interaction") or "full")
    if interaction not in {"full", "simplified"}:
        return _fail("invalid interaction condition")
    events = payload.get("events")
    if not isinstance(events, list) or not events or len(events) > 1200:
        return _fail("empty or oversized Hearthlift transcript")
    state: dict[str, Any] = {
        "avatar": copy.deepcopy((truth.get("world") or {}).get("avatar_start")),
        "boxes": copy.deepcopy((truth.get("world") or {}).get("boxes") or []),
        "held": None,
        "delivered": False,
        "camera_yaw": float(((truth.get("world") or {}).get("camera") or {}).get("initial_yaw", 0.0)),
    }
    camera_events = 0
    pickup = drop = 0
    certified = False
    try:
        for sequence, event in enumerate(events, 1):
            if not isinstance(event, dict) or event.get("seq") != sequence:
                return _fail(f"event {sequence} sequence is malformed")
            event_type = str(event.get("type") or "")
            if certified:
                return _fail("events appear after certification")
            source = str(event.get("input_source") or "")
            expected_source = _expected_source(interaction, event_type)
            if source != expected_source:
                return _fail(f"{event_type} used {source!r}, expected {expected_source!r}")
            if event_type == "certify":
                if event.get("before") != _snapshot(state) or event.get("after") != _snapshot(state):
                    return _fail("certification snapshot is stale")
                certified = True
                continue
            if event.get("before") != _snapshot(state):
                return _fail(f"event {sequence} starts from a stale visible state")
            _apply_action(truth["world"], state, event)
            if event.get("after") != _snapshot(state):
                return _fail(f"event {sequence} reports a state not produced by voxel replay")
            if event_type == "camera":
                camera_events += 1
            if event_type == "pickup":
                pickup += 1
            if event_type == "drop":
                drop += 1
        if not certified or payload.get("completed") is not True:
            return _fail("attempt was not certified")
        if camera_events < 1:
            return _fail("the 3D garden was never inspected from another camera angle")
        if pickup != 1 or drop != 1 or not state.get("delivered") or state.get("held") is not None:
            return _fail("marked cargo was not carried and burned at the hearth")
        return {"graded": True, "passed": True, "score": 100, "feedback": "voxel replay delivered the marked cargo through the inspected stacked route"}
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return _fail(f"invalid Hearthlift replay: {exc}")


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    """Expose only a construction witness to the opt-in local cheat route."""
    return {
        "mechanic_id": MECHANIC_ID,
        "challenge_id": ground_truth.get("challenge_id"),
        "solution_action_count": len(ground_truth.get("solution_actions") or []),
    }


__all__ = ["MECHANIC_ID", "grade", "cheat"]
