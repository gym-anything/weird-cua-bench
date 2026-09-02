from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "terrarium_order_of_operations"
MODULE_LIBRARY = (
    {"key": "dew", "name": "Dew Harp", "sigil": "◇", "hue": "#63d9d1", "accent": "#d3fffb", "kind": "mist", "climate": [2, 0, -1]},
    {"key": "moss", "name": "Velvet Moss", "sigil": "✦", "hue": "#8edc79", "accent": "#e7ffd8", "kind": "frond", "climate": [1, -1, 0]},
    {"key": "spore", "name": "Spore Bell", "sigil": "◎", "hue": "#c991e8", "accent": "#f4dcff", "kind": "cap", "climate": [0, 1, 1]},
    {"key": "beetle", "name": "Glass Beetle", "sigil": "⬡", "hue": "#efad58", "accent": "#fff0c7", "kind": "carapace", "climate": [-1, 2, 0]},
    {"key": "root", "name": "Root Archive", "sigil": "⌁", "hue": "#d07d65", "accent": "#ffe0d3", "kind": "root", "climate": [1, 0, 2]},
    {"key": "lumen", "name": "Lumen Lichen", "sigil": "☼", "hue": "#f0d761", "accent": "#fff8c5", "kind": "light", "climate": [-1, 1, 2]},
    {"key": "fern", "name": "Clock Fern", "sigil": "❧", "hue": "#55bf89", "accent": "#d8ffe8", "kind": "leaf", "climate": [2, -1, 1]},
    {"key": "coral", "name": "Mineral Coral", "sigil": "△", "hue": "#e47f9c", "accent": "#ffdce7", "kind": "branch", "climate": [0, 2, -1]},
)
HABITAT_POSITIONS = (
    (18, 66), (32, 42), (48, 70), (64, 43),
    (80, 65), (23, 24), (51, 22), (77, 26),
)
DEFAULT_PARAMETERS = {
    "module_count": 6,
    "echo_budget": 2,
    "echo_mode": "transient",
    "stage_mode": "rings",
    "cascade_ms": 900,
}


def _condition(task: dict[str, Any]) -> dict[str, Any] | None:
    value = task.get("_control_condition")
    return copy.deepcopy(value) if isinstance(value, dict) else None


def _parameters(task: dict[str, Any]) -> dict[str, Any]:
    condition = _condition(task)
    if condition:
        return copy.deepcopy(condition["difficulty_parameters"])
    return copy.deepcopy(DEFAULT_PARAMETERS)


def _validate(parameters: dict[str, Any]) -> None:
    module_count = parameters.get("module_count")
    echo_budget = parameters.get("echo_budget")
    cascade_ms = parameters.get("cascade_ms")
    if isinstance(module_count, bool) or not isinstance(module_count, int) or not 4 <= module_count <= 8:
        raise ValueError("module_count must be an integer in [4, 8]")
    if isinstance(echo_budget, bool) or not isinstance(echo_budget, int) or not 1 <= echo_budget <= module_count:
        raise ValueError("echo_budget must be an integer in [1, module_count]")
    if parameters.get("echo_mode") not in {"named", "sigil", "transient"}:
        raise ValueError("echo_mode is invalid")
    if parameters.get("stage_mode") not in {"rings", "silhouette"}:
        raise ValueError("stage_mode is invalid")
    if isinstance(cascade_ms, bool) or not isinstance(cascade_ms, int) or not 600 <= cascade_ms <= 1200:
        raise ValueError("cascade_ms must be an integer in [600, 1200]")


def generate(task: dict[str, Any], seed: str):
    parameters = _parameters(task)
    _validate(parameters)
    stable = hashlib.sha256(f"{MECHANIC_ID}:{seed}:{parameters}".encode("utf-8")).hexdigest()
    rng = random.Random(int(stable[:16], 16))
    task_id = str(task.get("id") or "terrarium_order_of_operations")
    challenge_id = f"too-{stable[:18]}"

    chosen = rng.sample(list(MODULE_LIBRARY), parameters["module_count"])
    modules = []
    for index, template in enumerate(chosen):
        module = copy.deepcopy(template)
        module["id"] = f"capsule-{template['key']}"
        module["habitat"] = {
            "x": HABITAT_POSITIONS[index][0],
            "y": HABITAT_POSITIONS[index][1],
            "bay": index + 1,
        }
        module["climate"] = [int(value) for value in template["climate"]]
        modules.append(module)

    solution_order = [module["id"] for module in modules]
    rng.shuffle(solution_order)
    tray_order = [module["id"] for module in modules]
    rng.shuffle(tray_order)
    causal_links = [
        {"source": solution_order[index - 1], "target": solution_order[index]}
        for index in range(1, len(solution_order))
    ]
    terrarium = {
        "modules": modules,
        "tray_order": tray_order,
        "runtime_causal_links": causal_links,
        "max_stage": 3,
        "final_cascade_waves": 2,
        "visual_seed": int(stable[18:26], 16),
        "season": rng.choice(("DUSK", "DAWN", "RAIN", "EMBER")),
    }
    condition = _condition(task)
    public_state = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": "Find the one order that brings every habitat to full bloom.",
        "terrarium": copy.deepcopy(terrarium),
        "parameters": copy.deepcopy(parameters),
        "asset_manifest": str((task.get("metadata") or {}).get("asset_manifest") or "shared_runtime/assets/provenance/terrarium_order_of_operations_v0.json"),
        "status": "ready",
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "modules": copy.deepcopy(modules),
        "tray_order": copy.deepcopy(tray_order),
        "solution_order": solution_order,
        "causal_links": copy.deepcopy(causal_links),
        "max_stage": 3,
        "final_cascade_waves": 2,
        "parameters": copy.deepcopy(parameters),
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
