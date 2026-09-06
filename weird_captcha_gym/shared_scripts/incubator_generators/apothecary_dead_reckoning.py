from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from typing import Any


MECHANIC_ID = "apothecary_dead_reckoning"
ASSET_MANIFEST = "shared_runtime/assets/provenance/apothecary_dead_reckoning_v0.json"
STAGE = {"width": 820, "height": 510}
ORIGIN = [410.0, 255.0]
PATH_SAMPLES = 24
STIR_STRIDE = 6
GRIND_TICK_MS = 240
GATE_REVEAL_FACTOR = 0.92
GATE_CENTER_TOLERANCE = 2.25
GATE_HEADING_TOLERANCE_DEGREES = 2.0
VARIANT_COUNT = 9_400_000_000

BASELINE_PARAMETERS = {
    "ingredient_count": 6,
    "route_commits": 4,
    "grind_notches": 9,
    "path_length_min": 120,
    "path_length_max": 146,
    "curve_degrees_min": 58,
    "curve_degrees_max": 94,
    "bone_count": 4,
    "known_bone_count": 2,
    "vortex_count": 1,
    "effect_count": 4,
    "initial_reveal_radius": 70,
    "reveal_radius": 62,
    "target_radius": 24,
    "gate_radius": 12,
    "ingredient_budget": 7,
    "water_budget": 4,
    "water_step": 32,
    "bellows_budget": 4,
    "bellows_step": 22,
    "max_hazard_contacts": 1,
}

INGREDIENT_CATALOGUE = (
    ("ashfern", "Ashfern", "fern", "#789064"),
    ("cinder_cap", "Cinder Cap", "cap", "#b65b47"),
    ("moon_reed", "Moon Reed", "reed", "#7793a7"),
    ("golden_rot", "Golden Rot", "rot", "#b18a43"),
    ("widow_root", "Widow Root", "root", "#745873"),
    ("salt_bloom", "Salt Bloom", "bloom", "#8ba9a0"),
)

EFFECT_CATALOGUE = (
    ("moth_fire", "Moth-Fire", "moth", "#c76842"),
    ("glass_sleep", "Glass Sleep", "eye", "#7189a5"),
    ("thorn_voice", "Thorn Voice", "thorn", "#657d55"),
    ("tide_memory", "Tide Memory", "wave", "#4f8990"),
    ("hollow_sun", "Hollow Sun", "sun", "#b89446"),
    ("mirror_blood", "Mirror Blood", "drop", "#9a4e56"),
)


def _condition(task: dict[str, Any]) -> dict[str, Any] | None:
    value = task.get("_control_condition")
    return copy.deepcopy(value) if isinstance(value, dict) else None


def _parameters(task: dict[str, Any]) -> dict[str, Any]:
    condition = _condition(task)
    if condition is None:
        return copy.deepcopy(BASELINE_PARAMETERS)
    value = condition.get("difficulty_parameters")
    if not isinstance(value, dict):
        raise ValueError("apothecary difficulty parameters are missing")
    return copy.deepcopy(value)


def _integer(parameters: dict[str, Any], key: str, low: int, high: int) -> int:
    value = parameters.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{key} must be an integer in [{low}, {high}]")
    return value


def _validate(parameters: dict[str, Any]) -> None:
    _integer(parameters, "ingredient_count", 3, len(INGREDIENT_CATALOGUE))
    commits = _integer(parameters, "route_commits", 2, 5)
    notches = _integer(parameters, "grind_notches", 5, 15)
    length_min = _integer(parameters, "path_length_min", 90, 180)
    length_max = _integer(parameters, "path_length_max", 90, 180)
    curve_min = _integer(parameters, "curve_degrees_min", 30, 130)
    curve_max = _integer(parameters, "curve_degrees_max", 30, 130)
    if length_min > length_max or curve_min > curve_max:
        raise ValueError("path or curvature bounds are reversed")
    bones = _integer(parameters, "bone_count", 0, 8)
    known = _integer(parameters, "known_bone_count", 0, 3)
    if known > bones:
        raise ValueError("known_bone_count exceeds bone_count")
    _integer(parameters, "vortex_count", 0, 3)
    _integer(parameters, "effect_count", 3, len(EFFECT_CATALOGUE))
    initial = _integer(parameters, "initial_reveal_radius", 45, 125)
    reveal = _integer(parameters, "reveal_radius", 40, 110)
    if reveal > initial + 8:
        raise ValueError("travel reveal cannot greatly exceed the initial reveal")
    _integer(parameters, "target_radius", 18, 42)
    _integer(parameters, "gate_radius", 8, 22)
    ingredients = _integer(parameters, "ingredient_budget", commits, 10)
    if ingredients < commits:
        raise ValueError("ingredient budget cannot complete the generated route")
    _integer(parameters, "water_budget", 0, 10)
    _integer(parameters, "water_step", 20, 50)
    _integer(parameters, "bellows_budget", 0, 10)
    _integer(parameters, "bellows_step", 15, 40)
    _integer(parameters, "max_hazard_contacts", 0, bones)
    if notches < 2:
        raise ValueError("grind control requires at least two notches")


def _distance(first: list[float], second: list[float]) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def path_points(
    start: list[float], ingredient: dict[str, Any], grind_step: int, grind_notches: int
) -> list[list[float]]:
    """Sample the same constant-curvature path used by browser and grader."""
    fraction = grind_step / max(1, grind_notches - 1)
    angle = math.radians(float(ingredient["angle_deg"]))
    turn = math.radians(float(ingredient["curve_degrees"]) * fraction * int(ingredient["turn"]))
    length = float(ingredient["length"])
    points: list[list[float]] = []
    for index in range(PATH_SAMPLES + 1):
        t = index / PATH_SAMPLES
        if abs(turn) < 1e-9:
            x = start[0] + length * t * math.cos(angle)
            y = start[1] + length * t * math.sin(angle)
        else:
            radius = length / turn
            x = start[0] + radius * (math.sin(angle + turn * t) - math.sin(angle))
            y = start[1] - radius * (math.cos(angle + turn * t) - math.cos(angle))
        points.append([round(x, 4), round(y, 4)])
    return points


def path_heading(
    ingredient: dict[str, Any], grind_step: int, grind_notches: int, path_index: int
) -> float:
    fraction = grind_step / max(1, grind_notches - 1)
    return (
        float(ingredient["angle_deg"])
        + float(ingredient["curve_degrees"])
        * fraction
        * int(ingredient["turn"])
        * path_index
        / PATH_SAMPLES
    ) % 360


def route_gate(
    start: list[float],
    ingredient: dict[str, Any],
    grind_step: int,
    parameters: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    segment = path_points(
        start,
        ingredient,
        grind_step,
        int(parameters["grind_notches"]),
    )
    gate_sample = max(
        5,
        min(
            PATH_SAMPLES - 2,
            round(
                float(parameters["reveal_radius"])
                * GATE_REVEAL_FACTOR
                / float(ingredient["length"])
                * PATH_SAMPLES
            ),
        ),
    )
    return {
        "id": f"route-ring-{index + 1}",
        "center": segment[gate_sample],
        "heading_deg": round(
            path_heading(
                ingredient,
                grind_step,
                int(parameters["grind_notches"]),
                gate_sample,
            ),
            3,
        ),
        "radius": int(parameters["gate_radius"]),
    }


def gate_alignment(
    start: list[float],
    ingredient: dict[str, Any],
    grind_step: int,
    grind_notches: int,
    gate: dict[str, Any],
) -> dict[str, Any]:
    points = path_points(start, ingredient, grind_step, grind_notches)
    nearest_index = min(
        range(len(points)),
        key=lambda candidate: _distance(points[candidate], gate["center"]),
    )
    center_error = _distance(points[nearest_index], gate["center"])
    candidate_heading = path_heading(
        ingredient,
        grind_step,
        grind_notches,
        nearest_index,
    )
    heading_error = abs(
        (candidate_heading - float(gate["heading_deg"]) + 180) % 360 - 180
    )
    return {
        "aligned": center_error <= GATE_CENTER_TOLERANCE
        and heading_error <= GATE_HEADING_TOLERANCE_DEGREES,
        "center_error": round(center_error, 4),
        "heading_error": round(heading_error, 4),
        "path_index": nearest_index,
    }


def gate_matching_choices(
    start: list[float],
    ingredients: list[dict[str, Any]],
    grind_notches: int,
    gate: dict[str, Any],
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for ingredient in ingredients:
        for grind_step in range(grind_notches):
            alignment = gate_alignment(
                start,
                ingredient,
                grind_step,
                grind_notches,
                gate,
            )
            if alignment["aligned"]:
                matches.append(
                    {
                        "ingredient_id": ingredient["id"],
                        "grind_step": grind_step,
                    }
                )
    return matches


def _inside_map(points: list[list[float]], margin: float = 34.0) -> bool:
    return all(
        margin <= point[0] <= STAGE["width"] - margin
        and margin <= point[1] <= STAGE["height"] - margin
        for point in points
    )


def _find_route(
    rng: random.Random,
    ingredients: list[dict[str, Any]],
    parameters: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[list[float]]]:
    commits = int(parameters["route_commits"])
    notches = int(parameters["grind_notches"])
    by_id = {item["id"]: item for item in ingredients}

    def search(
        position: list[float],
        route: list[dict[str, Any]],
        trace: list[list[float]],
        step_schedule: list[int],
    ) -> tuple[list[dict[str, Any]], list[list[float]]] | None:
        if len(route) == commits:
            radial = _distance(position, ORIGIN)
            early_trace = trace[: -2 * STIR_STRIDE] if len(trace) > 2 * STIR_STRIDE else trace[:1]
            minimum_radial = max(
                float(parameters["initial_reveal_radius"]) + 20,
                95 + 15 * commits,
            )
            if minimum_radial <= radial <= 330 and min(_distance(position, point) for point in early_trace) >= 34:
                return route, trace
            return None
        grind_step = step_schedule[len(route)]
        candidate_ids = list(by_id)
        rng.shuffle(candidate_ids)
        for ingredient_id in candidate_ids:
            if route and ingredient_id == route[-1]["ingredient_id"]:
                continue
            points = path_points(position, by_id[ingredient_id], grind_step, notches)
            if not _inside_map(points):
                continue
            endpoint = points[-1]
            if len(route) > 0 and _distance(endpoint, position) < 65:
                continue
            result = search(
                endpoint,
                [*route, {"ingredient_id": ingredient_id, "grind_step": grind_step}],
                [*trace, *points[1:]],
                step_schedule,
            )
            if result is not None:
                return result
        return None

    # Each authored route uses different grind outcomes at successive stages.
    # Schedules are uniformly shuffled instead of being sorted toward a fixed
    # fraction, so the action-relevant choices vary across seeds and levels.
    for _attempt in range(max(64, notches * 12)):
        steps = list(range(notches))
        rng.shuffle(steps)
        step_schedule = steps[:commits]
        result = search(ORIGIN[:], [], [ORIGIN[:]], step_schedule)
        if result is None:
            continue
        route, trace = result
        position = ORIGIN[:]
        unique = True
        for index, expected in enumerate(route):
            ingredient = by_id[expected["ingredient_id"]]
            gate = route_gate(
                position,
                ingredient,
                int(expected["grind_step"]),
                parameters,
                index,
            )
            if gate_matching_choices(position, ingredients, notches, gate) != [expected]:
                unique = False
                break
            position = path_points(
                position,
                ingredient,
                int(expected["grind_step"]),
                notches,
            )[-1]
        if unique:
            return route, trace
    raise RuntimeError("could not construct a varied reachable apothecary route")


def _regular_polygon(center: list[float], radius: float, sides: int, phase: float) -> list[list[float]]:
    return [
        [
            round(center[0] + radius * math.cos(phase + index * math.tau / sides), 3),
            round(center[1] + radius * math.sin(phase + index * math.tau / sides), 3),
        ]
        for index in range(sides)
    ]


def _far_from(point: list[float], others: list[list[float]], distance: float) -> bool:
    return all(_distance(point, other) >= distance for other in others)


def _place_known_bones(
    rng: random.Random, count: int, radius: float, safe_trace: list[list[float]]
) -> list[dict[str, Any]]:
    if count == 0:
        return []
    bones: list[dict[str, Any]] = []
    phase = rng.random() * math.tau
    candidates = [
        (radial, slot)
        for radial in (0.58, 0.7, 0.82, 0.94, 1.02)
        for slot in range(144)
    ]
    rng.shuffle(candidates)
    centers: list[list[float]] = []
    for safe_distance in (25.0, 21.0, 16.0):
        for radial, slot in candidates:
            angle = phase + slot * math.tau / 144
            center = [
                ORIGIN[0] + radius * radial * math.cos(angle),
                ORIGIN[1] + radius * radial * math.sin(angle),
            ]
            if not _far_from(center, safe_trace, safe_distance):
                continue
            if not _far_from(center, centers, 32):
                continue
            centers.append(center)
            bones.append({
                "id": f"spur-{len(bones) + 1}",
                "polygon": _regular_polygon(center, 14, 5, angle + 0.3),
                "known": True,
            })
            if len(bones) == count:
                return bones
    raise RuntimeError("could not place initially visible bone spurs on exhaustive rings")


def _random_point(rng: random.Random, margin: float = 42) -> list[float]:
    return [rng.uniform(margin, STAGE["width"] - margin), rng.uniform(margin, STAGE["height"] - margin)]


def _field_candidates(
    rng: random.Random,
    margin: float,
    spacing: float = 34.0,
) -> list[list[float]]:
    candidates = [
        [round(x, 3), round(y, 3)]
        for y in range(round(margin), round(STAGE["height"] - margin) + 1, round(spacing))
        for x in range(round(margin), round(STAGE["width"] - margin) + 1, round(spacing))
    ]
    rng.shuffle(candidates)
    return candidates


def _line_trace(first: list[float], second: list[float], samples: int = 32) -> list[list[float]]:
    return [
        [
            round(first[0] + (second[0] - first[0]) * index / samples, 4),
            round(first[1] + (second[1] - first[1]) * index / samples, 4),
        ]
        for index in range(samples + 1)
    ]


def _select_recovery_probe(
    rng: random.Random,
    ingredients: list[dict[str, Any]],
    parameters: dict[str, Any],
    first_gate: dict[str, Any],
    solution_trace: list[list[float]],
) -> tuple[dict[str, Any], dict[str, Any] | None, list[list[float]]]:
    """Choose a committed wrong route that can be recovered with visible tools.

    When the level contains a vortex, the probe is routed through it so the
    retained browser solve demonstrates displacement and recovery rather than
    an artificial one-step inverse action at the origin.
    """
    notches = int(parameters["grind_notches"])
    water_budget = int(parameters["water_budget"])
    water_step = float(parameters["water_step"])
    bellows_reserve = 1 if water_budget >= 2 and int(parameters["bellows_budget"]) else 0
    recoverable_distance = max(0.0, (water_budget - bellows_reserve) * water_step)
    candidates = [(ingredient, step) for ingredient in ingredients for step in range(notches)]
    rng.shuffle(candidates)
    wants_vortex = int(parameters["vortex_count"]) > 0
    for ingredient, grind_step in candidates:
        alignment = gate_alignment(ORIGIN, ingredient, grind_step, notches, first_gate)
        if alignment["aligned"]:
            continue
        points = path_points(ORIGIN, ingredient, grind_step, notches)
        if not _inside_map(points):
            continue
        if wants_vortex:
            for sample_index in (12, 10, 14, 8, 16):
                center = points[sample_index]
                radius = 20.0
                if not _far_from(center, solution_trace[3:], radius + 15):
                    continue
                collision_index = next(
                    (
                        index
                        for index, point in enumerate(points[1:], start=1)
                        if _distance(point, center) <= radius
                    ),
                    None,
                )
                if collision_index is None:
                    continue
                collision = points[collision_index]
                spin = rng.choice((-1, 1))
                dx, dy = collision[0] - center[0], collision[1] - center[1]
                displaced = (
                    [center[0] - dy, center[1] + dx]
                    if spin > 0
                    else [center[0] + dy, center[1] - dx]
                )
                displaced = [round(displaced[0], 4), round(displaced[1], 4)]
                if _distance(displaced, ORIGIN) > recoverable_distance + 1e-6:
                    continue
                vortex = {
                    "id": "vortex-1",
                    "center": [round(center[0], 3), round(center[1], 3)],
                    "radius": radius,
                    "spin": spin,
                }
                trace = [*points[: collision_index + 1], displaced, *_line_trace(displaced, ORIGIN)[1:]]
                return (
                    {
                        "ingredient_id": ingredient["id"],
                        "grind_step": grind_step,
                        "expected_vortex_id": vortex["id"],
                    },
                    vortex,
                    trace,
                )
        elif _distance(points[-1], ORIGIN) <= recoverable_distance + 1e-6:
            return (
                {
                    "ingredient_id": ingredient["id"],
                    "grind_step": grind_step,
                    "expected_vortex_id": None,
                },
                None,
                [*points, *_line_trace(points[-1], ORIGIN)[1:]],
            )
    raise RuntimeError("could not construct a recoverable off-route probe")


def _jar_rects(ingredients: list[dict[str, Any]]) -> dict[str, list[float]]:
    rects: dict[str, list[float]] = {}
    for index, ingredient in enumerate(ingredients):
        column, row = index % 3, index // 3
        rects[ingredient["id"]] = [
            round(0.725 + column * 0.0865, 5),
            round(0.192 + row * 0.104, 5),
            0.077,
            0.086,
        ]
    return rects


def generate(task: dict[str, Any], seed: str):
    parameters = _parameters(task)
    _validate(parameters)
    condition = _condition(task)
    stable_parameters = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
    stable = hashlib.sha256(f"{MECHANIC_ID}|{seed}|{stable_parameters}".encode("utf-8")).hexdigest()
    rng = random.Random(int(stable[:16], 16))
    task_id = str(task.get("id") or "apothecary_dead_reckoning_seed_0001@0.1")
    challenge_id = f"adr-{hashlib.sha256(f'{stable}|{task_id}'.encode()).hexdigest()[:17]}"

    count = int(parameters["ingredient_count"])
    ingredients: list[dict[str, Any]] = []
    solution: list[dict[str, Any]] = []
    solution_trace: list[list[float]] = []
    for _world_attempt in range(128):
        catalogue = list(INGREDIENT_CATALOGUE)
        rng.shuffle(catalogue)
        catalogue = catalogue[:count]
        base_rotation = rng.uniform(-28, 28)
        candidate_ingredients: list[dict[str, Any]] = []
        for index, (ingredient_id, name, glyph, color) in enumerate(catalogue):
            candidate_ingredients.append({
                "id": ingredient_id,
                "name": name,
                "glyph": glyph,
                "color": color,
                "angle_deg": round(base_rotation + index * 360 / count + rng.uniform(-12, 12), 3),
                "length": rng.randint(int(parameters["path_length_min"]), int(parameters["path_length_max"])),
                "curve_degrees": rng.randint(int(parameters["curve_degrees_min"]), int(parameters["curve_degrees_max"])),
                "turn": rng.choice((-1, 1)),
            })
        try:
            candidate_solution, candidate_trace = _find_route(
                rng,
                candidate_ingredients,
                parameters,
            )
        except RuntimeError:
            continue
        ingredients = candidate_ingredients
        solution = candidate_solution
        solution_trace = candidate_trace
        break
    if not solution:
        raise RuntimeError("could not construct an apothecary world after 128 varied layouts")
    target_center = solution_trace[-1][:]
    ingredient_by_id = {ingredient["id"]: ingredient for ingredient in ingredients}
    route_gates: list[dict[str, Any]] = []
    gate_start = ORIGIN[:]
    for index, commit in enumerate(solution):
        ingredient = ingredient_by_id[commit["ingredient_id"]]
        segment = path_points(
            gate_start,
            ingredient,
            int(commit["grind_step"]),
            int(parameters["grind_notches"]),
        )
        route_gates.append(
            route_gate(
                gate_start,
                ingredient,
                int(commit["grind_step"]),
                parameters,
                index,
            )
        )
        gate_start = segment[-1][:]
    recovery_probe, reserved_vortex, off_route_recovery_trace = _select_recovery_probe(
        rng,
        ingredients,
        parameters,
        route_gates[0],
        solution_trace,
    )
    bellows_recovery_trace = [
        [ORIGIN[0] + offset, ORIGIN[1]]
        for offset in range(0, int(parameters["bellows_step"]) + 1, 2)
    ]
    hazard_safe_trace = [
        *solution_trace,
        *off_route_recovery_trace,
        *bellows_recovery_trace,
    ]

    bones = _place_known_bones(
        rng,
        int(parameters["known_bone_count"]),
        float(parameters["initial_reveal_radius"]),
        hazard_safe_trace,
    )
    occupied = [
        target_center,
        *[
            [
                sum(point[0] for point in bone["polygon"]) / len(bone["polygon"]),
                sum(point[1] for point in bone["polygon"]) / len(bone["polygon"]),
            ]
            for bone in bones
        ],
    ]
    for center in _field_candidates(rng, 42, 32):
        if len(bones) >= int(parameters["bone_count"]):
            break
        if not _far_from(center, hazard_safe_trace, 27) or not _far_from(center, occupied, 35):
            continue
        radius = rng.uniform(13, 18)
        bones.append({
            "id": f"spur-{len(bones) + 1}",
            "polygon": _regular_polygon(center, radius, rng.choice((5, 6)), rng.random() * math.tau),
            "known": False,
        })
        occupied.append(center)
    if len(bones) != int(parameters["bone_count"]):
        raise RuntimeError("could not place safe bone field on exhaustive grid")

    vortices: list[dict[str, Any]] = [reserved_vortex] if reserved_vortex else []
    if reserved_vortex:
        occupied.append(reserved_vortex["center"])
    for center in _field_candidates(rng, 58, 38):
        if len(vortices) >= int(parameters["vortex_count"]):
            break
        radius = rng.uniform(19, 24)
        if not _far_from(center, hazard_safe_trace, radius + 13) or not _far_from(center, occupied, radius + 28):
            continue
        vortices.append({
            "id": f"vortex-{len(vortices) + 1}",
            "center": [round(center[0], 3), round(center[1], 3)],
            "radius": round(radius, 3),
            "spin": rng.choice((-1, 1)),
        })
        occupied.append(center)
    if len(vortices) != int(parameters["vortex_count"]):
        raise RuntimeError("could not place safe vortex field on exhaustive grid")

    effects_catalogue = list(EFFECT_CATALOGUE)
    rng.shuffle(effects_catalogue)
    target_record = effects_catalogue[0]
    effects = [{
        "id": target_record[0],
        "name": target_record[1],
        "glyph": target_record[2],
        "color": target_record[3],
        "center": [round(target_center[0], 3), round(target_center[1], 3)],
        "radius": int(parameters["target_radius"]),
    }]
    effect_candidates: list[list[float]] = []
    effect_phase = rng.random() * math.tau
    reveal_radius = float(parameters["reveal_radius"])
    for anchor in solution_trace[:: max(1, STIR_STRIDE // 2)]:
        for distance_factor in (0.48, 0.63, 0.78):
            for slot in range(24):
                angle = effect_phase + slot * math.tau / 24
                effect_candidates.append([
                    anchor[0] + math.cos(angle) * reveal_radius * distance_factor,
                    anchor[1] + math.sin(angle) * reveal_radius * distance_factor,
                ])
    rng.shuffle(effect_candidates)
    for center in effect_candidates:
        if len(effects) >= int(parameters["effect_count"]):
            break
        record = effects_catalogue[len(effects)]
        if not (42 <= center[0] <= STAGE["width"] - 42 and 42 <= center[1] <= STAGE["height"] - 42):
            continue
        minimum_spacing = max(42.0, float(parameters["target_radius"]) * 2 + 6)
        if not _far_from(center, occupied, minimum_spacing) or _distance(center, target_center) < 68:
            continue
        effects.append({
            "id": record[0],
            "name": record[1],
            "glyph": record[2],
            "color": record[3],
            "center": [round(center[0], 3), round(center[1], 3)],
            "radius": int(parameters["target_radius"]),
        })
        occupied.append(center)
    if len(effects) != int(parameters["effect_count"]):
        raise RuntimeError("could not place effect seals on exhaustive revealed candidates")
    rng.shuffle(effects)

    mechanics = {
        "path_samples": PATH_SAMPLES,
        "stir_stride": STIR_STRIDE,
        "grind_tick_ms": GRIND_TICK_MS,
        "gate_reveal_factor": GATE_REVEAL_FACTOR,
        "gate_center_tolerance": GATE_CENTER_TOLERANCE,
        "gate_heading_tolerance_degrees": GATE_HEADING_TOLERANCE_DEGREES,
        "route_feedback": "post_commit_only",
        "marker_radius": 8,
        "vortex_turn_degrees": 90,
        "map_margin": 12,
    }
    interaction_geometry = {
        "jar_rects": _jar_rects(ingredients),
        "mortar_rect": [0.748, 0.425, 0.218, 0.177],
        "pestle_rect": [0.815, 0.437, 0.082, 0.145],
    }
    order = {"name": target_record[1], "glyph": target_record[2], "color": target_record[3]}
    shared = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "stage": copy.deepcopy(STAGE),
        "origin": ORIGIN[:],
        "ingredients": copy.deepcopy(ingredients),
        "effects": copy.deepcopy(effects),
        "route_gates": copy.deepcopy(route_gates),
        "bones": copy.deepcopy(bones),
        "vortices": copy.deepcopy(vortices),
        "parameters": copy.deepcopy(parameters),
        "mechanics": mechanics,
        "interaction_geometry": interaction_geometry,
        "order": copy.deepcopy(order),
    }
    public_state = {
        **copy.deepcopy(shared),
        "benchmark": "weird_captcha_gym",
        "prompt": str(task.get("natural_language") or "Brew the ordered sigil."),
        "asset_manifest": str((task.get("metadata") or {}).get("asset_manifest") or ASSET_MANIFEST),
        "generator": {"name": "fogged_constant_curvature_apothecary_v1", "variant_count": VARIANT_COUNT},
    }
    ground_truth = {
        **copy.deepcopy(shared),
        "target_effect_id": target_record[0],
        "solution": copy.deepcopy(solution),
        "solution_trace": copy.deepcopy(solution_trace),
        "recovery_probe": copy.deepcopy(recovery_probe),
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
