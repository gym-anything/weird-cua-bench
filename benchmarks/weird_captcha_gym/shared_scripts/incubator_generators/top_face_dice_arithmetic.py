from __future__ import annotations

import hashlib
import random
from itertools import product
from typing import Any


MECHANIC_ID = "top_face_dice_arithmetic"
VARIANT_COUNT = 24**4 * 7**4 * 10_000_000
FACE_NAMES = ("top", "bottom", "north", "south", "east", "west")
CANONICAL = {"top": 1, "bottom": 6, "north": 2, "south": 5, "east": 3, "west": 4}
DELTAS = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
LABELS = ("ALPHA", "BRAVO", "CHARLIE", "DELTA")
COLORWAYS = (
    ("verdigris", "#45b9a8"),
    ("vermilion", "#e05a3f"),
    ("saffron", "#e0ad32"),
    ("cobalt", "#377da8"),
    ("plum", "#86577c"),
)
OPEN_CELLS = (
    (0, 1),
    (1, 0), (1, 1), (1, 2),
    (2, 0), (2, 1), (2, 2),
    (3, 0), (3, 1), (3, 2),
    (4, 0), (4, 1), (4, 2),
    (5, 1),
)
SCANNERS = ((1, 1), (4, 1))
START = (0, 1)
DOCK = (5, 1)
ROUTE_PLANS = (
    ("E", "E", "E", "E", "E"),
    ("E", "N", "E", "E", "E", "S", "E"),
    ("E", "S", "E", "E", "E", "N", "E"),
    ("E", "N", "E", "S", "E", "E", "E"),
    ("E", "S", "E", "N", "E", "E", "E"),
    ("E", "N", "E", "S", "W", "N", "E", "E", "E", "S", "E"),
    ("E", "S", "E", "N", "W", "S", "E", "E", "E", "N", "E"),
)


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _roll(orientation: dict[str, int], direction: str) -> dict[str, int]:
    old = dict(orientation)
    if direction == "N":
        return {"top": old["south"], "bottom": old["north"], "north": old["top"], "south": old["bottom"], "east": old["east"], "west": old["west"]}
    if direction == "S":
        return {"top": old["north"], "bottom": old["south"], "north": old["bottom"], "south": old["top"], "east": old["east"], "west": old["west"]}
    if direction == "E":
        return {"top": old["west"], "bottom": old["east"], "north": old["north"], "south": old["south"], "east": old["top"], "west": old["bottom"]}
    if direction == "W":
        return {"top": old["east"], "bottom": old["west"], "north": old["north"], "south": old["south"], "east": old["bottom"], "west": old["top"]}
    raise ValueError(f"unknown die roll {direction!r}")


def _point(x: int, y: int) -> dict[str, int]:
    return {"x": x, "y": y}


def _initial_orientation(rng: random.Random) -> dict[str, int]:
    orientation = dict(CANONICAL)
    for _ in range(rng.randint(9, 28)):
        orientation = _roll(orientation, rng.choice(tuple(DELTAS)))
    return orientation


def _trace(initial: dict[str, int], commands: tuple[str, ...]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    open_cells = set(OPEN_CELLS)
    position = START
    orientation = dict(initial)
    trace: list[dict[str, Any]] = []
    for index, command in enumerate(commands, start=1):
        dx, dy = DELTAS[command]
        candidate = (position[0] + dx, position[1] + dy)
        if candidate not in open_cells:
            raise ValueError(f"route plan left the foundry rail at step {index}")
        position = candidate
        orientation = _roll(orientation, command)
        trace.append({
            "step": index,
            "direction": command,
            "position": _point(*position),
            "orientation": dict(orientation),
        })
    if position != DOCK:
        raise ValueError("route plan does not finish on its scale dock")
    return trace, orientation


def _candidate_lot(
    initials: list[dict[str, int]],
    plans: tuple[tuple[str, ...], ...],
) -> list[tuple[tuple[str, ...], list[dict[str, Any]], dict[str, int]]]:
    return [
        (plan, *_trace(initial, plan))
        for initial, plan in zip(initials, plans)
    ]


def _matches_profile(
    candidate: list[tuple[tuple[str, ...], list[dict[str, Any]], dict[str, int]]],
    minimum_target_sum: int,
    maximum_target_sum: int,
    dice_count: int,
) -> bool:
    total = sum(item[2]["top"] for item in candidate)
    tops = {item[2]["top"] for item in candidate}
    return (
        minimum_target_sum <= total <= maximum_target_sum
        and len(tops) >= min(3, dice_count)
    )


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = task.get("_control_condition")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    dice_count = int(parameters.get("dice_count", len(LABELS)))
    orientation_visibility = str(parameters.get("orientation_visibility", "initial_and_scanners"))
    minimum_target_sum = int(parameters.get("minimum_target_sum", 10))
    maximum_target_sum = int(parameters.get("maximum_target_sum", 20))
    if not 1 <= dice_count <= len(LABELS):
        raise ValueError("foundry dice count is outside supported limits")
    if orientation_visibility not in {"always", "initial_and_scanners"}:
        raise ValueError("foundry orientation visibility is unsupported")
    if not dice_count <= minimum_target_sum <= maximum_target_sum <= 6 * dice_count:
        raise ValueError("foundry target-sum bounds are malformed")

    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    # L5 is the historical uncontrolled configuration, including its visible
    # foundry serial derived from the challenge identity. Lower profiles need
    # distinct identities, while the paired interaction modes deliberately do
    # not participate in this salt.
    challenge_salt = (
        MECHANIC_ID
        if condition is None or int(condition["difficulty"]) == 5
        else f"{MECHANIC_ID}|d{condition['difficulty']}"
    )
    challenge_id = hashlib.sha256(f"{seed}|{challenge_salt}".encode("utf-8")).hexdigest()[:12]
    task_id = str(task.get("id") or "top_face_dice_arithmetic_seed_0001@0.1")
    colors = list(COLORWAYS)
    rng.shuffle(colors)

    dice: list[dict[str, Any]] = []
    private_initials: list[dict[str, int]] = []
    for index, label in enumerate(LABELS[:dice_count]):
        initial = _initial_orientation(rng)
        private_initials.append(initial)
        token = hashlib.sha256(f"{seed}|die|{index}".encode("utf-8")).hexdigest()[:5]
        color_name, color_hex = colors[index]
        dice.append({
            "id": f"die-{token}",
            "label": label,
            "color_name": color_name,
            "color": color_hex,
            "rail_code": f"R-{rng.randint(21, 98)}{chr(65 + index)}",
            "start": _point(*START),
            "dock": _point(*DOCK),
            "open_cells": [_point(x, y) for x, y in OPEN_CELLS],
            "scanner_cells": [_point(x, y) for x, y in SCANNERS],
            "housing_cells": [
                _point(x, y)
                for x, y in OPEN_CELLS
                if (x, y) not in {START, DOCK, *SCANNERS}
            ],
            "initial_orientation": dict(initial),
        })

    chosen: list[tuple[tuple[str, ...], list[dict[str, Any]], dict[str, int]]] | None = None
    last_candidate: list[tuple[tuple[str, ...], list[dict[str, Any]], dict[str, int]]] | None = None
    for _ in range(80):
        candidate = _candidate_lot(
            private_initials,
            tuple(rng.choice(ROUTE_PLANS) for _ in range(dice_count)),
        )
        last_candidate = candidate
        if _matches_profile(candidate, minimum_target_sum, maximum_target_sum, dice_count):
            chosen = candidate
            break
    if chosen is None:
        if condition is None or int(condition["difficulty"]) == 5:
            # Preserve the uncontrolled generator byte-for-byte in behavior:
            # the historical baseline emitted the final sampled lot after all
            # retries. Controlled L5 deliberately keeps that same behavior.
            if last_candidate is None:
                raise RuntimeError("could not construct a solver-backed foundry lot")
            chosen = last_candidate
        else:
            # Controlled lots must satisfy the published profile. Keep the
            # historical random draws above, then deterministically enumerate
            # the finite route-product space without consuming more RNG.
            for plans in product(ROUTE_PLANS, repeat=dice_count):
                candidate = _candidate_lot(private_initials, plans)
                if _matches_profile(candidate, minimum_target_sum, maximum_target_sum, dice_count):
                    chosen = candidate
                    break
            if chosen is None:
                raise RuntimeError(
                    "could not construct a foundry lot satisfying the controlled profile"
                )

    target_sum = sum(item[2]["top"] for item in chosen)
    solution_plans = []
    for die, (plan, trace, final_orientation) in zip(dice, chosen):
        solution_plans.append({
            "die_id": die["id"],
            "world_directions": list(plan),
            "trace": trace,
            "final_orientation": final_orientation,
            "final_top": int(final_orientation["top"]),
        })

    palette = rng.choice(("brassworks", "black-iron", "salt-mill"))
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "prompt": task.get("natural_language")
        or "Route all three foundry dice to their docks, rotate the table, and settle the displayed top-face sum.",
        "generator": {"name": "four_die_foundry_scale_v2", "variant_count": VARIANT_COUNT},
        "foundry_serial": f"F-{challenge_id[:4].upper()}-{rng.randint(100, 999)}",
        "palette": palette,
        "board": {"columns": 6, "rows": 3},
        "dice": dice,
        "target_sum": target_sum,
        "starting_view": 0,
        "initial_selected_die_id": dice[0]["id"],
        "submit_label": "WEIGH LOT",
    }
    # The uncontrolled public contract did not export this field. L5 keeps
    # that exact contract and the browser/grader use the historical default;
    # lower controlled profiles need an explicit non-baseline visibility mode.
    if condition is not None and int(condition["difficulty"]) != 5:
        public_state["orientation_visibility"] = orientation_visibility
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "board": public_state["board"],
        "dice": dice,
        "target_sum": target_sum,
        "starting_view": 0,
        "initial_selected_die_id": dice[0]["id"],
        "solution_plans": solution_plans,
        "settle_profile": [26, -16, 10, -6, 3, -1, 0],
        "variant_count": VARIANT_COUNT,
    }
    if condition:
        public_state["control_condition"] = condition
        ground_truth["control_condition"] = condition
    assert len(dice) == dice_count
    assert all(len(plan["world_directions"]) >= 5 for plan in solution_plans)
    assert sum(plan["final_top"] for plan in solution_plans) == target_sum
    return public_state, ground_truth
