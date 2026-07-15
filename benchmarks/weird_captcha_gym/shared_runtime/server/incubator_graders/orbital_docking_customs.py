from __future__ import annotations

import math
from typing import Any

MECHANIC_ID = "orbital_docking_customs"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _close(first: Any, second: Any, tolerance: float = .004) -> bool:
    try:
        return math.isfinite(float(first)) and abs(float(first) - float(second)) <= tolerance
    except (TypeError, ValueError):
        return False


def _same(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return all(_close(first.get(key), second.get(key)) for key in ("x", "y", "vx", "vy", "angle_deg", "radius"))


def _angle_error(first: float, second: float) -> float:
    return abs((first - second + 180) % 360 - 180)


def _station_y(station: dict[str, Any], tick: int) -> float:
    return float(station["base_y"]) + float(station["y_amplitude"]) * math.sin(tick * float(station["y_rate"]) + float(station["y_phase"]))


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    if payload.get("mechanic_id") != MECHANIC_ID or truth.get("mechanic_id") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    if payload.get("task_id") != truth.get("task_id") or payload.get("challenge_id") != truth.get("challenge_id") or public.get("challenge_id") != truth.get("challenge_id"):
        return _fail("stale task or challenge")
    events = payload.get("events")
    if not isinstance(events, list) or len(events) > 900:
        return _fail("orbital transcript malformed")
    ship = dict(public["ship"])
    physics = public["physics"]
    fuel = int(physics["fuel"])
    ticks = 0
    scans: list[str] = []
    collision = None
    dock_event = None
    for sequence, item in enumerate(events, 1):
        if not isinstance(item, dict) or item.get("seq") != sequence:
            return _fail(f"event {sequence} sequence invalid")
        action = item.get("type")
        if action == "abandon":
            return _fail("orbit abandoned")
        if action == "control":
            if dock_event is not None or not _same(item.get("before") or {}, ship):
                return _fail("RCS control starts from stale inertial state")
            control = item.get("action")
            radians = math.radians(float(ship["angle_deg"]))
            if control in {"thrust", "retro", "strafe-up", "strafe-down"}:
                if fuel <= 0:
                    return _fail("thruster fired without fuel")
                fuel -= 1
                sign = -1 if control == "retro" else 1
                if control in {"thrust", "retro"}:
                    ship["vx"] += math.cos(radians) * float(physics["impulse"]) * sign
                    ship["vy"] += math.sin(radians) * float(physics["impulse"]) * sign
                else:
                    side = -1 if control == "strafe-up" else 1
                    ship["vx"] += math.cos(radians + math.pi / 2) * float(physics["impulse"]) * side
                    ship["vy"] += math.sin(radians + math.pi / 2) * float(physics["impulse"]) * side
            elif control == "rotate-left":
                ship["angle_deg"] = (float(ship["angle_deg"]) - float(physics["rotation_step_deg"]) + 360) % 360
            elif control == "rotate-right":
                ship["angle_deg"] = (float(ship["angle_deg"]) + float(physics["rotation_step_deg"])) % 360
            elif control in {"coast", "coast-long"}:
                coast_ticks = int(physics["coast_long_ticks"] if control == "coast-long" else physics["coast_step_ticks"])
                for _ in range(coast_ticks):
                    if ticks >= int(physics["max_ticks"]):
                        break
                    ship["x"] += ship["vx"]
                    ship["y"] += ship["vy"]
                    ticks += 1
                    debris = next((body for body in public["debris"] if math.hypot(ship["x"] - body["x"], ship["y"] - body["y"]) < ship["radius"] + body["radius"]), None)
                    if debris is not None:
                        collision = debris["id"]
                        break
                    if len(scans) < len(public["beacons"]):
                        beacon = public["beacons"][len(scans)]
                        if math.hypot(ship["x"] - beacon["x"], ship["y"] - beacon["y"]) <= beacon["radius"]:
                            scans.append(beacon["id"])
            else:
                return _fail("unknown RCS action")
            if not _same(item.get("after") or {}, ship) or item.get("fuel_after") != fuel or item.get("ticks_after") != ticks or item.get("scans_after") != scans or item.get("collision") != collision:
                return _fail("RCS event reports false dynamics, scans, or collision state")
            if collision is not None:
                return _fail(f"swept replay struck {collision}")
        elif action == "dock":
            if dock_event is not None:
                return _fail("duplicate hard-dock request")
            dock_event = item
        else:
            return _fail(f"unknown orbital event {action!r}")
    if not isinstance(dock_event, dict):
        return _fail("no hard-dock request")
    station = public["station"]
    target_angle = (float(station["angle_deg"]) + ticks * float(station["rotation_deg_per_tick"])) % 360
    station_y = _station_y(station, ticks)
    distance = math.hypot(ship["x"] - float(station["x"]), ship["y"] - station_y)
    speed = math.hypot(ship["vx"], ship["vy"])
    aligned = _angle_error(float(ship["angle_deg"]), target_angle) <= float(physics["angle_tolerance_deg"])
    accepted = collision is None and scans == [item["id"] for item in public["beacons"]] and distance <= float(physics["dock_distance"]) and speed <= float(physics["dock_speed"]) and aligned
    if dock_event.get("ticks") != ticks or dock_event.get("fuel_after") != fuel or not _same(dock_event.get("ship") or {}, ship) or dock_event.get("scans") != scans or dock_event.get("collision") != collision:
        return _fail("hard-dock request starts from a false inertial ledger")
    if bool(dock_event.get("accepted")) != accepted or bool(dock_event.get("aligned")) != aligned or not _close(dock_event.get("target_angle"), target_angle, .025) or not _close(dock_event.get("station_y"), station_y, .025) or not _close(dock_event.get("distance"), distance, .025) or not _close(dock_event.get("speed"), speed, .025):
        return _fail("hard-dock verdict disagrees with moving-station replay")
    passed = accepted and payload.get("completed") is True
    return {"graded": True, "passed": passed, "feedback": "collision-free replay cleared two scans and matched the moving rotating port" if passed else f"scans={len(scans)}/2; range={distance:.1f}; speed={speed:.2f}; aligned={aligned}"}
