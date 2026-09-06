from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "two_season_strand"
PALETTE = (
    {"id": 0, "name": "SUN", "short": "S", "color": "#f2bd4b"},
    {"id": 1, "name": "MOSS", "short": "M", "color": "#78ad78"},
    {"id": 2, "name": "BERRY", "short": "B", "color": "#b45a76"},
    {"id": 3, "name": "NIGHT", "short": "N", "color": "#52628f"},
)
DEFAULT_PARAMETERS = {
    "strand_length": 64,
    "mutation_count": 6,
    "edit_budget": 18,
    "index_label_stride": 4,
    "minimum_winter_pairs": 12,
    "minimum_coupled_nodes": 18,
    "minimum_conflicting_repairs": 4,
    "blueprint_guidance": "standard",
}


def _pairs(sequence: list[int], order: list[int]) -> list[list[int]]:
    """Return the deterministic nested pairing produced in one seasonal order."""
    stacks: dict[int, list[int]] = {0: [], 1: []}
    pairs: list[list[int]] = []
    for index in order:
        color = sequence[index]
        if color in (0, 1):
            stacks[color].append(index)
            continue
        opener = 1 if color == 2 else 0
        if stacks[opener]:
            partner = stacks[opener].pop()
            pairs.append(sorted((partner, index)))
    return sorted(pairs)


def _winter_order(length: int, stride: int, offset: int) -> list[int]:
    return [(offset + rank * stride) % length for rank in range(length)]


def _pair_map(pairs: list[list[int]]) -> dict[int, int]:
    result: dict[int, int] = {}
    for left, right in pairs:
        result[left] = right
        result[right] = left
    return result


def _canonical_sequence(rng: random.Random, length: int) -> list[int]:
    # Eight-bead balanced phrases guarantee a legible Spring fold while the
    # seeded Winter permutation reuses every bead in a different global order.
    sequence: list[int] = []
    for _ in range(length // 8):
        opening = [rng.randrange(2) for _ in range(4)]
        closing = [3 if color == 0 else 2 for color in reversed(opening)]
        sequence.extend((*opening, *closing))
    return sequence


def _candidate_strides(length: int) -> list[int]:
    return [
        value
        for value in range(3, min(length, 24), 2)
        if math.gcd(value, length) == 1 and value not in {length - 1}
    ]


def _symmetric_difference_size(left: list[list[int]], right: list[list[int]]) -> int:
    return len({tuple(pair) for pair in left} ^ {tuple(pair) for pair in right})


def _matched_pair_count(current: list[list[int]], target: list[list[int]]) -> int:
    return len({tuple(pair) for pair in current} & {tuple(pair) for pair in target})


def _conflicting_repairs(
    initial: list[int],
    canonical: list[int],
    selected: list[int],
    spring_order: list[int],
    winter_order: list[int],
    spring_pairs: list[list[int]],
    winter_pairs: list[list[int]],
) -> list[dict[str, int]]:
    baseline = {
        "spring": _matched_pair_count(_pairs(initial, spring_order), spring_pairs),
        "winter": _matched_pair_count(_pairs(initial, winter_order), winter_pairs),
    }
    conflicts: list[dict[str, int]] = []
    for index in selected:
        probe = initial[:]
        probe[index] = canonical[index]
        deltas = {
            "spring": _matched_pair_count(_pairs(probe, spring_order), spring_pairs) - baseline["spring"],
            "winter": _matched_pair_count(_pairs(probe, winter_order), winter_pairs) - baseline["winter"],
        }
        if (deltas["spring"] > 0 > deltas["winter"]) or (deltas["winter"] > 0 > deltas["spring"]):
            conflicts.append({
                "index": index,
                "spring_matched_delta": deltas["spring"],
                "winter_matched_delta": deltas["winter"],
            })
    return conflicts


def _build_instance(rng: random.Random, parameters: dict[str, Any]) -> dict[str, Any]:
    length = int(parameters["strand_length"])
    mutation_count = int(parameters["mutation_count"])
    minimum_winter_pairs = int(parameters["minimum_winter_pairs"])
    minimum_coupled_nodes = int(parameters["minimum_coupled_nodes"])
    minimum_conflicting_repairs = int(parameters["minimum_conflicting_repairs"])
    spring_order = list(range(length))
    strides = _candidate_strides(length)
    if not strides:
        raise ValueError("strand length has no supported Winter stride")

    for attempt in range(240):
        canonical = _canonical_sequence(rng, length)
        stride = rng.choice(strides)
        offset = rng.randrange(length)
        winter_order = _winter_order(length, stride, offset)
        spring_pairs = _pairs(canonical, spring_order)
        winter_pairs = _pairs(canonical, winter_order)
        if len(winter_pairs) < minimum_winter_pairs:
            continue
        spring_map = _pair_map(spring_pairs)
        winter_map = _pair_map(winter_pairs)
        coupled = [
            index
            for index in range(length)
            if index in spring_map
            and index in winter_map
            and spring_map[index] != winter_map[index]
        ]
        if len(coupled) < max(minimum_coupled_nodes, mutation_count):
            continue

        # Reserve one adjacent, same-colour pair so the Full-mode solution
        # demonstrates a physical paint stroke rather than only taps.
        row_break = length // 2 - 1
        adjacent_runs = [
            (index, index + 1)
            for index in coupled
            if index + 1 in coupled
            and index != row_break
            and canonical[index] == canonical[index + 1]
        ]
        if not adjacent_runs:
            continue
        impacts: list[tuple[int, int]] = []
        for index in coupled:
            probe = canonical[:]
            probe[index] = (canonical[index] - 1) % 4
            impact = _symmetric_difference_size(spring_pairs, _pairs(probe, spring_order))
            impact += _symmetric_difference_size(winter_pairs, _pairs(probe, winter_order))
            impacts.append((impact, index))
        rng.shuffle(impacts)
        impacts.sort(reverse=True)
        impact_order = [index for _impact, index in impacts]
        for selection_attempt in range(240):
            run = rng.choice(adjacent_runs)
            selected = list(run)
            pool = impact_order[:]
            if selection_attempt:
                rng.shuffle(pool)
            if len(selected) < mutation_count:
                for index in pool:
                    if index in selected:
                        continue
                    # Spread remaining defects through the strand so the views,
                    # not a single local cluster, must guide the repair.
                    if any(abs(index - other) <= 1 for other in selected):
                        continue
                    selected.append(index)
                    if len(selected) == mutation_count:
                        break
            if len(selected) < mutation_count:
                continue

            initial = canonical[:]
            for index in selected:
                initial[index] = (canonical[index] - 1) % 4
            current_spring = _pairs(initial, spring_order)
            current_winter = _pairs(initial, winter_order)
            spring_delta = _symmetric_difference_size(spring_pairs, current_spring)
            winter_delta = _symmetric_difference_size(winter_pairs, current_winter)
            if spring_delta < mutation_count or winter_delta < max(2, mutation_count // 2):
                continue
            conflicting = _conflicting_repairs(
                initial,
                canonical,
                selected,
                spring_order,
                winter_order,
                spring_pairs,
                winter_pairs,
            )
            if len(conflicting) < minimum_conflicting_repairs:
                continue
            return {
                "canonical": canonical,
                "initial": initial,
                "spring_order": spring_order,
                "winter_order": winter_order,
                "winter_stride": stride,
                "winter_offset": offset,
                "spring_pairs": spring_pairs,
                "winter_pairs": winter_pairs,
                "mutated_indices": sorted(selected),
                "paint_run": list(run),
                "coupled_node_count": len(coupled),
                "conflicting_repairs": sorted(conflicting, key=lambda item: item["index"]),
                "initial_pair_delta": {"spring": spring_delta, "winter": winter_delta},
                "attempt": attempt,
                "selection_attempt": selection_attempt,
            }
    raise ValueError("could not construct a reachable coupled two-season strand")


def _validate_parameters(parameters: dict[str, Any]) -> None:
    length = int(parameters["strand_length"])
    mutation_count = int(parameters["mutation_count"])
    edit_budget = int(parameters["edit_budget"])
    if length % 8 or not 40 <= length <= 88:
        raise ValueError("strand_length must be a multiple of eight from 40 through 88")
    if not 2 <= mutation_count <= 12:
        raise ValueError("mutation_count must be from two through twelve")
    if not mutation_count <= edit_budget <= 40:
        raise ValueError("edit_budget must cover the generated defects and stay finite")
    if not 1 <= int(parameters["index_label_stride"]) <= 12:
        raise ValueError("index_label_stride is outside the supported range")
    if parameters["blueprint_guidance"] not in {"strong", "standard", "sparse"}:
        raise ValueError("blueprint_guidance is invalid")
    conflicting = int(parameters["minimum_conflicting_repairs"])
    if not 0 <= conflicting <= mutation_count:
        raise ValueError("minimum_conflicting_repairs must fit inside the generated defects")


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = task.get("_control_condition")
    parameters = copy.deepcopy(DEFAULT_PARAMETERS)
    parameters.update(dict((condition or {}).get("difficulty_parameters") or {}))
    _validate_parameters(parameters)
    difficulty = int((condition or {}).get("difficulty") or 4)
    digest = hashlib.sha256(f"{seed}|{MECHANIC_ID}|d{difficulty}|v2".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    instance = _build_instance(rng, parameters)
    task_id = str(task.get("id") or "two_season_strand_seed_0001@0.1")
    challenge_id = hashlib.sha256(
        f"{seed}|{MECHANIC_ID}|d{difficulty}|v2|{instance['winter_stride']}|{instance['winter_offset']}".encode("utf-8")
    ).hexdigest()[:18]
    target_pairs = {
        "spring": instance["spring_pairs"],
        "winter": instance["winter_pairs"],
    }
    orders = {
        "spring": instance["spring_order"],
        "winter": instance["winter_order"],
    }
    pair_total = sum(len(value) for value in target_pairs.values())
    variant_lower_bound = len(_candidate_strides(int(parameters["strand_length"]))) * (2 ** (int(parameters["strand_length"]) // 2))
    public_state: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": (
            f"Repair the {int(parameters['strand_length'])}-bead strand so its Spring and Winter folds both match their ghost blueprints. "
            f"Use the season tabs to inspect both live views; some locally helpful repairs temporarily regress the other season. "
            f"Every changed bead spends one of {int(parameters['edit_budget'])} edits."
        ),
        "submit_label": "SEAL BOTH SEASONS",
        "asset_manifest": "shared_runtime/assets/provenance/two_season_strand_v0.json",
        "generator": {
            "name": "two_season_strand_v2",
            "search_attempt": instance["attempt"],
            "constraint_selection_attempt": instance["selection_attempt"],
            "variant_count": variant_lower_bound,
            "variant_count_kind": "lower bound from balanced colour phrases and coprime Winter traversals",
        },
        "palette": copy.deepcopy(list(PALETTE)),
        "initial_sequence": instance["initial"],
        "season_orders": orders,
        "target_pairs": target_pairs,
        "parameters": parameters,
        "fold_rule": {
            "open_colors": [0, 1],
            "closing_to_open": {"2": 1, "3": 0},
            "description": "Each season reads the same strand in its own visible order. SUN/NIGHT and MOSS/BERRY close last-opened compatible stems.",
        },
        "target_pair_total": pair_total,
        "initial_pair_delta": instance["initial_pair_delta"],
    }
    ground_truth: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "palette": copy.deepcopy(list(PALETTE)),
        "initial_sequence": instance["initial"],
        "canonical_sequence": instance["canonical"],
        "season_orders": orders,
        "target_pairs": target_pairs,
        "parameters": parameters,
        "mutated_indices": instance["mutated_indices"],
        "canonical_paint_run": instance["paint_run"],
        "coupled_node_count": instance["coupled_node_count"],
        "conflicting_repairs": instance["conflicting_repairs"],
        "initial_pair_delta": instance["initial_pair_delta"],
        "variant_count": variant_lower_bound,
        "variant_count_kind": "lower bound from balanced colour phrases and coprime Winter traversals",
    }
    if condition:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
