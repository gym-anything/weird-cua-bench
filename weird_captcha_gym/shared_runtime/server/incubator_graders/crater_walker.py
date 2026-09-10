"""Independent replay grader for the original Crater Walker contact model."""

from __future__ import annotations

import copy
import math
from typing import Any


MECHANIC_ID = "crater_walker"
LEGS = ("front_left", "front_right", "rear_left", "rear_right")
ACTUATORS = ("yaw", "lift", "extend")
BASE_X = {"front_left": 0.84, "front_right": 0.84, "rear_left": -0.84, "rear_right": -0.84}
BASE_Y = {"front_left": -0.64, "front_right": 0.64, "rear_left": -0.64, "rear_right": 0.64}
LIFT_RAISED = 3
LIFT_SCALE = 0.45
EXTEND_SCALE = 0.30
YAW_SCALE = 0.18


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def foot_target(pose: dict[str, Any], leg: str, controls: dict[str, Any]) -> dict[str, float]:
    return {
        "x": round(float(pose["x"]) + BASE_X[leg] + int(controls["extend"]) * EXTEND_SCALE, 4),
        "y": round(float(pose["y"]) + BASE_Y[leg] + int(controls["yaw"]) * YAW_SCALE, 4),
        "z": round(float(pose["z"]) - 1.28 + int(controls["lift"]) * LIFT_SCALE, 4),
    }


def _distance(a: dict[str, Any], b: dict[str, Any]) -> float:
    return math.sqrt(sum((float(a[key]) - float(b[key])) ** 2 for key in ("x", "y", "z")))


def _inside_xy(quad: dict[str, Any], point: dict[str, Any]) -> bool:
    vertices = quad.get("vertices") or []
    if len(vertices) != 4:
        return False
    epsilon = 1e-7
    crosses = []
    px, py = float(point["x"]), float(point["y"])
    for index, vertex in enumerate(vertices):
        following = vertices[(index + 1) % len(vertices)]
        crosses.append((float(following["x"]) - float(vertex["x"])) * (py - float(vertex["y"])) - (float(following["y"]) - float(vertex["y"])) * (px - float(vertex["x"])))
    return min(crosses) >= -epsilon or max(crosses) <= epsilon


def _quad_z(quad: dict[str, Any]) -> float:
    vertices = quad.get("vertices") or []
    return sum(float(vertex["z"]) for vertex in vertices) / len(vertices)


def terrain_surface_z(world: dict[str, Any], point: dict[str, Any]) -> float | None:
    """Return the top terrain surface under a world point.

    Support pads are represented by raised support-surface quads inside the
    same terrain mesh.  Taking the highest containing surface makes those
    patches collide as terrain instead of leaving pads as floating markers.
    """
    surfaces = [
        quad for quad in world.get("terrain_quads") or []
        if _inside_xy(quad, point)
    ]
    if not surfaces:
        return None
    return max(_quad_z(quad) for quad in surfaces)


def _pad_surface_z(world: dict[str, Any], pad_id: str, point: dict[str, Any]) -> float | None:
    for quad in world.get("terrain_quads") or []:
        if str(quad.get("kind") or "") == "support_surface" and str(quad.get("pad_id")) == pad_id:
            if _inside_xy(quad, point):
                return _quad_z(quad)
            return None
    return None


def body_clear_of_terrain(world: dict[str, Any], body: dict[str, Any]) -> bool:
    surface = terrain_surface_z(world, body)
    if surface is None:
        return False
    # The body reference point is above the feet; the clearance is part of
    # the visible walker/terrain collision model, not a presentation offset.
    return float(body["z"]) >= surface + 0.20


def _nearest_pad(world: dict[str, Any], pose: dict[str, Any], leg: str, controls: dict[str, Any], occupied: set[str]) -> str | None:
    if int(controls["lift"]) >= LIFT_RAISED:
        return None
    target = foot_target(pose, leg, controls)
    tolerance = float(world["contact_tolerance"])
    candidates = [
        pad for pad in world.get("pads") or []
        if (
            str(pad.get("id")) not in occupied
            and _distance(target, pad) <= tolerance
            and _pad_surface_z(world, str(pad.get("id")), target) is not None
        )
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda pad: (_distance(target, pad), str(pad.get("id"))))
    return str(candidates[0]["id"])


def contacts_for(world: dict[str, Any], pose: dict[str, Any], actuators: dict[str, dict[str, int]]) -> dict[str, str | None]:
    contacts: dict[str, str | None] = {}
    occupied: set[str] = set()
    for leg in LEGS:
        pad_id = _nearest_pad(world, pose, leg, actuators[leg], occupied)
        contacts[leg] = pad_id
        if pad_id is not None:
            occupied.add(pad_id)
    return contacts


def posture(world: dict[str, Any], contacts: dict[str, str | None]) -> tuple[float, float]:
    pads = {str(pad["id"]): pad for pad in world.get("pads") or []}
    points = [pads[pad_id] for pad_id in contacts.values() if pad_id in pads]
    if len(points) < 2:
        return 1.0, 1.0
    all_z = sum(float(point["z"]) for point in points) / len(points)
    left = [pads[pad_id] for leg, pad_id in contacts.items() if leg.endswith("left") and pad_id in pads]
    right = [pads[pad_id] for leg, pad_id in contacts.items() if leg.endswith("right") and pad_id in pads]
    front = [pads[pad_id] for leg, pad_id in contacts.items() if leg.startswith("front") and pad_id in pads]
    rear = [pads[pad_id] for leg, pad_id in contacts.items() if leg.startswith("rear") and pad_id in pads]
    left_z = sum(float(point["z"]) for point in left) / len(left) if left else all_z
    right_z = sum(float(point["z"]) for point in right) / len(right) if right else all_z
    front_z = sum(float(point["z"]) for point in front) / len(front) if front else all_z
    rear_z = sum(float(point["z"]) for point in rear) / len(rear) if rear else all_z
    return round((left_z - right_z) * 0.75, 4), round((front_z - rear_z) * 0.75, 4)


def initial_state(world: dict[str, Any]) -> dict[str, Any]:
    first = world["stages"][0]
    actuators = copy.deepcopy(first["stance_controls"])
    contacts = {str(leg): str(pad_id) for leg, pad_id in first["support_pad_ids"].items()}
    return {
        "stage": 0,
        "body": copy.deepcopy(first["body_pose"]),
        "actuators": actuators,
        "contacts": contacts,
        "released": [],
        "failed": False,
        "complete": False,
        "settles": 0,
        "motion": None,
        "body_trace": [copy.deepcopy(first["body_pose"])],
    }


def apply_settle(state: dict[str, Any], world: dict[str, Any]) -> dict[str, Any]:
    if state["failed"] or state["complete"]:
        return state
    state["settles"] += 1
    if state.get("motion") is not None:
        motion = state["motion"]
        target_stage = int(motion["target_stage"])
        path = world["stages"][target_stage].get("body_path_from_previous") or []
        step = int(motion["step"])
        if step >= len(path):
            state["failed"] = True
            return state
        next_body = copy.deepcopy(path[step])
        if not body_clear_of_terrain(world, next_body):
            state["failed"] = True
            return state
        state["body"] = next_body
        state.setdefault("body_trace", []).append(copy.deepcopy(next_body))
        motion["step"] = step + 1
        if motion["step"] >= len(path):
            destination = world["stages"][target_stage]
            state["stage"] = target_stage
            state["body"] = copy.deepcopy(path[-1])
            state["actuators"] = copy.deepcopy(destination["stance_controls"])
            state["contacts"] = {str(leg): str(pad_id) for leg, pad_id in destination["support_pad_ids"].items()}
            state["motion"] = None
        if int(state["stage"]) == len(world["stages"]) - 1 and float(state["body"]["x"]) >= float(world["escape_x"]):
            final_support = set(state["contacts"].values())
            if len(final_support) == 4:
                state["complete"] = True
        return state
    current_stage = int(state["stage"])
    contacts = contacts_for(world, state["body"], state["actuators"])
    support_count = sum(pad_id is not None for pad_id in contacts.values())
    roll, pitch = posture(world, contacts)
    limit = float(world["posture_limit"])
    if support_count < 3 or abs(roll) > limit or abs(pitch) > limit:
        state["contacts"] = contacts
        state["failed"] = True
        return state
    state["contacts"] = contacts
    stages = world["stages"]
    if current_stage < len(stages) - 1:
        next_stage = stages[current_stage + 1]
        transfer_leg = str(next_stage["transfer_leg"])
        current_ids = {str(value) for value in stages[current_stage]["support_pad_ids"].values()}
        expected_next = str(next_stage["support_pad_ids"][transfer_leg])
        other_legs_safe = all(
            contacts.get(leg) == str(stages[current_stage]["support_pad_ids"][leg])
            for leg in LEGS
            if leg != transfer_leg
        )
        if contacts.get(transfer_leg) is None and int(state["actuators"][transfer_leg]["lift"]) >= LIFT_RAISED and other_legs_safe:
            if current_stage not in state["released"]:
                state["released"].append(current_stage)
        elif (
            current_stage in state["released"]
            and contacts.get(transfer_leg) == expected_next
            and other_legs_safe
        ):
            state["motion"] = {"target_stage": current_stage + 1, "step": 0}
    if int(state["stage"]) == len(stages) - 1 and float(state["body"]["x"]) >= float(world["escape_x"]):
        final_support = set(state["contacts"].values())
        if len(final_support) == 4:
            state["complete"] = True
    return state


def _int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if not isinstance(value, bool) else None


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if payload.get("mechanic_id") != MECHANIC_ID or ground_truth.get("mechanic_id") != MECHANIC_ID or public_state.get("mechanic_id") != MECHANIC_ID:
        return _fail("mechanic identity mismatch")
    for key in ("task_id", "challenge_id"):
        if str(payload.get(key) or "") != str(ground_truth.get(key) or "") or str(public_state.get(key) or "") != str(ground_truth.get(key) or ""):
            return _fail(f"{key} mismatch")
    if public_state.get("world") != ground_truth.get("world"):
        return _fail("public and hidden 3D world disagree")
    if public_state.get("control_condition") != ground_truth.get("control_condition"):
        return _fail("control condition mismatch")
    if payload.get("completed") is not True:
        return _fail("escape was not certified")
    condition = ground_truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "simplified")
    expected_control_source = {"simplified": "nudge_button", "full": "slider_drag"}.get(interaction)
    if expected_control_source is None:
        return _fail("invalid interaction condition")
    events = payload.get("actions")
    if not isinstance(events, list) or not events or len(events) > 800:
        return _fail("missing or oversized actuator transcript")
    world = ground_truth.get("world")
    if not isinstance(world, dict) or not world.get("stages") or not world.get("pads"):
        return _fail("invalid hidden crater world")
    state = initial_state(world)
    expected_seq = 1
    last_tick = -1
    for index, event in enumerate(events):
        if not isinstance(event, dict) or _int(event.get("seq")) != expected_seq:
            return _fail(f"action {index + 1} sequence is not contiguous")
        expected_seq += 1
        tick = _int(event.get("tick"))
        if tick is None or tick < last_tick:
            return _fail("actuator transcript ticks are invalid")
        last_tick = tick
        event_type = str(event.get("type") or "")
        if event_type == "control":
            leg = str(event.get("leg") or "")
            actuator = str(event.get("actuator") or "")
            if leg not in LEGS or actuator not in ACTUATORS:
                return _fail("unknown actuator channel")
            if event.get("input_source") != expected_control_source:
                return _fail("control used the wrong interaction input surface")
            before = _int(event.get("before"))
            value = _int(event.get("value"))
            if before is None or value is None or before != int(state["actuators"][leg][actuator]) or not -5 <= value <= 5:
                return _fail("control value does not match replay")
            if expected_control_source == "nudge_button" and abs(value - before) != 1:
                return _fail("simplified control must move one signed step")
            state["actuators"][leg][actuator] = value
            if _int(event.get("after")) != value:
                return _fail("control after-value does not match replay")
        elif event_type == "settle":
            if event.get("input_source") != "settle_button":
                return _fail("settle did not come from the visible settle action")
            stage_before = int(state["stage"])
            body_before = copy.deepcopy(state["body"])
            apply_settle(state, world)
            if _int(event.get("stage_before")) != stage_before or _int(event.get("stage_after")) != int(state["stage"]):
                return _fail("settle stage report does not match replay")
            if event.get("body_before") != body_before or event.get("body_after") != state["body"]:
                return _fail("settle body path report does not match replay")
            motion_step = state["motion"]["step"] if state.get("motion") is not None else None
            if event.get("motion_step_after") != motion_step:
                return _fail("settle motion report does not match replay")
            if event.get("contacts_after") != state["contacts"]:
                return _fail("settle contact report does not match replay")
            if _int(event.get("support_count")) != sum(value is not None for value in state["contacts"].values()):
                return _fail("settle support count does not match replay")
            if bool(event.get("failed")) != bool(state["failed"]):
                return _fail("settle failure report does not match replay")
        else:
            return _fail(f"unknown action type {event_type!r}")
        if state["failed"]:
            return _fail("walker lost its three-point support")
    if not state["complete"] or int(state["stage"]) != len(world["stages"]) - 1:
        return _fail("walker did not reach the outside ledge")
    if payload.get("final_stage") != state["stage"] or payload.get("final_contacts") != state["contacts"]:
        return _fail("final support ledger does not match replay")
    return {
        "graded": True,
        "passed": True,
        "score": 100,
        "feedback": f"replayed {state['settles']} settles across {len(world['stages']) - 1} support transfers with four final contacts",
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    return {
        "transfer_controls": copy.deepcopy(ground_truth.get("transfer_controls") or []),
        "stage_count": len((ground_truth.get("world") or {}).get("stages") or []),
    }


__all__ = ["MECHANIC_ID", "initial_state", "foot_target", "contacts_for", "posture", "apply_settle", "grade", "cheat"]
