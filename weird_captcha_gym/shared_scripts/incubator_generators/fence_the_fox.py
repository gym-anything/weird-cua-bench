from __future__ import annotations

from collections import deque
import copy
from functools import lru_cache
import hashlib
import json
import math
import random
from typing import Any


MECHANIC_ID = "fence_the_fox"
DIRECTIONS: tuple[tuple[int, int], ...] = (
    (1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1),
)
DIRECTION_NAMES = ("E", "NE", "NW", "W", "SW", "SE")
PALETTES = ("ember-pine", "blue-hour", "lichen-paper", "autumn-watch")

Coord = tuple[int, int]


def _coord(value: Coord) -> list[int]:
    return [value[0], value[1]]


@lru_cache(maxsize=2)
def _cells(radius: int) -> tuple[Coord, ...]:
    return tuple(
        sorted(
            (
                (q, r)
                for q in range(-radius, radius + 1)
                for r in range(-radius, radius + 1)
                if max(abs(q), abs(r), abs(-q - r)) <= radius
            ),
            key=lambda item: (item[1], item[0]),
        )
    )


def _edge(cell: Coord, radius: int) -> bool:
    q, r = cell
    return max(abs(q), abs(r), abs(-q - r)) == radius


def _neighbors(cell: Coord, cell_set: set[Coord]) -> tuple[Coord, ...]:
    q, r = cell
    return tuple((q + dq, r + dr) for dq, dr in DIRECTIONS if (q + dq, r + dr) in cell_set)


@lru_cache(maxsize=12_000)
def _distance_map(radius: int, blocked: frozenset[Coord]) -> dict[Coord, int]:
    cells = set(_cells(radius))
    distances = {cell: 0 for cell in cells if _edge(cell, radius) and cell not in blocked}
    queue = deque(sorted(distances, key=lambda item: (item[1], item[0])))
    while queue:
        current = queue.popleft()
        for neighbor in _neighbors(current, cells):
            if neighbor in blocked or neighbor in distances:
                continue
            distances[neighbor] = distances[current] + 1
            queue.append(neighbor)
    return distances


@lru_cache(maxsize=12_000)
def _fox_distances(radius: int, fox: Coord, blocked: frozenset[Coord]) -> dict[Coord, int]:
    cells = set(_cells(radius))
    distances = {fox: 0}
    queue = deque([fox])
    while queue:
        current = queue.popleft()
        for neighbor in _neighbors(current, cells):
            if neighbor in blocked or neighbor in distances:
                continue
            distances[neighbor] = distances[current] + 1
            queue.append(neighbor)
    return distances


def _wind_indices(wind_start: int) -> dict[Coord, int]:
    ordered = DIRECTIONS[wind_start:] + DIRECTIONS[:wind_start]
    return {direction: index for index, direction in enumerate(ordered)}


def _fox_choice(radius: int, fox: Coord, blocked: frozenset[Coord], wind_start: int) -> dict[str, Any]:
    cells = set(_cells(radius))
    distances = _distance_map(radius, blocked)
    if fox not in distances:
        return {"outcome": "trapped", "fox": fox, "distance": None, "onward": 0}
    wind = _wind_indices(wind_start)
    options: list[tuple[int, int, int, int, Coord]] = []
    for neighbor in _neighbors(fox, cells):
        if neighbor in blocked or neighbor not in distances:
            continue
        onward = sum(
            candidate not in blocked
            and candidate in distances
            and distances[candidate] == distances[neighbor] - 1
            for candidate in _neighbors(neighbor, cells)
        )
        degree = sum(candidate not in blocked for candidate in _neighbors(neighbor, cells))
        direction = (neighbor[0] - fox[0], neighbor[1] - fox[1])
        options.append((distances[neighbor], wind[direction], -onward, -degree, neighbor))
    if not options:
        return {"outcome": "trapped", "fox": fox, "distance": None, "onward": 0}
    options.sort()
    distance, _wind_rank, negative_onward, _negative_degree, destination = options[0]
    return {
        "outcome": "escaped" if _edge(destination, radius) else "moved",
        "fox": destination,
        "distance": distance,
        "onward": -negative_onward,
    }


def _simulate(
    radius: int,
    fox: Coord,
    blocked: frozenset[Coord],
    placement: Coord,
    wind_start: int,
) -> tuple[dict[str, Any], frozenset[Coord]]:
    next_blocked = blocked | {placement}
    return _fox_choice(radius, fox, next_blocked, wind_start), next_blocked


def _candidate_cells(
    radius: int,
    fox: Coord,
    blocked: frozenset[Coord],
    cap: int,
) -> list[Coord]:
    cells = set(_cells(radius))
    edge_distances = _distance_map(radius, blocked)
    fox_distances = _fox_distances(radius, fox, blocked)
    fox_edge_distance = edge_distances.get(fox, 10_000)
    fox_neighbors = set(_neighbors(fox, cells))

    def sort_key(cell: Coord) -> tuple[int, int, int, int, int]:
        on_shortest_path = (
            cell in fox_distances
            and cell in edge_distances
            and fox_distances[cell] + edge_distances[cell] == fox_edge_distance
        )
        return (
            0 if cell in fox_neighbors else 1,
            0 if on_shortest_path else 1,
            fox_distances.get(cell, 10_000),
            edge_distances.get(cell, 10_000),
            cell[1] * 32 + cell[0],
        )

    choices = sorted((cell for cell in cells if cell not in blocked and cell != fox), key=sort_key)
    return choices[:cap]


def _search_plan(
    radius: int,
    initial_fences: frozenset[Coord],
    wind_sequence: tuple[int, ...],
    maximum_turns: int,
) -> list[Coord] | None:
    cells = set(_cells(radius))
    frontier: list[tuple[Coord, frozenset[Coord], list[Coord]]] = [((0, 0), initial_fences, [])]
    seen: set[tuple[Coord, frozenset[Coord]]] = set()
    beam_width = 180 if radius == 3 else 260
    candidate_cap = min(34, len(cells))
    for _depth in range(1, maximum_turns + 1):
        children: list[tuple[float, Coord, frozenset[Coord], list[Coord]]] = []
        for fox, blocked, path in frontier:
            for placement in _candidate_cells(radius, fox, blocked, candidate_cap):
                reply, next_blocked = _simulate(
                    radius,
                    fox,
                    blocked,
                    placement,
                    wind_sequence[len(path)],
                )
                if reply["outcome"] == "trapped":
                    return [*path, placement]
                if reply["outcome"] == "escaped":
                    continue
                next_fox = reply["fox"]
                state_key = (next_fox, next_blocked)
                if state_key in seen:
                    continue
                seen.add(state_key)
                free_degree = sum(
                    neighbor not in next_blocked
                    for neighbor in _neighbors(next_fox, cells)
                )
                distance = int(reply["distance"] or 0)
                score = distance * 40 - int(reply["onward"]) * 7 - free_degree * 3
                children.append((score, next_fox, next_blocked, [*path, placement]))
        if not children:
            return None
        children.sort(key=lambda item: (-item[0], item[1][1], item[1][0], tuple(item[3])))
        frontier = [(fox, blocked, path) for _score, fox, blocked, path in children[:beam_width]]
    return None


def _exact_shortest_plan(
    radius: int,
    initial_fences: frozenset[Coord],
    wind_sequence: tuple[int, ...],
    maximum_turns: int,
) -> list[Coord] | None:
    """Return a globally shortest win by exhaustive breadth-first search.

    Radius-three fields are small enough to retain this proof in ordinary
    generation.  The search intentionally considers every currently legal
    placement, rather than the candidate cap and beam used to discover a
    good plan quickly.
    """

    cells = _cells(radius)
    frontier: dict[tuple[Coord, frozenset[Coord]], list[Coord]] = {
        ((0, 0), initial_fences): []
    }
    seen: set[tuple[Coord, frozenset[Coord]]] = set(frontier)
    for _depth in range(1, maximum_turns + 1):
        following: dict[tuple[Coord, frozenset[Coord]], list[Coord]] = {}
        for (fox, blocked), path in frontier.items():
            for placement in cells:
                if placement == fox or placement in blocked:
                    continue
                reply, next_blocked = _simulate(
                    radius,
                    fox,
                    blocked,
                    placement,
                    wind_sequence[len(path)],
                )
                candidate = [*path, placement]
                if reply["outcome"] == "trapped":
                    return candidate
                if reply["outcome"] == "escaped":
                    continue
                state_key = (reply["fox"], next_blocked)
                if state_key in seen:
                    continue
                seen.add(state_key)
                following[state_key] = candidate
        if not following:
            return None
        frontier = following
    return None


def _trace_plan(
    radius: int,
    initial_fences: frozenset[Coord],
    wind_sequence: tuple[int, ...],
    plan: list[Coord],
) -> list[dict[str, Any]]:
    fox = (0, 0)
    blocked = initial_fences
    trace = []
    for index, placement in enumerate(plan, start=1):
        before = fox
        wind_start = wind_sequence[index - 1]
        reply, blocked = _simulate(radius, fox, blocked, placement, wind_start)
        fox = reply["fox"]
        trace.append(
            {
                "sequence": index,
                "placed": _coord(placement),
                "fox_from": _coord(before),
                "fox_to": None if reply["outcome"] == "trapped" else _coord(fox),
                "outcome": reply["outcome"],
                "distance_after": reply["distance"],
                "wind_start": wind_start,
            }
        )
        if reply["outcome"] != "moved":
            break
    if not trace or trace[-1]["outcome"] != "trapped":
        raise ValueError("generated fence plan does not trap the fox")
    return trace


def _wind_changes_response(
    radius: int,
    fox: Coord,
    blocked: frozenset[Coord],
    placement: Coord,
) -> bool:
    destinations = set()
    for wind in range(len(DIRECTIONS)):
        reply, _next_blocked = _simulate(radius, fox, blocked, placement, wind)
        destinations.add((reply["outcome"], reply["fox"]))
    return len(destinations) > 1


def _trace_has_later_wind_decision(
    radius: int,
    initial_fences: frozenset[Coord],
    plan: list[Coord],
    trace: list[dict[str, Any]],
) -> bool:
    """Require a post-initial route priority to affect a visible reply.

    This prevents the changing vane from becoming decorative evidence: at
    least one placement after the initial screenshot reaches a state whose fox
    response differs under another displayed wind order.
    """

    blocked = initial_fences
    fox = (0, 0)
    for index, (placement, event) in enumerate(zip(plan, trace, strict=True)):
        if index > 0 and _wind_changes_response(radius, fox, blocked, placement):
            return True
        blocked = blocked | {placement}
        if event["outcome"] == "trapped":
            break
        fox = tuple(event["fox_to"])
    return False


def _build_instance(
    rng: random.Random,
    wind_rng: random.Random,
    parameters: dict[str, int],
) -> dict[str, Any]:
    radius = parameters["radius"]
    fence_count = parameters["initial_fence_count"]
    minimum_turns = parameters["minimum_plan_turns"]
    maximum_turns = parameters["maximum_plan_turns"]
    wind_start = rng.randrange(len(DIRECTIONS))
    wind_sequence = [wind_start]
    while len(wind_sequence) < parameters["stake_budget"]:
        wind_sequence.append(
            (wind_sequence[-1] + wind_rng.randrange(1, len(DIRECTIONS)))
            % len(DIRECTIONS)
        )
    wind_sequence_tuple = tuple(wind_sequence)
    cells = set(_cells(radius))
    interior = sorted(cells - {cell for cell in cells if _edge(cell, radius)} - {(0, 0)})
    for attempt in range(180):
        initial_fences = frozenset(rng.sample(interior, fence_count))
        if (0, 0) not in _distance_map(radius, initial_fences):
            continue
        if sum(neighbor not in initial_fences for neighbor in _neighbors((0, 0), cells)) < 2:
            continue
        plan = _search_plan(radius, initial_fences, wind_sequence_tuple, maximum_turns)
        if plan is None:
            continue
        if not minimum_turns <= len(plan) <= maximum_turns:
            continue
        trace = _trace_plan(radius, initial_fences, wind_sequence_tuple, plan)
        if len(plan) > 1 and not _trace_has_later_wind_decision(
            radius,
            initial_fences,
            plan,
            trace,
        ):
            continue
        proof_kind = "bounded_beam_discovery"
        shortest_plan_turns: int | None = None
        if radius == 3:
            exact_plan = _exact_shortest_plan(
                radius,
                initial_fences,
                wind_sequence_tuple,
                len(plan),
            )
            if exact_plan is None or len(exact_plan) != len(plan):
                continue
            proof_kind = "exhaustive_breadth_first_search"
            shortest_plan_turns = len(exact_plan)
        return {
            "attempt": attempt,
            "initial_fences": initial_fences,
            "wind_start": wind_start,
            "wind_sequence": wind_sequence_tuple,
            "plan": plan,
            "trace": trace,
            "shortest_plan_turns": shortest_plan_turns,
            "shortest_plan_certified": shortest_plan_turns is not None,
            "shortest_plan_proof": proof_kind,
            "post_initial_wind_influenced": len(plan) > 1,
        }
    raise ValueError(
        f"could not generate a solver-audited fence field with a {minimum_turns}-{maximum_turns} turn plan"
    )


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = task.get("_control_condition")
    supplied = dict((condition or {}).get("difficulty_parameters") or {})
    parameters = {
        "radius": int(supplied.get("radius", 3)),
        "initial_fence_count": int(supplied.get("initial_fence_count", 8)),
        "minimum_plan_turns": int(supplied.get("minimum_plan_turns", 3)),
        "maximum_plan_turns": int(supplied.get("maximum_plan_turns", 5)),
        "stake_budget": int(supplied.get("stake_budget", 5)),
    }
    radius = parameters["radius"]
    if radius not in {3, 4}:
        raise ValueError("fence field radius must be 3 or 4")
    cell_count = len(_cells(radius))
    if not 1 <= parameters["initial_fence_count"] < cell_count - 7:
        raise ValueError("initial fence count is outside supported limits")
    if not 1 <= parameters["minimum_plan_turns"] <= parameters["maximum_plan_turns"] <= parameters["stake_budget"] <= 10:
        raise ValueError("fence turn parameters are outside supported limits")

    parameter_token = ",".join(f"{key}={parameters[key]}" for key in sorted(parameters))
    digest = hashlib.sha256(f"{MECHANIC_ID}|{seed}|{parameter_token}|v1".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    wind_digest = hashlib.sha256(
        f"{MECHANIC_ID}|{seed}|{parameter_token}|wind-sequence-v2".encode("utf-8")
    ).digest()
    wind_rng = random.Random(int.from_bytes(wind_digest[:8], "big"))
    instance = _build_instance(rng, wind_rng, parameters)
    palette = PALETTES[rng.randrange(len(PALETTES))]
    task_id = str(task.get("id") or "fence_the_fox_seed_0001@0.1")
    difficulty = int((condition or {}).get("difficulty") or 3)
    challenge_id = hashlib.sha256(
        f"{MECHANIC_ID}|{seed}|d{difficulty}|{task_id}|v1".encode("utf-8")
    ).hexdigest()[:14]
    cells = _cells(radius)
    initial_fences = sorted(instance["initial_fences"], key=lambda item: (item[1], item[0]))
    wind_start = int(instance["wind_start"])
    wind_sequence = [int(value) for value in instance["wind_sequence"]]
    wind_order = [DIRECTION_NAMES[index % len(DIRECTION_NAMES)] for index in range(wind_start, wind_start + len(DIRECTION_NAMES))]
    driver_digest = hashlib.sha256(
        f"{MECHANIC_ID}|{seed}|{parameter_token}|stake-driver-v2".encode("utf-8")
    ).digest()
    driver_rng = random.Random(int.from_bytes(driver_digest[:8], "big"))
    driver_patterns = []
    for _turn in range(parameters["stake_budget"]):
        first = driver_rng.randrange(12)
        second = (first + driver_rng.choice((3, 4, 5, 7, 8, 9))) % 12
        driver_patterns.append([first, second])
    interaction = str((condition or {}).get("interaction") or "simplified")
    input_instruction = (
        "Drag the reusable stake to an open hex, keep holding, follow its numbered driver marks, return to center, and release"
        if interaction == "full"
        else "Click an open hex"
    )
    prompt = (
        f"Fence the fox before it reaches the glowing rim. {input_instruction} to place one of your "
        f"{parameters['stake_budget']} stakes. After each stake, the fox moves one cell along a shortest "
        "open route; ties follow the CURRENT WIND order shown beside the field, then prefer more shortest "
        f"continuations and more open neighbors (starting at {' > '.join(wind_order)}). The wind order changes after every "
        "fox step, so observe the new vane before placing again. Win by cutting every open route to the rim."
    )
    variant_count = len(PALETTES) * len(DIRECTIONS) * math.comb(cell_count - 1 - radius * 6, parameters["initial_fence_count"])
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": prompt,
        "submit_label": "CHECK ENCLOSURE",
        "asset_manifest": str((task.get("metadata") or {}).get("asset_manifest") or "shared_runtime/assets/provenance/fence_the_fox_v0.json"),
        "generator": {
            "name": "fence_the_fox_axial_search_v2",
            "search_attempt": instance["attempt"],
            "shortest_plan_certified": instance["shortest_plan_certified"],
            "shortest_plan_proof": instance["shortest_plan_proof"],
            "post_initial_wind_influenced": instance["post_initial_wind_influenced"],
            "variant_count": variant_count,
            "variant_count_kind": "initial-fence/palette/wind upper bound",
        },
        "radius": radius,
        "cells": [_coord(cell) for cell in cells],
        "fox_start": [0, 0],
        "initial_fences": [_coord(cell) for cell in initial_fences],
        "stake_budget": parameters["stake_budget"],
        "wind_start": wind_start,
        "wind_order": wind_order,
        "runtime_wind_sequence": wind_sequence,
        "wind_sequence_commitment": hashlib.sha256(
            json.dumps(wind_sequence, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "runtime_driver_patterns": driver_patterns,
        "driver_pattern_commitment": hashlib.sha256(
            json.dumps(driver_patterns, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "fox_policy": "Move one cell along a shortest open route. Ties follow the currently displayed wind order, then favor more shortest onward steps and more open neighbors. A new wind order is revealed after every fox step.",
        "parameters": copy.deepcopy(parameters),
        "palette": palette,
        "variant_count": variant_count,
        "variant_count_kind": "initial-fence/palette/wind upper bound",
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "radius": radius,
        "cells": [_coord(cell) for cell in cells],
        "fox_start": [0, 0],
        "initial_fences": [_coord(cell) for cell in initial_fences],
        "stake_budget": parameters["stake_budget"],
        "wind_start": wind_start,
        "wind_sequence": wind_sequence,
        "driver_patterns": copy.deepcopy(driver_patterns),
        "parameters": copy.deepcopy(parameters),
        "canonical_plan": [_coord(cell) for cell in instance["plan"]],
        "canonical_trace": copy.deepcopy(instance["trace"]),
        "solver_plan_turns": len(instance["plan"]),
        "shortest_plan_turns": instance["shortest_plan_turns"],
        "shortest_plan_certified": instance["shortest_plan_certified"],
        "shortest_plan_proof": instance["shortest_plan_proof"],
        "post_initial_wind_influenced": instance["post_initial_wind_influenced"],
        "palette": palette,
        "variant_count": variant_count,
        "variant_count_kind": "initial-fence/palette/wind upper bound",
    }
    if condition:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
