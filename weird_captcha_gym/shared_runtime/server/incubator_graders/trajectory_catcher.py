from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "trajectory_catcher"


def _failure(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _finite(value: Any) -> float | None:
    try: number = float(value)
    except (TypeError, ValueError): return None
    return number if math.isfinite(number) else None


def _close(first: Any, second: Any, tolerance: float = 0.12) -> bool:
    a, b = _finite(first), _finite(second)
    return a is not None and b is not None and abs(a - b) <= tolerance


def _point(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, dict): return None
    x, y = _finite(value.get("x")), _finite(value.get("y"))
    return None if x is None or y is None else (x, y)


def _path(round_data: dict[str, Any], t_ms: float) -> tuple[float, float]:
    duration = float(round_data["duration_ms"])
    u = _clamp(t_ms / duration, 0.0, 1.0)
    travel = u if round_data["direction"] == "ltr" else 1.0 - u
    x = 70.0 + travel * 760.0
    base, amplitude, wobble, phase = (float(round_data[key]) for key in ("base_y", "amplitude", "wobble", "phase"))
    if round_data["family"] == "ballistic_arc":
        y = base + amplitude * (4.0 * u * (1.0 - u) - 0.48) + wobble * math.sin(math.tau * u + phase)
    elif round_data["family"] == "sine_drift":
        y = base + amplitude * math.sin(math.tau * (u + phase)) + wobble * math.sin(6.0 * math.pi * u)
    else:
        centered = 2.0 * u - 1.0
        y = base + amplitude * (centered**3 - 0.34 * centered) + wobble * math.sin(4.0 * math.pi * u + phase)
    return x, y


def _velocity_angle(round_data: dict[str, Any], t_ms: float) -> float:
    before = _path(round_data, max(0.0, t_ms - 6.0))
    after = _path(round_data, min(float(round_data["duration_ms"]), t_ms + 6.0))
    return math.degrees(math.atan2(after[1] - before[1], after[0] - before[0])) % 360.0


def _local(point: tuple[float, float], catcher: dict[str, Any]) -> tuple[float, float]:
    radians = math.radians(float(catcher["angle_deg"]))
    cosine, sine = math.cos(radians), math.sin(radians)
    dx, dy = point[0] - float(catcher["x"]), point[1] - float(catcher["y"])
    return dx * cosine + dy * sine, -dx * sine + dy * cosine


def _angle_error(first: float, second: float) -> float:
    return abs((first - second + 90.0) % 180.0 - 90.0)


def _swept_catch(round_data: dict[str, Any], catcher: dict[str, Any]) -> tuple[bool, float | None]:
    if not catcher.get("armed"): return False, None
    current_t = float(round_data["wall_exit_ms"])
    end = float(round_data["duration_ms"])
    projectile_radius = float(round_data["projectile_radius"])
    clear_half_aperture = float(catcher["aperture"]) / 2.0 - projectile_radius
    clear_half_depth = float(round_data["capture_depth"]) / 2.0 - projectile_radius
    while current_t <= end + 1e-6:
        local = _local(_path(round_data, current_t), catcher)
        aligned = _angle_error(_velocity_angle(round_data, current_t), float(catcher["angle_deg"])) <= float(round_data["alignment_tolerance_deg"]) + 1e-9
        if clear_half_aperture >= 0 and clear_half_depth >= 0 and abs(local[0]) <= clear_half_depth and abs(local[1]) <= clear_half_aperture and aligned:
            return True, current_t
        current_t += 5.0
    return False, None


def _catcher(raw: dict[str, Any]) -> dict[str, Any]:
    initial = raw["initial_catcher"]
    return {"x": float(initial["x"]), "y": float(initial["y"]), "angle_deg": int(initial["angle_deg"]) % 180, "aperture": int(initial["aperture"]), "armed": False}


def _state_matches(value: Any, state: dict[str, Any]) -> bool:
    if not isinstance(value, dict): return False
    return _close(value.get("x"), state["x"]) and _close(value.get("y"), state["y"]) and value.get("angle_deg") == state["angle_deg"] and value.get("aperture") == state["aperture"] and bool(value.get("armed")) == bool(state["armed"])


def _control_condition(
    ground_truth: dict[str, Any], public_state: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    condition = ground_truth.get("control_condition")
    if condition is None:
        return (None, None) if public_state.get("control_condition") is None else (None, "public flight control condition is unexpected")
    if not isinstance(condition, dict) or condition != public_state.get("control_condition"):
        return None, "public flight control condition differs from hidden state"
    try:
        difficulty = int(condition.get("difficulty"))
    except (TypeError, ValueError):
        return None, "flight control difficulty is invalid"
    if difficulty not in {1, 2, 3, 4, 5} or str(condition.get("interaction") or "") not in {"simplified", "full"}:
        return None, "flight control condition is invalid"
    if str(condition.get("real_time") or "") not in {"live", "paused"} or not isinstance(condition.get("difficulty_parameters"), dict):
        return None, "flight control condition is incomplete"
    return condition, None


def _in_range(value: Any, low: Any, high: Any) -> bool:
    number, minimum, maximum = _finite(value), _finite(low), _finite(high)
    return number is not None and minimum is not None and maximum is not None and minimum <= number <= maximum


def _matches_controlled_profile(rounds: list[dict[str, Any]], condition: dict[str, Any]) -> bool:
    """Bind declared profile variables to the rendered flight contract."""
    parameters = condition["difficulty_parameters"]
    try:
        timing_step = int(parameters["wall_timing_step_ms"])
        duration_step = int(parameters["duration_step_ms"])
        initial = dict(parameters["initial_catcher"])
        families = {str(item) for item in parameters["family_pool"]}
        if not families or len(rounds) != int(parameters["round_count"]):
            return False
        for round_data in rounds:
            if str(round_data.get("family")) not in families:
                return False
            if not _in_range(round_data.get("duration_ms"), parameters["duration_min_ms"], parameters["duration_max_ms"]):
                return False
            if (int(round_data["duration_ms"]) - int(parameters["duration_min_ms"])) % duration_step:
                return False
            if not _in_range(round_data.get("wall_enter_ms"), parameters["wall_enter_min_ms"], parameters["wall_enter_max_ms"]):
                return False
            if (int(round_data["wall_enter_ms"]) - int(parameters["wall_enter_min_ms"])) % timing_step:
                return False
            if not int(parameters["wall_exit_min_ms"]) <= int(round_data["wall_exit_ms"]) < min(int(parameters["wall_exit_max_exclusive_ms"]), int(round_data["duration_ms"]) - int(parameters["minimum_post_exit_ms"])):
                return False
            if (int(round_data["wall_exit_ms"]) - int(parameters["wall_exit_min_ms"])) % timing_step:
                return False
            if int(round_data.get("minimum_observation_ms")) != int(parameters["minimum_observation_ms"]) or int(round_data.get("commit_margin_ms")) != int(parameters["commit_margin_ms"]):
                return False
            if not _in_range(round_data.get("base_y"), parameters["base_y_min"], parameters["base_y_max"]) or not _in_range(round_data.get("amplitude"), parameters["amplitude_min"], parameters["amplitude_max"]):
                return False
            if not _in_range(round_data.get("wobble"), parameters["wobble_min"], parameters["wobble_max"]) or not _in_range(round_data.get("phase"), parameters["phase_min"], parameters["phase_max"]):
                return False
            if not _in_range(round_data.get("projectile_radius"), parameters["projectile_radius_min"], parameters["projectile_radius_max"]):
                return False
            if int(round_data.get("alignment_tolerance_deg")) != int(parameters["alignment_tolerance_deg"]) or int(round_data.get("capture_depth")) != int(parameters["capture_depth"]):
                return False
            if int(round_data.get("aperture_min")) != int(parameters["aperture_min"]) or int(round_data.get("aperture_max")) != int(parameters["aperture_max"]) or int(round_data.get("aperture_step")) != int(parameters["aperture_step"]):
                return False
            if int(round_data.get("rotation_step_deg")) != int(parameters["rotation_step_deg"]) or int(round_data.get("replay_limit")) != int(parameters["replay_limit"]):
                return False
            if not _close(round_data["initial_catcher"].get("x"), initial["x"]) or not _close(round_data["initial_catcher"].get("y"), initial["y"]):
                return False
            if int(round_data["initial_catcher"].get("angle_deg")) != int(initial["angle_deg"]) or int(round_data["initial_catcher"].get("aperture")) != int(initial["aperture"]):
                return False
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return False
    return True


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if str(payload.get("mechanic_id") or "") != MECHANIC_ID or str(ground_truth.get("mechanic_id") or "") != MECHANIC_ID: return _failure("mechanic mismatch")
    task_id = str(ground_truth.get("task_id") or "")
    if not task_id or str(payload.get("task_id") or "") != task_id or str(public_state.get("task_id") or "") != task_id: return _failure("task identity mismatch")
    if not challenge_id or str(payload.get("challenge_id") or "") != challenge_id: return _failure("stale challenge")
    if str(public_state.get("challenge_id") or "") != challenge_id or str(public_state.get("mechanic_id") or "") != MECHANIC_ID: return _failure("public flight log does not match hidden state")
    condition, condition_error = _control_condition(ground_truth, public_state)
    if condition_error:
        return _failure(condition_error)
    interaction = str((condition or {}).get("interaction") or "")
    if condition is not None and str(payload.get("interaction") or "") != interaction:
        return _failure("flight transcript belongs to the other interaction mode")
    rounds = ground_truth.get("rounds")
    if not isinstance(rounds, list) or not rounds or public_state.get("rounds") != rounds: return _failure("analytic flight schedule is missing or inconsistent")
    if int(ground_truth.get("round_count") or 0) != len(rounds) or int(public_state.get("round_count") or 0) != len(rounds):
        return _failure("flight round count is inconsistent")
    if condition is not None and not _matches_controlled_profile(rounds, condition):
        return _failure("analytic flight schedule does not match its declared difficulty profile")
    events = payload.get("events")
    if not isinstance(events, list) or not events or len(events) > 1800: return _failure("flight transcript is missing or too long")

    current_index = 0
    expected_attempt = 0
    phase = "await_start"
    context: dict[str, Any] | None = None
    completed: list[str] = []
    replay_used = {str(item["id"]): 0 for item in rounds}
    attempt_counts = {str(item["id"]): 0 for item in rounds}
    replay_count = 0
    catcher_reset_count = 0
    challenge_reset_count = 0
    caught_crossings: list[float] = []
    previous_global = -1.0

    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("seq") != sequence: return _failure(f"flight event {sequence} has invalid sequence")
        global_t = _finite(event.get("t_ms"))
        if global_t is None or global_t < previous_global or global_t > 7_200_000: return _failure(f"flight event {sequence} has invalid timestamp")
        previous_global = global_t
        action = str(event.get("type") or "")
        if phase == "final_terminal": return _failure("flight transcript continues after terminal catch")

        if action == "challenge_reset":
            if phase not in {"terminal_miss", "terminal_caught"}: return _failure("challenge reset occurred during an active flight")
            current_index, expected_attempt, phase, context = 0, 0, "await_start", None
            completed = []
            replay_used = {str(item["id"]): 0 for item in rounds}
            challenge_reset_count += 1
            if event.get("next_round_id") != rounds[0]["id"]: return _failure("challenge reset points at the wrong flight")
            continue

        if action == "replay":
            if phase != "terminal_miss" or context is None: return _failure("round replay occurred without a physical miss")
            round_data = rounds[current_index]
            round_id = str(round_data["id"])
            if event.get("round_id") != round_id or event.get("attempt_before") != expected_attempt or replay_used[round_id] >= int(round_data["replay_limit"]): return _failure("round replay exceeds its budget or replays the wrong attempt")
            replay_used[round_id] += 1
            replay_count += 1
            expected_attempt += 1
            phase, context = "await_start", None
            continue

        if action == "advance":
            if phase != "terminal_caught" or current_index >= len(rounds) - 1: return _failure("round advance occurred without a completed non-final catch")
            if event.get("from_round_id") != rounds[current_index]["id"] or event.get("to_round_id") != rounds[current_index + 1]["id"]: return _failure("round advance targets the wrong flight")
            current_index += 1
            expected_attempt = 0
            phase, context = "await_start", None
            continue

        if action == "round_start":
            if phase != "await_start": return _failure("round starts in an impossible order")
            round_data = rounds[current_index]
            if event.get("round_id") != round_data["id"] or event.get("attempt") != expected_attempt or event.get("round_t_ms") != 0: return _failure("round start identity disagrees with replay")
            context = {
                "catcher": _catcher(round_data), "last_round_t": 0.0, "observations": [], "dragging": False,
                "gesture": None, "drag_offset": (0.0, 0.0), "last_pointer": None, "drag_moves": 0, "rotations": 0, "resizes": 0,
                "global_start": global_t,
            }
            attempt_counts[str(round_data["id"])] += 1
            phase = "running"
            continue

        if phase != "running" or context is None: return _failure(f"flight action {action!r} occurs outside a running round")
        round_data = rounds[current_index]
        if event.get("round_id") != round_data["id"] or event.get("attempt") != expected_attempt: return _failure(f"flight event {sequence} is bound to the wrong round")
        round_t = _finite(event.get("round_t_ms"))
        if round_t is None or round_t < context["last_round_t"] or round_t > float(round_data["duration_ms"]) + 500: return _failure(f"flight event {sequence} has impossible round time")
        if abs(round_t - (global_t - context["global_start"])) > 90: return _failure(f"flight event {sequence} compresses or dilates real elapsed time")
        context["last_round_t"] = round_t
        hidden_start = float(round_data["wall_enter_ms"])
        commit_deadline = float(round_data["wall_exit_ms"]) - float(round_data["commit_margin_ms"])
        in_commit_window = hidden_start <= round_t <= commit_deadline

        if action == "observe_sample":
            position = _point(event.get("position"))
            expected = _path(round_data, round_t)
            if round_t > hidden_start or position is None or not _close(position[0], expected[0]) or not _close(position[1], expected[1]): return _failure(f"observation sample {sequence} exposes or misreports the hidden flight")
            context["observations"].append(round_t)
            continue
        if action == "catcher_drag_start":
            point = _point(event.get("pointer"))
            state = context["catcher"]
            if condition is not None and event.get("input_source") != "canvas_drag": return _failure(f"catcher drag {sequence} uses the wrong interaction input")
            if not in_commit_window or state["armed"] or context["dragging"] or point is None or math.hypot(point[0] - state["x"], point[1] - state["y"]) > 42: return _failure(f"catcher drag {sequence} starts outside the hidden physical handle")
            context["drag_offset"] = (point[0] - state["x"], point[1] - state["y"])
            context["last_pointer"] = point
            context["dragging"] = True; context["gesture"] = "move"
            if not _state_matches(event.get("catcher_before"), state): return _failure(f"catcher drag {sequence} reports stale state")
            continue
        if action == "catcher_drag_move":
            point = _point(event.get("pointer"))
            before = _point(event.get("from"))
            after = _point(event.get("to"))
            state = context["catcher"]
            if condition is not None and event.get("input_source") != "canvas_drag": return _failure(f"catcher drag move {sequence} uses the wrong interaction input")
            if not in_commit_window or not context["dragging"] or context["gesture"] != "move" or state["armed"] or point is None or before is None or after is None: return _failure(f"catcher drag move {sequence} occurs outside a valid drag")
            if math.hypot(point[0] - context["last_pointer"][0], point[1] - context["last_pointer"][1]) > 150: return _failure(f"catcher drag move {sequence} teleports")
            if not _close(before[0], state["x"]) or not _close(before[1], state["y"]): return _failure(f"catcher drag move {sequence} has a stale origin")
            expected_x = round(_clamp(point[0] - context["drag_offset"][0], 34, 866), 2)
            expected_y = round(_clamp(point[1] - context["drag_offset"][1], 34, 446), 2)
            if not _close(after[0], expected_x) or not _close(after[1], expected_y): return _failure(f"catcher drag move {sequence} reports a false destination")
            state["x"], state["y"] = expected_x, expected_y
            context["last_pointer"] = point
            context["drag_moves"] += 1
            continue
        if action == "catcher_drag_end":
            point = _point(event.get("pointer"))
            # Releasing after the commit horn changes no geometry and must not
            # poison a later replay; only drag starts/moves are commit-gated.
            if condition is not None and event.get("input_source") != "canvas_drag": return _failure(f"catcher drag end {sequence} uses the wrong interaction input")
            if not context["dragging"] or context["gesture"] != "move" or point is None or not _state_matches(event.get("catcher_after"), context["catcher"]): return _failure(f"catcher drag end {sequence} is malformed")
            context["dragging"] = False; context["gesture"] = None
            continue
        if action == "catcher_rotate_start":
            point = _point(event.get("pointer")); state = context["catcher"]
            if condition is None or interaction != "full" or event.get("input_source") != "canvas_ring": return _failure(f"catcher rotation start {sequence} uses the wrong interaction input")
            if not in_commit_window or state["armed"] or context["dragging"] or point is None or not _state_matches(event.get("catcher_before"), state): return _failure(f"catcher rotation start {sequence} is malformed")
            radius = math.hypot(point[0] - state["x"], point[1] - state["y"])
            if not 34 <= radius <= 100: return _failure(f"catcher rotation start {sequence} misses the visible ring")
            context["dragging"] = True; context["gesture"] = "rotate"; context["last_pointer"] = point
            continue
        if action == "catcher_rotate":
            state = context["catcher"]
            delta = event.get("delta_deg")
            if condition is not None and interaction == "simplified" and event.get("input_source") != "transform_button": return _failure(f"catcher rotation {sequence} uses the wrong interaction input")
            if condition is not None and interaction == "full":
                point = _point(event.get("pointer")); after = event.get("angle_after")
                if not in_commit_window or state["armed"] or not context["dragging"] or context["gesture"] != "rotate" or point is None or event.get("input_source") != "canvas_ring" or event.get("angle_before") != state["angle_deg"]: return _failure(f"catcher rotation {sequence} is malformed")
                radius = math.hypot(point[0] - state["x"], point[1] - state["y"])
                step = int(round_data["rotation_step_deg"])
                if not 34 <= radius <= 100 or not isinstance(after, int) or after % step or not 0 <= after < 180: return _failure(f"catcher rotation {sequence} lies about direct orientation")
                state["angle_deg"] = after
            else:
                step = int(round_data["rotation_step_deg"])
                if not in_commit_window or state["armed"] or context["dragging"] or delta not in {-step, step} or event.get("angle_before") != state["angle_deg"]: return _failure(f"catcher rotation {sequence} is malformed")
                state["angle_deg"] = (state["angle_deg"] + int(delta)) % 180
                if event.get("angle_after") != state["angle_deg"]: return _failure(f"catcher rotation {sequence} lies about orientation")
            context["rotations"] += 1
            continue
        if action == "catcher_rotate_end":
            point = _point(event.get("pointer"))
            if condition is None or interaction != "full" or event.get("input_source") != "canvas_ring" or not context["dragging"] or context["gesture"] != "rotate" or point is None or not _state_matches(event.get("catcher_after"), context["catcher"]): return _failure(f"catcher rotation end {sequence} is malformed")
            context["dragging"] = False; context["gesture"] = None
            continue
        if action == "catcher_resize_start":
            point = _point(event.get("pointer")); state = context["catcher"]
            if condition is None or interaction != "full" or event.get("input_source") != "canvas_mouth": return _failure(f"catcher resize start {sequence} uses the wrong interaction input")
            if not in_commit_window or state["armed"] or context["dragging"] or point is None or not _state_matches(event.get("catcher_before"), state): return _failure(f"catcher resize start {sequence} is malformed")
            local = _local(point, state)
            if abs(local[0]) > 22 or abs(abs(local[1]) - state["aperture"] / 2) > 18: return _failure(f"catcher resize start {sequence} misses the visible mouth handle")
            context["dragging"] = True; context["gesture"] = "resize"; context["last_pointer"] = point
            continue
        if action == "catcher_resize":
            state = context["catcher"]
            delta = event.get("delta")
            if condition is not None and interaction == "simplified" and event.get("input_source") != "transform_button": return _failure(f"catcher resize {sequence} uses the wrong interaction input")
            step = int(round_data["aperture_step"])
            direct_resize = condition is not None and interaction == "full"
            if direct_resize:
                point = _point(event.get("pointer"))
                if not in_commit_window or state["armed"] or not context["dragging"] or context["gesture"] != "resize" or point is None or event.get("input_source") != "canvas_mouth" or event.get("aperture_before") != state["aperture"] or not isinstance(delta, int) or not delta or delta % step: return _failure(f"catcher resize {sequence} is malformed")
            elif not in_commit_window or state["armed"] or context["dragging"] or delta not in {-step, step} or event.get("aperture_before") != state["aperture"]:
                return _failure(f"catcher resize {sequence} is malformed")
            next_aperture = state["aperture"] + int(delta)
            if not int(round_data["aperture_min"]) <= next_aperture <= int(round_data["aperture_max"]): return _failure("catcher resize exceeds physical stops")
            state["aperture"] = next_aperture
            if event.get("aperture_after") != state["aperture"]: return _failure(f"catcher resize {sequence} lies about aperture")
            context["resizes"] += 1
            continue
        if action == "catcher_resize_end":
            point = _point(event.get("pointer"))
            if condition is None or interaction != "full" or event.get("input_source") != "canvas_mouth" or not context["dragging"] or context["gesture"] != "resize" or point is None or not _state_matches(event.get("catcher_after"), context["catcher"]): return _failure(f"catcher resize end {sequence} is malformed")
            context["dragging"] = False; context["gesture"] = None
            continue
        if action == "catcher_reset":
            if not in_commit_window or context["catcher"]["armed"] or context["dragging"]: return _failure("catcher reset occurred outside the hidden setup interval")
            context["catcher"] = _catcher(round_data)
            context["drag_moves"] = 0
            context["rotations"] = 0
            context["resizes"] = 0
            catcher_reset_count += 1
            if not _state_matches(event.get("catcher_after"), context["catcher"]): return _failure("catcher reset does not restore its stops")
            continue
        if action == "arm":
            state = context["catcher"]
            if not in_commit_window or state["armed"] or context["dragging"]: return _failure("catcher was armed outside the pre-emergence commitment window")
            state["armed"] = True
            if not _state_matches(event.get("catcher"), state): return _failure("arm event reports a false catcher transform")
            continue
        if action == "round_result":
            if round_t < float(round_data["duration_ms"]) - 80 or context["dragging"]: return _failure("round terminated before its analytic flight completed")
            observations = context["observations"]
            required_samples = max(8, math.ceil(float(round_data["minimum_observation_ms"]) / 150.0))
            if len(observations) < required_samples or max(observations) - min(observations) < float(round_data["minimum_observation_ms"]): return _failure("round lacks genuine visible observation duration")
            caught, crossing = _swept_catch(round_data, context["catcher"])
            if bool(event.get("caught")) != caught or not _state_matches(event.get("catcher"), context["catcher"]): return _failure("round result disagrees with swept catcher geometry")
            if caught:
                # One standard drag may produce one pointermove between its
                # down/up endpoints. The displacement and resulting catcher
                # geometry are already replayed above; requiring event
                # fragmentation would reject the same physical action solely
                # because of how an input backend samples it.
                if context["drag_moves"] < 1: return _failure("successful catch lacks physical catcher placement")
                if not _close(event.get("crossing_ms"), crossing, 0.15): return _failure("reported crossing time disagrees with swept replay")
                completed.append(str(round_data["id"]))
                caught_crossings.append(float(crossing))
                phase = "final_terminal" if current_index == len(rounds) - 1 else "terminal_caught"
            else:
                if event.get("crossing_ms") is not None: return _failure("miss reports a fabricated crossing")
                phase = "terminal_miss"
            continue
        return _failure(f"flight event {sequence} has invalid action {action!r}")

    expected_final = {
        "completed_round_ids": completed,
        "replay_count": replay_count,
        "catcher_reset_count": catcher_reset_count,
        "challenge_reset_count": challenge_reset_count,
        "round_attempt_counts": [{"round_id": str(item["id"]), "attempts": attempt_counts[str(item["id"])]} for item in rounds],
    }
    if payload.get("final_state") != expected_final: return _failure("claimed final flight state does not match transcript replay")
    passed = phase == "final_terminal" and completed == [str(item["id"]) for item in rounds] and len(caught_crossings) == len(rounds)
    return {
        "graded": True,
        "passed": passed,
        "score": 100 if passed else 0,
        "feedback": f"replayed {len(completed)}/{len(rounds)} swept catches; replays {replay_count}; catcher resets {catcher_reset_count}; challenge resets {challenge_reset_count}",
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {"solutions": ground_truth.get("solutions") or [], "answers": []}
