from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "wonky_text_hostile_rendering"


def _wrap(value: float) -> float:
    return value % 360.0


def _delta(first: float, second: float) -> float:
    return abs((first - second + 180.0) % 360.0 - 180.0)


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if str(payload.get("mechanic_id") or "") != MECHANIC_ID or str(ground_truth.get("mechanic_id") or "") != MECHANIC_ID:
        return {"graded": True, "passed": False, "feedback": "mechanic mismatch"}
    if not challenge_id or str(payload.get("challenge_id") or "") != challenge_id or str(public_state.get("challenge_id") or "") != challenge_id:
        return {"graded": True, "passed": False, "feedback": "stale challenge"}
    contract = dict(ground_truth.get("press") or {})
    condition = ground_truth.get("control_condition")
    if condition is not None:
        if public_state.get("control_condition") != condition:
            return {"graded": True, "passed": False, "feedback": "public registration condition differs from the replay contract"}
        if str(payload.get("task_id") or "") != str(ground_truth.get("task_id") or ""):
            return {"graded": True, "passed": False, "feedback": "stale controlled registration task"}
        parameters = dict(condition.get("difficulty_parameters") or {}) if isinstance(condition, dict) else {}
        try:
            interaction = str(condition["interaction"])
            expected_source = {"simplified": "proxy_step", "full": "wheel_drag"}[interaction]
            expected_plate_count = int(parameters["plate_count"])
            expected_token_length = int(parameters["token_length"])
            expected_harmonics = {int(value) for value in parameters["harmonic_values"]}
            expected_warp_min = float(parameters["warp_min"])
            expected_warp_max = float(parameters["warp_max"])
            expected_tolerance = float(parameters["tolerance"])
            expected_degrees_per_pixel = float(parameters["degrees_per_pixel"])
            expected_minimum_delta = float(parameters["min_initial_delta_degrees"])
            maximum_events = int(parameters["max_event_count"])
            proxy_step = float(parameters["proxy_step_degrees"])
            proxy_coarse_step = float(parameters.get("proxy_coarse_step_degrees") or 0.0)
        except (KeyError, TypeError, ValueError):
            return {"graded": True, "passed": False, "feedback": "registration control condition is malformed"}
        if (
            int(condition.get("difficulty") or 0) not in range(1, 6)
            or expected_source not in {"proxy_step", "wheel_drag"}
            or not 1 <= expected_plate_count <= 5
            or expected_token_length != len(str(contract.get("token") or ""))
            or not 4 <= maximum_events <= 250
            or not 1.0 <= proxy_step <= 15.0
            or not 0.0 <= proxy_coarse_step <= 20.0
            or proxy_coarse_step not in {0.0, proxy_step} and proxy_coarse_step <= proxy_step
            or float(contract.get("tolerance") or 0.0) != expected_tolerance
            or float(contract.get("degrees_per_pixel") or 0.0) != expected_degrees_per_pixel
        ):
            return {"graded": True, "passed": False, "feedback": "registration profile differs from the replay contract"}
    else:
        expected_source = None
        maximum_events = 100
        proxy_step = 0.0
        proxy_coarse_step = 0.0
    plates = {str(item["id"]): dict(item) for item in contract.get("plates") or []}
    if condition is not None and (
        len(plates) != expected_plate_count
        or any(
            int(plate.get("harmonic") or 0) not in expected_harmonics
            or not expected_warp_min <= float(plate.get("warp") or 0.0) <= expected_warp_max
            or _delta(float(plate.get("initial") or 0.0), float(plate.get("target") or 0.0)) < expected_minimum_delta
            for plate in plates.values()
        )
    ):
        return {"graded": True, "passed": False, "feedback": "registration plate geometry differs from the selected profile"}
    angles = {plate_id: float(plate["initial"]) for plate_id, plate in plates.items()}
    locked: set[str] = set()
    pressed = False
    events = payload.get("events")
    minimum_events = len(plates) + 1 if condition is not None else 4
    if not isinstance(events, list) or not minimum_events <= len(events) <= maximum_events:
        return {"graded": True, "passed": False, "feedback": "registration transcript is missing or outside limits"}
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return {"graded": True, "passed": False, "feedback": f"event {sequence} sequence mismatch"}
        kind, plate_id = str(event.get("kind") or ""), str(event.get("plate_id") or "")
        if kind == "wheel_drag":
            try:
                drag = float(event.get("delta"))
            except (TypeError, ValueError):
                return {"graded": True, "passed": False, "feedback": "plate drag is invalid"}
            if plate_id not in plates or plate_id in locked or not math.isfinite(drag) or abs(drag) > float(contract["max_drag_delta"]):
                return {"graded": True, "passed": False, "feedback": "plate moved outside the optical wheel contract"}
            if expected_source is not None and event.get("input_source") != expected_source:
                return {"graded": True, "passed": False, "feedback": "plate rotation uses the wrong interaction input"}
            if expected_source == "proxy_step" and not any(
                math.isclose(abs(drag), visible_step, abs_tol=0.001)
                for visible_step in (proxy_step, proxy_coarse_step)
                if visible_step > 0.0
            ):
                return {"graded": True, "passed": False, "feedback": "proxy rotation does not match one visible step control"}
            angles[plate_id] = _wrap(angles[plate_id] + drag)
            continue
        if kind == "lock":
            if plate_id not in plates or pressed or event.get("locked") is not True:
                return {"graded": True, "passed": False, "feedback": "plate lock is invalid"}
            locked.add(plate_id)
            continue
        if kind == "press":
            if pressed or locked != set(plates):
                return {"graded": True, "passed": False, "feedback": "press descended before all physical locks engaged"}
            pressed = True
            continue
        return {"graded": True, "passed": False, "feedback": f"unknown registration event {kind}"}
    errors = {plate_id: _delta(angles[plate_id], float(plate["target"])) for plate_id, plate in plates.items()}
    passed = pressed and all(error <= float(contract["tolerance"]) for error in errors.values())
    return {"graded": True, "passed": passed, "feedback": "plate registration " + ", ".join(f"{plate_id}={error:.2f}°" for plate_id, error in errors.items())}
