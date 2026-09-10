from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "downsky_causeway"
_MOVEMENT_CONTROLS = {"forward", "back", "strafe_left", "strafe_right"}
_LOOK_CONTROLS = {"left", "right", "up", "down"}


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _number(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} is not numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} is not finite")
    return result


def _platform_contains(platform: dict[str, Any], x: float, y: float, radius: float = 0.0) -> bool:
    cx, cy = _number(platform["center"][0], "platform x"), _number(platform["center"][1], "platform y")
    width, depth = _number(platform["size"][0], "platform width"), _number(platform["size"][1], "platform depth")
    return abs(x - cx) <= max(0.0, width / 2 - radius) and abs(y - cy) <= max(0.0, depth / 2 - radius)


def _distance_to_rect(platform: dict[str, Any], x: float, y: float) -> float:
    cx, cy = _number(platform["center"][0], "platform x"), _number(platform["center"][1], "platform y")
    width, depth = _number(platform["size"][0], "platform width"), _number(platform["size"][1], "platform depth")
    dx = max(abs(x - cx) - width / 2, 0.0)
    dy = max(abs(y - cy) - depth / 2, 0.0)
    return math.hypot(dx, dy)


def _clamp_inside(platform: dict[str, Any], x: float, y: float, radius: float) -> tuple[float, float]:
    cx, cy = _number(platform["center"][0], "platform x"), _number(platform["center"][1], "platform y")
    width, depth = _number(platform["size"][0], "platform width"), _number(platform["size"][1], "platform depth")
    return (
        max(cx - width / 2 + radius, min(cx + width / 2 - radius, x)),
        max(cy - depth / 2 + radius, min(cy + depth / 2 - radius, y)),
    )


def _same_condition(ground_truth: dict[str, Any], public_state: dict[str, Any]) -> tuple[str, str | None]:
    truth_condition = ground_truth.get("control_condition")
    if truth_condition != public_state.get("control_condition"):
        raise ValueError("public interaction condition differs from the causeway contract")
    if truth_condition is None:
        return "full", None
    interaction = str(truth_condition.get("interaction") or "")
    if interaction not in {"simplified", "full"}:
        raise ValueError("causeway interaction condition is invalid")
    return interaction, str(truth_condition.get("difficulty"))


def _select_landing(
    platforms: list[dict[str, Any]],
    current: dict[str, Any],
    x: float,
    y: float,
    move_x: float,
    move_y: float,
    rules: dict[str, Any],
) -> dict[str, Any] | None:
    current_z = _number(current["center"][2], "current platform height")
    radius = _number(rules["player_radius"], "player radius")
    max_drop = _number(rules["max_drop"], "maximum drop")
    gap = _number(rules["walkable_gap"], "walkable gap") + radius * 2.0 + 0.04
    candidates: list[tuple[float, float, dict[str, Any]]] = []
    for platform in platforms:
        if platform["id"] == current["id"]:
            continue
        z = _number(platform["center"][2], "candidate platform height")
        drop = current_z - z
        if drop <= 0.01 or drop > max_drop + 1e-6:
            continue
        distance = _distance_to_rect(platform, x, y)
        if distance > gap:
            continue
        cx, cy = _number(platform["center"][0], "candidate x"), _number(platform["center"][1], "candidate y")
        toward = (cx - x) * move_x + (cy - y) * move_y
        if toward <= 0.0:
            continue
        candidates.append((distance, -drop, platform))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1], str(item[2]["id"])))
    return candidates[0][2]


def _advance(
    state: dict[str, Any],
    dt_ms: float,
    platforms: list[dict[str, Any]],
    rules: dict[str, Any],
) -> None:
    if state["failed"] or state["finished"]:
        return
    if dt_ms <= 0 or dt_ms > 500:
        raise ValueError("tick duration is outside the allowed range")
    speed = _number(rules["move_speed"], "move speed")
    radius = _number(rules["player_radius"], "player radius")
    current = next((p for p in platforms if p["id"] == state["platform_id"]), None)
    if current is None:
        raise ValueError("current platform is not in world geometry")
    heading = _number(state["heading"], "heading")
    dx = 0.0
    dy = 0.0
    if state["keys"]["forward"]:
        dx += math.cos(heading)
        dy += math.sin(heading)
    if state["keys"]["back"]:
        dx -= math.cos(heading)
        dy -= math.sin(heading)
    if state["keys"]["strafe_right"]:
        dx += math.cos(heading + math.pi / 2)
        dy += math.sin(heading + math.pi / 2)
    if state["keys"]["strafe_left"]:
        dx -= math.cos(heading + math.pi / 2)
        dy -= math.sin(heading + math.pi / 2)
    magnitude = math.hypot(dx, dy)
    if magnitude <= 1e-9:
        return
    dx /= magnitude
    dy /= magnitude
    distance = speed * dt_ms / 1000.0
    substeps = max(1, math.ceil(distance / 0.08))
    step = distance / substeps
    for _ in range(substeps):
        nx = state["x"] + dx * step
        ny = state["y"] + dy * step
        if _platform_contains(current, nx, ny, radius):
            state["x"], state["y"] = nx, ny
            continue
        landing = _select_landing(platforms, current, state["x"], state["y"], dx, dy, rules)
        if landing is None:
            state["failed"] = True
            state["failure_reason"] = "left a terrace without a lower walkable support"
            return
        state["x"], state["y"] = _clamp_inside(landing, nx, ny, radius)
        state["platform_id"] = landing["id"]
        current = landing
    state["z"] = _number(current["center"][2], "support height")


def replay_events(
    events: list[dict[str, Any]],
    world: dict[str, Any],
    interaction: str,
) -> tuple[dict[str, Any], str | None]:
    platforms = list(world["platforms"])
    rules = dict(world["rules"])
    start = dict(world["start"])
    position = list(start["position"])
    state: dict[str, Any] = {
        "x": _number(position[0], "start x"),
        "y": _number(position[1], "start y"),
        "z": _number(position[2], "start z"),
        "heading": _number(start["heading"], "start heading"),
        "pitch": _number(start.get("pitch", 0), "start pitch"),
        "platform_id": str(start["platform_id"]),
        "keys": {name: False for name in _MOVEMENT_CONTROLS},
        "failed": False,
        "finished": False,
        "finished_event": False,
        "failure_reason": None,
    }
    movement_source = "keyboard" if interaction == "full" else "control_button"
    look_source = "viewport_drag" if interaction == "full" else "look_button"
    previous_t = -1.0
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict) or int(event.get("seq", -1)) != index:
            return state, f"event {index} has invalid sequence numbering"
        kind = str(event.get("kind") or "")
        try:
            t_ms = _number(event.get("t_ms"), f"event {index} time")
        except ValueError as exc:
            return state, str(exc)
        if t_ms < previous_t or t_ms > 900_000:
            return state, f"event {index} time is reversed or exceeds the session bound"
        previous_t = t_ms
        if state["failed"] or state["finished"]:
            return state, f"event {index} occurs after terminal state"
        if kind == "key_down" or kind == "key_up":
            control = str(event.get("control") or "")
            if control not in _MOVEMENT_CONTROLS:
                return state, f"event {index} names an unknown movement control"
            if event.get("input_source") != movement_source:
                return state, f"event {index} uses the wrong movement input surface"
            down = kind == "key_down"
            if state["keys"][control] == down:
                return state, f"event {index} repeats a key transition"
            state["keys"][control] = down
        elif kind == "look":
            if event.get("input_source") != look_source:
                return state, f"event {index} uses the wrong look input surface"
            dx = _number(event.get("dx"), f"event {index} look dx")
            dy = _number(event.get("dy"), f"event {index} look dy")
            if abs(dx) > 500 or abs(dy) > 500 or (abs(dx) + abs(dy) <= 0):
                return state, f"event {index} has an implausible look delta"
            if interaction == "simplified" and (dx, dy) not in {(-8, 0), (8, 0), (0, -8), (0, 8)}:
                return state, f"event {index} changes the discrete look control"
            sensitivity = _number(rules["look_sensitivity"], "look sensitivity")
            state["heading"] += dx * sensitivity
            state["pitch"] = max(-0.34, min(0.34, state["pitch"] + dy * sensitivity * 0.55))
        elif kind == "tick":
            if event.get("input_source") != "physics":
                return state, f"event {index} has an invalid physics source"
            dt_ms = _number(event.get("dt_ms"), f"event {index} tick duration")
            if abs(dt_ms - _number(rules["tick_ms"], "tick size")) > 1e-6:
                return state, f"event {index} changes the fixed physics tick"
            _advance(state, dt_ms, platforms, rules)
        elif kind == "finish":
            exit_id = str(world["exit_platform_id"])
            exit_platform = next((p for p in platforms if p["id"] == exit_id), None)
            if event.get("input_source") != "physical_contact" or state["platform_id"] != exit_id or exit_platform is None:
                return state, f"event {index} certifies without physical exit contact"
            radius = _number(rules["finish_radius"], "finish radius")
            if radius <= 0 or "finish_guard_radius" in rules:
                return state, f"event {index} uses an invalid pavilion contact contract"
            if math.hypot(state["x"] - float(exit_platform["center"][0]), state["y"] - float(exit_platform["center"][1])) > radius:
                return state, f"event {index} certifies outside the pavilion contact region"
            state["finished"] = True
            state["finished_event"] = True
        elif kind in {"abandon", "fail"}:
            return state, "failure or abandonment cannot be a passing trajectory"
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
        return _fail("stale or cross-seed causeway")
    try:
        interaction, _difficulty = _same_condition(ground_truth, public_state)
    except ValueError as exc:
        return _fail(str(exc))
    if str(payload.get("interaction") or interaction) != interaction:
        return _fail("submitted interaction mode does not match the task")
    if payload.get("completed") is not True:
        return _fail("the pavilion was not reached")
    events = payload.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 20_000:
        return _fail("causeway transcript is missing or outside limits")
    try:
        if ground_truth.get("world") != public_state.get("world"):
            return _fail("public geometry differs from verifier geometry")
        state, error = replay_events(events, ground_truth["world"], interaction)
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        return _fail(f"invalid causeway transcript: {exc}")
    if error:
        return _fail(error)
    if not state["finished"] or not state["finished_event"]:
        return _fail("transcript never records physical contact with the exit pavilion")
    return {
        "graded": True,
        "passed": True,
        "score": 100,
        "feedback": f"physical causeway replay reached {ground_truth['world']['exit_platform_id']} after {len(events)} events",
    }


__all__ = ["grade", "replay_events"]
