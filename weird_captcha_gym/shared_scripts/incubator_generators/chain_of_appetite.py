from __future__ import annotations

import copy
import hashlib
import math
import random
from functools import lru_cache
from typing import Any


MECHANIC_ID = "chain_of_appetite"
COLOR_NAMES = ("ember", "citron", "moss", "lagoon", "iris", "rose")
PALETTES = ("midnight-canteen", "rust-orbit", "deep-freezer", "acid-dawn")
SOLUTION_COUNT_CAP = 80
DRAG_TARGET_RADIUS_CELLS = 0.4
MIN_DRAG_TRAVEL_PX = 32
MIN_DRAG_SAMPLES = 3


def _game_monster(monster: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(monster["id"]),
        "row": int(monster["row"]),
        "column": int(monster["column"]),
        "body": str(monster["body"]),
        "mouth": str(monster["mouth"]),
        "shape": int(monster.get("shape", 0)),
        "horns": int(monster.get("horns", 0)),
        "eyes": int(monster.get("eyes", 2)),
        "mark": int(monster.get("mark", 0)),
        "tilt": int(monster.get("tilt", 0)),
    }


def _ordered(monsters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted((_game_monster(monster) for monster in monsters), key=lambda item: item["id"])


def _state_key(monsters: list[dict[str, Any]]) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        sorted(
            (
                str(monster["id"]),
                int(monster["row"]),
                int(monster["column"]),
                str(monster["body"]),
                str(monster["mouth"]),
            )
            for monster in monsters
        )
    )


def _from_key(key: tuple[tuple[Any, ...], ...]) -> list[dict[str, Any]]:
    return [
        {"id": item[0], "row": item[1], "column": item[2], "body": item[3], "mouth": item[4]}
        for item in key
    ]


def _clear_line(actor: dict[str, Any], victim: dict[str, Any], monsters: list[dict[str, Any]]) -> bool:
    row_a, column_a = int(actor["row"]), int(actor["column"])
    row_b, column_b = int(victim["row"]), int(victim["column"])
    if row_a != row_b and column_a != column_b:
        return False
    occupied = {
        (int(monster["row"]), int(monster["column"]))
        for monster in monsters
        if monster["id"] not in {actor["id"], victim["id"]}
    }
    if row_a == row_b:
        for column in range(min(column_a, column_b) + 1, max(column_a, column_b)):
            if (row_a, column) in occupied:
                return False
    else:
        for row in range(min(row_a, row_b) + 1, max(row_a, row_b)):
            if (row, column_a) in occupied:
                return False
    return True


def legal_moves(monsters: list[dict[str, Any]]) -> list[tuple[str, str]]:
    moves: list[tuple[str, str]] = []
    for actor in monsters:
        for victim in monsters:
            if actor["id"] == victim["id"]:
                continue
            if actor["mouth"] != victim["body"]:
                continue
            if _clear_line(actor, victim, monsters):
                moves.append((str(actor["id"]), str(victim["id"])))
    return sorted(moves)


def apply_move(monsters: list[dict[str, Any]], actor_id: str, victim_id: str) -> list[dict[str, Any]]:
    current = [_game_monster(monster) for monster in monsters]
    by_id = {monster["id"]: monster for monster in current}
    actor = by_id.get(str(actor_id))
    victim = by_id.get(str(victim_id))
    if actor is None or victim is None or (str(actor_id), str(victim_id)) not in legal_moves(current):
        raise ValueError("illegal appetite move")
    actor["row"] = victim["row"]
    actor["column"] = victim["column"]
    actor["mouth"] = victim["mouth"]
    return _ordered([monster for monster in current if monster["id"] != victim["id"]])


def _count_solutions(monsters: list[dict[str, Any]], limit: int) -> int:
    @lru_cache(maxsize=None)
    def walk(key: tuple[tuple[Any, ...], ...]) -> int:
        if len(key) == 1:
            return 1
        state = _from_key(key)
        total = 0
        for actor_id, victim_id in legal_moves(state):
            total += walk(_state_key(apply_move(state, actor_id, victim_id)))
            if total >= limit:
                return limit
        return total

    return walk(_state_key(monsters))


def _find_deadlock_path(
    monsters: list[dict[str, Any]], rng: random.Random, attempts: int = 220
) -> list[dict[str, str]] | None:
    # A full losing-path proof is needlessly expensive at the largest profile.
    # Sample deterministic complete plays instead, preferring moves that reduce
    # the next legal set. Any returned path is replayed and checked below.
    for _ in range(attempts):
        state = _ordered(monsters)
        path: list[dict[str, str]] = []
        while len(state) > 1:
            moves = legal_moves(state)
            if not moves:
                return path
            ranked: list[tuple[int, float, str, str, list[dict[str, Any]]]] = []
            for actor_id, victim_id in moves:
                next_state = apply_move(state, actor_id, victim_id)
                ranked.append((len(legal_moves(next_state)), rng.random(), actor_id, victim_id, next_state))
            ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
            pool = ranked[: min(3, len(ranked))]
            _, _, actor_id, victim_id, state = rng.choice(pool)
            path.append({"actor_id": actor_id, "victim_id": victim_id})
    return None


def _aligned_empty_origins(
    child: dict[str, Any], monsters: list[dict[str, Any]], grid_size: int
) -> list[tuple[int, int]]:
    occupied = {(int(monster["row"]), int(monster["column"])) for monster in monsters}
    origins: list[tuple[int, int]] = []
    row, column = int(child["row"]), int(child["column"])
    for test_column in range(grid_size):
        position = (row, test_column)
        if position in occupied:
            continue
        blocker = any((row, middle) in occupied for middle in range(min(column, test_column) + 1, max(column, test_column)))
        if not blocker:
            origins.append(position)
    for test_row in range(grid_size):
        position = (test_row, column)
        if position in occupied:
            continue
        blocker = any((middle, column) in occupied for middle in range(min(row, test_row) + 1, max(row, test_row)))
        if not blocker:
            origins.append(position)
    return origins


def _construct(
    rng: random.Random, *, grid_size: int, monster_count: int, colors: tuple[str, ...]
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    survivor = {
        "id": "m00",
        "row": rng.randrange(grid_size),
        "column": rng.randrange(grid_size),
        "body": rng.choice(colors),
        "mouth": rng.choice(colors),
    }
    monsters: list[dict[str, Any]] = [survivor]
    expansions: list[dict[str, str]] = []
    for index in range(1, monster_count):
        candidates: list[tuple[str, tuple[int, int]]] = []
        for child in monsters:
            candidates.extend((str(child["id"]), origin) for origin in _aligned_empty_origins(child, monsters, grid_size))
        if not candidates:
            raise ValueError("reverse construction ran out of clear orthogonal cells")
        actor_id, origin = rng.choice(candidates)
        actor = next(monster for monster in monsters if monster["id"] == actor_id)
        victim_id = f"m{index:02d}"
        inherited_mouth = str(actor["mouth"])
        victim_body = rng.choice(colors)
        victim = {
            "id": victim_id,
            "row": int(actor["row"]),
            "column": int(actor["column"]),
            "body": victim_body,
            "mouth": inherited_mouth,
        }
        actor["row"], actor["column"] = origin
        actor["mouth"] = victim_body
        monsters.append(victim)
        expansions.append({"actor_id": actor_id, "victim_id": victim_id})
    for monster in monsters:
        monster.update(
            {
                "shape": rng.randrange(6),
                "horns": rng.randrange(4),
                "eyes": rng.choice((1, 2, 2, 2, 3)),
                "mark": rng.randrange(5),
                "tilt": rng.randrange(-5, 6),
            }
        )
    return _ordered(monsters), list(reversed(expansions))


def _replay_solution(monsters: list[dict[str, Any]], moves: list[dict[str, str]]) -> list[dict[str, Any]]:
    state = _ordered(monsters)
    for move in moves:
        state = apply_move(state, move["actor_id"], move["victim_id"])
    if len(state) != 1:
        raise ValueError("reverse construction did not collapse to one survivor")
    return state


def _build_instance(
    rng: random.Random,
    *,
    grid_size: int,
    monster_count: int,
    color_count: int,
    solution_count_cap: int,
) -> dict[str, Any]:
    colors = COLOR_NAMES[:color_count]
    for attempt in range(500):
        try:
            monsters, solution = _construct(rng, grid_size=grid_size, monster_count=monster_count, colors=colors)
            final_state = _replay_solution(monsters, solution)
        except ValueError:
            continue
        opening_moves = legal_moves(monsters)
        if not opening_moves:
            continue
        solution_count = _count_solutions(monsters, solution_count_cap)
        if solution_count < 1:
            continue
        deadlock_path = _find_deadlock_path(monsters, rng)
        candidate = {
            "monsters": monsters,
            "solution_moves": solution,
            "solution_final": final_state,
            "solution_count": solution_count,
            "solution_count_capped": solution_count >= solution_count_cap,
            "failure_moves": deadlock_path,
            "opening_move_count": len(opening_moves),
            "attempt": attempt,
        }
        if deadlock_path is not None:
            return candidate
    raise ValueError("could not construct a solvable chain with a visible deadlock branch")


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = copy.deepcopy(task.get("_control_condition"))
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    grid_size = int(parameters.get("grid_size", 5))
    monster_count = int(parameters.get("monster_count", 12))
    color_count = int(parameters.get("color_count", 5))
    hint_mode = str(parameters.get("hint_mode", "none"))
    if not 3 <= grid_size <= 5:
        raise ValueError("grid size lies outside the supported range")
    if not 4 <= monster_count <= grid_size * grid_size - 1:
        raise ValueError("monster count lies outside the supported range")
    if not 3 <= color_count <= len(COLOR_NAMES):
        raise ValueError("color count lies outside the supported range")
    if hint_mode not in {"legal", "line", "none"}:
        raise ValueError("unknown appetite hint mode")

    difficulty = int((condition or {}).get("difficulty") or 4)
    digest = hashlib.sha256(f"{seed}|{MECHANIC_ID}|v1|d{difficulty}".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    instance = _build_instance(
        rng,
        grid_size=grid_size,
        monster_count=monster_count,
        color_count=color_count,
        solution_count_cap=SOLUTION_COUNT_CAP,
    )
    task_id = str(task.get("id") or "chain_of_appetite_seed_0001@0.1")
    challenge_id = hashlib.sha256(
        f"{seed}|{MECHANIC_ID}|v1|d{difficulty}|{task_id}".encode("utf-8")
    ).hexdigest()[:12]
    palette = PALETTES[rng.randrange(len(PALETTES))]
    variant_count = len(PALETTES) * math.comb(grid_size * grid_size, monster_count) * (color_count ** (monster_count * 2))
    prompt = (
        f"Reduce the tray from {monster_count} creatures to one. A mouth may eat a matching body "
        "along a clear row or column; the survivor inherits its meal's mouth colour."
    )
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": prompt,
        "submit_label": "SEAL SURVIVOR",
        "asset_manifest": "shared_runtime/assets/provenance/chain_of_appetite_v0.json",
        "generator": {
            "name": "chain_of_appetite_backward_v1",
            "search_attempt": instance["attempt"],
            "variant_count": variant_count,
            "variant_count_kind": "pre-search placement/colour upper bound",
        },
        "grid_size": grid_size,
        "monsters": copy.deepcopy(instance["monsters"]),
        "colors": list(COLOR_NAMES[:color_count]),
        "palette": palette,
        "parameters": {
            "grid_size": grid_size,
            "monster_count": monster_count,
            "color_count": color_count,
            "hint_mode": hint_mode,
        },
        "rule": {
            "match": "MOUTH COLOUR → BODY COLOUR",
            "travel": "CLEAR ROW OR COLUMN · NEVER DIAGONAL · NEVER JUMP A CREATURE",
            "inheritance": "THE EATER KEEPS ITS BODY AND INHERITS THE EATEN MOUTH",
            "terminal": "ONE SURVIVOR PASSES · A DEADLOCK FAILS",
        },
        "interaction_geometry": {
            "drag_target_shape": "circle",
            "drag_target_radius_cells": DRAG_TARGET_RADIUS_CELLS,
            "min_drag_travel_px": MIN_DRAG_TRAVEL_PX,
            "min_drag_samples": MIN_DRAG_SAMPLES,
        },
        "variant_count": variant_count,
        "variant_count_kind": "pre-search placement/colour upper bound",
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "initial_monsters": copy.deepcopy(instance["monsters"]),
        "parameters": copy.deepcopy(public_state["parameters"]),
        "solution_moves": copy.deepcopy(instance["solution_moves"]),
        "solution_final": copy.deepcopy(instance["solution_final"]),
        "solution_count": int(instance["solution_count"]),
        "solution_count_capped": bool(instance["solution_count_capped"]),
        "failure_moves": copy.deepcopy(instance["failure_moves"]),
        "opening_move_count": int(instance["opening_move_count"]),
        "palette": palette,
        "interaction_geometry": copy.deepcopy(public_state["interaction_geometry"]),
        "variant_count": variant_count,
        "variant_count_kind": "pre-search placement/colour upper bound",
    }
    if condition:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
