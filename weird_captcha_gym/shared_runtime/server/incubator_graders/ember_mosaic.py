"""Independent replay grader for Ember Mosaic."""
from __future__ import annotations

import copy
import math
from typing import Any, Iterable


MECHANIC_ID = "ember_mosaic"
MATERIAL_TO_CELL = {"water": "w", "sand": "s", "stone": "#"}
MOVABLE = {".", "a", "w", "s"}
NEIGHBOURS = ((0, -1), (0, 1), (-1, 0), (1, 0))


def _fail(message: str, **extra: Any) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message, **extra}


def _index(x: int, y: int, width: int) -> int:
    return y * width + x


def _xy(index: int, width: int) -> tuple[int, int]:
    return index % width, index // width


def _adjacent(index: int, width: int, height: int) -> Iterable[int]:
    x, y = _xy(index, width)
    for dx, dy in NEIGHBOURS:
        nx, ny = x + dx, y + dy
        if 0 <= nx < width and 0 <= ny < height:
            yield _index(nx, ny, width)


def _valid_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _paint_one(state: dict[str, Any], x: int, y: int, material: str) -> None:
    width, height = state["width"], state["height"]
    if not (0 <= x < width and 0 <= y < height):
        return
    index = _index(x, y, width)
    current = state["grid"][index]
    target_cells = state["target_cells"]
    if material == "stone":
        if current in MOVABLE or current == "f" or (current == "p" and index not in target_cells):
            state["grid"][index] = "#"
            state["stone_age"][index] = 0
    elif material == "water":
        if current in {".", "a", "w", "s", "f"}:
            state["grid"][index] = "w"
            state["age"][index] = 0
    elif material == "sand":
        if current in {".", "a", "w"}:
            state["grid"][index] = "s"
            state["age"][index] = 0


def _raster_segment(first: tuple[int, int], second: tuple[int, int]) -> Iterable[tuple[int, int]]:
    """Yield the same integer Bresenham path used by the browser mechanic."""
    x1, y1 = first
    x2, y2 = second
    dx = abs(x2 - x1)
    sx = 1 if x1 < x2 else -1
    dy = -abs(y2 - y1)
    sy = 1 if y1 < y2 else -1
    error = dx + dy
    while True:
        yield x1, y1
        if x1 == x2 and y1 == y2:
            break
        twice = 2 * error
        if twice >= dy:
            error += dy
            x1 += sx
        if twice <= dx:
            error += dx
            y1 += sy


def _apply_brush(state: dict[str, Any], material: str, points: list[dict[str, Any]], radius: int) -> None:
    integer_points = [(int(point["x"]), int(point["y"])) for point in points]
    raster: list[tuple[int, int]] = []
    for left, right in zip(integer_points, integer_points[1:]):
        raster.extend(_raster_segment(left, right))
    if integer_points:
        raster.append(integer_points[-1])
    for x, y in raster:
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy <= radius * radius:
                    _paint_one(state, x + dx, y + dy, material)


def _step(state: dict[str, Any]) -> None:
    width, height = state["width"], state["height"]
    grid = state["grid"]
    age = state["age"]
    next_grid = list(grid)
    next_age = list(age)
    next_stone_age = list(state["stone_age"])
    next_oil_heat = list(state["oil_heat"])

    # Water touching a flame wins before the flame can ignite oil.  This is a
    # real state transition in the grid, not a visual overlay.
    for index, value in enumerate(grid):
        if value != "w":
            continue
        for neighbour in _adjacent(index, width, height):
            if grid[neighbour] == "f":
                next_grid[neighbour] = "a"
                next_age[neighbour] = 0

    # Oil warms while a flame remains adjacent.  It ignites only after the
    # declared heat window, giving a visible state-dependent opportunity to
    # cool the front with water instead of reducing the hazard to a one-frame
    # contact test.
    oil_heat_limit = int(state["parameters"]["oil_heat_ticks"])
    for index, value in enumerate(grid):
        if value != "o":
            continue
        hot = any(next_grid[neighbour] == "f" for neighbour in _adjacent(index, width, height))
        if hot:
            next_oil_heat[index] += 1
            if next_oil_heat[index] >= oil_heat_limit:
                state["oil_ignited"] = True
        else:
            next_oil_heat[index] = max(0, next_oil_heat[index] - 1)

    # Fire consumes connected plant material.  Oil is handled by the heat
    # window above rather than by an immediate contact shortcut.
    for index, value in enumerate(grid):
        if value != "f" or next_grid[index] == "a":
            continue
        next_age[index] = age[index] + 1
        for neighbour in _adjacent(index, width, height):
            if grid[neighbour] == "p":
                next_grid[neighbour] = "f"
                next_age[neighbour] = 0
                if neighbour in state["target_cells"]:
                    state["burned"].add(neighbour)
        if next_age[index] >= int(state["parameters"]["fire_lifetime"]):
            next_grid[index] = "a"
            next_age[index] = 0

    # Painted stone is a temporary baffle under direct flame pressure.  Its
    # erosion is why a successful run must inspect the evolving mosaic again.
    erosion_limit = int(state["parameters"]["stone_erosion_ticks"])
    for index, value in enumerate(grid):
        if value != "#":
            continue
        if any(grid[neighbour] == "f" for neighbour in _adjacent(index, width, height)):
            next_stone_age[index] += 1
            if next_stone_age[index] >= erosion_limit:
                next_grid[index] = "."
                next_stone_age[index] = 0

    # Powder movement uses a deterministic gravity-first scan.  Water and
    # sand are consequently visible moving particles, not static paint.
    bias = int(state["parameters"]["flow_bias"])
    for index in sorted((i for i, value in enumerate(grid) if value in {"w", "s"}), reverse=True):
        if grid[index] != next_grid[index] or next_grid[index] not in {"w", "s"}:
            continue
        x, y = _xy(index, width)
        candidates = [(x, y + 1), (x + bias, y), (x - bias, y)]
        for nx, ny in candidates:
            if not (0 < nx < width - 1 and 0 < ny < height - 1):
                continue
            destination = _index(nx, ny, width)
            if next_grid[destination] not in {".", "a"}:
                continue
            next_grid[destination] = grid[index]
            next_age[destination] = next_age[index]
            next_grid[index] = "."
            next_age[index] = 0
            break

    state["grid"] = next_grid
    state["age"] = next_age
    state["stone_age"] = next_stone_age
    state["oil_heat"] = next_oil_heat
    state["tick"] += 1


def _new_state(truth: dict[str, Any]) -> dict[str, Any]:
    world = copy.deepcopy(truth["world"])
    return {
        "width": int(world["width"]),
        "height": int(world["height"]),
        "grid": list(world["grid"]),
        "age": [0] * len(world["grid"]),
        "stone_age": [0] * len(world["grid"]),
        "target_cells": set(int(value) for value in truth["target_cells"]),
        "burned": set(),
        "oil_ignited": False,
        "oil_heat": [0] * len(world["grid"]),
        "tick": 0,
        "parameters": dict(world["parameters"]),
    }


def _public_world(public: dict[str, Any], truth_world: dict[str, Any]) -> dict[str, Any]:
    expected = copy.deepcopy(truth_world)
    expected.pop("control_condition", None)
    return {key: public.get(key) for key in expected}


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    if not all(isinstance(item, dict) for item in (payload, truth, public)):
        return _fail("malformed Ember Mosaic submission")
    for key in ("mechanic_id", "task_id", "challenge_id", "control_condition"):
        if payload.get(key) != truth.get(key) or public.get(key) != truth.get(key):
            return _fail("stale task, challenge, or control condition")
    if truth.get("mechanic_id") != MECHANIC_ID:
        return _fail("mechanic identity mismatch")
    world = truth.get("world")
    if not isinstance(world, dict):
        return _fail("public mosaic world is malformed")
    expected_public_world = copy.deepcopy(world)
    expected_public_world.pop("control_condition", None)
    if any(public.get(key) != value for key, value in expected_public_world.items()):
        return _fail("rendered particle world differs from hidden replay world")

    condition = truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "full")
    expected_source = {"full": "freehand_brush", "simplified": "stamp_controls"}.get(interaction)
    if expected_source is None or payload.get("interaction_mode") != interaction:
        return _fail("wrong Ember Mosaic interaction mode")
    events = payload.get("events")
    if not isinstance(events, list) or not events or len(events) > 30000:
        return _fail("missing or oversized particle transcript")

    state = _new_state(truth)
    radius = int(world["parameters"]["brush_radius"])
    previous_tick = 0
    brush_count = 0
    saw_submit = False
    max_tick = max(1, math.ceil(150_000 / int(world["parameters"]["tick_ms"])))
    try:
        for sequence, event in enumerate(events, 1):
            if not isinstance(event, dict) or event.get("seq") != sequence or saw_submit:
                return _fail("event sequence is invalid")
            event_type = event.get("type")
            event_tick = event.get("tick")
            if not _valid_int(event_tick) or event_tick < previous_tick or event_tick > max_tick:
                return _fail("event tick is invalid")
            while state["tick"] < event_tick:
                _step(state)
            previous_tick = event_tick
            if event_type == "brush":
                brush_count += 1
                if event.get("input_source") != expected_source:
                    return _fail("brush used the wrong interaction surface")
                material = event.get("material")
                if material not in MATERIAL_TO_CELL:
                    return _fail("unknown brush material")
                points = event.get("points")
                if not isinstance(points, list) or not points or len(points) > 3000:
                    return _fail("brush path is missing or oversized")
                if interaction == "simplified" and len(points) != 1:
                    return _fail("a coordinate stamp must contain exactly one point")
                checked: list[dict[str, int]] = []
                for point in points:
                    if not isinstance(point, dict) or not _valid_int(point.get("x")) or not _valid_int(point.get("y")):
                        return _fail("brush point is malformed")
                    if not 0 <= point["x"] < state["width"] or not 0 <= point["y"] < state["height"]:
                        return _fail("brush point leaves the visible grid")
                    checked.append({"x": point["x"], "y": point["y"]})
                _apply_brush(state, material, checked, radius)
            elif event_type == "submit":
                if event.get("input_source") != "certify_button" or event.get("completed") is not True:
                    return _fail("certification event is malformed")
                saw_submit = True
            else:
                return _fail(f"unknown event type {event_type!r}")
        if not saw_submit or brush_count == 0:
            return _fail("mosaic was never certified after a brush intervention")
        if payload.get("completed") is not True:
            return _fail("submission did not declare completion")
        passed = not state["oil_ignited"] and state["burned"] >= state["target_cells"]
        coverage = len(state["burned"] & state["target_cells"])
        feedback = (
            f"burned {coverage}/{len(state['target_cells'])} marked cells; "
            f"oil ignitions {1 if state['oil_ignited'] else 0}; "
            f"{brush_count} brush interventions"
        )
        return {
            "graded": True,
            "passed": passed,
            "score": 100 if passed else 0,
            "feedback": feedback,
            "burned_target_cells": coverage,
            "target_cells": len(state["target_cells"]),
            "oil_ignited": bool(state["oil_ignited"]),
            "brush_count": brush_count,
            "replay_tick": state["tick"],
        }
    except (KeyError, TypeError, ValueError, IndexError, OverflowError):
        return _fail("malformed particle replay")
