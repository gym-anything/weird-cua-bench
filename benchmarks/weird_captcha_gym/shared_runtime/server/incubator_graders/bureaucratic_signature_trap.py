from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "bureaucratic_signature_trap"


def _point(value: Any) -> tuple[float, float]:
    if isinstance(value, dict):
        value = [value.get("x"), value.get("y")]
    if not isinstance(value, list) or len(value) != 2 or not all(isinstance(item, (int, float)) and math.isfinite(item) for item in value):
        raise ValueError("point is malformed")
    return float(value[0]), float(value[1])


def _length(points: list[tuple[float, float]]) -> float:
    return sum(math.hypot(after[0] - before[0], after[1] - before[1]) for before, after in zip(points, points[1:]))


def _resample(points: list[tuple[float, float]], count: int = 128) -> list[tuple[float, float]]:
    distances = [0.0]
    for before, after in zip(points, points[1:]):
        distances.append(distances[-1] + math.hypot(after[0] - before[0], after[1] - before[1]))
    total = distances[-1]
    if total <= 1e-6:
        return [points[0]] * count
    result: list[tuple[float, float]] = []
    segment = 0
    for index in range(count):
        target = total * index / (count - 1)
        while segment + 1 < len(distances) - 1 and distances[segment + 1] < target:
            segment += 1
        span = max(1e-9, distances[segment + 1] - distances[segment])
        amount = (target - distances[segment]) / span
        before, after = points[segment], points[segment + 1]
        result.append((before[0] + (after[0] - before[0]) * amount, before[1] + (after[1] - before[1]) * amount))
    return result


def _deviations(first: list[tuple[float, float]], second: list[tuple[float, float]]) -> list[float]:
    return [math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(first, second)]


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    task_id = str(ground_truth.get("task_id") or "")
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if any(
        str(source.get("mechanic_id") or "") != MECHANIC_ID
        for source in (payload, ground_truth, public_state)
    ):
        return {"graded": True, "passed": False, "feedback": "mechanic mismatch"}
    if (
        not task_id
        or str(payload.get("task_id") or "") != task_id
        or str(public_state.get("task_id") or "") != task_id
        or not challenge_id
        or str(payload.get("challenge_id") or "") != challenge_id
        or str(public_state.get("challenge_id") or "") != challenge_id
    ):
        return {"graded": True, "passed": False, "feedback": "stale task or challenge"}
    contract = dict(ground_truth.get("form") or {})
    if public_state.get("form") != contract:
        return {"graded": True, "passed": False, "feedback": "public/private carbon contract mismatch"}
    truth_condition = ground_truth.get("control_condition")
    if truth_condition is not None and public_state.get("control_condition") != truth_condition:
        return {"graded": True, "passed": False, "feedback": "public/private control condition mismatch"}
    interaction = str((truth_condition or {}).get("interaction") or "full")
    expected_sheet_source = ({
        "simplified": "sheet_nudge_button",
        "full": "fixed_registration_tab",
    }.get(interaction) if truth_condition is not None else None)
    if truth_condition is not None and expected_sheet_source is None:
        return {"graded": True, "passed": False, "feedback": "carbon interaction condition is invalid"}
    layers = {str(layer["id"]): dict(layer) for layer in contract.get("layers") or []}
    if not 1 <= len(layers) <= 5 or len(layers) != len(contract.get("layers") or []):
        return {"graded": True, "passed": False, "feedback": "carbon layer contract is malformed"}
    if truth_condition is not None:
        parameters = dict(truth_condition.get("difficulty_parameters") or {})
        signature_parameters = {
            "min_samples": "signature_min_samples",
            "max_step": "signature_max_step",
            "start_tolerance": "signature_start_tolerance",
            "end_tolerance": "signature_end_tolerance",
            "mean_deviation": "signature_mean_deviation",
            "p90_deviation": "signature_p90_deviation",
            "coverage_tolerance": "signature_coverage_tolerance",
            "minimum_coverage": "signature_minimum_coverage",
            "minimum_length_ratio": "signature_minimum_length_ratio",
            "maximum_length_ratio": "signature_maximum_length_ratio",
        }
        try:
            profile_matches = (
                int(truth_condition.get("difficulty")) in range(1, 6)
                and len(layers) == int(parameters["layer_count"])
                and int(contract["aperture"]["radius"]) == int(parameters["aperture_radius"])
                and float(contract["alignment_tolerance"]) == float(parameters["alignment_tolerance"])
                and len(contract["original_trace"]) == int(parameters["trace_sample_count"]) + 1
                and all(
                    float(contract["signature"][contract_key]) == float(parameters[parameter_key])
                    for contract_key, parameter_key in signature_parameters.items()
                )
                and all(
                    int(parameters["initial_x_offset_min"])
                    <= abs(int(layer["initial"]["x"]) - int(layer["target"]["x"]))
                    <= int(parameters["initial_x_offset_max"])
                    and int(parameters["initial_y_offset_min"])
                    <= abs(int(layer["initial"]["y"]) - int(layer["target"]["y"]))
                    <= int(parameters["initial_y_offset_max"])
                    for layer in layers.values()
                )
            )
        except (KeyError, TypeError, ValueError):
            profile_matches = False
        if not profile_matches:
            return {"graded": True, "passed": False, "feedback": "carbon difficulty profile differs from form contract"}
    offsets = {layer_id: _point(layer["initial"]) for layer_id, layer in layers.items()}
    stroke: list[tuple[float, float]] | None = None
    certified = False
    events = payload.get("events")
    minimum_events = len(layers) + 2
    if not isinstance(events, list) or not minimum_events <= len(events) <= 220:
        return {"graded": True, "passed": False, "feedback": "carbon transcript is missing or outside limits"}
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return {"graded": True, "passed": False, "feedback": f"event {sequence} sequence mismatch"}
        kind = str(event.get("kind") or "")
        if kind == "sheet_drag":
            sheet_id = str(event.get("sheet_id") or "")
            if sheet_id not in layers or certified or stroke is not None:
                return {"graded": True, "passed": False, "feedback": "unknown or late sheet drag"}
            if expected_sheet_source is not None and event.get("input_source") != expected_sheet_source:
                return {"graded": True, "passed": False, "feedback": "sheet drag uses the wrong interaction input"}
            try:
                start = _point(event.get("start"))
                samples = [_point(point) for point in event.get("samples") or []]
                end = _point(event.get("end"))
            except ValueError as exc:
                return {"graded": True, "passed": False, "feedback": str(exc)}
            if math.hypot(start[0] - offsets[sheet_id][0], start[1] - offsets[sheet_id][1]) > 1.5 or not samples or end != samples[-1]:
                return {"graded": True, "passed": False, "feedback": "sheet drag does not continue from visible state"}
            if truth_condition is not None and interaction == "simplified":
                delta = (end[0] - start[0], end[1] - start[1])
                normal_nudge = delta in {(-8.0, 0.0), (8.0, 0.0), (0.0, -8.0), (0.0, 8.0)}
                boundary_nudge = (
                    (delta[1] == 0 and 0 < abs(delta[0]) < 8 and abs(end[0]) == 170)
                    or (delta[0] == 0 and 0 < abs(delta[1]) < 8 and abs(end[1]) == 110)
                )
                if len(samples) != 1 or not (normal_nudge or boundary_nudge):
                    return {"graded": True, "passed": False, "feedback": "sheet nudge does not match one visible direction button"}
            previous = start
            for point in samples:
                if not -170 <= point[0] <= 170 or not -110 <= point[1] <= 110 or math.hypot(point[0] - previous[0], point[1] - previous[1]) > float(contract["max_drag_step"]):
                    return {"graded": True, "passed": False, "feedback": "sheet teleported or left the form rail"}
                previous = point
            offsets[sheet_id] = end
            continue
        if kind == "signature_clear":
            if stroke is None or certified:
                return {"graded": True, "passed": False, "feedback": "ink clear occurred without a live stroke"}
            stroke = None
            continue
        if kind == "signature":
            if stroke is not None or certified:
                return {"graded": True, "passed": False, "feedback": "multiple or late signatures are not allowed"}
            tolerance = float(contract["alignment_tolerance"])
            if any(math.hypot(offsets[layer_id][0] - float(layer["target"]["x"]), offsets[layer_id][1] - float(layer["target"]["y"])) > tolerance for layer_id, layer in layers.items()):
                return {"graded": True, "passed": False, "feedback": "signature began while the carbon aperture was closed"}
            try:
                stroke = [_point(point) for point in event.get("points") or []]
            except ValueError as exc:
                return {"graded": True, "passed": False, "feedback": str(exc)}
            continue
        if kind == "certify":
            if stroke is None or certified:
                return {"graded": True, "passed": False, "feedback": "form was certified without one physical stroke"}
            certified = True
            continue
        return {"graded": True, "passed": False, "feedback": f"unknown carbon event {kind}"}
    if stroke is None:
        return {"graded": True, "passed": False, "feedback": "counter-signature is missing"}

    requirements = dict(contract["signature"])
    if not int(requirements["min_samples"]) <= len(stroke) <= int(requirements["max_samples"]):
        return {"graded": True, "passed": False, "feedback": "counter-signature sampling is outside limits"}
    for first, second in zip(stroke, stroke[1:]):
        if math.hypot(second[0] - first[0], second[1] - first[1]) > float(requirements["max_step"]):
            return {"graded": True, "passed": False, "feedback": "counter-signature jumped across the paper"}
    aperture = dict(contract["aperture"])
    center = (float(aperture["x"]), float(aperture["y"]))
    radius = float(aperture["radius"])
    if any(math.hypot(point[0] - center[0], point[1] - center[1]) > radius * 0.98 for point in stroke):
        return {"graded": True, "passed": False, "feedback": "counter-signature left the exposed aperture"}

    original = [_point(point) for point in contract.get("original_trace") or []]
    if len(original) < 20:
        return {"graded": True, "passed": False, "feedback": "hidden original is malformed"}
    if math.hypot(stroke[0][0] - original[0][0], stroke[0][1] - original[0][1]) > float(requirements["start_tolerance"]):
        return {"graded": True, "passed": False, "feedback": "trace did not begin at the original seal dot"}
    if math.hypot(stroke[-1][0] - original[-1][0], stroke[-1][1] - original[-1][1]) > float(requirements["end_tolerance"]):
        return {"graded": True, "passed": False, "feedback": "trace did not return to the original seal dot"}

    sampled_original = _resample(original)
    sampled_stroke = _resample(stroke)
    forward = _deviations(sampled_stroke, sampled_original)
    reverse = _deviations(sampled_stroke, list(reversed(sampled_original)))
    deviations = min((forward, reverse), key=lambda values: sum(values))
    mean_deviation = sum(deviations) / len(deviations)
    p90_deviation = sorted(deviations)[int(len(deviations) * 0.9)]
    coverage = sum(
        min(math.hypot(target[0] - sample[0], target[1] - sample[1]) for sample in sampled_stroke) <= float(requirements["coverage_tolerance"])
        for target in sampled_original
    ) / len(sampled_original)
    length_ratio = _length(stroke) / max(1e-9, _length(original))
    passed = bool(
        certified
        and mean_deviation <= float(requirements["mean_deviation"])
        and p90_deviation <= float(requirements["p90_deviation"])
        and coverage >= float(requirements["minimum_coverage"])
        and float(requirements["minimum_length_ratio"]) <= length_ratio <= float(requirements["maximum_length_ratio"])
    )
    return {
        "graded": True,
        "passed": passed,
        "feedback": f"registered {len(layers)}/{len(layers)}; trace mean {mean_deviation:.1f}px; p90 {p90_deviation:.1f}px; coverage {coverage * 100:.0f}%; length {length_ratio:.2f}×",
    }
