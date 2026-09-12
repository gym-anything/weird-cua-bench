from __future__ import annotations

import copy
import hashlib
import random
from collections import deque
from typing import Any


MECHANIC_ID = "elemental_wayfarer"
ELEMENTS = ("ember", "tide", "zephyr", "basalt")
ELEMENT_LABELS = {
    "clay": "CLAY",
    "ember": "EMBER",
    "tide": "TIDE",
    "zephyr": "ZEPHYR",
    "basalt": "BASALT",
}
ELEMENT_GLYPHS = {"ember": "✦", "tide": "≈", "zephyr": "⌁", "basalt": "◆"}
ELEMENT_COLORS = {"ember": "ember", "tide": "tide", "zephyr": "zephyr", "basalt": "basalt"}
SEQUENCES = {
    1: ["ember"],
    2: ["ember", "tide"],
    3: ["ember", "tide", "zephyr"],
    4: ["ember", "tide", "zephyr", "basalt"],
    5: ["ember", "tide", "zephyr", "basalt", "tide"],
}
PROFILES = {
    1: {"width": 11, "height": 7, "gate_count": 1, "decoy_tokens": 0, "theme_count": 3},
    2: {"width": 13, "height": 7, "gate_count": 2, "decoy_tokens": 1, "theme_count": 4},
    3: {"width": 13, "height": 9, "gate_count": 3, "decoy_tokens": 1, "theme_count": 5},
    4: {"width": 15, "height": 11, "gate_count": 4, "decoy_tokens": 2, "theme_count": 6},
    5: {"width": 17, "height": 11, "gate_count": 5, "decoy_tokens": 3, "theme_count": 7},
}


def _seed_int(seed: str, salt: str) -> int:
    return int(hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).hexdigest()[:16], 16)


def _neighbors(cell: tuple[int, int], width: int, height: int) -> list[tuple[int, int]]:
    x, y = cell
    candidates = [(x + 2, y), (x - 2, y), (x, y + 2), (x, y - 2)]
    return [(nx, ny) for nx, ny in candidates if 1 <= nx < width - 1 and 1 <= ny < height - 1]


def _make_maze(rng: random.Random, width: int, height: int) -> tuple[list[list[str]], tuple[int, int], tuple[int, int]]:
    grid = [["wall" for _ in range(width)] for _ in range(height)]
    start = (1, height - 2)
    exit_cell = (width - 2, 1)
    stack = [start]
    visited = {start}
    grid[start[1]][start[0]] = "floor"
    while stack:
        current = stack[-1]
        choices = [cell for cell in _neighbors(current, width, height) if cell not in visited]
        if not choices:
            stack.pop()
            continue
        nxt = rng.choice(choices)
        visited.add(nxt)
        x, y = current
        nx, ny = nxt
        grid[(y + ny) // 2][(x + nx) // 2] = "floor"
        grid[ny][nx] = "floor"
        stack.append(nxt)
    grid[start[1]][start[0]] = "floor"
    grid[exit_cell[1]][exit_cell[0]] = "floor"
    return grid, start, exit_cell


def _path(grid: list[list[str]], start: tuple[int, int], goal: tuple[int, int]) -> list[tuple[int, int]]:
    queue = deque([start])
    previous: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    while queue:
        x, y = queue.popleft()
        if (x, y) == goal:
            break
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= ny < len(grid) and 0 <= nx < len(grid[0]) and grid[ny][nx] == "floor" and (nx, ny) not in previous:
                previous[(nx, ny)] = (x, y)
                queue.append((nx, ny))
    if goal not in previous:
        raise ValueError("generated chamber has no route to the exit")
    result: list[tuple[int, int]] = []
    cursor: tuple[int, int] | None = goal
    while cursor is not None:
        result.append(cursor)
        cursor = previous[cursor]
    return list(reversed(result))


def _direction(first: tuple[int, int], second: tuple[int, int]) -> str:
    dx, dy = second[0] - first[0], second[1] - first[1]
    return {(1, 0): "RIGHT", (-1, 0): "LEFT", (0, 1): "DOWN", (0, -1): "UP"}[dx, dy]


def _tile(x: int, y: int, kind: str = "floor", element: str | None = None) -> dict[str, Any]:
    tile: dict[str, Any] = {"x": x, "y": y, "kind": kind}
    if element is not None:
        tile["element"] = element
        tile["glyph"] = ELEMENT_GLYPHS[element]
    return tile


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = copy.deepcopy((task.get("metadata") or {}).get("control_condition") or None)
    level = int((condition or {}).get("difficulty") or 4)
    profile = dict(PROFILES[level])
    profile.update(dict((condition or {}).get("difficulty_parameters") or {}))
    width = int(profile["width"])
    height = int(profile["height"])
    gate_count = int(profile["gate_count"])
    decoy_count = int(profile["decoy_tokens"])
    sequence = list(SEQUENCES[level])
    if gate_count != len(sequence) or width % 2 != 1 or height % 2 != 1:
        raise ValueError("Elemental Wayfarer profile is malformed")

    # Interaction is deliberately absent from the random stream: the two input
    # surfaces receive the same chamber, tokens, gates, and route.
    rng = random.Random(_seed_int(seed, f"{MECHANIC_ID}|d{level}"))
    grid, start, exit_cell = _make_maze(rng, width, height)
    route = _path(grid, start, exit_cell)
    if len(route) < gate_count * 2 + 5:
        raise ValueError("generated chamber route is too short for its elemental stages")

    specials: dict[tuple[int, int], dict[str, Any]] = {}
    gate_positions: list[tuple[int, int]] = []
    token_positions: list[tuple[int, int]] = []
    spacing = max(4, len(route) // (gate_count + 1))
    for index, element in enumerate(sequence):
        gate_index = min(len(route) - 3, (index + 1) * spacing)
        while gate_index in {route.index(pos) for pos in gate_positions} or gate_index - 1 in {route.index(pos) for pos in token_positions}:
            gate_index += 1
        token_index = gate_index - 1
        token_position = route[token_index]
        gate_position = route[gate_index]
        token_id = f"token-{index + 1}-{hashlib.sha256(f'{seed}|token|{index}'.encode()).hexdigest()[:7]}"
        specials[token_position] = {"kind": "token", "element": element, "id": token_id, "order": index + 1}
        specials[gate_position] = {"kind": "gate", "element": element, "id": f"gate-{index + 1}"}
        token_positions.append(token_position)
        gate_positions.append(gate_position)

    route_set = set(route)
    open_cells = [
        (x, y)
        for y in range(1, height - 1)
        for x in range(1, width - 1)
        if grid[y][x] == "floor" and (x, y) not in route_set and (x, y) not in specials
    ]
    rng.shuffle(open_cells)
    decoy_specs: list[dict[str, Any]] = []
    for index, position in enumerate(open_cells[:decoy_count]):
        element = rng.choice(ELEMENTS)
        token_id = f"decoy-{index + 1}-{hashlib.sha256(f'{seed}|decoy|{index}'.encode()).hexdigest()[:7]}"
        specials[position] = {"kind": "decoy", "element": element, "id": token_id, "order": None}
        decoy_specs.append({"id": token_id, "element": element, "x": position[0], "y": position[1]})

    tiles: list[dict[str, Any]] = []
    for y in range(height):
        for x in range(width):
            if grid[y][x] == "wall":
                tile = _tile(x, y, "wall")
            else:
                tile = _tile(x, y)
                if (x, y) in specials:
                    tile.update(specials[(x, y)])
            tiles.append(tile)

    solution_actions = [_direction(first, second) for first, second in zip(route, route[1:])]
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|d{level}".encode("utf-8")).hexdigest()[:12]
    task_id = str(task.get("id") or f"{MECHANIC_ID}_seed_0001@0.1")
    interaction = str((condition or {}).get("interaction") or "full")
    prompt = (
        "Guide the traveler to the marked exit. Step onto elemental tokens to change form; "
        "only the matching form can cross each luminous seal."
    )
    public_state: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": prompt,
        "submit_label": "CERTIFY ARRIVAL",
        "asset_manifest": "shared_runtime/assets/provenance/elemental_wayfarer_v0.json",
        "generator": {
            "name": "elemental_wayfarer_maze_v1",
            "variant_count": 5 * 2 * 10_000_000,
            "level": level,
        },
        "chamber": {
            "width": width,
            "height": height,
            "tiles": tiles,
            "start": {"x": start[0], "y": start[1]},
            "exit": {"x": exit_cell[0], "y": exit_cell[1], "requires": sequence[-1]},
            "theme": rng.randrange(int(profile["theme_count"])),
        },
        "initial_form": "clay",
        "elements": {
            element: {"label": ELEMENT_LABELS[element], "glyph": ELEMENT_GLYPHS[element], "color": ELEMENT_COLORS[element]}
            for element in ELEMENTS
        },
        "movement_rules": "Arrow or direction input moves one chamber tile. A token changes the visible form; a seal admits only its matching form.",
        "action_hint": "Use the visible direction controls" if interaction == "simplified" else "Use arrow keys or WASD",
    }
    ground_truth: dict[str, Any] = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "level": level,
        "control_condition": condition,
        "initial_form": "clay",
        "tiles": tiles,
        "start": {"x": start[0], "y": start[1]},
        "exit": {"x": exit_cell[0], "y": exit_cell[1], "requires": sequence[-1]},
        "solution_actions": solution_actions,
        "token_order": [str(specials[pos]["id"]) for pos in token_positions],
        "gate_order": [str(specials[pos]["id"]) for pos in gate_positions],
        "decoys": decoy_specs,
        "variant_count": 5 * 2 * 10_000_000,
    }
    if condition:
        public_state["control_condition"] = copy.deepcopy(condition)
    else:
        ground_truth["control_condition"] = None
    return public_state, ground_truth
