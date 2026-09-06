from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "after_hours_at_the_reliquary"
ASSET_MANIFEST = "shared_runtime/assets/provenance/after_hours_at_the_reliquary_v0.json"
LOCK_ORDER = ("digit", "color", "key")
WARD_COUNT_LABELS = {1: "ONE WARD", 2: "TWO WARDS", 3: "THREE WARDS"}
COLOR_IDS = ("vermilion", "amber", "verdigris", "cobalt", "ivory", "violet")
ITEM_CARD_LAYOUT = {
    "left": 0.012,
    "top": 0.07,
    "width": 0.118,
    "height": 0.86,
    "gap": 0.006,
    "max_slots": 7,
}
BASELINE_PARAMETERS = {
    "view_count": 6,
    "active_locks": ["digit", "color", "key"],
    "digit_length": 4,
    "color_length": 5,
    "hook_mode": "combined",
    "decoy_items": 0,
    "cue_level": "unmarked",
    "cross_view_order": False,
    "max_wrong_entries": 3,
}
VIEW_ROLES = {
    3: ("door", "desk", "cabinet"),
    4: ("door", "desk", "cabinet", "gallery"),
    5: ("door", "desk", "cabinet", "gallery", "reliquary"),
    6: ("door", "desk", "cabinet", "gallery", "radiator", "reliquary"),
}
ITEMS = {
    "empty_frame": {"name": "Empty Ocular Frame", "glyph": "ring"},
    "lens": {"name": "Loose Glass Lens", "glyph": "lens"},
    "loupe": {"name": "Catalog Loupe", "glyph": "loupe"},
    "handle": {"name": "Ivory Handle", "glyph": "handle"},
    "wire": {"name": "Bent Wire", "glyph": "wire"},
    "hook": {"name": "Reacher Hook", "glyph": "hook"},
    "ward_key": {"name": "Ward Key", "glyph": "key"},
    "wax_seal": {"name": "Loose Wax Seal", "glyph": "seal"},
    "bone_pin": {"name": "Bone Catalogue Pin", "glyph": "pin"},
}


def _condition(task: dict[str, Any]) -> dict[str, Any] | None:
    value = task.get("_control_condition")
    return copy.deepcopy(value) if isinstance(value, dict) else None


def _parameters(task: dict[str, Any]) -> dict[str, Any]:
    condition = _condition(task)
    if condition:
        return copy.deepcopy(condition["difficulty_parameters"])
    return copy.deepcopy(BASELINE_PARAMETERS)


def _validate(parameters: dict[str, Any]) -> None:
    view_count = parameters.get("view_count")
    if isinstance(view_count, bool) or not isinstance(view_count, int) or view_count not in VIEW_ROLES:
        raise ValueError("view_count must be an integer from 3 through 6")
    active_locks = parameters.get("active_locks")
    if (
        not isinstance(active_locks, list)
        or not active_locks
        or len(active_locks) != len(set(active_locks))
        or any(lock not in LOCK_ORDER for lock in active_locks)
        or active_locks != [lock for lock in LOCK_ORDER if lock in active_locks]
    ):
        raise ValueError("active_locks must be a nonempty ordered subset of the ward types")
    digit_length = parameters.get("digit_length")
    if isinstance(digit_length, bool) or not isinstance(digit_length, int) or not 3 <= digit_length <= 5:
        raise ValueError("digit_length must be in [3, 5]")
    color_length = parameters.get("color_length")
    if isinstance(color_length, bool) or not isinstance(color_length, int) or not 0 <= color_length <= 6:
        raise ValueError("color_length must be in [0, 6]")
    if ("color" in active_locks) != (color_length > 0):
        raise ValueError("color_length disagrees with the active colour ward")
    if parameters.get("hook_mode") not in {"none", "ready", "combined"}:
        raise ValueError("hook_mode is invalid")
    if ("key" in active_locks) != (parameters["hook_mode"] != "none"):
        raise ValueError("hook construction disagrees with the active key ward")
    decoys = parameters.get("decoy_items")
    if isinstance(decoys, bool) or not isinstance(decoys, int) or not 0 <= decoys <= 2:
        raise ValueError("decoy_items must be in [0, 2]")
    if parameters.get("cue_level") not in {"clear", "subtle", "unmarked"}:
        raise ValueError("cue_level is invalid")
    if not isinstance(parameters.get("cross_view_order"), bool):
        raise ValueError("cross_view_order must be boolean")
    maximum = parameters.get("max_wrong_entries")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum != 3:
        raise ValueError("the source-selected seizure contract requires exactly three wrong entries")


def _rect(rng: random.Random, base: tuple[float, float, float, float], cue: str) -> list[float]:
    # The artwork and hit target use this same rectangle. Jitter changes layout
    # without shrinking an affordance into a tiny or misleading target.
    spread = {"clear": 0.004, "subtle": 0.008, "unmarked": 0.012}[cue]
    x, y, width, height = base
    return [
        round(x + rng.uniform(-spread, spread), 5),
        round(y + rng.uniform(-spread, spread), 5),
        round(width, 5),
        round(height, 5),
    ]


def _target(
    rng: random.Random,
    target_id: str,
    view_id: int,
    role: str,
    base: tuple[float, float, float, float],
    action: str,
    cue: str,
    *,
    requires_flags: tuple[str, ...] = (),
    forbids_flags: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "id": target_id,
        "view_id": view_id,
        "role": role,
        "rect": _rect(rng, base, cue),
        "action": action,
        "requires_flags": list(requires_flags),
        "forbids_flags": list(forbids_flags),
    }


def _role_index(roles: tuple[str, ...], role: str) -> int:
    if role not in roles:
        raise ValueError(f"view role {role!r} is unavailable")
    return roles.index(role)


def generate(task: dict[str, Any], seed: str):
    parameters = _parameters(task)
    _validate(parameters)
    stable = hashlib.sha256(
        f"{MECHANIC_ID}:{seed}:{parameters}".encode("utf-8")
    ).hexdigest()
    rng = random.Random(int(stable[:16], 16))
    task_id = str(task.get("id") or "after_hours_at_the_reliquary")
    challenge_id = f"rel-{stable[:18]}"
    roles = VIEW_ROLES[int(parameters["view_count"])]
    cue = str(parameters["cue_level"])
    active_locks = list(parameters["active_locks"])

    raw_digits = "".join(str(rng.randrange(10)) for _ in range(int(parameters["digit_length"])))
    if raw_digits[0] == "0":
        raw_digits = str(rng.randrange(1, 10)) + raw_digits[1:]
    raw_colors = rng.sample(list(COLOR_IDS), int(parameters["color_length"]))
    # Keep the post-clue random stream stable after removing the old decorative
    # key-profile draw. The task has one ward key; it never asks the player to
    # select or compare profiles.
    rng.randrange(5)
    digit_direction = rng.choice(("forward", "reverse")) if parameters["cross_view_order"] else "forward"
    color_direction = rng.choice(("forward", "reverse")) if parameters["cross_view_order"] else "forward"
    digit_answer = raw_digits if digit_direction == "forward" else raw_digits[::-1]
    color_answer = raw_colors if color_direction == "forward" else list(reversed(raw_colors))

    views = [
        {
            "id": index,
            "role": role,
            "palette": rng.randrange(4),
            "catalogue_mark": rng.randrange(11, 98),
        }
        for index, role in enumerate(roles)
    ]
    desk = _role_index(roles, "desk")
    cabinet = _role_index(roles, "cabinet")
    targets: list[dict[str, Any]] = [
        _target(rng, "door_handle", 0, "door_handle", (0.505, 0.425, 0.06, 0.15), "open_door", cue),
        _target(rng, "label_frame", desk, "label_frame", (0.60, 0.17, 0.19, 0.29), "flip_label", cue, forbids_flags=("label_flipped",)),
        _target(rng, "empty_frame", desk, "empty_frame", (0.645, 0.27, 0.085, 0.12), "collect_empty_frame", cue, requires_flags=("label_flipped",), forbids_flags=("collected_empty_frame",)),
        _target(rng, "label_code", desk, "label_code", (0.59, 0.17, 0.21, 0.30), "use_loupe", cue, requires_flags=("label_flipped", "collected_empty_frame"), forbids_flags=("digit_revealed",)),
        _target(rng, "lens_drawer", cabinet, "lens_drawer", (0.18, 0.51, 0.25, 0.16), "open_lens_drawer", cue, forbids_flags=("lens_drawer_open",)),
        _target(rng, "lens", cabinet, "lens", (0.255, 0.555, 0.10, 0.105), "collect_lens", cue, requires_flags=("lens_drawer_open",), forbids_flags=("collected_lens",)),
    ]
    collectible_items = ["empty_frame", "lens"]

    if "color" in active_locks:
        gallery = _role_index(roles, "gallery")
        targets.append(_target(rng, "dust_sheet", gallery, "dust_sheet", (0.365, 0.15, 0.31, 0.57), "remove_dust_sheet", cue, forbids_flags=("color_revealed",)))

    if parameters["hook_mode"] == "ready":
        targets.append(_target(rng, "ready_hook", cabinet, "ready_hook", (0.72, 0.31, 0.07, 0.18), "collect_hook", cue, forbids_flags=("collected_hook",)))
        collectible_items.append("hook")
    elif parameters["hook_mode"] == "combined":
        radiator = _role_index(roles, "radiator")
        targets.extend([
            _target(rng, "floor_tile", cabinet, "floor_tile", (0.55, 0.72, 0.24, 0.14), "lift_floor_tile", cue, forbids_flags=("floor_open",)),
            _target(rng, "handle", cabinet, "handle", (0.625, 0.75, 0.095, 0.075), "collect_handle", cue, requires_flags=("floor_open",), forbids_flags=("collected_handle",)),
            _target(rng, "radiator_wire", radiator, "radiator_wire", (0.655, 0.46, 0.065, 0.22), "collect_wire", cue, forbids_flags=("collected_wire",)),
        ])
        collectible_items.extend(["handle", "wire"])

    if "key" in active_locks:
        reliquary = _role_index(roles, "reliquary")
        targets.extend([
            _target(rng, "grate", reliquary, "grate", (0.36, 0.63, 0.25, 0.15), "use_hook", cue, forbids_flags=("collected_ward_key",)),
            _target(
                rng,
                "keyhole",
                0,
                "keyhole",
                (0.765, 0.53, 0.07, 0.14),
                "use_key",
                cue,
                forbids_flags=("key_released",),
            ),
        ])
        collectible_items.append("ward_key")
        if parameters["cross_view_order"]:
            targets.append(_target(rng, "order_drawer", reliquary, "order_drawer", (0.70, 0.34, 0.18, 0.14), "reveal_order", cue, forbids_flags=("order_revealed",)))

    decoy_ids = ["wax_seal", "bone_pin"][: int(parameters["decoy_items"])]
    if decoy_ids:
        gallery = _role_index(roles, "gallery")
        targets.append(_target(rng, "wax_seal", gallery, "wax_seal", (0.76, 0.55, 0.09, 0.12), "collect_wax_seal", cue, forbids_flags=("collected_wax_seal",)))
        collectible_items.append("wax_seal")
    if len(decoy_ids) > 1:
        radiator = _role_index(roles, "radiator")
        targets.append(_target(rng, "bone_pin", radiator, "bone_pin", (0.24, 0.65, 0.075, 0.08), "collect_bone_pin", cue, forbids_flags=("collected_bone_pin",)))
        collectible_items.append("bone_pin")

    recipes = [{"inputs": ["empty_frame", "lens"], "output": "loupe"}]
    if parameters["hook_mode"] == "combined":
        recipes.append({"inputs": ["handle", "wire"], "output": "hook"})

    lock_answers = {
        "digit": digit_answer,
        "color": color_answer,
    }
    public_state = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": f"{WARD_COUNT_LABELS[len(active_locks)]} · ONE EXIT",
        "views": views,
        "targets": copy.deepcopy(targets),
        "items": copy.deepcopy(ITEMS),
        "recipes": copy.deepcopy(recipes),
        "active_locks": active_locks,
        "raw_digit_clue": raw_digits,
        "raw_color_clue": raw_colors,
        "read_directions": {"digit": digit_direction, "color": color_direction},
        "runtime_lock_answers": copy.deepcopy(lock_answers),
        "collectible_item_ids": collectible_items,
        "parameters": copy.deepcopy(parameters),
        "regions": {"inventory": [0.025, 0.80, 0.725, 0.185], "scene": [0.025, 0.13, 0.95, 0.66]},
        "item_card_layout": copy.deepcopy(ITEM_CARD_LAYOUT),
        "asset_manifest": str((task.get("metadata") or {}).get("asset_manifest") or ASSET_MANIFEST),
        "status": "ready",
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "views": copy.deepcopy(views),
        "targets": copy.deepcopy(targets),
        "items": copy.deepcopy(ITEMS),
        "recipes": copy.deepcopy(recipes),
        "active_locks": active_locks,
        "raw_digit_clue": raw_digits,
        "raw_color_clue": raw_colors,
        "read_directions": {"digit": digit_direction, "color": color_direction},
        "lock_answers": copy.deepcopy(lock_answers),
        "collectible_item_ids": collectible_items,
        "parameters": copy.deepcopy(parameters),
        "regions": copy.deepcopy(public_state["regions"]),
        "item_card_layout": copy.deepcopy(ITEM_CARD_LAYOUT),
    }
    condition = _condition(task)
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
