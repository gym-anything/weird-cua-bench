from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "polarity_run"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _close(first: Any, second: Any, tolerance: float = 0.06) -> bool:
    left = _number(first)
    right = _number(second)
    return left is not None and right is not None and abs(left - right) <= tolerance


def _circle_hits_rect(body: dict[str, float], rect: dict[str, Any], radius: float) -> bool:
    left = float(rect["x"])
    top = float(rect["y"])
    right = left + float(rect["width"])
    bottom = top + float(rect["height"])
    closest_x = max(left, min(body["x"], right))
    closest_y = max(top, min(body["y"], bottom))
    return math.hypot(body["x"] - closest_x, body["y"] - closest_y) < radius


def _step(body: dict[str, float], polarity: int, charges: list[dict[str, Any]], physics: dict[str, Any]) -> None:
    fx = 0.0
    fy = 0.0
    for charge in charges:
        dx = float(charge["x"]) - body["x"]
        dy = float(charge["y"]) - body["y"]
        distance = math.hypot(dx, dy)
        if distance <= 0.001 or distance >= float(physics["influence_radius"]):
            continue
        coefficient = -float(physics["force_strength"]) * polarity * int(charge["charge"])
        coefficient /= distance + float(physics["softening"])
        fx += coefficient * dx
        fy += coefficient * dy
    body["vx"] = (body["vx"] + fx * float(physics["integration"])) * float(physics["damping"])
    body["vy"] = (body["vy"] + fy * float(physics["integration"])) * float(physics["damping"])
    speed = math.hypot(body["vx"], body["vy"])
    if speed > float(physics["max_speed"]):
        scale = float(physics["max_speed"]) / speed
        body["vx"] *= scale
        body["vy"] *= scale
    body["x"] += body["vx"]
    body["y"] += body["vy"]


def _replay(
    public: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    physics = public["physics"]
    body = {key: float(public["initial_bead"][key]) for key in ("x", "y", "vx", "vy")}
    polarity = 0
    event_index = 0
    gate_index = 0
    previous_x = body["x"]
    crossings: list[dict[str, Any]] = []
    completion_tick: int | None = None
    failure: str | None = None
    for tick in range(int(physics["ticks"])):
        while event_index < len(events) and int(events[event_index]["tick"]) == tick:
            polarity = int(events[event_index]["polarity"])
            event_index += 1
        _step(body, polarity, public["charges"], physics)
        if not all(math.isfinite(body[key]) for key in ("x", "y", "vx", "vy")):
            failure = "non-finite bead state"
            break
        if body["y"] < float(physics["world_padding"]) or body["y"] > 480.0 - float(physics["world_padding"]):
            failure = "bead left the chamber"
            break
        if any(_circle_hits_rect(body, wall, float(physics["bead_radius"])) for wall in public["walls"]):
            failure = "bead struck a maze rail"
            break
        if gate_index < len(public["gates"]) and previous_x < float(public["gates"][gate_index]["x"]) <= body["x"]:
            gate = public["gates"][gate_index]
            crossings.append({
                "tick": tick + 1,
                "gate_id": gate["id"],
                "x": round(body["x"], 4),
                "y": round(body["y"], 4),
                "polarity": polarity,
            })
            gate_index += 1
        previous_x = body["x"]
        if body["x"] >= float(public["target"]["x"]):
            if gate_index != len(public["gates"]):
                failure = "exit reached before every gate"
                break
            if math.hypot(body["x"] - float(public["target"]["x"]), body["y"] - float(public["target"]["y"])) <= float(public["target"]["radius"]):
                completion_tick = tick + 1
                break
            failure = "bead passed the exit ring"
            break
    if completion_tick is None and failure is None:
        failure = "time expired"
    return {
        "body": {key: round(body[key], 5) for key in ("x", "y", "vx", "vy")},
        "crossings": crossings,
        "completion_tick": completion_tick,
        "failure": failure,
        "gate_index": gate_index,
    }


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    if payload.get("mechanic_id") != MECHANIC_ID or truth.get("mechanic_id") != MECHANIC_ID or public.get("mechanic_id") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    for key in ("task_id", "challenge_id"):
        if payload.get(key) != truth.get(key) or public.get(key) != truth.get(key):
            return _fail(f"stale {key}")
    condition = truth.get("control_condition")
    if not isinstance(condition, dict) or public.get("control_condition") != condition:
        return _fail("control condition differs from the replay contract")
    interaction = str(condition.get("interaction") or "")
    expected_source = {"simplified": "polarity_button", "full": "polarity_dial_drag"}.get(interaction)
    if expected_source is None or payload.get("interaction_mode") != interaction:
        return _fail("wrong polarity interaction mode")
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        return _fail("no polarity events were recorded")
    max_events = int(truth.get("max_events") or 0)
    if len(events) > max_events:
        return _fail("polarity change budget exceeded")
    normalized: list[dict[str, Any]] = []
    previous_tick = -1
    for sequence, item in enumerate(events, 1):
        if not isinstance(item, dict) or item.get("seq") != sequence:
            return _fail("polarity event sequence is malformed")
        if item.get("type") != "polarity_change" or item.get("input_source") != expected_source:
            return _fail("polarity event uses the wrong input surface")
        try:
            tick = int(item["tick"])
            polarity = int(item["polarity"])
        except (KeyError, TypeError, ValueError):
            return _fail("polarity event has no physical tick or sign")
        if tick < 0 or tick >= int(public["physics"]["ticks"]) or tick <= previous_tick:
            return _fail("polarity event time is not strictly increasing")
        if polarity not in {-1, 0, 1}:
            return _fail("polarity sign is outside the three physical stops")
        normalized.append({"tick": tick, "polarity": polarity})
        previous_tick = tick
    replayed = _replay(public, normalized)
    terminal = payload.get("terminal")
    if not isinstance(terminal, dict):
        return _fail("terminal bead ledger is missing")
    if replayed["completion_tick"] is None:
        return _fail(replayed["failure"] or "bead did not reach the target")
    if payload.get("completed") is not True or terminal.get("passed") is not True:
        return _fail("completion flag missing")
    if terminal.get("tick") != replayed["completion_tick"]:
        return _fail("terminal tick disagrees with replay")
    if terminal.get("gates") != [item["gate_id"] for item in replayed["crossings"]]:
        return _fail("terminal gate ledger disagrees with replay")
    reported_crossings = payload.get("gate_crossings")
    if not isinstance(reported_crossings, list) or len(reported_crossings) != len(replayed["crossings"]):
        return _fail("visible gate ledger disagrees with replay")
    for reported, expected in zip(reported_crossings, replayed["crossings"], strict=True):
        if not isinstance(reported, dict) or reported.get("gate_id") != expected["gate_id"] or reported.get("tick") != expected["tick"]:
            return _fail("gate crossing is bound to the wrong gate or tick")
        if not _close(reported.get("x"), expected["x"]) or not _close(reported.get("y"), expected["y"]):
            return _fail("gate crossing telemetry disagrees with replay")
    reported_body = terminal.get("bead")
    if not isinstance(reported_body, dict) or any(not _close(reported_body.get(key), replayed["body"][key]) for key in ("x", "y", "vx", "vy")):
        return _fail("terminal bead state disagrees with replay")
    return {
        "graded": True,
        "passed": True,
        "feedback": f"charged bead cleared {len(replayed['crossings'])} force-field gates and entered the exit ring",
    }

