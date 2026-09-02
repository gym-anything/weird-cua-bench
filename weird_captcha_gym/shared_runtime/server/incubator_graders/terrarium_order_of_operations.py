from __future__ import annotations

import copy
import math
from typing import Any


MECHANIC_ID = "terrarium_order_of_operations"


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


def _contract(truth: dict[str, Any], public: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]], dict[str, Any], str]:
    modules = truth.get("modules")
    solution = truth.get("solution_order")
    parameters = truth.get("parameters")
    terrarium = public.get("terrarium")
    if not isinstance(modules, list) or not isinstance(solution, list) or not isinstance(parameters, dict) or not isinstance(terrarium, dict):
        raise ValueError("causal contract is incomplete")
    module_ids = [str(item.get("id") or "") for item in modules if isinstance(item, dict)]
    if len(module_ids) != parameters.get("module_count") or len(set(module_ids)) != len(module_ids) or not all(module_ids):
        raise ValueError("module inventory is invalid")
    if sorted(solution) != sorted(module_ids):
        raise ValueError("solution is not a permutation of the module inventory")
    causal_links = [
        {"source": solution[index - 1], "target": solution[index]}
        for index in range(1, len(solution))
    ]
    if truth.get("causal_links") != causal_links:
        raise ValueError("hidden causal links disagree with solution order")
    if terrarium.get("modules") != modules or terrarium.get("tray_order") != truth.get("tray_order"):
        raise ValueError("public terrarium differs from the generated world")
    if terrarium.get("runtime_causal_links") != causal_links:
        raise ValueError("browser causal simulation differs from independent replay")
    if terrarium.get("max_stage") != 3 or truth.get("max_stage") != 3:
        raise ValueError("growth-stage contract is invalid")
    if terrarium.get("final_cascade_waves") != 2 or truth.get("final_cascade_waves") != 2:
        raise ValueError("final cascade contract is invalid")
    if public.get("parameters") != parameters:
        raise ValueError("public difficulty parameters differ from ground truth")
    condition = truth.get("control_condition")
    if condition != public.get("control_condition"):
        raise ValueError("public control condition differs from ground truth")
    if condition is not None and condition.get("difficulty_parameters") != parameters:
        raise ValueError("condition parameters differ from generated terrarium")
    interaction = str((condition or {}).get("interaction") or "full")
    if interaction not in {"simplified", "full"}:
        raise ValueError("interaction mode is invalid")
    return [str(item) for item in solution], copy.deepcopy(modules), parameters, interaction


def _gesture(event: dict[str, Any]) -> None:
    gesture = event.get("gesture")
    if not isinstance(gesture, dict):
        raise ValueError("direct inoculation lacks drag geometry")
    fields = ("start_u", "start_v", "end_u", "end_v", "travel_px")
    values = []
    for field in fields:
        value = gesture.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError("direct inoculation has invalid drag geometry")
        values.append(float(value))
    start_u, start_v, end_u, end_v, travel = values
    samples = gesture.get("sample_count")
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 1:
        raise ValueError("direct inoculation has no delivered pointer sample")
    if not (0 <= start_u <= 1 and 0 <= start_v <= 1):
        raise ValueError("direct inoculation did not start on the visible capsule")
    if not (0 <= end_u <= 1 and 0 <= end_v <= 1):
        raise ValueError("direct inoculation did not end inside the visible delivery hatch")
    if travel < 80:
        raise ValueError("stationary click is not a direct inoculation drag")


def _replay(solution: list[str], order: list[str], echo_budget: int) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    predecessor = {solution[index]: (solution[index - 1] if index else None) for index in range(len(solution))}
    state = {module_id: {"active": False, "scarred": False, "stage": 0} for module_id in solution}
    expected_results = []
    echoes_used = 0
    for sequence, module_id in enumerate(order, 1):
        required = predecessor[module_id]
        healthy_predecessor = required is None or (state[required]["active"] and not state[required]["scarred"])
        scarred = not healthy_predecessor
        state[module_id] = {"active": True, "scarred": scarred, "stage": 0}
        cascade = []
        for candidate in solution:
            current = state[candidate]
            if not current["active"] or current["scarred"]:
                continue
            before = int(current["stage"])
            after = min(2, before + 1)
            current["stage"] = after
            if before != after:
                cascade.append({"module_id": candidate, "before": before, "after": after})
        clue_shown = bool(scarred and echoes_used < echo_budget)
        echo_module_id = required if clue_shown else None
        if clue_shown:
            echoes_used += 1
        final_cascade = []
        if sequence == len(solution):
            for candidate in solution:
                current = state[candidate]
                if not current["active"] or current["scarred"]:
                    continue
                before = int(current["stage"])
                current["stage"] = 3
                if before != 3:
                    final_cascade.append({"module_id": candidate, "before": before, "after": 3})
        expected_results.append({
            "scarred": scarred,
            "clue_shown": clue_shown,
            "echo_module_id": echo_module_id,
            "cascade": cascade,
            "final_cascade": final_cascade,
        })
    return expected_results, state


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    binding = _bind(payload, truth, public)
    if binding:
        return _fail(binding)
    try:
        solution, modules, parameters, interaction = _contract(truth, public)
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"invalid terrarium contract: {exc}")
    if payload.get("interaction_mode") != interaction:
        return _fail("submitted interaction mode differs from task condition")
    events = payload.get("events")
    if not isinstance(events, list) or len(events) != len(solution):
        return _fail(f"inoculation transcript must contain exactly {len(solution)} events")
    sources = {"full": "direct_capsule_drag", "simplified": "tray_inoculate_button"}
    module_ids = {str(module["id"]) for module in modules}
    order = []
    try:
        for sequence, event in enumerate(events, 1):
            if not isinstance(event, dict) or event.get("sequence") != sequence or event.get("type") != "inoculate":
                raise ValueError(f"event {sequence} has an invalid sequence or type")
            module_id = str(event.get("module_id") or "")
            if module_id not in module_ids or module_id in order:
                raise ValueError(f"event {sequence} names an unknown or repeated capsule")
            if event.get("input_source") != sources[interaction]:
                raise ValueError(f"event {sequence} uses the wrong input surface")
            if interaction == "full":
                _gesture(event)
            elif "gesture" in event:
                raise ValueError(f"event {sequence} adds drag proof to the proxy interface")
            order.append(module_id)
    except (TypeError, ValueError) as exc:
        return _fail(f"terrarium replay rejected: {exc}")
    expected_results, expected_final = _replay(solution, order, int(parameters["echo_budget"]))
    for index, event in enumerate(events):
        if event.get("result") != expected_results[index]:
            return _fail(f"visible cascade claim disagrees with replay at inoculation {index + 1}")
    if payload.get("order") != order:
        return _fail("submitted order differs from the inoculation transcript")
    if payload.get("final_state") != expected_final:
        return _fail("submitted habitat stages differ from causal replay")
    all_max = all(item["active"] and not item["scarred"] and item["stage"] == 3 for item in expected_final.values())
    passed = payload.get("completed") is True and order == solution and all_max
    maxed = sum(1 for item in expected_final.values() if item["stage"] == 3 and not item["scarred"])
    return {
        "graded": True,
        "passed": passed,
        "feedback": f"terrarium habitats {maxed}/{len(solution)} at full bloom; {len(events)} inoculations replayed; order {'exact' if order == solution else 'nonmaximal'}",
    }
