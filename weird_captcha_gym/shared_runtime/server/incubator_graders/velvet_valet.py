from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "velvet_valet"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _angle_error(first: float, second: float) -> float:
    return abs((first - second + math.pi) % (2 * math.pi) - math.pi)


def _corners(x: float, y: float, length: float, width: float, angle: float) -> list[tuple[float, float]]:
    ca, sa = math.cos(angle), math.sin(angle)
    return [
        (x + ca * dx - sa * dy, y + sa * dx + ca * dy)
        for dx, dy in ((-length / 2, -width / 2), (length / 2, -width / 2),
                       (length / 2, width / 2), (-length / 2, width / 2))
    ]


def _axes(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    axes = []
    for index, first in enumerate(points):
        second = points[(index + 1) % len(points)]
        dx, dy = second[0] - first[0], second[1] - first[1]
        length = math.hypot(dx, dy)
        if length > 1e-9:
            axes.append((-dy / length, dx / length))
    return axes


def _overlap(first: list[tuple[float, float]], second: list[tuple[float, float]]) -> bool:
    for axis in _axes(first) + _axes(second):
        a = [point[0] * axis[0] + point[1] * axis[1] for point in first]
        b = [point[0] * axis[0] + point[1] * axis[1] for point in second]
        if max(a) <= min(b) + 1e-7 or max(b) <= min(a) + 1e-7:
            return False
    return True


def _state_valid(state: dict[str, float], world: dict[str, Any]) -> str | None:
    physics = world["physics"]
    car = _corners(
        float(state["x"]), float(state["y"]), float(physics["car_length"]),
        float(physics["car_width"]), float(state["heading"]),
    )
    if any(point[0] < 0 or point[0] > float(world["width"]) or point[1] < 0 or point[1] > float(world["height"]) for point in car):
        return "kerb collision"
    for obstacle in world["obstacles"]:
        other = _corners(
            float(obstacle["x"]), float(obstacle["y"]), float(obstacle["width"]),
            float(obstacle["height"]), float(obstacle.get("angle", 0.0)),
        )
        if _overlap(car, other):
            return f"collision with {obstacle['id']}"
    return None


def _advance(state: dict[str, float], controls: dict[str, Any], world: dict[str, Any]) -> str | None:
    physics = world["physics"]
    throttle = int(controls.get("throttle", 0))
    speed = float(state["speed"])
    if bool(controls.get("brake")):
        speed *= float(physics["brake_factor"])
    elif throttle > 0:
        speed = min(float(physics["max_forward_speed"]), speed + float(physics["acceleration"]))
    elif throttle < 0:
        speed = max(-float(physics["max_reverse_speed"]), speed - float(physics["reverse_acceleration"]))
    else:
        speed *= float(physics["coast_factor"])
    steer = max(-1, min(1, int(controls.get("steer", 0))))
    speed_fraction = min(1.0, abs(speed) / max(float(physics["max_forward_speed"]), 0.001))
    direction = -1.0 if speed < 0 else 1.0
    state["heading"] = (float(state["heading"]) + steer * float(physics["turn_rate"]) * (0.25 + 0.75 * speed_fraction) * direction + math.pi) % (2 * math.pi) - math.pi
    state["x"] += math.cos(float(state["heading"])) * speed
    state["y"] += math.sin(float(state["heading"])) * speed
    state["speed"] = speed
    return _state_valid(state, world)


def _apply_command(controls: dict[str, Any], command: str) -> None:
    if command == "steer_left":
        controls["steer"] = -1
    elif command == "steer_right":
        controls["steer"] = 1
    elif command == "steer_center":
        controls["steer"] = 0
    elif command == "forward":
        controls["throttle"] = 1
        controls["brake"] = False
    elif command == "reverse":
        controls["throttle"] = -1
        controls["brake"] = False
    elif command == "coast":
        controls["throttle"] = 0
    elif command == "brake_on":
        controls["brake"] = True
        controls["throttle"] = 0
    elif command == "brake_off":
        controls["brake"] = False
    else:
        raise ValueError(f"unknown control command {command!r}")


def _parked(state: dict[str, float], world: dict[str, Any]) -> tuple[bool, str]:
    physics, target = world["physics"], world["target"]
    distance = math.hypot(float(state["x"]) - float(target["x"]), float(state["y"]) - float(target["y"]))
    position_limit = float(physics["position_tolerance"])
    heading_limit = math.radians(float(physics["heading_tolerance_deg"]))
    if distance > position_limit:
        return False, f"bay center error {distance:.1f}px"
    if _angle_error(float(state["heading"]), float(target["heading"])) > heading_limit:
        return False, "nose is not aligned with the bay arrow"
    if abs(float(state["speed"])) > float(physics["speed_tolerance"]):
        return False, "car is still moving"
    car = _corners(float(state["x"]), float(state["y"]), float(physics["car_length"]), float(physics["car_width"]), float(state["heading"]))
    ca, sa = math.cos(float(target["heading"])), math.sin(float(target["heading"]))
    for px, py in car:
        local_x = (px - float(target["x"])) * ca + (py - float(target["y"])) * sa
        local_y = -(px - float(target["x"])) * sa + (py - float(target["y"])) * ca
        if abs(local_x) > float(target["width"]) / 2 or abs(local_y) > float(target["length"]) / 2:
            return False, "car footprint crosses the velvet bay border"
    return True, "car is stationary inside the velvet bay"


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if any(source.get("mechanic_id") != MECHANIC_ID for source in (payload, ground_truth, public_state)):
        return _fail("mechanic mismatch")
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if not challenge_id or payload.get("challenge_id") != challenge_id or public_state.get("challenge_id") != challenge_id:
        return _fail("stale courtyard challenge")
    if payload.get("task_id") != ground_truth.get("task_id") or public_state.get("task_id") != ground_truth.get("task_id"):
        return _fail("stale task identity")
    if public_state.get("world") != ground_truth.get("world"):
        return _fail("visible courtyard differs from the replay world")
    condition = ground_truth.get("control_condition")
    if public_state.get("control_condition") != condition:
        return _fail("interaction or difficulty condition differs from the visible contract")
    interaction = str((condition or {}).get("interaction") or "")
    expected_source = {"simplified": "control_button", "full": "keyboard"}.get(interaction)
    if condition is not None and expected_source is None:
        return _fail("invalid interaction condition")
    world = ground_truth.get("world")
    if not isinstance(world, dict):
        return _fail("missing courtyard world")
    try:
        physics = world["physics"]
        max_ticks = int(physics["max_ticks"])
        events = payload.get("events")
        final_tick = int(payload.get("final_tick"))
    except (KeyError, TypeError, ValueError):
        return _fail("parking transcript is malformed")
    if not isinstance(events, list) or len(events) > 2400 or not 0 <= final_tick <= max_ticks:
        return _fail("parking transcript is outside supported limits")
    start = world["start"]
    state = {"x": float(start["x"]), "y": float(start["y"]), "heading": float(start["heading"]), "speed": 0.0}
    controls: dict[str, Any] = {"steer": 0, "throttle": 0, "brake": False}
    tick = 0
    collision: str | None = None
    for sequence, event in enumerate(events, 1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return _fail(f"event {sequence} sequence mismatch")
        if event.get("input_source") != expected_source:
            return _fail(f"event {sequence} uses the wrong interaction input")
        try:
            event_tick = int(event["tick"])
        except (KeyError, TypeError, ValueError):
            return _fail(f"event {sequence} has no valid tick")
        if event_tick < tick or event_tick > final_tick:
            return _fail(f"event {sequence} is out of chronological order")
        while tick < event_tick:
            collision = _advance(state, controls, world)
            tick += 1
            if collision:
                return _fail(collision)
        if event.get("type") != "control":
            return _fail(f"event {sequence} is not a control event")
        try:
            _apply_command(controls, str(event["command"]))
        except ValueError as exc:
            return _fail(str(exc))
    while tick < final_tick:
        collision = _advance(state, controls, world)
        tick += 1
        if collision:
            return _fail(collision)
    accepted, feedback = _parked(state, world)
    passed = payload.get("completed") is True and accepted and not collision
    return {
        "graded": True,
        "passed": passed,
        "feedback": feedback if passed else feedback,
        "replay": {
            "final_tick": tick,
            "x": round(state["x"], 3),
            "y": round(state["y"], 3),
            "heading": round(state["heading"], 5),
            "speed": round(state["speed"], 4),
            "accepted": accepted,
        },
    }
