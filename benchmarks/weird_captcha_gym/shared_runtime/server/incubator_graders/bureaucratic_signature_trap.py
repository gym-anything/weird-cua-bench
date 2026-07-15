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
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if str(payload.get("mechanic_id") or "") != MECHANIC_ID or str(ground_truth.get("mechanic_id") or "") != MECHANIC_ID:
        return {"graded": True, "passed": False, "feedback": "mechanic mismatch"}
    if not challenge_id or str(payload.get("challenge_id") or "") != challenge_id or str(public_state.get("challenge_id") or "") != challenge_id:
        return {"graded": True, "passed": False, "feedback": "stale challenge"}
    contract = dict(ground_truth.get("form") or {})
    if public_state.get("form") != contract:
        return {"graded": True, "passed": False, "feedback": "public/private carbon contract mismatch"}
    layers = {str(layer["id"]): dict(layer) for layer in contract.get("layers") or []}
    offsets = {layer_id: _point(layer["initial"]) for layer_id, layer in layers.items()}
    stroke: list[tuple[float, float]] | None = None
    certified = False
    events = payload.get("events")
    if not isinstance(events, list) or not 6 <= len(events) <= 160:
        return {"graded": True, "passed": False, "feedback": "carbon transcript is missing or outside limits"}
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return {"graded": True, "passed": False, "feedback": f"event {sequence} sequence mismatch"}
        kind = str(event.get("kind") or "")
        if kind == "sheet_drag":
            sheet_id = str(event.get("sheet_id") or "")
            if sheet_id not in layers or certified or stroke is not None:
                return {"graded": True, "passed": False, "feedback": "unknown or late sheet drag"}
            try:
                start = _point(event.get("start"))
                samples = [_point(point) for point in event.get("samples") or []]
                end = _point(event.get("end"))
            except ValueError as exc:
                return {"graded": True, "passed": False, "feedback": str(exc)}
            if math.hypot(start[0] - offsets[sheet_id][0], start[1] - offsets[sheet_id][1]) > 1.5 or not samples or end != samples[-1]:
                return {"graded": True, "passed": False, "feedback": "sheet drag does not continue from visible state"}
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
