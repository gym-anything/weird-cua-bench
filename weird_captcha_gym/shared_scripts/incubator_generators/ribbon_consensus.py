from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "ribbon_consensus"
COLORS = (
    {"name": "coral", "hex": "#f26b6b", "ink": "#4e171c"},
    {"name": "turquoise", "hex": "#4fc7c0", "ink": "#073a3b"},
    {"name": "gold", "hex": "#f2c75c", "ink": "#4d3510"},
    {"name": "violet", "hex": "#9b88e8", "ink": "#24184d"},
    {"name": "lime", "hex": "#9dd66f", "ink": "#203e19"},
)

# The uncontrolled task and controlled L4 profile share this configuration.
# The other profiles alter the actual alignment problem, not just a label.
DEFAULT_PARAMETERS = {
    "row_count": 5,
    "sequence_length": 13,
    "target_gap_count": 2,
    "misalignment_count": 5,
    "max_edits": 8,
    "color_count": 4,
    "mutation_rate": 0.14,
    "gap_open_penalty": 5,
    "gap_extend_penalty": 1,
    "required_gain_ratio": 0.82,
}
CONTROL_FIELDS = frozenset(DEFAULT_PARAMETERS)


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _control_parameters(task: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    condition = task.get("_control_condition")
    if condition is None:
        return None, dict(DEFAULT_PARAMETERS)
    if not isinstance(condition, dict):
        raise ValueError("ribbon consensus control condition is malformed")
    parameters = dict(condition.get("difficulty_parameters") or {})
    if set(parameters) != CONTROL_FIELDS:
        missing = sorted(CONTROL_FIELDS - set(parameters))
        unexpected = sorted(set(parameters) - CONTROL_FIELDS)
        detail = ", ".join([*(f"missing {item}" for item in missing), *(f"unexpected {item}" for item in unexpected)])
        raise ValueError(f"ribbon consensus control fields do not match: {detail}")
    merged = dict(DEFAULT_PARAMETERS)
    merged.update(parameters)
    integer_ranges = {
        "row_count": (3, 6),
        "sequence_length": (7, 18),
        "target_gap_count": (0, 5),
        "misalignment_count": (2, 10),
        "max_edits": (2, 16),
        "color_count": (3, len(COLORS)),
        "gap_open_penalty": (1, 20),
        "gap_extend_penalty": (1, 8),
    }
    for name, (low, high) in integer_ranges.items():
        value = merged[name]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"ribbon consensus parameter {name} must be an integer in {low}..{high}")
    for name in ("mutation_rate", "required_gain_ratio"):
        value = merged[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"ribbon consensus parameter {name} must be finite")
    if not (0 <= float(merged["mutation_rate"]) <= 0.45):
        raise ValueError("ribbon consensus mutation_rate is outside 0..0.45")
    if not 0.2 <= float(merged["required_gain_ratio"]) <= 0.99:
        raise ValueError("ribbon consensus required_gain_ratio is outside 0.2..0.99")
    if int(merged["misalignment_count"]) > int(merged["max_edits"]):
        raise ValueError("ribbon consensus max_edits must cover the generated repairs")
    if int(merged["target_gap_count"]) >= int(merged["sequence_length"]) - 2:
        raise ValueError("ribbon consensus target gaps leave too little sequence")
    return copy.deepcopy(condition), merged


def _valid_shift(columns: list[int], break_index: int, delta: int, column_count: int) -> list[int] | None:
    if not 1 <= break_index < len(columns) or delta not in (-1, 1):
        return None
    shifted = list(columns)
    for index in range(break_index, len(shifted)):
        shifted[index] += delta
    if min(shifted) < 0 or max(shifted) >= column_count:
        return None
    if any(left >= right for left, right in zip(shifted, shifted[1:])):
        return None
    return shifted


def score_alignment(
    rows: list[dict[str, Any]],
    columns_by_row: dict[str, list[int]],
    gap_open_penalty: int,
    gap_extend_penalty: int,
) -> dict[str, Any]:
    """Return the visible sum-of-pairs score and affine internal-gap audit.

    Terminal gaps are ignored, matching the source mechanic's anti-shove rule.
    Row order and tile order remain fixed; only the integer column positions
    are changed by a move.
    """
    lookup = {
        row["id"]: {column: index for index, column in enumerate(columns_by_row[row["id"]])}
        for row in rows
    }
    minimum = min(min(values) for values in columns_by_row.values())
    maximum = max(max(values) for values in columns_by_row.values())
    matches = 0
    mismatches = 0
    column_scores: list[int] = []
    for column in range(minimum, maximum + 1):
        tokens: list[int | None] = []
        for row in rows:
            index = lookup[row["id"]].get(column)
            tokens.append(None if index is None else int(row["colors"][index]))
        column_score = 0
        for left_index in range(len(tokens)):
            for right_index in range(left_index + 1, len(tokens)):
                left, right = tokens[left_index], tokens[right_index]
                if left is None or right is None:
                    continue
                if left == right:
                    matches += 1
                    column_score += 1
                else:
                    mismatches += 1
                    column_score -= 1
        column_scores.append(column_score)

    gap_open_runs = 0
    gap_extensions = 0
    for row in rows:
        positions = set(columns_by_row[row["id"]])
        first = min(positions)
        last = max(positions)
        inside_gap = False
        for column in range(first + 1, last):
            if column not in positions:
                if inside_gap:
                    gap_extensions += 1
                else:
                    gap_open_runs += 1
                    inside_gap = True
            else:
                inside_gap = False
    score = (
        matches
        - mismatches
        - gap_open_runs * int(gap_open_penalty)
        - gap_extensions * int(gap_extend_penalty)
    )
    return {
        "score": int(score),
        "matches": int(matches),
        "mismatches": int(mismatches),
        "gap_open_runs": int(gap_open_runs),
        "gap_extensions": int(gap_extensions),
        "column_scores": column_scores,
    }


def _make_rows(
    rng: random.Random,
    row_count: int,
    sequence_length: int,
    target_gap_count: int,
    color_count: int,
    mutation_rate: float,
) -> tuple[list[dict[str, Any]], dict[str, list[int]], int]:
    target_width = sequence_length + target_gap_count
    motif = [rng.randrange(color_count) for _ in range(target_width)]
    # Short repeating runs make vertical agreements visible while the small
    # mutation rate keeps local matches from becoming a one-look answer key.
    if target_width >= 6:
        for index in range(2, target_width, 5):
            motif[index] = motif[index - 1]
    rows: list[dict[str, Any]] = []
    target_columns: dict[str, list[int]] = {}
    for row_index in range(row_count):
        row_id = f"ribbon-{row_index + 1}"
        gap_choices = list(range(1, target_width - 1))
        gaps = set(rng.sample(gap_choices, target_gap_count)) if target_gap_count else set()
        positions = [column for column in range(target_width) if column not in gaps]
        colors: list[int] = []
        for column in positions:
            color = motif[column]
            if rng.random() < mutation_rate:
                alternatives = [value for value in range(color_count) if value != color]
                color = rng.choice(alternatives)
            colors.append(color)
        rows.append({
            "id": row_id,
            "label": f"RIBBON {chr(65 + row_index)}",
            "colors": colors,
            "target_columns": positions,
        })
        target_columns[row_id] = positions
    return rows, target_columns, target_width


def _candidate_layout(
    rng: random.Random,
    parameters: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, list[int]], dict[str, list[int]], list[dict[str, Any]], int] | None:
    row_count = int(parameters["row_count"])
    sequence_length = int(parameters["sequence_length"])
    target_gap_count = int(parameters["target_gap_count"])
    column_count = sequence_length + target_gap_count + int(parameters["misalignment_count"]) + 3
    rows, target_columns, _target_width = _make_rows(
        rng,
        row_count,
        sequence_length,
        target_gap_count,
        int(parameters["color_count"]),
        float(parameters["mutation_rate"]),
    )
    initial_columns = copy.deepcopy(target_columns)
    actions: list[dict[str, Any]] = []
    row_order = list(range(row_count))
    rng.shuffle(row_order)
    for action_index in range(int(parameters["misalignment_count"])):
        row_index = row_order[action_index % row_count]
        row = rows[row_index]
        current = initial_columns[row["id"]]
        candidates = list(range(1, len(current)))
        rng.shuffle(candidates)
        selected: tuple[int, int, list[int]] | None = None
        for break_index in candidates:
            for delta in rng.sample([-1, 1], 2):
                shifted = _valid_shift(current, break_index, delta, column_count)
                if shifted is not None:
                    selected = (break_index, delta, shifted)
                    break
            if selected is not None:
                break
        if selected is None:
            return None
        break_index, delta, shifted = selected
        initial_columns[row["id"]] = shifted
        actions.append({"row_id": row["id"], "break_index": break_index, "delta": delta})
    return rows, target_columns, initial_columns, actions, column_count


def _public_rows(rows: list[dict[str, Any]], initial_columns: dict[str, list[int]], color_count: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        columns = initial_columns[row["id"]]
        result.append({
            "id": row["id"],
            "label": row["label"],
            "tiles": [
                {
                    "id": f"{row['id']}-tile-{index + 1}",
                    "index": index,
                    "color": int(color),
                    "column": int(columns[index]),
                    "color_name": COLORS[int(color)]["name"],
                }
                for index, color in enumerate(row["colors"])
            ],
            "color_count": color_count,
        })
    return result


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    condition, parameters = _control_parameters(task)
    rows: list[dict[str, Any]] | None = None
    target_columns: dict[str, list[int]] | None = None
    initial_columns: dict[str, list[int]] | None = None
    repair_actions: list[dict[str, Any]] | None = None
    column_count = 0
    target_score: dict[str, Any] | None = None
    initial_score: dict[str, Any] | None = None
    threshold = 0
    for _attempt in range(500):
        candidate = _candidate_layout(rng, parameters)
        if candidate is None:
            continue
        candidate_rows, candidate_target, candidate_initial, candidate_actions, candidate_column_count = candidate
        target_eval = score_alignment(candidate_rows, candidate_target, int(parameters["gap_open_penalty"]), int(parameters["gap_extend_penalty"]))
        initial_eval = score_alignment(candidate_rows, candidate_initial, int(parameters["gap_open_penalty"]), int(parameters["gap_extend_penalty"]))
        gain = target_eval["score"] - initial_eval["score"]
        if gain <= 0:
            continue
        candidate_threshold = initial_eval["score"] + max(1, math.ceil(gain * float(parameters["required_gain_ratio"])))
        if candidate_threshold >= target_eval["score"]:
            continue
        rows, target_columns, initial_columns, repair_actions = candidate_rows, candidate_target, candidate_initial, candidate_actions
        column_count = candidate_column_count
        target_score, initial_score, threshold = target_eval, initial_eval, candidate_threshold
        break
    if rows is None or target_columns is None or initial_columns is None or repair_actions is None or target_score is None or initial_score is None:
        raise RuntimeError("could not generate a solvable ribbon consensus layout")

    task_id = str(task.get("id") or "ribbon_consensus_seed_0001@0.1")
    condition_token = "" if condition is None or int(condition["difficulty"]) == 4 else f"|d{int(condition['difficulty'])}"
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}{condition_token}".encode("utf-8")).hexdigest()[:12]
    colors = [copy.deepcopy(item) for item in COLORS[: int(parameters["color_count"])]]
    public_rows = _public_rows(rows, initial_columns, int(parameters["color_count"]))
    public_state: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": "Reweave the colored ribbons so their vertical bands agree. Shift a suffix; never reorder a ribbon.",
        "submit_label": "CERTIFY ALIGNMENT",
        "asset_manifest": "shared_runtime/assets/provenance/ribbon_consensus_v0.json",
        "generator": {"name": "procedural_ribbon_alignment_v1", "variant_count": 4_800_000_000},
        "stage": {"column_count": column_count, "cell_width": 40, "row_height": 52},
        "colors": colors,
        "rows": public_rows,
        "initial_columns": copy.deepcopy(initial_columns),
        "column_count": column_count,
        "score": int(initial_score["score"]),
        "score_floor": int(threshold),
        "score_breakdown": initial_score,
        "max_edits": int(parameters["max_edits"]),
        "parameters": copy.deepcopy(parameters),
    }
    ground_truth: dict[str, Any] = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "parameters": copy.deepcopy(parameters),
        "stage": public_state["stage"],
        "colors": colors,
        "rows": rows,
        "public_rows": public_rows,
        "initial_columns": copy.deepcopy(initial_columns),
        "target_columns": copy.deepcopy(target_columns),
        "repair_actions": [
            {"row_id": item["row_id"], "break_index": int(item["break_index"]), "delta": -int(item["delta"])}
            for item in reversed(repair_actions)
        ],
        "target_score": target_score,
        "initial_score": initial_score,
        "score_floor": int(threshold),
        "variant_count": public_state["generator"]["variant_count"],
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
