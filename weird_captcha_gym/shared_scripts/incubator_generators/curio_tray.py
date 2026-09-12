from __future__ import annotations

import copy
import hashlib
import random
from functools import lru_cache
from typing import Any


MECHANIC_ID = "curio_tray"
TRAY_CAPACITY = 7
ITEM_WIDTH = 112
ITEM_HEIGHT = 78
TYPES = (
    {"kind": "amber_compass", "name": "AMBER COMPASS", "icon": "✦", "tone": "amber"},
    {"kind": "jade_beetle", "name": "JADE BEETLE", "icon": "◈", "tone": "jade"},
    {"kind": "cobalt_vase", "name": "COBALT VASE", "icon": "◒", "tone": "cobalt"},
    {"kind": "coral_feather", "name": "CORAL FEATHER", "icon": "❧", "tone": "coral"},
    {"kind": "violet_key", "name": "VIOLET KEY", "icon": "⚿", "tone": "violet"},
    {"kind": "ivory_moon", "name": "IVORY MOON", "icon": "☾", "tone": "ivory"},
    {"kind": "vermilion_die", "name": "VERMILION DIE", "icon": "✣", "tone": "vermilion"},
    {"kind": "teal_locket", "name": "TEAL LOCKET", "icon": "⬡", "tone": "teal"},
    {"kind": "rose_thimble", "name": "ROSE THIMBLE", "icon": "◉", "tone": "rose"},
)


def _seed_int(seed: str, salt: str) -> int:
    return int(hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).hexdigest()[:16], 16)


def _rect_overlap(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return (
        float(first["x"]) < float(second["x"]) + float(second["width"])
        and float(second["x"]) < float(first["x"]) + float(first["width"])
        and float(first["y"]) < float(second["y"]) + float(second["height"])
        and float(second["y"]) < float(first["y"]) + float(first["height"])
    )


def _accessible(item_ids: tuple[int, ...], items: list[dict[str, Any]], remaining: int) -> tuple[int, ...]:
    result: list[int] = []
    for index in item_ids:
        if not remaining & (1 << index):
            continue
        item = items[index]
        covered = any(
            remaining & (1 << other_index)
            and int(items[other_index]["z"]) > int(item["z"])
            and _rect_overlap(item, items[other_index])
            for other_index in item_ids
            if other_index != index
        )
        if not covered:
            result.append(index)
    return tuple(result)


def _solve_order(items: list[dict[str, Any]], type_count: int) -> list[int] | None:
    item_ids = tuple(range(len(items)))
    item_type = tuple(int(item["type_index"]) for item in items)
    initial_remaining = (1 << len(items)) - 1
    seen_states = 0

    @lru_cache(maxsize=250_000)
    def search(remaining: int, tray_counts: tuple[int, ...]) -> tuple[int, ...] | None:
        nonlocal seen_states
        seen_states += 1
        if seen_states > 240_000:
            return None
        if remaining == 0:
            return ()
        candidates = _accessible(item_ids, items, remaining)
        ordered = sorted(
            candidates,
            key=lambda index: (
                0 if tray_counts[item_type[index]] == 2 else 1,
                0 if tray_counts[item_type[index]] == 0 else 1,
                int(items[index]["z"]),
            ),
        )
        for index in ordered:
            counts = list(tray_counts)
            kind_index = item_type[index]
            counts[kind_index] += 1
            tray_size = sum(counts)
            if counts[kind_index] == 3:
                counts[kind_index] = 0
                tray_size -= 3
            next_remaining = remaining & ~(1 << index)
            if tray_size >= TRAY_CAPACITY and next_remaining:
                continue
            suffix = search(next_remaining, tuple(counts))
            if suffix is not None:
                return (index, *suffix)
        return None

    solved = search(initial_remaining, (0,) * type_count)
    return list(solved) if solved is not None else None


def _make_items(rng: random.Random, stack_count: int, type_count: int, jitter: int) -> list[dict[str, Any]]:
    tokens = [type_index for type_index in range(type_count) for _ in range(3)]
    rng.shuffle(tokens)
    stacks: list[list[int]] = [[] for _ in range(stack_count)]
    for index, type_index in enumerate(tokens):
        stacks[index % stack_count].append(type_index)
    rng.shuffle(stacks)
    items: list[dict[str, Any]] = []
    spacing = 122
    for stack_index, stack in enumerate(stacks):
        base_x = 48 + stack_index * spacing + rng.randint(-jitter, jitter)
        base_y = 18 + rng.randint(-jitter, jitter)
        stack_length = len(stack)
        for depth, type_index in enumerate(stack):
            item_number = len(items) + 1
            item_id = f"curio-{item_number:02d}-{hashlib.sha256(f'{rng.random()}|{item_number}'.encode()).hexdigest()[:7]}"
            item = {
                "id": item_id,
                "type_index": type_index,
                "type": TYPES[type_index]["kind"],
                "name": TYPES[type_index]["name"],
                "icon": TYPES[type_index]["icon"],
                "tone": TYPES[type_index]["tone"],
                "stack": stack_index,
                "depth": depth,
                "x": round(base_x + depth * 13 + rng.randint(-jitter, jitter), 2),
                "y": round(base_y + depth * 28 + rng.randint(-jitter, jitter), 2),
                "width": ITEM_WIDTH,
                "height": ITEM_HEIGHT,
                "z": stack_length - depth,
            }
            items.append(item)
    return items


def _build_instance(
    rng: random.Random,
    *,
    stack_count: int,
    type_count: int,
    jitter: int,
    minimum_visible_choices: int,
) -> tuple[list[dict[str, Any]], list[str], int]:
    best: tuple[int, list[dict[str, Any]], list[int]] | None = None
    for attempt in range(260):
        items = _make_items(rng, stack_count, type_count, jitter)
        solution = _solve_order(items, type_count)
        if solution is None:
            continue
        initial_choices = len(_accessible(tuple(range(len(items))), items, (1 << len(items)) - 1))
        if initial_choices < minimum_visible_choices:
            continue
        score = initial_choices
        if best is None or score > best[0]:
            best = (score, items, solution)
        if attempt >= 12:
            return items, [str(items[index]["id"]) for index in solution], attempt
    if best is None:
        raise ValueError("could not generate a solvable Curio Tray heap")
    return best[1], [str(best[1][index]["id"]) for index in best[2]], 260


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = task.get("_control_condition")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    stack_count = int(parameters.get("stack_count", 5))
    type_count = int(parameters.get("type_count", 7))
    jitter = int(parameters.get("jitter", 5))
    minimum_visible_choices = int(parameters.get("minimum_visible_choices", min(3, stack_count)))
    if not 3 <= stack_count <= 6 or not 3 <= type_count <= 9:
        raise ValueError("Curio Tray stack/type counts are outside supported limits")
    if not 0 <= jitter <= 10 or not 1 <= minimum_visible_choices <= stack_count:
        raise ValueError("Curio Tray layout parameters are invalid")

    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    items, solution_ids, search_attempt = _build_instance(
        rng,
        stack_count=stack_count,
        type_count=type_count,
        jitter=jitter,
        minimum_visible_choices=minimum_visible_choices,
    )
    difficulty_token = f"|d{int(condition['difficulty'])}" if condition else "|baseline"
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}{difficulty_token}".encode("utf-8")).hexdigest()[:12]
    task_id = str(task.get("id") or "curio_tray_seed_0001@0.1")
    interaction = str((condition or {}).get("interaction") or "full")
    action_hint = (
        "Click one item in the EXPOSED PICKS panel"
        if interaction == "simplified"
        else "Click the visible top item in the cabinet"
    )
    prompt = f"Empty the cabinet. {action_hint}. Three matching curios clear the tray; seven unmatched curios lose the attempt."
    public_items = [copy.deepcopy(item) for item in items]
    for item in public_items:
        item.pop("type_index", None)
        item.pop("stack", None)
        item.pop("depth", None)
    public_state: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": prompt,
        "submit_label": "APPRAISE EMPTY TRAY",
        "asset_manifest": "shared_runtime/assets/provenance/curio_tray_v0.json",
        "generator": {
            "name": "curio_tray_v1",
            "variant_count": 3**type_count,
            "search_attempt": search_attempt,
        },
        "cabinet": {
            "width": 820,
            "height": 270,
            "items": public_items,
            "stack_count": stack_count,
        },
        "tray_capacity": TRAY_CAPACITY,
        "triple_rule": "Three matching curios vanish together and free their slots.",
        "loss_rule": "Seven unmatched curios in the tray void the attempt.",
        "action_hint": action_hint,
    }
    ground_truth: dict[str, Any] = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "items": items,
        "solution_order": solution_ids,
        "stack_count": stack_count,
        "type_count": type_count,
        "tray_capacity": TRAY_CAPACITY,
        "variant_count": 3**type_count,
    }
    if condition:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
