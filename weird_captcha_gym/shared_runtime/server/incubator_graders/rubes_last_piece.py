from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "rubes_last_piece"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _close(first: Any, second: Any, tolerance: float = 0.025) -> bool:
    try:
        return math.isfinite(float(first)) and math.isfinite(float(second)) and abs(float(first) - float(second)) <= tolerance
    except (TypeError, ValueError):
        return False


def _pose(value: Any) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 3:
        return None
    try:
        result = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    return result if all(math.isfinite(item) for item in result) else None


def _point(value: Any) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    try:
        result = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    return result if all(math.isfinite(item) for item in result) else None


def _inside_work_zone(point: list[float], bay: dict[str, Any]) -> bool:
    left, top, width, height = (float(item) for item in bay["work_zone"])
    return left <= point[0] <= left + width and top <= point[1] <= top + height


def _drag_gesture(value: Any, tool_id: str) -> dict[str, Any] | None:
    if not isinstance(value, dict) or value.get("origin") not in {"rack", "canvas"} or value.get("start_tool_id") != tool_id:
        return None
    release = _point(value.get("release_stage"))
    raw_samples = value.get("samples_stage")
    if release is None or not isinstance(raw_samples, list) or not 1 <= len(raw_samples) <= 64:
        return None
    samples = [_point(item) for item in raw_samples]
    if any(item is None for item in samples):
        return None
    normalized_samples = [item for item in samples if item is not None]
    if math.dist(normalized_samples[-1], release) > 0.06:
        return None
    start = value.get("start_stage")
    if start is not None:
        start = _point(start)
        if start is None:
            return None
    return {"origin": value["origin"], "start": start, "samples": normalized_samples, "release": release}


def _distance_to_segment(point: tuple[float, float], first: tuple[float, float], second: tuple[float, float]) -> float:
    dx, dy = second[0] - first[0], second[1] - first[1]
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-12:
        return math.dist(point, first)
    amount = max(0.0, min(1.0, ((point[0] - first[0]) * dx + (point[1] - first[1]) * dy) / length_sq))
    return math.hypot(point[0] - (first[0] + dx * amount), point[1] - (first[1] + dy * amount))


def _step_ball(ball: dict[str, Any], bay: dict[str, Any], tool: dict[str, Any], pose: list[float], contract: dict[str, Any]) -> bool:
    first = (float(ball["x"]), float(ball["y"]))
    vx, vy = float(ball["vx"]), float(ball["vy"])
    if ball["bounced"]:
        vy += float(bay["wind_y"])
        vx *= float(contract["flight_drag"])
        vy *= float(contract["flight_drag"])
    next_point = (first[0] + vx, first[1] + vy)
    if not ball["bounced"]:
        radians = math.radians(float(pose[2]) + float(tool["facet_deg"]))
        tangent = (math.cos(radians), math.sin(radians))
        normal = (-tangent[1], tangent[0])
        center = (float(pose[0]), float(pose[1]))
        threshold = -(float(contract["ball_radius"]) + float(tool["thickness"]) / 2.0)
        before = (first[0] - center[0]) * normal[0] + (first[1] - center[1]) * normal[1]
        after = (next_point[0] - center[0]) * normal[0] + (next_point[1] - center[1]) * normal[1]
        if before < threshold <= after and after - before > 1e-9:
            amount = (threshold - before) / (after - before)
            contact = (first[0] + (next_point[0] - first[0]) * amount, first[1] + (next_point[1] - first[1]) * amount)
            along = (contact[0] - center[0]) * tangent[0] + (contact[1] - center[1]) * tangent[1]
            if abs(along) <= float(tool["length"]) / 2.0 + float(contract["ball_radius"]):
                projection = vx * normal[0] + vy * normal[1]
                impulse = (1.0 + float(tool["restitution"])) * projection
                vx -= impulse * normal[0]
                vy -= impulse * normal[1]
                remaining = 1.0 - amount
                next_point = (contact[0] + vx * remaining, contact[1] + vy * remaining)
                ball["bounced"] = True
                ball["bounce_tick"] = int(ball["tick"]) + 1
    ball["tick"] = int(ball["tick"]) + 1
    ball["x"], ball["y"], ball["vx"], ball["vy"] = next_point[0], next_point[1], vx, vy
    receiver = tuple(float(value) for value in bay["receiver"])
    geometry_hit = ball["bounced"] and _distance_to_segment(receiver, first, next_point) <= float(bay["receiver_radius"]) + float(contract["ball_radius"])
    receiver_success = False
    if geometry_hit and not ball.get("receiver_encountered"):
        ball["receiver_encountered"] = True
        contact_speed = math.hypot(vx, vy)
        ball["impact_speed"] = contact_speed
        impact_error = contact_speed - float(bay["impact_speed"])
        ball["impact_error"] = impact_error
        receiver_success = abs(impact_error) <= float(bay["impact_tolerance"])
    if not ball.get("crossing") and first[0] < receiver[0] <= next_point[0]:
        amount = (receiver[0] - first[0]) / max(1e-9, next_point[0] - first[0])
        ball["crossing"] = [receiver[0], first[1] + (next_point[1] - first[1]) * amount]
    return receiver_success


def replay_lane(public: dict[str, Any], bay: dict[str, Any], tool: dict[str, Any], pose: list[float]) -> dict[str, Any]:
    contract = public["contract"]
    anchor = bay["anchor"]
    if math.hypot(float(pose[0]) - float(anchor[0]), float(pose[1]) - float(anchor[1])) > float(contract["snap_position_tolerance"]):
        return {"passed": False, "ticks": 0, "reason": "deflector is outside its physical station", "contact": None, "miss_offset": None, "impact_error": None}
    normalized_angle = float(pose[2]) % 180.0
    step = float(contract["rotation_step_deg"])
    if not _close(normalized_angle / step, round(normalized_angle / step), 0.002):
        return {"passed": False, "ticks": 0, "reason": "deflector angle is between its physical stops", "contact": None, "miss_offset": None, "impact_error": None}
    normalized_pose = [float(anchor[0]), float(anchor[1]), normalized_angle]
    ball = {
        "x": float(bay["launcher"][0]),
        "y": float(bay["launcher"][1]),
        "vx": float(contract["initial_velocity"][0]),
        "vy": float(contract["initial_velocity"][1]),
        "tick": 0,
        "bounced": False,
        "crossing": None,
    }
    for _ in range(int(contract["lane_timeout_ticks"])):
        if _step_ball(ball, bay, tool, normalized_pose, contract):
            return {
                "passed": True,
                "ticks": int(ball["tick"]),
                "reason": "receiver contact",
                "contact": [round(float(ball["x"]), 3), round(float(ball["y"]), 3)],
                "miss_offset": 0.0,
                "impact_error": round(float(ball.get("impact_error") or 0.0), 3),
            }
    crossing = ball.get("crossing")
    miss_offset = None if not crossing else round(float(crossing[1]) - float(bay["receiver"][1]), 3)
    return {
        "passed": False,
        "ticks": int(ball["tick"]),
        "reason": "receiver contact outside impact band" if ball.get("impact_error") is not None else "trajectory missed the receiver" if ball["bounced"] else "ball missed the deflector face",
        "contact": None,
        "miss_offset": miss_offset,
        "impact_error": None if ball.get("impact_error") is None else round(float(ball["impact_error"]), 3),
    }


def replay_run(public: dict[str, Any], placements: dict[str, dict[str, Any]]) -> dict[str, Any]:
    tools = {str(item["id"]): item for item in public["tools"]}
    global_tick = 0
    releases: list[dict[str, Any]] = []
    for bay in public["bays"]:
        assigned = [(tool_id, item) for tool_id, item in placements.items() if item.get("bay_id") == bay["id"]]
        if len(assigned) != 1:
            global_tick += int(public["contract"]["lane_timeout_ticks"])
            return {"passed": False, "ticks": global_tick, "releases": releases, "stalled_bay": bay["id"], "miss_offset": None, "impact_error": None, "reason": "station has no unique deflector"}
        tool_id, placement = assigned[0]
        tool = tools.get(tool_id)
        pose = _pose(placement.get("pose"))
        if tool is None or pose is None:
            global_tick += int(public["contract"]["lane_timeout_ticks"])
            return {"passed": False, "ticks": global_tick, "releases": releases, "stalled_bay": bay["id"], "miss_offset": None, "impact_error": None, "reason": "station contains an unknown deflector"}
        lane = replay_lane(public, bay, tool, pose)
        global_tick += int(lane["ticks"])
        if not lane["passed"]:
            return {
                "passed": False,
                "ticks": global_tick,
                "releases": releases,
                "stalled_bay": bay["id"],
                "miss_offset": lane["miss_offset"],
                "impact_error": lane["impact_error"],
                "reason": lane["reason"],
            }
        releases.append({"bay_id": bay["id"], "tool_id": tool_id, "tick": global_tick, "contact": lane["contact"]})
    return {"passed": True, "ticks": global_tick, "releases": releases, "stalled_bay": None, "miss_offset": 0.0, "impact_error": None, "reason": "final receiver contact"}


def _same_contact(first: Any, second: Any) -> bool:
    return isinstance(first, list) and isinstance(second, list) and len(first) == len(second) == 2 and all(_close(a, b, 0.035) for a, b in zip(first, second, strict=True))


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    challenge = str(ground_truth.get("challenge_id") or "")
    if str(payload.get("mechanic_id") or "") != MECHANIC_ID or str(ground_truth.get("mechanic_id") or "") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    if not challenge or str(payload.get("challenge_id") or "") != challenge or str(public_state.get("challenge_id") or "") != challenge:
        return _fail("stale challenge")
    task_id = str(ground_truth.get("task_id") or "")
    if not task_id or str(payload.get("task_id") or "") != task_id:
        return _fail("task identity mismatch")
    truth_condition = ground_truth.get("control_condition")
    if truth_condition != public_state.get("control_condition"):
        return _fail("public interaction condition differs from Rube contract")
    interaction = str((truth_condition or {}).get("interaction") or "full")
    place_source = {"simplified": "bay_place_button", "full": "direct_drag"}.get(interaction)
    rotate_source = {"simplified": "rotation_buttons", "full": "direct_right_click"}.get(interaction)
    if place_source is None or rotate_source is None:
        return _fail("invalid interaction condition")
    for field in ("task_id", "stage", "bays", "tools", "guide_mode", "feedback_mode", "trail_mode", "contract"):
        if public_state.get(field) != ground_truth.get(field):
            return _fail(f"public/private Rube {field} contract skew")
    try:
        bays = {str(item["id"]): item for item in ground_truth["bays"]}
        tools = {str(item["id"]): item for item in ground_truth["tools"]}
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"invalid Rube contract: {exc}")

    events = payload.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 1600:
        return _fail("Rube transcript missing or outside limits")
    placements: dict[str, dict[str, Any]] = {}
    active = False
    need_rewind = False
    terminal_success = False
    attempt = 0
    rewinds = 0
    pending_run: dict[str, Any] | None = None
    pending_release_index = 0
    pending_bell = False
    last_sequence: list[str] = []
    last_ticks = 0

    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return _fail(f"event {sequence} sequence mismatch")
        kind = str(event.get("kind") or "")
        if kind == "drop_rejected":
            if interaction != "full" or active or need_rewind or terminal_success or event.get("input_source") != place_source:
                return _fail("rejected drop used the wrong surface or phase")
            tool_id = str(event.get("tool_id") or "")
            gesture = _drag_gesture(event.get("gesture"), tool_id)
            if tool_id not in tools or gesture is None:
                return _fail("rejected drop has no valid raw drag evidence")
            if any(_inside_work_zone(gesture["release"], bay) for bay in bays.values()):
                return _fail("rejected drop ended inside a visible station")
            if gesture["origin"] == "rack":
                if gesture["start"] is not None:
                    return _fail("rack drag invented a canvas start")
            else:
                previous = placements.get(tool_id)
                if previous is None or previous["bay_id"] == "unassigned" or gesture["start"] is None:
                    return _fail("canvas drag did not start on a placed deflector")
                if math.dist(gesture["start"], previous["pose"][:2]) > 0.06 or math.dist(gesture["samples"][0], gesture["start"]) > 0.06:
                    return _fail("canvas drag start disagrees with the placed deflector")
            continue
        if kind == "place":
            if active or need_rewind or terminal_success or event.get("input_source") != place_source:
                return _fail("placement used the wrong surface or phase")
            tool_id, bay_id = str(event.get("tool_id") or ""), str(event.get("bay_id") or "")
            pose = _pose(event.get("pose"))
            if tool_id not in tools or bay_id not in bays or pose is None:
                return _fail("invalid deflector placement")
            anchor = bays[bay_id]["anchor"]
            if math.hypot(pose[0] - float(anchor[0]), pose[1] - float(anchor[1])) > float(ground_truth["contract"]["snap_position_tolerance"]):
                return _fail("deflector placement did not snap to the visible station")
            previous = placements.get(tool_id)
            if interaction == "full":
                gesture = _drag_gesture(event.get("gesture"), tool_id)
                if gesture is None or not _inside_work_zone(gesture["release"], bays[bay_id]):
                    return _fail("direct drag did not end inside the claimed visible station")
                if gesture["origin"] == "rack":
                    if gesture["start"] is not None:
                        return _fail("rack drag invented a canvas start")
                else:
                    if previous is None or previous["bay_id"] == "unassigned" or gesture["start"] is None:
                        return _fail("canvas drag did not start on a placed deflector")
                    if math.dist(gesture["start"], previous["pose"][:2]) > 0.06 or math.dist(gesture["samples"][0], gesture["start"]) > 0.06:
                        return _fail("canvas drag start disagrees with the placed deflector")
            elif event.get("gesture") is not None:
                return _fail("button placement invented a drag gesture")
            expected_angle = 45.0 if previous is None else float(previous["pose"][2])
            if not _close((pose[2] - expected_angle) % 360, 0.0, 0.01) and not _close((pose[2] - expected_angle) % 360, 360.0, 0.01):
                return _fail("placement invented a deflector angle without a rotation input")
            for other in placements.values():
                if other["bay_id"] == bay_id and other["tool_id"] != tool_id:
                    other["bay_id"] = "unassigned"
            placements[tool_id] = {"tool_id": tool_id, "bay_id": bay_id, "pose": pose}
            continue
        if kind == "rotate":
            if active or need_rewind or terminal_success or event.get("input_source") != rotate_source:
                return _fail("rotation used the wrong surface or phase")
            tool_id = str(event.get("tool_id") or "")
            pose = _pose(event.get("pose"))
            try:
                delta = float(event.get("delta_degrees"))
            except (TypeError, ValueError):
                return _fail("invalid deflector rotation")
            prior = placements.get(tool_id)
            if prior is None or pose is None or abs(abs(delta) - float(ground_truth["contract"]["rotation_step_deg"])) > 0.001:
                return _fail("invalid five-degree deflector rotation")
            if math.hypot(pose[0] - prior["pose"][0], pose[1] - prior["pose"][1]) > 0.05 or not _close((pose[2] - prior["pose"][2]) % 360, delta % 360, 0.01):
                return _fail("rotation trace disagrees with the placed deflector")
            prior["pose"] = pose
            continue
        if kind == "run_start":
            if active or need_rewind or terminal_success:
                return _fail("rollout started in an invalid phase")
            attempt += 1
            if event.get("attempt") != attempt:
                return _fail("rollout attempt counter mismatch")
            normalized = {tool_id: {"bay_id": item["bay_id"], "pose": item["pose"]} for tool_id, item in placements.items()}
            pending_run = replay_run(public_state, normalized)
            pending_release_index = 0
            pending_bell = False
            last_sequence = []
            active = True
            continue
        if kind == "release":
            if not active or pending_run is None or pending_release_index >= len(pending_run["releases"]):
                return _fail("release outside an independently replayed rollout")
            expected = pending_run["releases"][pending_release_index]
            if event.get("bay_id") != expected["bay_id"] or event.get("tool_id") != expected["tool_id"] or event.get("tick") != expected["tick"] or not _same_contact(event.get("contact"), expected["contact"]):
                return _fail("reported release disagrees with circle-segment flight replay")
            last_sequence.append(f"release:{expected['bay_id']}")
            pending_release_index += 1
            continue
        if kind == "bell":
            if not active or pending_run is None or not pending_run["passed"] or pending_release_index != len(pending_run["releases"]) or event.get("tick") != pending_run["ticks"]:
                return _fail("bell rang before the independently replayed chain completed")
            if pending_bell:
                return _fail("bell event duplicated")
            pending_bell = True
            last_sequence.append("bell:ring")
            continue
        if kind == "rollout_end":
            if not active or pending_run is None:
                return _fail("rollout ended outside an active replay")
            if event.get("tick") != pending_run["ticks"] or event.get("bell_rung") is not pending_run["passed"] or event.get("stalled_bay") != pending_run["stalled_bay"]:
                return _fail("rollout terminal state disagrees with independent flight replay")
            if pending_release_index != len(pending_run["releases"]) or pending_bell is not pending_run["passed"]:
                return _fail("visible release ledger is incomplete")
            expected_miss = pending_run["miss_offset"]
            reported_miss = event.get("miss_offset")
            if expected_miss is None:
                if reported_miss is not None:
                    return _fail("rollout invented a receiver miss offset")
            elif not _close(reported_miss, expected_miss, 0.035):
                return _fail("visible miss trace disagrees with replay")
            expected_impact = pending_run["impact_error"]
            reported_impact = event.get("impact_error")
            if expected_impact is None:
                if reported_impact is not None:
                    return _fail("rollout invented a receiver impact error")
            elif not _close(reported_impact, expected_impact, 0.035):
                return _fail("visible impact response disagrees with replay")
            active = False
            last_ticks = int(pending_run["ticks"])
            terminal_success = bool(pending_run["passed"])
            need_rewind = not terminal_success
            pending_run = None
            continue
        if kind == "rewind":
            if active or terminal_success or not need_rewind:
                return _fail("rewind outside a failed rollout")
            rewinds += 1
            need_rewind = False
            continue
        return _fail(f"event {sequence} has unknown kind")

    normalized_payload_placements = payload.get("placements")
    expected_placements = {tool_id: {"bay_id": item["bay_id"], "pose": item["pose"]} for tool_id, item in sorted(placements.items())}
    if normalized_payload_placements != expected_placements:
        return _fail("submitted placements disagree with replay")
    summaries = {
        "release_sequence": last_sequence,
        "bell_rung": terminal_success,
        "rollout_ticks": last_ticks,
        "attempts": attempt,
        "rewinds": rewinds,
        "physics_engine": ground_truth["contract"]["physics_engine"],
    }
    for field, value in summaries.items():
        if payload.get(field) != value:
            return _fail(f"submitted {field} disagrees with causal replay")
    passed = terminal_success and not active and not need_rewind and last_sequence == ground_truth["expected_release_sequence"]
    return {
        "graded": True,
        "passed": passed,
        "score": 100 if passed else 0,
        "feedback": f"Rube flight replay: {len(last_sequence) - (1 if terminal_success else 0)}/{len(bays)} receivers; attempts {attempt}; rewinds {rewinds}; ticks {last_ticks}; bell {'rang' if terminal_success else 'silent'}",
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {"oracle_by_bay": ground_truth.get("oracle_by_bay") or {}}
