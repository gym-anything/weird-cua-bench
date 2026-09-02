from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "unlabeled_drawer"
RULE_ARITY = {"literal": 1, "and2": 2, "xor2": 2, "majority3": 3, "paired4": 4}


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _evaluate(features: list[bool], rule: dict[str, Any]) -> bool:
    values = [bool(features[index]) ^ bool(invert) for index, invert in zip(rule["indices"], rule["invert"])]
    family = rule["family"]
    if family == "literal":
        return values[0]
    if family == "and2":
        return values[0] and values[1]
    if family == "xor2":
        return values[0] != values[1]
    if family == "majority3":
        return sum(values) >= 2
    if family == "paired4":
        return values[0] == values[1] and values[2] != values[3]
    raise ValueError("unknown rule family")


def _identity(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> str | None:
    if any(str(item.get("mechanic_id") or "") != MECHANIC_ID for item in (payload, truth, public)):
        return "mechanic mismatch"
    for key in ("task_id", "challenge_id"):
        expected = str(truth.get(key) or "")
        if not expected or str(payload.get(key) or "") != expected or str(public.get(key) or "") != expected:
            return f"stale or mismatched {key}"
    return None


def _specimen_map(value: Any, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{label} is not a list")
    result: dict[str, dict[str, Any]] = {}
    for specimen in value:
        if not isinstance(specimen, dict):
            raise ValueError(f"{label} contains a malformed specimen")
        specimen_id = str(specimen.get("id") or "")
        features = specimen.get("features")
        if (
            not specimen_id
            or specimen_id in result
            or not isinstance(features, list)
            or len(features) != 6
            or any(not isinstance(item, bool) for item in features)
            or not isinstance(specimen.get("style"), dict)
        ):
            raise ValueError(f"{label} contains invalid specimen geometry")
        result[specimen_id] = specimen
    return result


def _inside(point: list[float], region: list[float], tolerance: float = 0.0) -> bool:
    x1, y1, x2, y2 = [float(value) for value in region]
    return x1 - tolerance <= float(point[0]) <= x2 + tolerance and y1 - tolerance <= float(point[1]) <= y2 + tolerance


def _gesture(
    event: dict[str, Any],
    destination_region: list[float],
    source_region: list[float],
    start_zone: str,
) -> None:
    gesture = event.get("gesture")
    if not isinstance(gesture, dict):
        raise ValueError("direct filing event lacks drag proof")
    start, end = gesture.get("start"), gesture.get("end")
    travel, samples = gesture.get("travel_px"), gesture.get("sample_count")
    if (
        not isinstance(start, list)
        or not isinstance(end, list)
        or len(start) != 2
        or len(end) != 2
        or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in start + end)
        or isinstance(travel, bool)
        or not isinstance(travel, (int, float))
        or not math.isfinite(float(travel))
        or isinstance(samples, bool)
        or not isinstance(samples, int)
    ):
        raise ValueError("direct filing drag proof is malformed")
    if event.get("start_zone") != start_zone:
        raise ValueError("direct filing drag starts from the wrong visible zone")
    if not _inside(start, source_region, 0.01):
        raise ValueError("direct filing start coordinate misses the visible source rack")
    if float(travel) < 12 or samples < 2 or math.hypot(float(end[0]) - float(start[0]), float(end[1]) - float(start[1])) < 0.04:
        raise ValueError("stationary click is not a direct filing drag")
    if not _inside(end, destination_region, 0.025):
        raise ValueError("direct filing endpoint misses the visible drawer")


def _contract(truth: dict[str, Any], public: dict[str, Any]) -> tuple[dict, dict, dict, dict, str]:
    parameters = truth.get("parameters")
    if not isinstance(parameters, dict) or public.get("parameters") != parameters:
        raise ValueError("difficulty parameters disagree")
    condition = truth.get("control_condition")
    if public.get("control_condition") != condition:
        raise ValueError("control condition disagrees")
    if condition is not None and condition.get("difficulty_parameters") != parameters:
        raise ValueError("condition parameters disagree")
    interaction = str((condition or {}).get("interaction") or "full")
    if interaction not in {"simplified", "full"}:
        raise ValueError("interaction mode is invalid")
    rule = truth.get("rule")
    if not isinstance(rule, dict) or rule.get("family") not in RULE_ARITY:
        raise ValueError("hidden rule is malformed")
    if rule.get("family") != parameters.get("rule_family"):
        raise ValueError("hidden rule family disagrees with difficulty parameters")
    arity = RULE_ARITY[str(rule["family"])]
    indices, invert = rule.get("indices"), rule.get("invert")
    if (
        not isinstance(indices, list)
        or len(indices) != arity
        or len(set(indices)) != arity
        or any(isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < 6 for index in indices)
        or not isinstance(invert, list)
        or len(invert) != arity
        or any(not isinstance(item, bool) for item in invert)
    ):
        raise ValueError("hidden rule terms are malformed")
    feature_pool = parameters.get("feature_pool")
    if isinstance(feature_pool, bool) or not isinstance(feature_pool, int) or not 1 <= feature_pool <= 6:
        raise ValueError("feature pool is malformed")
    if any(index >= feature_pool for index in indices):
        raise ValueError("hidden rule escapes the configured feature pool")
    probes = _specimen_map(truth.get("probe_specimens"), "probe bank")
    finals = _specimen_map(truth.get("final_specimens"), "final tray")
    if public.get("probe_specimens") != truth.get("probe_specimens") or public.get("final_specimens") != truth.get("final_specimens"):
        raise ValueError("public specimen geometry disagrees with hidden state")
    probe_budget = parameters.get("probe_count")
    probe_bank_count = parameters.get("probe_bank_count")
    if (
        isinstance(probe_budget, bool)
        or not isinstance(probe_budget, int)
        or isinstance(probe_bank_count, bool)
        or not isinstance(probe_bank_count, int)
        or probe_bank_count != len(probes)
        or not 1 <= probe_budget <= probe_bank_count
        or parameters.get("final_count") != len(finals)
    ):
        raise ValueError("configured specimen counts disagree")
    probe_outcomes = truth.get("probe_outcomes")
    final_outcomes = truth.get("final_outcomes")
    if not isinstance(probe_outcomes, dict) or set(probe_outcomes) != set(probes):
        raise ValueError("probe oracle is malformed")
    if not isinstance(final_outcomes, dict) or set(final_outcomes) != set(finals):
        raise ValueError("final answer map is malformed")
    expected_probes = {item_id: _evaluate(item["features"], rule) for item_id, item in probes.items()}
    expected_finals = {item_id: _evaluate(item["features"], rule) for item_id, item in finals.items()}
    if probe_outcomes != expected_probes or final_outcomes != expected_finals:
        raise ValueError("hidden outcomes disagree with the generated visual rule")
    if public.get("runtime_probe_outcomes") != expected_probes:
        raise ValueError("browser oracle commitment disagrees with hidden rule")
    regions = public.get("drop_regions")
    if (
        not isinstance(regions, dict)
        or set(regions) != {"probe", "accept", "reject"}
        or any(
            not isinstance(value, list)
            or len(value) != 4
            or any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)) for item in value)
            or not 0 <= float(value[0]) < float(value[2]) <= 1
            or not 0 <= float(value[1]) < float(value[3]) <= 1
            for value in regions.values()
        )
    ):
        raise ValueError("drawer drop regions are malformed")
    source_regions = public.get("source_regions")
    if (
        not isinstance(source_regions, dict)
        or set(source_regions) != {"probe-rack", "final-rack"}
        or any(
            not isinstance(value, list)
            or len(value) != 4
            or any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)) for item in value)
            or not 0 <= float(value[0]) < float(value[2]) <= 1
            or not 0 <= float(value[1]) < float(value[3]) <= 1
            for value in source_regions.values()
        )
    ):
        raise ValueError("drawer source regions are malformed")
    return probes, finals, expected_probes, expected_finals, interaction


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    identity_error = _identity(payload, truth, public)
    if identity_error:
        return _fail(identity_error)
    try:
        probes, finals, probe_outcomes, final_outcomes, interaction = _contract(truth, public)
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"invalid drawer contract: {exc}")
    if payload.get("interaction_mode") != interaction:
        return _fail("submitted interaction mode differs from task condition")
    events = payload.get("events")
    if not isinstance(events, list) or len(events) > 200:
        return _fail("drawer transcript is missing or oversized")
    tested: set[str] = set()
    assignments: dict[str, str] = {}
    opened_final = False
    final_order = list(finals)
    sources = {
        "full": {"probe": "specimen_drag", "assign": "specimen_drag"},
        "simplified": {"probe": "selected_test_button", "assign": "selected_drawer_button"},
    }[interaction]
    regions = public["drop_regions"]
    try:
        for sequence, event in enumerate(events, 1):
            if not isinstance(event, dict) or event.get("sequence") != sequence:
                raise ValueError(f"event {sequence} has an invalid sequence")
            event_type = event.get("type")
            if event_type == "probe":
                specimen_id = str(event.get("specimen_id") or "")
                if opened_final or specimen_id not in probes or specimen_id in tested or len(tested) >= int(truth["parameters"]["probe_count"]):
                    raise ValueError(f"event {sequence} tests an unavailable specimen")
                if event.get("input_source") != sources["probe"]:
                    raise ValueError(f"event {sequence} uses the wrong probe input surface")
                if event.get("outcome") is not probe_outcomes[specimen_id]:
                    raise ValueError(f"event {sequence} forges drawer feedback")
                if interaction == "full":
                    _gesture(event, regions["probe"], public["source_regions"]["probe-rack"], "probe-rack")
                tested.add(specimen_id)
            elif event_type == "open_final":
                if opened_final or len(tested) != int(truth["parameters"]["probe_count"]) or event.get("input_source") != "seal_latch":
                    raise ValueError(f"event {sequence} opens the sealed tray too early")
                opened_final = True
            elif event_type == "assign":
                specimen_id = str(event.get("specimen_id") or "")
                drawer = str(event.get("drawer") or "")
                before = event.get("before")
                expected_specimen = final_order[len(assignments)] if len(assignments) < len(final_order) else None
                if (
                    not opened_final
                    or specimen_id != expected_specimen
                    or specimen_id not in finals
                    or drawer not in {"accept", "reject"}
                ):
                    raise ValueError(f"event {sequence} files an unavailable specimen")
                if before is not None or specimen_id in assignments:
                    raise ValueError(f"event {sequence} starts from stale filing state")
                if event.get("input_source") != sources["assign"]:
                    raise ValueError(f"event {sequence} uses the wrong final input surface")
                if interaction == "full":
                    _gesture(event, regions[drawer], public["source_regions"]["final-rack"], "final-rack")
                assignments[specimen_id] = drawer
            else:
                raise ValueError(f"event {sequence} has unknown type {event_type!r}")
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"drawer replay rejected: {exc}")

    if payload.get("tested_probe_ids") != [item["specimen_id"] for item in events if isinstance(item, dict) and item.get("type") == "probe"]:
        return _fail("submitted probe order does not match replay")
    if payload.get("final_assignments") != assignments:
        return _fail("submitted final drawers do not match replay")
    correct = sum(
        assignments.get(specimen_id) == ("accept" if accepted else "reject")
        for specimen_id, accepted in final_outcomes.items()
    )
    passed = (
        payload.get("completed") is True
        and opened_final
        and len(tested) == int(truth["parameters"]["probe_count"])
        and len(assignments) == len(finals)
        and correct == len(finals)
    )
    return {
        "graded": True,
        "passed": passed,
        "score": 100 if passed else 0,
        "feedback": f"replayed {len(tested)} calibration tests and {len(assignments)} final filings; final drawer agreement {correct}/{len(finals)}",
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {
        "rule": ground_truth.get("rule"),
        "probe_outcomes": ground_truth.get("probe_outcomes"),
        "final_outcomes": ground_truth.get("final_outcomes"),
    }
