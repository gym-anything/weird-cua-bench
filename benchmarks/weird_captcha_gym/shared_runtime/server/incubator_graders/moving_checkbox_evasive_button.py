from __future__ import annotations

from typing import Any


MECHANIC_ID = "moving_checkbox_evasive_button"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _sign(value: int) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _trunc_ratio(value: int, numerator: int, denominator: int = 1000) -> int:
    magnitude = abs(value) * numerator // denominator
    return magnitude if value >= 0 else -magnitude


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _portal_geometry(boundary: dict[str, Any], offsets: list[int]) -> tuple[bool, int]:
    left_y = int(boundary["left_base_y"]) - offsets[int(boundary["left_shaft"])]
    right_y = int(boundary["right_base_y"]) - offsets[int(boundary["right_shaft"])]
    aligned = abs(left_y - right_y) <= int(boundary["alignment_tolerance"])
    return aligned, (left_y + right_y) // 2


def _step(
    body: dict[str, Any],
    cursor: dict[str, Any],
    offsets: list[int],
    scene: dict[str, Any],
    physics: dict[str, Any],
) -> tuple[dict[str, Any], list[tuple[int, int]]]:
    if body["captured"]:
        return dict(body), []
    x, y = int(body["x"]), int(body["y"])
    vx = _trunc_ratio(int(body["vx"]), int(physics["friction_milli"]))
    vy = _trunc_ratio(int(body["vy"]), int(physics["friction_milli"]))
    if cursor.get("active") is True:
        dx = x - int(cursor["x"])
        dy = y - int(cursor["y"])
        radius = int(physics["cursor_radius"])
        distance_sq = dx * dx + dy * dy
        if 0 < distance_sq < radius * radius:
            acceleration = 1 + (radius * radius - distance_sq) * (int(physics["cursor_acceleration"]) - 1) // (radius * radius)
            if abs(dx) * 2 >= abs(dy):
                vx += _sign(dx) * acceleration
            if abs(dy) * 2 >= abs(dx):
                vy += _sign(dy) * acceleration
    maximum = int(physics["max_speed"])
    vx = _clamp(vx, -maximum, maximum)
    vy = _clamp(vy, -maximum, maximum)
    next_x, next_y = x + vx, y + vy
    radius = int(scene["target"]["radius"])
    top, bottom = int(physics["top"]), int(physics["bottom"])
    restitution = int(physics["wall_restitution_milli"])
    if next_y - radius < top:
        next_y = top + radius
        vy = abs(_trunc_ratio(vy, restitution))
    elif next_y + radius > bottom:
        next_y = bottom - radius
        vy = -abs(_trunc_ratio(vy, restitution))

    left_edge = int(scene["shaft_lefts"][0]) + radius
    right_edge = int(scene["shaft_lefts"][-1]) + int(scene["shaft_width"]) - radius
    if next_x < left_edge:
        next_x = left_edge
        vx = abs(_trunc_ratio(vx, restitution))
    elif next_x > right_edge:
        next_x = right_edge
        vx = -abs(_trunc_ratio(vx, restitution))

    crossings: list[tuple[int, int]] = []
    for index, boundary in enumerate(scene["boundaries"]):
        boundary_x = int(boundary["x"])
        aligned, portal_y = _portal_geometry(boundary, offsets)
        within_opening = abs(next_y - portal_y) <= int(boundary["opening_half_height"]) - radius
        if vx > 0 and x <= boundary_x - radius < next_x:
            if aligned and within_opening:
                pass
            else:
                next_x = boundary_x - radius
                vx = -abs(_trunc_ratio(vx, restitution))
        elif vx < 0 and x >= boundary_x + radius > next_x:
            if aligned and within_opening:
                pass
            else:
                next_x = boundary_x + radius
                vx = abs(_trunc_ratio(vx, restitution))
        if aligned and within_opening and x < boundary_x <= next_x:
            crossings.append((index, 1))
        elif aligned and within_opening and x > boundary_x >= next_x:
            crossings.append((index, -1))

    clamp = scene["clamp"]
    capture_dx = next_x - int(clamp["x"])
    capture_dy = next_y - int(clamp["y"])
    captured = capture_dx * capture_dx + capture_dy * capture_dy <= int(clamp["capture_radius"]) ** 2
    if captured:
        next_x, next_y = int(clamp["x"]), int(clamp["y"])
        vx = vy = 0
    return {
        "x": next_x,
        "y": next_y,
        "vx": vx,
        "vy": vy,
        "captured": captured,
    }, crossings


def _body_matches(reported: Any, body: dict[str, Any]) -> bool:
    if not isinstance(reported, dict):
        return False
    return all(reported.get(key) == body[key] for key in ("x", "y", "vx", "vy", "captured"))


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    if payload.get("mechanic_id") != MECHANIC_ID or truth.get("mechanic_id") != MECHANIC_ID or public.get("mechanic_id") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    if payload.get("task_id") != truth.get("task_id") or public.get("task_id") != truth.get("task_id"):
        return _fail("task mismatch")
    if payload.get("challenge_id") != truth.get("challenge_id") or public.get("challenge_id") != truth.get("challenge_id"):
        return _fail("stale challenge")
    scene = truth.get("scene")
    physics = truth.get("physics")
    if not isinstance(scene, dict) or public.get("scene") != scene or not isinstance(physics, dict) or public.get("physics") != physics:
        return _fail("scroll-cage geometry contract mismatch")
    events = payload.get("events")
    if not isinstance(events, list) or not 3 <= len(events) <= 12_000:
        return _fail("scroll-cage transcript missing or outside limits")

    offsets = [int(value) for value in scene["initial_offsets"]]
    target = scene["target"]
    body = {
        "x": int(target["x"]),
        "y": int(target["y"]),
        "vx": int(target["vx"]),
        "vy": int(target["vy"]),
        "captured": False,
    }
    cursor = {"active": False, "x": 0, "y": 0}
    tick = 0
    checked = False
    verified = False
    forward_crossings: set[int] = set()
    scroll_events = 0

    for sequence, event in enumerate(events, 1):
        if verified:
            return _fail("transcript continues after verification")
        if not isinstance(event, dict) or event.get("seq") != sequence:
            return _fail(f"event {sequence} sequence invalid")
        action = event.get("type")
        if action == "cursor":
            active = event.get("active") is True
            if active:
                try:
                    x, y = int(event["x"]), int(event["y"])
                except (KeyError, TypeError, ValueError):
                    return _fail(f"event {sequence} cursor malformed")
                if not (0 <= x <= int(scene["width"]) and 0 <= y <= int(scene["height"])):
                    return _fail(f"event {sequence} cursor outside arena")
                cursor = {"active": True, "x": x, "y": y}
            else:
                cursor = {"active": False, "x": 0, "y": 0}
        elif action == "scroll":
            shaft = event.get("shaft")
            if shaft not in range(4):
                return _fail(f"event {sequence} scroll shaft invalid")
            before = offsets[shaft]
            try:
                delta = int(event["delta"])
            except (KeyError, TypeError, ValueError):
                return _fail(f"event {sequence} scroll delta malformed")
            if event.get("before") != before or delta not in {-int(scene["offset_step"]), int(scene["offset_step"])}:
                return _fail(f"event {sequence} scroll starts from stale offset")
            expected = _clamp(before + delta, int(scene["offset_min"]), int(scene["offset_max"]))
            if expected == before or event.get("after") != expected:
                return _fail(f"event {sequence} scroll crosses a stop or reports false offset")
            offsets[shaft] = expected
            scroll_events += 1
        elif action == "tick":
            if event.get("tick") != tick + 1:
                return _fail(f"event {sequence} fixed tick is missing or reordered")
            body, crossings = _step(body, cursor, offsets, scene, physics)
            tick += 1
            for boundary, direction in crossings:
                if direction == 1:
                    forward_crossings.add(boundary)
            if not _body_matches(event.get("body"), body):
                return _fail(f"event {sequence} body disagrees with fixed-step replay")
        elif action == "check":
            if not body["captured"] or checked:
                return _fail("checkbox was checked outside the physical clamp")
            if not _body_matches(event.get("body"), body):
                return _fail("check event reports false body geometry")
            checked = event.get("checked") is True
            if not checked:
                return _fail("check event did not set the checkbox")
        elif action == "verify":
            if event.get("tick") != tick or event.get("offsets") != offsets or not _body_matches(event.get("body"), body):
                return _fail("verification reports stale cage state")
            if event.get("checked") is not checked:
                return _fail("verification reports a false checkbox state")
            verified = True
        else:
            return _fail(f"unknown scroll-cage event {action!r}")
        if tick > int(physics["maximum_ticks"]):
            return _fail("scroll-cage run exceeded its fixed-step budget")

    passed = (
        verified
        and checked
        and body["captured"]
        and forward_crossings == {0, 1, 2}
        and scroll_events > 0
        and payload.get("completed") is True
    )
    feedback = (
        f"fixed-step cage replay: ticks {tick}; scrolls {scroll_events}; "
        f"forward gates {len(forward_crossings)}/3; captured {str(body['captured']).lower()}; checked {str(checked).lower()}"
    )
    return {"graded": True, "passed": passed, "feedback": feedback}


def cheat(public: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    del public
    return {
        "solution_offsets": truth.get("solution_offsets"),
        "route_screen_y": truth.get("route_screen_y"),
        "clamp": (truth.get("scene") or {}).get("clamp"),
    }
