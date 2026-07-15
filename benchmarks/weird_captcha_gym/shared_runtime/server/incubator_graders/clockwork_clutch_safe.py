from __future__ import annotations

import math
from typing import Any

MECHANIC_ID = "clockwork_clutch_safe"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _close(first: Any, second: Any, tolerance: float = .025) -> bool:
    try:
        return math.isfinite(float(first)) and abs(float(first) - float(second)) <= tolerance
    except (TypeError, ValueError):
        return False


def _error(angle: float) -> float:
    return abs((angle + 180) % 360 - 180)


def _phase_close(first: Any, second: Any, tolerance: float = .025) -> bool:
    try:
        return math.isfinite(float(first)) and _error(float(first) - float(second)) <= tolerance
    except (TypeError, ValueError):
        return False


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    if payload.get("mechanic_id") != MECHANIC_ID or truth.get("mechanic_id") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    if payload.get("task_id") != truth.get("task_id") or payload.get("challenge_id") != truth.get("challenge_id") or public.get("challenge_id") != truth.get("challenge_id"):
        return _fail("stale task or challenge")
    events = payload.get("events")
    if not isinstance(events, list) or len(events) > 1000:
        return _fail("load-coupled clockwork transcript malformed")
    shafts = [dict(item) for item in public["shafts"]]
    physics = public["physics"]
    last_tick = 0
    running = False
    unlock = None

    def advance(target: int) -> bool:
        nonlocal last_tick
        if target < last_tick or target > int(physics["max_ticks"]):
            return False
        delta = target - last_tick
        if delta and not running:
            return False
        active = sum(bool(shaft["engaged"]) for shaft in shafts)
        factor = float(physics["load_numerator"]) / active if active else 0.0
        for shaft in shafts:
            if shaft["engaged"]:
                shaft["angle_deg"] = (float(shaft["angle_deg"]) + delta * float(shaft["ratio"]) * float(physics["drive_deg_per_tick"]) * factor) % 360
        last_tick = target
        return True

    for sequence, item in enumerate(events, 1):
        if not isinstance(item, dict) or item.get("seq") != sequence:
            return _fail(f"event {sequence} sequence invalid")
        action = item.get("type")
        if action == "abandon":
            return _fail("gear train broken")
        if action not in {"drive", "clutch", "unlock"}:
            return _fail(f"unknown clockwork event {action!r}")
        try:
            tick = int(item["tick"])
        except (KeyError, TypeError, ValueError):
            return _fail("clockwork event missing tick")
        if not advance(tick):
            return _fail("clockwork time advanced while braked or moved backward")
        if action == "drive":
            requested = bool(item.get("running"))
            if requested == running:
                return _fail("duplicate drive transition")
            if not requested:
                reported = item.get("angles")
                if not isinstance(reported, list) or len(reported) != len(shafts) or any(not _phase_close(value, shafts[index]["angle_deg"]) for index, value in enumerate(reported)):
                    return _fail("brake reports false shaft phases")
            running = requested
        elif action == "clutch":
            index = item.get("shaft")
            if index not in range(4) or bool(item.get("before")) != bool(shafts[index]["engaged"]):
                return _fail("clutch starts from stale active set")
            shafts[index]["engaged"] = not shafts[index]["engaged"]
            if bool(item.get("after")) != bool(shafts[index]["engaged"]) or not _phase_close(item.get("angle_deg"), shafts[index]["angle_deg"]) or item.get("active_after") != sum(bool(shaft["engaged"]) for shaft in shafts):
                return _fail("clutch reports false phase or load redistribution set")
        else:
            if running:
                return _fail("safe tried while master drive still running")
            unlock = item
    errors = [_error(float(shaft["angle_deg"])) for shaft in shafts]
    accepted = all(not shaft["engaged"] for shaft in shafts) and all(value <= float(physics["phase_tolerance_deg"]) for value in errors)
    reported_angles = unlock.get("angles") if isinstance(unlock, dict) else None
    if not isinstance(unlock, dict) or not isinstance(reported_angles, list) or len(reported_angles) != len(shafts) or any(not _phase_close(value, shafts[index]["angle_deg"]) for index, value in enumerate(reported_angles)) or unlock.get("engaged") != [bool(shaft["engaged"]) for shaft in shafts] or bool(unlock.get("accepted")) != accepted:
        return _fail("safe verdict disagrees with load-coupled replay")
    passed = accepted and payload.get("completed") is True
    return {"graded": True, "passed": passed, "feedback": "four phases accepted under active-set load redistribution" if passed else f"phase errors {' / '.join(f'{value:.1f}' for value in errors)}"}
