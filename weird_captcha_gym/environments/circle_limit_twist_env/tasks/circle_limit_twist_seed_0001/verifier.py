from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from typing import Any


MECHANIC_ID = "circle_limit_twist"
BENCHMARK_ROOT = Path(__file__).resolve().parents[4]
HELPER_PATH = BENCHMARK_ROOT / "shared_runtime" / "verifier_helpers.py"


def _load_helpers():
    spec = importlib.util.spec_from_file_location("circle_limit_twist_verifier_helpers", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {HELPER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _multiply(left: tuple[complex, ...], right: tuple[complex, ...]) -> tuple[complex, ...]:
    a, b, c, d = left
    e, f, g, h = right
    return (a * e + b * g, a * f + b * h, c * e + d * g, c * f + d * h)


def _view(matrix: tuple[complex, ...], point: complex) -> complex:
    a, b, c, d = matrix
    denominator = c * point + d
    if abs(denominator) < 1e-12:
        raise ValueError("singular view")
    return (a * point + b) / denominator


def _phi(point: complex) -> tuple[complex, ...]:
    return (1 + 0j, -point, -point.conjugate(), 1 + 0j)


def _inverse_phi(point: complex) -> tuple[complex, ...]:
    return (1 + 0j, point, point.conjugate(), 1 + 0j)


def _translation(start: complex, end: complex) -> tuple[complex, ...]:
    return _multiply(_inverse_phi(end), _phi(start))


def _point(value: Any) -> complex:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("invalid point")
    point = complex(float(value[0]), float(value[1]))
    if not math.isfinite(point.real) or not math.isfinite(point.imag):
        raise ValueError("non-finite point")
    return point


def _state(value: Any, face_count: int, sides: int) -> tuple[tuple[int, ...], ...]:
    if not isinstance(value, list) or len(value) != face_count:
        raise ValueError("wrong face count")
    result = tuple(tuple(int(color) for color in face) for face in value)
    if any(len(face) != sides for face in result):
        raise ValueError("wrong sticker count")
    if any(color < 0 or color >= face_count for face in result for color in face):
        raise ValueError("invalid color")
    return result


def _twist(
    state: tuple[tuple[int, ...], ...],
    cycles: dict[str, Any],
    face_id: int,
    direction: int,
) -> tuple[tuple[int, ...], ...]:
    next_state = [list(face) for face in state]
    definition = cycles.get(str(face_id))
    if not isinstance(definition, dict):
        raise ValueError("unknown face")
    for name in ("own", "ring"):
        positions = definition.get(name)
        if not isinstance(positions, list) or len(positions) != 7:
            raise ValueError("invalid cycle")
        parsed = [(int(item[0]), int(item[1])) for item in positions]
        values = [state[face][sector] for face, sector in parsed]
        shifted = values[-1:] + values[:-1] if direction == 1 else values[1:] + values[:1]
        for (face, sector), color in zip(parsed, shifted):
            next_state[face][sector] = color
    return tuple(tuple(face) for face in next_state)


def _verify_export(exported: dict[str, Any]) -> tuple[bool, str]:
    payload = exported.get("result") or {}
    truth = exported.get("ground_truth") or {}
    public = exported.get("public_state") or {}
    challenge = str(truth.get("challenge_id") or "")
    if payload.get("mechanic_id") != MECHANIC_ID or truth.get("mechanic_id") != MECHANIC_ID:
        return False, "mechanic mismatch"
    if not challenge or payload.get("challenge_id") != challenge or public.get("challenge_id") != challenge:
        return False, "stale challenge"
    if payload.get("task_id") != truth.get("task_id") or public.get("task_id") != truth.get("task_id"):
        return False, "task mismatch"
    puzzle = truth.get("puzzle") or {}
    if public.get("puzzle") != puzzle or public.get("control_condition") != truth.get("control_condition"):
        return False, "public contract mismatch"
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    twist_source = {"full": "canvas_click", "simplified": "proxy_buttons"}.get(interaction)
    if twist_source is None:
        return False, "invalid interaction condition"
    try:
        faces = puzzle["faces"]
        face_count = len(faces)
        sides = int(puzzle["sides"])
        budget = int(puzzle["move_budget"])
        aperture = float(puzzle["activation_radius"])
        state = _state(puzzle["initial_state"], face_count, sides)
        centers = {int(face["id"]): _point(face["center"]) for face in faces}
        cycles = puzzle["twist_cycles"]
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        return False, f"invalid puzzle contract: {exc}"
    if sides != 7 or set(centers) != set(range(face_count)):
        return False, "malformed face contract"

    events = payload.get("events")
    if not isinstance(events, list) or len(events) > 600:
        return False, "invalid transcript"
    matrix: tuple[complex, ...] = (1 + 0j, 0j, 0j, 1 + 0j)
    twists = 0
    views = 0
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return False, f"event {sequence} sequence mismatch"
        kind = str(event.get("kind") or "")
        try:
            if kind == "pan":
                if interaction != "full" or event.get("input_source") != "mobius_drag":
                    return False, f"event {sequence} wrong pan input"
                start, end = _point(event.get("start")), _point(event.get("end"))
                if abs(start) >= 0.98 or abs(end) >= 0.98 or abs(start - end) < 0.001:
                    return False, f"event {sequence} invalid pan"
                matrix = _multiply(_translation(start, end), matrix)
                views += 1
                continue
            if kind == "focus":
                if interaction != "simplified" or event.get("input_source") != "focus_click":
                    return False, f"event {sequence} wrong focus input"
                face_id = int(event.get("face_id"))
                current = _view(matrix, centers[face_id])
                if abs(current) >= 0.985:
                    return False, f"event {sequence} focuses an invisible face"
                matrix = _multiply(_phi(current), matrix)
                views += 1
                continue
            if kind != "twist" or event.get("input_source") != twist_source:
                return False, f"event {sequence} wrong twist input"
            face_id, direction = int(event.get("face_id")), int(event.get("direction"))
            if twists >= budget or face_id not in centers or direction not in (-1, 1):
                return False, f"event {sequence} invalid twist"
            distance = abs(_view(matrix, centers[face_id]))
            reported = float(event.get("focus_distance"))
            if distance > aperture + 0.003 or not math.isfinite(reported) or abs(reported - distance) > 0.002:
                return False, f"event {sequence} outside aperture"
            before = _state(event.get("before_state"), face_count, sides)
            after = _state(event.get("after_state"), face_count, sides)
            expected = _twist(state, cycles, face_id, direction)
            twists += 1
            if before != state or after != expected or event.get("twists_after") != twists:
                return False, f"event {sequence} permutation mismatch"
            state = expected
        except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError) as exc:
            return False, f"event {sequence} malformed: {exc}"

    solved = bool(state) and all(len(set(face)) == 1 for face in state) and twists <= budget
    try:
        claimed_state = _state(payload.get("final_state"), face_count, sides)
    except (TypeError, ValueError) as exc:
        return False, f"invalid final state: {exc}"
    if (
        claimed_state != state
        or payload.get("twist_count") != twists
        or payload.get("view_event_count") != views
        or payload.get("completed") is not solved
    ):
        return False, "final claims mismatch"
    return solved, f"independent circle-limit replay {'restored' if solved else 'incomplete'}; twists {twists}/{budget}; view changes {views}"


def verify_task(traj=None, env_info=None, task_info=None):
    del traj, task_info
    try:
        exported, error = _load_helpers().load_exported_result(env_info or {})
    except Exception as exc:
        return {"passed": False, "score": 0, "feedback": f"cannot load verifier dependency: {exc}"}
    if error:
        return {"passed": False, "score": 0, "feedback": error}
    passed, feedback = _verify_export(exported or {})
    return {"passed": passed, "score": 100 if passed else 0, "feedback": feedback}
