from __future__ import annotations

import hashlib
import json
import math
from collections import deque
from typing import Any


MECHANIC_ID = "leaning_tower_of_panels"
BASELINE_INTERACTION = "simplified"
CANVAS_WIDTH = 880.0
CANVAS_HEIGHT = 540.0
CONTROL_FIELDS = {
    "floor_count",
    "sector_count",
    "visible_arc_degrees",
    "scramble_distance_min",
    "scramble_distance_max",
    "move_allowance",
    "mural_band_count",
}


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _neighbors(blank: int, rows: int, sectors: int) -> tuple[int, ...]:
    row, sector = divmod(blank, sectors)
    result = [row * sectors + (sector - 1) % sectors, row * sectors + (sector + 1) % sectors]
    if row:
        result.append((row - 1) * sectors + sector)
    if row + 1 < rows:
        result.append((row + 1) * sectors + sector)
    return tuple(dict.fromkeys(result))


def _swap(state: tuple[str | None, ...], first: int, second: int) -> tuple[str | None, ...]:
    values = list(state)
    values[first], values[second] = values[second], values[first]
    return tuple(values)


def _visible(index: int, view_sector: int, sectors: int, visible_arc_degrees: int) -> bool:
    sector = index % sectors
    step_distance = min((sector - view_sector) % sectors, (view_sector - sector) % sectors)
    return step_distance * 360 / sectors <= visible_arc_degrees / 2 + 1e-9


def _wrap_angle(value: float) -> float:
    return (value + math.pi) % math.tau - math.pi


def _cell_geometry(
    index: int,
    view_sector: int,
    grid: tuple[str | None, ...],
    goal: tuple[str | None, ...],
    rows: int,
    sectors: int,
    visible_arc_degrees: int,
) -> dict[str, Any] | None:
    row, sector = divmod(index, sectors)
    angle = _wrap_angle((sector - view_sector) * math.tau / sectors)
    half_arc = visible_arc_degrees * math.pi / 360
    if abs(angle) > half_arc + 0.0001:
        return None
    half_panel = math.tau / sectors * 0.47
    depth = math.cos(angle)
    perspective_lift = (1 - depth) * 7
    aligned = sum(item is not None and item == goal[cell] for cell, item in enumerate(grid))
    lean = 28 * (1 - aligned / (rows * sectors - 1))
    lean_top = -lean * (1 - row / max(1, rows))
    lean_bottom = -lean * (1 - (row + 1) / max(1, rows))
    x1 = 440 + math.sin(angle - half_panel) * 252 + lean_top
    x2 = 440 + math.sin(angle + half_panel) * 252 + lean_top
    row_height = 414 / rows
    y1 = 68 + row * row_height + perspective_lift
    y2 = 68 + (row + 1) * row_height + perspective_lift
    bottom_shift = lean_bottom - lean_top
    return {
        "depth": depth,
        "polygon": (
            (x1, y1),
            (x2, y1),
            (x2 + bottom_shift, y2),
            (x1 + bottom_shift, y2),
        ),
    }


def _point_in_polygon(point: tuple[float, float], polygon: tuple[tuple[float, float], ...]) -> bool:
    inside = False
    previous = len(polygon) - 1
    for index, (x_i, y_i) in enumerate(polygon):
        x_j, y_j = polygon[previous]
        crosses = (y_i > point[1]) != (y_j > point[1]) and point[0] < (
            (x_j - x_i) * (point[1] - y_i) / ((y_j - y_i) or 0.00001) + x_i
        )
        if crosses:
            inside = not inside
        previous = index
    return inside


def _visible_cell(
    point: tuple[float, float],
    view_sector: int,
    grid: tuple[str | None, ...],
    goal: tuple[str | None, ...],
    rows: int,
    sectors: int,
    visible_arc_degrees: int,
) -> int | None:
    cells = []
    for index in range(rows * sectors):
        geometry = _cell_geometry(index, view_sector, grid, goal, rows, sectors, visible_arc_degrees)
        if geometry is not None:
            cells.append((index, geometry))
    cells.sort(key=lambda item: item[1]["depth"], reverse=True)
    for index, geometry in cells:
        if _point_in_polygon(point, geometry["polygon"]):
            return index
    return None


def _pointer_trace(event: dict[str, Any]) -> list[tuple[float, float]]:
    trace = event.get("pointer_trace")
    if not isinstance(trace, dict) or trace.get("coordinate_space") != "normalized_canvas_v1":
        raise ValueError("missing normalized pointer trace")
    raw_points = trace.get("points")
    if not isinstance(raw_points, list) or not 2 <= len(raw_points) <= 128:
        raise ValueError("pointer trace must contain 2 to 128 samples")
    points = []
    for raw in raw_points:
        if not isinstance(raw, dict) or set(raw) != {"x", "y"}:
            raise ValueError("pointer trace sample is malformed")
        x, y = raw["x"], raw["y"]
        if (
            isinstance(x, bool)
            or isinstance(y, bool)
            or not isinstance(x, (int, float))
            or not isinstance(y, (int, float))
            or not math.isfinite(float(x))
            or not math.isfinite(float(y))
            or not -0.25 <= float(x) <= 1.25
            or not -0.25 <= float(y) <= 1.25
        ):
            raise ValueError("pointer trace sample is outside the bounded canvas space")
        points.append((float(x) * CANVAS_WIDTH, float(y) * CANVAS_HEIGHT))
    return points


def _validate_tower_drag(
    event: dict[str, Any],
    grid: tuple[str | None, ...],
    goal: tuple[str | None, ...],
    rows: int,
    sectors: int,
    visible_arc_degrees: int,
    view_sector: int,
    delta: int,
) -> None:
    points = _pointer_trace(event)
    if _visible_cell(points[0], view_sector, grid, goal, rows, sectors, visible_arc_degrees) is not None:
        raise ValueError("tower drag did not start in open sky")
    travel = points[-1][0] - points[0][0]
    if abs(travel) + 1e-6 < 64:
        raise ValueError("tower drag did not cross the 64-pixel threshold")
    expected_delta = -1 if travel > 0 else 1
    if delta != expected_delta:
        raise ValueError("tower drag direction disagrees with its pointer trace")


def _validate_panel_drag(
    event: dict[str, Any],
    source_index: int,
    blank: int,
    grid: tuple[str | None, ...],
    goal: tuple[str | None, ...],
    rows: int,
    sectors: int,
    visible_arc_degrees: int,
    view_sector: int,
) -> None:
    points = _pointer_trace(event)
    if _visible_cell(points[0], view_sector, grid, goal, rows, sectors, visible_arc_degrees) != source_index:
        raise ValueError("panel drag did not start inside the claimed frontmost panel")
    visible_destination = _visible_cell(
        points[-1], view_sector, grid, goal, rows, sectors, visible_arc_degrees
    )
    blank_geometry = _cell_geometry(
        blank, view_sector, grid, goal, rows, sectors, visible_arc_degrees
    )
    if blank_geometry is not None:
        if visible_destination != blank:
            raise ValueError("panel drag did not end inside the visible opening")
        return
    source_sector = source_index % sectors
    blank_sector = blank % sectors
    if (blank_sector - source_sector) % sectors == 1:
        if points[-1][0] <= CANVAS_WIDTH:
            raise ValueError("hidden-wrap panel drag did not cross the correct right edge")
        return
    if (source_sector - blank_sector) % sectors == 1:
        if points[-1][0] >= 0:
            raise ValueError("hidden-wrap panel drag did not cross the correct left edge")
        return
    raise ValueError("panel drag targets an opening hidden outside the wrap edge")


def _shortest_distance(
    start: tuple[str | None, ...],
    goal: tuple[str | None, ...],
    rows: int,
    sectors: int,
) -> int:
    """Independently recompute the exact optimum with bidirectional BFS."""

    if start == goal:
        return 0
    left = {start: 0}
    right = {goal: 0}
    left_frontier = {start}
    right_frontier = {goal}
    while left_frontier and right_frontier:
        expand_left = len(left_frontier) <= len(right_frontier)
        frontier = left_frontier if expand_left else right_frontier
        own = left if expand_left else right
        other = right if expand_left else left
        next_frontier: set[tuple[str | None, ...]] = set()
        for state in frontier:
            depth = own[state]
            blank = state.index(None)
            for clicked in _neighbors(blank, rows, sectors):
                child = _swap(state, blank, clicked)
                if child in own:
                    continue
                own[child] = depth + 1
                if child in other:
                    return own[child] + other[child]
                next_frontier.add(child)
        if expand_left:
            left_frontier = next_frontier
        else:
            right_frontier = next_frontier
    raise ValueError("leaning-tower puzzle graph is disconnected")


def _fingerprint(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _condition(
    ground_truth: dict[str, Any], public_state: dict[str, Any]
) -> tuple[str, dict[str, Any] | None]:
    condition = ground_truth.get("control_condition")
    if condition is None:
        if public_state.get("control_condition") is not None:
            raise ValueError("unexpected public control condition")
        return BASELINE_INTERACTION, None
    if not isinstance(condition, dict) or public_state.get("control_condition") != condition:
        raise ValueError("public and hidden control conditions differ")
    interaction = str(condition.get("interaction") or "")
    parameters = condition.get("difficulty_parameters")
    if interaction not in {"simplified", "full"}:
        raise ValueError("unsupported interaction mode")
    if not isinstance(parameters, dict) or set(parameters) != CONTROL_FIELDS:
        raise ValueError("difficulty parameters are malformed")
    return interaction, parameters


def grade(
    payload: dict[str, Any],
    ground_truth: dict[str, Any],
    public_state: dict[str, Any],
) -> dict[str, Any]:
    if any(
        str(source.get("mechanic_id") or "") != MECHANIC_ID
        for source in (payload, ground_truth, public_state)
    ):
        return _fail("mechanic mismatch")
    challenge = str(ground_truth.get("challenge_id") or "")
    task_id = str(ground_truth.get("task_id") or "")
    if not challenge or any(
        str(source.get("challenge_id") or "") != challenge
        for source in (payload, public_state)
    ):
        return _fail("stale leaning-tower challenge")
    if not task_id or any(
        str(source.get("task_id") or "") != task_id for source in (payload, public_state)
    ):
        return _fail("task identity mismatch")

    try:
        interaction, parameters = _condition(ground_truth, public_state)
        rows = int(ground_truth["floor_count"])
        sectors = int(ground_truth["sector_count"])
        visible_arc_degrees = int(ground_truth["visible_arc_degrees"])
        start = tuple(ground_truth["start_grid"])
        goal = tuple(ground_truth["goal_grid"])
        optimal_claim = int(ground_truth["optimal_move_count"])
        allowed_moves = int(ground_truth["allowed_moves"])
        opening_target = int(ground_truth["opening_target_index"])
        if len(start) != rows * sectors or len(goal) != rows * sectors:
            raise ValueError("grid dimensions do not match the tower")
        if start.count(None) != 1 or goal.count(None) != 1 or goal[opening_target] is not None:
            raise ValueError("tower must contain one opening in its target bay")
        tile_ids = [str(item["id"]) for item in ground_truth["tiles"]]
        if len(tile_ids) != len(set(tile_ids)) or set(tile_ids) != {str(item) for item in goal if item is not None}:
            raise ValueError("panel identities do not match the target")
        for key in (
            "floor_count",
            "sector_count",
            "visible_arc_degrees",
            "tiles",
            "start_grid",
            "mural",
            "opening_target_index",
            "optimal_move_count",
            "allowed_moves",
            "world_fingerprint",
        ):
            if public_state.get(key) != ground_truth.get(key):
                raise ValueError(f"public {key} differs from replay truth")
        world = {
            "floor_count": rows,
            "sector_count": sectors,
            "visible_arc_degrees": int(ground_truth["visible_arc_degrees"]),
            "tiles": ground_truth["tiles"],
            "start_grid": list(start),
            "mural": ground_truth["mural"],
            "opening_target_index": opening_target,
            "optimal_move_count": optimal_claim,
            "allowed_moves": allowed_moves,
        }
        if _fingerprint(world) != str(ground_truth["world_fingerprint"]):
            raise ValueError("world fingerprint is invalid")
        optimal = _shortest_distance(start, goal, rows, sectors)
        if optimal != optimal_claim:
            raise ValueError("stored optimum differs from BFS replay")
        if allowed_moves < optimal:
            raise ValueError("move budget is below the optimum")
        if parameters is not None:
            if (
                rows != int(parameters["floor_count"])
                or sectors != int(parameters["sector_count"])
                or int(ground_truth["visible_arc_degrees"]) != int(parameters["visible_arc_degrees"])
                or not int(parameters["scramble_distance_min"]) <= optimal <= int(parameters["scramble_distance_max"])
                or allowed_moves != optimal + int(parameters["move_allowance"])
                or int(ground_truth["mural"]["band_count"]) != int(parameters["mural_band_count"])
            ):
                raise ValueError("generated tower does not implement its selected profile")
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"invalid leaning-tower contract: {exc}")

    events = payload.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 600:
        return _fail("tower transcript is missing or outside limits")

    grid = start
    view_sector = 0
    move_count = 0
    rotations = 0
    resets = 0
    expected_slide_source = "panel_click" if interaction == "simplified" else "panel_drag"
    expected_rotate_source = "rotation_buttons" if interaction == "simplified" else "tower_drag"

    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return _fail(f"event {sequence} sequence mismatch")
        kind = str(event.get("kind") or "")
        if kind == "rotate":
            if event.get("input_source") != expected_rotate_source:
                return _fail(f"event {sequence} uses the wrong rotation input surface")
            try:
                before = int(event.get("view_before"))
                delta = int(event.get("delta"))
                after = int(event.get("view_after"))
            except (TypeError, ValueError):
                return _fail(f"event {sequence} has invalid rotation values")
            if before != view_sector or delta not in {-1, 1} or after != (view_sector + delta) % sectors:
                return _fail(f"event {sequence} reports an impossible tower rotation")
            try:
                if interaction == "full":
                    _validate_tower_drag(
                        event,
                        grid,
                        goal,
                        rows,
                        sectors,
                        visible_arc_degrees,
                        view_sector,
                        delta,
                    )
                elif "pointer_trace" in event:
                    raise ValueError("simplified rotation unexpectedly includes pointer geometry")
            except (TypeError, ValueError) as exc:
                return _fail(f"event {sequence} has invalid rotation geometry: {exc}")
            view_sector = after
            rotations += 1
            continue
        if kind == "slide":
            if event.get("input_source") != expected_slide_source:
                return _fail(f"event {sequence} uses the wrong panel input surface")
            tile_id = str(event.get("tile_id") or "")
            try:
                source_index = int(event.get("from_index"))
                destination_index = int(event.get("to_index"))
            except (TypeError, ValueError):
                return _fail(f"event {sequence} has invalid panel indices")
            blank = grid.index(None)
            if (
                destination_index != blank
                or source_index not in _neighbors(blank, rows, sectors)
                or not 0 <= source_index < len(grid)
                or grid[source_index] != tile_id
            ):
                return _fail(f"event {sequence} is not a legal cylindrical slide")
            if not _visible(source_index, view_sector, sectors, visible_arc_degrees):
                return _fail(f"event {sequence} slides a panel outside the visible arc")
            try:
                if interaction == "full":
                    _validate_panel_drag(
                        event,
                        source_index,
                        blank,
                        grid,
                        goal,
                        rows,
                        sectors,
                        visible_arc_degrees,
                        view_sector,
                    )
                elif "pointer_trace" in event:
                    raise ValueError("simplified panel input unexpectedly includes pointer geometry")
            except (TypeError, ValueError) as exc:
                return _fail(f"event {sequence} has invalid panel geometry: {exc}")
            grid = _swap(grid, blank, source_index)
            move_count += 1
            continue
        if kind == "reset":
            if event.get("input_source") != "reset_button":
                return _fail(f"event {sequence} uses an unknown reset input")
            if event.get("grid_before") != list(grid):
                return _fail(f"event {sequence} reset does not describe the visible board")
            grid = start
            view_sector = 0
            move_count = 0
            resets += 1
            continue
        return _fail(f"event {sequence} has unknown kind {kind!r}")

    if payload.get("interaction_mode") != interaction:
        return _fail("submitted interaction mode differs from the task")
    if payload.get("final_grid") != list(grid):
        return _fail("submitted final grid differs from replay")
    if payload.get("move_count") != move_count:
        return _fail("submitted move count differs from replay")
    if payload.get("view_sector") != view_sector:
        return _fail("submitted tower view differs from replay")
    if payload.get("optimal_move_count") != optimal or payload.get("allowed_moves") != allowed_moves:
        return _fail("submitted shortest-path docket differs from replay")

    solved = grid == goal
    within_budget = move_count <= allowed_moves
    passed = solved and within_budget
    return {
        "graded": True,
        "passed": passed,
        "score": 100 if passed else 0,
        "feedback": (
            f"cylindrical replay: solved {str(solved).lower()}; moves {move_count}/{allowed_moves}; "
            f"BFS optimum {optimal}; rotations {rotations}; resets {resets}"
        ),
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {
        "optimal_solution": list(ground_truth.get("optimal_solution") or []),
        "goal_grid": list(ground_truth.get("goal_grid") or []),
    }
