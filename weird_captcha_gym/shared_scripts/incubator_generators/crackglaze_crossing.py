from __future__ import annotations

import copy
import hashlib
import itertools
import json
import random
from collections import deque
from typing import Any, Iterable


MECHANIC_ID = "crackglaze_crossing"
ASSET_MANIFEST = "shared_runtime/assets/provenance/crackglaze_crossing_v0.json"
GLAZES = (
    {"id": "celadon", "label": "Celadon", "color": "#77a98d", "vein": "#d7ead9"},
    {"id": "cobalt", "label": "Cobalt", "color": "#315d91", "vein": "#a9c9e8"},
    {"id": "ochre", "label": "Ochre", "color": "#c88842", "vein": "#f6d8a4"},
    {"id": "oxblood", "label": "Oxblood", "color": "#7e3133", "vein": "#e0a4a1"},
)

# There was no pre-control implementation. This is the first source-grounded
# configuration, assigned by its active decision problem rather than by name.
BASELINE_PARAMETERS = {
    "core_rows": 5,
    "core_columns": 6,
    "core_cells": 15,
    "lantern_count": 3,
    "glaze_count": 3,
    "fuse_lengths": [3, 6, 10],
    "gallery_cells": 2,
    "crack_contrast": "standard",
    "minimum_policy_failures": 4,
}


Point = tuple[int, int]


def _condition(task: dict[str, Any]) -> dict[str, Any] | None:
    value = task.get("_control_condition")
    return copy.deepcopy(value) if isinstance(value, dict) else None


def _parameters(task: dict[str, Any]) -> dict[str, Any]:
    condition = _condition(task)
    if condition:
        return copy.deepcopy(condition["difficulty_parameters"])
    return copy.deepcopy(BASELINE_PARAMETERS)


def _cell_id(row: int, column: int) -> str:
    return f"r{row}c{column}"


def _validate(parameters: dict[str, Any]) -> None:
    integer_ranges = {
        "core_rows": (4, 6),
        "core_columns": (5, 7),
        "core_cells": (10, 22),
        "lantern_count": (2, 4),
        "glaze_count": (2, 4),
        "gallery_cells": (0, 8),
        "minimum_policy_failures": (1, 8),
    }
    for key, (lower, upper) in integer_ranges.items():
        value = parameters.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
            raise ValueError(f"{key} must be in [{lower}, {upper}]")
    if parameters["core_cells"] > parameters["core_rows"] * parameters["core_columns"]:
        raise ValueError("core_cells exceeds the core bounds")
    if parameters["gallery_cells"] > parameters["core_cells"]:
        raise ValueError("gallery_cells exceeds the core size")
    lengths = parameters.get("fuse_lengths")
    if (
        not isinstance(lengths, list)
        or len(lengths) != parameters["glaze_count"]
        or any(isinstance(value, bool) or not isinstance(value, int) for value in lengths)
        or sorted(lengths) != lengths
        or len(set(lengths)) != len(lengths)
        or lengths[0] < 3
    ):
        raise ValueError("fuse_lengths must be distinct increasing integers, one per glaze")
    if parameters.get("crack_contrast") not in {"clear", "standard", "subtle"}:
        raise ValueError("crack_contrast is invalid")


def _neighbors(cells: set[Point]) -> dict[Point, list[Point]]:
    return {
        point: sorted(
            other
            for other in (
                (point[0] - 1, point[1]),
                (point[0] + 1, point[1]),
                (point[0], point[1] - 1),
                (point[0], point[1] + 1),
            )
            if other in cells
        )
        for point in cells
    }


def _grow_core(rng: random.Random, rows: int, columns: int, count: int) -> set[Point]:
    cells = {(0, 0)}
    while len(cells) < count:
        frontier: dict[Point, int] = {}
        for row, column in cells:
            for candidate in ((row - 1, column), (row + 1, column), (row, column - 1), (row, column + 1)):
                if not (0 <= candidate[0] < rows and 0 <= candidate[1] < columns) or candidate in cells:
                    continue
                contacts = sum(
                    neighbor in cells
                    for neighbor in (
                        (candidate[0] - 1, candidate[1]),
                        (candidate[0] + 1, candidate[1]),
                        (candidate[0], candidate[1] - 1),
                        (candidate[0], candidate[1] + 1),
                    )
                )
                frontier[candidate] = max(frontier.get(candidate, 0), 1 + candidate[1] + contacts * 3)
        if not frontier:
            raise RuntimeError("Crackglaze core growth exhausted its frontier")
        choices = sorted(frontier)
        cells.add(rng.choices(choices, weights=[frontier[item] for item in choices], k=1)[0])
    return cells


def _shortest_path(
    neighbors: dict[Point, list[Point]],
    start: Point,
    goal: Point,
    *,
    reverse: bool = False,
    rng: random.Random | None = None,
) -> list[Point] | None:
    queue = deque([start])
    parent: dict[Point, Point | None] = {start: None}
    while queue:
        point = queue.popleft()
        if point == goal:
            path: list[Point] = []
            cursor: Point | None = point
            while cursor is not None:
                path.append(cursor)
                cursor = parent[cursor]
            return list(reversed(path))
        options = list(neighbors[point])
        if rng is not None:
            rng.shuffle(options)
        else:
            options.sort(reverse=reverse)
        for other in options:
            if other not in parent:
                parent[other] = point
                queue.append(other)
    return None


def _join_waypoints(
    neighbors: dict[Point, list[Point]],
    waypoints: Iterable[Point],
    *,
    reverse: bool = False,
    rng: random.Random | None = None,
) -> list[Point] | None:
    points = list(waypoints)
    result = [points[0]]
    for start, goal in zip(points, points[1:]):
        segment = _shortest_path(neighbors, start, goal, reverse=reverse, rng=rng)
        if segment is None:
            return None
        result.extend(segment[1:])
    return result


def _truncate_at_success(path: list[Point], exit_cell: Point, lanterns: list[Point]) -> list[Point]:
    required = set(lanterns)
    collected: set[Point] = set()
    for index, point in enumerate(path):
        if point in required:
            collected.add(point)
        if point == exit_cell and collected == required:
            return path[: index + 1]
    return path


def _geometry_state_path(
    neighbors: dict[Point, list[Point]], start: Point, exit_cell: Point, lanterns: list[Point], *, reverse: bool
) -> list[Point] | None:
    bits = {point: 1 << index for index, point in enumerate(lanterns)}
    complete = (1 << len(lanterns)) - 1
    initial = (start, bits.get(start, 0))
    queue = deque([initial])
    parent: dict[tuple[Point, int], tuple[Point, int] | None] = {initial: None}
    while queue:
        position, collected = queue.popleft()
        state = (position, collected)
        if position == exit_cell and collected == complete:
            path: list[Point] = []
            cursor: tuple[Point, int] | None = state
            while cursor is not None:
                path.append(cursor[0])
                cursor = parent[cursor]
            return list(reversed(path))
        for destination in sorted(neighbors[position], reverse=reverse):
            next_state = (destination, collected | bits.get(destination, 0))
            if next_state not in parent:
                parent[next_state] = state
                queue.append(next_state)
    return None


def _geometry_policy_paths(
    neighbors: dict[Point, list[Point]], start: Point, exit_cell: Point, lanterns: list[Point]
) -> list[list[Point]]:
    paths: list[list[Point]] = []
    for reverse in (False, True):
        path = _geometry_state_path(neighbors, start, exit_cell, lanterns, reverse=reverse)
        if path:
            paths.append(path)
        for order in itertools.permutations(lanterns):
            path = _join_waypoints(neighbors, (start, *order, exit_cell), reverse=reverse)
            if path:
                paths.append(_truncate_at_success(path, exit_cell, lanterns))
    unique: list[list[Point]] = []
    seen: set[tuple[Point, ...]] = set()
    for path in paths:
        signature = tuple(path)
        if signature not in seen:
            seen.add(signature)
            unique.append(path)
    return unique[:8]


def _candidate_paths(
    rng: random.Random,
    neighbors: dict[Point, list[Point]],
    start: Point,
    exit_cell: Point,
    lanterns: list[Point],
) -> list[list[Point]]:
    candidates: list[list[Point]] = []
    orders = list(itertools.permutations(lanterns))
    rng.shuffle(orders)
    for order in orders:
        for _ in range(4):
            path = _join_waypoints(neighbors, (start, *order, exit_cell), rng=rng)
            if path:
                candidates.append(_truncate_at_success(path, exit_cell, lanterns))
    seen: set[tuple[Point, ...]] = set()
    unique: list[list[Point]] = []
    for path in candidates:
        signature = tuple(path)
        if signature not in seen:
            seen.add(signature)
            unique.append(path)
    rng.shuffle(unique)
    return unique


def _revisit_requirements(path: list[Point]) -> dict[Point, int]:
    first_leave: dict[Point, int] = {}
    requirements: dict[Point, int] = {}
    for step, point in enumerate(path[:-1], 1):
        first_leave.setdefault(point, step)
    for step, point in enumerate(path[1:], 1):
        if point in first_leave:
            requirements[point] = max(requirements.get(point, 0), step - first_leave[point])
    return requirements


def _replay_path(path: list[Point], fuse_by_cell: dict[Point, int]) -> tuple[bool, Point | None, int]:
    lit_at: dict[Point, int] = {}
    for step, (origin, destination) in enumerate(zip(path, path[1:]), 1):
        lit_at.setdefault(origin, step)
        if destination in lit_at and step - lit_at[destination] >= fuse_by_cell[destination]:
            return False, destination, step
    return True, None, len(path) - 1


def _assign_for_path(
    rng: random.Random,
    cells: set[Point],
    intended: list[Point],
    geometry_paths: list[list[Point]],
    glaze_ids: list[str],
    fuse_by_glaze: dict[str, int],
    minimum_policy_failures: int,
) -> tuple[dict[Point, str], list[dict[str, Any]]] | None:
    requirements = _revisit_requirements(intended)
    feasible = {
        point: [glaze_id for glaze_id in glaze_ids if fuse_by_glaze[glaze_id] > requirements.get(point, 0)]
        for point in cells
    }
    if any(not values for values in feasible.values()):
        return None
    for _ in range(120):
        assignments = {point: rng.choice(feasible[point]) for point in sorted(cells)}
        shortest = min(glaze_ids, key=fuse_by_glaze.__getitem__)
        short_fuse = fuse_by_glaze[shortest]
        discriminators = [
            point
            for path in geometry_paths
            for point, gap in _revisit_requirements(path).items()
            if requirements.get(point, 0) < short_fuse <= gap and shortest in feasible[point]
        ]
        primary_discriminators = [
            point
            for point, gap in _revisit_requirements(geometry_paths[0]).items()
            if requirements.get(point, 0) < short_fuse <= gap and shortest in feasible[point]
        ]
        if not discriminators or not primary_discriminators:
            return None
        rng.shuffle(discriminators)
        rng.shuffle(primary_discriminators)
        assignments[primary_discriminators[0]] = shortest
        for point in discriminators[: max(0, minimum_policy_failures // 2 - 1)]:
            assignments[point] = shortest
        fuse_by_cell = {point: fuse_by_glaze[assignments[point]] for point in cells}
        if not _replay_path(intended, fuse_by_cell)[0]:
            continue
        results: list[dict[str, Any]] = []
        for index, path in enumerate(geometry_paths):
            passed, failure_cell, failure_step = _replay_path(path, fuse_by_cell)
            results.append({
                "policy": f"geometry_only_{index + 1}",
                "passed": passed,
                "steps": len(path) - 1,
                "failure_point": failure_cell,
                "failure_step": failure_step if not passed else None,
            })
        if not results[0]["passed"] and sum(not result["passed"] for result in results) >= minimum_policy_failures:
            return assignments, results
    return None


def _find_counterfactual(
    cells: set[Point],
    assignments: dict[Point, str],
    intended: list[Point],
    candidates: list[list[Point]],
    glaze_ids: list[str],
    actual_mapping: dict[str, int],
) -> dict[str, Any] | None:
    actual_cell_fuses = {point: actual_mapping[assignments[point]] for point in cells}
    values = [actual_mapping[glaze_id] for glaze_id in glaze_ids]
    for permutation in itertools.permutations(values):
        mapping = dict(zip(glaze_ids, permutation, strict=True))
        if mapping == actual_mapping:
            continue
        counterfactual_fuses = {point: mapping[assignments[point]] for point in cells}
        if _replay_path(intended, counterfactual_fuses)[0]:
            continue
        for path in candidates:
            if _replay_path(path, counterfactual_fuses)[0] and not _replay_path(path, actual_cell_fuses)[0]:
                common = 0
                for first, second in zip(intended, path):
                    if first != second:
                        break
                    common += 1
                return {
                    "fuse_lengths": mapping,
                    "solution": path,
                    "first_route_divergence": common,
                }
    return None


def _calibration_path(columns: int) -> list[Point]:
    return (
        [(0, column) for column in range(columns)]
        + [(1, columns - 1)]
        + [(2, column) for column in reversed(range(columns))]
        + [(3, 0), (4, 0)]
    )


def _offset(point: Point) -> Point:
    return point[0] + 4, point[1]


def generate(task: dict[str, Any], seed: str):
    parameters = _parameters(task)
    _validate(parameters)
    stable_input = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
    stable = hashlib.sha256(f"{MECHANIC_ID}:{seed}:{stable_input}".encode("utf-8")).hexdigest()
    rng = random.Random(int(stable[:16], 16))
    rows = int(parameters["core_rows"])
    columns = int(parameters["core_columns"])
    core_count = int(parameters["core_cells"])
    lantern_count = int(parameters["lantern_count"])
    glaze_specs = [copy.deepcopy(item) for item in GLAZES[: int(parameters["glaze_count"])]]
    glaze_ids = [str(item["id"]) for item in glaze_specs]
    shuffled_lengths = list(parameters["fuse_lengths"])
    rng.shuffle(shuffled_lengths)
    fuse_by_glaze = dict(zip(glaze_ids, shuffled_lengths, strict=True))

    selected: dict[str, Any] | None = None
    for topology_attempt in range(900):
        core = _grow_core(rng, rows, columns, core_count)
        neighbors = _neighbors(core)
        edge_count = sum(len(values) for values in neighbors.values()) // 2
        exits = [point for point in sorted(core) if point[1] == columns - 1]
        if not exits or edge_count < len(core) + 1:
            continue
        exit_cell = rng.choice(exits)
        eligible = [
            point for point in sorted(core)
            if point not in {(0, 0), exit_cell} and point[1] > 0 and len(neighbors[point]) >= 2
        ]
        if len(eligible) < lantern_count:
            continue
        lanterns = sorted(rng.sample(eligible, lantern_count))
        geometry_paths = _geometry_policy_paths(neighbors, (0, 0), exit_cell, lanterns)
        if len(geometry_paths) < int(parameters["minimum_policy_failures"]):
            continue
        candidates = _candidate_paths(rng, neighbors, (0, 0), exit_cell, lanterns)
        policy_signatures = {tuple(path) for path in geometry_paths}
        for intended in candidates:
            if tuple(intended) in policy_signatures:
                continue
            active_hidden_candidates = [
                point
                for point, gap in _revisit_requirements(intended).items()
                if gap > 0 and point not in {(0, 0), exit_cell}
            ]
            if len(active_hidden_candidates) < int(parameters["gallery_cells"]):
                continue
            assigned = _assign_for_path(
                rng,
                core,
                intended,
                geometry_paths,
                glaze_ids,
                fuse_by_glaze,
                int(parameters["minimum_policy_failures"]),
            )
            if assigned is None:
                continue
            assignments, ablations = assigned
            counterfactual = _find_counterfactual(
                core, assignments, intended, candidates, glaze_ids, fuse_by_glaze
            )
            if counterfactual is None:
                continue
            selected = {
                "core": core,
                "neighbors": neighbors,
                "exit": exit_cell,
                "lanterns": lanterns,
                "solution": intended,
                "assignments": assignments,
                "ablations": ablations,
                "geometry_paths": geometry_paths,
                "counterfactual": counterfactual,
                "topology_attempt": topology_attempt + 1,
                "candidate_count": len(candidates),
                "edge_count": edge_count,
            }
            break
        if selected is not None:
            break
    if selected is None:
        raise RuntimeError("could not generate a fuse-dependent Crackglaze floor")

    calibration = _calibration_path(columns)
    if calibration[-1] != _offset((0, 0)):
        raise RuntimeError("calibration path does not meet the generated core")
    core_global = {_offset(point) for point in selected["core"]}
    all_points = set(calibration) | core_global
    all_neighbors = _neighbors(all_points)
    global_solution = calibration + [_offset(point) for point in selected["solution"][1:]]
    global_counterfactual = calibration + [
        _offset(point) for point in selected["counterfactual"]["solution"][1:]
    ]

    assignments: dict[Point, str] = {
        _offset(point): glaze for point, glaze in selected["assignments"].items()
    }
    witness_order = list(glaze_ids)
    rng.shuffle(witness_order)
    for index, point in enumerate(calibration[:-1]):
        assignments[point] = witness_order[index] if index < len(witness_order) else rng.choice(glaze_ids)
    fuse_by_cell = {point: fuse_by_glaze[assignments[point]] for point in all_points}
    if not _replay_path(global_solution, fuse_by_cell)[0]:
        raise RuntimeError("constructed Crackglaze solution failed global physical replay")
    counter_mapping = selected["counterfactual"]["fuse_lengths"]
    counter_fuses = {point: counter_mapping[assignments[point]] for point in all_points}
    if _replay_path(global_solution, counter_fuses)[0] or not _replay_path(global_counterfactual, counter_fuses)[0]:
        raise RuntimeError("counterfactual Crackglaze certificate is inconsistent")

    repeated_core = [
        point for point, gap in _revisit_requirements(selected["solution"]).items()
        if gap > 0 and point not in {(0, 0), selected["exit"]}
    ]
    rng.shuffle(repeated_core)
    gallery_count = int(parameters["gallery_cells"])
    gallery_core = set(repeated_core[:gallery_count])
    if len(gallery_core) != gallery_count:
        raise RuntimeError("constructed Crackglaze route lacks active gallery revisits")
    gallery_global = {_offset(point) for point in gallery_core}

    task_id = str(task.get("id") or f"{MECHANIC_ID}_seed_0001")
    challenge_id = f"glaze-{stable[:18]}"
    start_point = calibration[0]
    exit_point = _offset(selected["exit"])
    lantern_points = {_offset(point) for point in selected["lanterns"]}
    cells: list[dict[str, Any]] = []
    for row, column in sorted(all_points):
        cell_id = _cell_id(row, column)
        cells.append({
            "id": cell_id,
            "row": row,
            "column": column,
            "glaze": assignments[(row, column)],
            "under_gallery": (row, column) in gallery_global,
            "lantern": (row, column) in lantern_points,
            "start": (row, column) == start_point,
            "exit": (row, column) == exit_point,
        })
    neighbor_ids = {
        _cell_id(*point): [_cell_id(*other) for other in values]
        for point, values in all_neighbors.items()
    }
    start_id = _cell_id(*start_point)
    exit_id = _cell_id(*exit_point)
    lantern_ids = sorted(_cell_id(*point) for point in lantern_points)
    certified = [_cell_id(*point) for point in global_solution]
    counterfactual_solution = [_cell_id(*point) for point in global_counterfactual]
    geometry_only_paths = [
        [_cell_id(*point) for point in calibration + [_offset(item) for item in path[1:]]]
        for path in selected["geometry_paths"]
    ]
    geometry_ablations = [
        {
            **{key: value for key, value in item.items() if key != "failure_point"},
            "failure_cell": _cell_id(*_offset(item["failure_point"])) if item["failure_point"] else None,
            "steps": len(geometry_only_paths[index]) - 1,
            "failure_step": (
                len(calibration) - 1 + int(item["failure_step"])
                if item["failure_step"] is not None else None
            ),
        }
        for index, item in enumerate(selected["ablations"])
    ]
    topology_hash = hashlib.sha256(json.dumps({
        "cells": sorted(core_global),
        "lanterns": sorted(lantern_points),
        "exit": exit_point,
    }, separators=(",", ":")).encode("utf-8")).hexdigest()[:18]

    shared = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "rows": rows + 4,
        "columns": columns,
        "cells": copy.deepcopy(cells),
        "neighbors": copy.deepcopy(neighbor_ids),
        "start_id": start_id,
        "exit_id": exit_id,
        "lantern_ids": lantern_ids,
        "glazes": copy.deepcopy(glaze_specs),
        "fuse_lengths": copy.deepcopy(fuse_by_glaze),
        "parameters": copy.deepcopy(parameters),
        "board_region": [0.12, 0.08, 0.76, 0.82],
    }
    public_state = {
        **copy.deepcopy(shared),
        "prompt": "GATHER EVERY LANTERN · REACH THE DOOR",
        "reference_steps": len(certified) - 1,
        "asset_manifest": str((task.get("metadata") or {}).get("asset_manifest") or ASSET_MANIFEST),
        "status": "ready",
    }
    ground_truth = {
        **copy.deepcopy(shared),
        "certified_solution": certified,
        "geometry_only_paths": geometry_only_paths,
        "calibration_cell_ids": [_cell_id(*point) for point in calibration[: len(glaze_ids)]],
        "search_certificate": {
            "algorithm": "seeded topology route enumeration with exact fuse replay",
            "solvable": True,
            "topology_hash": topology_hash,
            "topology_attempt": selected["topology_attempt"],
            "edge_count": selected["edge_count"],
            "candidate_paths_examined": selected["candidate_count"],
            "solution_steps": len(certified) - 1,
            "requires_revisit": len(certified) != len(set(certified)),
            "geometry_only_ablations": geometry_ablations,
            "counterfactual": {
                "same_geometry": True,
                "fuse_lengths": counter_mapping,
                "certified_solution": counterfactual_solution,
                "actual_solution_fails_counterfactual": True,
                "counterfactual_solution_fails_actual": True,
                "first_route_divergence": len(calibration) - 1
                + selected["counterfactual"]["first_route_divergence"],
            },
        },
    }
    condition = _condition(task)
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
