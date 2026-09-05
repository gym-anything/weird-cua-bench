from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "two_lamp_dyeworks"
BASE_REFLECTANCE = (0.88, 0.90, 0.92, 0.94, 0.95, 0.95, 0.94, 0.92, 0.90)
ABSORPTION_STRENGTH = 0.18
CIE_1931 = {
    "x": (0.134, 0.336, 0.095, 0.004, 0.594, 1.056, 0.642, 0.165, 0.011),
    "y": (0.004, 0.038, 0.208, 0.793, 0.995, 0.631, 0.265, 0.061, 0.004),
    "z": (0.646, 1.772, 1.287, 0.272, 0.004, 0.001, 0.000, 0.000, 0.000),
}
ILLUMINANTS = {
    "daylight": (0.76, 0.90, 1.04, 1.08, 1.05, 1.00, 0.94, 0.89, 0.84),
    "sodium": (0.05, 0.07, 0.11, 0.25, 0.92, 1.40, 0.78, 0.18, 0.05),
}
PIGMENTS = {
    "woad": (0.08, 0.05, 0.04, 0.12, 0.28, 0.55, 0.82, 0.92, 1.00),
    "madder": (0.78, 0.90, 0.88, 0.65, 0.38, 0.16, 0.08, 0.07, 0.08),
    "weld": (1.00, 0.90, 0.70, 0.25, 0.08, 0.04, 0.03, 0.03, 0.04),
    "logwood": (0.30, 0.18, 0.10, 0.46, 0.86, 0.84, 0.48, 0.25, 0.18),
}


def _fail(feedback: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": feedback}


def _bind(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> str | None:
    if payload.get("mechanic_id") != MECHANIC_ID or truth.get("mechanic_id") != MECHANIC_ID or public.get("mechanic_id") != MECHANIC_ID:
        return "mechanic mismatch"
    challenge_id = str(truth.get("challenge_id") or "")
    if not challenge_id or payload.get("challenge_id") != challenge_id or public.get("challenge_id") != challenge_id:
        return "stale challenge"
    task_id = str(truth.get("task_id") or "")
    if not task_id or payload.get("task_id") != task_id or public.get("task_id") != task_id:
        return "task mismatch"
    if truth.get("control_condition") != public.get("control_condition"):
        return "public control condition differs from hidden contract"
    return None


def _reflectance(recipe: dict[str, int], pigment_ids: list[str]) -> tuple[float, ...]:
    return tuple(
        max(
            0.025,
            BASE_REFLECTANCE[band]
            * math.exp(
                -ABSORPTION_STRENGTH
                * sum(recipe[pigment_id] * PIGMENTS[pigment_id][band] for pigment_id in pigment_ids)
            ),
        )
        for band in range(len(BASE_REFLECTANCE))
    )


def _xyz(reflectance: tuple[float, ...], illuminant: str) -> tuple[float, float, float]:
    spectrum = ILLUMINANTS[illuminant]
    normalizer = 1.0 / sum(spectrum[index] * CIE_1931["y"][index] for index in range(len(spectrum)))
    return tuple(
        normalizer
        * sum(
            spectrum[index] * reflectance[index] * CIE_1931[channel][index]
            for index in range(len(spectrum))
        )
        for channel in ("x", "y", "z")
    )


def _lab(reflectance: tuple[float, ...], illuminant: str) -> tuple[float, float, float]:
    xyz = _xyz(reflectance, illuminant)
    white = _xyz((1.0,) * len(BASE_REFLECTANCE), illuminant)

    def transform(value: float) -> float:
        boundary = 216.0 / 24389.0
        return value ** (1.0 / 3.0) if value > boundary else ((24389.0 / 27.0) * value + 16.0) / 116.0

    fx, fy, fz = (transform(xyz[index] / white[index]) for index in range(3))
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def _delta_e(left: tuple[float, ...] | list[float], right: tuple[float, ...] | list[float]) -> float:
    return math.sqrt(sum((float(left[index]) - float(right[index])) ** 2 for index in range(3)))


def _integer(value: Any, *, minimum: int, maximum: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} is outside limits")
    return value


def _composition(value: Any, pigment_ids: list[str], maximum: int) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != set(pigment_ids):
        raise ValueError("composition keys do not match the pigment rack")
    return {
        pigment_id: _integer(value[pigment_id], minimum=0, maximum=maximum, label=f"{pigment_id} amount")
        for pigment_id in pigment_ids
    }


def _recipe_spec_error(composition: dict[str, int], parameters: dict[str, Any]) -> str | None:
    component_count = sum(units > 0 for units in composition.values())
    total_units = sum(composition.values())
    minimum_components = int(parameters["target_components_min"])
    maximum_components = int(parameters["target_components_max"])
    minimum_total = int(parameters["target_total_min"])
    maximum_total = int(parameters["target_total_max"])
    if not minimum_components <= component_count <= maximum_components:
        return (
            f"lot specification requires {minimum_components}–{maximum_components} active dye families; "
            f"the mixture uses {component_count}"
        )
    if not minimum_total <= total_units <= maximum_total:
        return (
            f"lot specification requires {minimum_total}–{maximum_total} total units; "
            f"the mixture contains {total_units}"
        )
    return None


def _close_numbers(left: Any, right: Any, tolerance: float = 1e-6) -> bool:
    if not isinstance(left, list) or not isinstance(right, (list, tuple)) or len(left) != len(right):
        return False
    try:
        return all(math.isfinite(float(left[index])) and abs(float(left[index]) - float(right[index])) <= tolerance for index in range(len(right)))
    except (TypeError, ValueError):
        return False


def _contract(truth: dict[str, Any], public: dict[str, Any]) -> tuple[list[str], dict[str, Any], dict[str, tuple[float, float, float]]]:
    pigment_ids = truth.get("pigment_ids")
    if not isinstance(pigment_ids, list) or not 2 <= len(pigment_ids) <= 4 or len(set(pigment_ids)) != len(pigment_ids):
        raise ValueError("hidden pigment rack is malformed")
    if any(pigment_id not in PIGMENTS for pigment_id in pigment_ids):
        raise ValueError("hidden pigment is unknown")
    public_pigments = public.get("pigments")
    if not isinstance(public_pigments, list) or [item.get("id") for item in public_pigments if isinstance(item, dict)] != pigment_ids:
        raise ValueError("public pigment rack differs from hidden contract")
    for item in public_pigments:
        pigment_id = item["id"]
        if not _close_numbers(item.get("absorption"), PIGMENTS[pigment_id], 1e-12):
            raise ValueError(f"public {pigment_id} spectrum differs from the grading contract")
    parameters = truth.get("parameters")
    if not isinstance(parameters, dict) or parameters != public.get("parameters"):
        raise ValueError("difficulty parameters differ across public and hidden state")
    maximum = _integer(parameters.get("maximum_units_per_pigment"), minimum=1, maximum=6, label="maximum dose")
    minimum_components = _integer(parameters.get("target_components_min"), minimum=1, maximum=len(pigment_ids), label="minimum active dyes")
    maximum_components = _integer(parameters.get("target_components_max"), minimum=minimum_components, maximum=len(pigment_ids), label="maximum active dyes")
    minimum_total = _integer(parameters.get("target_total_min"), minimum=1, maximum=30, label="minimum total units")
    _integer(parameters.get("target_total_max"), minimum=minimum_total, maximum=30, label="maximum total units")
    target_recipe = _composition(truth.get("target_recipe"), pigment_ids, maximum)
    target_reflectance = _reflectance(target_recipe, pigment_ids)
    target_labs = {illuminant: _lab(target_reflectance, illuminant) for illuminant in ILLUMINANTS}
    public_target = public.get("target") or {}
    hidden_labs = truth.get("target_lab") or {}
    for illuminant in ILLUMINANTS:
        if not _close_numbers(hidden_labs.get(illuminant), target_labs[illuminant], 2e-6):
            raise ValueError(f"hidden {illuminant} target is inconsistent")
        if not _close_numbers(public_target.get("lab", {}).get(illuminant), target_labs[illuminant], 2e-6):
            raise ValueError(f"public {illuminant} target is inconsistent")
    return pigment_ids, parameters, target_labs


def _gesture(event: dict[str, Any], kind: str, units: int | None = None, maximum_units: int | None = None) -> str | None:
    gesture = event.get("gesture")
    if not isinstance(gesture, dict):
        return f"{kind} gesture is missing"
    try:
        sample_count = int(gesture.get("sample_count"))
        travel = float(gesture.get("travel_px"))
    except (TypeError, ValueError):
        return f"{kind} gesture metrics are malformed"
    if not math.isfinite(travel):
        return f"{kind} gesture travel is not finite"
    if kind == "plunger":
        if sample_count < 2 or travel < 18.0 or units is None or maximum_units is None:
            return "plunger drag is too short or sparsely sampled"
        try:
            start_ratio = float(gesture.get("start_ratio"))
            end_ratio = float(gesture.get("end_ratio"))
        except (TypeError, ValueError):
            return "plunger ratios are malformed"
        expected = units / maximum_units
        if abs(start_ratio) > 0.08 or abs(end_ratio - expected) > 0.12:
            return "plunger endpoint does not agree with the injected dose"
    elif kind == "stir":
        try:
            sweep = float(gesture.get("angular_sweep_rad"))
        except (TypeError, ValueError):
            return "stir sweep is malformed"
        if sample_count < 8 or travel < 180.0 or not math.isfinite(sweep) or sweep < 5.0:
            return "stirring did not complete one sampled turn"
    elif kind == "strip":
        if sample_count < 2 or travel < 70.0:
            return "test-strip drag did not reach the vat"
        if gesture.get("target_region") != "vat_opening_inner_ellipse_v1":
            return "test-strip drop does not identify the visible vat opening"
        geometry_names = (
            "start_x", "start_y", "end_x", "end_y",
            "opening_left", "opening_top", "opening_width", "opening_height",
            "opening_inset_px", "endpoint_normalized_x",
            "endpoint_normalized_y", "endpoint_ellipse_value",
        )
        try:
            geometry = {name: float(gesture.get(name)) for name in geometry_names}
        except (TypeError, ValueError):
            return "test-strip drop geometry is malformed"
        if not all(math.isfinite(value) for value in geometry.values()):
            return "test-strip drop geometry is not finite"
        width = geometry["opening_width"]
        height = geometry["opening_height"]
        inset = geometry["opening_inset_px"]
        # These bounds cover the fixed benchmark layout at its supported
        # 1280x720 and 1920x1080 captures, including the compact-height rule.
        if not (220.0 <= width <= 260.0 and 95.0 <= height <= 125.0):
            return "test-strip opening geometry differs from the visible vat"
        if abs(inset - 12.0) > 1e-6:
            return "test-strip opening inset differs from the visible liquid target"
        radius_x = width / 2.0 - inset
        radius_y = height / 2.0 - inset
        if radius_x <= 0 or radius_y <= 0:
            return "test-strip opening ellipse is malformed"
        center_x = geometry["opening_left"] + width / 2.0
        center_y = geometry["opening_top"] + height / 2.0
        normalized_x = (geometry["end_x"] - center_x) / radius_x
        normalized_y = (geometry["end_y"] - center_y) / radius_y
        ellipse_value = normalized_x * normalized_x + normalized_y * normalized_y
        if (
            abs(normalized_x - geometry["endpoint_normalized_x"]) > 2e-4
            or abs(normalized_y - geometry["endpoint_normalized_y"]) > 2e-4
            or abs(ellipse_value - geometry["endpoint_ellipse_value"]) > 3e-4
        ):
            return "test-strip endpoint witness is inconsistent"
        if ellipse_value > 1.0 + 1e-6:
            return "test-strip was released outside the visible vat opening"
        start_normalized_x = (geometry["start_x"] - center_x) / radius_x
        start_normalized_y = (geometry["start_y"] - center_y) / radius_y
        if start_normalized_x * start_normalized_x + start_normalized_y * start_normalized_y <= 1.0:
            return "test-strip drag did not begin outside the vat opening"
        direct_travel = math.hypot(
            geometry["end_x"] - geometry["start_x"],
            geometry["end_y"] - geometry["start_y"],
        )
        if direct_travel > travel + 1.0:
            return "test-strip travel is shorter than its recorded endpoints"
    return None


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    binding_error = _bind(payload, ground_truth, public_state)
    if binding_error:
        return _fail(binding_error)
    try:
        pigment_ids, parameters, target_labs = _contract(ground_truth, public_state)
        maximum_units = _integer(parameters.get("maximum_units_per_pigment"), minimum=1, maximum=6, label="maximum dose")
        vat_capacity = _integer(parameters.get("vat_capacity_units"), minimum=1, maximum=30, label="vat capacity")
        fresh_vats = _integer(parameters.get("fresh_vats"), minimum=1, maximum=6, label="fresh vat count")
        tolerance = float(parameters.get("tolerance_delta_e"))
        if not math.isfinite(tolerance) or not 1.0 <= tolerance <= 12.0:
            raise ValueError("delta-E tolerance is invalid")
    except (TypeError, ValueError) as exc:
        return _fail(f"invalid dyeworks contract: {exc}")

    condition = ground_truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "full")
    if interaction not in {"simplified", "full"}:
        return _fail("interaction condition is invalid")
    expected_sources = {
        "simplified": {"dose": "dose_buttons", "stir": "stir_button", "dip": "dip_button"},
        "full": {"dose": "plunger_drag", "stir": "stir_gesture", "dip": "strip_drag"},
    }[interaction]
    events = payload.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 120:
        return _fail("dyeworks transcript is missing or outside limits")

    composition = {pigment_id: 0 for pigment_id in pigment_ids}
    vat = 1
    lamp = "daylight"
    stirred = False
    sampled: dict[str, int] | None = None
    viewed: set[str] = set()
    total_dispensed = 0
    terminal = False
    certified = False
    exhausted = False

    for index, event in enumerate(events, start=1):
        if terminal:
            return _fail("transcript continues after a terminal action")
        if not isinstance(event, dict) or event.get("sequence") != index:
            return _fail(f"event {index} has an invalid sequence")
        if event.get("vat") != vat:
            return _fail(f"event {index} reports the wrong vat")
        kind = str(event.get("type") or "")
        if kind == "dose":
            if event.get("input_source") != expected_sources["dose"]:
                return _fail(f"dose {index} uses the wrong interaction surface")
            pigment_id = str(event.get("pigment") or "")
            if pigment_id not in composition:
                return _fail(f"dose {index} names an unavailable pigment")
            try:
                units = _integer(event.get("units"), minimum=1, maximum=maximum_units, label="dose")
            except ValueError as exc:
                return _fail(f"dose {index} is invalid: {exc}")
            if sum(composition.values()) + units > vat_capacity:
                return _fail(f"dose {index} exceeds visible vat headroom")
            if interaction == "full":
                gesture_error = _gesture(event, "plunger", units, maximum_units)
                if gesture_error:
                    return _fail(f"dose {index}: {gesture_error}")
            composition[pigment_id] += units
            total_dispensed += units
            stirred = False
            sampled = None
            viewed.clear()
        elif kind == "stir":
            if event.get("input_source") != expected_sources["stir"]:
                return _fail(f"stir {index} uses the wrong interaction surface")
            if sum(composition.values()) <= 0:
                return _fail(f"stir {index} operates an empty vat")
            if interaction == "full":
                gesture_error = _gesture(event, "stir")
                if gesture_error:
                    return _fail(f"stir {index}: {gesture_error}")
            stirred = True
        elif kind == "dip":
            if event.get("input_source") != expected_sources["dip"]:
                return _fail(f"dip {index} uses the wrong interaction surface")
            if not stirred or sum(composition.values()) <= 0:
                return _fail(f"dip {index} samples an unstirred or empty vat")
            if interaction == "full":
                gesture_error = _gesture(event, "strip")
                if gesture_error:
                    return _fail(f"dip {index}: {gesture_error}")
            sampled = dict(composition)
            viewed = {lamp}
        elif kind == "lamp":
            if event.get("input_source") != "lamp_switch":
                return _fail(f"lamp event {index} uses the wrong control")
            expected_lamp = "sodium" if lamp == "daylight" else "daylight"
            if event.get("illuminant") != expected_lamp:
                return _fail(f"lamp event {index} does not toggle the illuminant")
            lamp = expected_lamp
            if sampled == composition:
                viewed.add(lamp)
        elif kind == "check":
            if event.get("input_source") != "certify_button" or sampled != composition or viewed != set(ILLUMINANTS):
                return _fail(f"check {index} was made without one current strip seen under both lamps")
            sample_labs = {illuminant: _lab(_reflectance(composition, pigment_ids), illuminant) for illuminant in ILLUMINANTS}
            recipe_spec_error = _recipe_spec_error(composition, parameters)
            if recipe_spec_error is None and all(_delta_e(sample_labs[illuminant], target_labs[illuminant]) <= tolerance for illuminant in ILLUMINANTS):
                return _fail(f"check {index} reports a passing mixture as unfinished")
        elif kind == "certify":
            if event.get("input_source") != "certify_button" or sampled != composition or viewed != set(ILLUMINANTS):
                return _fail(f"certification {index} lacks a current strip viewed under both lamps")
            recipe_spec_error = _recipe_spec_error(composition, parameters)
            if recipe_spec_error:
                return _fail(f"certification {index} violates the visible {recipe_spec_error}")
            sample_labs = {illuminant: _lab(_reflectance(composition, pigment_ids), illuminant) for illuminant in ILLUMINANTS}
            if not all(_delta_e(sample_labs[illuminant], target_labs[illuminant]) <= tolerance for illuminant in ILLUMINANTS):
                return _fail(f"certification {index} does not match both illuminants")
            certified = True
            terminal = True
        elif kind == "dump":
            if event.get("input_source") != "dump_valve":
                return _fail(f"dump {index} uses the wrong control")
            sampled = None
            viewed.clear()
            stirred = False
            if vat >= fresh_vats:
                exhausted = True
                terminal = True
            else:
                vat += 1
                composition = {pigment_id: 0 for pigment_id in pigment_ids}
        else:
            return _fail(f"event {index} has unknown type {kind!r}")

    try:
        submitted_composition = _composition(payload.get("final_composition"), pigment_ids, maximum_units * 20)
    except ValueError as exc:
        return _fail(f"submitted composition is invalid: {exc}")
    if submitted_composition != composition:
        return _fail("submitted composition does not match replay")
    if payload.get("vat_index") != vat or payload.get("lamp") != lamp:
        return _fail("submitted bench state does not match replay")
    if payload.get("total_dispensed") != total_dispensed:
        return _fail("submitted pigment counter does not match replay")
    if payload.get("vats_consumed") != vat:
        return _fail("submitted vat counter does not match replay")

    final_labs = {illuminant: _lab(_reflectance(composition, pigment_ids), illuminant) for illuminant in ILLUMINANTS}
    deltas = {illuminant: _delta_e(final_labs[illuminant], target_labs[illuminant]) for illuminant in ILLUMINANTS}
    passed = payload.get("completed") is True and certified and not exhausted
    if payload.get("completed") is False and not exhausted:
        return _fail("unfinished payload does not end by exhausting the visible vats")
    return {
        "graded": True,
        "passed": passed,
        "feedback": (
            f"north-light ΔE {deltas['daylight']:.2f}; sodium ΔE {deltas['sodium']:.2f}; "
            f"tolerance {tolerance:.2f}; lot {sum(units > 0 for units in composition.values())} dyes/"
            f"{sum(composition.values())} units; vats {vat}/{fresh_vats}; dispensed {total_dispensed} units"
        ),
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {
        "instruction": "Dose the canonical pigments, stir once, dip once, inspect both lamps, then seal.",
        "canonical_plan": ground_truth.get("canonical_plan") or [],
        "answers": [],
    }
