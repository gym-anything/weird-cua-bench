from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "quiet_transfer"
GOAL_SCALES = {
    "center": 0.015,
    "velocity": 0.020,
    "width": 0.0015,
    "width_velocity": 0.003,
    "phase": 0.070,
}


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _close(first: Any, second: Any, tolerance: float = 1e-4) -> bool:
    try:
        return math.isfinite(float(first)) and abs(float(first) - float(second)) <= tolerance
    except (TypeError, ValueError):
        return False


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _curve_error(first: list[float], second: list[float]) -> float:
    if len(first) != len(second) or not first:
        return float("inf")
    return math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(first, second)) / len(first))


def _interpolate(curve: list[float], tick: int, ticks: int) -> float:
    if ticks <= 0:
        return float(curve[-1])
    position = _clamp(float(tick) / float(ticks), 0.0, 1.0) * (len(curve) - 1)
    index = min(len(curve) - 2, max(0, int(math.floor(position))))
    fraction = position - index
    return float(curve[index]) * (1.0 - fraction) + float(curve[index + 1]) * fraction


def _goal_fidelity(state: dict[str, float], goal_state: dict[str, Any]) -> float:
    """Score the same terminal residuals that the browser renders.

    The goal state is public task state and is drawn as the dashed terminal
    profile plus raw state markers.  Keeping this calculation independent of
    ``truth`` prevents an unseen route comparison from disagreeing with the
    visible objective.
    """
    try:
        squared_error = sum(
            ((float(state[field]) - float(goal_state[field])) / scale) ** 2
            for field, scale in GOAL_SCALES.items()
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return 0.0
    if not math.isfinite(squared_error):
        return 0.0
    return _clamp(math.exp(-0.5 * squared_error), 0.0, 1.0)


def _state_at(curve: list[float], tick: int, config: dict[str, Any]) -> dict[str, float]:
    curve_config = config.get("curve") or {}
    ticks = int(config.get("playback_ticks", curve_config.get("playback_ticks")))
    model = config["wave_model"]
    dt = float(model["dt"])
    spring = float(model["spring_strength"])
    damping = float(model["velocity_damping"])
    excitation = float(model["excitation_gain"])
    width_damping = float(model["width_damping"])
    width_restore = float(model["width_restore"])
    base_width = float(model["base_width"])
    center = float(curve[0])
    velocity = 0.0
    width = base_width
    width_velocity = 0.0
    previous_trap = float(curve[0])
    previous_previous_trap = float(curve[0])
    for current_tick in range(1, max(0, int(tick)) + 1):
        trap = _interpolate(curve, current_tick, ticks)
        acceleration = trap - 2.0 * previous_trap + previous_previous_trap
        velocity += (3.5 * spring * (trap - center) - damping * velocity) * dt
        center += velocity * dt
        width_velocity += (
            abs(acceleration) * excitation
            - width_damping * width_velocity
            - width_restore * (width - base_width)
        ) * dt
        width += width_velocity * dt
        previous_previous_trap, previous_trap = previous_trap, trap
    phase = velocity * 4.0 + width_velocity * 8.0
    state = {
        "tick": int(tick),
        "trap": _interpolate(curve, int(tick), ticks),
        "center": center,
        "velocity": velocity,
        "width": width,
        "width_velocity": width_velocity,
        "phase": phase,
    }
    state["fidelity"] = _goal_fidelity(state, config["requirements"]["goal_state"])
    return state


def simulate(curve: list[float], public_state: dict[str, Any]) -> list[dict[str, float]]:
    config = {
        "playback_ticks": int(public_state["curve"]["playback_ticks"]),
        "wave_model": public_state["wave_model"],
        "destination": public_state["destination"],
        "requirements": public_state["requirements"],
    }
    return [_state_at(curve, tick, config) for tick in range(config["playback_ticks"] + 1)]


def _same_public_contract(truth: dict[str, Any], public: dict[str, Any]) -> bool:
    for field in (
        "task_id",
        "challenge_id",
        "difficulty_level",
        "interaction_mode",
        "source",
        "destination",
        "curve",
        "wave_model",
        "requirements",
    ):
        if truth.get(field) != public.get(field):
            return False
    return True


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    if str(payload.get("mechanic_id") or "") != MECHANIC_ID or str(truth.get("mechanic_id") or "") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    if not truth.get("challenge_id") or payload.get("challenge_id") != truth.get("challenge_id"):
        return _fail("stale challenge")
    if payload.get("task_id") != truth.get("task_id") or public.get("challenge_id") != truth.get("challenge_id"):
        return _fail("task identity mismatch")
    if not _same_public_contract(truth, public):
        return _fail("public/private quiet-transfer contract skew")
    condition = truth.get("control_condition")
    if condition != public.get("control_condition"):
        return _fail("public interaction condition differs from quiet-transfer contract")
    interaction = str((condition or {}).get("interaction") or truth.get("interaction_mode") or "")
    expected_source = {"simplified": "nudge_buttons", "full": "curve_drag"}.get(interaction)
    if expected_source is None:
        return _fail("quiet-transfer interaction condition is invalid")
    if payload.get("interaction") != interaction:
        return _fail("submitted interaction surface does not match the selected contract")
    curve_config = public.get("curve") or {}
    knot_count = int(curve_config.get("knot_count") or 0)
    minimum = float(curve_config.get("minimum") or 0.05)
    maximum = float(curve_config.get("maximum") or 0.95)
    initial = curve_config.get("initial")
    if not isinstance(initial, list) or len(initial) != knot_count:
        return _fail("initial quiet-transfer curve is malformed")
    requirements = public.get("requirements") or {}
    goal_state = requirements.get("goal_state")
    valid_goal_state = isinstance(goal_state, dict)
    if valid_goal_state:
        for field in GOAL_SCALES:
            try:
                valid_goal_state = valid_goal_state and math.isfinite(float(goal_state[field]))
            except (KeyError, TypeError, ValueError):
                valid_goal_state = False
    if not valid_goal_state:
        return _fail("visible quiet-transfer goal state is malformed")
    events = payload.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 12000:
        return _fail("quiet-transfer transcript missing or outside limits")
    try:
        current_curve = [float(value) for value in initial]
    except (TypeError, ValueError):
        return _fail("initial curve contains a non-numeric knot")
    if not all(math.isfinite(value) for value in current_curve):
        return _fail("initial curve contains a non-finite knot")
    expected_events = 0
    complete_runs = 0
    first_complete_curve: list[float] | None = None
    revision_after_playback = False
    last_complete_curve: list[float] | None = None
    final_state: dict[str, Any] | None = None
    run_active = False
    run_curve: list[float] | None = None
    expected_tick = 1
    index = 0
    while index < len(events):
        event = events[index]
        expected_events += 1
        if not isinstance(event, dict) or event.get("seq") != expected_events:
            return _fail(f"event {expected_events} sequence mismatch")
        kind = str(event.get("type") or "")
        if kind == "curve_edit":
            if run_active:
                return _fail("curve edit occurred while playback was active")
            try:
                knot = event["index"]
                if type(knot) is not int:
                    return _fail("malformed curve edit index")
                before = float(event["before"])
                after = float(event["after"])
            except (KeyError, TypeError, ValueError):
                return _fail("malformed curve edit")
            if knot <= 0 or knot >= knot_count - 1 or event.get("input_source") != expected_source:
                return _fail("curve edit uses the wrong interaction input or endpoint")
            if not _close(before, current_curve[knot], 0.002):
                return _fail("curve edit starts from stale knot geometry")
            if not math.isfinite(after) or not minimum <= after <= maximum:
                return _fail("curve edit leaves the visible control bounds")
            if interaction == "simplified":
                step = float(curve_config["nudge_step"])
                position = current_curve[knot] / step
                grids = (math.floor(position + 1e-7) + 1, math.ceil(position - 1e-7) - 1)
                if not any(_close(after, round(_clamp(grid * step, minimum, maximum), 3), 1e-6) for grid in grids):
                    return _fail("curve edit does not match one visible nudge")
            # A captured drag can cover the entire range in one pointermove.
            # Event density is a transport detail, not a motor constraint.
            if abs(after - current_curve[knot]) < 0.0005:
                return _fail("curve edit has no visible effect")
            if complete_runs > 0:
                revision_after_playback = True
            current_curve[knot] = after
        elif kind == "curve_reset":
            if run_active:
                return _fail("curve reset occurred while playback was active")
            if event.get("input_source") != "reset_button":
                return _fail("curve reset is not bound to the visible reset control")
            current_curve = [float(value) for value in initial]
        elif kind == "run_start":
            if run_active:
                return _fail("playback was started before the prior run completed")
            if event.get("input_source") != "run_button":
                return _fail("playback was not started by the visible run control")
            submitted_curve = event.get("curve")
            if not isinstance(submitted_curve, list) or len(submitted_curve) != knot_count or any(not _close(value, current_curve[pos], 0.002) for pos, value in enumerate(submitted_curve)):
                return _fail("playback started from a curve different from the visible curve")
            if index + 1 >= len(events) or not isinstance(events[index + 1], dict):
                return _fail("playback has no recorded samples")
            run_active = True
            run_curve = [float(value) for value in submitted_curve]
            expected_tick = 1
        elif kind == "playback_sample":
            if not run_active or run_curve is None:
                return _fail("playback sample arrived outside an active run")
            try:
                tick = event["tick"]
                if type(tick) is not int:
                    return _fail("playback sample tick is malformed")
            except (KeyError, TypeError, ValueError):
                return _fail("playback sample tick is malformed")
            if tick != expected_tick or tick < 0 or tick > int(curve_config["playback_ticks"]):
                return _fail("playback sample is outside the configured duration")
            expected = _state_at(run_curve, tick, public)
            observed = event.get("state")
            if not isinstance(observed, dict):
                return _fail("playback sample state is missing")
            for field in ("trap", "center", "velocity", "width", "width_velocity", "phase", "fidelity"):
                if not _close(observed.get(field), expected[field], 0.003):
                    return _fail(f"playback sample {field} disagrees with wave replay")
            expected_tick += 1
        elif kind == "run_complete":
            if not run_active or run_curve is None:
                return _fail("playback completion is not bound to an active run")
            if index == 0 or events[index - 1].get("type") != "playback_sample":
                return _fail("playback completed without a final visible sample")
            if expected_tick != int(curve_config["playback_ticks"]) + 1:
                return _fail("playback completed before the final visible sample")
            if type(event.get("ticks")) is not int or event["ticks"] != int(curve_config["playback_ticks"]):
                return _fail("playback completed at the wrong tick")
            expected = _state_at(run_curve, int(curve_config["playback_ticks"]), public)
            observed = event.get("state")
            if not isinstance(observed, dict) or any(not _close(observed.get(field), expected[field], 0.003) for field in ("center", "velocity", "width", "width_velocity", "phase", "fidelity")):
                return _fail("completed state disagrees with wave replay")
            if not isinstance(event.get("curve"), list) or len(event["curve"]) != knot_count or any(not _close(value, current_curve[pos], 0.002) for pos, value in enumerate(event["curve"])):
                return _fail("completed run curve differs from the visible curve")
            if first_complete_curve is None:
                first_complete_curve = list(run_curve)
            complete_runs += 1
            last_complete_curve = list(run_curve)
            final_state = expected
            run_active = False
            run_curve = None
        else:
            return _fail(f"unknown quiet-transfer event {kind!r}")
        if kind == "run_complete":
            pass
        index += 1

    if run_active:
        return _fail("playback ended before its final visible sample")
    if not events or events[-1].get("type") != "run_complete":
        return _fail("quiet transfer was certified after changing the curve without a new complete playback")
    if last_complete_curve is None or any(
        not _close(value, current_curve[pos], 0.002)
        for pos, value in enumerate(last_complete_curve)
    ):
        return _fail("submitted curve was changed after the last complete playback")

    minimum_playbacks = int(public.get("requirements", {}).get("minimum_playbacks") or 2)
    if complete_runs < minimum_playbacks:
        return _fail(
            f"quiet transfer requires at least {minimum_playbacks} complete calibration playbacks"
        )
    if not revision_after_playback:
        return _fail("quiet transfer requires a visible curve revision after observing playback")
    if first_complete_curve is None or _curve_error(first_complete_curve, current_curve) <= 0.002:
        return _fail("the certified playback must use a revised curve")

    submitted_curve = payload.get("curve")
    if not isinstance(submitted_curve, list) or len(submitted_curve) != knot_count or any(not _close(value, current_curve[pos], 0.002) for pos, value in enumerate(submitted_curve)):
        return _fail("submitted curve does not match the replayed visible edits")
    if final_state is None or payload.get("completed") is not True:
        return _fail("quiet transfer was certified before a complete playback")
    threshold = float(requirements["fidelity_threshold"])
    fidelity = float(final_state["fidelity"])
    passed = fidelity + 1e-7 >= threshold
    return {
        "graded": True,
        "passed": passed,
        "feedback": (
            f"visible goal fidelity {fidelity:.4f} / required {threshold:.4f}; "
            f"{complete_runs} deterministic playback(s) replayed"
        ),
    }
