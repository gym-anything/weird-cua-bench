"""Seeded lifeboat-and-passenger worlds for Last Seats in the Lagoon.

The generator deliberately keeps the world independent of the input surface.  A
full task drags a boat by one orthogonal cell; a simplified task presses the
same one-cell direction through a visible control pad.  The boats, passengers,
reefs, capacities, and solution geometry are shared by both modes.
"""

from __future__ import annotations

import copy
import hashlib
import itertools
import random
from typing import Any


MECHANIC_ID = "last_seats_in_the_lagoon"
STAGE = {"width": 960, "height": 560}
VARIANT_COUNT = 4_800_000_000
DIRS = {
    "N": (0, -1),
    "E": (1, 0),
    "S": (0, 1),
    "W": (-1, 0),
}

DEFAULT_PARAMETERS: dict[str, Any] = {
    "columns": 10,
    "rows": 7,
    "boat_count": 3,
    "boat_orientations": ["horizontal", "horizontal", "vertical"],
    "boat_capacities": [2, 2, 1],
    "passengers_per_boat": [2, 2, 1],
    "route_span": 4,
    "route_cycles": 2,
    "reef_count": 4,
    "reef_buffer": 0,
}


def _seed_int(seed: str, salt: str) -> int:
    return int.from_bytes(
        hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).digest()[:8],
        "big",
    )


def _boat_shape(orientation: str) -> tuple[int, int]:
    return (2, 1) if orientation == "horizontal" else (1, 2)


def _cells(boat: dict[str, Any], anchor: tuple[int, int] | None = None) -> set[tuple[int, int]]:
    x, y = anchor or (int(boat["x"]), int(boat["y"]))
    width, height = _boat_shape(str(boat["orientation"]))
    return {(x + dx, y + dy) for dx in range(width) for dy in range(height)}


def _rope_cells(boat: dict[str, Any], anchor: tuple[int, int] | None = None) -> set[tuple[int, int]]:
    x, y = anchor or (int(boat["x"]), int(boat["y"]))
    if str(boat["orientation"]) == "horizontal":
        return {(x, y - 1), (x + 1, y - 1), (x, y + 1), (x + 1, y + 1)}
    return {(x - 1, y), (x - 1, y + 1), (x + 1, y), (x + 1, y + 1)}


def _inside(boat: dict[str, Any], anchor: tuple[int, int], columns: int, rows: int) -> bool:
    return all(0 <= x < columns and 0 <= y < rows for x, y in _cells(boat, anchor))


def _candidate_clear(
    boat: dict[str, Any],
    anchor: tuple[int, int],
    boats: list[dict[str, Any]],
    reefs: set[tuple[int, int]],
    columns: int,
    rows: int,
    *,
    ignore_id: str | None = None,
) -> bool:
    footprint = _cells(boat, anchor)
    if not _inside(boat, anchor, columns, rows) or footprint & reefs:
        return False
    for other in boats:
        if str(other["id"]) == ignore_id:
            continue
        if footprint & _cells(other):
            return False
    return True


def _apply_move(
    boats: list[dict[str, Any]],
    passengers: list[dict[str, Any]],
    boat_id: str,
    direction: str,
    reefs: set[tuple[int, int]],
    columns: int,
    rows: int,
) -> tuple[bool, list[str]]:
    boat = next((item for item in boats if str(item["id"]) == boat_id), None)
    if boat is None or direction not in DIRS:
        return False, []
    dx, dy = DIRS[direction]
    target = (int(boat["x"]) + dx, int(boat["y"]) + dy)
    if not _candidate_clear(boat, target, boats, reefs, columns, rows, ignore_id=boat_id):
        return False, []
    boat["x"], boat["y"] = target
    free = int(boat["capacity"]) - len(boat.setdefault("occupants", []))
    contacts = _rope_cells(boat)
    boarded: list[str] = []
    for passenger in sorted(passengers, key=lambda item: str(item["id"])):
        if passenger.get("boarded") or free <= 0:
            continue
        if tuple(passenger["position"]) not in contacts:
            continue
        passenger["boarded"] = True
        passenger["boat_id"] = boat_id
        passenger["seat"] = len(boat["occupants"])
        boat["occupants"].append(str(passenger["id"]))
        free -= 1
        boarded.append(str(passenger["id"]))
    return True, boarded


def _route(orientation: str, span: int, cycles: int) -> list[str]:
    forward, backward = (("E", "W") if orientation == "horizontal" else ("S", "N"))
    result: list[str] = []
    for _ in range(cycles):
        result.extend([forward] * span)
        result.extend([backward] * span)
    return result


def _start_slots(
    columns: int, rows: int, orientations: list[str], span: int
) -> list[tuple[int, int]]:
    horizontal_y = [1, max(1, rows // 2 - 1), rows - 2, 1, rows - 2]
    vertical_x = [
        max(1, columns - 2 - 2 * index)
        for index in range(max(1, len(orientations) + 1))
    ]
    h_index = v_index = 0
    slots: list[tuple[int, int]] = []
    for orientation in orientations:
        if orientation == "horizontal":
            # The route runs east first, so leave the entire forward span
            # available.  Separate horizontal boats by water lanes instead of
            # placing a second hull on the vertical boat's lane.
            x = 1
            y = horizontal_y[h_index % len(horizontal_y)]
            h_index += 1
        else:
            x = vertical_x[v_index % len(vertical_x)]
            # The vertical route runs south first and therefore starts at the
            # top of its dedicated column.
            y = 1
            v_index += 1
        slots.append((x, y))
    return slots


def _passenger_candidates(
    boats: list[dict[str, Any]],
    routes: list[list[str]],
    counts: list[int],
    rng: random.Random,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    used_positions: set[tuple[int, int]] = set()
    occupied_initial = set().union(*(set(_cells(boat)) for boat in boats))
    for boat, route, count in zip(boats, routes, counts):
        x, y = int(boat["x"]), int(boat["y"])
        states: list[tuple[int, int]] = [(x, y)]
        for direction in route:
            dx, dy = DIRS[direction]
            x, y = x + dx, y + dy
            states.append((x, y))
        initial_rope = _rope_cells(boat, states[0])
        useful: list[tuple[int, int]] = []
        for index in range(1, len(states)):
            before = _rope_cells(boat, states[index - 1])
            after = _rope_cells(boat, states[index])
            for position in sorted(before & after):
                # A passenger starts in the water, not under a hull or
                # already at a rope side.  Keep only distinct reachable
                # water cells so the first visible board state is unambiguous.
                if (
                    position in initial_rope
                    or position in occupied_initial
                    or position in useful
                    or position in used_positions
                ):
                    continue
                useful.append(position)
        if len(useful) < count:
            raise ValueError("route does not offer enough side contacts")
        selected = rng.sample(useful, count)
        used_positions.update(selected)
        for position in selected:
            candidates.append({
                "position": [int(position[0]), int(position[1])],
                "boat_hint": str(boat["id"]),
            })
    return candidates


def _protected_cells(
    boats: list[dict[str, Any]], routes: list[list[str]], passengers: list[dict[str, Any]]
) -> set[tuple[int, int]]:
    protected: set[tuple[int, int]] = set()
    for boat, route in zip(boats, routes):
        x, y = int(boat["x"]), int(boat["y"])
        protected |= _cells(boat, (x, y)) | _rope_cells(boat, (x, y))
        for direction in route:
            dx, dy = DIRS[direction]
            x, y = x + dx, y + dy
            protected |= _cells(boat, (x, y)) | _rope_cells(boat, (x, y))
    protected |= {tuple(item["position"]) for item in passengers}
    return protected


def _solution_for(
    initial_boats: list[dict[str, Any]],
    initial_passengers: list[dict[str, Any]],
    routes: list[list[str]],
    reefs: set[tuple[int, int]],
    columns: int,
    rows: int,
) -> list[dict[str, Any]] | None:
    for order in itertools.permutations(range(len(initial_boats))):
        boats = copy.deepcopy(initial_boats)
        passengers = copy.deepcopy(initial_passengers)
        solution: list[dict[str, Any]] = []
        valid = True
        for boat_index in order:
            boat_id = str(boats[boat_index]["id"])
            for direction in routes[boat_index]:
                accepted, boarded = _apply_move(
                    boats, passengers, boat_id, direction, reefs, columns, rows
                )
                if not accepted:
                    valid = False
                    break
                solution.append({
                    "boat_id": boat_id,
                    "direction": direction,
                    "boarded": boarded,
                })
            if not valid:
                break
        if valid and all(item.get("boarded") for item in passengers):
            return solution
    return None


def _parameters(task: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    condition = task.get("_control_condition")
    if not isinstance(condition, dict):
        condition = (task.get("metadata") or {}).get("control_condition")
    if not isinstance(condition, dict):
        condition = None
    parameters = copy.deepcopy(DEFAULT_PARAMETERS)
    parameters.update(copy.deepcopy((condition or {}).get("difficulty_parameters") or {}))
    count = int(parameters["boat_count"])
    orientations = [str(item) for item in parameters.get("boat_orientations", [])]
    if len(orientations) != count or any(item not in {"horizontal", "vertical"} for item in orientations):
        raise ValueError("boat orientations do not match boat_count")
    capacities = [int(item) for item in parameters.get("boat_capacities", [])]
    passenger_counts = [int(item) for item in parameters.get("passengers_per_boat", [])]
    if len(capacities) != count or len(passenger_counts) != count:
        raise ValueError("boat capacity arrays do not match boat_count")
    if any(capacity < count_for_boat for capacity, count_for_boat in zip(capacities, passenger_counts)):
        raise ValueError("every boat must have enough seats for its generated passengers")
    parameters["boat_orientations"] = orientations
    parameters["boat_capacities"] = capacities
    parameters["passengers_per_boat"] = passenger_counts
    return parameters, condition


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    parameters, condition = _parameters(task)
    columns = int(parameters["columns"])
    rows = int(parameters["rows"])
    boat_count = int(parameters["boat_count"])
    span = int(parameters["route_span"])
    cycles = int(parameters["route_cycles"])
    reef_count = int(parameters["reef_count"])
    if not 7 <= columns <= 16 or not 5 <= rows <= 10:
        raise ValueError("lagoon dimensions are outside supported limits")
    if not 1 <= boat_count <= 4 or span < 2 or cycles < 1:
        raise ValueError("lagoon route parameters are outside supported limits")

    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    orientations = list(parameters["boat_orientations"])
    slots = _start_slots(columns, rows, orientations, span)
    routes = [_route(orientation, span, cycles) for orientation in orientations]

    for attempt in range(480):
        jittered_slots = []
        for index, (x, y) in enumerate(slots):
            orientation = orientations[index]
            if orientation == "horizontal":
                x = max(1, min(columns - 3 - span, x + rng.choice((0, 0, 0, 1))))
                y = max(1, min(rows - 2, y + rng.choice((-1, 0, 0, 1))))
            else:
                x = max(1, min(columns - 2, x + rng.choice((0, 0, 0, -1))))
                y = max(1, min(rows - 3 - span, y + rng.choice((0, 0, 0, 1))))
            jittered_slots.append((x, y))
        boats: list[dict[str, Any]] = []
        occupied: set[tuple[int, int]] = set()
        valid_starts = True
        for index, (orientation, anchor) in enumerate(zip(orientations, jittered_slots)):
            boat = {
                "id": f"boat-{index + 1}",
                "x": int(anchor[0]),
                "y": int(anchor[1]),
                "orientation": orientation,
                "capacity": int(parameters["boat_capacities"][index]),
                "occupants": [],
                "color": ["coral", "saffron", "indigo", "mint"][index % 4],
            }
            if _cells(boat) & occupied:
                valid_starts = False
                break
            occupied |= _cells(boat)
            boats.append(boat)
        if not valid_starts:
            continue

        try:
            passenger_specs = _passenger_candidates(
                boats, routes, list(parameters["passengers_per_boat"]), rng
            )
        except ValueError:
            continue
        passengers = [
            {
                "id": f"passenger-{index + 1}",
                "position": list(spec["position"]),
                "boat_hint": spec["boat_hint"],
                "boarded": False,
            }
            for index, spec in enumerate(passenger_specs)
        ]
        protected = _protected_cells(boats, routes, passengers)
        reef_pool = [
            (x, y)
            for y in range(rows)
            for x in range(columns)
            if (x, y) not in protected
            and all(abs(x - px) + abs(y - py) > int(parameters.get("reef_buffer", 0)) for px, py in protected)
        ]
        if len(reef_pool) < reef_count:
            continue
        reefs = set(rng.sample(reef_pool, reef_count))
        if any(_cells(boat) & reefs for boat in boats):
            continue
        solution = _solution_for(boats, passengers, routes, reefs, columns, rows)
        if solution is None:
            continue

        challenge_id = hashlib.sha256(
            f"{seed}|{MECHANIC_ID}|d{(condition or {}).get('difficulty', 4)}".encode("utf-8")
        ).hexdigest()[:16]
        palette = rng.choice(("seafoam", "moonlit", "sunset", "stormglass"))
        public_boats = copy.deepcopy(boats)
        public_passengers = [
            {"id": item["id"], "position": list(item["position"])} for item in passengers
        ]
        public = {
            "benchmark": "weird_captcha_gym",
            "mechanic_id": MECHANIC_ID,
            "task_id": str(task.get("id") or f"{MECHANIC_ID}_seed_0001@0.1"),
            "challenge_id": challenge_id,
            "prompt": str(task.get("natural_language") or "Move every lifeboat so all passengers board safely."),
            "submit_label": "CERTIFY RESCUE",
            "stage": STAGE,
            "board": {"columns": columns, "rows": rows},
            "boats": public_boats,
            "passengers": public_passengers,
            "reefs": [[x, y] for x, y in sorted(reefs, key=lambda point: (point[1], point[0]))],
            "rules": {
                "boat_moves": "one orthogonal cell per action",
                "rotation": "forbidden",
                "diagonal": "forbidden",
                "pickup": "automatic at rope-side contact while a seat is free",
            },
            "palette": palette,
            "generator": {"name": "procedural_lifeboat_lagoon_v1", "variant_count": VARIANT_COUNT},
            "asset_manifest": "shared_runtime/assets/provenance/last_seats_in_the_lagoon_v0.json",
        }
        if condition is not None:
            public["control_condition"] = copy.deepcopy(condition)
        truth = copy.deepcopy(public)
        truth.update({
            "seed": seed,
            "initial_boats": copy.deepcopy(boats),
            "initial_passengers": copy.deepcopy(passengers),
            "solution_path": [{"boat_id": item["boat_id"], "direction": item["direction"]} for item in solution],
            "solution_boarded": [item["boarded"] for item in solution],
        })
        return public, truth
    raise RuntimeError("could not generate a solvable lifeboat lagoon")
