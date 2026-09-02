from __future__ import annotations

import math
import re
from typing import Any


MECHANIC_ID = "reveal_to_identify"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} is not finite")
    return float(value)


def _point(value: Any, width: int, height: int, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} is malformed")
    x = _number(value[0], f"{label} x")
    y = _number(value[1], f"{label} y")
    if not 0 <= x <= width or not 0 <= y <= height:
        raise ValueError(f"{label} leaves the plate")
    return [round(x, 2), round(y, 2)]


def _normalise_answer(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if any(str(item.get("mechanic_id") or "") != MECHANIC_ID for item in (payload, ground_truth, public_state)):
        return _fail("mechanic mismatch")
    challenge_id = str(ground_truth.get("challenge_id") or "")
    task_id = str(ground_truth.get("task_id") or "")
    if not challenge_id or str(payload.get("challenge_id") or "") != challenge_id or str(public_state.get("challenge_id") or "") != challenge_id:
        return _fail("stale or mismatched reveal challenge")
    if not task_id or str(payload.get("task_id") or "") != task_id or str(public_state.get("task_id") or "") != task_id:
        return _fail("task identity mismatch")
    truth_condition = ground_truth.get("control_condition")
    if truth_condition != public_state.get("control_condition"):
        return _fail("public control condition differs from reveal contract")
    interaction = str((truth_condition or {}).get("interaction") or "full")
    if interaction not in {"simplified", "full"}:
        return _fail("reveal interaction condition is invalid")
    if str(payload.get("interaction_mode") or "") != interaction:
        return _fail("submitted interaction mode does not match the task")
    expected_source = {"simplified": "coordinate_reveal", "full": "plate_click"}[interaction]
    try:
        stage = dict(ground_truth["stage"])
        width, height = int(stage["width"]), int(stage["height"])
        reveal = dict(ground_truth["reveal"])
        budget, radius = int(reveal["budget"]), int(reveal["radius"])
        accepted_answers = {_normalise_answer(item) for item in ground_truth["accepted_answers"]}
        if not accepted_answers or "" in accepted_answers:
            raise ValueError("accepted answer set is empty")
        for key in ("stage", "scene", "reveal"):
            if public_state.get(key) != ground_truth.get(key):
                raise ValueError(f"public {key} differs from replay contract")
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"invalid reveal contract: {exc}")

    events = payload.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= budget:
        return _fail("a valid identification requires one to the configured number of reveals")
    centers: list[list[float]] = []
    try:
        for sequence, event in enumerate(events, start=1):
            if not isinstance(event, dict) or event.get("sequence") != sequence:
                raise ValueError(f"reveal {sequence} has invalid sequence")
            if str(event.get("kind") or "") != "reveal":
                raise ValueError(f"event {sequence} is not a reveal")
            if str(event.get("input_source") or "") != expected_source:
                raise ValueError(f"reveal {sequence} uses the wrong interaction surface")
            if _number(event.get("radius"), f"reveal {sequence} radius") != radius:
                raise ValueError(f"reveal {sequence} reports the wrong disc radius")
            expected_remaining = budget - sequence
            if _number(event.get("remaining_after"), f"reveal {sequence} remaining budget") != expected_remaining:
                raise ValueError(f"reveal {sequence} reports a false remaining budget")
            centers.append(_point(event.get("point"), width, height, f"reveal {sequence} point"))
    except (TypeError, ValueError) as exc:
        return _fail(str(exc))

    submitted_centers = payload.get("revealed_centers")
    if submitted_centers != centers:
        return _fail("submitted reveal centers do not match the replay")
    if payload.get("reveal_count") != len(events):
        return _fail("submitted reveal count does not match the replay")
    if payload.get("remaining_budget") != budget - len(events):
        return _fail("submitted remaining budget does not match the replay")
    if payload.get("completed") is not True:
        return _fail("identification was not submitted as complete")
    answer = _normalise_answer(payload.get("answer"))
    if not answer or len(str(payload.get("answer") or "")) > 32:
        return _fail("the identification text is missing or too long")
    passed = answer in accepted_answers
    return {
        "graded": True,
        "passed": passed,
        "score": 100 if passed else 0,
        "feedback": (
            f"reveal replay: {len(events)}/{budget} discs used; identification accepted"
            if passed
            else f"reveal replay: {len(events)}/{budget} discs used; identification does not match the plate"
        ),
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {
        "answer": ground_truth.get("answer"),
        "salient_points": ground_truth.get("salient_points") or [],
        "answers": [ground_truth.get("answer")],
    }
