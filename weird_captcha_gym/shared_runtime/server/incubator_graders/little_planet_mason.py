from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "little_planet_mason"
STEP = math.pi / 12.0
INPUT_SOURCES = {
    "simplified": {"select": "tray_select", "rotate": "rotate_button", "place": "socket_click"},
    "full": {"select": None, "rotate": "block_right_click", "place": "direct_drag"},
}


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _angle(value: float) -> float:
    return ((float(value) + math.pi) % (2 * math.pi)) - math.pi


def _distance(a: list[float], b: list[float]) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def _radial_settle(drop: list[float], target: list[float], planet: dict[str, Any]) -> list[float]:
    px = float(planet.get("x", 450))
    py = float(planet.get("y", 258))
    dx = float(drop[0]) - px
    dy = float(drop[1]) - py
    drop_radius = math.hypot(dx, dy)
    target_dx = float(target[0]) - px
    target_dy = float(target[1]) - py
    target_radius = math.hypot(target_dx, target_dy)
    if drop_radius <= 1e-9:
        return [float(target[0]), float(target[1])]
    return [px + dx / drop_radius * target_radius, py + dy / drop_radius * target_radius]


def _same_number(actual: Any, expected: float, tolerance: float) -> bool:
    try:
        return abs(float(actual) - expected) <= tolerance
    except (TypeError, ValueError):
        return False


def _bind(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> str | None:
    for key in ("mechanic_id", "task_id", "challenge_id"):
        expected = str(truth.get(key) or "")
        if not expected or str(payload.get(key) or "") != expected:
            return f"payload {key} mismatch"
        if str(public.get(key) or "") != expected:
            return f"public {key} mismatch"
    if truth.get("control_condition") != public.get("control_condition"):
        return "interaction condition mismatch"
    return None


def _contract(truth: dict[str, Any], public: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str], str, float, float]:
    hidden = truth.get("blocks")
    visible = public.get("blocks")
    if not isinstance(hidden, list) or not isinstance(visible, list) or hidden != visible:
        raise ValueError("visible blocks differ from the generated block contract")
    by_id: dict[str, dict[str, Any]] = {}
    for block in hidden:
        if not isinstance(block, dict) or not block.get("id"):
            raise ValueError("block is malformed")
        block_id = str(block["id"])
        if block_id in by_id:
            raise ValueError("block ids are not unique")
        by_id[block_id] = block
    required = [block_id for block_id in truth.get("solution_order") or []]
    if not required or any(block_id not in by_id or not by_id[block_id].get("required") for block_id in required):
        raise ValueError("solution order is malformed")
    condition = truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "full")
    if interaction not in INPUT_SOURCES:
        raise ValueError("interaction mode is malformed")
    requirements = truth.get("requirements") or {}
    return (
        by_id,
        required,
        interaction,
        float(requirements.get("placement_tolerance", 0)),
        float(requirements.get("angle_tolerance", 0)),
    )


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if not all(isinstance(value, dict) for value in (payload, ground_truth, public_state)):
        return _fail("invalid result documents")
    binding_error = _bind(payload, ground_truth, public_state)
    if binding_error:
        return _fail(binding_error)
    try:
        blocks, required_order, interaction, position_tolerance, angle_tolerance = _contract(ground_truth, public_state)
    except (TypeError, ValueError, KeyError) as exc:
        return _fail(f"invalid Little Planet Mason contract: {exc}")
    if str(payload.get("interaction_mode") or "") != interaction:
        return _fail("payload interaction mode mismatch")

    events = payload.get("events")
    if not isinstance(events, list) or len(events) > 160:
        return _fail("masonry transcript is missing or too long")
    sources = INPUT_SOURCES[interaction]
    angles: dict[str, float] = {block_id: 0.0 for block_id in blocks}
    selected: str | None = None
    placed: list[str] = []
    accepted_events = 0
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return _fail(f"event {sequence} has an invalid sequence")
        kind = str(event.get("kind") or "")
        block_id = str(event.get("block_id") or "")
        if block_id not in blocks:
            return _fail(f"event {sequence} names an unknown block")
        if kind == "select":
            if interaction != "simplified" or event.get("input_source") != sources["select"]:
                return _fail(f"event {sequence} uses the wrong selection surface")
            if block_id in placed:
                return _fail(f"event {sequence} selects an already placed block")
            selected = block_id
            continue
        if kind == "rotate":
            if event.get("input_source") != sources["rotate"]:
                return _fail(f"event {sequence} uses the wrong rotation surface")
            try:
                delta = float(event.get("delta"))
                before = float(event.get("angle_before"))
                after = float(event.get("angle_after"))
            except (TypeError, ValueError):
                return _fail(f"event {sequence} has an invalid rotation")
            if abs(abs(delta) - STEP) > 1e-5 or abs(_angle(before) - _angle(angles[block_id])) > 1e-5:
                return _fail(f"event {sequence} has an inconsistent rotation delta")
            if abs(_angle(after) - _angle(before + delta)) > 1e-5:
                return _fail(f"event {sequence} has an inconsistent rotation result")
            angles[block_id] = _angle(after)
            continue
        if kind != "place":
            return _fail(f"event {sequence} has an invalid action kind")
        if event.get("input_source") != sources["place"]:
            return _fail(f"event {sequence} uses the wrong placement surface")
        if interaction == "simplified" and selected != block_id:
            return _fail(f"event {sequence} places without selecting that block")
        if interaction == "full" and selected is not None:
            return _fail(f"event {sequence} carries simplified selection state")
        if block_id in placed:
            return _fail(f"event {sequence} places a block twice")
        if block_id not in required_order:
            return _fail(f"event {sequence} names a non-required block")
        block = blocks[block_id]
        if not block.get("required"):
            return _fail(f"event {sequence} attempts to use a spare block")
        support = str(block.get("support") or "")
        if support != "planet" and support not in placed:
            return _fail(f"event {sequence} places before its support is available")
        target = block.get("target")
        drop = event.get("drop")
        settled = event.get("settled")
        if not isinstance(target, list) or len(target) != 2 or not isinstance(drop, list) or len(drop) != 2 or not isinstance(settled, list) or len(settled) != 2:
            return _fail(f"event {sequence} is missing release or settle coordinates")
        predicted_settled = _radial_settle(drop, target, ground_truth.get("planet") or {})
        if _distance(settled, predicted_settled) > 1e-3:
            return _fail(f"event {sequence} does not record the radial settled position")
        if _distance(settled, target) > position_tolerance:
            return _fail(f"event {sequence} settles outside the keyed landing window")
        if not _same_number(event.get("angle"), angles[block_id], 1e-5):
            return _fail(f"event {sequence} records the wrong block orientation")
        try:
            target_angle = float(block["target_angle"])
        except (TypeError, ValueError, KeyError):
            return _fail(f"event {sequence} has no target orientation")
        if abs(_angle(angles[block_id] - target_angle)) > angle_tolerance:
            return _fail(f"event {sequence} leaves the block face misaligned with radial gravity")
        if event.get("support") != support or event.get("accepted") is not True:
            return _fail(f"event {sequence} has an inconsistent support contact")
        placed.append(block_id)
        accepted_events += 1
        selected = None

    completed = payload.get("completed") is True
    passed = completed and set(placed) == set(required_order) and accepted_events == len(required_order)
    return {
        "graded": True,
        "passed": passed,
        "feedback": (
            f"radial masonry replay: {len(placed)}/{len(required_order)} blocks settled; "
            f"{interaction} input; {'PASS' if passed else 'FAIL'}"
        ),
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    return {
        "solution_order": ground_truth.get("solution_order") or [],
        "instruction": "Place each visible block in support order, aligning its face with the planet-centre ray.",
    }
