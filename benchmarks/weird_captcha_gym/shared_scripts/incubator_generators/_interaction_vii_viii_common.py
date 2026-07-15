from __future__ import annotations

import hashlib
import math
import random
from collections import deque
from typing import Any


ASSET_MANIFEST = "shared_runtime/assets/provenance/interaction_vii_viii_v0.json"


def _seed(seed: str, mechanic: str) -> int:
    return int(hashlib.sha256(f"{seed}|{mechanic}".encode()).hexdigest()[:16], 16)


def _identity(mechanic: str, task: dict[str, Any], seed: str) -> tuple[random.Random, dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed(seed, mechanic))
    task_id = str(task.get("id") or f"{mechanic}_seed_0001@0.1")
    challenge_id = hashlib.sha256(f"{seed}|{mechanic}".encode()).hexdigest()[:12]
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": mechanic,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "asset_manifest": ASSET_MANIFEST,
        "prompt": task.get("natural_language") or "Complete the physical verification.",
    }
    truth = {
        "mechanic_id": mechanic,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "seed": seed,
    }
    return rng, public, truth


def _angle(value: float) -> float:
    return (value % 180.0 + 180.0) % 180.0


def _mirror_angle(previous: tuple[float, float], center: tuple[float, float], following: tuple[float, float]) -> float:
    incoming = math.atan2(center[1] - previous[1], center[0] - previous[0])
    outgoing = math.atan2(following[1] - center[1], following[0] - center[0])
    normal = (incoming + outgoing) / 2.0 + math.pi / 2.0
    return round(_angle(math.degrees(normal) + 90.0), 2)


def _specular(task: dict[str, Any], seed: str):
    mechanic = "specular_lighthouse_relay"
    rng, public, truth = _identity(mechanic, task, seed)
    rounds = []
    solutions = []
    for index in range(4):
        emitter = (70.0, float(rng.randint(150, 330)))
        mirrors = [
            (250.0, float(rng.randint(80, 190))),
            (455.0, float(rng.randint(265, 395))),
            (660.0, float(rng.randint(85, 225))),
        ]
        receiver = (845.0, float(rng.randint(165, 335)))
        points = [emitter, *mirrors, receiver]
        angles = [_mirror_angle(points[i], points[i + 1], points[i + 2]) for i in range(3)]
        initial = [round(_angle(value + rng.choice((-58, -42, 37, 53))), 2) for value in angles]
        round_id = f"lamp-{index + 1}-{hashlib.sha1(f'{seed}|lamp|{index}'.encode()).hexdigest()[:5]}"
        rounds.append({
            "id": round_id,
            "emitter": list(emitter),
            "mirrors": [{"id": f"m{n + 1}", "center": list(center), "length": 118, "angle_deg": initial[n]} for n, center in enumerate(mirrors)],
            "receiver": {
                "center": list(receiver),
                "radius": 23,
                "motion_axis": "y",
                "amplitude": rng.choice((38, 42, 46)),
                "angular_rate": rng.choice((0.044, 0.048, 0.052)),
                "phase": round(rng.random() * math.tau, 5),
            },
            "angle_step_deg": 1,
            "tolerance_px": 15,
            "required_charge_ticks": 52,
            "miss_decay_ticks": 2,
        })
        solutions.append({"round_id": round_id, "angles": angles})
    public.update({
        "generator": {"name": "live_tracking_specular_relay_v2", "variant_count": 10**12},
        "rounds": rounds,
        "round_count": len(rounds),
        "palette": rng.choice(("storm-lantern", "salt-glass", "signal-oxide")),
    })
    truth.update({"rounds": rounds, "solutions": solutions, "angle_tolerance_deg": 3.25})
    return public, truth


def _wind_sim(
    plan: list[dict[str, int]],
    ticks: int,
    phase: float,
    pods: list[dict[str, Any]],
    physics: dict[str, Any],
) -> dict[str, list[tuple[float, float, int]]]:
    """Author two routes with the same shared spooling/thermal plant used by the UI."""
    commands = [0, 0, 0, 0]
    actual = [0.0, 0.0, 0.0, 0.0]
    heat = [0.0, 0.0, 0.0, 0.0]
    events: dict[int, list[dict[str, int]]] = {}
    for item in plan:
        events.setdefault(int(item["tick"]), []).append(item)
    bodies = {item["id"]: {key: float(item[key]) for key in ("x", "y", "vx", "vy")} for item in pods}
    samples: dict[str, list[tuple[float, float, int]]] = {item["id"]: [] for item in pods}
    fan_x = (205.0, 365.0, 525.0, 685.0)
    for tick in range(ticks):
        for item in events.get(tick, []):
            commands[int(item["fan"])] = int(item["power"])
        accelerations = {item["id"]: 0.006 * math.sin(tick * 0.083 + phase + float(item["gust_phase"])) for item in pods}
        for index, center in enumerate(fan_x):
            heat[index] = max(0.0, heat[index] + (float(physics["heat_rate"]) if commands[index] else -float(physics["cool_rate"])))
            if heat[index] >= float(physics["trip_heat"]):
                raise RuntimeError("authored wind plan overheated")
            actual[index] += (commands[index] - actual[index]) * float(physics["spool_rate"])
            for item in pods:
                body = bodies[item["id"]]
                influence = max(0.0, 1.0 - abs(body["x"] - center) / 112.0)
                accelerations[item["id"]] += actual[index] * float(physics["fan_accel"]) * float(item["response"]) * influence
        for item in pods:
            body = bodies[item["id"]]
            body["vy"] = (body["vy"] + accelerations[item["id"]]) * float(physics["drag"])
            body["y"] = max(35.0, min(441.0, body["y"] + body["vy"]))
            body["x"] += body["vx"]
            samples[item["id"]].append((body["x"], body["y"], tick + 1))
    return samples


def _wind(task: dict[str, Any], seed: str):
    mechanic = "wind_tunnel_seed_courier"
    rng, public, truth = _identity(mechanic, task, seed)
    phase = round(rng.random() * math.tau, 5)
    fan_x = (205, 365, 525, 685)
    pods = [
        {"id": "thistle", "x": 76.0, "y": 166.0, "vx": 2.48, "vy": 0.0, "response": 1.0, "gust_phase": 0.0, "color": "#f4c84d"},
        {"id": "acorn", "x": -142.0, "y": 314.0, "vx": 2.18, "vy": 0.0, "response": 0.72, "gust_phase": 1.7, "color": "#a85b39"},
    ]
    physics = {
        "tick_ms": 38, "ticks": 466, "phase": phase,
        "fan_accel": 0.030, "drag": 0.968, "pod_radius": 11,
        "spool_rate": 0.15, "heat_rate": 0.006, "cool_rate": 0.014,
        "trip_heat": 1.0,
    }
    plan: list[dict[str, int]] = []
    for pod in pods:
        for index, center in enumerate(fan_x):
            power = rng.choice((-1, 1))
            on_tick = max(0, round((center - 90 - float(pod["x"])) / float(pod["vx"])))
            off_tick = round((center + 76 - float(pod["x"])) / float(pod["vx"]))
            plan.extend((
                {"tick": on_tick, "fan": index, "power": power},
                {"tick": off_tick, "fan": index, "power": 0},
            ))
    plan.sort(key=lambda item: (item["tick"], item["fan"]))
    samples = _wind_sim(plan, int(physics["ticks"]), phase, pods, physics)
    gates = []
    for index, gx in enumerate((285, 445, 605, 765)):
        slots = []
        for pod in pods:
            sample = min(samples[pod["id"]], key=lambda item: abs(item[0] - gx))
            amplitude = rng.choice((14, 17, 20))
            angular_rate = rng.choice((0.061, 0.073, 0.087))
            gate_phase = round(rng.random() * math.tau, 5)
            base_y = sample[1] - amplitude * math.sin(sample[2] * angular_rate + gate_phase)
            slots.append({
                "pod_id": pod["id"], "base_y": round(base_y, 3),
                "amplitude": amplitude, "angular_rate": angular_rate,
                "phase": gate_phase, "half_gap": 31,
            })
        gates.append({
            "id": f"gate-{index + 1}", "x": gx, "slots": slots,
        })
    docks = []
    for pod in pods:
        sample = min(samples[pod["id"]], key=lambda item: abs(item[0] - 855))
        docks.append({"pod_id": pod["id"], "x": 855, "y": round(sample[1], 2), "radius": 32})
    public.update({
        "generator": {"name": "dual_pod_shared_wind_field_v3", "variant_count": 2**8 * 10**10},
        "canvas": {"width": 900, "height": 480},
        "fans": [{"id": f"fan-{i + 1}", "x": x, "radius": 112} for i, x in enumerate(fan_x)],
        "gates": gates,
        "pods": pods,
        "physics": physics,
        "docks": docks,
    })
    truth.update({"plan": plan, "gates": gates, "physics": physics, "docks": docks})
    return public, truth


def _rod_cells(item: dict[str, Any]) -> set[tuple[int, int, int]]:
    center = [int(value) for value in item["center"]]
    axis = "xyz".index(str(item["axis"]))
    cells = set()
    for offset in (-1, 0, 1):
        point = center.copy()
        point[axis] += offset
        cells.add(tuple(point))
    return cells


def _masks(objects: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Return the frontmost colored cell for every orthographic ray."""
    views = {
        "front": (lambda cell: (cell[0], cell[2]), lambda cell: cell[1]),
        "side": (lambda cell: (cell[1], cell[2]), lambda cell: cell[0]),
        "top": (lambda cell: (cell[0], cell[1]), lambda cell: cell[2]),
    }
    result: dict[str, list[str]] = {}
    for view, (project, depth) in views.items():
        nearest: dict[tuple[int, int], tuple[int, str]] = {}
        for item in objects:
            for cell in _rod_cells(item):
                key = project(cell)
                candidate = (depth(cell), str(item["color"]))
                if key not in nearest or candidate[0] < nearest[key][0]:
                    nearest[key] = candidate
        result[view] = sorted(f"{u}:{v}:{color}" for (u, v), (_depth, color) in nearest.items())
    return result


def _hologram(task: dict[str, Any], seed: str):
    mechanic = "hologram_silhouette_foundry"
    rng, public, truth = _identity(mechanic, task, seed)
    palette = ("#ff6d4a", "#5bd8c8", "#f6c85f", "#a983ff", "#62a7ff", "#ef7fc4")
    solutions: list[dict[str, Any]] = []
    for _attempt in range(500):
        candidate: list[dict[str, Any]] = []
        occupied: set[tuple[int, int, int]] = set()
        for index, color in enumerate(palette):
            for _ in range(160):
                axis = rng.choice("xyz")
                center = [rng.randint(1, 5), rng.randint(1, 5), rng.randint(1, 5)]
                item = {"id": f"rod-{index + 1}", "center": center, "axis": axis, "color": color}
                cells = _rod_cells(item)
                if not cells & occupied and all(0 <= value <= 6 for cell in cells for value in cell):
                    occupied |= cells
                    candidate.append(item)
                    break
            else:
                break
        if len(candidate) != 6:
            continue
        masks = _masks(candidate)
        # Each die must contain genuine depth ambiguity; otherwise this falls
        # back to the sparse binary-v1 problem.
        if all(18 - len(masks[view]) >= 2 for view in ("front", "side", "top")):
            solutions = candidate
            break
    if not solutions:
        raise RuntimeError("could not generate an occluding six-rod casting")
    rack = ([1, 1, 1], [3, 1, 1], [5, 1, 1], [1, 5, 5], [3, 5, 5], [5, 5, 5])
    initial = [{**item, "center": list(rack[index]), "axis": "z"} for index, item in enumerate(solutions)]
    public.update({
        "generator": {"name": "occluding_color_inverse_foundry_v2", "variant_count": 10**14},
        "grid_size": 7,
        "objects": initial,
        "target_masks": _masks(solutions),
        "views": ("front", "side", "top"),
    })
    truth.update({"solution_objects": solutions, "target_masks": public["target_masks"]})
    return public, truth


def _orbital(task: dict[str, Any], seed: str):
    mechanic = "orbital_docking_customs"
    rng, public, truth = _identity(mechanic, task, seed)
    lane_y = 240.0
    thrusts = 6
    acceleration = 0.20
    velocity = thrusts * acceleration
    total_coast_ticks = 600
    station_angle = rng.randrange(0, 360, 15)
    port_rate = rng.choice((-1.5, 1.5))
    final_port_angle = (station_angle + total_coast_ticks * port_rate) % 360
    plan = [
        {"action": "thrust", "count": thrusts},
        {"action": "strafe-up", "count": 5},
        {"action": "coast", "ticks": 60},
        {"action": "strafe-down", "count": 5},
        {"action": "coast", "ticks": 120},
        {"action": "strafe-down", "count": 10},
        {"action": "coast", "ticks": 60},
        {"action": "strafe-up", "count": 10},
        {"action": "coast", "ticks": 360},
        {"action": "retro", "count": thrusts},
        {"action": "rotate", "target_deg": final_port_angle},
        {"action": "dock"},
    ]
    distance = round(velocity * total_coast_ticks, 3)
    station_x = 115.0 + distance
    station_amplitude = rng.choice((20.0, 24.0, 28.0))
    station_motion_rate = rng.choice((0.016, 0.018, 0.020))
    station_phase = round(math.pi / 2 - total_coast_ticks * station_motion_rate, 6)
    public.update({
        "generator": {"name": "scanned_s_rendezvous_v3", "variant_count": 10**11},
        "canvas": {"width": 900, "height": 480},
        "ship": {"x": 115.0, "y": lane_y, "vx": 0.0, "vy": 0.0, "angle_deg": 0.0, "radius": 16},
        "station": {
            "x": station_x, "base_y": lane_y + 60.0 - station_amplitude,
            "y_amplitude": station_amplitude, "y_rate": station_motion_rate,
            "y_phase": station_phase, "angle_deg": station_angle,
            "rotation_deg_per_tick": port_rate, "port_radius": 26,
        },
        "physics": {
            "impulse": acceleration, "rotation_step_deg": 15,
            "coast_step_ticks": 10, "coast_long_ticks": 30,
            "fuel": 64, "dock_speed": 0.12, "dock_distance": 22,
            "angle_tolerance_deg": 8, "max_ticks": 760,
        },
        "debris": [
            {"id": "debris-a", "x": 265.0, "y": lane_y, "radius": 39},
            {"id": "debris-b", "x": 505.0, "y": lane_y, "radius": 39},
        ],
        "beacons": [
            {"id": "scan-a", "x": 187.0, "y": lane_y - 60.0, "radius": 27},
            {"id": "scan-b", "x": 403.0, "y": lane_y + 60.0, "radius": 27},
        ],
    })
    truth.update({"reference_plan": plan, "station": public["station"], "physics": public["physics"]})
    return public, truth


def _slide(board: dict[str, Any], position: tuple[int, int], direction: int, collected: int) -> tuple[tuple[int, int], int]:
    vectors = ((1, 0), (0, 1), (-1, 0), (0, -1))
    dx, dy = vectors[direction % 4]
    walls = {tuple(item) for item in board["walls"]}
    gates = [tuple(item) for item in board["gates"]]
    x, y = position
    while (x + dx, y + dy) not in walls:
        x += dx
        y += dy
        if collected < len(gates) and (x, y) == gates[collected]:
            collected += 1
    return (x, y), collected


def _gravity_board(rng: random.Random) -> tuple[dict[str, Any], list[str]]:
    size = 8
    perimeter = {(x, 0) for x in range(size)} | {(x, size - 1) for x in range(size)} | {(0, y) for y in range(size)} | {(size - 1, y) for y in range(size)}
    for _ in range(2400):
        walls = set(perimeter)
        for y in range(1, size - 1):
            for x in range(1, size - 1):
                if rng.random() < 0.21:
                    walls.add((x, y))
        free = [(x, y) for y in range(1, size - 1) for x in range(1, size - 1) if (x, y) not in walls]
        if len(free) < 18:
            continue
        cargo_start, counter_start, *rest = rng.sample(free, 8)
        gates, cargo_target, counter_target = rest[:4], rest[4], rest[5]
        board = {
            "size": size, "walls": [list(p) for p in sorted(walls)],
            "cargo_start": list(cargo_start), "counter_start": list(counter_start),
            "gates": [list(p) for p in gates],
            "cargo_target": list(cargo_target), "counter_target": list(counter_target),
            "counter_layer": "isolated-under-deck-rail",
        }
        queue = deque([(cargo_start, counter_start, 0, 0, [])])
        seen = {(cargo_start, counter_start, 0, 0)}
        while queue:
            cargo, counter, orientation, collected, path = queue.popleft()
            if cargo == cargo_target and counter == counter_target and collected == 4 and 14 <= len(path) <= 30:
                return board, path
            if len(path) >= 30:
                continue
            for label, delta in (("cw", 1), ("ccw", -1)):
                new_orientation = (orientation + delta) % 4
                next_cargo, next_collected = _slide(board, cargo, new_orientation, collected)
                next_counter, _ = _slide(board, counter, new_orientation, 0)
                state = (next_cargo, next_counter, new_orientation, next_collected)
                if state not in seen:
                    seen.add(state)
                    queue.append((next_cargo, next_counter, new_orientation, next_collected, [*path, label]))
    raise RuntimeError("could not generate gravity room")


def _gravity(task: dict[str, Any], seed: str):
    mechanic = "gravity_room_freight"
    rng, public, truth = _identity(mechanic, task, seed)
    board, solution = _gravity_board(rng)
    public.update({
        "generator": {"name": "dual_body_rotating_gravity_room_v2", "variant_count": 10**12},
        "board": board,
        "initial_orientation": 0,
        "rotation_ms": 620,
    })
    truth.update({"board": board, "solution": solution})
    return public, truth


def _equalize_levels(
    start: tuple[int, ...],
    gate: int,
    circuits: list[tuple[int, int]],
) -> tuple[tuple[int, ...], list[dict[str, int]]]:
    queue = deque([(start, [])])
    seen = {start}
    while queue:
        levels, path = queue.popleft()
        if abs(levels[gate] - levels[gate + 1]) <= 1:
            return levels, path
        if len(path) >= 14:
            continue
        for circuit, (first, second) in enumerate(circuits):
            for source, destination, direction in ((first, second, 1), (second, first, -1)):
                if levels[source] <= 3 or levels[destination] >= 17:
                    continue
                changed = list(levels)
                changed[source] -= 1
                changed[destination] += 1
                candidate = tuple(changed)
                if candidate not in seen:
                    seen.add(candidate)
                    queue.append((candidate, [*path, {"action": "pump", "circuit": circuit, "direction": direction}]))
    raise RuntimeError("could not equalize authored flood lock")


def _flood(task: dict[str, Any], seed: str):
    mechanic = "floodgate_archive_rescue"
    rng, public, truth = _identity(mechanic, task, seed)
    circuits = [(0, 2), (2, 4), (4, 1), (1, 3), (3, 0)]
    crossing_order = (0, 3, 1, 2, 1, 3, 0)
    for _ in range(120):
        integer_levels = tuple(rng.randint(5, 15) for _ in range(5))
        cursor = integer_levels
        plan: list[dict[str, Any]] = []
        for gate in crossing_order:
            cursor, pumps = _equalize_levels(cursor, gate, circuits)
            plan.extend(pumps)
            plan.extend((
                {"action": "gate", "gate": gate, "open": True},
                {"action": "transfer", "gate": gate},
                {"action": "gate", "gate": gate, "open": False},
            ))
        pump_count = sum(item["action"] == "pump" for item in plan)
        if 10 <= pump_count <= 30:
            break
    else:
        raise RuntimeError("could not author coupled opposing flood route")
    levels = [value / 20 for value in integer_levels]
    public.update({
        "generator": {"name": "conserved_dual_capsule_lock_archive_v2", "variant_count": 10**10},
        "chambers": [{"id": f"vault-{i + 1}", "level": round(level, 2), "safe_min": 0.15, "safe_max": 0.85} for i, level in enumerate(levels)],
        "gates": [{"id": f"lock-{i + 1}", "between": [i, i + 1]} for i in range(4)],
        "circuits": [{"id": f"circuit-{i + 1}", "between": list(edge)} for i, edge in enumerate(circuits)],
        "capsules": [
            {"id": "amber", "chamber": 0, "dock_chamber": 4, "direction": 1, "color": "#ffb13b"},
            {"id": "cyan", "chamber": 4, "dock_chamber": 0, "direction": -1, "color": "#55dbe8"},
        ],
        "pump_step": 0.05,
        "equal_tolerance": 0.055,
    })
    truth.update({"reference_plan": plan, "initial_levels": levels, "pump_step": public["pump_step"], "equal_tolerance": public["equal_tolerance"]})
    return public, truth


def _membrane(task: dict[str, Any], seed: str):
    mechanic = "elastic_membrane_sorter"
    rng, public, truth = _identity(mechanic, task, seed)
    wells = ((125, 115), (775, 120), (450, 385))
    rounds = []
    courses = (
        [[355, 175], [235, 108]],
        [[545, 175], [665, 110]],
        [[365, 305], [515, 355]],
    )
    order = list(range(3)); rng.shuffle(order)
    for index, target in enumerate(order):
        initial = [round(rng.uniform(0.42, 0.58), 2) for _ in range(4)]
        rounds.append({
            "id": f"marble-{index + 1}", "target_well": target,
            "start": [450, 230], "post_heights": initial,
            "wells": [list(item) for item in wells], "checkpoints": courses[target],
        })
    public.update({
        "generator": {"name": "live_steered_membrane_course_v2", "variant_count": 10**9},
        "canvas": {"width": 900, "height": 480},
        "rounds": rounds,
        "post_positions": [[70, 55], [830, 55], [70, 425], [830, 425]],
        "physics": {"tick_ms": 35, "slope_accel": 0.10, "drag": 0.955, "well_radius": 30, "capture_speed": 2.8, "checkpoint_radius": 34, "max_ticks": 720, "boundary_restitution": 0.55},
    })
    truth.update({"rounds": rounds, "physics": public["physics"]})
    return public, truth


def _pheromone(task: dict[str, Any], seed: str):
    mechanic = "pheromone_dispatch"
    rng, public, truth = _identity(mechanic, task, seed)
    centre = rng.randint(232, 248)
    nest = [rng.randint(55, 70), centre]
    dock = [rng.randint(830, 845), centre]
    upper = rng.randint(78, 103)
    lower = rng.randint(377, 402)
    fields = [
        {"id": "amber", "label": "AMBER / UPPER CACHE", "color": "#d94f72", "cache": [450, upper], "trail_ttl_ticks": 96, "speed": 3.25},
        {"id": "violet", "label": "VIOLET / LOWER CACHE", "color": "#6f5bd8", "cache": [450, lower], "trail_ttl_ticks": 112, "speed": 2.85},
    ]
    obstacles = [
        {"x": rng.randint(285, 315), "y": centre, "w": rng.randint(88, 108), "h": rng.randint(175, 195)},
        {"x": rng.randint(585, 615), "y": centre, "w": rng.randint(88, 108), "h": rng.randint(175, 195)},
    ]
    reference_paths = {
        "amber": [nest, [175, upper], [380, upper], fields[0]["cache"], [690, upper], dock],
        "violet": [nest, [175, lower], [380, lower], fields[1]["cache"], [690, lower], dock],
    }
    public.update({
        "generator": {"name": "dual_decaying_pheromone_fields_v3", "variant_count": 10**10},
        "canvas": {"width": 900, "height": 480},
        "nest": nest,
        "dock": dock,
        "fields": fields,
        "obstacles": obstacles,
        "ant_count": 10,
        "physics": {"tick_ms": 45, "sample_radius": 22, "brush_radius": 23, "delivery_required": 7, "ant_spacing": 18},
    })
    truth.update({"reference_paths": reference_paths, "obstacles": obstacles, "physics": public["physics"]})
    return public, truth


def _clutch(task: dict[str, Any], seed: str):
    mechanic = "clockwork_clutch_safe"
    rng, public, truth = _identity(mechanic, task, seed)
    ratios = rng.choice((
        (1.0, -1.25, 1.5, -1.75),
        (1.25, -1.0, 1.75, -1.5),
        (1.5, -1.75, 1.0, -1.25),
    ))
    order = list(range(4)); rng.shuffle(order)
    moments = [rng.randint(31, 38), rng.randint(56, 65), rng.randint(84, 94), rng.randint(116, 128)]
    release_schedule = sorted(({"tick": tick, "shaft": shaft} for tick, shaft in zip(moments, order)), key=lambda item: item["tick"])
    drive_deg = 1.8
    accumulated = [0.0] * 4
    active = set(range(4))
    by_tick = {item["tick"]: item["shaft"] for item in release_schedule}
    for tick in range(1, max(moments) + 1):
        factor = 4 / len(active)
        for shaft in active:
            accumulated[shaft] += ratios[shaft] * drive_deg * factor
        if tick in by_tick:
            active.remove(by_tick[tick])
    initial = [round((-value) % 360.0, 3) for value in accumulated]
    public.update({
        "generator": {"name": "load_redistributing_clutch_safe_v2", "variant_count": 10**10},
        "shafts": [{"id": f"seal-{i + 1}", "ratio": ratio, "angle_deg": initial[i], "engaged": True} for i, ratio in enumerate(ratios)],
        "physics": {"tick_ms": 85, "drive_deg_per_tick": drive_deg, "load_numerator": 4, "phase_tolerance_deg": 13.0, "max_ticks": 170},
    })
    truth.update({"release_schedule": release_schedule, "ratios": ratios, "initial_angles": initial, "physics": public["physics"]})
    return public, truth


def _marionette(task: dict[str, Any], seed: str):
    mechanic = "marionette_checkpoint"
    rng, public, truth = _identity(mechanic, task, seed)
    poses = []
    for index in range(3):
        base = [rng.randint(34, 66) for _ in range(4)]
        amplitudes = [rng.randint(5, min(8, value - 21, 79 - value)) for value in base]
        poses.append({
            "id": f"inspection-{index + 1}",
            "base_lengths": base,
            "amplitudes": amplitudes,
            "phases": [round(rng.random() * math.tau, 5) for _ in range(4)],
            "angular_rate": rng.choice((0.046, 0.050, 0.054)),
            "tracking_ticks": 68,
            "miss_decay_ticks": 2,
        })
    public.update({
        "generator": {"name": "moving_coupled_marionette_inspection_v2", "variant_count": 10**11},
        "canvas": {"width": 900, "height": 480},
        "initial_lengths": [50, 50, 50, 50],
        "poses": poses,
        "length_range": [20, 80],
        "ring_radius": 21,
        "tick_ms": 55,
    })
    truth.update({"poses": poses, "ring_radius": public["ring_radius"]})
    return public, truth


GENERATORS = {
    "specular_lighthouse_relay": _specular,
    "wind_tunnel_seed_courier": _wind,
    "hologram_silhouette_foundry": _hologram,
    "orbital_docking_customs": _orbital,
    "gravity_room_freight": _gravity,
    "floodgate_archive_rescue": _flood,
    "elastic_membrane_sorter": _membrane,
    "pheromone_dispatch": _pheromone,
    "clockwork_clutch_safe": _clutch,
    "marionette_checkpoint": _marionette,
}


def generate(mechanic: str, task: dict[str, Any], seed: str):
    return GENERATORS[mechanic](task, seed)
