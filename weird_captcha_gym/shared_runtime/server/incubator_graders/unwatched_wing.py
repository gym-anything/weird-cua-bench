from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "unwatched_wing"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite")
    return float(value)


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _q(value: float) -> float:
    return round(float(value), 6)


def _normalize_mdeg(value: int) -> int:
    return value % 360_000


def _signed_radians(value: float) -> float:
    return (value + math.pi) % (2 * math.pi) - math.pi


def _angle_radians(angle_mdeg: int) -> float:
    return math.radians(angle_mdeg / 1000)


def _circle_clear(museum_map: list[str], x: float, y: float, radius: float) -> bool:
    height = len(museum_map)
    width = len(museum_map[0]) if height else 0
    for cell_y in range(math.floor(y - radius), math.floor(y + radius) + 1):
        for cell_x in range(math.floor(x - radius), math.floor(x + radius) + 1):
            if cell_y < 0 or cell_y >= height or cell_x < 0 or cell_x >= width:
                return False
            if museum_map[cell_y][cell_x] != "#":
                continue
            nearest_x = max(cell_x, min(x, cell_x + 1))
            nearest_y = max(cell_y, min(y, cell_y + 1))
            if (x - nearest_x) ** 2 + (y - nearest_y) ** 2 < radius ** 2 - 1e-10:
                return False
    return True


def _cast_wall(museum_map: list[str], x: float, y: float, angle_mdeg: int) -> float:
    angle = _angle_radians(angle_mdeg)
    direction_x, direction_y = math.cos(angle), math.sin(angle)
    map_x, map_y = math.floor(x), math.floor(y)
    delta_x = abs(1 / direction_x) if abs(direction_x) > 1e-12 else 1e30
    delta_y = abs(1 / direction_y) if abs(direction_y) > 1e-12 else 1e30
    step_x, step_y = (-1 if direction_x < 0 else 1), (-1 if direction_y < 0 else 1)
    side_x = (x - map_x) * delta_x if direction_x < 0 else (map_x + 1 - x) * delta_x
    side_y = (y - map_y) * delta_y if direction_y < 0 else (map_y + 1 - y) * delta_y
    height, width = len(museum_map), len(museum_map[0])
    for _ in range(256):
        if side_x < side_y:
            distance = side_x
            side_x += delta_x
            map_x += step_x
        else:
            distance = side_y
            side_y += delta_y
            map_y += step_y
        if map_y < 0 or map_y >= height or map_x < 0 or map_x >= width or museum_map[map_y][map_x] == "#":
            return distance
    return 1e9


def _line_of_sight(museum_map: list[str], first: tuple[float, float], second: tuple[float, float]) -> bool:
    distance = math.dist(first, second)
    if distance <= 1e-9:
        return True
    angle = round(math.degrees(math.atan2(second[1] - first[1], second[0] - first[0])) * 1000)
    return _cast_wall(museum_map, first[0], first[1], angle) >= distance - .08


def _contract(ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "map", "world", "initial_pose", "controls", "plinths", "target_path", "dock",
        "wall_lights", "required_pin_steps", "target_exhibit", "decoy_exhibits", "palette",
    )
    for key in keys:
        if ground_truth.get(key) != public_state.get(key):
            raise ValueError(f"public {key} differs from the hidden museum contract")
    museum_map = ground_truth.get("map")
    world = ground_truth.get("world")
    controls = ground_truth.get("controls")
    initial = ground_truth.get("initial_pose")
    plinths = ground_truth.get("plinths")
    path = ground_truth.get("target_path")
    dock = ground_truth.get("dock")
    if not isinstance(museum_map, list) or not museum_map or not all(isinstance(row, str) for row in museum_map):
        raise ValueError("museum map is malformed")
    width = len(museum_map[0])
    if width < 5 or any(len(row) != width or set(row) - {"#", "."} for row in museum_map):
        raise ValueError("museum map rows are malformed")
    if not isinstance(world, dict) or int(world.get("width", -1)) != width or int(world.get("height", -1)) != len(museum_map):
        raise ValueError("museum world bounds differ from the map")
    if not isinstance(controls, dict) or not isinstance(initial, dict):
        raise ValueError("museum controls or initial pose are malformed")
    if not isinstance(plinths, list) or not 3 <= len(plinths) <= 12 or not isinstance(path, list) or not 3 <= len(path) <= 7:
        raise ValueError("museum plinth bank or target path is malformed")
    plinth_by_id: dict[str, dict[str, Any]] = {}
    for item in plinths:
        if not isinstance(item, dict) or not str(item.get("id") or "") or str(item["id"]) in plinth_by_id:
            raise ValueError("museum plinth identity is malformed")
        center = item.get("center")
        if not isinstance(center, list) or len(center) != 2:
            raise ValueError("museum plinth center is malformed")
        point = _number(center[0], "plinth x"), _number(center[1], "plinth y")
        if not _circle_clear(museum_map, point[0], point[1], .2):
            raise ValueError("museum plinth is outside reachable floor")
        plinth_by_id[str(item["id"])] = item
    if len(set(map(str, path))) != len(path) or any(str(value) not in plinth_by_id for value in path):
        raise ValueError("target path references an invalid plinth")
    if not isinstance(dock, dict) or str(dock.get("id") or "") in plinth_by_id:
        raise ValueError("museum dock identity is malformed")
    dock_center = dock.get("center")
    if not isinstance(dock_center, list) or len(dock_center) != 2 or not _circle_clear(museum_map, float(dock_center[0]), float(dock_center[1]), .2):
        raise ValueError("museum dock is outside reachable floor")
    return {
        "map": museum_map,
        "world": world,
        "controls": controls,
        "initial": initial,
        "plinths": plinths,
        "plinth_by_id": plinth_by_id,
        "path": list(map(str, path)),
        "dock": dock,
        "lights": ground_truth.get("wall_lights") or [],
        "required_pin_steps": set(int(value) for value in ground_truth.get("required_pin_steps") or []),
    }


def _initial_state(contract: dict[str, Any]) -> dict[str, Any]:
    initial = contract["initial"]
    return {
        "pose": {
            "x": _number(initial.get("x"), "initial x"),
            "y": _number(initial.get("y"), "initial y"),
            "angle_mdeg": _normalize_mdeg(_integer(initial.get("angle_mdeg"), "initial angle")),
        },
        "target_cursor": 0,
        "target_armed": True,
        "dock_occupied": False,
        "lamp_on": True,
        "viewer_open": False,
        "probe_plinth_id": None,
        "lights": {str(item["id"]): bool(item.get("enabled")) for item in contract["lights"]},
        "pin_ready": set(),
        "jump_count": 0,
        "rejected_handoffs": 0,
        "entangled": False,
    }


def _point(contract: dict[str, Any], plinth_id: str) -> tuple[float, float]:
    if plinth_id == str(contract["dock"]["id"]):
        center = contract["dock"]["center"]
    else:
        center = contract["plinth_by_id"][plinth_id]["center"]
    return float(center[0]), float(center[1])


def _relative_angle(state: dict[str, Any], point: tuple[float, float]) -> float:
    pose = state["pose"]
    bearing = math.atan2(point[1] - float(pose["y"]), point[0] - float(pose["x"]))
    return _signed_radians(bearing - _angle_radians(int(pose["angle_mdeg"])))


def _geometric_visible(contract: dict[str, Any], state: dict[str, Any], point: tuple[float, float], half_angle_scale: float = 1.0) -> bool:
    pose = state["pose"]
    origin = float(pose["x"]), float(pose["y"])
    distance = math.dist(origin, point)
    half = math.radians(float(contract["controls"]["field_of_view_deg"]) / 2) * half_angle_scale
    return (
        distance <= float(contract["controls"]["visible_range"])
        and abs(_relative_angle(state, point)) <= half
        and _line_of_sight(contract["map"], origin, point)
    )


def _visible_lights(contract: dict[str, Any], state: dict[str, Any]) -> list[str]:
    return [
        str(item["id"])
        for item in contract["lights"]
        if state["lights"].get(str(item["id"]), False)
        and _geometric_visible(contract, state, (float(item["center"][0]), float(item["center"][1])))
    ]


def _target_observation(contract: dict[str, Any], state: dict[str, Any]) -> dict[str, bool]:
    if state["dock_occupied"]:
        return {"main": True, "hand": False, "ambient": False, "probe": False}
    plinth_id = contract["path"][int(state["target_cursor"])]
    target = _point(contract, plinth_id)
    pose = state["pose"]
    origin = float(pose["x"]), float(pose["y"])
    hand = bool(
        state["lamp_on"]
        and math.dist(origin, target) <= float(contract["controls"]["hand_lamp_range"])
        and _line_of_sight(contract["map"], origin, target)
    )
    ambient = any(
        state["lights"].get(str(item["id"]), False) and str(item.get("plinth_id")) == plinth_id
        for item in contract["lights"]
    )
    scene_lit = bool(state["lamp_on"] or _visible_lights(contract, state) or state["viewer_open"])
    main = bool(scene_lit and _geometric_visible(contract, state, target) and (hand or ambient or state["lamp_on"]))
    probe = bool(state["viewer_open"] and state["probe_plinth_id"] == plinth_id)
    return {"main": main, "hand": hand, "ambient": ambient, "probe": probe}


def _render_dark(contract: dict[str, Any], state: dict[str, Any]) -> bool:
    return bool(not state["lamp_on"] and not state["viewer_open"] and not _visible_lights(contract, state))


def _settle(contract: dict[str, Any], state: dict[str, Any]) -> None:
    if state["dock_occupied"]:
        return
    cursor = int(state["target_cursor"])
    observation = _target_observation(contract, state)
    observed = any(observation.values())
    current = _point(contract, contract["path"][cursor])
    pose_point = float(state["pose"]["x"]), float(state["pose"]["y"])
    final_ready = bool(
        cursor == len(contract["path"]) - 1
        and math.dist(pose_point, current) <= float(contract["controls"]["entangle_radius"])
        and _render_dark(contract, state)
        and not observation["ambient"]
        and state["probe_plinth_id"] is None
        and not state["viewer_open"]
        and not state["lamp_on"]
    )
    if final_ready:
        dock = _point(contract, str(contract["dock"]["id"]))
        state["target_cursor"] = len(contract["path"])
        state["dock_occupied"] = True
        state["entangled"] = True
        state["target_armed"] = False
        state["jump_count"] += 1
        state["pose"]["x"], state["pose"]["y"] = _q(dock[0]), _q(dock[1])
        return
    if observed:
        state["target_armed"] = True
        only_probe = observation["probe"] and not observation["main"] and not observation["hand"] and not observation["ambient"]
        if only_probe and cursor in contract["required_pin_steps"]:
            release = _point(contract, contract["path"][cursor + 1])
            if math.dist(pose_point, release) <= float(contract["controls"]["release_radius"]):
                state["pin_ready"].add(cursor)
        return
    if not state["target_armed"]:
        return
    if cursor == len(contract["path"]) - 1:
        state["target_cursor"] = max(0, cursor - 1)
        state["rejected_handoffs"] += 1
    elif cursor in contract["required_pin_steps"] and cursor not in state["pin_ready"]:
        state["target_cursor"] = max(0, cursor - 1)
        state["rejected_handoffs"] += 1
    else:
        state["target_cursor"] = cursor + 1
    state["target_armed"] = False
    state["jump_count"] += 1


def _move(contract: dict[str, Any], state: dict[str, Any], forward: int, strafe: int) -> tuple[dict[str, Any], bool, bool]:
    pose = state["pose"]
    before = {"x": _q(pose["x"]), "y": _q(pose["y"]), "angle_mdeg": int(pose["angle_mdeg"])}
    angle = _angle_radians(int(pose["angle_mdeg"]))
    step = float(contract["controls"]["move_step"])
    intended_x = _q(float(pose["x"]) + (math.cos(angle) * forward + math.cos(angle + math.pi / 2) * strafe) * step)
    intended_y = _q(float(pose["y"]) + (math.sin(angle) * forward + math.sin(angle + math.pi / 2) * strafe) * step)
    radius = float(contract["controls"]["player_radius"])
    blocked_x = not _circle_clear(contract["map"], intended_x, float(pose["y"]), radius)
    if not blocked_x:
        pose["x"] = intended_x
    blocked_y = not _circle_clear(contract["map"], float(pose["x"]), intended_y, radius)
    if not blocked_y:
        pose["y"] = intended_y
    pose["x"], pose["y"] = _q(pose["x"]), _q(pose["y"])
    return before, blocked_x, blocked_y


def _aimed_plinth(contract: dict[str, Any], state: dict[str, Any]) -> str | None:
    pose = state["pose"]
    origin = float(pose["x"]), float(pose["y"])
    candidates: list[tuple[float, float, str]] = []
    tolerance = math.radians(float(contract["controls"]["probe_aim_tolerance_deg"]))
    for item in contract["plinths"]:
        point = float(item["center"][0]), float(item["center"][1])
        distance = math.dist(origin, point)
        error = abs(_relative_angle(state, point))
        if distance <= float(contract["controls"]["probe_range"]) and error <= tolerance and _line_of_sight(contract["map"], origin, point):
            candidates.append((error, distance, str(item["id"])))
    return min(candidates)[2] if candidates else None


def _nearest_breaker(contract: dict[str, Any], state: dict[str, Any]) -> str | None:
    pose = state["pose"]
    origin = float(pose["x"]), float(pose["y"])
    candidates = []
    for item in contract["lights"]:
        point = float(item["center"][0]), float(item["center"][1])
        distance = math.dist(origin, point)
        if distance <= float(contract["controls"]["breaker_range"]) and _line_of_sight(contract["map"], origin, point):
            candidates.append((distance, str(item["id"])))
    return min(candidates)[1] if candidates else None


def _same_pose(value: Any, pose: dict[str, Any]) -> bool:
    return isinstance(value, dict) and value == {"x": _q(pose["x"]), "y": _q(pose["y"]), "angle_mdeg": int(pose["angle_mdeg"])}


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    for label, source in (("payload", payload), ("ground truth", ground_truth), ("public state", public_state)):
        if str(source.get("mechanic_id") or "") != MECHANIC_ID:
            return _fail(f"{label} mechanic mismatch")
    task_id = str(ground_truth.get("task_id") or "")
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if not task_id or any(str(source.get("task_id") or "") != task_id for source in (payload, public_state)):
        return _fail("task binding mismatch")
    if not challenge_id or any(str(source.get("challenge_id") or "") != challenge_id for source in (payload, public_state)):
        return _fail("stale or cross-seed museum challenge")
    truth_condition = ground_truth.get("control_condition")
    if public_state.get("control_condition") != truth_condition:
        return _fail("public control condition differs from the museum contract")
    if payload.get("control_condition") != truth_condition:
        return _fail("submitted control condition differs from the museum contract")
    interaction = str((truth_condition or {}).get("interaction") or "full")
    if interaction not in {"simplified", "full"} or payload.get("interaction_mode") != interaction:
        return _fail("museum interaction mode mismatch")
    sources = {
        "simplified": {
            "move": "control_buttons", "look": "turn_buttons", "lamp": "lamp_button",
            "viewer": "viewer_button", "probe": "probe_button", "recall": "recall_button",
            "breaker": "breaker_button", "abandon": "abandon_button",
        },
        "full": {
            "move": "keyboard", "look": "viewport_drag", "lamp": "keyboard_lamp",
            "viewer": "keyboard_viewer", "probe": "viewport_probe", "recall": "keyboard_recall",
            "breaker": "keyboard_breaker", "abandon": "abandon_button",
        },
    }[interaction]
    try:
        contract = _contract(ground_truth, public_state)
        state = _initial_state(contract)
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"invalid museum geometry: {exc}")

    events = payload.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 2400:
        return _fail("museum interaction transcript is missing or outside limits")
    terminal = submitted = abandoned = False
    counts = {"moves": 0, "looks": 0, "equipment": 0, "breakers": 0}
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return _fail(f"museum event {sequence} has invalid sequencing")
        if terminal:
            return _fail("museum transcript continues after terminal interaction")
        kind = str(event.get("kind") or "")
        try:
            if kind == "move":
                if event.get("input_source") != sources["move"]:
                    return _fail(f"museum event {sequence} uses the wrong movement input")
                forward = _integer(event.get("forward"), "forward amount")
                strafe = _integer(event.get("strafe"), "strafe amount")
                if forward not in {-1, 0, 1} or strafe not in {-1, 0, 1} or abs(forward) + abs(strafe) != 1:
                    return _fail(f"museum event {sequence} has an invalid movement vector")
                before, blocked_x, blocked_y = _move(contract, state, forward, strafe)
                if event.get("from") != before or not _same_pose(event.get("to"), state["pose"]):
                    return _fail(f"museum event {sequence} movement geometry disagrees with replay")
                if event.get("blocked_x") is not blocked_x or event.get("blocked_y") is not blocked_y:
                    return _fail(f"museum event {sequence} collision flags disagree with replay")
                counts["moves"] += 1
            elif kind == "look":
                if event.get("input_source") != sources["look"]:
                    return _fail(f"museum event {sequence} uses the wrong look input")
                delta = _integer(event.get("delta_mdeg"), "look delta")
                if delta == 0 or abs(delta) > 30_000:
                    return _fail(f"museum event {sequence} has an invalid look delta")
                before = int(state["pose"]["angle_mdeg"])
                state["pose"]["angle_mdeg"] = _normalize_mdeg(before + delta)
                if event.get("before_mdeg") != before or event.get("after_mdeg") != state["pose"]["angle_mdeg"]:
                    return _fail(f"museum event {sequence} look geometry disagrees with replay")
                counts["looks"] += 1
            elif kind == "lamp":
                if event.get("input_source") != sources["lamp"] or not isinstance(event.get("enabled"), bool):
                    return _fail(f"museum event {sequence} uses the wrong lamp input")
                if event["enabled"] is state["lamp_on"]:
                    return _fail(f"museum event {sequence} repeats the hand-lamp state")
                state["lamp_on"] = event["enabled"]
                counts["equipment"] += 1
            elif kind == "viewer":
                if event.get("input_source") != sources["viewer"] or not isinstance(event.get("open"), bool):
                    return _fail(f"museum event {sequence} uses the wrong viewer input")
                if event["open"] is state["viewer_open"]:
                    return _fail(f"museum event {sequence} repeats the viewer state")
                state["viewer_open"] = event["open"]
                counts["equipment"] += 1
            elif kind == "probe_deploy":
                if event.get("input_source") != sources["probe"]:
                    return _fail(f"museum event {sequence} uses the wrong probe input")
                aimed = _aimed_plinth(contract, state)
                if aimed is None or str(event.get("plinth_id") or "") != aimed:
                    return _fail(f"museum event {sequence} probe misses the replayed reticle")
                state["probe_plinth_id"] = aimed
                counts["equipment"] += 1
            elif kind == "probe_recall":
                if event.get("input_source") != sources["recall"] or state["probe_plinth_id"] is None:
                    return _fail(f"museum event {sequence} uses the wrong or empty recall input")
                if str(event.get("plinth_id") or "") != str(state["probe_plinth_id"]):
                    return _fail(f"museum event {sequence} recalls a different probe")
                state["probe_plinth_id"] = None
                counts["equipment"] += 1
            elif kind == "breaker":
                if event.get("input_source") != sources["breaker"] or not isinstance(event.get("enabled"), bool):
                    return _fail(f"museum event {sequence} uses the wrong breaker input")
                light_id = str(event.get("light_id") or "")
                if light_id != _nearest_breaker(contract, state) or light_id not in state["lights"]:
                    return _fail(f"museum event {sequence} operates no nearby gallery light")
                if event["enabled"] is state["lights"][light_id]:
                    return _fail(f"museum event {sequence} repeats the gallery-light state")
                state["lights"][light_id] = event["enabled"]
                counts["breakers"] += 1
            elif kind == "submit":
                if event.get("input_source") != "dock_auto":
                    return _fail(f"museum event {sequence} uses the wrong dock submission input")
                submitted = terminal = True
            elif kind == "abandon":
                if event.get("input_source") != sources["abandon"]:
                    return _fail(f"museum event {sequence} uses the wrong abandon input")
                abandoned = terminal = True
            else:
                return _fail(f"museum event {sequence} has unknown primitive kind {kind!r}")
            if kind not in {"submit", "abandon"}:
                _settle(contract, state)
        except (KeyError, TypeError, ValueError) as exc:
            return _fail(f"museum event {sequence}: {exc}")

    final_target = str(contract["dock"]["id"]) if state["dock_occupied"] else contract["path"][int(state["target_cursor"])]
    expected_equipment = {
        "lamp_on": state["lamp_on"],
        "viewer_open": state["viewer_open"],
        "probe_plinth_id": state["probe_plinth_id"],
        "wall_lights": state["lights"],
    }
    if not _same_pose(payload.get("final_pose"), state["pose"]):
        return _fail("submitted player pose disagrees with independent replay")
    if payload.get("final_target_plinth_id") != final_target or payload.get("dock_occupied") is not state["dock_occupied"]:
        return _fail("submitted exhibit location disagrees with independent replay")
    if payload.get("jump_count") != state["jump_count"] or payload.get("rejected_handoffs") != state["rejected_handoffs"]:
        return _fail("submitted jump ledger disagrees with independent replay")
    if payload.get("pin_ready_steps") != sorted(state["pin_ready"]):
        return _fail("submitted probe-handoff ledger disagrees with independent replay")
    if payload.get("equipment") != expected_equipment or payload.get("interaction_counts") != counts:
        return _fail("submitted equipment or interaction counts disagree with independent replay")
    darkness = payload.get("darkness_sample")
    try:
        mean_luminance = _number((darkness or {}).get("mean_luminance"), "mean frame luminance")
        max_luminance = _number((darkness or {}).get("max_luminance"), "maximum frame luminance")
    except (AttributeError, ValueError) as exc:
        return _fail(f"darkness sample is malformed: {exc}")
    if mean_luminance < 0 or max_luminance < mean_luminance or max_luminance > 1:
        return _fail("darkness sample lies outside luminance bounds")
    passed = bool(
        payload.get("completed") is True
        and submitted
        and not abandoned
        and state["dock_occupied"]
        and state["entangled"]
        and contract["required_pin_steps"].issubset(state["pin_ready"])
        and not state["lamp_on"]
        and not state["viewer_open"]
        and state["probe_plinth_id"] is None
        and mean_luminance <= .01
        and max_luminance <= .02
    )
    return {
        "graded": True,
        "passed": passed,
        "score": 100 if passed else 0,
        "feedback": (
            f"observer replay: target {final_target}; jumps {state['jump_count']}; "
            f"probe thresholds {len(state['pin_ready'])}/{len(contract['required_pin_steps'])}; "
            f"darkness mean {mean_luminance:.4f} max {max_luminance:.4f}; dock {'occupied' if state['dock_occupied'] else 'empty'}"
        ),
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {
        "route_points": (ground_truth.get("solution") or {}).get("route_points"),
        "target_route_indices": (ground_truth.get("solution") or {}).get("target_route_indices"),
        "dock_route_index": (ground_truth.get("solution") or {}).get("dock_route_index"),
        "required_pin_steps": ground_truth.get("required_pin_steps"),
        "instruction": "Use the viewport and lights to release ordinary jumps, hold marked blind handoffs in the live probe viewer, then remove every observer while standing on the last pedestal.",
        "answers": [],
    }
