from __future__ import annotations

from typing import Any


MECHANIC_ID = "borrowed_tiles"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _binding_error(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> str | None:
    if payload.get("mechanic_id") != MECHANIC_ID or truth.get("mechanic_id") != MECHANIC_ID or public.get("mechanic_id") != MECHANIC_ID:
        return "mechanic mismatch"
    challenge_id = str(truth.get("challenge_id") or "")
    if not challenge_id or payload.get("challenge_id") != challenge_id:
        return "stale challenge"
    if public.get("challenge_id") != challenge_id:
        return "public-state challenge mismatch"
    task_id = str(truth.get("task_id") or "")
    if not task_id or payload.get("task_id") != task_id or public.get("task_id") != task_id:
        return "task mismatch"
    return None


def _tile_catalog(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("tile catalogue is missing")
    result: dict[str, dict[str, Any]] = {}
    for tile in value:
        if not isinstance(tile, dict):
            raise ValueError("tile catalogue item is malformed")
        tile_id = str(tile.get("id") or "")
        color = tile.get("color")
        number = tile.get("number")
        if not tile_id or tile_id in result or not isinstance(color, str) or isinstance(number, bool) or not isinstance(number, int):
            raise ValueError("tile catalogue item is invalid")
        result[tile_id] = {"id": tile_id, "color": color, "number": number}
    return result


def _initial_locations(truth: dict[str, Any], catalog: dict[str, dict[str, Any]]) -> tuple[dict[str, dict[str, str]], dict[str, list[str]]]:
    sets = truth.get("initial_sets")
    rack = truth.get("initial_rack")
    if not isinstance(sets, list) or not isinstance(rack, list):
        raise ValueError("initial tile layout is missing")
    locations: dict[str, dict[str, str]] = {}
    layout: dict[str, list[str]] = {}
    for item in sets:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("tiles"), list):
            raise ValueError("initial set is malformed")
        set_id = item["id"]
        if set_id in layout:
            raise ValueError("duplicate initial set")
        layout[set_id] = []
        for tile_id in item["tiles"]:
            tile_id = str(tile_id)
            if tile_id not in catalog or tile_id in locations:
                raise ValueError("initial layout does not conserve tiles")
            layout[set_id].append(tile_id)
            locations[tile_id] = {"zone": "table", "set_id": set_id}
    for tile_id in rack:
        tile_id = str(tile_id)
        if tile_id not in catalog or tile_id in locations:
            raise ValueError("initial rack does not conserve tiles")
        locations[tile_id] = {"zone": "rack"}
    if set(locations) != set(catalog):
        raise ValueError("initial layout omits or invents a tile")
    return locations, layout


def _is_valid_set(tile_ids: list[str], catalog: dict[str, dict[str, Any]]) -> tuple[bool, str]:
    if len(tile_ids) < 3:
        return False, "too short"
    tiles = [catalog[tile_id] for tile_id in tile_ids]
    numbers = [int(tile["number"]) for tile in tiles]
    colors = [str(tile["color"]) for tile in tiles]
    if len(set(numbers)) == 1 and len(tile_ids) <= 4 and len(set(colors)) == len(colors):
        return True, "group"
    if len(set(colors)) == 1 and len(set(numbers)) == len(numbers) and sorted(numbers) == list(range(min(numbers), max(numbers) + 1)):
        return True, "run"
    return False, "not a legal run or group"


def _copy_layout(initial_layout: dict[str, list[str]], initial_rack: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    return {set_id: tiles[:] for set_id, tiles in initial_layout.items()}, [str(tile_id) for tile_id in initial_rack]


def _location(layout: dict[str, list[str]], rack: list[str], tile_id: str) -> dict[str, str] | None:
    if tile_id in rack:
        return {"zone": "rack"}
    for set_id, tiles in layout.items():
        if tile_id in tiles:
            return {"zone": "table", "set_id": set_id}
    return None


def _remove(layout: dict[str, list[str]], rack: list[str], tile_id: str) -> None:
    if tile_id in rack:
        rack.remove(tile_id)
        return
    for tiles in layout.values():
        if tile_id in tiles:
            tiles.remove(tile_id)
            return
    raise ValueError("tile is not in the current layout")


def _normal_layout(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, list):
        raise ValueError("table layout must be a list")
    result: dict[str, list[str]] = {}
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("tiles"), list):
            raise ValueError("table set is malformed")
        set_id = item["id"]
        if set_id in result or any(not isinstance(tile_id, str) for tile_id in item["tiles"]):
            raise ValueError("table set identity is invalid")
        result[set_id] = list(item["tiles"])
    return result


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    error = _binding_error(payload, ground_truth, public_state)
    if error:
        return _fail(error)
    if ground_truth.get("control_condition") != public_state.get("control_condition"):
        return _fail("interaction condition differs from tile contract")
    condition = ground_truth.get("control_condition") or {}
    expected_source = {"simplified": "tile_click_drop", "full": "tile_drag"}.get(str(condition.get("interaction") or "")) if condition else "tile_drag"
    if expected_source is None:
        return _fail("invalid tile interaction condition")
    try:
        catalog = _tile_catalog(ground_truth.get("tiles"))
        public_catalog = _tile_catalog(public_state.get("tiles"))
        if catalog != public_catalog:
            return _fail("public tile catalogue differs from hidden contract")
        initial_locations, initial_layout = _initial_locations(ground_truth, catalog)
        public_initial = _normal_layout(public_state.get("table_sets"))
        if {key: sorted(value) for key, value in public_initial.items()} != {key: sorted(value) for key, value in initial_layout.items()}:
            return _fail("public table layout differs from hidden contract")
        initial_rack = [str(tile_id) for tile_id in ground_truth.get("initial_rack") or []]
        if public_state.get("rack_tiles") != initial_rack:
            return _fail("public rack differs from hidden contract")
    except (TypeError, ValueError) as exc:
        return _fail(f"invalid tile contract: {exc}")

    layout, rack = _copy_layout(initial_layout, initial_rack)
    actions = payload.get("actions")
    if not isinstance(actions, list) or not (1 <= len(actions) <= 300):
        return _fail("move transcript is missing or outside limits")
    reassigned = 0
    rack_to_table = 0
    for index, action in enumerate(actions, start=1):
        if not isinstance(action, dict) or action.get("sequence") != index or action.get("input_source") != expected_source:
            return _fail(f"move {index} has invalid sequence or interaction source")
        tile_id = action.get("tile_id")
        if tile_id not in catalog:
            return _fail(f"move {index} names an unknown tile")
        actual_from = _location(layout, rack, tile_id)
        declared_from = action.get("from")
        destination = action.get("to")
        if actual_from != declared_from:
            return _fail(f"move {index} starts from the wrong visible location")
        if not isinstance(destination, dict) or destination.get("zone") not in {"rack", "table"}:
            return _fail(f"move {index} has an invalid destination")
        from_set = str(actual_from.get("set_id") or "") if actual_from.get("zone") == "table" else ""
        if destination.get("zone") == "rack":
            if actual_from.get("zone") == "rack":
                return _fail(f"move {index} is a no-op")
            _remove(layout, rack, tile_id)
            rack.append(tile_id)
        else:
            set_id = str(destination.get("set_id") or "")
            if not set_id:
                return _fail(f"move {index} has no target set")
            if set_id not in layout:
                if not set_id.startswith("new_set_") or set_id in layout:
                    return _fail(f"move {index} invents an invalid set identity")
                layout[set_id] = []
            if actual_from.get("zone") == "table" and from_set == set_id:
                return _fail(f"move {index} is a no-op")
            _remove(layout, rack, tile_id)
            layout[set_id].append(tile_id)
            if actual_from.get("zone") == "rack":
                rack_to_table += 1
            elif from_set != set_id:
                reassigned += 1

    try:
        final_layout = _normal_layout(payload.get("table_sets"))
        final_rack = payload.get("rack_tiles")
        if not isinstance(final_rack, list) or any(not isinstance(tile_id, str) for tile_id in final_rack):
            return _fail("submitted rack is malformed")
    except ValueError as exc:
        return _fail(str(exc))
    if {key: sorted(value) for key, value in final_layout.items()} != {key: sorted(value) for key, value in layout.items()} or final_rack != rack:
        return _fail("submitted layout does not match the physical move transcript")
    all_ids = [tile_id for tiles in final_layout.values() for tile_id in tiles] + list(final_rack)
    if len(all_ids) != len(catalog) or set(all_ids) != set(catalog) or len(set(all_ids)) != len(all_ids):
        return _fail("final layout does not conserve each physical tile exactly once")
    invalid_sets: list[str] = []
    valid_kinds: dict[str, str] = {}
    for set_id, tile_ids in final_layout.items():
        valid, kind = _is_valid_set(tile_ids, catalog)
        if not valid:
            invalid_sets.append(set_id)
        else:
            valid_kinds[set_id] = kind
    required_borrow = int(ground_truth.get("required_borrow_count") or 1)
    passed = (
        payload.get("completed") is True
        and not final_rack
        and not invalid_sets
        and rack_to_table >= required_borrow
        and reassigned >= required_borrow
    )
    return {
        "graded": True,
        "passed": passed,
        "feedback": (
            f"{len(final_layout)} valid sets; rack {len(final_rack)}; "
            f"rack-to-table {rack_to_table}/{required_borrow}; borrowed reassignments {reassigned}/{required_borrow}; "
            f"kinds {', '.join(valid_kinds.values()) or 'none'}"
            + (f"; invalid {', '.join(invalid_sets)}" if invalid_sets else "")
        ),
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    actions = []
    condition = ground_truth.get("control_condition") or {}
    source = {"simplified": "tile_click_drop", "full": "tile_drag"}.get(str(condition.get("interaction") or "full"), "tile_drag")
    for item in ground_truth.get("solution_actions") or []:
        action = dict(item)
        action["input_source"] = source
        actions.append(action)
    return {"actions": actions, "instruction": "Follow the visible ceramic tiles, borrow every required donor, then commit the table."}
