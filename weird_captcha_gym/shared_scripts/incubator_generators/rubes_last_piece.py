from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "rubes_last_piece"
STAGE = {"width": 760, "height": 440}
TOOL_SPECS = (
    {"kind": "brass_vane", "glyph": "BR", "color": "#f3a85f", "length": 72, "thickness": 9, "restitution": 0.78, "facet_deg": -4.0},
    {"kind": "jade_spring", "glyph": "JA", "color": "#73d9a3", "length": 80, "thickness": 8, "restitution": 0.88, "facet_deg": -2.0},
    {"kind": "cobalt_fin", "glyph": "CO", "color": "#76a9ff", "length": 66, "thickness": 7, "restitution": 0.98, "facet_deg": 0.0},
    {"kind": "ivory_cam", "glyph": "IV", "color": "#eadfc3", "length": 86, "thickness": 10, "restitution": 1.08, "facet_deg": 2.0},
    {"kind": "rose_notch", "glyph": "RO", "color": "#ee829d", "length": 76, "thickness": 8, "restitution": 1.18, "facet_deg": 4.0},
)
DEFAULTS = {
    "link_count": 3,
    "decoy_count": 1,
    "receiver_radius": 14,
    "wind_strength": 0.007,
    "guide_mode": "station",
    "feedback_mode": "link",
    "trail_mode": "persistent",
    "lane_timeout_ticks": 88,
    "impact_tolerance": 0.06,
}


def _seed_int(seed: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{MECHANIC_ID}|{seed}".encode()).digest()[:8], "big")


def _integer(parameters: dict[str, Any], key: str, default: int, low: int, high: int) -> int:
    value = int(parameters.get(key, default))
    if not low <= value <= high:
        raise ValueError(f"{key} outside supported range")
    return value


def _number(parameters: dict[str, Any], key: str, default: float, low: float, high: float) -> float:
    value = float(parameters.get(key, default))
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{key} outside supported range")
    return value


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
        target_speed = bay.get("impact_speed")
        if target_speed is None:
            receiver_success = True
        else:
            impact_error = contact_speed - float(target_speed)
            ball["impact_error"] = impact_error
            receiver_success = abs(impact_error) <= float(bay["impact_tolerance"])
    if not ball.get("crossing") and first[0] < receiver[0] <= next_point[0]:
        amount = (receiver[0] - first[0]) / max(1e-9, next_point[0] - first[0])
        ball["crossing"] = [receiver[0], first[1] + (next_point[1] - first[1]) * amount]
    return receiver_success


def _flight_to_x(bay: dict[str, Any], tool: dict[str, Any], pose: list[float], contract: dict[str, Any]) -> tuple[float, int, float]:
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
        _step_ball(ball, bay, tool, pose, contract)
        if ball.get("crossing"):
            return float(ball["crossing"][1]), int(ball["tick"]), math.hypot(float(ball["vx"]), float(ball["vy"]))
    raise ValueError("seeded Rube oracle does not cross the receiver plane")


def _flight_contact_speed(bay: dict[str, Any], tool: dict[str, Any], pose: list[float], contract: dict[str, Any]) -> float:
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
        if _step_ball(ball, bay, tool, pose, contract):
            return float(ball["impact_speed"])
    raise ValueError("seeded Rube oracle does not make geometric receiver contact")


def _variant(base: dict[str, Any], index: int) -> dict[str, Any]:
    result = dict(base)
    result["kind"] = f"{base['kind']}_{'short' if index % 2 == 0 else 'hard'}"
    result["glyph"] = f"{base['glyph']}·"
    result["length"] = int(base["length"]) - (12 if index % 2 == 0 else 4)
    result["restitution"] = round(max(0.68, min(1.24, float(base["restitution"]) + (0.09 if index % 2 == 0 else -0.08))), 3)
    result["facet_deg"] = float(base["facet_deg"]) + (3.0 if index % 2 == 0 else -3.0)
    return result


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = task.get("_control_condition")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    link_count = _integer(parameters, "link_count", DEFAULTS["link_count"], 1, 5)
    decoy_count = _integer(parameters, "decoy_count", DEFAULTS["decoy_count"], 0, 3)
    receiver_radius = _integer(parameters, "receiver_radius", DEFAULTS["receiver_radius"], 8, 28)
    wind_strength = _number(parameters, "wind_strength", DEFAULTS["wind_strength"], 0.0, 0.02)
    lane_timeout_ticks = _integer(parameters, "lane_timeout_ticks", DEFAULTS["lane_timeout_ticks"], 60, 130)
    impact_tolerance = _number(parameters, "impact_tolerance", DEFAULTS["impact_tolerance"], 0.04, 0.25)
    guide_mode = str(parameters.get("guide_mode") or DEFAULTS["guide_mode"])
    feedback_mode = str(parameters.get("feedback_mode") or DEFAULTS["feedback_mode"])
    trail_mode = str(parameters.get("trail_mode") or DEFAULTS["trail_mode"])
    if guide_mode not in {"angle_ticks", "station"}:
        raise ValueError("unsupported Rube guide mode")
    if feedback_mode not in {"exact", "link", "first_stall", "generic"}:
        raise ValueError("unsupported Rube feedback mode")
    if trail_mode not in {"persistent", "last", "live"}:
        raise ValueError("unsupported Rube trail mode")

    rng = random.Random(_seed_int(seed))
    base_order = list(TOOL_SPECS)
    rng.shuffle(base_order)
    expected_specs = base_order[:link_count]
    specs = [dict(spec) for spec in expected_specs]
    for index in range(decoy_count):
        specs.append(_variant(base_order[(link_count + index) % len(base_order)], index))

    tools: list[dict[str, Any]] = []
    for index, spec in enumerate(specs):
        tools.append({"id": f"deflector-{index + 1}-{spec['kind']}", **spec, "rack_order": 0})
    rng.shuffle(tools)
    for index, tool in enumerate(tools):
        tool["rack_order"] = index

    contract = {
        "ball_radius": 9,
        "initial_velocity": [0.0, 4.2],
        "flight_drag": 0.998,
        "lane_timeout_ticks": lane_timeout_ticks,
        "maximum_rollout_ticks": lane_timeout_ticks * link_count,
        "snap_position_tolerance": 0.51,
        "rotation_step_deg": 5,
        "allowed_angles_deg": list(range(25, 71, 5)),
        "physics_engine": "rube-deflector-physics@2",
    }
    if link_count == 1:
        lane_ys = [220.0]
    else:
        top, bottom = 50.0, 390.0
        lane_ys = [round(top + index * (bottom - top) / (link_count - 1), 3) for index in range(link_count)]
    bays: list[dict[str, Any]] = []
    oracle_by_bay: dict[str, dict[str, Any]] = {}
    lane_letters = list("ABCDE")
    for index, (lane_y, spec) in enumerate(zip(lane_ys, expected_specs, strict=True)):
        bay_id = f"lane-{index + 1}"
        anchor = [300.0 + rng.choice((-4.0, 0.0, 4.0)), lane_y]
        launcher = [anchor[0], lane_y - 43.0]
        receiver_x = 470.0 + rng.choice((-8.0, 0.0, 8.0))
        wind_y = 0.0 if wind_strength == 0 else round(rng.choice((-1.0, 1.0)) * wind_strength * rng.choice((0.8, 1.0, 1.2)), 5)
        provisional = {
            "id": bay_id,
            "label": f"LINK {lane_letters[index]}",
            "sequence": index + 1,
            "anchor": anchor,
            "launcher": launcher,
            "receiver": [receiver_x, lane_y],
            "receiver_radius": receiver_radius,
            "impact_tolerance": impact_tolerance,
            "wind_y": wind_y,
            "wind_phase": round(rng.random() * math.tau, 6),
            "work_zone": [anchor[0] - 54.0, lane_y - 38.0, 108.0, 76.0],
        }
        candidate_angles = [45.0, 50.0, 55.0, 40.0, 35.0]
        rng.shuffle(candidate_angles)
        chosen: tuple[float, float, int, float] | None = None
        for angle in candidate_angles:
            pose = [anchor[0], anchor[1], angle]
            crossing_y, crossing_tick, impact_speed = _flight_to_x(provisional, spec, pose, contract)
            if abs(crossing_y - lane_y) <= 29.0:
                chosen = (angle, crossing_y, crossing_tick, impact_speed)
                break
        if chosen is None:
            raise AssertionError("no human-sized seeded deflector trajectory")
        angle, receiver_y, crossing_tick, impact_speed = chosen
        provisional["receiver"][1] = round(receiver_y, 3)
        impact_speed = _flight_contact_speed(provisional, spec, [anchor[0], anchor[1], angle], contract)
        provisional["impact_speed"] = round(impact_speed, 3)
        bays.append(provisional)
        tool_id = next(tool["id"] for tool in tools if tool["kind"] == spec["kind"])
        oracle_by_bay[bay_id] = {
            "tool_id": tool_id,
            "pose": [anchor[0], anchor[1], angle],
            "crossing_tick": crossing_tick,
        }

    task_id = str(task.get("id") or "rubes_last_piece_seed_0001@0.1")
    condition_token = f"|d{condition['difficulty']}|{task_id}" if condition else "|baseline"
    challenge_id = hashlib.sha256(f"{MECHANIC_ID}|{seed}{condition_token}".encode()).hexdigest()[:12]
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Complete the serial deflector chain. Run it, study the moving traces, rewind, and revise until the final bell rings.",
        "submit_label": "CERTIFY THE BELL",
        "stage": STAGE,
        "bays": bays,
        "tools": tools,
        "guide_mode": guide_mode,
        "feedback_mode": feedback_mode,
        "trail_mode": trail_mode,
        "contract": contract,
        "generator": {"name": "serial_deflector_bench_v3", "variant_count": 38_880_000_000},
        "clearance_audit": {"lane_spacing_min": 85, "receiver_clearance": 28, "rack_canvas_separation": 22},
        "asset_manifest": "shared_runtime/assets/provenance/rubes_last_piece_v0.json",
    }
    truth = {
        **copy.deepcopy(public),
        "seed": seed,
        "oracle_by_bay": oracle_by_bay,
        "expected_release_sequence": [f"release:{bay['id']}" for bay in bays] + ["bell:ring"],
    }
    if condition:
        public["control_condition"] = copy.deepcopy(condition)
        truth["control_condition"] = copy.deepcopy(condition)
    assert len(bays) == link_count and len(tools) == link_count + decoy_count
    assert set(oracle_by_bay) == {bay["id"] for bay in bays}
    assert "oracle_by_bay" not in public
    return public, truth
