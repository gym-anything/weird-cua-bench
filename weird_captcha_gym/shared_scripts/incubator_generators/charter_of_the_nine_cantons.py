from __future__ import annotations

import copy
import hashlib
import itertools
import random
from collections import Counter, deque
from typing import Any


MECHANIC_ID = "charter_of_the_nine_cantons"
GUILDS = (
    {"id": "gilt", "name": "GILT", "mark": "SUN", "color": "#d6a63a"},
    {"id": "tide", "name": "TIDE", "mark": "WAVE", "color": "#3a91a6"},
    {"id": "plum", "name": "PLUM", "mark": "BLOOM", "color": "#a65378"},
)
CANTON_COLORS = (
    "#d86b4b", "#e3a52f", "#a3ad43", "#4ea17d", "#3f91aa",
    "#567bc2", "#8766b1", "#b85e93", "#b46f4d",
)
TARGET_WINNERS = ("gilt", "tide", "gilt", "plum", "gilt", "tide", "gilt", "plum", "gilt")
TARGET_SPLIT = {"gilt": 5, "tide": 2, "plum": 2}
DEFAULT_PARAMETERS = {
    "columns": 15,
    "rows": 9,
    "boundary_warp_steps": 12,
    "displaced_parcels": 8,
    "change_budget": 18,
    "winner_margin": 1,
    "population_tolerance": 1,
}


def _condition(task: dict[str, Any]) -> dict[str, Any] | None:
    value = task.get("_control_condition")
    return copy.deepcopy(value) if isinstance(value, dict) else None


def _parameters(task: dict[str, Any]) -> dict[str, Any]:
    condition = _condition(task)
    raw = copy.deepcopy(condition["difficulty_parameters"] if condition else DEFAULT_PARAMETERS)
    # Materialized JSON is written with sorted keys.  Rebuild the historical
    # parameter order before hashing so the controlled profile containing the
    # exact original settings reproduces the uncontrolled fixed-seed world.
    ordered = {key: raw[key] for key in DEFAULT_PARAMETERS if key in raw}
    ordered.update({key: raw[key] for key in sorted(set(raw) - set(DEFAULT_PARAMETERS))})
    return ordered


def _validate(parameters: dict[str, Any]) -> None:
    optional = {
        "construction_mode", "exchange_count", "bundle_size",
        "minimum_brush_changes", "minimum_brush_path",
    }
    if not set(DEFAULT_PARAMETERS) <= set(parameters) or not set(parameters) <= set(DEFAULT_PARAMETERS) | optional:
        raise ValueError("difficulty parameters do not match the nine-canton contract")
    for key, low, high in (
        ("columns", 9, 18), ("rows", 6, 9), ("boundary_warp_steps", 0, 30),
        ("displaced_parcels", 2, 36), ("change_budget", 4, 36),
        ("winner_margin", 1, 5), ("population_tolerance", 0, 1),
    ):
        value = parameters.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"{key} must be an integer in [{low}, {high}]")
    if parameters["columns"] % 3 or parameters["rows"] % 3:
        raise ValueError("columns and rows must divide into the nine charter cantons")
    parcel_count = parameters["columns"] * parameters["rows"]
    if parcel_count % 9:
        raise ValueError("parcel count must divide equally among nine cantons")
    if parameters["change_budget"] < parameters["displaced_parcels"]:
        raise ValueError("change budget cannot be smaller than the repair set")
    mode = parameters.get("construction_mode", "legacy_center_repair")
    if mode not in {"legacy_center_repair", "balanced_exchange"}:
        raise ValueError("construction_mode is invalid")
    if mode == "legacy_center_repair" and set(parameters) != set(DEFAULT_PARAMETERS):
        raise ValueError("the preserved original construction cannot carry exchange parameters")
    if mode == "balanced_exchange":
        for key, low, high in (
            ("exchange_count", 1, 4), ("bundle_size", 1, 4),
            ("minimum_brush_changes", 1, 4), ("minimum_brush_path", 2, 9),
        ):
            value = parameters.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise ValueError(f"{key} must be an integer in [{low}, {high}]")
        if parameters["displaced_parcels"] != 2 * parameters["exchange_count"] * parameters["bundle_size"]:
            raise ValueError("balanced exchanges must account for every displaced parcel")
        if parameters["minimum_brush_changes"] > parameters["bundle_size"]:
            raise ValueError("brush change requirement exceeds one generated exchange bundle")


def _grid(columns: int, rows: int) -> tuple[list[str], dict[str, list[str]]]:
    ids = [f"p{row:02d}{column:02d}" for row in range(rows) for column in range(columns)]
    adjacency: dict[str, list[str]] = {}
    for row in range(rows):
        for column in range(columns):
            parcel_id = f"p{row:02d}{column:02d}"
            neighbors = []
            for dc, dr in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                cc, rr = column + dc, row + dr
                if 0 <= cc < columns and 0 <= rr < rows:
                    neighbors.append(f"p{rr:02d}{cc:02d}")
            adjacency[parcel_id] = neighbors
    return ids, adjacency


def _polygons(columns: int, rows: int, rng: random.Random) -> dict[str, list[list[float]]]:
    cell_w, cell_h = 1000.0 / columns, 600.0 / rows
    points: list[list[tuple[float, float]]] = []
    for row in range(rows + 1):
        line = []
        for column in range(columns + 1):
            x, y = column * cell_w, row * cell_h
            if 0 < column < columns:
                x += rng.uniform(-cell_w * 0.20, cell_w * 0.20)
            if 0 < row < rows:
                y += rng.uniform(-cell_h * 0.18, cell_h * 0.18)
            line.append((round(x, 3), round(y, 3)))
        points.append(line)
    return {
        f"p{row:02d}{column:02d}": [
            list(points[row][column]), list(points[row][column + 1]),
            list(points[row + 1][column + 1]), list(points[row + 1][column]),
        ]
        for row in range(rows)
        for column in range(columns)
    }


def _connected(canton: int, assignment: dict[str, int], adjacency: dict[str, list[str]]) -> bool:
    members = {parcel_id for parcel_id, owner in assignment.items() if owner == canton}
    if not members:
        return False
    seen = {next(iter(members))}
    queue = deque(seen)
    while queue:
        current = queue.popleft()
        for neighbor in adjacency[current]:
            if neighbor in members and neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return seen == members


def _canonical_assignment(columns: int, rows: int) -> dict[str, int]:
    band_w, band_h = columns // 3, rows // 3
    return {
        f"p{row:02d}{column:02d}": (row // band_h) * 3 + column // band_w
        for row in range(rows)
        for column in range(columns)
    }


def _warp_boundaries(
    assignment: dict[str, int], adjacency: dict[str, list[str]], steps: int, rng: random.Random
) -> dict[str, int]:
    result = dict(assignment)
    parcel_ids = list(result)
    completed = 0
    for _attempt in range(max(80, steps * 100)):
        if completed >= steps:
            break
        candidates = [
            parcel_id for parcel_id in parcel_ids
            if any(result[neighbor] != result[parcel_id] for neighbor in adjacency[parcel_id])
        ]
        rng.shuffle(candidates)
        moved = False
        for first in candidates:
            source, destination_choices = result[first], sorted({result[n] for n in adjacency[first] if result[n] != result[first]})
            rng.shuffle(destination_choices)
            for destination in destination_choices:
                trial = dict(result)
                trial[first] = destination
                if not _connected(source, trial, adjacency) or not _connected(destination, trial, adjacency):
                    continue
                reverse = [
                    parcel_id for parcel_id in parcel_ids
                    if parcel_id != first and result[parcel_id] == destination
                    and any(trial[n] == source for n in adjacency[parcel_id])
                ]
                rng.shuffle(reverse)
                for second in reverse:
                    balanced = dict(trial)
                    balanced[second] = source
                    if _connected(source, balanced, adjacency) and _connected(destination, balanced, adjacency):
                        result = balanced
                        completed += 1
                        moved = True
                        break
                if moved:
                    break
            if moved:
                break
    if completed < steps:
        raise RuntimeError("could not construct enough connected boundary warps")
    return result


def _winner_counts(population: int, minimum_margin: int) -> tuple[int, int, int]:
    candidates = []
    for winner in range(1, population + 1):
        for runner in range(winner):
            third = population - winner - runner
            if 0 <= third <= runner and winner - runner >= minimum_margin:
                candidates.append((winner - runner, winner, runner - third, winner, runner, third))
    if not candidates:
        raise RuntimeError("no guild distribution satisfies the requested margin")
    _gap, _winner, _balance, winner, runner, third = min(candidates)
    return winner, runner, third


def _guild_assignment(
    assignment: dict[str, int], population: int, minimum_margin: int, rng: random.Random
) -> dict[str, str]:
    guild_ids = [guild["id"] for guild in GUILDS]
    winner_count, runner_count, third_count = _winner_counts(population, minimum_margin)
    parties: dict[str, str] = {}
    for canton, winning_guild in enumerate(TARGET_WINNERS):
        members = [parcel_id for parcel_id, owner in assignment.items() if owner == canton]
        rng.shuffle(members)
        losing = [guild_id for guild_id in guild_ids if guild_id != winning_guild]
        if rng.random() < 0.5:
            losing.reverse()
        labels = [winning_guild] * winner_count + [losing[0]] * runner_count + [losing[1]] * third_count
        rng.shuffle(labels)
        parties.update(zip(members, labels))
    return parties


def _boundary_paths(
    assignment: dict[str, int], adjacency: dict[str, list[str]], source: int,
    destination: int, length: int, rng: random.Random,
) -> list[list[str]]:
    candidates = {
        parcel_id for parcel_id, owner in assignment.items()
        if owner == source and any(assignment[neighbor] == destination for neighbor in adjacency[parcel_id])
    }
    starts = sorted(candidates)
    rng.shuffle(starts)
    paths: list[list[str]] = []

    def visit(path: list[str]) -> None:
        if len(paths) >= 80:
            return
        if len(path) == length:
            paths.append(path[:])
            return
        choices = sorted(
            neighbor for neighbor in adjacency[path[-1]]
            if neighbor in candidates and neighbor not in path
        )
        rng.shuffle(choices)
        for neighbor in choices:
            visit([*path, neighbor])

    for start in starts:
        visit([start])
    # A path and its reversal paint the same bundle.  Retain only one copy.
    unique: dict[tuple[str, ...], list[str]] = {}
    for path in paths:
        key = min(tuple(path), tuple(reversed(path)))
        unique.setdefault(key, path)
    values = list(unique.values())
    rng.shuffle(values)
    return values


def _exchange_options(
    target: dict[str, int], adjacency: dict[str, list[str]], left: int,
    right: int, bundle_size: int, rng: random.Random,
) -> list[dict[str, Any]]:
    left_paths = _boundary_paths(target, adjacency, left, right, bundle_size, rng)
    right_paths = _boundary_paths(target, adjacency, right, left, bundle_size, rng)
    pairs = list(itertools.product(left_paths[:24], right_paths[:24]))
    rng.shuffle(pairs)
    options = []
    for left_path, right_path in pairs:
        trial = dict(target)
        for parcel_id in left_path:
            trial[parcel_id] = right
        for parcel_id in right_path:
            trial[parcel_id] = left
        if not _connected(left, trial, adjacency) or not _connected(right, trial, adjacency):
            continue
        options.append({
            "cantons": [left, right],
            "transfers": [
                {"from_canton": left, "to_canton": right, "parcels": left_path},
                {"from_canton": right, "to_canton": left, "parcels": right_path},
            ],
        })
        if len(options) >= 12:
            break
    return options


def _balanced_exchange_plan(
    target: dict[str, int], adjacency: dict[str, list[str]], exchange_count: int,
    bundle_size: int, rng: random.Random,
) -> list[dict[str, Any]]:
    pairs = sorted({
        tuple(sorted((owner, target[neighbor])))
        for parcel_id, owner in target.items() for neighbor in adjacency[parcel_id]
        if owner != target[neighbor]
        and TARGET_WINNERS[owner] != TARGET_WINNERS[target[neighbor]]
        and "gilt" in {TARGET_WINNERS[owner], TARGET_WINNERS[target[neighbor]]}
    })
    rng.shuffle(pairs)
    options = {
        pair: _exchange_options(target, adjacency, pair[0], pair[1], bundle_size, rng)
        for pair in pairs
    }

    def choose(index: int, used: set[int], selected: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        if len(selected) == exchange_count:
            return selected
        if len(pairs) - index < exchange_count - len(selected):
            return None
        for offset in range(index, len(pairs)):
            pair = pairs[offset]
            if used.intersection(pair) or not options[pair]:
                continue
            candidates = options[pair][:]
            rng.shuffle(candidates)
            for option in candidates:
                found = choose(offset + 1, used | set(pair), [*selected, option])
                if found is not None:
                    return found
        return None

    selected = choose(0, set(), [])
    if selected is None:
        raise RuntimeError("could not construct enough disjoint balanced exchanges")
    for index, exchange in enumerate(selected, 1):
        exchange["exchange_id"] = f"exchange-{index}"
    return selected


def _guild_assignment_for_exchanges(
    assignment: dict[str, int], population: int, minimum_margin: int,
    exchanges: list[dict[str, Any]], rng: random.Random,
) -> dict[str, str]:
    guild_ids = [guild["id"] for guild in GUILDS]
    winner_count, runner_count, third_count = _winner_counts(population, minimum_margin)
    forced: dict[str, str] = {}
    preferred_runner: dict[int, str] = {}
    for exchange in exchanges:
        first, second = exchange["cantons"]
        # Every eligible boundary joins a Gilt target canton to Tide or Plum.
        # Orient the exchange so each unresolved pair removes one Gilt holding;
        # the effects cannot cancel when several exchanges are combined.
        if TARGET_WINNERS[first] == "gilt":
            left, right = second, first
        else:
            left, right = first, second
        left_winner, right_winner = TARGET_WINNERS[left], TARGET_WINNERS[right]
        third_guild = next(guild_id for guild_id in guild_ids if guild_id not in {left_winner, right_winner})
        left_transfer = next(item for item in exchange["transfers"] if item["from_canton"] == left)
        right_transfer = next(item for item in exchange["transfers"] if item["from_canton"] == right)
        for parcel_id in left_transfer["parcels"]:
            forced[parcel_id] = left_winner
        for parcel_id in right_transfer["parcels"]:
            forced[parcel_id] = third_guild
        preferred_runner[left] = third_guild
        preferred_runner[right] = left_winner

    parties: dict[str, str] = {}
    for canton, winning_guild in enumerate(TARGET_WINNERS):
        members = [parcel_id for parcel_id, owner in assignment.items() if owner == canton]
        rng.shuffle(members)
        losing = [guild_id for guild_id in guild_ids if guild_id != winning_guild]
        runner = preferred_runner.get(canton)
        if runner is None:
            rng.shuffle(losing)
            runner = losing[0]
        third = next(guild_id for guild_id in losing if guild_id != runner)
        required = Counter(forced[parcel_id] for parcel_id in members if parcel_id in forced)
        available = {winning_guild: winner_count, runner: runner_count, third: third_count}
        if any(required[guild_id] > available[guild_id] for guild_id in guild_ids):
            raise RuntimeError("exchange bundle exceeds its target guild allocation")
        remaining = []
        for guild_id, count in available.items():
            remaining.extend([guild_id] * (count - required[guild_id]))
        rng.shuffle(remaining)
        for parcel_id in members:
            if parcel_id in forced:
                parties[parcel_id] = forced[parcel_id]
            else:
                parties[parcel_id] = remaining.pop()
    return parties


def _balanced_displace(
    target: dict[str, int], adjacency: dict[str, list[str]], population: int,
    minimum_margin: int, exchange_count: int, bundle_size: int, rng: random.Random,
) -> tuple[dict[str, int], list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    exchanges = _balanced_exchange_plan(target, adjacency, exchange_count, bundle_size, rng)
    parties = _guild_assignment_for_exchanges(target, population, minimum_margin, exchanges, rng)
    initial = dict(target)
    moved: list[dict[str, Any]] = []
    for exchange in exchanges:
        for bundle_index, transfer in enumerate(exchange["transfers"], 1):
            for parcel_id in transfer["parcels"]:
                initial[parcel_id] = transfer["to_canton"]
                moved.append({
                    "parcel_id": parcel_id,
                    "from_canton": transfer["from_canton"],
                    "to_canton": transfer["to_canton"],
                    "exchange_id": exchange["exchange_id"],
                    "bundle_id": f"{exchange['exchange_id']}-{bundle_index}",
                })
    if not all(_connected(canton, initial, adjacency) for canton in range(9)):
        raise RuntimeError("balanced exchange disconnected an initial canton")
    return initial, moved, exchanges, parties


def _stats(
    assignment: dict[str, int], parties: dict[str, str], adjacency: dict[str, list[str]],
    ideal_population: int, tolerance: int,
) -> dict[str, Any]:
    cantons = []
    seat_split = {guild["id"]: 0 for guild in GUILDS}
    for canton in range(9):
        members = [parcel_id for parcel_id, owner in assignment.items() if owner == canton]
        counts = Counter(parties[parcel_id] for parcel_id in members)
        ordered = counts.most_common()
        winner = ordered[0][0] if ordered and (len(ordered) == 1 or ordered[0][1] > ordered[1][1]) else "tie"
        if winner != "tie":
            seat_split[winner] += 1
        cantons.append({
            "id": canton,
            "population": len(members),
            "population_ok": abs(len(members) - ideal_population) <= tolerance,
            "connected": _connected(canton, assignment, adjacency),
            "guild_counts": {guild["id"]: counts.get(guild["id"], 0) for guild in GUILDS},
            "winner": winner,
        })
    completed = all(entry["population_ok"] and entry["connected"] for entry in cantons) and seat_split == TARGET_SPLIT
    return {"cantons": cantons, "seat_split": seat_split, "completed": completed}


def _displace(
    target: dict[str, int], adjacency: dict[str, list[str]], count: int,
    parties: dict[str, str], ideal_population: int, tolerance: int, rng: random.Random,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    initial = dict(target)
    moved: list[dict[str, Any]] = []
    moved_ids: set[str] = set()
    donors = [1, 3, 5, 7]
    for index in range(count):
        source_canton = donors[index % len(donors)]
        destination_canton = 4
        candidates = [
            parcel_id for parcel_id, owner in initial.items()
            if parcel_id not in moved_ids
            and owner == source_canton
            and source_canton != destination_canton
            and any(initial[neighbor] == destination_canton for neighbor in adjacency[parcel_id])
        ]
        rng.shuffle(candidates)
        chosen = None
        for parcel_id in candidates:
            trial = dict(initial)
            trial[parcel_id] = destination_canton
            if _connected(source_canton, trial, adjacency) and _connected(destination_canton, trial, adjacency):
                chosen = parcel_id
                initial = trial
                break
        if chosen is None:
            # Warped maps occasionally exhaust one side. Use any boundary between
            # two cantons while preserving both components; the repair remains visible.
            fallback = [
                (parcel_id, neighbor, initial[parcel_id], initial[neighbor])
                for parcel_id in initial for neighbor in adjacency[parcel_id]
                if parcel_id not in moved_ids and initial[parcel_id] != initial[neighbor]
            ]
            rng.shuffle(fallback)
            for parcel_id, _neighbor, source, destination in fallback:
                trial = dict(initial)
                trial[parcel_id] = destination
                if _connected(source, trial, adjacency) and _connected(destination, trial, adjacency):
                    chosen = parcel_id
                    source_canton = source
                    destination_canton = destination
                    initial = trial
                    break
        if chosen is None:
            raise RuntimeError("could not displace a connected boundary parcel")
        moved_ids.add(chosen)
        moved.append({
            "parcel_id": chosen,
            "from_canton": source_canton,
            "to_canton": destination_canton,
        })
    if _stats(initial, parties, adjacency, ideal_population, tolerance)["completed"]:
        raise RuntimeError("constructed initial charter already passes")
    return initial, moved


def _construct(parameters: dict[str, Any], stable: str):
    for attempt in range(80):
        rng = random.Random(int(hashlib.sha256(f"{stable}:{attempt}".encode()).hexdigest()[:16], 16))
        parcel_ids, adjacency = _grid(parameters["columns"], parameters["rows"])
        target = _warp_boundaries(
            _canonical_assignment(parameters["columns"], parameters["rows"]),
            adjacency, parameters["boundary_warp_steps"], rng,
        )
        ideal_population = len(parcel_ids) // 9
        exchanges = None
        try:
            if parameters.get("construction_mode") == "balanced_exchange":
                initial, displaced, exchanges, parties = _balanced_displace(
                    target, adjacency, ideal_population, parameters["winner_margin"],
                    parameters["exchange_count"], parameters["bundle_size"], rng,
                )
            else:
                parties = _guild_assignment(target, ideal_population, parameters["winner_margin"], rng)
                initial, displaced = _displace(
                    target, adjacency, parameters["displaced_parcels"], parties,
                    ideal_population, parameters["population_tolerance"], rng,
                )
        except RuntimeError:
            continue
        target_stats = _stats(target, parties, adjacency, ideal_population, parameters["population_tolerance"])
        initial_stats = _stats(initial, parties, adjacency, ideal_population, parameters["population_tolerance"])
        if target_stats["completed"] and not initial_stats["completed"]:
            return parcel_ids, adjacency, _polygons(parameters["columns"], parameters["rows"], rng), parties, target, initial, displaced, target_stats, exchanges
    raise RuntimeError("could not construct a valid nine-canton charter")


def generate(task: dict[str, Any], seed: str):
    parameters = _parameters(task)
    _validate(parameters)
    stable = hashlib.sha256(f"{MECHANIC_ID}:{seed}:{parameters}".encode("utf-8")).hexdigest()
    parcel_ids, adjacency, polygons, parties, target, initial, displaced, target_stats, exchanges = _construct(parameters, stable)
    task_id = str(task.get("id") or MECHANIC_ID)
    challenge_id = f"cn-{stable[:18]}"
    condition = _condition(task)
    ideal_population = len(parcel_ids) // 9
    parcels = [
        {"id": parcel_id, "polygon": polygons[parcel_id], "guild": parties[parcel_id], "households": 1}
        for parcel_id in parcel_ids
    ]
    public_state = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": "Ratify the nine-canton charter.",
        "parcels": parcels,
        "adjacency": copy.deepcopy(adjacency),
        "initial_assignment": copy.deepcopy(initial),
        "guilds": copy.deepcopy(list(GUILDS)),
        "canton_colors": list(CANTON_COLORS),
        "target_seat_split": copy.deepcopy(TARGET_SPLIT),
        "ideal_population": ideal_population,
        "population_tolerance": parameters["population_tolerance"],
        "parameters": copy.deepcopy(parameters),
        "status": "ready",
        "asset_manifest": str((task.get("metadata") or {}).get("asset_manifest") or "shared_runtime/assets/provenance/charter_of_the_nine_cantons_v0.json"),
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "parcels": copy.deepcopy(parcels),
        "adjacency": copy.deepcopy(adjacency),
        "initial_assignment": copy.deepcopy(initial),
        "target_assignment": copy.deepcopy(target),
        "target_stats": copy.deepcopy(target_stats),
        "displaced_parcels": copy.deepcopy(displaced),
        "guilds": copy.deepcopy(list(GUILDS)),
        "canton_colors": list(CANTON_COLORS),
        "target_seat_split": copy.deepcopy(TARGET_SPLIT),
        "ideal_population": ideal_population,
        "population_tolerance": parameters["population_tolerance"],
        "parameters": copy.deepcopy(parameters),
    }
    if exchanges is not None:
        ground_truth["exchange_plan"] = copy.deepcopy(exchanges)
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
