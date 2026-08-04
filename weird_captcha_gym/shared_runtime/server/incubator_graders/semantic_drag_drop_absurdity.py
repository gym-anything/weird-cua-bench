from __future__ import annotations

from typing import Any


MECHANIC_ID = "semantic_drag_drop_absurdity"


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if str(payload.get("mechanic_id") or "") != MECHANIC_ID or str(ground_truth.get("mechanic_id") or "") != MECHANIC_ID:
        return {"graded": True, "passed": False, "feedback": "mechanic mismatch"}
    if not challenge_id or str(payload.get("challenge_id") or "") != challenge_id or str(public_state.get("challenge_id") or "") != challenge_id:
        return {"graded": True, "passed": False, "feedback": "stale challenge"}
    expected = {str(key): str(value) for key, value in (ground_truth.get("expected_assignments") or {}).items()}
    placements = {str(key): str(value) for key, value in (payload.get("placements") or {}).items()}
    condition = ground_truth.get("control_condition")
    if condition is not None:
        expected_interaction = str(condition.get("interaction") or "")
        expected_probe_source = {
            "simplified": "proxy_probe",
            "full": "direct_probe_drag",
        }.get(expected_interaction)
        expected_placement_source = {
            "simplified": "proxy_pair_click",
            "full": "direct_specimen_drag",
        }.get(expected_interaction)
        placement_sources = payload.get("placement_sources") or {}
        if (
            public_state.get("control_condition") != condition
            or expected_probe_source is None
            or expected_placement_source is None
            or str(payload.get("interaction_mode") or "") != expected_interaction
            or not isinstance(placement_sources, dict)
            or set(str(key) for key in placement_sources) != set(expected)
            or any(str(placement_sources.get(object_id) or "") != expected_placement_source for object_id in expected)
        ):
            return {"graded": True, "passed": False, "feedback": "causal routing transcript uses the wrong interaction mode"}
    probes = payload.get("probes")
    if not isinstance(probes, list) or len(probes) > 40:
        return {"graded": True, "passed": False, "feedback": "material probe transcript is invalid"}
    observed: set[tuple[str, str]] = set()
    for sequence, probe in enumerate(probes, start=1):
        if not isinstance(probe, dict) or probe.get("sequence") != sequence:
            return {"graded": True, "passed": False, "feedback": f"probe {sequence} sequence mismatch"}
        object_id, channel = str(probe.get("object_id") or ""), str(probe.get("probe") or "")
        if object_id not in expected or channel not in {"thermal", "polarity"} or int(probe.get("hold_ms") or 0) < int(public_state.get("probe_hold_ms") or 0):
            return {"graded": True, "passed": False, "feedback": "material probe was incomplete or unknown"}
        if condition is not None and str(probe.get("input_source") or "") != expected_probe_source:
            return {"graded": True, "passed": False, "feedback": "material probe uses the wrong interaction input"}
        observed.add((object_id, channel))
    required = {(object_id, channel) for object_id in expected for channel in ("thermal", "polarity")}
    correct = sum(1 for object_id, receiver_id in expected.items() if placements.get(object_id) == receiver_id)
    passed = placements == expected and required <= observed
    return {"graded": True, "passed": passed, "feedback": f"causal probes {len(observed & required)}/{len(required)}; routed {correct}/{len(expected)}"}
