from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "temporal_memory_first_change"


def _point(value: Any) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("point is malformed")
    if not all(isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(float(item)) for item in value):
        raise ValueError("point is malformed")
    return float(value[0]), float(value[1])


def _moving_position(item: dict[str, Any], elapsed_ms: float) -> tuple[float, float]:
    return (
        float(item["x0"]) + math.sin(float(item["phase"]) + elapsed_ms * float(item["rate_x"])) * float(item["amp_x"]),
        float(item["y0"]) + math.cos(float(item["phase"]) * .83 + elapsed_ms * float(item["rate_y"])) * float(item["amp_y"]),
    )


def _settled_position(timeline: dict[str, Any], object_id: str) -> tuple[float, float]:
    index = list(timeline["settle_order"]).index(object_id)
    grid = timeline["settle_grid"]
    return (
        float(grid["x0"]) + (index % int(grid["columns"])) * float(grid["dx"]),
        float(grid["y0"]) + (index // int(grid["columns"])) * float(grid["dy"]),
    )


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if str(payload.get("mechanic_id") or "") != MECHANIC_ID or str(ground_truth.get("mechanic_id") or "") != MECHANIC_ID:
        return {"graded": True, "passed": False, "feedback": "mechanic mismatch"}
    if not challenge_id or str(payload.get("challenge_id") or "") != challenge_id or str(public_state.get("challenge_id") or "") != challenge_id:
        return {"graded": True, "passed": False, "feedback": "stale challenge"}
    timeline = ground_truth.get("timeline")
    if not isinstance(timeline, dict) or public_state.get("timeline") != timeline:
        return {"graded": True, "passed": False, "feedback": "public/private timeline mismatch"}
    objects = {str(item["id"]): item for item in timeline.get("objects") or []}
    target_id = str(ground_truth.get("target_object_id") or "")
    if target_id not in objects:
        return {"graded": True, "passed": False, "feedback": "hidden first carrier is malformed"}
    first_event = min(timeline.get("events") or [], key=lambda item: int(item["at_ms"]), default=None)
    if not isinstance(first_event, dict) or str(first_event.get("object_id")) != target_id:
        return {"graded": True, "passed": False, "feedback": "hidden event order is malformed"}

    events = payload.get("events")
    if not isinstance(events, list) or not 3 <= len(events) <= 480:
        return {"graded": True, "passed": False, "feedback": "lens transcript is missing or outside limits"}
    armed = returned = selected = False
    pre_hits = change_hits = 0
    selected_id = ""
    lens_radius = float(timeline["lens_radius"])
    pre_window = int(timeline["proof"]["pre_window_ms"])
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return {"graded": True, "passed": False, "feedback": f"lens event {sequence} sequence mismatch"}
        kind = str(event.get("kind") or "")
        if kind == "arm":
            if armed or returned or selected:
                return {"graded": True, "passed": False, "feedback": "field armed out of order"}
            armed = True
            continue
        if kind == "observe":
            if not armed or returned or selected or str(event.get("mode") or "") not in {"live", "review"}:
                return {"graded": True, "passed": False, "feedback": "lens observation occurred outside the recorded field"}
            try:
                at_ms = float(event.get("timeline_ms"))
                cursor = _point(event.get("cursor"))
            except (TypeError, ValueError):
                return {"graded": True, "passed": False, "feedback": "lens observation is malformed"}
            if not 0 <= at_ms <= float(timeline["review_end_ms"]):
                return {"graded": True, "passed": False, "feedback": "lens observation lies outside recorded time"}
            target_position = _moving_position(objects[target_id], at_ms)
            if math.hypot(cursor[0] - target_position[0], cursor[1] - target_position[1]) <= lens_radius:
                start = float(first_event["at_ms"])
                end = start + float(first_event["duration_ms"])
                if start - pre_window <= at_ms < start:
                    pre_hits += 1
                elif start <= at_ms <= end:
                    change_hits += 1
            continue
        if kind == "return_settled":
            if not armed or returned or selected:
                return {"graded": True, "passed": False, "feedback": "settled return occurred out of order"}
            returned = True
            continue
        if kind == "select":
            if not returned or selected:
                return {"graded": True, "passed": False, "feedback": "carrier selected before returning to the settled field"}
            selected_id = str(event.get("selected_object_id") or "")
            if selected_id not in objects:
                return {"graded": True, "passed": False, "feedback": "selected carrier does not exist"}
            try:
                point = _point(event.get("point"))
            except ValueError as exc:
                return {"graded": True, "passed": False, "feedback": str(exc)}
            expected_point = _settled_position(timeline, selected_id)
            if math.hypot(point[0] - expected_point[0], point[1] - expected_point[1]) > 40:
                return {"graded": True, "passed": False, "feedback": "settled click missed the claimed carrier"}
            selected = True
            continue
        return {"graded": True, "passed": False, "feedback": f"unknown lens event {kind}"}
    if str(payload.get("selected_object_id") or "") != selected_id:
        return {"graded": True, "passed": False, "feedback": "submitted carrier disagrees with the physical selection"}
    proof = timeline["proof"]
    passed = bool(
        selected
        and selected_id == target_id
        and pre_hits >= int(proof["minimum_pre_hits"])
        and change_hits >= int(proof["minimum_change_hits"])
    )
    return {
        "graded": True,
        "passed": passed,
        "feedback": f"first-carrier lens comparison pre {pre_hits}/{proof['minimum_pre_hits']}; change {change_hits}/{proof['minimum_change_hits']}; identity {'matched' if selected_id == target_id else 'mismatched'}",
    }
