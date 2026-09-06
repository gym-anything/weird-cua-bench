from __future__ import annotations

import copy
import hashlib
import math
import random
from functools import lru_cache
from typing import Any


MECHANIC_ID = "circle_limit_twist"
SIDES = 7
DEFAULTS = {"face_count": 12, "scramble_length": 4, "move_budget": 6}
ACTIVE_TILE_ORDER = (0, 1, 2, 3, 4, 5, 6, 7, 10, 20, 16, 25, 13, 22, 28)
PALETTE = (
    ("#e84b35", "#ffb199"),
    ("#f5a623", "#ffe08a"),
    ("#f5de51", "#fff6aa"),
    ("#95c94b", "#d9f59c"),
    ("#25a985", "#8fe1cc"),
    ("#35aeca", "#9ce8f6"),
    ("#4678d3", "#a8c5ff"),
    ("#7657c9", "#c5afff"),
    ("#b14eaa", "#eca7e5"),
    ("#d95079", "#ffadc3"),
    ("#d66b32", "#ffbd8b"),
    ("#9b7043", "#e5bd82"),
    ("#617f42", "#b8d995"),
    ("#318c9d", "#a1dae3"),
    ("#9a577d", "#dfacd0"),
)


def _seed(seed: str) -> int:
    digest = hashlib.sha256(f"{seed}|{MECHANIC_ID}|v1".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _centroid(polygon: list[complex]) -> complex:
    twice_area = 0.0
    x_sum = 0.0
    y_sum = 0.0
    for first, second in zip(polygon, polygon[1:] + polygon[:1]):
        cross = first.real * second.imag - second.real * first.imag
        twice_area += cross
        x_sum += (first.real + second.real) * cross
        y_sum += (first.imag + second.imag) * cross
    if abs(twice_area) < 1e-12:
        return sum(polygon) / len(polygon)
    return complex(x_sum / (3.0 * twice_area), y_sum / (3.0 * twice_area))


def _reflect_point(point: complex, first: complex, second: complex) -> complex:
    # A Poincare geodesic is a Euclidean circle orthogonal to the unit disc.
    # Reflection in that circle is a hyperbolic reflection. Diameters use the
    # limiting line-reflection form.
    a11, a12 = first.real, first.imag
    a21, a22 = second.real, second.imag
    b1 = (abs(first) ** 2 + 1.0) / 2.0
    b2 = (abs(second) ** 2 + 1.0) / 2.0
    determinant = a11 * a22 - a12 * a21
    if abs(determinant) < 1e-10:
        midpoint = first + second
        angle = math.atan2(midpoint.imag, midpoint.real)
        return complex(math.cos(2.0 * angle), math.sin(2.0 * angle)) * point.conjugate()
    center = complex(
        (b1 * a22 - a12 * b2) / determinant,
        (a11 * b2 - b1 * a21) / determinant,
    )
    radius_squared = abs(center) ** 2 - 1.0
    delta = point - center
    return center + radius_squared * delta / (abs(delta) ** 2)


def _rotate(point: complex, angle: float) -> complex:
    phase = complex(math.cos(angle), math.sin(angle))
    return point * phase


@lru_cache(maxsize=1)
def _base_tiling() -> tuple[dict[str, Any], ...]:
    # For a regular {7,3} tiling, cosh(circumradius) = cot(pi/7)cot(pi/3).
    circumradius = math.acosh(1.0 / (math.tan(math.pi / 7.0) * math.tan(math.pi / 3.0)))
    disc_radius = math.tanh(circumradius / 2.0)
    initial = [
        complex(
            disc_radius * math.cos(-math.pi / 2.0 + 2.0 * math.pi * index / SIDES),
            disc_radius * math.sin(-math.pi / 2.0 + 2.0 * math.pi * index / SIDES),
        )
        for index in range(SIDES)
    ]
    polygons: list[tuple[list[complex], int]] = [(initial, 0)]
    seen = {(0.0, 0.0)}
    frontier = [0]
    for depth in (1, 2, 3):
        next_frontier: list[int] = []
        for tile_index in frontier:
            polygon = polygons[tile_index][0]
            for side in range(SIDES):
                first = polygon[side]
                second = polygon[(side + 1) % SIDES]
                reflected = [_reflect_point(point, first, second) for point in polygon]
                center = _centroid(reflected)
                key = (round(center.real, 5), round(center.imag, 5))
                if key in seen:
                    continue
                seen.add(key)
                polygons.append((reflected, depth))
                next_frontier.append(len(polygons) - 1)
        frontier = next_frontier
    if len(polygons) != 85:
        raise RuntimeError(f"unexpected reflected tiling size: {len(polygons)}")
    result = []
    for tile_id, (polygon, depth) in enumerate(polygons):
        center = _centroid(polygon)
        result.append({
            "id": tile_id,
            "depth": depth,
            "center": [round(center.real, 9), round(center.imag, 9)],
            "vertices": [[round(point.real, 9), round(point.imag, 9)] for point in polygon],
        })
    return tuple(result)


def _hyperbolic_distance(first: complex, second: complex) -> float:
    denominator = (1.0 - abs(first) ** 2) * (1.0 - abs(second) ** 2)
    value = 1.0 + 2.0 * abs(first - second) ** 2 / max(denominator, 1e-12)
    return math.acosh(max(1.0, value))


def _sector_facing(face: dict[str, Any], target: complex) -> int:
    vertices = [complex(*point) for point in face["vertices"]]
    midpoints = [(vertices[index] + vertices[(index + 1) % SIDES]) / 2.0 for index in range(SIDES)]
    return min(range(SIDES), key=lambda index: _hyperbolic_distance(midpoints[index], target))


def _twist_cycles(faces: list[dict[str, Any]]) -> dict[str, dict[str, list[list[int]]]]:
    centers = {int(face["id"]): complex(*face["center"]) for face in faces}
    by_id = {int(face["id"]): face for face in faces}
    result: dict[str, dict[str, list[list[int]]]] = {}
    for face in faces:
        face_id = int(face["id"])
        origin = centers[face_id]
        nearest = sorted(
            (other for other in centers if other != face_id),
            key=lambda other: (_hyperbolic_distance(origin, centers[other]), other),
        )[:SIDES]
        nearest.sort(key=lambda other: math.atan2((centers[other] - origin).imag, (centers[other] - origin).real))
        ring = [[other, _sector_facing(by_id[other], origin)] for other in nearest]
        result[str(face_id)] = {
            "own": [[face_id, sector] for sector in range(SIDES)],
            "ring": ring,
        }
    return result


def apply_twist(
    state: tuple[tuple[int, ...], ...],
    cycles: dict[str, dict[str, list[list[int]]]],
    face_id: int,
    direction: int,
) -> tuple[tuple[int, ...], ...]:
    if direction not in (-1, 1):
        raise ValueError("twist direction must be -1 or 1")
    next_state = [list(face) for face in state]
    for cycle_name in ("own", "ring"):
        positions = cycles[str(face_id)][cycle_name]
        values = [state[face][sector] for face, sector in positions]
        shifted = values[-1:] + values[:-1] if direction == 1 else values[1:] + values[:1]
        for (face, sector), value in zip(positions, shifted):
            next_state[face][sector] = value
    return tuple(tuple(face) for face in next_state)


def is_solved(state: tuple[tuple[int, ...], ...]) -> bool:
    return bool(state) and all(len(set(face)) == 1 for face in state)


def _geometry(face_count: int, rotation_steps: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    angle = rotation_steps * 2.0 * math.pi / SIDES
    active_tiles = ACTIVE_TILE_ORDER[:face_count]
    face_for_tile = {tile_id: face_id for face_id, tile_id in enumerate(active_tiles)}
    tiles: list[dict[str, Any]] = []
    faces: list[dict[str, Any]] = []
    for source in _base_tiling():
        center = _rotate(complex(*source["center"]), angle)
        vertices = [_rotate(complex(*point), angle) for point in source["vertices"]]
        tile = {
            "id": source["id"],
            "depth": source["depth"],
            "center": [round(center.real, 9), round(center.imag, 9)],
            "vertices": [[round(point.real, 9), round(point.imag, 9)] for point in vertices],
            "face_id": face_for_tile.get(source["id"]),
        }
        tiles.append(tile)
        if tile["face_id"] is not None:
            faces.append({
                "id": tile["face_id"],
                "tile_id": tile["id"],
                "center": copy.deepcopy(tile["center"]),
                "vertices": copy.deepcopy(tile["vertices"]),
            })
    faces.sort(key=lambda item: item["id"])
    return tiles, faces


def _scramble_faces(rng: random.Random, face_count: int, length: int) -> list[int]:
    outer = list(range(8, face_count))
    required_outer = min(len(outer), max(1, length // 2)) if outer else 0
    for _attempt in range(256):
        sequence: list[int] = []
        for _index in range(length):
            choices = [face for face in range(face_count) if not sequence or face != sequence[-1]]
            sequence.append(rng.choice(choices))
        if len(set(sequence).intersection(outer)) >= required_outer:
            return sequence
    raise RuntimeError("could not distribute the scramble across the required outer faces")


def _move_operators(
    cycles: dict[str, dict[str, list[list[int]]]],
    face_count: int,
) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    operators = []
    for face_id in range(face_count):
        for direction in (-1, 1):
            destinations: list[int] = []
            sources: list[int] = []
            for cycle_name in ("own", "ring"):
                positions = cycles[str(face_id)][cycle_name]
                shifted = positions[1:] + positions[:1] if direction == -1 else positions[-1:] + positions[:-1]
                for (destination_face, destination_sector), (source_face, source_sector) in zip(positions, shifted):
                    destinations.append(destination_face * SIDES + destination_sector)
                    sources.append(source_face * SIDES + source_sector)
            operators.append((tuple(destinations), tuple(sources)))
    return tuple(operators)


def _apply_operator(
    state: bytes,
    operator: tuple[tuple[int, ...], tuple[int, ...]],
) -> bytes:
    destinations, sources = operator
    updated = bytearray(state)
    for destination, source in zip(destinations, sources):
        updated[destination] = state[source]
    return bytes(updated)


def _canonicalize_colors(state: bytes, face_count: int) -> bytes:
    """Quotient states by a global color renaming so every monochrome goal is equivalent."""
    order = sorted(range(face_count), key=state.index)
    translation = bytes.maketrans(bytes(order), bytes(range(face_count)))
    return state.translate(translation)


@lru_cache(maxsize=16)
def _solved_ball(
    face_count: int,
    operators: tuple[tuple[tuple[int, ...], tuple[int, ...]], ...],
    radius: int,
) -> frozenset[bytes]:
    solved = bytes(face_id for face_id in range(face_count) for _sector in range(SIDES))
    visited = {solved}
    frontier = {solved}
    for _depth in range(radius):
        following: set[bytes] = set()
        for state in frontier:
            for operator in operators:
                candidate = _canonicalize_colors(_apply_operator(state, operator), face_count)
                if candidate not in visited:
                    visited.add(candidate)
                    following.add(candidate)
        frontier = following
    return frozenset(visited)


def has_solution_shorter_than(
    state: tuple[tuple[int, ...], ...],
    cycles: dict[str, dict[str, list[list[int]]]],
    witness_length: int,
) -> bool:
    """Return whether any monochrome state is reachable in fewer than the witness moves."""
    face_count = len(state)
    operators = _move_operators(cycles, face_count)
    solved_radius = witness_length // 2
    candidate_radius = witness_length - 1 - solved_radius
    solved_states = _solved_ball(face_count, operators, solved_radius)
    encoded = _canonicalize_colors(bytes(color for face in state for color in face), face_count)
    if encoded in solved_states:
        return True
    visited = {encoded}
    frontier = {encoded}
    for _depth in range(candidate_radius):
        following: set[bytes] = set()
        for current in frontier:
            for operator in operators:
                candidate = _canonicalize_colors(_apply_operator(current, operator), face_count)
                if candidate in solved_states:
                    return True
                if candidate not in visited:
                    visited.add(candidate)
                    following.add(candidate)
        frontier = following
    return False


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = task.get("_control_condition")
    parameters = {**DEFAULTS, **dict((condition or {}).get("difficulty_parameters") or {})}
    face_count = int(parameters["face_count"])
    scramble_length = int(parameters["scramble_length"])
    move_budget = int(parameters["move_budget"])
    if not 8 <= face_count <= len(ACTIVE_TILE_ORDER):
        raise ValueError("circle-limit face_count must be between 8 and 15")
    if not 1 <= scramble_length <= 8:
        raise ValueError("circle-limit scramble_length must be between 1 and 8")
    if move_budget < scramble_length or move_budget > 24:
        raise ValueError("circle-limit move_budget must cover the scramble and stay finite")

    rng = random.Random(_seed(seed))
    rotation_steps = rng.randrange(SIDES)
    tiles, faces = _geometry(face_count, rotation_steps)
    cycles = _twist_cycles(faces)
    palette_values = list(PALETTE)
    rng.shuffle(palette_values)
    palette = [
        {"id": index, "fill": fill, "glint": glint, "motif": (index * 5 + rotation_steps) % 7}
        for index, (fill, glint) in enumerate(palette_values[:face_count])
    ]
    solved = tuple(tuple([face_id] * SIDES) for face_id in range(face_count))
    scramble: list[dict[str, int]] = []
    for _attempt in range(512):
        state = solved
        candidate: list[dict[str, int]] = []
        for face_id in _scramble_faces(rng, face_count, scramble_length):
            direction = rng.choice((-1, 1))
            state = apply_twist(state, cycles, face_id, direction)
            candidate.append({"face_id": face_id, "direction": direction})
        if not has_solution_shorter_than(state, cycles, scramble_length):
            scramble = candidate
            break
    if not scramble:
        raise RuntimeError("could not construct a scramble at the configured exact depth")
    solution = [
        {"face_id": move["face_id"], "direction": -move["direction"]}
        for move in reversed(scramble)
    ]
    token = f"|d{condition['difficulty']}|{task.get('id')}" if condition else ""
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|challenge{token}".encode()).hexdigest()[:12]
    puzzle = {
        "model": "poincare_heptagonal_reflection_v1",
        "sides": SIDES,
        "tiles": tiles,
        "faces": faces,
        "palette": palette,
        "initial_state": [list(face) for face in state],
        "twist_cycles": cycles,
        "scramble_length": scramble_length,
        "move_budget": move_budget,
        "activation_radius": 0.30,
        "rotation_steps": rotation_steps,
    }
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "challenge_id": challenge_id,
        "prompt": "Return every colored heptagon to one color before the twist limit.",
        "submit_label": "CERTIFY",
        "asset_manifest": "shared_runtime/assets/provenance/circle_limit_twist_v0.json",
        "generator": {"name": "reflected_heptagonal_permutation_v1", "variant_count": 7 * math.factorial(face_count)},
        "puzzle": puzzle,
    }
    truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "seed": seed,
        "challenge_id": challenge_id,
        "puzzle": copy.deepcopy(puzzle),
        "solution_moves": solution,
        "scramble_moves": scramble,
        "minimum_solution_depth": scramble_length,
    }
    if condition:
        public["control_condition"] = copy.deepcopy(condition)
        truth["control_condition"] = copy.deepcopy(condition)
    return public, truth
