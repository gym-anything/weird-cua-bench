from __future__ import annotations

import math
from typing import Any, Callable


def _ghost(result: dict[str, Any], truth: dict[str, Any], _state: dict[str, Any]) -> dict[str, Any]:
    expected = {str(key): int(value) for key, value in (truth.get("expected_positions") or {}).items()}
    try:
        placements = {str(key): int(value) for key, value in (result.get("placements") or {}).items()}
    except (TypeError, ValueError):
        placements = {}
    correct = sum(1 for key, value in expected.items() if placements.get(key) == value)
    passed = bool(expected) and placements == expected
    return {"graded": True, "passed": passed, "feedback": f"pieces {correct}/{len(expected)}"}


def _constellation(result: dict[str, Any], truth: dict[str, Any], _state: dict[str, Any]) -> dict[str, Any]:
    expected = truth.get("expected_click") or {}
    click = result.get("click") or {}
    try:
        distance = math.hypot(
            float(click.get("x")) - float(expected.get("x")),
            float(click.get("y")) - float(expected.get("y")),
        )
        radius = float(expected.get("radius"))
    except (TypeError, ValueError):
        return {"graded": True, "passed": False, "feedback": "click missing"}
    return {"graded": True, "passed": distance <= radius, "feedback": f"distance {distance:.2f}"}


def _grillmaster(result: dict[str, Any], truth: dict[str, Any], _state: dict[str, Any]) -> dict[str, Any]:
    targets = truth.get("targets") or {}
    durations = result.get("durations_ms") or {}
    correct = 0
    for food_id, target in targets.items():
        try:
            elapsed = float(durations.get(food_id))
            target_ms = float(target.get("target_ms"))
            tolerance_ms = float(target.get("tolerance_ms"))
        except (TypeError, ValueError):
            continue
        if abs(elapsed - target_ms) <= tolerance_ms:
            correct += 1
    passed = bool(targets) and correct == len(targets) and set(durations) == set(targets)
    return {"graded": True, "passed": passed, "feedback": f"foods {correct}/{len(targets)}"}


def _rotating_keyboard(result: dict[str, Any], truth: dict[str, Any], _state: dict[str, Any]) -> dict[str, Any]:
    expected = str(truth.get("target") or "")
    submitted = str(result.get("text") or "").upper()
    passed = bool(expected) and submitted == expected
    return {"graded": True, "passed": passed, "feedback": "code accepted" if passed else "code rejected"}


def _slot_reel(result: dict[str, Any], truth: dict[str, Any], _state: dict[str, Any]) -> dict[str, Any]:
    expected = str(truth.get("sequence") or "")
    submitted = str(result.get("captured_sequence") or "").upper()
    expected_reels = [str(item) for item in truth.get("reel_ids") or []]
    frozen_reels = [str(item) for item in result.get("frozen_reel_ids") or []]
    wrong_keys = int(result.get("wrong_keys") or 0)
    max_strikes = int(truth.get("max_strikes") or 3)
    passed = (
        bool(expected)
        and submitted == expected
        and frozen_reels == expected_reels
        and wrong_keys < max_strikes
    )
    return {
        "graded": True,
        "passed": passed,
        "feedback": f"captured {len(submitted)}/{len(expected)}; strikes {wrong_keys}/{max_strikes}",
    }


def _domino(result: dict[str, Any], truth: dict[str, Any], _state: dict[str, Any]) -> dict[str, Any]:
    loose_ids = set(str(item) for item in truth.get("loose_ids") or [])
    raw = result.get("placements") or {}
    if set(str(key) for key in raw) != loose_ids:
        return {"graded": True, "passed": False, "feedback": "not all loose dominoes were placed"}
    try:
        for item in raw.values():
            float(item.get("x"))
            float(item.get("y"))
            float(item.get("angle"))
    except (TypeError, ValueError):
        return {"graded": True, "passed": False, "feedback": "domino placement is invalid"}
    expected = set(str(item) for item in truth.get("expected_body_ids") or [])
    first = str(truth.get("first_body_id") or "")
    bell = str(truth.get("bell_body_id") or "bell-body")
    minimum_swing = float(truth.get("minimum_bell_swing_radians") or 0.03)
    try:
        bell_swing = abs(float(result.get("bell_peak_angle") or 0.0))
    except (TypeError, ValueError):
        bell_swing = 0.0
    allowed = expected | {bell}
    graph = {label: set() for label in allowed}
    valid_pairs = 0
    for pair in result.get("collision_pairs") or []:
        if not isinstance(pair, list) or len(pair) != 2:
            continue
        left, right = str(pair[0]), str(pair[1])
        if left not in allowed or right not in allowed or left == right:
            continue
        graph[left].add(right)
        graph[right].add(left)
        valid_pairs += 1
    seen: set[str] = set()
    queue = [first] if first in graph else []
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        queue.extend(graph[current] - seen)
    connected = len((expected | {bell}) & seen)
    physics_engine = str(result.get("physics_engine") or "")
    passed = (
        result.get("run_completed") is True
        and result.get("bell_hit") is True
        and bell_swing >= minimum_swing
        and physics_engine == "matter-js@0.20.0"
        and (expected | {bell}) <= seen
    )
    return {
        "graded": True,
        "passed": passed,
        "feedback": (
            f"rigid-body collision graph {connected}/{len(expected) + 1}; "
            f"contacts {valid_pairs}; physical bell swing={bell_swing:.3f} rad"
        ),
    }


def _funeral(result: dict[str, Any], truth: dict[str, Any], _state: dict[str, Any]) -> dict[str, Any]:
    required_events = [str(item) for item in truth.get("required_events") or []]
    events = [str(item) for item in result.get("events") or []]
    max_cells = int(truth.get("moss_cells") or 24)
    cells = set()
    for item in result.get("brushed_cells") or []:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= value < max_cells:
            cells.add(value)
    flowers = set(str(item) for item in result.get("gathered_flower_ids") or [])
    expected_flowers = set(str(item) for item in truth.get("flower_ids") or [])
    threshold = int(truth.get("brush_threshold") or 17)
    completed = result.get("completed") is True
    passed = completed and events == required_events and len(cells) >= threshold and flowers == expected_flowers
    return {
        "graded": True,
        "passed": passed,
        "feedback": (
            f"ritual {len(events)}/{len(required_events)}; moss {len(cells)}/{threshold}; "
            f"flowers {len(flowers)}/{len(expected_flowers)}"
        ),
    }


GRADERS: dict[str, Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], dict[str, Any]]] = {
    "motion_only_ghost_jigsaw": _ghost,
    "cursor_constellation_hunt": _constellation,
    "parallel_grillmaster": _grillmaster,
    "rotating_keyboard": _rotating_keyboard,
    "slot_reel_capture": _slot_reel,
    "domino_autopsy": _domino,
    "funeral_ritual": _funeral,
}


def grade(result: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    mechanic_id = str(ground_truth.get("mechanic_id") or result.get("mechanic_id") or "")
    grader = GRADERS.get(mechanic_id)
    if grader is None:
        return {"graded": False, "passed": False, "feedback": f"no legacy grader for {mechanic_id}"}
    return grader(result, ground_truth, public_state)
