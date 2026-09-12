"""Independent swept-voxel replay for Timber Knot Release."""
from __future__ import annotations

from typing import Any, Iterable

MECHANIC_ID = "timber_knot_release"


def _cells(cells: Iterable[Iterable[int]], offset: Iterable[int]) -> set[tuple[int, int, int]]:
    origin = tuple(int(value) for value in offset)
    return {tuple(int(cell[i]) + origin[i] for i in range(3)) for cell in cells}


def _swept_clear(cells: list[list[int]], old: list[int], new: list[int], others: list[dict[str, Any]]) -> bool:
    delta = [int(new[i]) - int(old[i]) for i in range(3)]
    axes = [i for i, value in enumerate(delta) if value]
    if len(axes) != 1 or delta[axes[0]] not in (-1, 1):
        return False
    axis = axes[0]
    moving = _cells(cells, old)
    for other in others:
        fixed = _cells(other["voxels"], other["offset"])
        for a in moving:
            for b in fixed:
                if any(a[i] != b[i] for i in range(3) if i != axis):
                    continue
                low, high = sorted((a[axis], a[axis] + delta[axis]))
                if max(low, b[axis]) < min(high + 1, b[axis] + 1):
                    return False
    return True


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _binding(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> str | None:
    for key in ("mechanic_id", "task_id", "challenge_id"):
        expected = str(truth.get(key) or "")
        if not expected or str(payload.get(key) or "") != expected:
            return f"{key} mismatch"
        if str(public.get(key) or "") != expected:
            return f"public {key} mismatch"
    if truth.get("control_condition") != public.get("control_condition"):
        return "control condition mismatch"
    return None


def _contract(truth: dict[str, Any], public: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], int, str]:
    hidden = truth.get("pieces")
    visible = public.get("pieces")
    if not isinstance(hidden, list) or not isinstance(visible, list) or len(hidden) != len(visible):
        raise ValueError("piece list mismatch")
    pieces: dict[str, dict[str, Any]] = {}
    public_keys = ("id", "label", "color", "voxels", "offset", "axis", "axis_index", "exit_sign", "voxel_count")
    for h, v in zip(hidden, visible):
        if not isinstance(h, dict) or not isinstance(v, dict) or any(h.get(k) != v.get(k) for k in public_keys):
            raise ValueError("visible voxel contract differs from server truth")
        piece_id = str(h.get("id") or "")
        if not piece_id or piece_id in pieces or h.get("axis") not in ("x", "y", "z"):
            raise ValueError("malformed beam")
        if int(h.get("voxel_count") or 0) != len(h.get("voxels") or []):
            raise ValueError("voxel count mismatch")
        pieces[piece_id] = h
    if len(pieces) != len(hidden):
        raise ValueError("duplicate beam id")
    if not 3 <= len(pieces) <= 6:
        raise ValueError("unsupported beam count")
    difficulty = public.get("difficulty") or {}
    steps = int(difficulty.get("extraction_steps") or 0)
    if not 4 <= steps <= 9:
        raise ValueError("invalid extraction length")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    if interaction not in ("simplified", "full"):
        raise ValueError("invalid interaction")
    return pieces, steps, interaction


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if not all(isinstance(value, dict) for value in (payload, ground_truth, public_state)):
        return _fail("malformed result")
    bound = _binding(payload, ground_truth, public_state)
    if bound:
        return _fail(bound)
    try:
        pieces, steps, interaction = _contract(ground_truth, public_state)
    except (TypeError, ValueError, KeyError) as exc:
        return _fail(f"invalid voxel contract: {exc}")
    if str(payload.get("interaction_mode") or "") != interaction:
        return _fail("wrong interaction mode")
    events = payload.get("events")
    if not isinstance(events, list) or not 2 <= len(events) <= 1500:
        return _fail("missing or malformed transcript")
    source = {"full": {"move": "direct_drag", "select": "beam_click", "orbit": "camera_drag"}, "simplified": {"move": "proxy_step", "select": "beam_select", "orbit": "orbit_button"}}[interaction]
    current = {piece_id: list(piece["offset"]) for piece_id, piece in pieces.items()}
    active = set(pieces)
    counts = {piece_id: 0 for piece_id in pieces}
    selected: str | None = None
    seen_start = False
    for sequence, event in enumerate(events, 1):
        if not isinstance(event, dict) or event.get("sequence") != sequence or type(event.get("sequence")) is not int:
            return _fail(f"event {sequence} has invalid sequence")
        kind = str(event.get("kind") or "")
        if kind == "start":
            if sequence != 1 or seen_start:
                return _fail("start must be the first event")
            seen_start = True
            continue
        if not seen_start:
            return _fail("missing start")
        if kind == "orbit":
            if event.get("input_source") != source["orbit"]:
                return _fail("wrong camera surface")
            continue
        if kind == "select":
            piece_id = str(event.get("piece") or "")
            if interaction != "simplified" or event.get("input_source") != source["select"] or piece_id not in active:
                return _fail("invalid beam selection")
            selected = piece_id
            continue
        if kind != "move":
            if kind == "finish" and sequence == len(events):
                if event.get("input_source") != "certify_button":
                    return _fail("missing visible certification")
                released = event.get("released")
                if event.get("completed") is not True or not isinstance(released, list) or set(map(str, released)) != set(pieces) or active:
                    return _fail("not every beam has cleared the knot")
                return {"graded": True, "passed": True, "score": 100, "feedback": f"swept voxel replay: {len(pieces)} beams released legally"}
            return _fail(f"unknown event kind {kind}")
        piece_id = str(event.get("piece") or "")
        if piece_id not in active:
            return _fail("move names a released or unknown beam")
        if event.get("input_source") != source["move"]:
            return _fail("move used the wrong interaction surface")
        if interaction == "simplified" and selected != piece_id:
            return _fail("simplified move requires selecting that beam")
        if interaction == "full" and selected is not None:
            return _fail("full move cannot carry proxy selection state")
        old = event.get("from")
        new = event.get("to")
        if not isinstance(old, list) or not isinstance(new, list) or len(old) != 3 or len(new) != 3 or old != current[piece_id]:
            return _fail("move does not start at the current visible offset")
        piece = pieces[piece_id]
        axis = str(piece["axis"])
        axis_index = {"x": 0, "y": 1, "z": 2}[axis]
        delta = [int(new[i]) - int(old[i]) for i in range(3)]
        if event.get("axis") != axis or event.get("direction") != int(piece["exit_sign"]):
            return _fail("beam moved against its permitted exit axis")
        if delta != [int(piece["exit_sign"]) if i == axis_index else 0 for i in range(3)]:
            return _fail("beam moves must be one cell along its exit axis")
        obstacles = [pieces[other_id] | {"offset": current[other_id]} for other_id in active if other_id != piece_id]
        if not _swept_clear(piece["voxels"], old, new, obstacles):
            return _fail("swept voxel solids intersect")
        current[piece_id] = list(new)
        counts[piece_id] += 1
        if counts[piece_id] > steps:
            return _fail("beam moved beyond its release travel")
        if counts[piece_id] == steps:
            active.remove(piece_id)
        if interaction == "simplified":
            selected = None
    return _fail("transcript ended without certification")


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    return {"instruction": "Release beams in the hidden legal order by moving each one cell along its visible exit axis.", "solution_order": ground_truth.get("solution_order") or [], "solution_steps": ground_truth.get("solution") or []}
