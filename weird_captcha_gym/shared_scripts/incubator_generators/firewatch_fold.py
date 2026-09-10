from __future__ import annotations

import copy
import hashlib
import random
from collections import deque
from typing import Any


MECHANIC_ID = "firewatch_fold"

DIRECTIONS: dict[str, tuple[int, int]] = {
    "UP": (0, 1),
    "RIGHT": (1, 0),
    "DOWN": (0, -1),
    "LEFT": (-1, 0),
}

BASELINE_PARAMETERS: dict[str, Any] = {
    "floor_count": 6,
    "floor_width": 9,
    "ladder_count": 2,
    "route_fire_count": 4,
    "decoy_fire_count": 3,
    "wall_count_per_floor": 2,
    "seam_crossings": 3,
    "inspection_complexity": "both_faces",
}


def _seed_int(seed: str) -> int:
    return int.from_bytes(
        hashlib.sha256(f"{seed}|{MECHANIC_ID}|v2".encode("utf-8")).digest()[:8],
        "big",
    )


def _condition(task: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    condition = copy.deepcopy(task.get("_control_condition"))
    if not isinstance(condition, dict):
        return None, dict(BASELINE_PARAMETERS)
    parameters = dict(condition.get("difficulty_parameters") or {})
    merged = dict(BASELINE_PARAMETERS)
    merged.update(parameters)
    return condition, merged


def _key(face: int, floor: int, x: int) -> tuple[int, int, int]:
    return int(face), int(floor), int(x)


def _walk_step(
    position: list[int],
    direction: str,
    width: int,
    steps: list[dict[str, Any]],
) -> None:
    face, floor, x = position
    if direction == "RIGHT":
        if x == width - 1:
            position[0] = 1 - face
            position[2] = 0
        else:
            position[2] += 1
    elif direction == "LEFT":
        if x == 0:
            position[0] = 1 - face
            position[2] = width - 1
        else:
            position[2] -= 1
    elif direction == "UP":
        position[1] += 1
    elif direction == "DOWN":
        position[1] -= 1
    else:
        raise ValueError(f"unsupported route direction {direction}")
    steps.append(
        {
            "action": "MOVE",
            "direction": direction,
            "target": [position[0], position[1], position[2]],
        }
    )


def _towards(position: list[int], target_x: int, width: int, steps: list[dict[str, Any]]) -> None:
    while position[2] < target_x:
        _walk_step(position, "RIGHT", width, steps)
    while position[2] > target_x:
        _walk_step(position, "LEFT", width, steps)


def _add_unique(values: list[int], value: int) -> None:
    if value not in values:
        values.append(value)


def _target(position: tuple[int, int, int], direction: str, width: int) -> tuple[int, int, int]:
    face, floor, x = position
    dx, dy = DIRECTIONS[direction]
    if direction == "RIGHT" and x == width - 1:
        return 1 - face, floor, 0
    if direction == "LEFT" and x == 0:
        return 1 - face, floor, width - 1
    return face, floor + dy, x + dx


def _find_path(
    start: tuple[int, int, int],
    goal: tuple[int, int, int],
    *,
    width: int,
    floors: int,
    walls: set[tuple[int, int, int]],
    ladders: set[tuple[int, int, int]],
    blocked: set[tuple[int, int, int]],
) -> list[tuple[int, int, int]] | None:
    """Find a legal movement path while treating selected fire cells as closed."""
    if start in walls or start in blocked or goal in walls or goal in blocked:
        return None
    pending = deque([start])
    previous: dict[tuple[int, int, int], tuple[tuple[int, int, int], str] | None] = {start: None}
    for_position = ("UP", "RIGHT", "DOWN", "LEFT")
    while pending:
        position = pending.popleft()
        if position == goal:
            break
        for direction in for_position:
            target = _target(position, direction, width)
            if not 0 <= target[1] < floors:
                continue
            if target in previous or target in walls or target in blocked:
                continue
            if direction in {"UP", "DOWN"}:
                ladder_position = position if direction == "UP" else target
                if ladder_position not in ladders:
                    continue
            previous[target] = (position, direction)
            pending.append(target)
    if goal not in previous:
        return None
    path = [goal]
    cursor = goal
    while previous[cursor] is not None:
        cursor = previous[cursor][0]
        path.append(cursor)
    path.reverse()
    return path


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition, parameters = _condition(task)
    rng = random.Random(_seed_int(seed))
    floors = int(parameters["floor_count"])
    width = int(parameters["floor_width"])
    ladder_count = int(parameters["ladder_count"])
    route_fire_count = int(parameters["route_fire_count"])
    decoy_fire_count = int(parameters["decoy_fire_count"])
    wall_count = int(parameters["wall_count_per_floor"])
    seam_crossings = int(parameters["seam_crossings"])
    if floors < 3 or width < 6:
        raise ValueError("Firewatch Fold needs at least three floors and six cells")
    if not 0 <= seam_crossings <= floors - 1:
        raise ValueError("seam crossings must fit between floors")

    start_x = rng.randint(1, width - 2)
    position = [0, 0, start_x]
    route_steps: list[dict[str, Any]] = []
    primary_ladders: dict[tuple[int, int], int] = {}
    seam_sides: list[str] = []

    for floor in range(floors - 1):
        if floor < seam_crossings:
            side = "LEFT" if rng.random() < 0.5 else "RIGHT"
            seam_sides.append(side)
            edge = 0 if side == "LEFT" else width - 1
            _towards(position, edge, width, route_steps)
            _walk_step(position, side, width, route_steps)
        ladder_x = rng.randint(1, width - 2)
        primary_ladders[(position[0], floor)] = ladder_x
        _towards(position, ladder_x, width, route_steps)
        _walk_step(position, "UP", width, route_steps)

    goal_x = rng.randint(1, width - 2)
    _towards(position, goal_x, width, route_steps)
    resident = list(position)
    start = [0, 0, start_x]

    ladders: list[list[list[int]]] = [
        [[] for _ in range(floors)] for _face in range(2)
    ]
    for face in range(2):
        for floor in range(floors - 1):
            values: list[int] = []
            primary = primary_ladders.get((face, floor))
            if primary is not None:
                values.append(primary)
            candidates = list(range(1, width - 1))
            rng.shuffle(candidates)
            for candidate in candidates:
                if len(values) >= ladder_count:
                    break
                _add_unique(values, candidate)
            ladders[face][floor] = sorted(values)

    route_positions = {_key(*step["target"]) for step in route_steps}
    route_positions.add(_key(*start))
    route_positions.add(_key(*resident))

    # Reserve an alternate route before placing masonry. A fire cut is placed
    # across every ladder at one floor boundary, so every legal route must
    # spend at least one canister. The canonical route is then given enough
    # additional route fires to use the nominal stock, while the alternate
    # route uses exactly one. This makes stock a real route-choice constraint.
    internal_floors = list(range(1, floors - 1))
    if route_fire_count < 1:
        raise ValueError("Firewatch Fold needs at least one extinguisher")
    route_sequence: list[tuple[int, int, int]] = []
    for step in route_steps:
        target = tuple(int(value) for value in step["target"])
        if target not in route_sequence:
            route_sequence.append(target)
    ladder_cells = {
        _key(face, floor, x)
        for face in range(2)
        for floor in range(floors)
        for x in ladders[face][floor]
    }

    chosen_boundary: int | None = None
    chosen_cut_points: list[tuple[int, int, int]] = []
    chosen_canonical_cut_points: list[tuple[int, int, int]] = []
    chosen_additional_points: list[tuple[int, int, int]] = []
    alternate_fire_point: tuple[int, int, int] | None = None
    preliminary_alternate_path: list[tuple[int, int, int]] | None = None
    boundary_candidates: list[tuple[int, int, list[tuple[int, int, int]], list[tuple[int, int, int]]]] = []
    for boundary in range(floors - 1):
        cut_points = [
            _key(face, boundary + 1, x)
            for face in range(2)
            for x in ladders[face][boundary]
        ]
        cut_set = set(cut_points)
        canonical_cut_points = [point for point in route_sequence if point in cut_set]
        if not canonical_cut_points or len(canonical_cut_points) > route_fire_count:
            continue
        boundary_candidates.append((len(canonical_cut_points), boundary, cut_points, canonical_cut_points))
    boundary_candidates.sort(key=lambda item: (item[0], item[1]))
    for canonical_cut_count, boundary, cut_points, canonical_cut_points in boundary_candidates:
        additional_count = route_fire_count - canonical_cut_count
        cut_set = set(cut_points)
        for candidate in cut_points:
            preliminary_path = _find_path(
                tuple(start),
                tuple(resident),
                width=width,
                floors=floors,
                walls=set(),
                ladders=ladder_cells,
                blocked=cut_set - {candidate},
            )
            if preliminary_path is None or candidate not in preliminary_path:
                continue
            path_cells = set(preliminary_path)
            additional_candidates = [
                point
                for point in route_sequence
                if point not in cut_set
                and point not in path_cells
                and point not in {tuple(start), tuple(resident)}
            ]
            if len(additional_candidates) < additional_count:
                continue
            chosen_boundary = boundary
            chosen_cut_points = cut_points
            chosen_canonical_cut_points = canonical_cut_points
            chosen_additional_points = additional_candidates[:additional_count]
            alternate_fire_point = candidate
            preliminary_alternate_path = preliminary_path
            break
        if preliminary_alternate_path is not None:
            break
    if (
        chosen_boundary is None
        or alternate_fire_point is None
        or preliminary_alternate_path is None
    ):
        raise ValueError("generated tower has no one-fire alternate route")
    route_fire_points = chosen_cut_points + chosen_additional_points
    safety_reserved = set(preliminary_alternate_path)
    walls: list[list[list[int]]] = [[[] for _floor in range(floors)] for _face in range(2)]
    for face in range(2):
        for floor in range(floors):
            if floor == 0 and face == 0:
                protected = {_key(face, floor, start_x)}
            else:
                protected = set()
            protected.update(
                _key(face, floor, x)
                for x in ladders[face][floor]
            )
            protected.update(
                point for point in route_positions if point[:2] == (face, floor)
            )
            protected.update(
                point for point in route_fire_points if point[:2] == (face, floor)
            )
            protected.update(
                point for point in safety_reserved if point[:2] == (face, floor)
            )
            candidates = [
                x
                for x in range(1, width - 1)
                if _key(face, floor, x) not in protected
            ]
            rng.shuffle(candidates)
            walls[face][floor] = sorted(candidates[: min(wall_count, len(candidates))])

    wall_cells = {
        _key(face, floor, x)
        for face in range(2)
        for floor in range(floors)
        for x in walls[face][floor]
    }
    ladder_cells = {
        _key(face, floor, x)
        for face in range(2)
        for floor in range(floors)
        for x in ladders[face][floor]
    }
    start_point = tuple(start)
    resident_point = tuple(resident)
    alternate_path = _find_path(
        start_point,
        resident_point,
        width=width,
        floors=floors,
        walls=wall_cells,
        ladders=ladder_cells,
        blocked=set(route_fire_points) - {alternate_fire_point},
    )
    if alternate_path is None or alternate_fire_point not in alternate_path:
        raise ValueError("wall placement removed the one-fire alternate route")

    fires: list[list[list[dict[str, Any]]]] = [[[] for _floor in range(floors)] for _face in range(2)]
    fire_lookup: dict[tuple[int, int, int], str] = {}
    route_fire_ids: list[str] = []
    for index, point in enumerate(route_fire_points):
        face, floor, x = point
        fire_id = f"fire_{index + 1:02d}"
        route_fire_ids.append(fire_id)
        fires[face][floor].append({"id": fire_id, "x": x, "kind": "route"})
        fire_lookup[point] = fire_id

    occupied = set(fire_lookup)
    occupied.update(route_positions)
    occupied.update(wall_cells)
    alternate_path_cells = set(alternate_path)
    alternate_ladder_candidates = [
        _key(face, floor, x)
        for face in range(2)
        for floor in range(floors)
        for x in range(1, width - 1)
        if _key(face, floor, x) not in occupied
        and _key(face, floor, x) not in alternate_path_cells
        and _key(face, floor, x) in ladder_cells
    ]
    other_decoy_candidates = [
        _key(face, floor, x)
        for face in range(2)
        for floor in range(floors)
        for x in range(1, width - 1)
        if _key(face, floor, x) not in occupied
        and _key(face, floor, x) not in alternate_path_cells
        and _key(face, floor, x) not in set(alternate_ladder_candidates)
    ]
    rng.shuffle(alternate_ladder_candidates)
    rng.shuffle(other_decoy_candidates)
    decoy_candidates = alternate_ladder_candidates + other_decoy_candidates
    if len(decoy_candidates) < decoy_fire_count:
        raise ValueError("generated tower does not have enough safe decoy fire locations")
    for index, (face, floor, x) in enumerate(decoy_candidates[:decoy_fire_count]):
        fire_id = f"ember_{index + 1:02d}"
        fires[face][floor].append({"id": fire_id, "x": x, "kind": "decoy"})
        fire_lookup[(face, floor, x)] = fire_id

    face_names = ("NORTH FACE", "SOUTH FACE")
    face_tones = ("copper", "indigo")
    face_data: list[dict[str, Any]] = []
    for face in range(2):
        floor_data: list[dict[str, Any]] = []
        for floor in range(floors):
            floor_data.append(
                {
                    "level": floor + 1,
                    "ladders": list(ladders[face][floor]),
                    "walls": list(walls[face][floor]),
                    "fires": sorted(fires[face][floor], key=lambda item: (item["x"], item["id"])),
                }
            )
        face_data.append({"id": face, "label": face_names[face], "tone": face_tones[face], "floors": floor_data})

    task_id = str(task.get("id") or "firewatch_fold_seed_0001@0.1")
    condition_token = ""
    if condition:
        condition_token = f"|d{int(condition['difficulty'])}|{condition['interaction']}|{task_id}"
    challenge_id = hashlib.sha256(
        f"{seed}|{MECHANIC_ID}{condition_token}".encode("utf-8")
    ).hexdigest()[:12]
    interaction = str((condition or {}).get("interaction") or "full")
    control_condition = copy.deepcopy(condition) if condition else None

    solution_actions: list[dict[str, Any]] = []
    if seam_crossings > 0:
        solution_actions.append({"action": "INSPECT", "face": 1})
    emitted_fires: set[str] = set()
    emitted_fire_ids: list[str] = []
    for step in route_steps:
        target = tuple(int(value) for value in step["target"])
        direction = str(step["direction"])
        fire_id = fire_lookup.get(target)
        if fire_id is not None and fire_id not in emitted_fires:
            # Facing is stateful.  The first press toward a fire stops at its
            # cell and establishes the direction; extinguishing then clears
            # the adjacent fire, and the repeated move enters it.
            solution_actions.append({"action": "MOVE", "direction": direction})
            solution_actions.append({"action": "EXTINGUISH", "direction": direction, "fire_id": fire_id})
            emitted_fires.add(fire_id)
            emitted_fire_ids.append(fire_id)
        solution_actions.append({"action": "MOVE", "direction": direction})
    if len(emitted_fire_ids) != route_fire_count:
        raise ValueError("canonical route does not consume the nominal extinguisher stock")

    tower = {
        "floor_count": floors,
        "floor_width": width,
        "faces": face_data,
        "start": start,
        "resident": resident,
        "palette": rng.randrange(5),
    }
    public_state: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Reach the resident. Choose an affordable route and use extinguishers only when needed.",
        "submit_label": "CERTIFY RESCUE",
        "asset_manifest": "shared_runtime/assets/provenance/firewatch_fold_v0.json",
        "generator": {
            "name": "firewatch_fold_v2",
            "variant_count": 2 * floors * width,
            "seam_crossings": seam_crossings,
        },
        "tower": tower,
        "extinguisher_count": route_fire_count,
        "rules": {
            "movement": "Arrow keys move one cell; walking past either floor edge crosses to the other face.",
            "fire": "A marked fire blocks its cell until you face it and use one extinguisher. Choose a route whose fire cost fits the stock.",
            "ladder": "UP and DOWN work only at a visible ladder connection.",
            "inspection": "The eye reveals the other face without moving the firefighter.",
        },
        "interaction": interaction,
    }
    ground_truth: dict[str, Any] = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "initial_tower": copy.deepcopy(tower),
        "extinguisher_count": route_fire_count,
        "solution_actions": copy.deepcopy(solution_actions),
        "route_fire_ids": list(route_fire_ids),
        "parameters": copy.deepcopy(parameters),
        "interaction": interaction,
        "seam_crossings": seam_crossings,
        "decoy_fire_count": decoy_fire_count,
        "control_condition": control_condition,
        "resource_options": {
            "alternate_route_available": True,
            "alternate_route_fire_clears": 1,
            "alternate_route_move_count": len(alternate_path) - 1,
            "minimum_route_fire_clears": 1,
            "alternate_route_fire_id": fire_lookup[alternate_fire_point],
            "canonical_route_fire_clears": len(emitted_fire_ids),
            "canonical_route_fire_ids": list(emitted_fire_ids),
            "route_fire_object_count": len(route_fire_ids),
            "canonical_route_move_count": sum(
                1 for action in solution_actions if action.get("action") == "MOVE"
            ),
        },
    }
    if control_condition is not None:
        public_state["control_condition"] = copy.deepcopy(control_condition)
        ground_truth["control_condition"] = copy.deepcopy(control_condition)
    return public_state, ground_truth
