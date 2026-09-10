from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "rising_causeway"
MOVEMENT_CONTROLS = {"forward", "back", "strafe_left", "strafe_right"}
# A 180-second run emits 4,500 physics ticks before any mouse/key events.
MAX_EVENTS = 20000


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _num(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} is not numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} is not finite")
    return result


def _same(a: Any, b: Any, tolerance: float = 1e-6) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= tolerance
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y, tolerance) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_same(a[key], b[key], tolerance) for key in a)
    return a == b


def _condition(truth: dict[str, Any], public: dict[str, Any]) -> tuple[str, str | None] | None:
    expected = truth.get("control_condition")
    if expected != public.get("control_condition"):
        raise ValueError("public interaction condition differs from the causeway contract")
    if expected is None:
        return "full", None
    interaction = str(expected.get("interaction") or "")
    if interaction not in {"simplified", "full"}:
        raise ValueError("invalid causeway interaction condition")
    return interaction, str(expected.get("difficulty"))


def _sources(interaction: str) -> dict[str, str]:
    if interaction == "full":
        return {"actuator": "viewport_click", "terminal": "viewport_click", "movement": "keyboard", "look": "viewport_drag", "physics": "physics"}
    return {"actuator": "proxy_button", "terminal": "proxy_button", "movement": "control_button", "look": "look_button", "physics": "physics"}


def _launcher(world: dict[str, Any], identifier: str) -> dict[str, Any] | None:
    for item in world.get("launcher_gallery") or []:
        if str(item.get("id")) == identifier:
            return item
    return None


def _surface_candidates(state: dict[str, Any], world: dict[str, Any], x: float, y: float) -> list[float]:
    chamber = world["chamber"]
    geometry = chamber["geometry"]
    candidates: list[float] = []

    def covers(surface: dict[str, Any]) -> bool:
        return (
            float(surface["x0"]) - 0.0001 <= x <= float(surface["x1"]) + 0.0001
            and float(surface["y0"]) - 0.0001 <= y <= float(surface["y1"]) + 0.0001
        )

    approach = geometry["approach_surface"]
    if covers(approach):
        candidates.append(_num(approach["z"], "approach surface z"))
    for extension in geometry.get("red_extensions") or []:
        if state["red_stage"] >= int(extension["required_stage"]) and covers(extension):
            candidates.append(_num(extension["z"], "red extension z"))
    if state.get("stair_end") in {"left", "right"}:
        stair_key = "z_left" if state["stair_end"] == "left" else "z_right"
        for step in geometry.get("stair_steps") or []:
            if covers(step):
                candidates.append(_num(step[stair_key], f"{stair_key} stair z"))
    launch_surface = geometry["launch_surface"]
    if covers(launch_surface):
        candidates.append(_num(launch_surface["z"], "launch surface z"))
    if state.get("landed") and state.get("primed"):
        for platform in geometry.get("landing_platforms") or []:
            if platform.get("launcher_id") == state["primed"] and covers(platform):
                candidates.append(_num(platform["z"], "landing platform z"))
    return candidates


def _support_z(state: dict[str, Any], world: dict[str, Any], x: float, y: float) -> float | None:
    candidates = _surface_candidates(state, world, x, y)
    if not candidates:
        return None
    current = _num(state["z"], "current z")
    max_up = _num(world["chamber"]["rules"]["max_step_up"], "max step up")
    max_down = _num(world["chamber"]["rules"]["max_step_down"], "max step down")
    accessible = [z for z in candidates if z - current <= max_up + 0.0001 and current - z <= max_down + 0.0001]
    if not accessible:
        return None
    return min(accessible, key=lambda value: abs(value - current))


def _move(state: dict[str, Any], world: dict[str, Any], dt_ms: float) -> None:
    if state["failed"] or state["terminal"] or state["in_flight"]:
        return
    chamber = world["chamber"]
    rules = chamber["rules"]
    dx = 0.0
    dy = 0.0
    heading = state["heading"]
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
    distance = _num(rules["move_speed"], "move speed") * dt_ms / 1000.0
    substeps = max(1, math.ceil(distance / 0.07))
    step = distance / substeps
    for _ in range(substeps):
        nx = state["x"] + dx * step
        ny = state["y"] + dy * step
        if abs(ny) > _num(rules["outer_y_half_width"], "outer y bound"):
            state["failed"] = True
            state["failure_reason"] = "the avatar left the causeway corridor"
            return
        if state["x"] < float(rules["stair_end"]) <= nx and state["stair_end"] != state["required_stair_end"]:
            state["failed"] = True
            state["failure_reason"] = "the selected triple staircase rises away from the landing"
            return
        support = _support_z(state, world, nx, ny)
        if support is None:
            state["failed"] = True
            state["failure_reason"] = "the avatar crossed a gap in the causeway geometry"
            return
        state["x"] = nx
        state["y"] = ny
        state["z"] = support


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    try:
        if payload.get("mechanic_id") != MECHANIC_ID or truth.get("mechanic_id") != MECHANIC_ID or public.get("mechanic_id") != MECHANIC_ID:
            return _fail("mechanic mismatch")
        if payload.get("task_id") != truth.get("task_id") or public.get("task_id") != truth.get("task_id") or payload.get("challenge_id") != truth.get("challenge_id") or public.get("challenge_id") != truth.get("challenge_id"):
            return _fail("stale task or challenge")
        if not _same(truth.get("world"), public.get("world")):
            return _fail("public chamber geometry differs from replay contract")
        interaction, _difficulty = _condition(truth, public) or ("full", None)
        if payload.get("interaction") != interaction:
            return _fail("submission interaction mode does not match the task condition")
        sources = _sources(interaction)
        world = public["world"]
        chamber = world["chamber"]
        start = chamber["start"]
        position = start["position"]
        state: dict[str, Any] = {
            "x": _num(position[0], "start x"),
            "y": _num(position[1], "start y"),
            "z": _num(position[2], "start z"),
            "heading": _num(start["heading"], "start heading"),
            "pitch": _num(start.get("pitch", 0), "start pitch"),
            "keys": {name: False for name in MOVEMENT_CONTROLS},
            "red_stage": 0,
            "stair_end": None,
            "selected_launcher": None,
            "primed": None,
            "in_flight": False,
            "landed": False,
            "landing_z": None,
            "flight_origin": None,
            "flight_velocity": None,
            "flight_elapsed_ms": 0.0,
            "terminal": False,
            "failed": False,
            "failure_reason": None,
            "required_stair_end": str(truth.get("required_stair_end")),
        }
        events = payload.get("events")
        if not isinstance(events, list) or len(events) > MAX_EVENTS:
            return _fail("causeway transcript malformed")
        previous_t = -1.0
        launch_started_at: float | None = None
        last_seq = 0
        for index, event in enumerate(events, start=1):
            if not isinstance(event, dict) or int(event.get("seq", -1)) != index:
                return _fail(f"event {index} has invalid sequence numbering")
            last_seq = index
            t_ms = _num(event.get("t_ms"), f"event {index} time")
            if t_ms < 0 or t_ms < previous_t or t_ms > 1_200_000:
                return _fail(f"event {index} time is reversed or exceeds the session bound")
            previous_t = t_ms
            kind = str(event.get("kind") or "")
            if state["terminal"]:
                return _fail(f"event {index} follows terminal submission")
            if state["in_flight"] and kind in {"red_actuator", "stair_actuator", "launcher_prime", "look", "key_down", "launch_start"}:
                return _fail(f"event {index} changes controls during the contact launch")
            if kind == "key_down" or kind == "key_up":
                control = str(event.get("control") or "")
                if control not in MOVEMENT_CONTROLS or event.get("input_source") != sources["movement"]:
                    return _fail(f"event {index} uses an invalid movement input")
                down = kind == "key_down"
                if state["keys"][control] == down:
                    return _fail(f"event {index} repeats a movement transition")
                state["keys"][control] = down
            elif kind == "look":
                if event.get("input_source") != sources["look"]:
                    return _fail(f"event {index} uses the wrong look input")
                dx = _num(event.get("dx"), f"event {index} look dx")
                dy = _num(event.get("dy"), f"event {index} look dy")
                if abs(dx) > 500 or abs(dy) > 500 or abs(dx) + abs(dy) <= 0:
                    return _fail(f"event {index} has an implausible look delta")
                sensitivity = _num(chamber["rules"]["look_sensitivity"], "look sensitivity")
                state["heading"] += dx * sensitivity
                state["pitch"] = max(-0.34, min(0.34, state["pitch"] + dy * sensitivity * 0.55))
            elif kind == "tick":
                if event.get("input_source") != sources["physics"]:
                    return _fail(f"event {index} tick is not physics-sourced")
                dt_ms = _num(event.get("dt_ms"), f"event {index} tick duration")
                if dt_ms != float(chamber["rules"]["tick_ms"]):
                    return _fail(f"event {index} tick duration is outside the browser contract")
                if state["in_flight"]:
                    origin = state["flight_origin"]
                    velocity = state["flight_velocity"]
                    if not isinstance(origin, list) or not isinstance(velocity, list):
                        return _fail(f"event {index} advances a launch without physical state")
                    state["flight_elapsed_ms"] += dt_ms
                    elapsed = state["flight_elapsed_ms"] / 1000.0
                    gravity = _num(chamber["rules"]["gravity"], "gravity")
                    state["x"] = float(origin[0]) + float(velocity[0]) * elapsed
                    state["y"] = float(origin[1]) + float(velocity[1]) * elapsed
                    state["z"] = float(origin[2]) + float(velocity[2]) * elapsed - 0.5 * gravity * elapsed * elapsed
                else:
                    _move(state, world, dt_ms)
            elif kind == "red_actuator":
                if event.get("input_source") != sources["actuator"] or event.get("target_id") != "red-main":
                    return _fail(f"event {index} is not a valid red actuator interaction")
                before = int(event.get("before_stage", -1))
                after = int(event.get("after_stage", -1))
                if before != state["red_stage"] or after != before + 1 or after > int(chamber["rules"]["red_stage_target"]):
                    return _fail(f"event {index} falsifies red extrusion stages")
                state["red_stage"] = after
            elif kind == "stair_actuator":
                if event.get("input_source") != sources["actuator"] or event.get("target_id") != "yellow-triple":
                    return _fail(f"event {index} is not a valid stair actuator interaction")
                end = str(event.get("high_end") or "")
                if end not in {"left", "right"}:
                    return _fail(f"event {index} names an invalid stair end")
                state["stair_end"] = end
            elif kind == "launcher_prime":
                if event.get("input_source") != sources["actuator"]:
                    return _fail(f"event {index} primes a launcher through the wrong surface")
                identifier = str(event.get("launcher_id") or "")
                if _launcher(world, identifier) is None:
                    return _fail(f"event {index} names an unknown launcher")
                state["selected_launcher"] = identifier
                state["primed"] = identifier
            elif kind == "launch_start":
                identifier = str(event.get("launcher_id") or "")
                if event.get("input_source") != "contact_physics" or state["primed"] != identifier or state["selected_launcher"] != identifier:
                    return _fail(f"event {index} launches without a matching primed contact block")
                launcher = _launcher(world, identifier)
                if launcher is None:
                    return _fail(f"event {index} launches an unknown block")
                contact = launcher.get("contact")
                if not isinstance(contact, list) or len(contact) != 3:
                    return _fail(f"event {index} names a launcher without a contact surface")
                contact_radius = _num(chamber["rules"]["contact_radius"], "contact radius")
                if math.dist((state["x"], state["y"], state["z"]), tuple(float(v) for v in contact)) > contact_radius:
                    return _fail(f"event {index} launches without physical contact with the selected surface")
                velocity = launcher.get("launch_velocity")
                if not isinstance(velocity, list) or len(velocity) != 3:
                    return _fail(f"event {index} names a launcher without a launch velocity")
                if not _same(event.get("contact"), contact, 0.08) or not _same(event.get("velocity"), velocity, 0.08):
                    return _fail(f"event {index} falsifies the selected surface contact or launch velocity")
                state["x"], state["y"], state["z"] = (float(contact[0]), float(contact[1]), float(contact[2]))
                state["in_flight"] = True
                state["flight_origin"] = [state["x"], state["y"], state["z"]]
                state["flight_velocity"] = [float(value) for value in velocity]
                state["flight_elapsed_ms"] = 0.0
                launch_started_at = t_ms
            elif kind == "launch_land":
                if not state["in_flight"] or launch_started_at is None or state["flight_elapsed_ms"] != float(chamber["rules"]["flight_duration_ms"]):
                    return _fail(f"event {index} lands before the visible launch arc completes")
                identifier = str(event.get("launcher_id") or "")
                launcher = _launcher(world, identifier)
                if launcher is None or identifier != state["primed"] or event.get("input_source") != "contact_physics":
                    return _fail(f"event {index} has an invalid landing identity")
                origin = state["flight_origin"]
                velocity = state["flight_velocity"]
                elapsed = state["flight_elapsed_ms"] / 1000.0
                gravity = _num(chamber["rules"]["gravity"], "gravity")
                expected_physical = (
                    float(origin[0]) + float(velocity[0]) * elapsed,
                    float(origin[1]) + float(velocity[1]) * elapsed,
                    float(origin[2]) + float(velocity[2]) * elapsed - 0.5 * gravity * elapsed * elapsed,
                )
                target = launcher["landing"]
                actual = (_num(event.get("x"), "landing x"), _num(event.get("y"), "landing y"), _num(event.get("z"), "landing z"))
                if any(abs(actual[pos] - expected_physical[pos]) > 0.08 for pos in range(3)) or any(abs(actual[pos] - float(target[pos])) > 0.08 for pos in range(3)):
                    return _fail(f"event {index} lands at a point different from the gravity arc")
                state["x"], state["y"], state["z"] = float(target[0]), float(target[1]), float(target[2])
                state["landing_z"] = float(target[2])
                state["in_flight"] = False
                state["landed"] = True
                launch_started_at = None
            elif kind == "terminal_activate":
                if event.get("input_source") != sources["terminal"]:
                    return _fail(f"event {index} activates the terminal through the wrong surface")
                target = chamber["terminal"]["position"]
                if not state["landed"] or state["red_stage"] != int(truth["required_red_stage"]) or state["stair_end"] != str(truth["required_stair_end"]) or state["primed"] != str(truth["required_launcher_id"]):
                    return _fail(f"event {index} activates the terminal before the causeway is configured")
                if math.dist((state["x"], state["y"], state["z"]), tuple(float(v) for v in target)) > float(chamber["terminal"]["radius"]):
                    return _fail(f"event {index} activates the terminal outside its physical region")
                state["terminal"] = True
            elif kind == "abandon":
                return _fail("causeway was abandoned")
            else:
                return _fail(f"event {index} has unknown kind {kind!r}")
        if any(state["keys"].values()):
            return _fail("a movement key remained held at submission")
        expected_launcher = str(truth.get("required_launcher_id") or "")
        passed = (
            payload.get("completed") is True
            and state["terminal"]
            and not state["failed"]
            and not state["in_flight"]
            and state["red_stage"] == int(truth["required_red_stage"])
            and state["stair_end"] == str(truth["required_stair_end"])
            and state["primed"] == expected_launcher
            and state["landed"]
        )
        if not passed:
            return _fail(f"route incomplete: red={state['red_stage']}/{truth['required_red_stage']}; stair={state['stair_end']}; launcher={state['primed']}; terminal={state['terminal']}")
        return {"graded": True, "passed": True, "score": 100, "feedback": f"physical replay reached terminal after staged extrusion, {state['stair_end']} stair rise, and {expected_launcher} contact launch"}
    except (KeyError, TypeError, ValueError, IndexError, OverflowError) as exc:
        return _fail(f"causeway replay error: {exc}")


def cheat(public: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    return {
        "red_stage": truth.get("required_red_stage"),
        "stair_end": truth.get("required_stair_end"),
        "launcher_id": truth.get("required_launcher_id"),
        "terminal": truth.get("world", {}).get("chamber", {}).get("terminal"),
    }
