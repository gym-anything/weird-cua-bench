from __future__ import annotations

import copy
import math
from typing import Any


MECHANIC_ID = "four_pane_pilgrimage"


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _close(a: float, b: float, tolerance: float = 1e-3) -> bool:
    return abs(float(a) - float(b)) <= tolerance


def _point_close(actual: Any, expected: list[float], tolerance: float = 1e-3) -> bool:
    return (
        isinstance(actual, list)
        and len(actual) == 2
        and all(_finite(value) for value in actual)
        and _close(float(actual[0]), expected[0], tolerance)
        and _close(float(actual[1]), expected[1], tolerance)
    )


def _unit_point(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(_finite(item) and 0.0 <= float(item) <= 1.0 for item in value)
    )


def _trace_valid(value: Any, minimum_travel: float = 0.04) -> bool:
    if not isinstance(value, list) or not 2 <= len(value) <= 32 or not all(_unit_point(point) for point in value):
        return False
    travel = sum(
        math.hypot(float(b[0]) - float(a[0]), float(b[1]) - float(a[1]))
        for a, b in zip(value, value[1:])
    )
    return travel >= minimum_travel


def _slot_header_contains(point: Any, slot: int) -> bool:
    if not _unit_point(point) or slot not in range(4):
        return False
    column = slot % 2
    row = slot // 2
    x, y = map(float, point)
    return column * .5 <= x <= (column + 1) * .5 and row * .5 <= y <= row * .5 + .09


def _button_proof(event: dict[str, Any], control: str, **fields: Any) -> bool:
    proof = event.get("interaction_proof")
    if not isinstance(proof, dict) or proof.get("type") != "button" or proof.get("control") != control:
        return False
    return all(proof.get(key) == value for key, value in fields.items())


def _direct_proof(event: dict[str, Any], proof_type: str) -> dict[str, Any] | None:
    proof = event.get("interaction_proof")
    if not isinstance(proof, dict) or proof.get("type") != proof_type:
        return None
    return proof


def _apply(point: list[float], transform: dict[str, float]) -> list[float]:
    return [
        (float(point[0]) - 150.0) * transform["zoom"] + 150.0 + transform["pan_x"],
        (float(point[1]) - 100.0) * transform["zoom"] + 100.0 + transform["pan_y"],
    ]


def _join_error(
    panel: dict[str, Any],
    join: dict[str, Any],
    transform: dict[str, float],
    *,
    source: bool,
) -> float:
    indices = join["source_indices" if source else "target_indices"]
    targets = join["source_targets" if source else "target_targets"]
    squares: list[float] = []
    for index, target in zip(indices, targets):
        actual = _apply(panel["path_points"][int(index)], transform)
        squares.append((actual[0] - float(target[0])) ** 2 + (actual[1] - float(target[1])) ** 2)
    return 2.0 * math.sqrt(sum(squares) / max(1, len(squares)))


def _interaction(public_state: dict[str, Any]) -> str:
    condition = public_state.get("control_condition") or {}
    mode = str(condition.get("interaction") or "full")
    return mode if mode in {"simplified", "full"} else "full"


def _initial(public_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "slots": list(public_state["initial_slots"]),
        "transforms": copy.deepcopy(public_state["initial_transforms"]),
        "plates": {
            str(plate["id"]): {"status": "bound", "target_panel_id": None, "pose": None}
            for plate in public_state.get("plates") or []
        },
        "stage": 0,
    }


def _eligible(state: dict[str, Any], public_state: dict[str, Any]) -> tuple[bool, dict[str, float]]:
    stage = int(state["stage"])
    joins = public_state.get("joins") or []
    if stage >= len(joins):
        return False, {"source": 0.0, "target": 0.0}
    join = joins[stage]
    source_panel_id = str(join["source_panel_id"])
    target_panel_id = str(join["target_panel_id"])
    if state["slots"][int(join["source_slot"])] != source_panel_id:
        return False, {"source": math.inf, "target": math.inf}
    if state["slots"][int(join["target_slot"])] != target_panel_id:
        return False, {"source": math.inf, "target": math.inf}
    panel_by_id = {str(panel["id"]): panel for panel in public_state["panels"]}
    source_error = _join_error(
        panel_by_id[source_panel_id], join, state["transforms"][source_panel_id], source=True
    )
    target_error = _join_error(
        panel_by_id[target_panel_id], join, state["transforms"][target_panel_id], source=False
    )
    tolerance = float(public_state["limits"]["alignment_tolerance_units"])
    plate_id = join.get("required_plate_id")
    plate_ready = True
    if plate_id:
        plate_state = state["plates"].get(str(plate_id)) or {}
        plate = next(
            (item for item in public_state.get("plates") or [] if str(item["id"]) == str(plate_id)),
            None,
        )
        plate_ready = (
            plate is not None
            and
            plate_state.get("status") == "stacked"
            and plate_state.get("target_panel_id") == target_panel_id
            and _point_close(
                plate_state.get("pose"),
                [float(value) for value in plate["target_pose"]],
                float(public_state["limits"]["plate_drop_tolerance_units"]),
            )
        )
    return source_error <= tolerance and target_error <= tolerance and plate_ready, {
        "source": round(source_error, 4),
        "target": round(target_error, 4),
    }


def _expected_source(mode: str) -> str:
    return "proxy_controls" if mode == "simplified" else "direct_manipulation"


def _check_source(event: dict[str, Any], mode: str) -> bool:
    return str(event.get("input_source") or "") == _expected_source(mode)


def _fail(message: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
    suffix = ""
    if state is not None:
        suffix = f"; crossings {int(state.get('stage', 0))}/3"
    return {"graded": True, "passed": False, "feedback": f"{message}{suffix}"}


def _check_final_state(payload_state: Any, replay: dict[str, Any]) -> bool:
    if not isinstance(payload_state, dict):
        return False
    if payload_state.get("slots") != replay["slots"] or int(payload_state.get("stage", -1)) != replay["stage"]:
        return False
    payload_transforms = payload_state.get("transforms")
    if not isinstance(payload_transforms, dict) or set(payload_transforms) != set(replay["transforms"]):
        return False
    for panel_id, expected in replay["transforms"].items():
        actual = payload_transforms.get(panel_id)
        if not isinstance(actual, dict):
            return False
        for key in ("zoom", "pan_x", "pan_y"):
            if not _finite(actual.get(key)) or not _close(float(actual[key]), float(expected[key]), 0.02):
                return False
    payload_targets = payload_state.get("plate_targets")
    expected_targets = {
        plate_id: plate["target_panel_id"]
        for plate_id, plate in replay["plates"].items()
        if plate["status"] == "stacked"
    }
    if payload_targets != expected_targets:
        return False
    payload_poses = payload_state.get("plate_poses")
    expected_poses = {
        plate_id: plate["pose"]
        for plate_id, plate in replay["plates"].items()
        if plate["status"] == "stacked"
    }
    if not isinstance(payload_poses, dict) or set(payload_poses) != set(expected_poses):
        return False
    return all(_point_close(payload_poses[plate_id], pose, .02) for plate_id, pose in expected_poses.items())


def grade(
    result: dict[str, Any],
    ground_truth: dict[str, Any],
    public_state: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(result, dict) or not isinstance(ground_truth, dict) or not isinstance(public_state, dict):
        return _fail("invalid pilgrimage payload")
    if str(result.get("mechanic_id") or "") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if not challenge_id or str(result.get("challenge_id") or "") != challenge_id:
        return _fail("stale challenge")
    if str(result.get("task_id") or "") != str(ground_truth.get("task_id") or ""):
        return _fail("task mismatch")
    if str(result.get("interaction_mode") or "") != _interaction(public_state):
        return _fail("interaction mode mismatch")

    events = result.get("events")
    if not isinstance(events, list) or not events or len(events) > 1200:
        return _fail("missing or excessive pilgrimage transcript")
    state = _initial(public_state)
    initial = copy.deepcopy(state)
    panels = {str(panel["id"]): panel for panel in public_state.get("panels") or []}
    plates = {str(plate["id"]): plate for plate in public_state.get("plates") or []}
    limits = public_state.get("limits") or {}
    mode = _interaction(public_state)
    zoom_min = float(limits["zoom_min"])
    zoom_max = float(limits["zoom_max"])
    zoom_step = float(limits["zoom_step"])
    pan_limit = float(limits["pan_limit"])
    pan_step = float(limits["pan_step"])
    submit_seen = False

    for event_index, event in enumerate(events):
        if not isinstance(event, dict) or event.get("sequence") != event_index + 1:
            return _fail("event sequence mismatch", state)
        kind = str(event.get("kind") or "")
        if submit_seen:
            return _fail("events follow terminal submission", state)

        if kind == "panel_move":
            if not _check_source(event, mode):
                return _fail("wrong interaction surface for pane move", state)
            panel_id = str(event.get("panel_id") or "")
            try:
                from_slot = int(event.get("from_slot"))
                to_slot = int(event.get("to_slot"))
            except (TypeError, ValueError):
                return _fail("invalid pane slots", state)
            if panel_id not in panels or from_slot not in range(4) or to_slot not in range(4) or from_slot == to_slot:
                return _fail("invalid pane move", state)
            if state["slots"][from_slot] != panel_id:
                return _fail("pane move does not start from replayed slot", state)
            displaced = state["slots"][to_slot]
            if str(event.get("displaced_panel_id") or "") != displaced:
                return _fail("pane swap identity mismatch", state)
            if mode == "simplified":
                if not _button_proof(
                    event,
                    "move_slot",
                    selected_panel_id=panel_id,
                    value=to_slot,
                ):
                    return _fail("pane move lacks its visible slot-button proof", state)
            else:
                proof = _direct_proof(event, "header_drag")
                if (
                    proof is None
                    or proof.get("start_slot") != from_slot
                    or proof.get("end_slot") != to_slot
                    or not _slot_header_contains(proof.get("start_board"), from_slot)
                    or not _slot_header_contains(proof.get("end_board"), to_slot)
                    or not _trace_valid(proof.get("trace"), .08)
                ):
                    return _fail("pane move lacks a valid header drag", state)
            state["slots"][from_slot], state["slots"][to_slot] = displaced, panel_id

        elif kind == "pan":
            if not _check_source(event, mode):
                return _fail("wrong interaction surface for pan", state)
            panel_id = str(event.get("panel_id") or "")
            if panel_id not in panels:
                return _fail("unknown panned pane", state)
            before = event.get("before")
            after = event.get("after")
            current = state["transforms"][panel_id]
            if not _point_close(before, [current["pan_x"], current["pan_y"]], 0.02):
                return _fail("pan does not continue from replayed transform", state)
            if not isinstance(after, list) or len(after) != 2 or not all(_finite(value) for value in after):
                return _fail("invalid pan endpoint", state)
            next_pan = [float(after[0]), float(after[1])]
            if any(abs(value) > pan_limit + 1e-6 for value in next_pan):
                return _fail("pan exceeds visible travel", state)
            if mode == "simplified":
                dx = abs(next_pan[0] - current["pan_x"])
                dy = abs(next_pan[1] - current["pan_y"])
                if not ((dx <= pan_step + 1e-3 and dy <= 1e-3) or (dy <= pan_step + 1e-3 and dx <= 1e-3)):
                    return _fail("proxy pan exceeds one visible control step", state)
                proof = event.get("interaction_proof")
                vector = proof.get("vector") if isinstance(proof, dict) else None
                if vector not in ([1, 0], [-1, 0], [0, 1], [0, -1]) or not _button_proof(event, "pan", selected_panel_id=panel_id, vector=vector):
                    return _fail("pan lacks its visible direction-button proof", state)
                expected = [
                    max(-pan_limit, min(pan_limit, current["pan_x"] + vector[0] * pan_step)),
                    max(-pan_limit, min(pan_limit, current["pan_y"] + vector[1] * pan_step)),
                ]
                if not _point_close(next_pan, expected, .02):
                    return _fail("proxy pan endpoint disagrees with its button", state)
            else:
                proof = _direct_proof(event, "canvas_drag")
                if proof is None or not _unit_point(proof.get("start")) or not _unit_point(proof.get("end")) or not _trace_valid(proof.get("trace"), .012):
                    return _fail("pan lacks a valid in-pane pointer trace", state)
                start, end = proof["start"], proof["end"]
                expected = [
                    max(-pan_limit, min(pan_limit, current["pan_x"] + (float(end[0]) - float(start[0])) * 300.0)),
                    max(-pan_limit, min(pan_limit, current["pan_y"] + (float(end[1]) - float(start[1])) * 200.0)),
                ]
                if not _point_close(next_pan, expected, 1.25):
                    return _fail("pan endpoint disagrees with the pointer trace", state)
            current["pan_x"], current["pan_y"] = next_pan

        elif kind == "zoom":
            if not _check_source(event, mode):
                return _fail("wrong interaction surface for zoom", state)
            panel_id = str(event.get("panel_id") or "")
            before = event.get("before")
            after = event.get("after")
            if panel_id not in panels or not _finite(before) or not _finite(after):
                return _fail("invalid zoom event", state)
            current = state["transforms"][panel_id]
            if not _close(float(before), current["zoom"], 0.002):
                return _fail("zoom does not continue from replayed transform", state)
            next_zoom = float(after)
            if next_zoom < zoom_min - 1e-6 or next_zoom > zoom_max + 1e-6:
                return _fail("zoom exceeds visible range", state)
            if abs(next_zoom - current["zoom"]) > zoom_step + 0.002:
                return _fail("zoom skips a control detent", state)
            direction = 1 if next_zoom > current["zoom"] else -1
            if mode == "simplified":
                if not _button_proof(
                    event,
                    "zoom",
                    selected_panel_id=panel_id,
                    direction=direction,
                ):
                    return _fail("zoom lacks its visible button proof", state)
            else:
                proof = _direct_proof(event, "wheel")
                delta_y = proof.get("delta_y") if proof else None
                if (
                    proof is None
                    or not _unit_point(proof.get("point"))
                    or not _finite(delta_y)
                    or float(delta_y) == 0
                    or direction != (-1 if float(delta_y) > 0 else 1)
                ):
                    return _fail("zoom lacks valid wheel evidence", state)
            current["zoom"] = round(next_zoom, 3)

        elif kind == "plate_peel":
            if not _check_source(event, mode):
                return _fail("wrong interaction surface for plate peel", state)
            plate_id = str(event.get("plate_id") or "")
            plate = plates.get(plate_id)
            if plate is None or int(plate["unlock_stage"]) > state["stage"]:
                return _fail("aperture was not visible yet", state)
            if str(event.get("source_panel_id") or "") != str(plate["source_panel_id"]):
                return _fail("aperture peeled from wrong pane", state)
            plate_state = state["plates"][plate_id]
            if plate_state["status"] != "bound":
                return _fail("aperture peeled more than once", state)
            if mode == "simplified":
                if not _button_proof(event, "peel", plate_id=plate_id):
                    return _fail("peel lacks its visible button proof", state)
            else:
                proof = _direct_proof(event, "plate_drag")
                if (
                    proof is None
                    or proof.get("start_region") != "bound_fragment"
                    or proof.get("end_region") != "tray"
                    or not _unit_point(proof.get("start_local"))
                    or not _unit_point(proof.get("end_local"))
                    or not _trace_valid(proof.get("trace"), .08)
                ):
                    return _fail("peel lacks a source-to-tray drag", state)
            plate_state["status"] = "peeled"
            plate_state["pose"] = None

        elif kind == "plate_stack":
            if not _check_source(event, mode):
                return _fail("wrong interaction surface for plate stack", state)
            plate_id = str(event.get("plate_id") or "")
            target_panel_id = str(event.get("target_panel_id") or "")
            if plate_id not in plates or target_panel_id not in panels:
                return _fail("unknown aperture stack target", state)
            plate_state = state["plates"][plate_id]
            if plate_state["status"] not in {"peeled", "stacked"}:
                return _fail("bound aperture cannot be stacked", state)
            pose = event.get("pose")
            if not isinstance(pose, list) or len(pose) != 2 or not all(_finite(value) for value in pose):
                return _fail("aperture stack omits its drop pose", state)
            pose = [float(pose[0]), float(pose[1])]
            if not 0 <= pose[0] <= 300 or not 0 <= pose[1] <= 200:
                return _fail("aperture stack pose leaves the pane", state)
            if mode == "simplified":
                current_join = (public_state.get("joins") or [])[state["stage"]] if state["stage"] < len(public_state.get("joins") or []) else None
                if not _button_proof(
                    event,
                    "stack",
                    plate_id=plate_id,
                    target_panel_id=target_panel_id,
                ) or not current_join or not current_join.get("required_plate_id") or target_panel_id != str(current_join["target_panel_id"]) or not _point_close(pose, [float(value) for value in current_join["target_pose"]], .02):
                    return _fail("stack lacks its target-button placement proof", state)
            else:
                proof = _direct_proof(event, "plate_drag")
                current_join = (public_state.get("joins") or [])[state["stage"]] if state["stage"] < len(public_state.get("joins") or []) else None
                expected_target = str((current_join or {}).get("target_panel_id") or "")
                expected_plate = str((current_join or {}).get("required_plate_id") or "")
                target_pose = (current_join or {}).get("target_pose")
                if (
                    proof is None
                    or proof.get("start_region") != "tray_fragment"
                    or proof.get("end_region") != "aperture"
                    or str(proof.get("target_plate_id") or "") != expected_plate
                    or target_panel_id != expected_target
                    or not _unit_point(proof.get("start_local"))
                    or not _unit_point(proof.get("end_local"))
                    or not _trace_valid(proof.get("trace"), .08)
                    or not isinstance(target_pose, list)
                    or not _point_close(pose, [float(value) for value in target_pose], 46.0)
                ):
                    return _fail("stack lacks a tray-to-aperture drop", state)
            plate_state["status"] = "stacked"
            plate_state["target_panel_id"] = target_panel_id
            plate_state["pose"] = [round(value, 3) for value in pose]

        elif kind == "crossing":
            eligible, errors = _eligible(state, public_state)
            stage = state["stage"]
            if not eligible or event.get("stage") != stage:
                return _fail("claimed crossing does not match replayed border geometry", state)
            join = public_state["joins"][stage]
            if (
                str(event.get("source_panel_id") or "") != str(join["source_panel_id"])
                or str(event.get("target_panel_id") or "") != str(join["target_panel_id"])
            ):
                return _fail("crossing pane identity mismatch", state)
            reported = event.get("alignment_error")
            if not isinstance(reported, dict):
                return _fail("crossing omits visible continuity error", state)
            if not _close(float(reported.get("source", math.inf)), errors["source"], 0.05) or not _close(
                float(reported.get("target", math.inf)), errors["target"], 0.05
            ):
                return _fail("crossing continuity measurement mismatch", state)
            state["stage"] += 1

        elif kind == "reset":
            if str(event.get("input_source") or "") != "shared_control":
                return _fail("reset input source mismatch", state)
            state = copy.deepcopy(initial)

        elif kind == "submit":
            if str(event.get("input_source") or "") != "shared_control":
                return _fail("submission input source mismatch", state)
            submit_seen = True

        else:
            return _fail(f"unknown pilgrimage event {kind!r}", state)

    if not submit_seen:
        return _fail("pilgrimage was not sealed", state)
    if state["stage"] != len(public_state.get("joins") or []):
        return _fail("the pilgrim has not reached the shrine", state)
    if result.get("completed") is not True:
        return _fail("terminal completion flag is false", state)
    if not _check_final_state(result.get("final_state"), state):
        return _fail("reported final pane state disagrees with replay", state)
    return {
        "graded": True,
        "passed": True,
        "feedback": "pilgrimage replayed: 3/3 borders continuous, required aperture stacks valid, shrine reached",
        "crossings": 3,
    }
