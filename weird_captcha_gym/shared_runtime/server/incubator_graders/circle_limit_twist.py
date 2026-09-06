from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "circle_limit_twist"


def _fail(feedback: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": feedback}


def _matrix_multiply(
    left: tuple[complex, complex, complex, complex],
    right: tuple[complex, complex, complex, complex],
) -> tuple[complex, complex, complex, complex]:
    a, b, c, d = left
    e, f, g, h = right
    return (a * e + b * g, a * f + b * h, c * e + d * g, c * f + d * h)


def _apply_view(matrix: tuple[complex, complex, complex, complex], point: complex) -> complex:
    a, b, c, d = matrix
    denominator = c * point + d
    if abs(denominator) < 1e-12:
        raise ValueError("singular view")
    return (a * point + b) / denominator


def _phi(point: complex) -> tuple[complex, complex, complex, complex]:
    return (1.0 + 0.0j, -point, -point.conjugate(), 1.0 + 0.0j)


def _inverse_phi(point: complex) -> tuple[complex, complex, complex, complex]:
    return (1.0 + 0.0j, point, point.conjugate(), 1.0 + 0.0j)


def _translation(start: complex, end: complex) -> tuple[complex, complex, complex, complex]:
    return _matrix_multiply(_inverse_phi(end), _phi(start))


def _point(value: Any) -> complex:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("point must have two coordinates")
    point = complex(float(value[0]), float(value[1]))
    if not math.isfinite(point.real) or not math.isfinite(point.imag):
        raise ValueError("point must be finite")
    return point


def _state(value: Any, face_count: int, sides: int) -> tuple[tuple[int, ...], ...]:
    if not isinstance(value, list) or len(value) != face_count:
        raise ValueError("state has wrong face count")
    parsed = tuple(tuple(int(color) for color in face) for face in value)
    if any(len(face) != sides for face in parsed):
        raise ValueError("state has wrong sticker count")
    if any(color < 0 or color >= face_count for face in parsed for color in face):
        raise ValueError("state has invalid color")
    return parsed


def _apply_twist(
    state: tuple[tuple[int, ...], ...],
    cycles: dict[str, Any],
    face_id: int,
    direction: int,
) -> tuple[tuple[int, ...], ...]:
    next_state = [list(face) for face in state]
    definition = cycles.get(str(face_id))
    if not isinstance(definition, dict):
        raise ValueError("unknown twist face")
    for cycle_name in ("own", "ring"):
        positions = definition.get(cycle_name)
        if not isinstance(positions, list) or len(positions) != 7:
            raise ValueError("invalid twist cycle")
        parsed = [(int(position[0]), int(position[1])) for position in positions]
        values = [state[face][sector] for face, sector in parsed]
        shifted = values[-1:] + values[:-1] if direction == 1 else values[1:] + values[:1]
        for (face, sector), color in zip(parsed, shifted):
            next_state[face][sector] = color
    return tuple(tuple(face) for face in next_state)


def _solved(state: tuple[tuple[int, ...], ...]) -> bool:
    return bool(state) and all(len(set(face)) == 1 for face in state)


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if any(str(item.get("mechanic_id") or "") != MECHANIC_ID for item in (payload, ground_truth, public_state)):
        return _fail("mechanic mismatch")
    if not challenge_id or payload.get("challenge_id") != challenge_id or public_state.get("challenge_id") != challenge_id:
        return _fail("stale challenge")
    if payload.get("task_id") != ground_truth.get("task_id") or public_state.get("task_id") != ground_truth.get("task_id"):
        return _fail("task mismatch")
    truth_puzzle = ground_truth.get("puzzle") or {}
    if public_state.get("puzzle") != truth_puzzle:
        return _fail("public puzzle differs from grading contract")
    if public_state.get("control_condition") != ground_truth.get("control_condition"):
        return _fail("control condition mismatch")

    interaction = str((ground_truth.get("control_condition") or {}).get("interaction") or "full")
    twist_source = {"simplified": "proxy_buttons", "full": "canvas_click"}.get(interaction)
    if twist_source is None:
        return _fail("invalid interaction condition")
    try:
        faces = truth_puzzle["faces"]
        face_count = len(faces)
        sides = int(truth_puzzle["sides"])
        budget = int(truth_puzzle["move_budget"])
        activation_radius = float(truth_puzzle["activation_radius"])
        state = _state(truth_puzzle["initial_state"], face_count, sides)
        centers = {int(face["id"]): _point(face["center"]) for face in faces}
        cycles = truth_puzzle["twist_cycles"]
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        return _fail(f"invalid puzzle contract: {exc}")
    if sides != 7 or set(centers) != set(range(face_count)):
        return _fail("malformed face contract")

    events = payload.get("events")
    if not isinstance(events, list) or len(events) > 600:
        return _fail("event transcript is missing or outside limits")
    view = (1.0 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j, 1.0 + 0.0j)
    twist_count = 0
    view_events = 0
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return _fail(f"event {sequence} sequence mismatch")
        kind = str(event.get("kind") or "")
        try:
            if kind == "pan":
                if interaction != "full" or event.get("input_source") != "mobius_drag":
                    return _fail(f"event {sequence} uses the wrong pan input")
                start = _point(event.get("start"))
                end = _point(event.get("end"))
                if abs(start) >= 0.98 or abs(end) >= 0.98 or abs(start - end) < 0.001:
                    return _fail(f"event {sequence} has an invalid Mobius drag")
                view = _matrix_multiply(_translation(start, end), view)
                view_events += 1
                continue
            if kind == "focus":
                if interaction != "simplified" or event.get("input_source") != "focus_click":
                    return _fail(f"event {sequence} uses the wrong focus input")
                face_id = int(event.get("face_id"))
                if face_id not in centers:
                    return _fail(f"event {sequence} focuses an unknown face")
                current = _apply_view(view, centers[face_id])
                if abs(current) >= 0.985:
                    return _fail(f"event {sequence} focuses an invisible face")
                view = _matrix_multiply(_phi(current), view)
                view_events += 1
                continue
            if kind != "twist":
                return _fail(f"event {sequence} has an unknown kind")
            if event.get("input_source") != twist_source:
                return _fail(f"event {sequence} uses the wrong twist input")
            if twist_count >= budget:
                return _fail(f"event {sequence} exceeds the twist limit")
            face_id = int(event.get("face_id"))
            direction = int(event.get("direction"))
            if face_id not in centers or direction not in (-1, 1):
                return _fail(f"event {sequence} has an invalid face or direction")
            focus_distance = abs(_apply_view(view, centers[face_id]))
            if focus_distance > activation_radius + 0.003:
                return _fail(f"event {sequence} twists outside the central aperture")
            reported_distance = float(event.get("focus_distance"))
            if not math.isfinite(reported_distance) or abs(reported_distance - focus_distance) > 0.002:
                return _fail(f"event {sequence} has a forged focus distance")
            before = _state(event.get("before_state"), face_count, sides)
            after = _state(event.get("after_state"), face_count, sides)
            if before != state:
                return _fail(f"event {sequence} before-state mismatch")
            expected_after = _apply_twist(state, cycles, face_id, direction)
            if after != expected_after:
                return _fail(f"event {sequence} contradicts the sticker permutation")
            twist_count += 1
            if event.get("twists_after") != twist_count:
                return _fail(f"event {sequence} has a forged twist count")
            state = expected_after
        except (TypeError, ValueError, KeyError, IndexError, ZeroDivisionError) as exc:
            return _fail(f"event {sequence} is malformed: {exc}")

    try:
        final_state = _state(payload.get("final_state"), face_count, sides)
    except (TypeError, ValueError) as exc:
        return _fail(f"invalid final state: {exc}")
    if final_state != state:
        return _fail("claimed final state does not match replay")
    if payload.get("twist_count") != twist_count or payload.get("view_event_count") != view_events:
        return _fail("claimed event totals do not match replay")
    completed = _solved(state) and twist_count <= budget
    if payload.get("completed") is not completed:
        return _fail("claimed completion does not match replay")
    return {
        "graded": True,
        "passed": completed,
        "feedback": (
            f"circle-limit replay {'restored' if completed else 'incomplete'}; "
            f"twists {twist_count}/{budget}; view changes {view_events}"
        ),
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {"solution_moves": ground_truth.get("solution_moves") or []}

