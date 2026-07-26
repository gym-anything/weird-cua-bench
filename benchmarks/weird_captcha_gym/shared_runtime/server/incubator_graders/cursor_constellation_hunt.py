from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "cursor_constellation_hunt"
INPUT_SOURCES = {
    "simplified": "coordinate_controls",
    "full": "canvas_pointer",
}


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if any(str(item.get("mechanic_id") or "") != MECHANIC_ID for item in (payload, ground_truth, public_state)):
        return _fail("mechanic mismatch")
    if str(payload.get("challenge_id") or "") != str(ground_truth.get("challenge_id") or ""):
        return _fail("stale constellation challenge")
    condition = ground_truth.get("control_condition")
    if condition is not None:
        if public_state.get("control_condition") != condition:
            return _fail("public interaction condition differs from constellation contract")
        if str(payload.get("task_id") or "") != str(ground_truth.get("task_id") or ""):
            return _fail("task identity mismatch")
        interaction = str(condition.get("interaction") or "")
        expected_source = INPUT_SOURCES.get(interaction)
        if expected_source is None:
            return _fail("constellation interaction condition is invalid")
        if payload.get("input_source") != expected_source:
            return _fail("constellation submission uses the wrong interaction input")

    expected = ground_truth.get("expected_click") or {}
    click = payload.get("click") or {}
    try:
        distance = math.hypot(
            float(click.get("x")) - float(expected.get("x")),
            float(click.get("y")) - float(expected.get("y")),
        )
        radius = float(expected.get("radius"))
    except (TypeError, ValueError):
        distance = math.inf
        radius = 0.0
    passed = distance <= radius
    score = 0 if not math.isfinite(distance) else max(0, int(round(100 * (1 - distance / max(radius * 4, 1)))))
    return {
        "graded": True,
        "passed": passed,
        "score": 100 if passed else score,
        "feedback": f"click distance {distance:.2f}px",
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {"target": ground_truth.get("expected_click") or {}, "shape": ground_truth.get("shape")}
