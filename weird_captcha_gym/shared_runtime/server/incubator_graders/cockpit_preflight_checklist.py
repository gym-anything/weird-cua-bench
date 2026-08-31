from __future__ import annotations

import copy
import math
from typing import Any


MECHANIC_ID = "cockpit_preflight_checklist"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _bind(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> str | None:
    if any(str(item.get("mechanic_id") or "") != MECHANIC_ID for item in (payload, truth, public)):
        return "mechanic mismatch"
    for key in ("task_id", "challenge_id"):
        expected = str(truth.get(key) or "")
        if not expected or str(payload.get(key) or "") != expected or str(public.get(key) or "") != expected:
            return f"stale or mismatched {key}"
    return None


def _panel_state(panel: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for item in panel.get("ranges") or []:
        values[str(item["id"])] = {"kind": "range", "low": item["low"], "high": item["high"]}
    for item in panel.get("dials") or []:
        values[str(item["id"])] = {"kind": "dial", "value": item["value"]}
    for branch in panel.get("branches") or []:
        values[str(branch["id"])] = {"kind": "branch", "expanded": branch["expanded"]}
        for row in branch.get("rows") or []:
            values[str(row["id"])] = {"kind": "circuit", "state": row["state"]}
    return values


def _index(panel: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for item in panel.get("ranges") or []:
        items[str(item["id"])] = item
    for item in panel.get("dials") or []:
        items[str(item["id"])] = item
    for branch in panel.get("branches") or []:
        items[str(branch["id"])] = branch
        for row in branch.get("rows") or []:
            items[str(row["id"])] = row
    return items


def _contract(truth: dict[str, Any], public: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    panel = copy.deepcopy(truth.get("initial_panel"))
    if not isinstance(panel, dict) or public.get("panel") != panel:
        raise ValueError("public panel differs from replay contract")
    parameters = truth.get("parameters")
    if not isinstance(parameters, dict) or public.get("parameters") != parameters:
        raise ValueError("difficulty parameters differ from replay contract")
    condition = truth.get("control_condition")
    if condition != public.get("control_condition"):
        raise ValueError("public control condition differs from replay contract")
    if condition is not None and condition.get("difficulty_parameters") != parameters:
        raise ValueError("condition parameters differ from generated panel")
    interaction = str((condition or {}).get("interaction") or "full")
    if interaction not in {"simplified", "full"}:
        raise ValueError("interaction mode is invalid")
    expected_counts = {
        "range_count": len(panel.get("ranges") or []),
        "dial_count": len(panel.get("dials") or []),
        "branch_count": len(panel.get("branches") or []),
    }
    for key, value in expected_counts.items():
        if parameters.get(key) != value:
            raise ValueError(f"{key} does not match generated panel")
    couplings = panel.get("couplings")
    if not isinstance(couplings, list) or parameters.get("coupling_count") != len(couplings):
        raise ValueError("coupling_count does not match generated panel")
    seen_couplings = set()
    for coupling in couplings:
        coupling_id = str(coupling.get("id") or "")
        if not coupling_id or coupling_id in seen_couplings:
            raise ValueError("calibration coupling IDs are invalid")
        seen_couplings.add(coupling_id)
        if coupling.get("ratio") not in {-1, 1}:
            raise ValueError("calibration coupling ratio is invalid")
    return panel, parameters, interaction


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _gesture(event: dict[str, Any], spec: dict[str, Any], before: int) -> None:
    gesture = event.get("gesture")
    if not isinstance(gesture, dict):
        raise ValueError("direct analog event lacks gesture proof")
    start = gesture.get("start_fraction")
    end = gesture.get("end_fraction")
    travel = gesture.get("travel_px")
    samples = gesture.get("sample_count")
    values = (start, end, travel)
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in values):
        raise ValueError("direct analog gesture has invalid geometry")
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 2:
        raise ValueError("direct analog gesture has too few movement samples")
    expected_start = (before - spec["minimum"]) / (spec["maximum"] - spec["minimum"])
    if abs(float(start) - expected_start) > .025:
        raise ValueError("direct analog gesture did not start on the active control")
    if abs(float(end) - float(event.get("pointer_fraction"))) > 1e-6:
        raise ValueError("direct analog gesture endpoint disagrees with pointer geometry")
    if float(travel) < 8 or abs(float(end) - float(start)) < .005:
        raise ValueError("stationary click is not a direct analog gesture")


def _apply_couplings(
    event: dict[str, Any],
    panel: dict[str, Any],
    specs: dict[str, dict[str, Any]],
    state: dict[str, dict[str, Any]],
    source_id: str,
    source_field: str,
    before: int,
    after: int,
) -> list[str]:
    source_spec = specs[source_id]
    source_steps = (after - before) // source_spec["step"]
    source_target_field = {"low": "target_low", "high": "target_high", "value": "target"}[source_field]
    releases_target = after == source_spec[source_target_field]
    effects = []
    revealed = []
    for coupling in panel.get("couplings") or []:
        if coupling.get("source") != {"id": source_id, "field": source_field}:
            continue
        target_id = str(coupling["target"]["id"])
        target_field = str(coupling["target"]["field"])
        target_spec = specs[target_id]
        target_state = state[target_id]
        target_before = _integer(target_state[target_field], "coupled target before")
        target_after = target_before + source_steps * target_spec["step"] * coupling["ratio"]
        target_after = max(target_spec["minimum"], min(target_spec["maximum"], target_after))
        if target_field == "low":
            target_after = min(target_after, target_state["high"] - target_spec["step"])
        elif target_field == "high":
            target_after = max(target_after, target_state["low"] + target_spec["step"])
        target_state[target_field] = target_after
        effects.append({
            "coupling_id": coupling["id"],
            "id": target_id,
            "field": target_field,
            "before": target_before,
            "after": target_after,
        })
        if releases_target:
            revealed.append(coupling["id"])
    if event.get("effects") != effects:
        raise ValueError("reported calibration-bus effects disagree with replay")
    if event.get("revealed_coupling_ids") != revealed:
        raise ValueError("reported released targets disagree with replay")
    return revealed


def _branch_available(branch: dict[str, Any], state: dict[str, dict[str, Any]], specs: dict[str, dict[str, Any]]) -> bool:
    parent_id = branch.get("parent_id")
    seen = set()
    while parent_id:
        if parent_id in seen or parent_id not in state or state[parent_id]["kind"] != "branch":
            return False
        seen.add(parent_id)
        if state[parent_id]["expanded"] is not True:
            return False
        parent_id = specs[parent_id].get("parent_id")
    return True


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    binding = _bind(payload, truth, public)
    if binding:
        return _fail(binding)
    try:
        panel, _parameters, interaction = _contract(truth, public)
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"invalid cockpit contract: {exc}")
    if payload.get("interaction_mode") != interaction:
        return _fail("submitted interaction mode differs from task condition")
    events = payload.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 500:
        return _fail("control transcript is missing or outside limits")
    state = _panel_state(panel)
    specs = _index(panel)
    row_parents = {
        str(row["id"]): branch
        for branch in panel.get("branches") or []
        for row in branch.get("rows") or []
    }
    sources = {
        "full": {"range": "range_thumb_drag", "dial": "rotary_pointer", "branch": "tree_disclosure", "circuit": "tree_cell"},
        "simplified": {"range": "range_step_button", "dial": "dial_step_button", "branch": "tree_navigator", "circuit": "tree_cycle_button"},
    }[interaction]
    released_couplings: set[str] = set()
    try:
        for sequence, event in enumerate(events, 1):
            if not isinstance(event, dict) or event.get("sequence") != sequence:
                raise ValueError(f"event {sequence} has an invalid sequence")
            item_id = str(event.get("id") or "")
            current = state.get(item_id)
            spec = specs.get(item_id)
            if current is None or spec is None:
                raise ValueError(f"event {sequence} names an unknown control")
            kind = current["kind"]
            if event.get("type") != kind or event.get("input_source") != sources[kind]:
                raise ValueError(f"event {sequence} uses the wrong input surface")
            if kind in {"range", "dial"}:
                channel_field = event.get("thumb") if kind == "range" else "value"
                incoming = next((
                    coupling for coupling in panel.get("couplings") or []
                    if coupling.get("target") == {"id": item_id, "field": channel_field}
                ), None)
                if incoming and incoming["id"] not in released_couplings:
                    raise ValueError(f"event {sequence} operates a bus-locked target")
            if kind == "range":
                thumb = event.get("thumb")
                if thumb not in {"low", "high"}:
                    raise ValueError(f"event {sequence} has an invalid range thumb")
                before = _integer(event.get("before"), "range before")
                after = _integer(event.get("after"), "range after")
                if before != current[thumb]:
                    raise ValueError(f"event {sequence} starts from stale range state")
                minimum, maximum, step = spec["minimum"], spec["maximum"], spec["step"]
                if not minimum <= after <= maximum or (after - minimum) % step:
                    raise ValueError(f"event {sequence} leaves range ticks")
                other = current["high" if thumb == "low" else "low"]
                paired = next((
                    coupling for coupling in panel.get("couplings") or []
                    if coupling.get("source") == {"id": item_id, "field": thumb}
                    and coupling.get("target", {}).get("id") == item_id
                ), None)
                predicted_other = other
                if paired:
                    predicted_other += ((after - before) // step) * step * paired["ratio"]
                    predicted_other = max(minimum, min(maximum, predicted_other))
                if (thumb == "low" and after > predicted_other - step) or (thumb == "high" and after < predicted_other + step):
                    raise ValueError(f"event {sequence} crosses range thumbs")
                if interaction == "simplified" and abs(after - before) != step:
                    raise ValueError(f"event {sequence} is not one range step")
                if interaction == "full":
                    fraction = event.get("pointer_fraction")
                    if not isinstance(fraction, (int, float)) or isinstance(fraction, bool) or not math.isfinite(float(fraction)):
                        raise ValueError(f"event {sequence} lacks pointer geometry")
                    derived = minimum + round(max(0.0, min(1.0, float(fraction))) * ((maximum - minimum) / step)) * step
                    if thumb == "low" and paired:
                        predicted_high = current["high"] + ((derived - before) // step) * step * paired["ratio"]
                        predicted_high = max(minimum, min(maximum, predicted_high))
                        constrained = min(derived, predicted_high - step)
                    else:
                        constrained = min(derived, other - step) if thumb == "low" else max(derived, other + step)
                    if constrained != after:
                        raise ValueError(f"event {sequence} disagrees with range geometry")
                    _gesture(event, spec, before)
                current[thumb] = after
                released_couplings.update(_apply_couplings(event, panel, specs, state, item_id, thumb, before, after))
            elif kind == "dial":
                before = _integer(event.get("before"), "dial before")
                after = _integer(event.get("after"), "dial after")
                if before != current["value"]:
                    raise ValueError(f"event {sequence} starts from stale dial state")
                minimum, maximum = spec["minimum"], spec["maximum"]
                if not minimum <= after <= maximum:
                    raise ValueError(f"event {sequence} leaves dial detents")
                if interaction == "simplified" and abs(after - before) != 1:
                    raise ValueError(f"event {sequence} is not one dial step")
                if interaction == "full":
                    fraction = event.get("pointer_fraction")
                    if not isinstance(fraction, (int, float)) or isinstance(fraction, bool) or not math.isfinite(float(fraction)):
                        raise ValueError(f"event {sequence} lacks rotary geometry")
                    derived = minimum + round(max(0.0, min(1.0, float(fraction))) * (maximum - minimum))
                    if derived != after:
                        raise ValueError(f"event {sequence} disagrees with rotary geometry")
                    _gesture(event, spec, before)
                current["value"] = after
                released_couplings.update(_apply_couplings(event, panel, specs, state, item_id, "value", before, after))
            elif kind == "branch":
                if not _branch_available(spec, state, specs):
                    raise ValueError(f"event {sequence} operates a branch behind a closed parent")
                if event.get("before") is not current["expanded"] or not isinstance(event.get("after"), bool) or event["after"] is current["expanded"]:
                    raise ValueError(f"event {sequence} has a stale branch transition")
                current["expanded"] = event["after"]
            else:
                if not _branch_available(row_parents[item_id], state, specs) or state[row_parents[item_id]["id"]]["expanded"] is not True:
                    raise ValueError(f"event {sequence} operates a circuit in a closed branch")
                before, after = event.get("before"), event.get("after")
                states = panel.get("tree_states") or []
                if before != current["state"] or before not in states or after != states[(states.index(before) + 1) % len(states)]:
                    raise ValueError(f"event {sequence} has an invalid circuit cycle")
                current["state"] = after
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"cockpit replay rejected: {exc}")

    final_state = payload.get("final_state")
    expected_final = {
        item_id: {key: value for key, value in item.items() if key != "kind"}
        for item_id, item in state.items()
    }
    if final_state != expected_final:
        return _fail("submitted panel does not match transcript replay")
    checks = []
    for item in panel.get("ranges") or []:
        checks.extend((state[item["id"]]["low"] == item["target_low"], state[item["id"]]["high"] == item["target_high"]))
    for item in panel.get("dials") or []:
        checks.append(state[item["id"]]["value"] == item["target"])
    for branch in panel.get("branches") or []:
        for row in branch.get("rows") or []:
            checks.append(state[row["id"]]["state"] == row["target"])
    all_couplings_released = released_couplings == {str(coupling["id"]) for coupling in panel.get("couplings") or []}
    passed = payload.get("completed") is True and all(checks) and all_couplings_released
    return {
        "graded": True,
        "passed": passed,
        "feedback": f"preflight vector {sum(checks)}/{len(checks)} exact; calibration links {len(released_couplings)}/{len(panel.get('couplings') or [])}; {len(events)} replayed control events",
    }
