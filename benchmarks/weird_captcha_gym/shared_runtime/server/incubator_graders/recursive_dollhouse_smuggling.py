from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "recursive_dollhouse_smuggling"


def _inverse(view: dict[str, Any], screen: list[float]) -> list[float]:
    matrix, origin = view["matrix"], view["origin"]
    a, b, c, d = float(matrix[0][0]), float(matrix[0][1]), float(matrix[1][0]), float(matrix[1][1])
    determinant = a * d - b * c
    u, v = float(screen[0]) - float(origin[0]), float(screen[1]) - float(origin[1])
    return [(d * u - b * v) / determinant, (-c * u + a * v) / determinant]


def _inside(point: list[float], center: list[float], size: list[float]) -> bool:
    return abs(point[0] - center[0]) <= size[0] / 2 and abs(point[1] - center[1]) <= size[1] / 2


def _contained(inner_center: list[float], inner_size: list[float], outer_center: list[float], outer_size: list[float]) -> bool:
    return abs(inner_center[0] - outer_center[0]) + inner_size[0] / 2 <= outer_size[0] / 2 + 1e-6 and abs(inner_center[1] - outer_center[1]) + inner_size[1] / 2 <= outer_size[1] / 2 + 1e-6


def _overlap(first_center: list[float], first_size: list[float], second_center: list[float], second_size: list[float]) -> bool:
    return abs(first_center[0] - second_center[0]) < (first_size[0] + second_size[0]) / 2 - 1e-6 and abs(first_center[1] - second_center[1]) < (first_size[1] + second_size[1]) / 2 - 1e-6


def _gates(contract: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    primary = contract.get("gate")
    if isinstance(primary, dict):
        result.append(primary)
    extra = contract.get("additional_gates") or []
    if not isinstance(extra, list) or not all(isinstance(item, dict) for item in extra):
        raise ValueError("additional gates are malformed")
    result.extend(extra)
    ids = [str(item.get("id") or "") for item in result]
    if any(not item for item in ids) or len(set(ids)) != len(ids):
        raise ValueError("gate identities are malformed")
    return result


def _parking(gate: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any] | None:
    parking = gate.get("parking") or (contract.get("parking") if gate.get("id") == "gate" else None)
    return parking if isinstance(parking, dict) else None


def _blocker(
    entity: str,
    gate_id: str | None,
    start: list[float],
    end: list[float],
    parcel_scale: int,
    parcel_center: list[float],
    gate_centers: dict[str, list[float]],
    gates: dict[str, dict[str, Any]],
    contract: dict[str, Any],
) -> str | None:
    parcel, room = contract["parcel"], contract["room"]
    if entity == "gate":
        if gate_id not in gates:
            return "unknown-gate"
        size = gates[gate_id]["size"]
    else:
        size = parcel["sizes"][parcel_scale]
    distance = math.hypot(end[0] - start[0], end[1] - start[1])
    steps = max(1, math.ceil(distance / float(contract["requirements"]["collision_substep"])))
    for index in range(1, steps + 1):
        amount = index / steps
        center = [start[0] + (end[0] - start[0]) * amount, start[1] + (end[1] - start[1]) * amount]
        if center[0] - size[0] / 2 < 0 or center[0] + size[0] / 2 > room["width"] or center[1] - size[1] / 2 < 0 or center[1] + size[1] / 2 > room["depth"]:
            return "room-boundary"
        for wall in contract["walls"]:
            if _overlap(center, size, wall["center"], wall["size"]):
                return str(wall["id"])
        if entity == "parcel":
            for other_id, gate in gates.items():
                if _overlap(center, size, gate_centers[other_id], gate["size"]):
                    return other_id
        else:
            if _overlap(center, size, parcel_center, parcel["sizes"][parcel_scale]):
                return "parcel"
            for other_id, gate in gates.items():
                if other_id != gate_id and _overlap(center, size, gate_centers[other_id], gate["size"]):
                    return other_id
    return None


def _bound(public: dict[str, Any], truth: dict[str, Any]) -> str | None:
    fields = (
        "task_id", "room", "views", "walls", "gate", "parking", "additional_gates", "portals", "parcel", "bay", "requirements", "control_condition",
    )
    for field in fields:
        if public.get(field) != truth.get(field):
            return field
    return None


def _condition(public: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any] | None:
    truth_condition = truth.get("control_condition")
    if truth_condition is None:
        return None if public.get("control_condition") is None else {}
    if not isinstance(truth_condition, dict) or public.get("control_condition") != truth_condition:
        return {}
    if int(truth_condition.get("difficulty") or 0) not in {1, 2, 3, 4, 5}:
        return {}
    if truth_condition.get("interaction") not in {"simplified", "full"} or truth_condition.get("real_time") != "live":
        return {}
    if not isinstance(truth_condition.get("difficulty_parameters"), dict):
        return {}
    return truth_condition


def _event_surface(event: dict[str, Any], condition: dict[str, Any] | None, *, expected_proxy: str | None = None) -> bool:
    if condition is None:
        return True
    expected = "route_card" if condition["interaction"] == "simplified" else "direct_canvas"
    if event.get("input_source") != expected:
        return False
    if expected_proxy is not None and event.get("proxy_action") != expected_proxy:
        return False
    return True


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    challenge, task_id = str(ground_truth.get("challenge_id") or ""), str(ground_truth.get("task_id") or "")
    if str(payload.get("mechanic_id") or "") != MECHANIC_ID or str(ground_truth.get("mechanic_id") or "") != MECHANIC_ID:
        return {"graded": True, "passed": False, "feedback": "mechanic mismatch"}
    if not challenge or str(payload.get("challenge_id") or "") != challenge or str(public_state.get("challenge_id") or "") != challenge:
        return {"graded": True, "passed": False, "feedback": "stale challenge"}
    if not task_id or str(payload.get("task_id") or "") != task_id:
        return {"graded": True, "passed": False, "feedback": "task identity mismatch"}
    skew = _bound(public_state, ground_truth)
    if skew:
        return {"graded": True, "passed": False, "feedback": f"public/private dollhouse {skew} contract skew"}
    condition = _condition(public_state, ground_truth)
    if condition == {}:
        return {"graded": True, "passed": False, "feedback": "controlled dollhouse condition mismatch"}
    try:
        views = {str(item["id"]): item for item in ground_truth["views"]}
        portals = {str(item["id"]): item for item in ground_truth["portals"]}
        parcel = ground_truth["parcel"]
        gates = {str(item["id"]): item for item in _gates(ground_truth)}
        requirements = ground_truth["requirements"]
        if set(views) != {"mini", "human", "giant"} or len(portals) != 2:
            raise ValueError("three views and two nested frames required")
        required_portals = list(requirements.get("required_portal_ids") or ["frame-mini-human", "frame-human-giant"])
        required_gates = list(requirements.get("required_gate_ids") or (["gate"] if "gate" in gates else []))
        required_views = list(requirements.get("required_views") or ["mini", "human", "giant"])
        if any(item not in portals for item in required_portals) or any(item not in gates for item in required_gates) or any(item not in views for item in required_views):
            raise ValueError("required route identities are malformed")
    except (KeyError, TypeError, ValueError) as exc:
        return {"graded": True, "passed": False, "feedback": f"invalid dollhouse contract: {exc}"}
    events = payload.get("events")
    if not isinstance(events, list) or not (1 <= len(events) <= 1800):
        return {"graded": True, "passed": False, "feedback": "cross-scale transcript missing or outside limits"}

    initial_parcel = list(parcel["initial_center"])
    initial_gate_centers = {gate_id: list(gate["center"]) for gate_id, gate in gates.items()}
    initial_parked = {
        gate_id
        for gate_id, gate in gates.items()
        if bool(gate.get("initially_parked")) and (parking := _parking(gate, ground_truth)) is not None and _contained(gate["center"], gate["size"], parking["center"], parking["size"])
    }
    parcel_center, scale = list(initial_parcel), int(parcel["initial_scale"])
    gate_centers = {gate_id: list(center) for gate_id, center in initial_gate_centers.items()}
    drag: dict[str, Any] | None = None
    transitions: list[str] = []
    views_used: set[str] = set()
    parked_ids = set(initial_parked)
    collisions = resets = 0
    delivered = terminal = False

    for sequence, event in enumerate(events, 1):
        if terminal:
            return {"graded": True, "passed": False, "feedback": "interaction continued after nested delivery"}
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return {"graded": True, "passed": False, "feedback": f"event {sequence} sequence mismatch"}
        kind = str(event.get("kind") or "")
        if kind == "drag_start":
            entity, view_id, screen, claimed = str(event.get("entity") or ""), str(event.get("view_id") or ""), event.get("screen"), event.get("canonical")
            gate_id = str(event.get("gate_id") or "") if entity == "gate" else None
            proxy_action = f"park:{gate_id}" if entity == "gate" else f"carry:{scale}"
            if drag is not None or view_id not in views or entity not in {"parcel", "gate"} or not isinstance(screen, list) or not isinstance(claimed, list) or not _event_surface(event, condition, expected_proxy=proxy_action if condition and condition["interaction"] == "simplified" else None):
                return {"graded": True, "passed": False, "feedback": "invalid cross-scale drag start"}
            if entity == "gate" and gate_id not in gates:
                return {"graded": True, "passed": False, "feedback": "unknown linked gate"}
            mapped = _inverse(views[view_id], screen)
            if math.hypot(mapped[0] - float(claimed[0]), mapped[1] - float(claimed[1])) > float(requirements["inverse_tolerance"]):
                return {"graded": True, "passed": False, "feedback": "screen/canonical inverse transform mismatch"}
            if entity == "gate":
                gate = gates[gate_id]
                center, size = gate_centers[gate_id], gate["size"]
                if view_id != gate["movable_in_view"]:
                    return {"graded": True, "passed": False, "feedback": "gate manipulated through the wrong room scale"}
            else:
                center, size = parcel_center, parcel["sizes"][scale]
                if int(views[view_id]["index"]) != scale:
                    return {"graded": True, "passed": False, "feedback": "parcel manipulated through the wrong room scale"}
            if not _inside(mapped, center, size):
                return {"graded": True, "passed": False, "feedback": "drag ray missed canonical footprint"}
            drag = {"entity": entity, "gate_id": gate_id, "view": view_id, "offset": [mapped[0] - center[0], mapped[1] - center[1]], "last_screen": [float(screen[0]), float(screen[1])], "proxy_action": proxy_action}
            views_used.add(view_id)
            continue
        if kind == "drag_sample":
            if drag is None:
                return {"graded": True, "passed": False, "feedback": "orphan cross-scale drag sample"}
            screen, claimed, center_claim = event.get("screen"), event.get("canonical"), event.get("center")
            if event.get("entity") != drag["entity"] or event.get("view_id") != drag["view"] or event.get("gate_id") != drag["gate_id"] or not all(isinstance(item, list) and len(item) == 2 for item in (screen, claimed, center_claim)) or not _event_surface(event, condition, expected_proxy=drag["proxy_action"] if condition and condition["interaction"] == "simplified" else None):
                return {"graded": True, "passed": False, "feedback": "malformed cross-scale drag sample"}
            if math.hypot(float(screen[0]) - drag["last_screen"][0], float(screen[1]) - drag["last_screen"][1]) > float(requirements["max_screen_step"]):
                return {"graded": True, "passed": False, "feedback": "sparse cross-view pointer teleport"}
            mapped = _inverse(views[drag["view"]], screen)
            expected_center = [mapped[0] - drag["offset"][0], mapped[1] - drag["offset"][1]]
            if math.hypot(mapped[0] - float(claimed[0]), mapped[1] - float(claimed[1])) > float(requirements["inverse_tolerance"]) or math.hypot(expected_center[0] - float(center_claim[0]), expected_center[1] - float(center_claim[1])) > float(requirements["inverse_tolerance"]):
                return {"graded": True, "passed": False, "feedback": "cross-view canonical pose lie"}
            current = gate_centers[drag["gate_id"]] if drag["entity"] == "gate" else parcel_center
            hit = _blocker(drag["entity"], drag["gate_id"], current, expected_center, scale, parcel_center, gate_centers, gates, ground_truth)
            accepted = hit is None
            if (event.get("accepted") is True) != accepted or (None if accepted else str(event.get("blocker") or "")) != hit:
                return {"graded": True, "passed": False, "feedback": "visible collision/containment disagrees with canonical replay"}
            if accepted:
                if drag["entity"] == "gate":
                    gate_centers[drag["gate_id"]] = expected_center
                else:
                    parcel_center = expected_center
            else:
                collisions += 1
            drag["last_screen"] = [float(screen[0]), float(screen[1])]
            continue
        if kind == "drag_end":
            center_claim = event.get("center")
            current = gate_centers[drag["gate_id"]] if drag and drag["entity"] == "gate" else parcel_center
            if drag is None or event.get("entity") != drag["entity"] or event.get("gate_id") != drag["gate_id"] or not isinstance(center_claim, list) or not _event_surface(event, condition, expected_proxy=drag["proxy_action"] if condition and condition["interaction"] == "simplified" else None) or math.hypot(float(center_claim[0]) - current[0], float(center_claim[1]) - current[1]) > 0.12:
                return {"graded": True, "passed": False, "feedback": "drag release disagrees with canonical body"}
            drag = None
            continue
        if kind == "gate_parked":
            gate_id = str(event.get("gate_id") or "")
            parking = _parking(gates.get(gate_id, {}), ground_truth)
            if drag is not None or gate_id in parked_ids or parking is None or not _event_surface(event, condition, expected_proxy=f"park:{gate_id}" if condition and condition["interaction"] == "simplified" else None) or not _contained(gate_centers[gate_id], gates[gate_id]["size"], parking["center"], parking["size"]):
                return {"graded": True, "passed": False, "feedback": "gate parking claim lacks full containment"}
            parked_ids.add(gate_id)
            continue
        if kind == "portal_transition":
            portal_id = str(event.get("portal_id") or "")
            portal = portals.get(portal_id)
            needed_gates = list((portal or {}).get("requires_gate_ids") or (["gate"] if portal and int(portal["from_scale"]) == 0 and "gate" in gates else []))
            if drag is not None or not portal or event.get("from_scale") != scale or event.get("to_scale") != scale + 1 or int(portal["from_scale"]) != scale or not _event_surface(event, condition, expected_proxy=f"carry:{scale}" if condition and condition["interaction"] == "simplified" else None) or not _contained(parcel_center, parcel["sizes"][scale], portal["center"], portal["size"]):
                return {"graded": True, "passed": False, "feedback": "portal teleport or wrong-scale transfer"}
            if any(gate_id not in parked_ids for gate_id in needed_gates):
                return {"graded": True, "passed": False, "feedback": "nested route was not physically opened through its linked projection"}
            transitions.append(portal_id)
            scale += 1
            continue
        if kind == "delivery":
            if drag is not None or delivered or scale != int(ground_truth["bay"]["scale"]) or not _event_surface(event, condition, expected_proxy=f"carry:{scale}" if condition and condition["interaction"] == "simplified" else None) or not _contained(parcel_center, parcel["sizes"][scale], ground_truth["bay"]["center"], ground_truth["bay"]["size"]):
                return {"graded": True, "passed": False, "feedback": "final bay fit or parcel scale is invalid"}
            delivered = terminal = True
            continue
        if kind == "reset":
            if drag is not None or terminal:
                return {"graded": True, "passed": False, "feedback": "reset during active drag or after delivery"}
            parcel_center, scale = list(initial_parcel), int(parcel["initial_scale"])
            gate_centers = {gate_id: list(center) for gate_id, center in initial_gate_centers.items()}
            transitions.clear()
            views_used.clear()
            parked_ids = set(initial_parked)
            delivered = False
            resets += 1
            continue
        return {"graded": True, "passed": False, "feedback": f"event {sequence} has unknown kind"}

    primary_parked = "gate" in parked_ids
    summary = {
        "delivered": delivered,
        "parcel_scale": scale,
        "portal_ids": transitions,
        "gate_parked": primary_parked,
        "collisions": collisions,
        "resets": resets,
        "views_used": sorted(views_used),
        "parcel_center": [round(value, 3) for value in parcel_center],
        "gate_center": [round(value, 3) for value in gate_centers.get("gate", [0, 0])],
    }
    if condition is not None:
        summary["gate_parked_ids"] = sorted(parked_ids)
    for field, value in summary.items():
        if field in {"parcel_center", "gate_center"}:
            submitted = payload.get(field)
            if not isinstance(submitted, list) or len(submitted) != 2 or math.hypot(float(submitted[0]) - value[0], float(submitted[1]) - value[1]) > 0.01:
                return {"graded": True, "passed": False, "feedback": f"submitted {field} disagrees with nested-room replay"}
        elif payload.get(field) != value:
            return {"graded": True, "passed": False, "feedback": f"submitted {field} disagrees with nested-room replay"}
    passed = delivered and transitions == required_portals and set(required_gates) <= parked_ids and views_used == set(required_views)
    gate_status = "parked" if set(required_gates) <= parked_ids else "blocking"
    return {
        "graded": True,
        "passed": passed,
        "score": 100 if passed else 0,
        "feedback": f"dollhouse replay: portals {len(transitions)}/{len(required_portals)}; views {len(views_used)}/{len(required_views)}; gate {gate_status}; collisions {collisions}; resets {resets}",
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {"solver_waypoints": ground_truth.get("solver_waypoints") or {}, "views": ground_truth.get("views") or []}
