from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "borrowed_tiles"
COLORS = ("coral", "azure", "amber", "jade")
AUX_COLOR = "violet"
GROUP_NUMBERS = (5, 8, 11, 13)
PALETTES = ("terracotta", "midnight", "seafoam", "saffron")


def _condition(task: dict[str, Any]) -> dict[str, Any] | None:
    value = task.get("_control_condition")
    return copy.deepcopy(value) if isinstance(value, dict) else None


def _parameters(task: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    condition = _condition(task)
    params = dict((condition or {}).get("difficulty_parameters") or {})
    defaults = {"module_count": 3, "auxiliary_set_count": 1}
    for key, value in defaults.items():
        params.setdefault(key, value)
    module_count = int(params["module_count"])
    auxiliary_count = int(params["auxiliary_set_count"])
    if not 1 <= module_count <= 4 or not 0 <= auxiliary_count <= 1:
        raise ValueError("borrowed tile profile is outside supported limits")
    params["module_count"] = module_count
    params["auxiliary_set_count"] = auxiliary_count
    return params, condition


def _tile(tile_id: str, color: str, number: int, finish: int, rng: random.Random) -> dict[str, Any]:
    return {
        "id": tile_id,
        "color": color,
        "number": number,
        "finish": finish,
        "pattern": rng.randrange(4),
    }


def _add_module(
    *,
    module_index: int,
    donor_color: str,
    group_colors: list[str],
    group_number: int,
    tiles: list[dict[str, Any]],
    initial_sets: list[dict[str, Any]],
    rack: list[str],
    solution_actions: list[dict[str, Any]],
    initial_locations: dict[str, dict[str, str]],
    rng: random.Random,
) -> None:
    prefix = f"m{module_index}"
    donor_set_id = f"donor_{module_index}"
    group_set_id = f"group_{module_index}"
    donor_ids: list[str] = []
    for number in (group_number - 2, group_number - 1, group_number):
        tile_id = f"{prefix}_{donor_color}_{number}"
        tiles.append(_tile(tile_id, donor_color, number, module_index, rng))
        donor_ids.append(tile_id)
        initial_locations[tile_id] = {"zone": "table", "set_id": donor_set_id}
    group_ids: list[str] = []
    for color in group_colors:
        tile_id = f"{prefix}_{color}_{group_number}"
        tiles.append(_tile(tile_id, color, group_number, module_index + 1, rng))
        group_ids.append(tile_id)
        initial_locations[tile_id] = {"zone": "table", "set_id": group_set_id}
    rack_id = f"{prefix}_{donor_color}_{group_number - 3}"
    tiles.append(_tile(rack_id, donor_color, group_number - 3, module_index + 2, rng))
    rack.append(rack_id)
    initial_locations[rack_id] = {"zone": "rack"}
    initial_sets.extend(
        [
            {"id": donor_set_id, "label": f"DONOR RUN {module_index}", "tiles": donor_ids},
            {"id": group_set_id, "label": f"COLOUR GROUP {module_index}", "tiles": group_ids},
        ]
    )
    sequence = len(solution_actions) + 1
    solution_actions.append(
        {
            "sequence": sequence,
            "tile_id": rack_id,
            "from": {"zone": "rack"},
            "to": {"zone": "table", "set_id": donor_set_id},
        }
    )
    solution_actions.append(
        {
            "sequence": sequence + 1,
            "tile_id": donor_ids[-1],
            "from": {"zone": "table", "set_id": donor_set_id},
            "to": {"zone": "table", "set_id": group_set_id},
        }
    )


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    params, condition = _parameters(task)
    digest = hashlib.sha256(f"{seed}|{MECHANIC_ID}|v1".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    module_count = int(params["module_count"])
    auxiliary_count = int(params["auxiliary_set_count"])
    colors = list(COLORS)
    rng.shuffle(colors)

    tiles: list[dict[str, Any]] = []
    initial_sets: list[dict[str, Any]] = []
    rack: list[str] = []
    solution_actions: list[dict[str, Any]] = []
    initial_locations: dict[str, dict[str, str]] = {}
    for index in range(module_count):
        donor_color = colors[index % len(colors)]
        group_colors = [color for color in COLORS if color != donor_color]
        _add_module(
            module_index=index + 1,
            donor_color=donor_color,
            group_colors=group_colors,
            group_number=GROUP_NUMBERS[index],
            tiles=tiles,
            initial_sets=initial_sets,
            rack=rack,
            solution_actions=solution_actions,
            initial_locations=initial_locations,
            rng=rng,
        )

    for aux_index in range(auxiliary_count):
        aux_id = f"display_run_{aux_index + 1}"
        aux_tiles: list[str] = []
        for number in (1, 2, 3):
            tile_id = f"aux_{aux_index + 1}_{AUX_COLOR}_{number}"
            tiles.append(_tile(tile_id, AUX_COLOR, number, 5 + aux_index, rng))
            aux_tiles.append(tile_id)
            initial_locations[tile_id] = {"zone": "table", "set_id": aux_id}
        initial_sets.append({"id": aux_id, "label": "DISPLAY RUN", "tiles": aux_tiles})

    rng.shuffle(initial_sets)
    rng.shuffle(rack)
    task_id = str(task.get("id") or f"{MECHANIC_ID}_seed_0001@0.1")
    condition_token = f"|d{condition['difficulty']}|{condition['interaction']}|{task_id}" if condition else ""
    challenge_id = hashlib.sha256(f"{seed}|borrowed-tiles-v1{condition_token}".encode("utf-8")).hexdigest()[:12]
    palette = PALETTES[rng.randrange(len(PALETTES))]
    prompt = str(task.get("natural_language") or "Rebuild the tabletop: place every rack tile, borrow from the existing sets, then commit only valid runs and groups.")
    public_state: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": prompt,
        "submit_label": "COMMIT TABLE",
        "asset_manifest": "shared_runtime/assets/provenance/borrowed_tiles_v0.json",
        "generator": {
            "name": "ceramic_table_borrow_reassembly_v1",
            "variant_count": 4 ** (module_count * 7) * 4 * 1000,
            "module_count": module_count,
            "auxiliary_set_count": auxiliary_count,
        },
        "tiles": copy.deepcopy(tiles),
        "table_sets": copy.deepcopy(initial_sets),
        "rack_tiles": rack[:],
        "palette": palette,
        "rules": {
            "run": "three or more consecutive numbers in one colour",
            "group": "three or four equal numbers in different colours",
            "goal": "empty the rack and leave every table set valid",
            "reassembly": "at least one original table tile must change sets; appending rack tiles alone is not enough",
        },
    }
    ground_truth: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "tiles": copy.deepcopy(tiles),
        "initial_sets": copy.deepcopy(initial_sets),
        "initial_rack": rack[:],
        "initial_locations": initial_locations,
        "solution_actions": copy.deepcopy(solution_actions),
        "required_borrow_count": module_count,
        "module_count": module_count,
        "auxiliary_set_count": auxiliary_count,
        "palette": palette,
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
