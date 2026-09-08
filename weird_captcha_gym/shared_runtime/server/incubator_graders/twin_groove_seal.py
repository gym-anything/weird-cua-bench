"""Independent replay grader for Twin-Groove Seal.

The browser receives the visible groove geometry so it can render and stop a
contact at a wall.  This module repeats the polar rigid-link math and checks
the submitted trajectory against that geometry; it never trusts a client
reported solved bit or a hidden route index.
"""
from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "twin_groove_seal"
PLATE_CENTERS = ((320.0, 350.0), (960.0, 350.0))
MIN_RADIUS = 60.0
RING_SPACING = 30.0
NUB_DISTANCE = 400.0
ACTION_NAMES = {
    "radial_in",
    "radial_out",
    "angular_cw",
    "angular_ccw",
    "rotate_cw",
    "rotate_ccw",
}
ORIGINS = {"rear", "tip"}


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _norm_angle(angle: float) -> float:
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def _angle_delta(a: float, b: float) -> float:
    return _norm_angle(a - b)


def _polar_xy(polar: list[float], center: tuple[float, float]) -> tuple[float, float]:
    return center[0] + polar[0] * math.cos(polar[1]), center[1] + polar[0] * math.sin(polar[1])


def _xy_polar(point: tuple[float, float], center: tuple[float, float]) -> list[float]:
    dx = point[0] - center[0]
    dy = point[1] - center[1]
    return [math.hypot(dx, dy), _norm_angle(math.atan2(dy, dx))]


def _copy_state(state: dict[str, list[float]]) -> dict[str, list[float]]:
    return {"rear": [float(state["rear"][0]), float(state["rear"][1])], "tip": [float(state["tip"][0]), float(state["tip"][1])]}


def _valid_radius(radius: float, contract: dict[str, Any]) -> bool:
    maximum = MIN_RADIUS + (int(contract["rings"]) - 1) * RING_SPACING
    return MIN_RADIUS - 1e-6 <= radius <= maximum + 1e-6


def _choose_other_angle(
    active_xy: tuple[float, float],
    other: list[float],
    other_center: tuple[float, float],
) -> list[float] | None:
    other_radius = float(other[0])
    dx = active_xy[0] - other_center[0]
    dy = active_xy[1] - other_center[1]
    distance = math.hypot(dx, dy)
    if distance < 1e-6 or other_radius < 1e-6:
        return None
    cosine = (distance * distance + other_radius * other_radius - NUB_DISTANCE * NUB_DISTANCE) / (2.0 * distance * other_radius)
    if cosine < -1.000001 or cosine > 1.000001:
        return None
    base = math.atan2(dy, dx)
    offset = math.acos(max(-1.0, min(1.0, cosine)))
    choices = (base + offset, base - offset)
    chosen = min(choices, key=lambda angle: abs(_angle_delta(angle, float(other[1]))))
    return [other_radius, _norm_angle(chosen)]


def _apply_raw(
    state: dict[str, list[float]],
    origin: str,
    action: str,
    contract: dict[str, Any],
) -> dict[str, list[float]] | None:
    if origin not in ORIGINS or action not in ACTION_NAMES:
        return None
    next_state = _copy_state(state)
    other_origin = "tip" if origin == "rear" else "rear"
    active = next_state[origin]
    other = next_state[other_origin]
    radial_step = float(contract["radial_step"])
    angular_step = math.radians(float(contract["angular_step_deg"]))
    rotation_step = math.radians(float(contract["rotation_step_deg"]))
    if action == "radial_in":
        active[0] -= radial_step
    elif action == "radial_out":
        active[0] += radial_step
    elif action == "angular_cw":
        active[1] += angular_step
    elif action == "angular_ccw":
        active[1] -= angular_step
    if action.startswith("radial_") or action.startswith("angular_"):
        active[1] = _norm_angle(active[1])
        if not _valid_radius(active[0], contract):
            return None
        active_xy = _polar_xy(active, PLATE_CENTERS[0 if origin == "rear" else 1])
        solved = _choose_other_angle(active_xy, other, PLATE_CENTERS[1 if origin == "rear" else 0])
        if solved is None:
            return None
        other[1] = solved[1]
    else:
        active_xy = _polar_xy(active, PLATE_CENTERS[0 if origin == "rear" else 1])
        other_xy = _polar_xy(other, PLATE_CENTERS[1 if origin == "rear" else 0])
        vx = other_xy[0] - active_xy[0]
        vy = other_xy[1] - active_xy[1]
        sign = 1.0 if action == "rotate_cw" else -1.0
        theta = sign * rotation_step
        rotated = (
            active_xy[0] + vx * math.cos(theta) - vy * math.sin(theta),
            active_xy[1] + vx * math.sin(theta) + vy * math.cos(theta),
        )
        next_state[other_origin] = _xy_polar(rotated, PLATE_CENTERS[1 if origin == "rear" else 0])
    if not _valid_radius(next_state["rear"][0], contract) or not _valid_radius(next_state["tip"][0], contract):
        return None
    return next_state


def _cell(point: tuple[float, float], center: tuple[float, float], contract: dict[str, Any]) -> tuple[int, int]:
    radius = math.hypot(point[0] - center[0], point[1] - center[1])
    angle = math.atan2(point[1] - center[1], point[0] - center[0])
    rings = int(contract["rings"])
    sectors = int(contract["sectors"])
    ring = round((radius - MIN_RADIUS) / RING_SPACING)
    sector = int(((angle + math.pi) / (2.0 * math.pi)) * sectors) % sectors
    return max(0, min(rings - 1, ring)), sector


def _open_sets(public_state: dict[str, Any]) -> list[set[tuple[int, int]]]:
    return [
        {(int(cell[0]), int(cell[1])) for cell in plate.get("open_cells") or []}
        for plate in public_state.get("plates") or []
    ]


def _path_clear(old: dict[str, list[float]], new: dict[str, list[float]], public_state: dict[str, Any], contract: dict[str, Any]) -> bool:
    open_sets = _open_sets(public_state)
    if len(open_sets) != 2:
        return False
    old_points = (_polar_xy(old["rear"], PLATE_CENTERS[0]), _polar_xy(old["tip"], PLATE_CENTERS[1]))
    new_points = (_polar_xy(new["rear"], PLATE_CENTERS[0]), _polar_xy(new["tip"], PLATE_CENTERS[1]))
    for sample in range(13):
        t = sample / 12.0
        for index in range(2):
            point = (
                old_points[index][0] + (new_points[index][0] - old_points[index][0]) * t,
                old_points[index][1] + (new_points[index][1] - old_points[index][1]) * t,
            )
            if _cell(point, PLATE_CENTERS[index], contract) not in open_sets[index]:
                return False
    return True


def _state_close(left: Any, right: dict[str, list[float]], tolerance: float = 0.002) -> bool:
    if not isinstance(left, dict):
        return False
    for key in ("rear", "tip"):
        values = left.get(key)
        if not isinstance(values, list) or len(values) != 2:
            return False
        try:
            if any(not math.isfinite(float(value)) for value in values):
                return False
            if abs(float(values[0]) - right[key][0]) > tolerance:
                return False
            if abs(_angle_delta(float(values[1]), right[key][1])) > tolerance:
                return False
        except (TypeError, ValueError):
            return False
    return True


def _inside_exit(state: dict[str, list[float]], plate_index: int, public_state: dict[str, Any], contract: dict[str, Any]) -> bool:
    origin = "rear" if plate_index == 0 else "tip"
    point = _polar_xy(state[origin], PLATE_CENTERS[plate_index])
    cell = _cell(point, PLATE_CENTERS[plate_index], contract)
    exits = {(int(item[0]), int(item[1])) for item in (public_state.get("plates") or [])[plate_index].get("exit_cells") or []}
    return cell in exits


def _bind(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> str | None:
    if str(payload.get("mechanic_id") or "") != MECHANIC_ID:
        return "payload mechanic mismatch"
    if str(ground_truth.get("mechanic_id") or "") != MECHANIC_ID:
        return "ground-truth mechanic mismatch"
    if str(public_state.get("mechanic_id") or "") != MECHANIC_ID:
        return "public-state mechanic mismatch"
    for key in ("task_id", "challenge_id"):
        expected = str(ground_truth.get(key) or "")
        if not expected or str(payload.get(key) or "") != expected:
            return f"payload {key} mismatch"
        if str(public_state.get(key) or "") != expected:
            return f"public-state {key} mismatch"
    if public_state.get("control_condition") != ground_truth.get("control_condition"):
        return "public interaction condition differs from seal contract"
    return None


def _contract(ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    contract = ground_truth.get("map")
    if not isinstance(contract, dict) or public_state.get("map") != contract:
        raise ValueError("visible map contract differs from hidden geometry")
    plates = ground_truth.get("plates")
    if not isinstance(plates, list) or len(plates) != 2 or public_state.get("plates") != plates:
        raise ValueError("visible plate contract differs from hidden geometry")
    start = ground_truth.get("start")
    if not isinstance(start, dict) or public_state.get("start") != start:
        raise ValueError("starting contact positions differ from hidden geometry")
    for key in ("rings", "sectors", "radial_step", "angular_step_deg", "rotation_step_deg"):
        if key not in contract:
            raise ValueError(f"map field {key} is missing")
    return contract


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    binding_error = _bind(payload, ground_truth, public_state)
    if binding_error:
        return _fail(binding_error)
    try:
        contract = _contract(ground_truth, public_state)
        condition = ground_truth.get("control_condition") or {}
        interaction = str(condition.get("interaction") or "full")
        expected_source = {"simplified": "proxy_controls", "full": "keyboard_polar"}.get(interaction)
        if expected_source is None:
            return _fail("seal interaction condition is invalid")
        state = _copy_state(ground_truth["start"])
        events = payload.get("actions")
        if not isinstance(events, list) or not events:
            return _fail("empty shoe trajectory")
        move_count = 0
        blocked_count = 0
        release_count = 0
        released = False
        for index, event in enumerate(events, start=1):
            if not isinstance(event, dict) or event.get("sequence") != index:
                return _fail(f"event {index} has an invalid sequence")
            if released:
                return _fail("trajectory continues after release")
            if not _state_close(event.get("before"), state):
                return _fail(f"event {index} starts from the wrong shoe state")
            event_type = str(event.get("type") or "")
            if event_type == "move":
                move_count += 1
                if move_count > int(ground_truth.get("max_actions") or 0):
                    return _fail("move budget exceeded")
                if event.get("input_source") != expected_source:
                    return _fail(f"event {index} uses the wrong interaction surface")
                origin = str(event.get("origin") or "")
                action = str(event.get("action") or "")
                candidate = _apply_raw(state, origin, action, contract)
                accepted = candidate is not None and _path_clear(state, candidate, public_state, contract)
                if accepted:
                    state = candidate
                else:
                    blocked_count += 1
                if event.get("accepted") is not accepted:
                    return _fail(f"event {index} disagrees with the groove-wall replay")
                if not _state_close(event.get("after"), state):
                    return _fail(f"event {index} reports the wrong resulting shoe state")
            elif event_type == "release":
                release_count += 1
                if release_count != 1 or event.get("input_source") != "release_button":
                    return _fail("release event is missing or duplicated")
                released = True
                if not _state_close(event.get("after"), state):
                    return _fail("release event moves the shoe")
            else:
                return _fail(f"event {index} has an unknown type")
        if not released:
            return _fail("shoe was never released")
        final_state = payload.get("final_state")
        if not _state_close(final_state, state):
            return _fail("submitted final shoe state does not match replay")
        exits = _inside_exit(state, 0, public_state, contract) and _inside_exit(state, 1, public_state, contract)
        completed = payload.get("completed") is True
        passed = completed and exits
        return {
            "graded": True,
            "passed": passed,
            "score": 100 if passed else 0,
            "feedback": (
                f"coupled groove replay; moves {move_count}; wall stops {blocked_count}; "
                f"rear exit={'yes' if _inside_exit(state, 0, public_state, contract) else 'no'}; "
                f"tip exit={'yes' if _inside_exit(state, 1, public_state, contract) else 'no'}"
            ),
        }
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError, OverflowError) as exc:
        return _fail(f"invalid seal trajectory: {exc}")


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    actions = []
    state = ground_truth.get("start")
    for sequence, item in enumerate(ground_truth.get("solution_actions") or [], start=1):
        next_state = (ground_truth.get("solution_states") or [])[sequence]
        actions.append(
            {
                "sequence": sequence,
                "type": "move",
                "origin": item.get("origin"),
                "action": item.get("action"),
                "input_source": "proxy_controls" if (ground_truth.get("control_condition") or {}).get("interaction") == "simplified" else "keyboard_polar",
                "accepted": True,
                "before": state,
                "after": next_state,
            }
        )
        state = next_state
    actions.append(
        {
            "sequence": len(actions) + 1,
            "type": "release",
            "input_source": "release_button",
            "before": state,
            "after": state,
        }
    )
    return {
        "actions": actions,
        "final_state": state,
        "completed": True,
        "instruction": "Replay the coupled move list with the selected input surface, then release the shoe.",
    }
