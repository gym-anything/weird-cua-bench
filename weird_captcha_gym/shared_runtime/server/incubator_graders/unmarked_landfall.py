from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "unmarked_landfall"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} is not finite")
    return result


def _point(value: Any, width: float, height: float, label: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} is malformed")
    x = _number(value[0], f"{label} x")
    y = _number(value[1], f"{label} y")
    if not 0 <= x <= width or not 0 <= y <= height:
        raise ValueError(f"{label} leaves its visible surface")
    return x, y


def _norm(angle: float) -> float:
    return angle % 360.0


def _angle_delta(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _clamp_pan(
    pan: tuple[float, float], zoom: float, width: float, height: float
) -> tuple[float, float]:
    return (
        _clamp(pan[0], width * (1.0 - zoom), 0.0),
        _clamp(pan[1], height * (1.0 - zoom), 0.0),
    )


def _arrow_point(
    bearing: float,
    yaw: float,
    width: float,
    height: float,
    field_of_view: float,
) -> tuple[float, float] | None:
    difference = _angle_delta(bearing - yaw)
    if abs(difference) > field_of_view / 2.0 - 4.0:
        return None
    x = width / 2.0 + difference / (field_of_view / 2.0) * width * 0.43
    y = height * 0.78 + min(abs(difference) / (field_of_view / 2.0), 1.0) * 18.0
    return x, y


def _object_visible(bearing: float, yaw: float, field_of_view: float) -> bool:
    return abs(_angle_delta(bearing - yaw)) <= field_of_view / 2.0 - 2.0


def _near(left: float, right: float, tolerance: float = 0.04) -> bool:
    return abs(left - right) <= tolerance


def _summary_point(value: Any, label: str) -> dict[str, float] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{label} is malformed")
    return {
        "x": round(_number(value.get("x"), f"{label} x"), 2),
        "y": round(_number(value.get("y"), f"{label} y"), 2),
    }


def grade(
    payload: dict[str, Any],
    ground_truth: dict[str, Any],
    public_state: dict[str, Any],
) -> dict[str, Any]:
    if any(
        str(source.get("mechanic_id") or "") != MECHANIC_ID
        for source in (payload, ground_truth, public_state)
    ):
        return _fail("mechanic mismatch")
    challenge_id = str(ground_truth.get("challenge_id") or "")
    task_id = str(ground_truth.get("task_id") or "")
    if not challenge_id or any(
        str(source.get("challenge_id") or "") != challenge_id
        for source in (payload, public_state)
    ):
        return _fail("stale landfall challenge")
    if not task_id or any(
        str(source.get("task_id") or "") != task_id
        for source in (payload, public_state)
    ):
        return _fail("task identity mismatch")
    if str(public_state.get("world_fingerprint") or "") != str(
        ground_truth.get("world_fingerprint") or ""
    ):
        return _fail("world fingerprint mismatch")

    try:
        condition = dict(ground_truth.get("control_condition") or {})
        if dict(public_state.get("control_condition") or {}) != condition:
            raise ValueError("public control condition differs from hidden state")
        interaction = str(condition.get("interaction") or "full")
        if interaction not in {"simplified", "full"}:
            raise ValueError("unsupported interaction mode")
        for key in (
            "active_features",
            "feature_labels",
            "feature_values",
            "parameters",
            "map",
            "guide",
            "journey",
        ):
            if public_state.get(key) != ground_truth.get(key):
                raise ValueError(f"public {key} differs from the replay contract")
        target = dict(ground_truth["target"])
        journey = dict(ground_truth["journey"])
        map_state = dict(ground_truth["map"])
        active_features = [str(item) for item in ground_truth["active_features"]]
        feature_values = {
            str(key): [str(value) for value in values]
            for key, values in dict(ground_truth["feature_values"]).items()
        }
        nodes = {str(item["id"]): dict(item) for item in journey["nodes"]}
        clue_nodes: dict[str, str] = {}
        landmark_nodes: set[str] = set()
        for node_id, node in nodes.items():
            clue = node.get("clue")
            if clue is not None:
                feature = str(clue["feature"])
                value = str(clue["value"])
                _number(clue["bearing"], f"{node_id} clue bearing")
                if feature in clue_nodes:
                    raise ValueError(f"duplicate clue for {feature}")
                if feature not in active_features or value != str(
                    ground_truth["target"]["signature"].get(feature)
                ):
                    raise ValueError(f"{node_id} clue differs from target signature")
                clue_nodes[feature] = node_id
            landmark = node.get("landmark")
            if landmark is not None:
                _number(landmark["bearing"], f"{node_id} landmark bearing")
                landmark_nodes.add(node_id)
        if set(clue_nodes) != set(active_features):
            raise ValueError("journey does not expose every active evidence class once")
        if len(landmark_nodes) != 1:
            raise ValueError("journey must expose exactly one localization landmark")
        landing_node = str(target["landing_node"])
        if landing_node != str(journey["landing_node"]) or landing_node not in nodes:
            raise ValueError("landing node is missing")
        target_signature = {
            str(key): str(value) for key, value in dict(target["signature"]).items()
        }
        if set(target_signature) != set(active_features):
            raise ValueError("target signature does not match active evidence classes")
        target_point = {
            "x": _number(target["landing_point"]["x"], "target x"),
            "y": _number(target["landing_point"]["y"], "target y"),
        }
        panorama_width = float(journey["panorama_width"])
        panorama_height = float(journey["panorama_height"])
        field_of_view = float(journey["field_of_view_deg"])
        step_budget = int(journey["step_budget"])
        map_width = float(map_state["width"])
        map_height = float(map_state["height"])
        map_max_zoom = float(map_state["max_zoom"])
        pin_radius = float(ground_truth["parameters"]["pin_radius"])
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"invalid landfall contract: {exc}")

    events = payload.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 2400:
        return _fail("landfall transcript is missing or outside limits")

    current_node = landing_node
    yaw = float(journey["initial_yaw"])
    steps = 0
    visited = [current_node]
    selections: dict[str, str] = {}
    pin: dict[str, float] | None = None
    surface = "guide"
    guide_page = 0
    guide_pages = max(
        1,
        math.ceil(
            len(ground_truth["guide"]["provinces"])
            / int(ground_truth["guide"]["page_size"])
        ),
    )
    map_zoom = 1.0
    map_pan = (0.0, 0.0)
    pan_hold: dict[str, Any] | None = None
    map_hold: dict[str, Any] | None = None
    panorama_actions = 0
    map_actions = 0
    submission_count = 0
    observed_features: set[str] = set()
    observed_landmark_nodes: set[str] = set()

    def observe_current_view() -> None:
        node = nodes[current_node]
        clue = node.get("clue")
        if clue is not None and _object_visible(
            float(clue["bearing"]), yaw, field_of_view
        ):
            observed_features.add(str(clue["feature"]))
        landmark = node.get("landmark")
        if landmark is not None and _object_visible(
            float(landmark["bearing"]), yaw, field_of_view
        ):
            observed_landmark_nodes.add(current_node)

    # The first browser frame is a real observation before the first event.
    observe_current_view()

    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return _fail(f"event {sequence} has invalid sequence")
        kind = str(event.get("kind") or "")
        try:
            if kind == "surface_tab":
                if pan_hold is not None or map_hold is not None:
                    return _fail(f"event {sequence} changes surface during a pointer hold")
                next_surface = str(event.get("surface") or "")
                if next_surface not in {"map", "guide", "deposition"}:
                    return _fail(f"event {sequence} opens an unknown surface")
                surface = next_surface
            elif kind == "pan_start":
                if interaction != "full" or event.get("input_source") != "panorama_drag":
                    return _fail(f"event {sequence} uses the wrong panorama interaction")
                if pan_hold is not None or map_hold is not None:
                    return _fail(f"event {sequence} overlaps a pointer hold")
                point = _point(
                    event.get("point"), panorama_width, panorama_height, "pan start"
                )
                before = _number(event.get("yaw_before"), "pan yaw")
                if abs(_angle_delta(before - yaw)) > 0.04:
                    return _fail(f"event {sequence} starts from a stale bearing")
                pan_hold = {"start": point, "base_yaw": yaw}
            elif kind == "pan_move":
                if interaction != "full" or event.get("input_source") != "panorama_drag":
                    return _fail(f"event {sequence} uses the wrong panorama interaction")
                if pan_hold is None:
                    return _fail(f"event {sequence} moves no active panorama drag")
                point = _point(
                    event.get("point"), panorama_width, panorama_height, "pan move"
                )
                expected = _norm(
                    pan_hold["base_yaw"] - (point[0] - pan_hold["start"][0]) * 0.32
                )
                after = _number(event.get("yaw_after"), "pan result")
                if abs(_angle_delta(after - expected)) > 0.05:
                    return _fail(f"event {sequence} reports a false panorama bearing")
                yaw = _norm(after)
                panorama_actions += 1
            elif kind == "pan_end":
                if interaction != "full" or event.get("input_source") != "panorama_drag":
                    return _fail(f"event {sequence} uses the wrong panorama interaction")
                if pan_hold is None:
                    return _fail(f"event {sequence} ends no panorama drag")
                _point(event.get("point"), panorama_width, panorama_height, "pan end")
                if abs(_angle_delta(_number(event.get("yaw"), "pan end yaw") - yaw)) > 0.05:
                    return _fail(f"event {sequence} ends at a false bearing")
                pan_hold = None
                observe_current_view()
            elif kind == "turn_step":
                if interaction != "simplified" or event.get("input_source") != "turn_buttons":
                    return _fail(f"event {sequence} uses the wrong panorama interaction")
                if pan_hold is not None or map_hold is not None:
                    return _fail(f"event {sequence} turns during a pointer hold")
                before = _number(event.get("yaw_before"), "turn yaw")
                delta = _number(event.get("delta"), "turn delta")
                after = _number(event.get("yaw_after"), "turn result")
                if delta not in {-30.0, 30.0} or abs(_angle_delta(before - yaw)) > 0.04:
                    return _fail(f"event {sequence} has an invalid turn step")
                expected = _norm(yaw + delta)
                if abs(_angle_delta(after - expected)) > 0.05:
                    return _fail(f"event {sequence} reports a false turn result")
                yaw = expected
                panorama_actions += 1
                observe_current_view()
            elif kind in {"road_click", "road_button"}:
                expected_kind = "road_click" if interaction == "full" else "road_button"
                expected_source = "road_arrow" if interaction == "full" else "road_buttons"
                if kind != expected_kind or event.get("input_source") != expected_source:
                    return _fail(f"event {sequence} uses the wrong road interaction")
                if pan_hold is not None or map_hold is not None:
                    return _fail(f"event {sequence} travels during a pointer hold")
                source = str(event.get("from") or "")
                destination = str(event.get("to") or "")
                if source != current_node or destination not in nodes:
                    return _fail(f"event {sequence} departs from a stale road node")
                road = next(
                    (
                        dict(item)
                        for item in nodes[current_node]["roads"]
                        if str(item.get("to")) == destination
                    ),
                    None,
                )
                if road is None:
                    return _fail(f"event {sequence} crosses a nonexistent road")
                arrow = _arrow_point(
                    float(road["bearing"]),
                    yaw,
                    panorama_width,
                    panorama_height,
                    field_of_view,
                )
                if arrow is None:
                    return _fail(f"event {sequence} takes a road outside the visible view")
                if interaction == "full":
                    point = _point(
                        event.get("point"), panorama_width, panorama_height, "road click"
                    )
                    if math.hypot(point[0] - arrow[0], point[1] - arrow[1]) > 40.0:
                        return _fail(f"event {sequence} misses the visible road arrow")
                steps += 1
                if steps > step_budget:
                    return _fail(f"event {sequence} exceeds the road-step budget")
                current_node = destination
                if current_node not in visited:
                    visited.append(current_node)
                observe_current_view()
            elif kind == "guide_page":
                if surface != "guide":
                    return _fail(f"event {sequence} pages a hidden field guide")
                page = int(_number(event.get("page"), "guide page"))
                if not 0 <= page < guide_pages:
                    return _fail(f"event {sequence} opens a nonexistent guide page")
                guide_page = page
            elif kind == "answer_select":
                if surface != "deposition":
                    return _fail(f"event {sequence} files through a hidden deposition")
                feature = str(event.get("feature") or "")
                value = str(event.get("value") or "")
                if event.get("input_source") != "deposition_buttons":
                    return _fail(f"event {sequence} uses an unknown deposition surface")
                if feature not in active_features or value not in feature_values[feature]:
                    return _fail(f"event {sequence} files an invalid convention")
                selections[feature] = value
            elif kind == "map_wheel":
                if surface != "map":
                    return _fail(f"event {sequence} zooms a hidden map")
                if interaction != "full" or event.get("input_source") != "map_wheel":
                    return _fail(f"event {sequence} uses the wrong map interaction")
                if map_hold is not None or pan_hold is not None:
                    return _fail(f"event {sequence} zooms during a pointer hold")
                point = _point(event.get("point"), map_width, map_height, "map wheel")
                delta = _number(event.get("delta"), "map wheel delta")
                before = _number(event.get("zoom_before"), "map zoom")
                after = _number(event.get("zoom_after"), "map zoom result")
                if not _near(before, map_zoom):
                    return _fail(f"event {sequence} starts from a stale map zoom")
                factor = 1.18 if delta < 0 else 1.0 / 1.18
                expected_zoom = _clamp(map_zoom * factor, 1.0, map_max_zoom)
                world_x = (point[0] - map_pan[0]) / map_zoom
                world_y = (point[1] - map_pan[1]) / map_zoom
                expected_pan = _clamp_pan(
                    (point[0] - world_x * expected_zoom, point[1] - world_y * expected_zoom),
                    expected_zoom,
                    map_width,
                    map_height,
                )
                reported_pan = _point_like(event.get("pan_after"), "map pan")
                if not _near(after, expected_zoom) or any(
                    not _near(actual, expected, 0.08)
                    for actual, expected in zip(reported_pan, expected_pan)
                ):
                    return _fail(f"event {sequence} reports a false map zoom")
                # Continue from the browser's bounded precision after validating it.
                map_zoom, map_pan = after, reported_pan
                map_actions += 1
            elif kind == "map_drag_start":
                if surface != "map":
                    return _fail(f"event {sequence} drags a hidden map")
                if interaction != "full" or event.get("input_source") != "map_drag":
                    return _fail(f"event {sequence} uses the wrong map interaction")
                if map_hold is not None or pan_hold is not None:
                    return _fail(f"event {sequence} overlaps a pointer hold")
                point = _point(event.get("point"), map_width, map_height, "map drag start")
                reported_pan = _point_like(event.get("pan_before"), "map pan")
                if any(
                    not _near(actual, expected, 0.08)
                    for actual, expected in zip(reported_pan, map_pan)
                ):
                    return _fail(f"event {sequence} starts from stale map pan")
                map_hold = {"start": point, "base_pan": map_pan}
            elif kind == "map_drag_move":
                if interaction != "full" or event.get("input_source") != "map_drag":
                    return _fail(f"event {sequence} uses the wrong map interaction")
                if map_hold is None:
                    return _fail(f"event {sequence} moves no active map drag")
                point = _point(event.get("point"), map_width, map_height, "map drag move")
                expected_pan = _clamp_pan(
                    (
                        map_hold["base_pan"][0] + point[0] - map_hold["start"][0],
                        map_hold["base_pan"][1] + point[1] - map_hold["start"][1],
                    ),
                    map_zoom,
                    map_width,
                    map_height,
                )
                reported_pan = _point_like(event.get("pan_after"), "map pan")
                if any(
                    not _near(actual, expected, 0.08)
                    for actual, expected in zip(reported_pan, expected_pan)
                ):
                    return _fail(f"event {sequence} reports false map panning")
                map_pan = reported_pan
                map_actions += 1
            elif kind == "map_drag_end":
                if interaction != "full" or event.get("input_source") != "map_drag":
                    return _fail(f"event {sequence} uses the wrong map interaction")
                if map_hold is None:
                    return _fail(f"event {sequence} ends no map drag")
                _point(event.get("point"), map_width, map_height, "map drag end")
                reported_pan = _point_like(event.get("pan_after"), "map pan")
                if any(
                    not _near(actual, expected, 0.08)
                    for actual, expected in zip(reported_pan, map_pan)
                ):
                    return _fail(f"event {sequence} ends at false map pan")
                map_hold = None
            elif kind == "map_zoom_step":
                if surface != "map":
                    return _fail(f"event {sequence} zooms a hidden map")
                if interaction != "simplified" or event.get("input_source") != "map_buttons":
                    return _fail(f"event {sequence} uses the wrong map interaction")
                direction = int(_number(event.get("direction"), "map zoom direction"))
                if direction not in {-1, 1}:
                    return _fail(f"event {sequence} has an invalid map zoom direction")
                factor = 1.18 if direction > 0 else 1.0 / 1.18
                expected_zoom = _clamp(map_zoom * factor, 1.0, map_max_zoom)
                world_x = (map_width / 2.0 - map_pan[0]) / map_zoom
                world_y = (map_height / 2.0 - map_pan[1]) / map_zoom
                expected_pan = _clamp_pan(
                    (
                        map_width / 2.0 - world_x * expected_zoom,
                        map_height / 2.0 - world_y * expected_zoom,
                    ),
                    expected_zoom,
                    map_width,
                    map_height,
                )
                after = _number(event.get("zoom_after"), "map zoom result")
                reported_pan = _point_like(event.get("pan_after"), "map pan")
                if not _near(after, expected_zoom) or any(
                    not _near(actual, expected, 0.08)
                    for actual, expected in zip(reported_pan, expected_pan)
                ):
                    return _fail(f"event {sequence} reports a false map zoom")
                map_zoom, map_pan = after, reported_pan
                map_actions += 1
            elif kind == "map_pan_step":
                if surface != "map":
                    return _fail(f"event {sequence} pans a hidden map")
                if interaction != "simplified" or event.get("input_source") != "map_buttons":
                    return _fail(f"event {sequence} uses the wrong map interaction")
                direction = str(event.get("direction") or "")
                deltas = {
                    "left": (36.0, 0.0),
                    "right": (-36.0, 0.0),
                    "up": (0.0, 36.0),
                    "down": (0.0, -36.0),
                }
                if direction not in deltas:
                    return _fail(f"event {sequence} has an invalid map pan direction")
                delta_x, delta_y = deltas[direction]
                expected_pan = _clamp_pan(
                    (map_pan[0] + delta_x, map_pan[1] + delta_y),
                    map_zoom,
                    map_width,
                    map_height,
                )
                reported_pan = _point_like(event.get("pan_after"), "map pan")
                if any(
                    not _near(actual, expected, 0.08)
                    for actual, expected in zip(reported_pan, expected_pan)
                ):
                    return _fail(f"event {sequence} reports false map panning")
                map_pan = reported_pan
                map_actions += 1
            elif kind == "map_pin":
                if surface != "map":
                    return _fail(f"event {sequence} pins a hidden map")
                if event.get("input_source") != "map_direct":
                    return _fail(f"event {sequence} uses an unknown pin surface")
                view_point = _point(event.get("view_point"), map_width, map_height, "map pin")
                world_point = _point(event.get("world_point"), map_width, map_height, "map world pin")
                expected_world = (
                    (view_point[0] - map_pan[0]) / map_zoom,
                    (view_point[1] - map_pan[1]) / map_zoom,
                )
                if any(
                    not _near(actual, expected, 0.08)
                    for actual, expected in zip(world_point, expected_world)
                ):
                    return _fail(f"event {sequence} reports a false map coordinate")
                pin = {"x": round(world_point[0], 2), "y": round(world_point[1], 2)}
                map_actions += 1
            elif kind == "submit":
                if pan_hold is not None or map_hold is not None:
                    return _fail(f"event {sequence} submits during a pointer hold")
                submission_count += 1
            else:
                return _fail(f"event {sequence} has unknown kind {kind!r}")
        except (KeyError, TypeError, ValueError) as exc:
            return _fail(f"event {sequence}: {exc}")

    try:
        submitted_pin = _summary_point(payload.get("pin"), "submitted pin")
        expected_summary = {
            "current_node": current_node,
            "step_count": steps,
            "visited_nodes": visited,
            "final_yaw": round(yaw, 2),
            "selections": selections,
            "pin": pin,
            "map_zoom": round(map_zoom, 4),
            "map_pan": [round(map_pan[0], 2), round(map_pan[1], 2)],
            "submission_count": submission_count,
        }
        submitted_summary = {
            "current_node": str(payload.get("current_node") or ""),
            "step_count": int(payload.get("step_count")),
            "visited_nodes": payload.get("visited_nodes"),
            "final_yaw": round(_number(payload.get("final_yaw"), "final yaw"), 2),
            "selections": payload.get("selections"),
            "pin": submitted_pin,
            "map_zoom": round(_number(payload.get("map_zoom"), "map zoom"), 4),
            "map_pan": [
                round(value, 2)
                for value in _point_like(payload.get("map_pan"), "map pan")
            ],
            "submission_count": int(payload.get("submission_count")),
        }
    except (TypeError, ValueError) as exc:
        return _fail(f"invalid submitted summary: {exc}")
    if submitted_summary != expected_summary:
        mismatches = [
            key for key in expected_summary if submitted_summary.get(key) != expected_summary[key]
        ]
        return _fail(
            "submitted landfall summary does not match replay: "
            + ", ".join(mismatches)
        )

    answers_correct = selections == target_signature
    pin_distance = (
        math.hypot(pin["x"] - target_point["x"], pin["y"] - target_point["y"])
        if pin is not None
        else math.inf
    )
    pin_correct = pin_distance <= pin_radius
    evidence_complete = observed_features == set(active_features)
    landmark_complete = observed_landmark_nodes == landmark_nodes
    passed = (
        payload.get("completed") is True
        and answers_correct
        and pin_correct
        and evidence_complete
        and landmark_complete
        and steps <= step_budget
        and panorama_actions >= 1
        and steps >= 1
        and map_actions >= 1
        and submission_count == 1
        and pan_hold is None
        and map_hold is None
    )
    target_name = next(
        (
            str(item["name"])
            for item in ground_truth["guide"]["provinces"]
            if str(item["id"]) == str(target["province_id"])
        ),
        "unknown province",
    )
    feedback = (
        f"landfall replay: province {target_name}; conventions "
        f"{sum(selections.get(feature) == target_signature[feature] for feature in active_features)}/{len(active_features)}; "
        f"observations {len(observed_features)}/{len(active_features)}; "
        f"landmark {len(observed_landmark_nodes)}/{len(landmark_nodes)}; "
        f"pin error {pin_distance:.1f}/{pin_radius:.1f}; steps {steps}/{step_budget}; "
        f"visited {len(visited)} road nodes"
    )
    return {
        "graded": True,
        "passed": passed,
        "score": 100 if passed else 0,
        "feedback": feedback,
    }


def _point_like(value: Any, label: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} is malformed")
    return _number(value[0], f"{label} x"), _number(value[1], f"{label} y")


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {
        "target": ground_truth.get("target") or {},
        "answers": [],
    }
