from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "restless_piston"
MODE_ACTIONS = {
    "nothing": {"pump", "heat", "wall"},
    "volume": {"pump", "heat"},
    "temperature": {"pump", "wall"},
    "pressure_v": {"pump", "heat"},
    "pressure_t": {"pump", "wall"},
}
MODES = set(MODE_ACTIONS)


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _close(first: Any, second: Any, tolerance: float) -> bool:
    try:
        return math.isfinite(float(first)) and abs(float(first) - float(second)) <= float(tolerance)
    except (TypeError, ValueError):
        return False


def _pressure(state: dict[str, float]) -> float:
    return float(state["particles"]) * float(state["temperature"]) / (float(state["volume"]) * 1000.0)


def _apply(
    state: dict[str, float],
    action: str,
    direction: int,
    physics: dict[str, Any],
    mode: str,
    reference_pressure: float,
) -> bool:
    if action not in MODE_ACTIONS.get(mode, set()):
        return False
    sign = 1 if int(direction) > 0 else -1
    if action == "pump":
        state["particles"] += sign * int(physics["pump_delta"])
        if not 6 <= state["particles"] <= 92:
            return False
    elif action == "heat":
        state["temperature"] += sign * float(physics["heat_delta"])
        if not float(physics["min_temperature"]) <= state["temperature"] <= float(physics["max_temperature"]):
            return False
    elif action == "wall":
        state["volume"] += sign * float(physics["wall_delta"])
        if not float(physics["min_volume"]) <= state["volume"] <= float(physics["max_volume"]):
            return False
    if mode == "pressure_v" and action in {"pump", "heat"}:
        if reference_pressure <= 0:
            return False
        state["volume"] = state["particles"] * state["temperature"] / (reference_pressure * 1000.0)
        if not float(physics["min_volume"]) <= state["volume"] <= float(physics["max_volume"]):
            return False
    if mode == "pressure_t" and action in {"pump", "wall"}:
        if state["particles"] <= 0:
            return False
        state["temperature"] = reference_pressure * 1000.0 * state["volume"] / state["particles"]
        if not float(physics["min_temperature"]) <= state["temperature"] <= float(physics["max_temperature"]):
            return False
    return True


def _mode_is_feasible(
    state: dict[str, float],
    mode: str,
    physics: dict[str, Any],
    reference_pressure: float,
) -> bool:
    """Replay the browser's pre-action Hold Constant feasibility check."""
    if mode == "temperature":
        return state["particles"] > 0
    if mode == "pressure_v":
        target_volume = state["particles"] * state["temperature"] / (reference_pressure * 1000.0)
        return float(physics["min_volume"]) <= target_volume <= float(physics["max_volume"])
    if mode == "pressure_t":
        if state["particles"] <= 0:
            return False
        target_temperature = reference_pressure * 1000.0 * state["volume"] / state["particles"]
        return float(physics["min_temperature"]) <= target_temperature <= float(physics["max_temperature"])
    return True


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    if any(source.get("mechanic_id") != MECHANIC_ID for source in (payload, truth, public)):
        return _fail("mechanic mismatch")
    if (
        not truth.get("task_id")
        or payload.get("task_id") != truth.get("task_id")
        or public.get("task_id") != truth.get("task_id")
        or not truth.get("challenge_id")
        or payload.get("challenge_id") != truth.get("challenge_id")
        or public.get("challenge_id") != truth.get("challenge_id")
    ):
        return _fail("stale task or chamber challenge")
    if truth.get("control_condition") != public.get("control_condition"):
        return _fail("public control condition differs from piston contract")

    try:
        condition = truth.get("control_condition")
        condition = condition if isinstance(condition, dict) else None
        parameters = dict((condition or {}).get("difficulty_parameters") or {})
        physics = dict(truth["physics"])
        if public.get("physics") != physics:
            raise ValueError("public physical constants differ from replay constants")
        goal = dict(truth["goal"])
        if public.get("goal") != goal:
            raise ValueError("public target differs from hidden target")
        initial = {key: float(value) for key, value in dict(truth["initial"]).items()}
        if int(initial["particles"]) != int(public["initial"]["particles"]):
            raise ValueError("public particle count differs from chamber state")
        if len(public.get("particles") or []) != int(initial["particles"]):
            raise ValueError("visible molecule cloud has the wrong count")
        mode_pool = set(str(item) for item in (parameters.get("mode_pool") or truth.get("mode_options") or ()))
        required_mode = str(goal["required_mode"])
        if not mode_pool or not mode_pool.issubset(MODES) or required_mode not in MODES or required_mode not in mode_pool:
            raise ValueError("required hold-constant mode is malformed")
        if condition:
            if len(truth.get("planned_actions") or []) != int(parameters["action_count"]):
                raise ValueError("profile action count is not active in the generated plan")
            if abs(int(initial["particles"]) - int(parameters["particle_count"])) > 2:
                raise ValueError("profile particle count is not active in the generated chamber")
            for name in (
                "pump_delta", "heat_delta", "wall_delta", "pressure_tolerance",
                "temperature_tolerance", "volume_tolerance", "settle_ticks", "max_ticks",
                "gauge_noise_ratio", "tick_ms", "min_volume", "max_volume",
                "min_temperature", "max_temperature",
            ):
                if name not in parameters:
                    raise ValueError(f"profile parameter {name} is missing")
        if not 1 <= int(physics["settle_ticks"]) <= 40 or not 20 <= int(physics["max_ticks"]) <= 500:
            raise ValueError("piston timing limits are malformed")
        if not 0 <= float(physics["gauge_noise_ratio"]) <= .4:
            raise ValueError("gauge noise is outside the supported range")
        if not 0.03 <= float(physics["wall_delta"]) <= .2:
            raise ValueError("wall stroke is outside the supported range")
        mode_source = {"simplified": "proxy_control", "full": "direct_manipulation"}
        interaction = str((truth.get("control_condition") or {}).get("interaction") or truth.get("interaction_mode") or "simplified")
        expected_source = mode_source.get(interaction)
        if expected_source is None:
            raise ValueError("piston interaction mode is invalid")
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"invalid piston contract: {exc}")

    events = payload.get("events")
    if not isinstance(events, list) or len(events) > 4000:
        return _fail("piston event transcript is malformed")
    state = dict(initial)
    reference_pressure = float(truth.get("reference_pressure") or _pressure(initial))
    selected_mode: str | None = None
    physical_started = False
    last_tick = 0
    stable_ticks = 0
    terminal = False
    certify: dict[str, Any] | None = None
    physical_actions = 0

    def in_goal() -> bool:
        tolerances = dict(goal["tolerances"])
        return (
            _close(_pressure(state), goal["pressure"], tolerances["pressure"])
            and _close(state["temperature"], goal["temperature"], tolerances["temperature"])
            and _close(state["volume"], goal["volume"], tolerances["volume"])
        )

    def advance(target_tick: int) -> bool:
        nonlocal last_tick, stable_ticks
        if target_tick < last_tick or target_tick > int(physics["max_ticks"]):
            return False
        for _tick in range(last_tick + 1, target_tick + 1):
            stable_ticks = stable_ticks + 1 if in_goal() else 0
        last_tick = target_tick
        return True

    for sequence, item in enumerate(events, 1):
        if not isinstance(item, dict) or item.get("seq") != sequence:
            return _fail(f"event {sequence} sequence invalid")
        if terminal:
            return _fail("piston transcript continues after certification")
        event_type = item.get("type")
        try:
            tick = item["tick"]
            if type(tick) is not int:
                raise ValueError("tick must be an integer")
        except (KeyError, TypeError, ValueError):
            return _fail("piston event has no valid tick")
        if not advance(tick):
            return _fail("piston clock moved backward or past its play limit")
        if event_type == "mode_error":
            mode = str(item.get("mode") or "")
            if mode not in mode_pool or item.get("input_source") != "mode_selector":
                return _fail("hold-constant mode error is outside the active selector pool")
            if _mode_is_feasible(state, mode, physics, reference_pressure):
                return _fail("hold-constant mode error was not physically justified")
            continue
        if event_type == "mode_select":
            mode = str(item.get("mode") or "")
            if mode not in mode_pool or item.get("input_source") != "mode_selector":
                return _fail("hold-constant selection is malformed")
            if not _mode_is_feasible(state, mode, physics, reference_pressure):
                return _fail("hold-constant selection requests an impossible state")
            selected_mode = mode
            stable_ticks = 0
            continue
        if event_type == "action":
            action = str(item.get("action") or "")
            if selected_mode is None:
                return _fail("physical control used before selecting Hold Constant")
            if item.get("input_source") != expected_source:
                return _fail("physical action came from the wrong interaction surface")
            if action not in MODE_ACTIONS[selected_mode]:
                return _fail(f"{selected_mode} makes {action} unavailable")
            direction = item.get("direction")
            if isinstance(direction, bool) or direction not in (-1, 1):
                return _fail("piston action direction is invalid")
            before = dict(state)
            if not _apply(state, action, int(direction), physics, selected_mode, reference_pressure):
                return _fail("action requests an impossible physical state")
            physical_started = True
            physical_actions += 1
            stable_ticks = 0
            reported = item.get("after")
            if reported is not None:
                if not isinstance(reported, dict) or not (
                    _close(reported.get("particles"), state["particles"], .001)
                    and _close(reported.get("temperature"), state["temperature"], .01)
                    and _close(reported.get("volume"), state["volume"], .0005)
                ):
                    return _fail("action reports a state different from physical replay")
            reported_before = item.get("before")
            if reported_before is not None:
                if not isinstance(reported_before, dict) or not (
                    _close(reported_before.get("particles"), before["particles"], .001)
                    and _close(reported_before.get("temperature"), before["temperature"], .01)
                    and _close(reported_before.get("volume"), before["volume"], .0005)
                ):
                    return _fail("action starts from a stale chamber state")
            continue
        if event_type == "certify":
            if selected_mode is None or selected_mode != required_mode or not physical_started:
                return _fail("certification used the wrong constraint or no physical controls")
            terminal = True
            certify = item
            continue
        if event_type == "abandon":
            return _fail("operator abandoned the chamber")
        return _fail(f"unknown piston event {event_type!r}")

    if not isinstance(certify, dict):
        return _fail("no final chamber certification")
    accepted = (
        selected_mode == required_mode
        and physical_actions > 0
        and in_goal()
        and stable_ticks >= int(physics["settle_ticks"])
        and last_tick <= int(physics["max_ticks"])
    )
    reported = certify.get("state")
    if not isinstance(reported, dict) or not (
        _close(reported.get("pressure"), _pressure(state), .02)
        and _close(reported.get("temperature"), state["temperature"], .05)
        and _close(reported.get("volume"), state["volume"], .001)
    ):
        return _fail("certification reports false gauge state")
    if type(certify.get("stable_ticks")) is not int or certify["stable_ticks"] != stable_ticks:
        return _fail("certification reports a false settling interval")
    if bool(certify.get("accepted")) != accepted:
        return _fail("certification verdict disagrees with physical replay")
    passed = accepted and payload.get("completed") is True
    return {
        "graded": True,
        "passed": passed,
        "feedback": (
            f"{selected_mode} settled at {state['particles']:.0f} particles, "
            f"{_pressure(state):.2f} pressure, {state['temperature']:.1f} K, {state['volume']:.3f} volume"
            if passed
            else f"target not settled: stable {stable_ticks}/{physics['settle_ticks']}"
        ),
    }
