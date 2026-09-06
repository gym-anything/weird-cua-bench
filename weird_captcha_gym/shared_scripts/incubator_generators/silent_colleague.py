from __future__ import annotations

import copy
import hashlib
import json
import random
from typing import Any


MECHANIC_ID = "silent_colleague"
DEFAULT_PARAMETERS = {
    "ticket_count": 4,
    "label_count": 4,
    "intent_mode": "position_only",
    "signal_ticks": 5,
    "press_window_ticks": 4,
    "tick_ms": 600,
    "max_spoils": 3,
}
FRUITS = (
    {"id": "quince", "name": "QUINCE", "glyph": "Q", "hue": "#e5c75f"},
    {"id": "plum", "name": "PLUM", "glyph": "P", "hue": "#ad79c7"},
    {"id": "pear", "name": "PEAR", "glyph": "R", "hue": "#9fca68"},
    {"id": "cherry", "name": "CHERRY", "glyph": "C", "hue": "#d9585d"},
    {"id": "apricot", "name": "APRICOT", "glyph": "A", "hue": "#e99352"},
)
LABELS = (
    {"id": "moon", "name": "MOON", "sigil": "◒", "hue": "#91bad0"},
    {"id": "key", "name": "KEY", "sigil": "⌑", "hue": "#e3b965"},
    {"id": "moth", "name": "MOTH", "sigil": "⋈", "hue": "#c292d5"},
    {"id": "wave", "name": "WAVE", "sigil": "≋", "hue": "#69c8ba"},
    {"id": "thorn", "name": "THORN", "sigil": "✣", "hue": "#d48275"},
)
LOOP_POINTS = (
    (20, 82), (32, 82), (44, 82), (56, 82), (68, 82), (80, 82),
    (88, 78), (88, 60), (88, 42), (88, 24),
    (80, 12), (68, 12), (56, 12), (44, 12), (32, 12), (20, 12),
    (12, 24), (12, 42), (12, 60), (12, 78),
)
FRUIT_STATIONS = (0, 2, 4, 16, 18)
LABEL_STATIONS = (10, 11, 12, 13, 14)
FIXED_STATIONS = {
    "handoff": 5,
    "player_press": 6,
    "colleague_press": 7,
    "colleague_handoff": 8,
    "jar_rack": 9,
    "hatch": 15,
}


def _condition(task: dict[str, Any]) -> dict[str, Any] | None:
    value = task.get("_control_condition")
    return copy.deepcopy(value) if isinstance(value, dict) else None


def _parameters(task: dict[str, Any]) -> dict[str, Any]:
    condition = _condition(task)
    return copy.deepcopy(condition["difficulty_parameters"] if condition else DEFAULT_PARAMETERS)


def _validate(parameters: dict[str, Any]) -> None:
    bounds = {
        "ticket_count": (1, 5), "label_count": (2, 5), "signal_ticks": (4, 8),
        "press_window_ticks": (4, 7), "tick_ms": (500, 850), "max_spoils": (2, 4),
    }
    for name, (low, high) in bounds.items():
        value = parameters.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"{name} must be an integer in [{low}, {high}]")
    if parameters["ticket_count"] > parameters["label_count"]:
        raise ValueError("ticket_count cannot exceed label_count")
    if parameters.get("intent_mode") not in {"fruit_badge", "label_badge", "hover_badge", "position_only"}:
        raise ValueError("intent_mode is invalid")


def generate(task: dict[str, Any], seed: str):
    parameters = _parameters(task)
    _validate(parameters)
    canonical_parameters = json.dumps(parameters, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    stable = hashlib.sha256(f"{MECHANIC_ID}:{seed}:{canonical_parameters}".encode("utf-8")).hexdigest()
    rng = random.Random(int(stable[:16], 16))
    task_id = str(task.get("id") or "silent_colleague")
    challenge_id = f"sc-{stable[:18]}"
    circulation = rng.choice((-1, 1))

    def oriented(index: int) -> int:
        return index if circulation < 0 else (-index) % len(LOOP_POINTS)

    labels = [copy.deepcopy(item) for item in rng.sample(LABELS, parameters["label_count"])]
    fruits = [copy.deepcopy(item) for item in rng.sample(FRUITS, parameters["label_count"])]
    label_positions = [oriented(item) for item in rng.sample(LABEL_STATIONS, parameters["label_count"])]
    fruit_positions = [oriented(item) for item in rng.sample(FRUIT_STATIONS, parameters["label_count"])]
    for label, position in zip(labels, label_positions, strict=True):
        label["station"] = position
    for fruit, position in zip(fruits, fruit_positions, strict=True):
        fruit["station"] = position
    rng.shuffle(fruits)
    tickets = []
    for index, (label, fruit) in enumerate(zip(labels, fruits, strict=True), 1):
        tickets.append({
            "id": f"ticket-{index}", "label_id": label["id"], "fruit_id": fruit["id"],
            "label_sigil": label["sigil"], "fruit_glyph": fruit["glyph"],
            "direction": circulation,
        })
    board_order = [item["id"] for item in tickets]
    runtime_sequence = [item["id"] for item in tickets[: parameters["ticket_count"]]]
    rng.shuffle(runtime_sequence)
    selected = set(runtime_sequence)
    tickets = [item for item in tickets if item["id"] in selected]
    rng.shuffle(tickets)

    workshop = {
        "loop_points": [list(point) for point in LOOP_POINTS],
        "loop_size": len(LOOP_POINTS),
        "player_start": oriented(1),
        "colleague_start": oriented(15),
        "circulation": circulation,
        "stations": {name: oriented(position) for name, position in FIXED_STATIONS.items()},
        "fruits": fruits,
        "labels": labels,
        "tickets": tickets,
        "board_order": [item for item in board_order if item in selected],
        "runtime_ticket_sequence": runtime_sequence,
        "visual_seed": int(stable[18:26], 16),
        "batch_code": rng.choice(("NIGHT BATCH", "FOG BATCH", "BRAMBLE BATCH", "TIDE BATCH")),
    }
    condition = _condition(task)
    public = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": "Fill the preserve tickets before the shift ends.",
        "workshop": copy.deepcopy(workshop),
        "parameters": copy.deepcopy(parameters),
        "asset_manifest": str((task.get("metadata") or {}).get("asset_manifest") or "shared_runtime/assets/provenance/silent_colleague_v0.json"),
        "generator": {"name": "silent_colleague_v1", "variant_count": 1_000_000_000},
        "status": "ready",
    }
    truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "workshop": copy.deepcopy(workshop),
        "parameters": copy.deepcopy(parameters),
    }
    if condition is not None:
        public["control_condition"] = copy.deepcopy(condition)
        truth["control_condition"] = copy.deepcopy(condition)
    return public, truth
