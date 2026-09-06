from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "one_stroke_atelier"
STAGE = {"width": 900, "height": 470}
FIELD_ORDER = ("tool", "colour", "width", "stamp", "burnish")
FIELD_OPTIONS = {
    "tool": (
        {"value": "nib", "label": "NIB", "glyph": "✒"},
        {"value": "brush", "label": "BRUSH", "glyph": "▥"},
        {"value": "burin", "label": "BURIN", "glyph": "⌁"},
        {"value": "roller", "label": "ROLLER", "glyph": "▰"},
    ),
    "colour": (
        {"value": "cobalt", "label": "COBALT", "glyph": "●", "swatch": "#3569c8"},
        {"value": "coral", "label": "CORAL", "glyph": "●", "swatch": "#d45c54"},
        {"value": "jade", "label": "JADE", "glyph": "●", "swatch": "#31906f"},
        {"value": "saffron", "label": "SAFFRON", "glyph": "●", "swatch": "#d49b2f"},
    ),
    "width": (
        {"value": "hairline", "label": "HAIRLINE", "glyph": "Ⅰ"},
        {"value": "fine", "label": "FINE", "glyph": "Ⅱ"},
        {"value": "broad", "label": "BROAD", "glyph": "Ⅲ"},
        {"value": "heavy", "label": "HEAVY", "glyph": "Ⅳ"},
    ),
    "stamp": (
        {"value": "star", "label": "STAR", "glyph": "✦"},
        {"value": "moth", "label": "MOTH", "glyph": "M"},
        {"value": "moon", "label": "MOON", "glyph": "◒"},
        {"value": "leaf", "label": "LEAF", "glyph": "⌇"},
    ),
    "burnish": (
        {"value": "matte", "label": "MATTE", "glyph": "░"},
        {"value": "satin", "label": "SATIN", "glyph": "▒"},
        {"value": "mirror", "label": "MIRROR", "glyph": "◇"},
        {"value": "hammered", "label": "HAMMERED", "glyph": "⠿"},
    ),
}

DEFAULT_PARAMETERS = {
    "phase_count": 4,
    "choice_count": 3,
    "branch_shift": 2,
    "reverse_count": 2,
    "motif_point_count": 6,
    "gate_half_length": 43,
    "gate_tolerance": 18,
    "motif_tolerance": 23,
    "stroke_budget": 1,
    "locked_gate_memory": 0,
}
CONTROL_FIELDS = frozenset(DEFAULT_PARAMETERS)
OPPOSITE = {"right": "left", "left": "right", "up": "down", "down": "up"}
BASE_DIRECTIONS = ("right", "down", "left", "up", "right")

MOTIFS = {
    "crown": [[600, 326], [640, 256], [688, 316], [735, 225], [782, 316], [830, 256], [870, 326]],
    "wave": [[598, 286], [642, 238], [687, 265], [733, 333], [780, 305], [827, 237], [871, 284]],
    "leaf": [[602, 326], [642, 270], [690, 239], [737, 226], [785, 242], [830, 275], [868, 326]],
    "zig": [[600, 255], [644, 325], [689, 247], [735, 328], [782, 245], [827, 322], [870, 252]],
}


def _seed_int(seed: str, salt: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{salt}".encode()).digest()[:8], "big")


def _parameters(task: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, int]]:
    condition = task.get("_control_condition")
    if condition is None:
        return None, dict(DEFAULT_PARAMETERS)
    if not isinstance(condition, dict):
        raise ValueError("atelier control condition is malformed")
    supplied = dict(condition.get("difficulty_parameters") or {})
    if set(supplied) != CONTROL_FIELDS:
        raise ValueError("atelier difficulty profile fields do not match the generator contract")
    values = dict(DEFAULT_PARAMETERS)
    values.update(supplied)
    ranges = {
        "phase_count": (2, 5), "choice_count": (2, 4), "branch_shift": (0, 3),
        "reverse_count": (0, 5), "motif_point_count": (3, 7), "gate_half_length": (30, 65),
        "gate_tolerance": (10, 30), "motif_tolerance": (12, 40), "stroke_budget": (1, 3),
        "locked_gate_memory": (0, 5),
    }
    for name, (low, high) in ranges.items():
        value = values[name]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"atelier control parameter {name} must be an integer in {low}..{high}")
    if values["reverse_count"] > values["phase_count"]:
        raise ValueError("atelier reverse_count cannot exceed phase_count")
    return copy.deepcopy(condition), values


def _sample_motif(template: list[list[int]], count: int) -> list[list[int]]:
    if count == len(template):
        return copy.deepcopy(template)
    indexes = [round(index * (len(template) - 1) / (count - 1)) for index in range(count)]
    return [copy.deepcopy(template[index]) for index in indexes]


def _gate_key(phase: int, prefix: tuple[str, ...]) -> str:
    return f"{phase}|{'/'.join(prefix)}"


def _gate_position(
    phase: int,
    slot: int,
    choice_count: int,
    shift: int,
    hit_half_length: int,
    locked_gate_memory: int,
) -> tuple[str, int, int]:
    # The entire accepted interval is visibly rendered. Keep at least sixteen
    # stage units of actual empty space between adjacent accepted bars.
    spread = max(126 if choice_count == 2 else 102, hit_half_length * 2 + 16)
    centered = (slot - (choice_count - 1) / 2) * spread
    if phase == 0:
        return "vertical", 225 + shift, round(235 + centered)
    if phase == 1:
        return "horizontal", round(470 + centered), 122 + shift
    if phase == 2:
        return "vertical", (800 if locked_gate_memory else 676) + shift, round(235 + centered)
    if phase == 3:
        return "horizontal", round(448 + centered), min(425, (416 if locked_gate_memory else 350) + shift)
    return "vertical", (150 if locked_gate_memory else 445) + shift, round(235 + centered)


def _build_gate_sets(
    seed: str,
    difficulty: int,
    target: dict[str, dict[str, str]],
    parameters: dict[str, int],
) -> tuple[dict[str, list[dict[str, Any]]], list[int]]:
    phase_count = parameters["phase_count"]
    choice_count = parameters["choice_count"]
    reversal_rng = random.Random(_seed_int(seed, f"{MECHANIC_ID}|d{difficulty}|reversals"))
    reversed_phases = sorted(reversal_rng.sample(range(phase_count), parameters["reverse_count"]))
    gate_sets: dict[str, list[dict[str, Any]]] = {}
    prefixes: list[tuple[str, ...]] = [()]
    for phase in range(phase_count):
        field = FIELD_ORDER[phase]
        options = list(FIELD_OPTIONS[field][:choice_count])
        next_prefixes: list[tuple[str, ...]] = []
        for prefix in prefixes:
            layout_rng = random.Random(_seed_int(seed, f"{MECHANIC_ID}|d{difficulty}|{phase}|{'/'.join(prefix)}"))
            shuffled = copy.deepcopy(options)
            layout_rng.shuffle(shuffled)
            branch_code = (_seed_int("/".join(prefix) or "start", field) % 5) - 2
            branch_shift = branch_code * parameters["branch_shift"] * 11 if phase else 0
            gates: list[dict[str, Any]] = []
            for slot, option in enumerate(shuffled):
                hit_half_length = parameters["gate_half_length"] + parameters["gate_tolerance"]
                orientation, x, y = _gate_position(
                    phase, slot, choice_count, branch_shift, hit_half_length, parameters["locked_gate_memory"]
                )
                direction = BASE_DIRECTIONS[phase]
                if option["value"] == target[field]["value"] and phase in reversed_phases:
                    direction = OPPOSITE[direction]
                elif option["value"] != target[field]["value"] and layout_rng.random() < 0.45:
                    direction = OPPOSITE[direction]
                gates.append({
                    "id": f"{field}-{option['value']}", "field": field, "value": option["value"],
                    "label": option["label"], "glyph": option["glyph"], "swatch": option.get("swatch"),
                    "orientation": orientation, "direction": direction, "center": [x, y],
                    "half_length": parameters["gate_half_length"], "tolerance": parameters["gate_tolerance"],
                    "hit_half_length": hit_half_length,
                })
            gate_sets[_gate_key(phase, prefix)] = gates
            next_prefixes.extend(prefix + (option["value"],) for option in options)
        prefixes = next_prefixes
    return gate_sets, reversed_phases


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition, parameters = _parameters(task)
    difficulty = int((condition or {}).get("difficulty") or 3)
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    active_fields = list(FIELD_ORDER[: parameters["phase_count"]])
    target: dict[str, dict[str, str]] = {}
    for field in active_fields:
        option = copy.deepcopy(rng.choice(FIELD_OPTIONS[field][: parameters["choice_count"]]))
        target[field] = option
    motif_name = rng.choice(tuple(MOTIFS))
    motif_points = _sample_motif(MOTIFS[motif_name], parameters["motif_point_count"])
    gate_sets, reversed_phases = _build_gate_sets(seed, difficulty, target, parameters)
    task_id = str(task.get("id") or "one_stroke_atelier_seed_0001@0.1")
    condition_token = "" if difficulty == 3 else f"|d{difficulty}"
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}{condition_token}".encode()).hexdigest()[:12]
    target_summary = [
        {"field": field, **copy.deepcopy(target[field])}
        for field in active_fields
    ]
    common = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "stage": copy.deepcopy(STAGE),
        "prompt": "Forge the target badge in one stroke." + (" Spent bars lock." if parameters["locked_gate_memory"] else ""),
        "submit_label": "CERTIFY BADGE",
        "active_fields": active_fields,
        "target": target_summary,
        "motif": {"name": motif_name, "points": motif_points, "tolerance": parameters["motif_tolerance"]},
        "gate_sets": gate_sets,
        "start": [78, 235],
        "stroke_budget": parameters["stroke_budget"],
        "locked_gate_memory": parameters["locked_gate_memory"],
        "reversed_target_phases": reversed_phases,
        "generator": {"name": "branching_crossing_atelier_v1", "variant_count": 268435456},
        "asset_manifest": "shared_runtime/assets/provenance/one_stroke_atelier_v0.json",
    }
    public_state = copy.deepcopy(common)
    ground_truth = copy.deepcopy(common)
    ground_truth.update({"seed": seed, "parameters": copy.deepcopy(parameters)})
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
