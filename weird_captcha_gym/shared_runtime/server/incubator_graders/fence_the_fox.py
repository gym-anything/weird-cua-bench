from __future__ import annotations

from collections import deque
import math
from typing import Any


MECHANIC_ID = "fence_the_fox"
DIRECTIONS: tuple[tuple[int, int], ...] = (
    (1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1),
)
Coord = tuple[int, int]


def _fail(feedback: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": feedback}


def _coord(value: Any, radius: int) -> Coord:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("hex coordinate must contain q and r")
    q, r = value
    if isinstance(q, bool) or isinstance(r, bool) or not isinstance(q, int) or not isinstance(r, int):
        raise ValueError("hex coordinate values must be integers")
    if max(abs(q), abs(r), abs(-q - r)) > radius:
        raise ValueError("hex coordinate lies outside the field")
    return q, r


def _coords(value: Any, radius: int) -> list[Coord]:
    if not isinstance(value, list):
        raise ValueError("hex coordinate collection is malformed")
    result = [_coord(item, radius) for item in value]
    if len(result) != len(set(result)):
        raise ValueError("hex coordinate collection contains duplicates")
    return result


def _cells(radius: int) -> set[Coord]:
    return {
        (q, r)
        for q in range(-radius, radius + 1)
        for r in range(-radius, radius + 1)
        if max(abs(q), abs(r), abs(-q - r)) <= radius
    }


def _edge(cell: Coord, radius: int) -> bool:
    q, r = cell
    return max(abs(q), abs(r), abs(-q - r)) == radius


def _neighbors(cell: Coord, cells: set[Coord]) -> tuple[Coord, ...]:
    q, r = cell
    return tuple((q + dq, r + dr) for dq, dr in DIRECTIONS if (q + dq, r + dr) in cells)


def _distance_map(radius: int, blocked: frozenset[Coord]) -> dict[Coord, int]:
    cells = _cells(radius)
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


def _fox_choice(radius: int, fox: Coord, blocked: frozenset[Coord], wind_start: int) -> dict[str, Any]:
    cells = _cells(radius)
    distances = _distance_map(radius, blocked)
    if fox not in distances:
        return {"outcome": "trapped", "fox": fox, "distance": None}
    ordered = DIRECTIONS[wind_start:] + DIRECTIONS[:wind_start]
    wind = {direction: index for index, direction in enumerate(ordered)}
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
        return {"outcome": "trapped", "fox": fox, "distance": None}
    options.sort()
    distance, _wind, _onward, _degree, destination = options[0]
    return {
        "outcome": "escaped" if _edge(destination, radius) else "moved",
        "fox": destination,
        "distance": distance,
    }


def _binding(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> str | None:
    if payload.get("mechanic_id") != MECHANIC_ID:
        return "payload mechanic mismatch"
    if truth.get("mechanic_id") != MECHANIC_ID or public.get("mechanic_id") != MECHANIC_ID:
        return "fence contract mechanic mismatch"
    challenge_id = str(truth.get("challenge_id") or "")
    if not challenge_id or payload.get("challenge_id") != challenge_id:
        return "stale or mismatched challenge_id"
    if public.get("challenge_id") != challenge_id:
        return "public challenge differs from fence contract"
    task_id = str(truth.get("task_id") or "")
    if not task_id or payload.get("task_id") != task_id or public.get("task_id") != task_id:
        return "task identity mismatch"
    return None


def _contract(
    truth: dict[str, Any],
    public: dict[str, Any],
) -> tuple[int, Coord, frozenset[Coord], int, tuple[int, ...], tuple[tuple[int, int], ...]]:
    radius = truth.get("radius")
    if isinstance(radius, bool) or not isinstance(radius, int) or radius not in {3, 4}:
        raise ValueError("field radius is invalid")
    public_cells = set(_coords(public.get("cells"), radius))
    hidden_cells = set(_coords(truth.get("cells"), radius))
    if public_cells != _cells(radius) or hidden_cells != public_cells:
        raise ValueError("public and hidden hex fields disagree")
    fox = _coord(truth.get("fox_start"), radius)
    if _coord(public.get("fox_start"), radius) != fox:
        raise ValueError("public fox start differs from hidden contract")
    blocked = frozenset(_coords(truth.get("initial_fences"), radius))
    if frozenset(_coords(public.get("initial_fences"), radius)) != blocked:
        raise ValueError("public initial fences differ from hidden contract")
    if fox in blocked:
        raise ValueError("fox starts inside a fence")
    budget = truth.get("stake_budget")
    if isinstance(budget, bool) or not isinstance(budget, int) or not 1 <= budget <= 10:
        raise ValueError("stake budget is invalid")
    if public.get("stake_budget") != budget:
        raise ValueError("public stake budget differs from hidden contract")
    wind_sequence_value = truth.get("wind_sequence")
    if (
        not isinstance(wind_sequence_value, list)
        or len(wind_sequence_value) != budget
        or any(
            isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 6
            for value in wind_sequence_value
        )
    ):
        raise ValueError("wind sequence is invalid")
    if public.get("runtime_wind_sequence") != wind_sequence_value:
        raise ValueError("browser wind sequence differs from hidden contract")
    if public.get("wind_start") != wind_sequence_value[0] or truth.get("wind_start") != wind_sequence_value[0]:
        raise ValueError("initial wind tie-break differs from the wind sequence")
    driver_value = truth.get("driver_patterns")
    if (
        not isinstance(driver_value, list)
        or len(driver_value) != budget
        or any(
            not isinstance(pattern, list)
            or len(pattern) != 2
            or any(
                isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 12
                for value in pattern
            )
            for pattern in driver_value
        )
    ):
        raise ValueError("stake-driver pattern sequence is invalid")
    if public.get("runtime_driver_patterns") != driver_value:
        raise ValueError("browser stake-driver patterns differ from hidden contract")
    return (
        radius,
        fox,
        blocked,
        budget,
        tuple(wind_sequence_value),
        tuple((pattern[0], pattern[1]) for pattern in driver_value),
    )


def _driver_checkpoint(angle_index: int) -> tuple[float, float]:
    angle = angle_index * math.pi / 6 - math.pi / 2
    return math.cos(angle) * 0.68, math.sin(angle) * 0.68


def _gesture(event: dict[str, Any], placed: Coord, pattern: tuple[int, int]) -> str | None:
    gesture = event.get("gesture")
    if not isinstance(gesture, dict):
        return "direct stake placement is missing drag geometry"
    travel = gesture.get("travel_px")
    samples = gesture.get("sample_count")
    start = gesture.get("start")
    end = gesture.get("end")
    drop = gesture.get("drop_cell")
    if isinstance(travel, bool) or not isinstance(travel, (int, float)) or not math.isfinite(float(travel)) or float(travel) < 48:
        return "direct stake drag is too short"
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 5:
        return "direct stake drag has too few movement samples"
    for label, point in (("start", start), ("end", end)):
        if not isinstance(point, list) or len(point) != 2 or not all(
            isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
            for value in point
        ):
            return f"direct stake drag {label} point is malformed"
    if drop != [placed[0], placed[1]]:
        return "direct stake drag reports the wrong drop cell"
    raw_path = gesture.get("driver_path")
    if not isinstance(raw_path, list) or not 3 <= len(raw_path) <= 128:
        return "stake driver path is missing or malformed"
    path: list[tuple[float, float]] = []
    for point in raw_path:
        if (
            not isinstance(point, list)
            or len(point) != 2
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or abs(float(value)) > 2.5
                for value in point
            )
        ):
            return "stake driver path contains an invalid normalized point"
        path.append((float(point[0]), float(point[1])))
    cursor = 0
    for sequence, angle_index in enumerate(pattern, start=1):
        expected = _driver_checkpoint(angle_index)
        matched = next(
            (
                index
                for index in range(cursor, len(path))
                if math.hypot(path[index][0] - expected[0], path[index][1] - expected[1]) <= 0.3
            ),
            None,
        )
        if matched is None:
            return f"stake driver missed numbered mark {sequence}"
        cursor = matched + 1
    if not any(math.hypot(point[0], point[1]) <= 0.3 for point in path[cursor:]):
        return "stake driver did not return to the cell center before release"
    return None


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    binding_error = _binding(payload, ground_truth, public_state)
    if binding_error:
        return _fail(binding_error)
    truth_condition = ground_truth.get("control_condition")
    if truth_condition != public_state.get("control_condition"):
        return _fail("public control condition differs from fence contract")
    interaction = str((truth_condition or {}).get("interaction") or "simplified")
    expected_source = {"simplified": "cell_click", "full": "stake_driver"}.get(interaction)
    if expected_source is None:
        return _fail("interaction condition is invalid")
    try:
        radius, fox, blocked, budget, wind_sequence, driver_patterns = _contract(ground_truth, public_state)
    except (TypeError, ValueError) as exc:
        return _fail(f"invalid fence contract: {exc}")

    events = payload.get("events")
    if not isinstance(events, list) or len(events) > budget:
        return _fail("fence transcript is missing or exceeds the stake budget")
    initial_blocked = blocked
    placed_cells: list[Coord] = []
    terminal = "active"
    for index, event in enumerate(events, start=1):
        if terminal != "active":
            return _fail("fence transcript continues after a terminal outcome")
        if not isinstance(event, dict) or event.get("sequence") != index:
            return _fail(f"fence event {index} has an invalid sequence")
        if event.get("input_source") != expected_source:
            return _fail(f"fence event {index} uses the wrong interaction input")
        try:
            placed = _coord(event.get("placed"), radius)
            reported_from = _coord(event.get("fox_from"), radius)
        except ValueError as exc:
            return _fail(f"fence event {index} is malformed: {exc}")
        if placed == fox or placed in blocked:
            return _fail(f"fence event {index} places on an occupied cell")
        if reported_from != fox:
            return _fail(f"fence event {index} reports the wrong fox origin")
        wind_start = wind_sequence[index - 1]
        if event.get("wind_start") != wind_start:
            return _fail(f"fence event {index} reports the wrong visible wind order")
        if interaction == "full":
            gesture_error = _gesture(event, placed, driver_patterns[index - 1])
            if gesture_error:
                return _fail(f"fence event {index}: {gesture_error}")

        blocked = blocked | {placed}
        reply = _fox_choice(radius, fox, blocked, wind_start)
        expected_to = None if reply["outcome"] == "trapped" else [reply["fox"][0], reply["fox"][1]]
        expected = {
            "fox_to": expected_to,
            "outcome": reply["outcome"],
            "distance_after": reply["distance"],
        }
        for field, value in expected.items():
            if event.get(field) != value:
                return _fail(f"fence event {index} has inconsistent {field}: expected {value!r}")
        placed_cells.append(placed)
        if reply["outcome"] == "trapped":
            terminal = "trapped"
        elif reply["outcome"] == "escaped":
            fox = reply["fox"]
            terminal = "escaped"
        else:
            fox = reply["fox"]
            if index == budget:
                terminal = "exhausted"

    try:
        final_fox = _coord(payload.get("final_fox"), radius)
        submitted_fences = set(_coords(payload.get("player_fences"), radius))
    except ValueError as exc:
        return _fail(f"submitted final state is malformed: {exc}")
    if final_fox != fox:
        return _fail("submitted fox position does not match replay")
    if submitted_fences != set(placed_cells) or submitted_fences & set(initial_blocked):
        return _fail("submitted player fences do not match replay")
    if payload.get("turns") != len(events):
        return _fail("submitted turn count does not match replay")
    if payload.get("terminal_outcome") != terminal:
        return _fail(f"submitted outcome does not match replay: expected {terminal}")

    passed = payload.get("completed") is True and terminal == "trapped" and 1 <= len(events) <= budget
    return {
        "graded": True,
        "passed": passed,
        "feedback": (
            f"fence replay: {terminal}; {len(events)}/{budget} stakes placed; "
            f"fox at {fox[0]},{fox[1]}"
        ),
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    return {
        "placements": ground_truth.get("canonical_plan") or [],
        "trace": ground_truth.get("canonical_trace") or [],
        "instruction": "Place the listed stakes in order, waiting for each fox reply, then check the enclosure.",
        "answers": [],
    }
