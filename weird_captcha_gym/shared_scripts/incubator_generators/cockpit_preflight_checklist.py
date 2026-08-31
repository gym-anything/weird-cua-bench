from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "cockpit_preflight_checklist"
RANGE_LABELS = ("CABIN ENVELOPE", "HYDRAULIC BAND", "THERMAL WINDOW")
DIAL_LABELS = ("BUS PHASE", "TRIM CODE", "VENT INDEX")
BRANCH_LABELS = ("PRIMARY BUS", "FLIGHT SURFACES", "ENVIRONMENTAL", "AUXILIARY BAY")
ROW_LABELS = (
    ("Beacon interlock", "Nav relay", "Pitot braid", "Yaw damper"),
    ("Flap logic", "Trim clutch", "Spoiler link", "Rudder servo"),
    ("Cabin loop", "De-ice grid", "Vent manifold", "Oxygen test"),
    ("Recorder feed", "Standby pump", "Cargo sensor", "Tail lamp"),
)
TREE_STATES = ("OFF", "STBY", "ARM")


def _condition(task: dict[str, Any]) -> dict[str, Any] | None:
    value = task.get("_control_condition")
    return copy.deepcopy(value) if isinstance(value, dict) else None


def _parameters(task: dict[str, Any]) -> dict[str, Any]:
    condition = _condition(task)
    if condition:
        return copy.deepcopy(condition["difficulty_parameters"])
    return {
        "range_count": 2,
        "dial_count": 2,
        "branch_count": 3,
        "rows_per_branch": 2,
        "nested_branch": False,
        "initial_collapsed": 2,
        "readout_mode": "all",
        "step_span": 8,
        "coupling_count": 2,
    }


def _validate(parameters: dict[str, Any]) -> None:
    bounds = {
        "range_count": (1, 3),
        "dial_count": (1, 3),
        "branch_count": (1, 4),
        "rows_per_branch": (2, 4),
        "initial_collapsed": (0, 4),
        "step_span": (1, 12),
        "coupling_count": (1, 8),
    }
    for key, (low, high) in bounds.items():
        value = parameters.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"{key} must be an integer in [{low}, {high}]")
    if parameters["initial_collapsed"] > parameters["branch_count"]:
        raise ValueError("initial_collapsed exceeds branch_count")
    if not isinstance(parameters.get("nested_branch"), bool):
        raise ValueError("nested_branch must be boolean")
    if parameters.get("readout_mode") not in {"all", "active", "ticks"}:
        raise ValueError("readout_mode is invalid")
    analog_channels = parameters["range_count"] * 2 + parameters["dial_count"]
    if parameters["coupling_count"] >= analog_channels:
        raise ValueError("coupling_count must leave one visible source channel")


def _shifted(rng: random.Random, target: int, minimum: int, maximum: int, span: int, *, step: int = 1) -> int:
    choices = [
        value
        for value in range(minimum, maximum + 1, step)
        if value != target and abs(value - target) <= span * step
    ]
    return rng.choice(choices)


def generate(task: dict[str, Any], seed: str):
    parameters = _parameters(task)
    _validate(parameters)
    stable = hashlib.sha256(f"{MECHANIC_ID}:{seed}:{parameters}".encode("utf-8")).hexdigest()
    rng = random.Random(int(stable[:16], 16))
    challenge_id = f"cpf-{stable[:18]}"
    task_id = str(task.get("id") or "cockpit_preflight_checklist")

    ranges = []
    for index in range(parameters["range_count"]):
        target_low = rng.randrange(10, 41, 5)
        target_high = rng.randrange(max(55, target_low + 25), 91, 5)
        low = _shifted(rng, target_low, 0, min(target_high - 10, 65), parameters["step_span"], step=5)
        high_choices = [
            value for value in range(max(low + 10, 35), 101, 5)
            if value != target_high and abs(value - target_high) <= parameters["step_span"] * 5
        ]
        high = rng.choice(high_choices)
        ranges.append({
            "id": f"range-{index + 1}", "label": RANGE_LABELS[index],
            "minimum": 0, "maximum": 100, "step": 5,
            "low": low, "high": high, "target_low": target_low, "target_high": target_high,
        })

    dials = []
    for index in range(parameters["dial_count"]):
        target = rng.randrange(0, 12)
        value = _shifted(rng, target, 0, 11, parameters["step_span"])
        dials.append({
            "id": f"dial-{index + 1}", "label": DIAL_LABELS[index],
            "minimum": 0, "maximum": 11, "step": 1, "value": value, "target": target,
        })

    branches = []
    collapsed_start = parameters["branch_count"] - parameters["initial_collapsed"]
    for branch_index in range(parameters["branch_count"]):
        rows = []
        for row_index in range(parameters["rows_per_branch"]):
            target = rng.choice(TREE_STATES)
            current = rng.choice([item for item in TREE_STATES if item != target])
            rows.append({
                "id": f"circuit-{branch_index + 1}-{row_index + 1}",
                "label": ROW_LABELS[branch_index][row_index],
                "state": current,
                "target": target,
                "depth": 2 if parameters["nested_branch"] and branch_index == parameters["branch_count"] - 1 else 1,
            })
        nested = parameters["nested_branch"] and branch_index == parameters["branch_count"] - 1
        branches.append({
            "id": f"branch-{branch_index + 1}",
            "label": BRANCH_LABELS[branch_index],
            "expanded": branch_index < collapsed_start,
            "depth": 2 if nested else 1,
            "parent_id": f"branch-{branch_index}" if nested else None,
            "rows": rows,
        })

    channels = []
    for item in ranges:
        channels.extend((
            {"id": item["id"], "field": "low", "label": f'{item["label"]} LOW'},
            {"id": item["id"], "field": "high", "label": f'{item["label"]} HIGH'},
        ))
    for item in dials:
        channels.append({"id": item["id"], "field": "value", "label": item["label"]})
    couplings = []
    for index in range(parameters["coupling_count"]):
        source = channels[index]
        target = channels[index + 1]
        couplings.append({
            "id": f"bus-{index + 1}",
            "source": {"id": source["id"], "field": source["field"]},
            "target": {"id": target["id"], "field": target["field"]},
            "source_label": source["label"],
            "target_label": target["label"],
            # A low-thumb bus must carry the paired high thumb in the same
            # direction so the two handles never pinch into an immovable
            # minimum-width band. Cross-instrument links may invert.
            "ratio": 1 if source["id"] == target["id"] else rng.choice((-1, 1)),
        })

    panel = {
        "ranges": ranges,
        "dials": dials,
        "branches": branches,
        "couplings": couplings,
        "tree_states": list(TREE_STATES),
        "readout_mode": parameters["readout_mode"],
    }
    condition = _condition(task)
    public_state = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": "Trace the calibration bus, release each sealed target, then certify CPF-27.",
        "panel": copy.deepcopy(panel),
        "parameters": copy.deepcopy(parameters),
        "asset_manifest": str((task.get("metadata") or {}).get("asset_manifest") or "shared_runtime/assets/provenance/cockpit_preflight_checklist_v0.json"),
        "status": "ready",
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "initial_panel": copy.deepcopy(panel),
        "parameters": copy.deepcopy(parameters),
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
