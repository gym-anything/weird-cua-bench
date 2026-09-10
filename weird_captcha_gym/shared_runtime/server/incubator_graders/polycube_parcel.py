"""Independent occupancy replay for Polycube Parcel."""

from __future__ import annotations

import math
from typing import Any, Iterable


MECHANIC_ID = "polycube_parcel"
PIECE_IDS = ("V", "L", "T", "Z", "A", "B", "P")


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _matrix(value: Any) -> list[list[int]] | None:
    if not isinstance(value, list) or len(value) != 3 or any(not isinstance(row, list) or len(row) != 3 for row in value):
        return None
    try:
        result = [[int(cell) for cell in row] for row in value]
    except (TypeError, ValueError):
        return None
    if any(abs(cell) > 1 for row in result for cell in row):
        return None
    return result


def _mat_mul(a: list[list[int]], b: list[list[int]]) -> list[list[int]]:
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _mat_vec(m: list[list[int]], v: Iterable[int]) -> list[int]:
    values = list(v)
    return [sum(m[i][j] * values[j] for j in range(3)) for i in range(3)]


def _det(m: list[list[int]]) -> int:
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


IDENTITY = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
ROTATIONS = {
    ("x", 1): [[1, 0, 0], [0, 0, -1], [0, 1, 0]],
    ("x", -1): [[1, 0, 0], [0, 0, 1], [0, -1, 0]],
    ("y", 1): [[0, 0, 1], [0, 1, 0], [-1, 0, 0]],
    ("y", -1): [[0, 0, -1], [0, 1, 0], [1, 0, 0]],
    ("z", 1): [[0, -1, 0], [1, 0, 0], [0, 0, 1]],
    ("z", -1): [[0, 1, 0], [-1, 0, 0], [0, 0, 1]],
}


def _cells(piece: dict[str, Any], orientation: list[list[int]], origin: list[int | float]) -> list[tuple[int, int, int]]:
    answer = []
    for raw in piece.get("shape") or []:
        if not isinstance(raw, list) or len(raw) != 3:
            raise ValueError("piece cell is malformed")
        rotated = _mat_vec(orientation, [int(value) for value in raw])
        answer.append(tuple(int(rotated[axis] + float(origin[axis])) for axis in range(3)))
    return answer


def _same(a: Any, b: Any, tolerance: float = 1e-6) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isfinite(float(a)) and math.isfinite(float(b)) and abs(float(a) - float(b)) <= tolerance
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y, tolerance) for x, y in zip(a, b))
    return a == b


def _finite_path(value: Any, minimum: int = 2) -> bool:
    return isinstance(value, list) and len(value) >= minimum and all(
        isinstance(point, list) and len(point) == 2 and all(isinstance(v, (int, float)) and math.isfinite(float(v)) for v in point)
        for point in value
    )


def _condition(truth: dict[str, Any], public: dict[str, Any]) -> str | None:
    if truth.get("control_condition") != public.get("control_condition"):
        raise ValueError("public interaction condition differs from the parcel contract")
    condition = truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "")
    if interaction not in {"full", "simplified"}:
        raise ValueError("invalid parcel interaction condition")
    return interaction


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    try:
        if not all(isinstance(value, dict) for value in (payload, truth, public)):
            return _fail("parcel submission is malformed")
        if any(payload.get(key) != truth.get(key) for key in ("mechanic_id", "task_id", "challenge_id")):
            return _fail("stale or mismatched parcel identity")
        if public.get("mechanic_id") != MECHANIC_ID or public.get("challenge_id") != truth.get("challenge_id"):
            return _fail("public parcel challenge is stale")
        interaction = _condition(truth, public)
        if payload.get("control_condition") != truth.get("control_condition"):
            return _fail("submitted parcel control contract mismatch")
        expected_camera_source = "direct_camera_drag" if interaction == "full" else "camera_proxy_button"
        expected_place_source = "piece_drag" if interaction == "full" else "placement_proxy"
        world = truth.get("world") or {}
        public_world = public.get("world") or {}
        if public_world != world:
            return _fail("visible parcel world differs from replay geometry")
        raw_pieces = world.get("pieces") or []
        pieces = {str(piece.get("id")): piece for piece in raw_pieces if isinstance(piece, dict)}
        if set(pieces) != set(PIECE_IDS):
            return _fail("parcel piece inventory is malformed")
        state: dict[str, dict[str, Any]] = {}
        for piece_id, piece in pieces.items():
            orientation = _matrix(piece.get("orientation"))
            origin = piece.get("origin")
            if orientation is None or _det(orientation) != 1 or not isinstance(origin, list) or len(origin) != 3:
                return _fail("initial piece transform is malformed")
            state[piece_id] = {"orientation": orientation, "origin": list(origin), "placed": bool(piece.get("placed")), "locked": bool(piece.get("locked"))}

        events = payload.get("events")
        if not isinstance(events, list) or not events or len(events) > 3000:
            return _fail("parcel transcript is missing or too long")
        selected: str | None = None
        camera_seen = False
        submitted = False
        sequence = 0

        def occupancy(exclude: str | None = None) -> dict[tuple[int, int, int], str]:
            occupied: dict[tuple[int, int, int], str] = {}
            for item_id, item in state.items():
                if item_id == exclude or not item["placed"]:
                    continue
                for cell in _cells(pieces[item_id], item["orientation"], item["origin"]):
                    occupied[cell] = item_id
            return occupied

        for event in events:
            sequence += 1
            if not isinstance(event, dict) or int(event.get("seq", -1)) != sequence:
                return _fail("parcel event sequence is malformed")
            event_type = str(event.get("type") or "")
            if event_type == "camera_orbit":
                if event.get("input_source") != expected_camera_source:
                    return _fail("camera orbit uses the wrong interaction surface")
                before = event.get("before") or {}
                after = event.get("after") or {}
                if not all(isinstance(item, (int, float)) and math.isfinite(float(item)) for item in (before.get("yaw"), before.get("pitch"), after.get("yaw"), after.get("pitch"))):
                    return _fail("camera orbit has invalid angles")
                if abs(float(before["yaw"])) > 360.1 or abs(float(after["yaw"])) > 720.1 or not 0.15 <= float(after["pitch"]) <= 0.9:
                    return _fail("camera orbit leaves the visible camera range")
                if interaction == "full":
                    if not _finite_path(event.get("path"), 2):
                        return _fail("direct camera orbit is missing its pointer path")
                elif event.get("direction") not in {"left", "right", "up", "down"}:
                    return _fail("proxy camera orbit has no direction")
                camera_seen = True
            elif event_type == "select_piece":
                if event.get("input_source") != "piece_click" or selected is not None:
                    return _fail("piece selection is invalid")
                piece_id = str(event.get("piece_id") or "")
                if piece_id not in state or state[piece_id]["locked"]:
                    return _fail("unknown or locked piece was selected")
                selected = piece_id
            elif event_type == "clear_selection":
                if event.get("input_source") != "piece_click" or selected is None:
                    return _fail("piece selection clear is invalid")
                selected = None
            elif event_type == "rotate_piece":
                if selected is None or event.get("input_source") != "axis_rotation_button" or str(event.get("piece_id")) != selected:
                    return _fail("rotation was not applied to the selected piece")
                axis = str(event.get("axis") or "")
                direction = int(event.get("direction", 0))
                rotation = ROTATIONS.get((axis, direction))
                if rotation is None:
                    return _fail("piece rotation axis or direction is invalid")
                before = _matrix(event.get("before_orientation"))
                after = _matrix(event.get("after_orientation"))
                if before is None or after is None or before != state[selected]["orientation"] or after != _mat_mul(rotation, before) or _det(after) != 1:
                    return _fail("piece rotation does not continue from the visible transform")
                state[selected]["orientation"] = after
            elif event_type == "place_piece":
                if selected is None or str(event.get("piece_id")) != selected or event.get("input_source") != expected_place_source:
                    return _fail("placement was not made through the selected interaction surface")
                piece_id = selected
                before_origin = event.get("before_origin")
                after_origin = event.get("after_origin")
                if not isinstance(before_origin, list) or not _same(before_origin, state[piece_id]["origin"]):
                    return _fail("placement starts from the wrong piece position")
                if not isinstance(after_origin, list) or len(after_origin) != 3 or any(not isinstance(value, (int, float)) or not math.isfinite(float(value)) or abs(float(value) - round(float(value))) > 1e-6 for value in after_origin):
                    return _fail("placement origin is not an integer lattice point")
                orientation = _matrix(event.get("orientation"))
                if orientation is None or orientation != state[piece_id]["orientation"]:
                    return _fail("placement orientation disagrees with replay")
                if interaction == "full":
                    if not _finite_path(event.get("path"), 2) or not _finite_path(event.get("drop_path"), 1):
                        return _fail("direct piece placement is missing its drag path")
                    if len(event.get("drop_path")) != 1:
                        return _fail("direct piece placement has malformed drop coordinates")
                elif not isinstance(event.get("proxy"), dict) or event["proxy"].get("surface") != "axis_cell_selectors":
                    return _fail("proxy placement is missing the visible cell selectors")
                origin = [int(round(float(value))) for value in after_origin]
                new_cells = _cells(pieces[piece_id], orientation, origin)
                if any(any(coordinate < 0 or coordinate >= 3 for coordinate in cell) for cell in new_cells):
                    return _fail("piece placement leaves the 3x3x3 parcel")
                occupied = occupancy(exclude=piece_id)
                if any(cell in occupied for cell in new_cells) or len(set(new_cells)) != len(new_cells):
                    return _fail("piece placement overlaps an occupied cell")
                state[piece_id]["origin"] = origin
                state[piece_id]["placed"] = True
            elif event_type == "submit":
                if event.get("input_source") != "certify_button":
                    return _fail("parcel certification uses an unknown control")
                submitted = True
                if payload.get("completed") is not True:
                    return _fail("parcel attempt was abandoned")
            else:
                return _fail(f"unknown parcel event type {event_type!r}")

        if selected is not None or not submitted or not camera_seen:
            return _fail("parcel transcript did not finish its visible interaction loop")
        occupied = occupancy()
        all_cells = set(occupied)
        expected = {(x, y, z) for x in range(3) for y in range(3) for z in range(3)}
        if set(state) != set(PIECE_IDS) or not all(item["placed"] for item in state.values()):
            return _fail("not every supplied polycube was placed")
        if len(occupied) != 27 or all_cells != expected:
            return _fail("the parcel is not covered exactly once")
        return {"graded": True, "passed": True, "score": 100, "feedback": "seven rigid polycubes replay to exact 3x3x3 occupancy"}
    except (KeyError, TypeError, ValueError, IndexError, OverflowError) as exc:
        return _fail(f"parcel replay error: {exc}")


def cheat(public: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    return {
        "mechanic_id": MECHANIC_ID,
        "challenge_id": truth.get("challenge_id"),
        "solution_placements": truth.get("solution_placements") or {},
        "preplaced_count": public.get("preplaced_count"),
    }
