from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "pocket_locksmith"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _close(first: Any, second: Any, tolerance: float = 0.04) -> bool:
    try:
        return math.isfinite(float(first)) and abs(float(first) - float(second)) <= tolerance
    except (TypeError, ValueError):
        return False


def _angle_error(first: float, second: float) -> float:
    return abs((float(first) - float(second) + 180.0) % 360.0 - 180.0)


def _norm(vector: list[float]) -> list[float]:
    length = math.sqrt(sum(float(item) ** 2 for item in vector))
    return [float(item) / length for item in vector] if length > 1e-9 else [1.0, 0.0, 0.0]


def _cross(first: list[float], second: list[float]) -> list[float]:
    return [
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    ]


def _rotate(point: list[float], origin: list[float], axis: list[float], radians: float) -> list[float]:
    relative = [point[index] - origin[index] for index in range(3)]
    cosine = math.cos(radians)
    sine = math.sin(radians)
    cross = _cross(axis, relative)
    dot = sum(axis[index] * relative[index] for index in range(3))
    return [
        origin[index] + relative[index] * cosine + cross[index] * sine + axis[index] * dot * (1.0 - cosine)
        for index in range(3)
    ]


def forward_kinematics(base_points: list[list[float]], torsions: list[float]) -> list[list[float]]:
    points = [[float(value) for value in point] for point in base_points]
    for bond_index, angle in enumerate(torsions):
        if bond_index + 2 >= len(points):
            break
        origin = points[bond_index]
        axis = _norm([points[bond_index + 1][axis] - origin[axis] for axis in range(3)])
        for point_index in range(bond_index + 2, len(points)):
            points[point_index] = _rotate(points[point_index], origin, axis, math.radians(float(angle)))
    return points


def _perpendicular(axis: list[float], sign: float) -> list[float]:
    candidate = _cross(axis, [0.0, 1.0, 0.0])
    if math.sqrt(sum(value * value for value in candidate)) < 1e-7:
        candidate = _cross(axis, [0.0, 0.0, 1.0])
    unit = _norm(candidate)
    return [value * sign for value in unit]


def _distance(first: list[float], second: list[float]) -> float:
    return math.sqrt(sum((first[index] - second[index]) ** 2 for index in range(3)))


def _camera_point(point: list[float], camera: dict[str, Any], public: dict[str, Any]) -> tuple[float, float, float, float]:
    view = public.get("view") or {}
    target = [float(value) for value in camera.get("target", [0.22, 0.0, 0.0])]
    relative = [float(point[index]) - target[index] for index in range(3)]
    yaw = math.radians(float(camera.get("yaw", 0.0)))
    pitch = math.radians(float(camera.get("pitch", 0.0)))
    x1 = math.cos(yaw) * relative[0] + math.sin(yaw) * relative[2]
    z1 = -math.sin(yaw) * relative[0] + math.cos(yaw) * relative[2]
    y2 = math.cos(pitch) * relative[1] - math.sin(pitch) * z1
    z2 = math.sin(pitch) * relative[1] + math.cos(pitch) * z1
    depth = max(0.2, float(camera.get("distance", 7.1)) + z2)
    scale = float(view.get("focal", camera.get("focal", 570.0))) / depth
    width = float(view.get("canvas_width", 780))
    height = float(view.get("canvas_height", 480))
    return width / 2.0 + x1 * scale, height / 2.0 - y2 * scale, depth, scale


def _handle_point(public: dict[str, Any], points: list[list[float]], bond_index: int, side: float) -> list[float]:
    first, second = points[bond_index], points[bond_index + 1]
    axis = _norm([second[index] - first[index] for index in range(3)])
    midpoint = [(first[index] + second[index]) / 2.0 for index in range(3)]
    lift = float((public.get("view") or {}).get("handle_lift", 0.34))
    direction = _perpendicular(axis, side)
    return [midpoint[index] + direction[index] * lift for index in range(3)]


def handle_visible(
    public: dict[str, Any],
    points: list[list[float]],
    camera: dict[str, Any],
    bond_index: int,
    side: float,
) -> tuple[bool, tuple[float, float]]:
    handle = _handle_point(public, points, bond_index, side)
    hx, hy, hdepth, hscale = _camera_point(handle, camera, public)
    if not (math.isfinite(hx) and math.isfinite(hy) and -80 <= hx <= 860 and -80 <= hy <= 560):
        return False, (hx, hy)
    if not bool((public.get("view") or {}).get("handle_occlusion", True)):
        return True, (hx, hy)
    handle_radius = float((public.get("view") or {}).get("handle_radius", 0.23)) * hscale
    atoms = (public.get("ligand") or {}).get("atoms") or []
    for index, point in enumerate(points):
        if index in {bond_index, bond_index + 1}:
            continue
        ax, ay, adepth, ascale = _camera_point(point, camera, public)
        atom_radius = float(atoms[index].get("radius", 0.18)) * ascale if index < len(atoms) else 0.18 * ascale
        if adepth < hdepth - 0.015 and math.hypot(ax - hx, ay - hy) <= handle_radius + atom_radius * 0.82:
            return False, (hx, hy)
    return True, (hx, hy)


def _world_check(
    public: dict[str, Any],
    truth: dict[str, Any],
    torsions: list[float],
) -> dict[str, Any]:
    points = forward_kinematics(truth["base_points"], torsions)
    pocket_center = [float(value) for value in truth["pocket_center"]]
    bounds = [float(value) for value in truth["pocket_bounds"]]
    margin = float(truth.get("clearance_margin", 0.04))
    atom_radius = float(truth.get("atom_radius", 0.18))
    out_of_bounds = [
        index for index, point in enumerate(points)
        if any(abs(point[axis] - pocket_center[axis]) > bounds[axis] - atom_radius for axis in range(3))
    ]
    obstacle_clashes = []
    for obstacle in truth.get("obstacles") or []:
        center = [float(value) for value in obstacle["center"]]
        radius = float(obstacle["radius"])
        for index, point in enumerate(points):
            if _distance(point, center) < atom_radius + radius + margin:
                obstacle_clashes.append((obstacle["id"], index + 1))
    atom_clashes = []
    for first in range(len(points)):
        for second in range(first + 2, len(points)):
            if _distance(points[first], points[second]) < atom_radius * 2.0 + margin:
                atom_clashes.append((first + 1, second + 1))
    contact_hits = []
    contact_failures = []
    contact_tolerance = float(truth.get("contact_tolerance", 0.22))
    # A marked site is a visible pocket region, not a hidden atom-to-site
    # assignment.  Use the nearest connected atom for the replay record so
    # this predicate is identical to the browser's visible readiness test.
    sites = list((public.get("pocket") or {}).get("sites", []))
    atom_ids = [str(item.get("id")) for item in (public.get("ligand") or {}).get("atoms", [])]
    for site in sites:
        distances = [(_distance(point, [float(value) for value in site["center"]]), index) for index, point in enumerate(points)]
        distance, atom_index = min(distances, default=(float("inf"), -1))
        item = {
            "site_id": site["id"],
            "atom_id": atom_ids[atom_index] if 0 <= atom_index < len(atom_ids) else None,
            "distance": distance,
        }
        if distance <= contact_tolerance:
            contact_hits.append(item)
        else:
            contact_failures.append(item)
    torsion_errors = [
        _angle_error(current, target)
        for current, target in zip(torsions, truth.get("target_torsions") or [], strict=True)
    ]
    passed = (
        not out_of_bounds
        and not obstacle_clashes
        and not atom_clashes
        and not contact_failures
        and len(contact_hits) == len(sites)
    )
    return {
        "passed": passed,
        "points": points,
        "torsion_errors": torsion_errors,
        "out_of_bounds": out_of_bounds,
        "obstacle_clashes": obstacle_clashes,
        "atom_clashes": atom_clashes,
        "contact_hits": contact_hits,
        "contact_failures": contact_failures,
    }


def _same_camera(first: Any, second: dict[str, Any]) -> bool:
    return isinstance(first, dict) and all(_close(first.get(key), second.get(key), 0.06) for key in ("yaw", "pitch"))


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    if any(item.get("mechanic_id") != MECHANIC_ID for item in (payload, truth, public)):
        return _fail("mechanic mismatch")
    if payload.get("task_id") != truth.get("task_id") or payload.get("challenge_id") != truth.get("challenge_id"):
        return _fail("stale task or challenge")
    if public.get("task_id") != truth.get("task_id") or public.get("challenge_id") != truth.get("challenge_id"):
        return _fail("public state is not bound to the challenge")
    if public.get("control_condition") != truth.get("control_condition"):
        return _fail("public interaction condition differs from pocket contract")
    condition = truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "full")
    expected = {
        "simplified": {"orbit": "orbit_button", "torsion": "torsion_button"},
        "full": {"orbit": "orbit_drag", "torsion": "torsion_drag"},
    }.get(interaction)
    if expected is None:
        return _fail("invalid pocket interaction condition")
    events = payload.get("events")
    if not isinstance(events, list) or len(events) > 6000:
        return _fail("pocket transcript malformed")

    torsions = [float(value) for value in truth.get("initial_torsions") or []]
    camera = dict(public.get("camera") or {})
    points = forward_kinematics(truth["base_points"], torsions)
    certify: dict[str, Any] | None = None
    orbit_count = 0
    torsion_count = 0
    for sequence, item in enumerate(events, 1):
        if not isinstance(item, dict) or item.get("seq") != sequence:
            return _fail(f"event {sequence} sequence invalid")
        action = item.get("type")
        if action == "orbit":
            if item.get("input_source") != expected["orbit"]:
                return _fail("camera orbit uses the wrong interaction input")
            if not _same_camera(item.get("before"), camera):
                return _fail("camera orbit starts from stale view")
            delta = item.get("delta") or {}
            try:
                delta_yaw = float(delta.get("yaw"))
                delta_pitch = float(delta.get("pitch"))
            except (TypeError, ValueError):
                return _fail("camera orbit delta is invalid")
            if abs(delta_yaw) + abs(delta_pitch) < 0.1 or abs(delta_yaw) > 100 or abs(delta_pitch) > 100:
                return _fail("camera orbit delta is outside the visible gesture")
            next_camera = dict(camera)
            next_camera["yaw"] = (float(camera.get("yaw", 0.0)) + delta_yaw + 180.0) % 360.0 - 180.0
            next_camera["pitch"] = max(-72.0, min(72.0, float(camera.get("pitch", 0.0)) + delta_pitch))
            if not _same_camera(item.get("after"), next_camera):
                return _fail("camera orbit does not replay from the submitted delta")
            if interaction == "full":
                gesture = item.get("gesture") or {}
                start, end = gesture.get("start"), gesture.get("end")
                if not isinstance(start, list) or not isinstance(end, list) or len(start) != 2 or len(end) != 2:
                    return _fail("direct orbit is missing its pointer gesture")
                if abs((float(end[0]) - float(start[0])) * 0.42 - delta_yaw) > 2.2 or abs((float(end[1]) - float(start[1])) * -0.42 - delta_pitch) > 2.2:
                    return _fail("direct orbit disagrees with its pointer displacement")
            camera = next_camera
            orbit_count += 1
        elif action == "torsion":
            if item.get("input_source") != expected["torsion"]:
                return _fail("bond rotation uses the wrong interaction input")
            bond_id = str(item.get("bond_id") or "")
            if not bond_id.startswith("bond-"):
                return _fail("unknown rotatable bond")
            try:
                bond_index = int(bond_id.split("-")[-1]) - 1
            except ValueError:
                return _fail("unknown rotatable bond")
            if bond_index < 0 or bond_index >= len(torsions):
                return _fail("bond is not rotatable")
            if not _close(item.get("before"), torsions[bond_index]):
                return _fail("bond rotation starts from stale torsion")
            try:
                after = float(item.get("after"))
                side = float(item.get("side"))
            except (TypeError, ValueError):
                return _fail("bond rotation is malformed")
            if side not in {-1.0, 1.0}:
                return _fail("bond rotation side is invalid")
            step = float(truth.get("torsion_step_deg", 15.0))
            if abs(after - torsions[bond_index] - side * step) > 0.06:
                return _fail("bond rotation moved by an impossible torsion step")
            if interaction == "full":
                if not _same_camera(item.get("camera"), camera):
                    return _fail("direct torsion drag uses a stale camera")
                visible, screen = handle_visible(public, points, camera, bond_index, side)
                if not visible:
                    return _fail("direct torsion drag used a handle hidden by the ligand")
                submitted_screen = item.get("screen")
                if not isinstance(submitted_screen, list) or len(submitted_screen) != 2 or math.hypot(float(submitted_screen[0]) - screen[0], float(submitted_screen[1]) - screen[1]) > 30:
                    return _fail("direct torsion drag missed the visible curved handle")
            torsions[bond_index] = after
            points = forward_kinematics(truth["base_points"], torsions)
            torsion_count += 1
        elif action == "certify":
            certify = item
        elif action == "abandon":
            return _fail("pocket abandoned")
        else:
            return _fail(f"unknown pocket event {action!r}")

    if certify is None:
        return _fail("no fit certification was submitted")
    if payload.get("completed") is not True:
        return _fail("fit was not completed")
    result = _world_check(public, truth, torsions)
    reported = certify.get("accepted")
    if reported is not None and bool(reported) != bool(result["passed"]):
        return _fail("visible fit verdict disagrees with replay")
    if not result["passed"]:
        return _fail(
            f"fit rejected: contacts {len(result['contact_hits'])}/{len((public.get('pocket') or {}).get('sites') or [])}; "
            f"clashes {len(result['obstacle_clashes']) + len(result['atom_clashes'])}"
        )
    return {
        "graded": True,
        "passed": True,
        "feedback": f"connected key fitted {len(torsions)} rotatable bonds, {len(result['contact_hits'])} marked contacts, no pocket clashes",
        "metrics": {
            "orbit_events": orbit_count,
            "torsion_events": torsion_count,
            "contacts": len(result["contact_hits"]),
            "torsion_errors_deg": result["torsion_errors"],
        },
    }
