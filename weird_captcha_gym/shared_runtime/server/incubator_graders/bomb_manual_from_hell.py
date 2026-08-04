from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "bomb_manual_from_hell"


def _failure(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _point(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    x, y = _number(value[0]), _number(value[1])
    return (x, y) if x is not None and y is not None else None


def _pose(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not isinstance(value.get("flipped"), bool):
        return None
    x, y = _number(value.get("x")), _number(value.get("y"))
    angle = _number(value.get("angle_deg"))
    if x is None or y is None or angle is None:
        return None
    return {"x": x, "y": y, "angle_deg": angle % 360, "flipped": bool(value["flipped"])}


def _same_pose(first: dict[str, Any], second: dict[str, Any], tolerance: float = .012) -> bool:
    angle_error = abs((float(first["angle_deg"]) - float(second["angle_deg"]) + 180) % 360 - 180)
    return (
        abs(float(first["x"]) - float(second["x"])) <= tolerance
        and abs(float(first["y"]) - float(second["y"])) <= tolerance
        and angle_error <= tolerance
        and bool(first["flipped"]) is bool(second["flipped"])
    )


def _transform(anchor: dict[str, Any], pose: dict[str, Any]) -> tuple[float, float]:
    x, y = float(anchor["x"]), float(anchor["y"])
    if bool(pose["flipped"]):
        x = -x
    angle = math.radians(float(pose["angle_deg"]))
    cosine, sine = math.cos(angle), math.sin(angle)
    return (
        float(pose["x"]) + x * cosine - y * sine,
        float(pose["y"]) + x * sine + y * cosine,
    )


def _max_anchor_error(plate: dict[str, Any], pose: dict[str, Any]) -> float:
    anchors = plate.get("anchors")
    pin_list = plate.get("pins")
    if (
        not isinstance(anchors, list)
        or not isinstance(pin_list, list)
        or not 2 <= len(anchors) <= 4
        or len(pin_list) != len(anchors)
    ):
        return math.inf
    pins = {str(pin.get("shape") or ""): pin for pin in pin_list if isinstance(pin, dict)}
    if len(pins) != len(pin_list) or "" in pins:
        return math.inf
    errors = []
    for anchor in anchors:
        if not isinstance(anchor, dict) or str(anchor.get("shape") or "") not in pins:
            return math.inf
        pin = pins[str(anchor["shape"])]
        try:
            x, y = _transform(anchor, pose)
            pin_x, pin_y = float(pin["x"]), float(pin["y"])
        except (KeyError, TypeError, ValueError):
            return math.inf
        if not all(math.isfinite(value) for value in (x, y, pin_x, pin_y)):
            return math.inf
        errors.append(math.hypot(x - pin_x, y - pin_y))
    return max(errors) if len(errors) == len(anchors) else math.inf


def _snap_translation(plate: dict[str, Any], pose: dict[str, Any]) -> dict[str, Any]:
    pins = {str(pin["shape"]): pin for pin in plate["pins"]}
    dx = dy = 0.0
    for anchor in plate["anchors"]:
        pin = pins[str(anchor["shape"])]
        x, y = _transform(anchor, pose)
        dx += float(pin["x"]) - x
        dy += float(pin["y"]) - y
    return {
        **pose,
        "x": float(pose["x"]) + dx / len(plate["anchors"]),
        "y": float(pose["y"]) + dy / len(plate["anchors"]),
    }


def _identity_error(
    payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]
) -> str | None:
    if {
        str(payload.get("mechanic_id") or ""),
        str(ground_truth.get("mechanic_id") or ""),
        str(public_state.get("mechanic_id") or ""),
    } != {MECHANIC_ID}:
        return "mechanic identity mismatch"
    challenge_ids = {
        str(payload.get("challenge_id") or ""),
        str(ground_truth.get("challenge_id") or ""),
        str(public_state.get("challenge_id") or ""),
    }
    if len(challenge_ids) != 1 or "" in challenge_ids:
        return "challenge identity mismatch"
    task_ids = {
        str(payload.get("task_id") or ""),
        str(ground_truth.get("task_id") or ""),
        str(public_state.get("task_id") or ""),
    }
    if len(task_ids) != 1 or "" in task_ids:
        return "task identity mismatch"
    return None


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    identity_error = _identity_error(payload, ground_truth, public_state)
    if identity_error:
        return _failure(identity_error)
    condition = ground_truth.get("control_condition")
    if public_state.get("control_condition") != condition:
        return _failure("public interaction condition differs from acetate contract")
    if condition is not None and not isinstance(condition, dict):
        return _failure("acetate interaction condition is malformed")
    interaction = str((condition or {}).get("interaction") or "")
    rotation_source = {"simplified": "binder_rotation_buttons", "full": "plate_right_click"}.get(interaction)
    flip_source = {"simplified": "binder_flip_button", "full": "plate_shift_right_click"}.get(interaction)
    lock_source = {"simplified": "seat_button", "full": "plate_drop"}.get(interaction)
    if condition is not None and None in {rotation_source, flip_source, lock_source}:
        return _failure("acetate interaction condition is invalid")
    plates = ground_truth.get("plates")
    wires = ground_truth.get("wires")
    requirements = ground_truth.get("requirements")
    stage = ground_truth.get("stage")
    expected_plate_count = _integer(requirements.get("plate_count")) if isinstance(requirements, dict) else None
    rotation_step = _integer(requirements.get("rotation_step_deg")) if isinstance(requirements, dict) else None
    snap_tolerance = _number(requirements.get("snap_tolerance_px")) if isinstance(requirements, dict) else None
    aperture_radius = _number(requirements.get("aperture_radius_px")) if isinstance(requirements, dict) else None
    if (
        not isinstance(plates, list)
        or expected_plate_count is None
        or not 2 <= expected_plate_count <= 6
        or len(plates) != expected_plate_count
        or not isinstance(wires, list)
        or not 5 <= len(wires) <= 11
        or not isinstance(requirements, dict)
        or not isinstance(stage, dict)
        or rotation_step not in {30, 45, 90}
        or snap_tolerance is None
        or not 12 <= snap_tolerance <= 40
        or aperture_radius is None
        or not 12 <= aperture_radius <= 30
    ):
        return _failure("hidden acetate contract is malformed")
    if public_state.get("plates") != plates or public_state.get("wires") != wires or public_state.get("requirements") != requirements or public_state.get("stage") != stage:
        return _failure("public acetate commitment disagrees with hidden state")
    plate_map = {str(plate.get("id") or ""): plate for plate in plates if isinstance(plate, dict)}
    wire_map = {str(wire.get("id") or ""): wire for wire in wires if isinstance(wire, dict)}
    if len(plate_map) != expected_plate_count or len(wire_map) != len(wires) or "" in plate_map or "" in wire_map:
        return _failure("hidden plate or wire bank is malformed")
    if any(
        _integer(wire.get("slot")) != index
        or _number(wire.get("y")) is None
        or not 57 <= float(wire["y"]) <= 429
        for index, wire in enumerate(wires)
    ):
        return _failure("hidden wire geometry is malformed")
    target_poses_raw = ground_truth.get("target_poses")
    if not isinstance(target_poses_raw, dict):
        return _failure("hidden plate registration is missing")
    target_poses = {plate_id: _pose(target_poses_raw.get(plate_id)) for plate_id in plate_map}
    if any(item is None for item in target_poses.values()):
        return _failure("hidden plate registration is malformed")
    correct_wire_id = str(ground_truth.get("correct_wire_id") or "")
    if correct_wire_id not in wire_map:
        return _failure("hidden defusal wire is missing")
    anchor_counts: set[int] = set()
    aperture_counts: set[int] = set()
    for plate in plate_map.values():
        anchors, pins, apertures = plate.get("anchors"), plate.get("pins"), plate.get("apertures")
        if (
            not isinstance(anchors, list)
            or not isinstance(pins, list)
            or not isinstance(apertures, list)
            or not 2 <= len(anchors) <= 4
            or len(pins) != len(anchors)
            or not 2 <= len(apertures) < len(wires)
            or len({str(item.get("shape") or "") for item in anchors if isinstance(item, dict)}) != len(anchors)
            or len({str(item.get("shape") or "") for item in pins if isinstance(item, dict)}) != len(pins)
        ):
            return _failure("acetate plate geometry is malformed")
        aperture_ids = [str(item.get("wire_id") or "") for item in apertures if isinstance(item, dict)]
        if len(aperture_ids) != len(apertures) or len(set(aperture_ids)) != len(apertures) or any(item not in wire_map for item in aperture_ids):
            return _failure("acetate aperture manifest is malformed")
        anchor_counts.add(len(anchors))
        aperture_counts.add(len(apertures))
    if len(anchor_counts) != 1 or len(aperture_counts) != 1:
        return _failure("acetate plate profiles are inconsistent")
    first_apertures = plate_map[next(iter(plate_map))]["apertures"]
    aperture_intersection = {str(item.get("wire_id") or "") for item in first_apertures if isinstance(item, dict)}
    for plate in list(plate_map.values())[1:]:
        aperture_intersection &= {str(item.get("wire_id") or "") for item in plate.get("apertures") or [] if isinstance(item, dict)}
    if aperture_intersection != {correct_wire_id}:
        return _failure("acetate apertures do not resolve a unique wire")
    for plate_id, target_pose in target_poses.items():
        assert target_pose is not None
        if _max_anchor_error(plate_map[plate_id], target_pose) > .01:
            return _failure("hidden plate pins disagree with its registration pose")
    initial_poses = {plate_id: _pose(plate.get("initial_pose")) for plate_id, plate in plate_map.items()}
    if any(item is None for item in initial_poses.values()):
        return _failure("plate has no valid initial pose")
    if condition is not None:
        parameters = condition.get("difficulty_parameters")
        if not isinstance(parameters, dict):
            return _failure("acetate difficulty parameters are malformed")
        structural_expectations = {
            "plate_count": len(plates),
            "wire_count": len(wires),
            "apertures_per_plate": next(iter(aperture_counts)),
            "anchor_count": next(iter(anchor_counts)),
            "rotation_step_deg": rotation_step,
            "snap_tolerance_px": snap_tolerance,
            "aperture_radius_px": aperture_radius,
        }
        for field, actual in structural_expectations.items():
            if parameters.get(field) != actual:
                return _failure(f"acetate difficulty parameter {field} disagrees with generated geometry")
        reflection_setting = parameters.get("reflection_mismatch_count")
        reflection_mismatches = sum(
            bool(initial_poses[plate_id]["flipped"]) is not bool(target_poses[plate_id]["flipped"])
            for plate_id in plate_map
        )
        if reflection_setting != "legacy_random" and _integer(reflection_setting) != reflection_mismatches:
            return _failure("acetate reflection profile disagrees with generated transforms")
        minimum_offset = _integer(parameters.get("rotation_offset_steps_min"))
        maximum_offset = _integer(parameters.get("rotation_offset_steps_max"))
        if minimum_offset is None or maximum_offset is None:
            return _failure("acetate rotation-offset profile is malformed")
        for plate_id in plate_map:
            initial_pose = initial_poses[plate_id]
            target_pose = target_poses[plate_id]
            assert initial_pose is not None and target_pose is not None
            clockwise_steps = int(round((target_pose["angle_deg"] - initial_pose["angle_deg"]) % 360 / rotation_step))
            if not minimum_offset <= clockwise_steps <= maximum_offset:
                return _failure("acetate rotation-offset profile disagrees with generated transforms")

    poses: dict[str, dict[str, Any]] = {}
    for plate_id, initial in initial_poses.items():
        assert initial is not None
        poses[plate_id] = initial
    locked: set[str] = set()
    selected_plate = str(plates[0]["id"])
    selected_wire: str | None = None
    active_drag: dict[str, Any] | None = None
    misseats = 0
    cut_count = 0
    previous_t = -1.0
    events = payload.get("events")
    if not isinstance(events, list) or len(events) > 2_500:
        return _failure("acetate interaction transcript is missing or oversized")

    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict) or _integer(event.get("seq")) != index:
            return _failure("acetate event sequence is malformed")
        event_t = _number(event.get("t_ms"))
        if event_t is None or event_t < previous_t or event_t > 3_600_000:
            return _failure("acetate event timestamps are invalid")
        previous_t = event_t
        event_type = str(event.get("type") or "")

        if event_type == "plate_select":
            if active_drag is not None:
                return _failure("plate changed during a drag")
            plate_id = str(event.get("plate_id") or "")
            if plate_id not in plate_map:
                return _failure("unknown acetate plate selected")
            selected_plate = plate_id
            continue

        if event_type == "drag_start":
            if condition is not None and event.get("input_source") != "plate_drag":
                return _failure("plate drag uses the wrong interaction input")
            if active_drag is not None or selected_plate in locked:
                return _failure("plate drag began from an invalid state")
            plate_id = str(event.get("plate_id") or "")
            point = _point(event.get("point"))
            claimed_pose = _pose(event.get("pose"))
            if plate_id != selected_plate or point is None or claimed_pose is None or not _same_pose(claimed_pose, poses[plate_id]):
                return _failure("plate drag origin does not match replay")
            active_drag = {
                "plate_id": plate_id,
                "start": point,
                "last": point,
                "origin": (poses[plate_id]["x"], poses[plate_id]["y"]),
            }
            continue

        if event_type == "drag_sample":
            if condition is not None and event.get("input_source") != "plate_drag":
                return _failure("plate drag uses the wrong interaction input")
            if active_drag is None or str(event.get("plate_id") or "") != active_drag["plate_id"]:
                return _failure("plate drag sample has no matching drag")
            point = _point(event.get("point"))
            claimed_pose = _pose(event.get("pose"))
            if point is None or claimed_pose is None:
                return _failure("plate drag sample is malformed")
            active_drag["last"] = point
            pose = poses[active_drag["plate_id"]]
            pose["x"] = max(110, min(840, active_drag["origin"][0] + point[0] - active_drag["start"][0]))
            pose["y"] = max(70, min(430, active_drag["origin"][1] + point[1] - active_drag["start"][1]))
            if not _same_pose(claimed_pose, pose):
                return _failure("reported plate drag pose disagrees with pointer replay")
            continue

        if event_type == "drag_end":
            if condition is not None and event.get("input_source") != "plate_drag":
                return _failure("plate drag uses the wrong interaction input")
            if active_drag is None or str(event.get("plate_id") or "") != active_drag["plate_id"]:
                return _failure("plate drag ended without starting")
            point = _point(event.get("point"))
            claimed_pose = _pose(event.get("pose"))
            if point is None or claimed_pose is None:
                return _failure("plate drag end pose is malformed")
            pose = poses[active_drag["plate_id"]]
            pose["x"] = max(110, min(840, active_drag["origin"][0] + point[0] - active_drag["start"][0]))
            pose["y"] = max(70, min(430, active_drag["origin"][1] + point[1] - active_drag["start"][1]))
            if not _same_pose(claimed_pose, pose):
                return _failure("plate drag end pose disagrees with replay")
            active_drag = None
            continue

        if event_type == "plate_rotate":
            if rotation_source is not None and event.get("input_source") != rotation_source:
                return _failure("plate rotation uses the wrong interaction input")
            plate_id = str(event.get("plate_id") or "")
            if active_drag is not None or plate_id != selected_plate or plate_id in locked:
                return _failure("plate rotation occurred from an invalid state")
            delta = _number(event.get("delta_deg"))
            before = _number(event.get("from_deg"))
            after = _number(event.get("to_deg"))
            step = float(rotation_step)
            if delta not in {-step, step} or before is None or after is None or abs((before - poses[plate_id]["angle_deg"] + 180) % 360 - 180) > .001:
                return _failure("plate rotation origin or step is invalid")
            poses[plate_id]["angle_deg"] = (poses[plate_id]["angle_deg"] + delta) % 360
            if abs((after - poses[plate_id]["angle_deg"] + 180) % 360 - 180) > .001:
                return _failure("plate rotation destination disagrees with replay")
            continue

        if event_type == "plate_flip":
            if flip_source is not None and event.get("input_source") != flip_source:
                return _failure("plate flip uses the wrong interaction input")
            plate_id = str(event.get("plate_id") or "")
            if active_drag is not None or plate_id != selected_plate or plate_id in locked:
                return _failure("plate flip occurred from an invalid state")
            if not isinstance(event.get("from_flipped"), bool) or not isinstance(event.get("to_flipped"), bool):
                return _failure("plate flip state is malformed")
            if bool(event["from_flipped"]) is not poses[plate_id]["flipped"] or bool(event["to_flipped"]) is poses[plate_id]["flipped"]:
                return _failure("plate flip disagrees with replay")
            poses[plate_id]["flipped"] = not poses[plate_id]["flipped"]
            continue

        if event_type == "plate_reset":
            if condition is not None and event.get("input_source") != "binder_return":
                return _failure("plate reset uses the wrong interaction input")
            plate_id = str(event.get("plate_id") or "")
            if active_drag is not None or plate_id != selected_plate or plate_id in locked:
                return _failure("plate reset occurred from an invalid state")
            before, after = _pose(event.get("before_pose")), _pose(event.get("after_pose"))
            initial = _pose(plate_map[plate_id]["initial_pose"])
            if before is None or after is None or initial is None or not _same_pose(before, poses[plate_id]) or not _same_pose(after, initial):
                return _failure("plate reset does not restore the binder pose")
            poses[plate_id] = initial
            continue

        if event_type == "plate_lock":
            if lock_source is not None and event.get("input_source") != lock_source:
                return _failure("plate lock uses the wrong interaction input")
            plate_id = str(event.get("plate_id") or "")
            if active_drag is not None or plate_id != selected_plate or plate_id in locked:
                return _failure("plate lock occurred from an invalid state")
            before, after = _pose(event.get("before_pose")), _pose(event.get("after_pose"))
            if before is None or after is None or not _same_pose(before, poses[plate_id]):
                return _failure("plate lock origin disagrees with replay")
            error = _max_anchor_error(plate_map[plate_id], poses[plate_id])
            accepted = error <= float(snap_tolerance)
            claimed_error = _number(event.get("max_error"))
            if bool(event.get("accepted")) != accepted or claimed_error is None or abs(claimed_error - round(error, 3)) > .012:
                return _failure("plate lock verdict disagrees with keyhole geometry")
            if accepted:
                poses[plate_id] = _snap_translation(plate_map[plate_id], poses[plate_id])
                target_pose = target_poses[plate_id]
                assert target_pose is not None
                if not _same_pose(poses[plate_id], target_pose, .02):
                    return _failure("accepted plate does not resolve to the hidden registration")
                locked.add(plate_id)
            else:
                misseats += 1
            if not _same_pose(after, poses[plate_id], .02):
                return _failure("plate post-lock pose disagrees with replay")
            continue

        if event_type == "wire_select":
            if condition is not None and event.get("input_source") != "wire_canvas":
                return _failure("wire selection uses the wrong interaction input")
            if active_drag is not None or len(locked) != len(plate_map):
                return _failure("wire selected before all acetate plates were seated")
            point = _point(event.get("point"))
            wire_id = str(event.get("wire_id") or "")
            if point is None or wire_id not in wire_map or not (82 <= point[0] <= 660):
                return _failure("wire selection is malformed")
            candidates = sorted(
                (
                    (abs(point[1] - float(wire["y"])), wire_index, str(wire["id"]))
                    for wire_index, wire in enumerate(wires)
                    if abs(point[1] - float(wire["y"])) <= 18
                ),
                key=lambda item: (item[0], item[1]),
            )
            if not candidates or candidates[0][2] != wire_id:
                return _failure("selected wire does not match the physical pointer location")
            selected_wire = wire_id
            continue

        if event_type == "cut":
            if condition is not None and event.get("input_source") != "cut_button":
                return _failure("wire cut uses the wrong interaction input")
            if len(locked) != len(plate_map) or selected_wire is None:
                return _failure("cut occurred before the acetate procedure was complete")
            cut_count += 1
            if str(event.get("wire_id") or "") != selected_wire or _integer(event.get("cut_count")) != cut_count:
                return _failure("cut record disagrees with the selected wire")
            continue

        return _failure(f"unknown acetate event {event_type!r}")

    if active_drag is not None:
        return _failure("submission interrupted an active plate drag")
    claimed_poses = payload.get("plate_poses")
    if not isinstance(claimed_poses, dict) or set(claimed_poses) != set(poses):
        return _failure("submitted plate pose map is malformed")
    for plate_id, pose in poses.items():
        claimed = _pose(claimed_poses.get(plate_id))
        if claimed is None or not _same_pose(claimed, pose, .02):
            return _failure("submitted plate poses do not match replay")
    if [str(item) for item in payload.get("locked_plate_ids") or []] != sorted(locked):
        return _failure("submitted seated-plate list does not match replay")
    if (str(payload.get("selected_wire_id") or "") or None) != selected_wire:
        return _failure("submitted wire selection does not match replay")
    if _integer(payload.get("cut_count")) != cut_count or _integer(payload.get("misseat_count")) != misseats:
        return _failure("submitted failure or cut counters do not match replay")
    passed = (
        payload.get("completed") is True
        and len(locked) == len(plate_map)
        and selected_wire == correct_wire_id
        and cut_count == 1
    )
    return {
        "graded": True,
        "passed": passed,
        "score": 100 if passed else 0,
        "feedback": (
            f"replayed {len(events)} acetate events; plates {len(locked)}/{len(plate_map)}; "
            f"misseats {misseats}; cut {selected_wire or 'none'}"
        ),
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {
        "target_poses": ground_truth.get("target_poses") or {},
        "correct_wire_id": ground_truth.get("correct_wire_id"),
        "correct_wire_index": ground_truth.get("correct_wire_index"),
    }
