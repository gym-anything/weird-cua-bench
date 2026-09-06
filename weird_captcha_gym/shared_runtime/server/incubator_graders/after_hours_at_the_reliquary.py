from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "after_hours_at_the_reliquary"
COLOR_IDS = {"vermilion", "amber", "verdigris", "cobalt", "ivory", "violet"}
DIRECT_ACTIONS = {
    "flip_label": ("label_flipped", None),
    "collect_empty_frame": ("collected_empty_frame", "empty_frame"),
    "open_lens_drawer": ("lens_drawer_open", None),
    "collect_lens": ("collected_lens", "lens"),
    "remove_dust_sheet": ("color_revealed", None),
    "collect_hook": ("collected_hook", "hook"),
    "lift_floor_tile": ("floor_open", None),
    "collect_handle": ("collected_handle", "handle"),
    "collect_wire": ("collected_wire", "wire"),
    "reveal_order": ("order_revealed", None),
    "collect_wax_seal": ("collected_wax_seal", "wax_seal"),
    "collect_bone_pin": ("collected_bone_pin", "bone_pin"),
}
USE_ACTIONS = {
    "use_loupe": ("loupe", "digit_revealed", None),
    "use_hook": ("hook", "collected_ward_key", "ward_key"),
    "use_key": ("ward_key", None, None),
}


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _identity(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> str | None:
    if any(str(item.get("mechanic_id") or "") != MECHANIC_ID for item in (payload, truth, public)):
        return "mechanic mismatch"
    for key in ("task_id", "challenge_id"):
        expected = str(truth.get(key) or "")
        if not expected or str(payload.get(key) or "") != expected or str(public.get(key) or "") != expected:
            return f"stale or mismatched {key}"
    return None


def _finite_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))


def _point(value: Any, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 2 or any(not _finite_number(item) for item in value):
        raise ValueError(f"{label} is malformed")
    point = [float(value[0]), float(value[1])]
    if any(item < -0.05 or item > 1.05 for item in point):
        raise ValueError(f"{label} is outside the normalized surface")
    return point


def _inside(point: list[float], rect: list[float], tolerance: float = 0.0) -> bool:
    x, y, width, height = [float(item) for item in rect]
    return x - tolerance <= point[0] <= x + width + tolerance and y - tolerance <= point[1] <= y + height + tolerance


def _rect(value: Any, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 4 or any(not _finite_number(item) for item in value):
        raise ValueError(f"{label} is malformed")
    x, y, width, height = [float(item) for item in value]
    if not (0 <= x < x + width <= 1 and 0 <= y < y + height <= 1 and width >= 0.05 and height >= 0.05):
        raise ValueError(f"{label} is outside the scene or too small")
    return [x, y, width, height]


def _item_card_rect(inventory: list[str], item_id: str, layout: dict[str, Any]) -> list[float]:
    try:
        slot = inventory.index(item_id)
    except ValueError as exc:
        raise ValueError("claimed drag item is not in the visible tray") from exc
    if slot >= int(layout["max_slots"]):
        raise ValueError("claimed drag item is outside the visible card slots")
    return [
        float(layout["left"]) + slot * (float(layout["width"]) + float(layout["gap"])),
        float(layout["top"]),
        float(layout["width"]),
        float(layout["height"]),
    ]


def _gesture(
    event: dict[str, Any],
    *,
    source_item_rect: list[float],
    destination_item_rect: list[float] | None,
    scene_rect: list[float] | None,
    inventory_region: list[float],
) -> None:
    gesture = event.get("gesture")
    if not isinstance(gesture, dict):
        raise ValueError("direct manipulation lacks drag proof")
    start = _point(gesture.get("start_root"), "drag start")
    end_root = _point(gesture.get("end_root"), "drag endpoint")
    start_inventory = _point(gesture.get("start_inventory"), "inventory drag start")
    travel = gesture.get("travel_px")
    samples = gesture.get("sample_count")
    if not _finite_number(travel) or not isinstance(samples, int) or isinstance(samples, bool):
        raise ValueError("drag travel proof is malformed")
    if not _inside(start, inventory_region, 0.02):
        raise ValueError("drag does not start in the visible object tray")
    if not _inside(start_inventory, source_item_rect):
        raise ValueError("drag does not start on the claimed object card")
    if float(travel) < 20 or samples < 2 or math.hypot(end_root[0] - start[0], end_root[1] - start[1]) < 0.035:
        raise ValueError("stationary click is not direct object manipulation")
    if destination_item_rect is not None:
        end_inventory = _point(gesture.get("end_inventory"), "inventory drag endpoint")
        if not _inside(end_root, inventory_region, 0.03):
            raise ValueError("item combination does not end in the visible object tray")
        if not _inside(end_inventory, destination_item_rect):
            raise ValueError("item combination does not end on the claimed object card")
    elif scene_rect is not None:
        end_scene = _point(gesture.get("end_scene"), "scene drag endpoint")
        if not _inside(end_scene, scene_rect, 0.025):
            raise ValueError("item use misses the generated scene geometry")


def _contract(truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    shared_keys = (
        "views", "targets", "items", "recipes", "active_locks", "raw_digit_clue",
        "raw_color_clue", "read_directions", "collectible_item_ids",
        "parameters", "regions", "item_card_layout",
    )
    for key in shared_keys:
        if public.get(key) != truth.get(key):
            raise ValueError(f"public and hidden {key} disagree")
    condition = truth.get("control_condition")
    if public.get("control_condition") != condition:
        raise ValueError("control condition disagrees")
    parameters = truth.get("parameters")
    if not isinstance(parameters, dict):
        raise ValueError("difficulty parameters are missing")
    if condition is not None and condition.get("difficulty_parameters") != parameters:
        raise ValueError("condition parameters disagree")
    interaction = str((condition or {}).get("interaction") or "full")
    if interaction not in {"simplified", "full"}:
        raise ValueError("interaction mode is invalid")
    views = truth.get("views")
    if not isinstance(views, list) or len(views) != parameters.get("view_count") or not 3 <= len(views) <= 6:
        raise ValueError("view inventory disagrees with difficulty")
    if [item.get("id") for item in views] != list(range(len(views))) or views[0].get("role") != "door":
        raise ValueError("fixed view topology is malformed")
    targets_value = truth.get("targets")
    if not isinstance(targets_value, list):
        raise ValueError("scene targets are missing")
    targets: dict[str, dict[str, Any]] = {}
    for target in targets_value:
        if not isinstance(target, dict):
            raise ValueError("scene target is malformed")
        target_id = str(target.get("id") or "")
        view_id = target.get("view_id")
        if not target_id or target_id in targets or isinstance(view_id, bool) or not isinstance(view_id, int) or not 0 <= view_id < len(views):
            raise ValueError("scene target identity is malformed")
        _rect(target.get("rect"), f"target {target_id}")
        if target.get("action") not in set(DIRECT_ACTIONS) | set(USE_ACTIONS) | {"open_door"}:
            raise ValueError(f"target {target_id} has an unknown action")
        if not isinstance(target.get("requires_flags"), list) or not isinstance(target.get("forbids_flags"), list):
            raise ValueError(f"target {target_id} has malformed visibility conditions")
        targets[target_id] = target
    expected_targets = {"door_handle", "label_frame", "empty_frame", "label_code", "lens_drawer", "lens"}
    if not expected_targets <= set(targets):
        raise ValueError("required scene affordances are absent")
    items = truth.get("items")
    if not isinstance(items, dict) or not {"empty_frame", "lens", "loupe"} <= set(items):
        raise ValueError("object tray vocabulary is malformed")
    recipes = truth.get("recipes")
    if not isinstance(recipes, list) or not recipes:
        raise ValueError("combination recipe list is missing")
    recipe_map: dict[frozenset[str], str] = {}
    for recipe in recipes:
        inputs = recipe.get("inputs") if isinstance(recipe, dict) else None
        output = str(recipe.get("output") or "") if isinstance(recipe, dict) else ""
        if not isinstance(inputs, list) or len(inputs) != 2 or len(set(inputs)) != 2 or any(item not in items for item in inputs) or output not in items:
            raise ValueError("combination recipe is malformed")
        key = frozenset(str(item) for item in inputs)
        if key in recipe_map:
            raise ValueError("combination recipe is duplicated")
        recipe_map[key] = output
    active_locks = truth.get("active_locks")
    if not isinstance(active_locks, list) or active_locks != parameters.get("active_locks"):
        raise ValueError("active wards disagree")
    answers = truth.get("lock_answers")
    if not isinstance(answers, dict) or public.get("runtime_lock_answers") != answers:
        raise ValueError("browser ward commitment disagrees with hidden truth")
    directions = truth.get("read_directions")
    raw_digits = str(truth.get("raw_digit_clue") or "")
    raw_colors = truth.get("raw_color_clue")
    if not raw_digits.isdigit() or len(raw_digits) != parameters.get("digit_length"):
        raise ValueError("digit clue is malformed")
    if not isinstance(raw_colors, list) or len(raw_colors) != parameters.get("color_length") or any(color not in COLOR_IDS for color in raw_colors):
        raise ValueError("colour clue is malformed")
    expected_digits = raw_digits if directions.get("digit") == "forward" else raw_digits[::-1]
    expected_colors = raw_colors if directions.get("color") == "forward" else list(reversed(raw_colors))
    if set(answers) != {"digit", "color"} or answers.get("digit") != expected_digits or answers.get("color") != expected_colors:
        raise ValueError("ward answers do not follow the visible clues")
    collectible = truth.get("collectible_item_ids")
    if not isinstance(collectible, list) or len(collectible) != len(set(collectible)) or any(item not in items for item in collectible):
        raise ValueError("collectible object list is malformed")
    regions = truth.get("regions")
    if not isinstance(regions, dict) or set(regions) != {"inventory", "scene"}:
        raise ValueError("interaction regions are malformed")
    inventory_region = _rect(regions["inventory"], "inventory region")
    _rect(regions["scene"], "scene region")
    item_card_layout = truth.get("item_card_layout")
    if not isinstance(item_card_layout, dict) or set(item_card_layout) != {
        "left", "top", "width", "height", "gap", "max_slots"
    }:
        raise ValueError("item-card layout is malformed")
    layout_numbers = [
        item_card_layout["left"], item_card_layout["top"], item_card_layout["width"],
        item_card_layout["height"], item_card_layout["gap"],
    ]
    if any(not _finite_number(value) for value in layout_numbers):
        raise ValueError("item-card layout contains a non-finite value")
    maximum_slots = item_card_layout["max_slots"]
    if isinstance(maximum_slots, bool) or not isinstance(maximum_slots, int) or maximum_slots < 2:
        raise ValueError("item-card layout has an invalid slot count")
    final_right = float(item_card_layout["left"]) + maximum_slots * float(item_card_layout["width"]) + (maximum_slots - 1) * float(item_card_layout["gap"])
    if (
        float(item_card_layout["left"]) < 0
        or float(item_card_layout["top"]) < 0
        or float(item_card_layout["width"]) < 0.08
        or float(item_card_layout["height"]) < 0.5
        or float(item_card_layout["gap"]) < 0
        or final_right > 1
        or float(item_card_layout["top"]) + float(item_card_layout["height"]) > 1
    ):
        raise ValueError("item-card layout falls outside the visible tray")
    return {
        "interaction": interaction,
        "views": views,
        "targets": targets,
        "items": items,
        "recipes": recipe_map,
        "active_locks": active_locks,
        "answers": answers,
        "collectible": collectible,
        "inventory_region": inventory_region,
        "item_card_layout": item_card_layout,
        "parameters": parameters,
    }


def _available(target: dict[str, Any], flags: set[str], view_id: int) -> bool:
    return (
        target["view_id"] == view_id
        and all(flag in flags for flag in target["requires_flags"])
        and all(flag not in flags for flag in target["forbids_flags"])
    )


def _snapshot(state: dict[str, Any], active_locks: list[str]) -> dict[str, Any]:
    return {
        "view_id": state["view_id"],
        "flags": sorted(state["flags"]),
        "inventory": list(state["inventory"]),
        "released_locks": [lock for lock in active_locks if lock in state["released"]],
        "wrong_entries": {lock: state["wrong"][lock] for lock in active_locks},
        "seized_lock": state["seized"],
        "completed": state["completed"],
    }


def _counters(state: dict[str, Any], active_locks: list[str], collectible: list[str]) -> dict[str, Any]:
    return {
        "locks_released": sum(lock in state["released"] for lock in active_locks),
        "items_collected": len(state["collected"]),
        "items_total": len(collectible),
        "misses": state["misses"],
        "wrong_lock_entries": sum(state["wrong"].values()),
    }


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    identity_error = _identity(payload, truth, public)
    if identity_error:
        return _fail(identity_error)
    try:
        contract = _contract(truth, public)
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"invalid reliquary contract: {exc}")
    interaction = contract["interaction"]
    if payload.get("interaction_mode") != interaction:
        return _fail("submitted interaction mode differs from task condition")
    events = payload.get("events")
    if not isinstance(events, list) or not events or len(events) > 240:
        return _fail("reliquary transcript is missing or oversized")
    state = {
        "view_id": 0,
        "flags": set(),
        "inventory": [],
        "collected": set(),
        "released": set(),
        "wrong": {lock: 0 for lock in contract["active_locks"]},
        "seized": None,
        "misses": 0,
        "completed": False,
    }
    turn_source = "turn_button" if interaction == "simplified" else "edge_arrow"
    combine_source = "inventory_select_pair" if interaction == "simplified" else "inventory_drag_item"
    use_source = "inventory_select_scene" if interaction == "simplified" else "inventory_drag_scene"
    try:
        for sequence, event in enumerate(events, 1):
            if not isinstance(event, dict) or event.get("sequence") != sequence:
                raise ValueError(f"event {sequence} has an invalid sequence")
            if state["completed"] or state["seized"] is not None:
                raise ValueError(f"event {sequence} occurs after a terminal state")
            kind = event.get("type")
            if kind == "turn":
                before, after = event.get("from_view"), event.get("to_view")
                direction = event.get("direction")
                if event.get("input_source") != turn_source or before != state["view_id"] or direction not in {"left", "right"}:
                    raise ValueError(f"event {sequence} uses an invalid view control")
                delta = -1 if direction == "left" else 1
                expected = (state["view_id"] + delta) % len(contract["views"])
                if after != expected:
                    raise ValueError(f"event {sequence} skips the fixed view topology")
                state["view_id"] = expected
            elif kind == "scene":
                target_id = str(event.get("target_id") or "")
                target = contract["targets"].get(target_id)
                if target is None or not _available(target, state["flags"], state["view_id"]):
                    raise ValueError(f"event {sequence} hits an unavailable scene object")
                if event.get("input_source") != "scene_click" or not _inside(_point(event.get("point"), "scene click"), target["rect"], 0.015):
                    raise ValueError(f"event {sequence} misses the visible scene geometry")
                action = target["action"]
                if action == "open_door":
                    if any(lock not in state["released"] for lock in contract["active_locks"]):
                        raise ValueError(f"event {sequence} opens a still-warded door")
                    state["flags"].add("door_open")
                    state["completed"] = True
                elif action in DIRECT_ACTIONS:
                    flag, item = DIRECT_ACTIONS[action]
                    state["flags"].add(flag)
                    if item is not None:
                        state["inventory"].append(item)
                        state["collected"].add(item)
                else:
                    raise ValueError(f"event {sequence} clicks an object that requires an inventory item")
            elif kind == "combine":
                first, second, result = str(event.get("first") or ""), str(event.get("second") or ""), str(event.get("result") or "")
                if event.get("input_source") != combine_source or first == second or first not in state["inventory"] or second not in state["inventory"]:
                    raise ValueError(f"event {sequence} combines unavailable objects or uses the wrong input surface")
                expected = contract["recipes"].get(frozenset((first, second)))
                if not expected or result != expected:
                    raise ValueError(f"event {sequence} reports an invalid object combination")
                if interaction == "full":
                    _gesture(
                        event,
                        source_item_rect=_item_card_rect(state["inventory"], first, contract["item_card_layout"]),
                        destination_item_rect=_item_card_rect(state["inventory"], second, contract["item_card_layout"]),
                        scene_rect=None,
                        inventory_region=contract["inventory_region"],
                    )
                state["inventory"].remove(first)
                state["inventory"].remove(second)
                state["inventory"].append(result)
                state["flags"].add(f"crafted_{result}")
            elif kind == "use":
                target_id, item_id = str(event.get("target_id") or ""), str(event.get("item_id") or "")
                target = contract["targets"].get(target_id)
                if target is None or not _available(target, state["flags"], state["view_id"]):
                    raise ValueError(f"event {sequence} uses an item on an unavailable scene object")
                if event.get("input_source") != use_source or item_id not in state["inventory"]:
                    raise ValueError(f"event {sequence} uses an unavailable object or wrong input surface")
                rule = USE_ACTIONS.get(target["action"])
                if rule is None or item_id != rule[0]:
                    raise ValueError(f"event {sequence} applies the wrong object")
                if interaction == "full":
                    _gesture(
                        event,
                        source_item_rect=_item_card_rect(state["inventory"], item_id, contract["item_card_layout"]),
                        destination_item_rect=None,
                        scene_rect=target["rect"],
                        inventory_region=contract["inventory_region"],
                    )
                if target["action"] == "use_key":
                    if "key" not in contract["active_locks"] or "key" in state["released"]:
                        raise ValueError(f"event {sequence} uses a key on an inactive ward")
                    state["released"].add("key")
                    state["inventory"].remove("ward_key")
                    state["flags"].add("key_released")
                else:
                    flag, output = rule[1], rule[2]
                    state["flags"].add(str(flag))
                    if output is not None:
                        state["inventory"].append(output)
                        state["collected"].add(output)
            elif kind in {"digit_submit", "color_submit"}:
                lock = "digit" if kind == "digit_submit" else "color"
                if lock not in contract["active_locks"] or lock in state["released"] or state["view_id"] != 0:
                    raise ValueError(f"event {sequence} submits to an unavailable ward")
                needed_flag = "digit_revealed" if lock == "digit" else "color_revealed"
                if needed_flag not in state["flags"] or (contract["parameters"].get("cross_view_order") and "order_revealed" not in state["flags"]):
                    raise ValueError(f"event {sequence} submits a ward before its visible evidence was uncovered")
                expected = contract["answers"][lock]
                guess = event.get("guess")
                if lock == "digit":
                    if not isinstance(guess, str) or len(guess) != len(expected) or not guess.isdigit():
                        raise ValueError(f"event {sequence} has a malformed dial entry")
                elif not isinstance(guess, list) or len(guess) != len(expected) or any(color not in COLOR_IDS for color in guess):
                    raise ValueError(f"event {sequence} has a malformed colour entry")
                accepted = guess == expected
                if event.get("accepted") is not accepted or event.get("input_source") != f"{lock}_controls":
                    raise ValueError(f"event {sequence} forges ward feedback or input source")
                if accepted:
                    state["released"].add(lock)
                    state["flags"].add(f"{lock}_released")
                else:
                    state["wrong"][lock] += 1
                    if state["wrong"][lock] >= int(contract["parameters"]["max_wrong_entries"]):
                        state["seized"] = lock
            elif kind == "miss":
                if event.get("input_source") != "scene_background":
                    raise ValueError(f"event {sequence} has a malformed miss source")
                _point(event.get("point"), "scene miss")
                state["misses"] += 1
            elif kind == "misuse":
                source = event.get("input_source")
                item_id = str(event.get("item_id") or "")
                target_id = str(event.get("target_id") or "")
                if item_id not in state["inventory"]:
                    raise ValueError(f"event {sequence} misuses an unavailable object")
                if target_id.startswith("item:"):
                    second = target_id.removeprefix("item:")
                    if (
                        source != combine_source
                        or second == item_id
                        or second not in state["inventory"]
                        or frozenset((item_id, second)) in contract["recipes"]
                    ):
                        raise ValueError(f"event {sequence} forges an invalid object combination")
                    if interaction == "full":
                        _gesture(
                            event,
                            source_item_rect=_item_card_rect(state["inventory"], item_id, contract["item_card_layout"]),
                            destination_item_rect=_item_card_rect(state["inventory"], second, contract["item_card_layout"]),
                            scene_rect=None,
                            inventory_region=contract["inventory_region"],
                        )
                elif target_id == "scene:none":
                    if interaction != "full" or source != use_source:
                        raise ValueError(f"event {sequence} has an invalid empty-scene drop")
                    _gesture(
                        event,
                        source_item_rect=_item_card_rect(state["inventory"], item_id, contract["item_card_layout"]),
                        destination_item_rect=None,
                        scene_rect=None,
                        inventory_region=contract["inventory_region"],
                    )
                else:
                    target = contract["targets"].get(target_id)
                    if target is None or not _available(target, state["flags"], state["view_id"]):
                        raise ValueError(f"event {sequence} misuses an item on an unavailable scene object")
                    expected = USE_ACTIONS.get(target["action"])
                    if source != use_source or (expected is not None and item_id == expected[0]):
                        raise ValueError(f"event {sequence} forges a scene-object misuse")
                    if interaction == "full":
                        _gesture(
                            event,
                            source_item_rect=_item_card_rect(state["inventory"], item_id, contract["item_card_layout"]),
                            destination_item_rect=None,
                            scene_rect=target["rect"],
                            inventory_region=contract["inventory_region"],
                        )
                    if target["action"] == "use_key":
                        if "key" not in contract["active_locks"] or "key" in state["released"]:
                            raise ValueError(f"event {sequence} submits to an unavailable key ward")
                        state["wrong"]["key"] += 1
                        if state["wrong"]["key"] >= int(contract["parameters"]["max_wrong_entries"]):
                            state["seized"] = "key"
                state["misses"] += 1
            else:
                raise ValueError(f"event {sequence} has unknown type {kind!r}")
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"reliquary replay rejected: {exc}")

    expected_snapshot = _snapshot(state, contract["active_locks"])
    expected_counters = _counters(state, contract["active_locks"], contract["collectible"])
    if payload.get("final_state") != expected_snapshot:
        return _fail("submitted final room state does not match replay")
    if payload.get("counters") != expected_counters:
        return _fail("submitted secondary counters do not match replay")
    passed = payload.get("completed") is True and state["completed"] and state["seized"] is None
    return {
        "graded": True,
        "passed": passed,
        "score": 100 if passed else 0,
        "feedback": (
            f"replayed {len(events)} actions; wards {expected_counters['locks_released']}/{len(contract['active_locks'])}, "
            f"objects {expected_counters['items_collected']}/{expected_counters['items_total']}, "
            f"misses {expected_counters['misses']}, wrong entries {expected_counters['wrong_lock_entries']}"
        ),
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {
        "lock_answers": ground_truth.get("lock_answers"),
        "targets": ground_truth.get("targets"),
        "recipes": ground_truth.get("recipes"),
    }
