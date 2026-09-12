from __future__ import annotations

from typing import Any


MECHANIC_ID = "curio_tray"
TRAY_CAPACITY = 7


def _fail(feedback: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": feedback}


def _overlap(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return (
        float(first["x"]) < float(second["x"]) + float(second["width"])
        and float(second["x"]) < float(first["x"]) + float(first["width"])
        and float(first["y"]) < float(second["y"]) + float(second["height"])
        and float(second["y"]) < float(first["y"]) + float(first["height"])
    )


def _accessible(items: list[dict[str, Any]], remaining: set[str]) -> list[str]:
    visible: list[str] = []
    for item in items:
        item_id = str(item.get("id") or "")
        if item_id not in remaining:
            continue
        covered = any(
            other is not item
            and str(other.get("id") or "") in remaining
            and int(other.get("z")) > int(item.get("z"))
            and _overlap(item, other)
            for other in items
        )
        if not covered:
            visible.append(item_id)
    return visible


def _bind(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> str | None:
    if str(payload.get("mechanic_id") or "") != MECHANIC_ID:
        return "payload mechanic mismatch"
    if str(ground_truth.get("mechanic_id") or "") != MECHANIC_ID:
        return "ground-truth mechanic mismatch"
    if str(public_state.get("mechanic_id") or "") != MECHANIC_ID:
        return "public-state mechanic mismatch"
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if not challenge_id or str(payload.get("challenge_id") or "") != challenge_id:
        return "stale challenge"
    if str(public_state.get("challenge_id") or "") != challenge_id:
        return "public-state challenge mismatch"
    task_id = str(ground_truth.get("task_id") or "")
    if not task_id or str(payload.get("task_id") or "") != task_id:
        return "payload task mismatch"
    if str(public_state.get("task_id") or "") != task_id:
        return "public-state task mismatch"
    return None


def _contract(ground_truth: dict[str, Any], public_state: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    hidden = ground_truth.get("items")
    public = (public_state.get("cabinet") or {}).get("items")
    if not isinstance(hidden, list) or not hidden or not isinstance(public, list) or len(public) != len(hidden):
        raise ValueError("item contract is malformed")
    public_by_id = {str(item.get("id") or ""): item for item in public if isinstance(item, dict)}
    if len(public_by_id) != len(public):
        raise ValueError("public item ids are not unique")
    projected: list[dict[str, Any]] = []
    for item in hidden:
        if not isinstance(item, dict) or not str(item.get("id") or ""):
            raise ValueError("hidden item is malformed")
        item_id = str(item["id"])
        public_item = public_by_id.get(item_id)
        if public_item is None:
            raise ValueError("public item set differs from hidden item set")
        for key in ("type", "name", "icon", "tone", "x", "y", "width", "height", "z"):
            if public_item.get(key) != item.get(key):
                raise ValueError(f"public item geometry differs for {item_id}")
        if not isinstance(item.get("type_index"), int):
            raise ValueError("hidden type index is malformed")
        projected.append(item)
    type_count = ground_truth.get("type_count")
    if isinstance(type_count, bool) or not isinstance(type_count, int) or not 3 <= type_count <= 9:
        raise ValueError("type-count contract is malformed")
    counts = [0] * type_count
    for item in projected:
        type_index = int(item["type_index"])
        if not 0 <= type_index < type_count:
            raise ValueError("item type lies outside the type contract")
        counts[type_index] += 1
    if counts != [3] * type_count:
        raise ValueError("every curio type must have exactly three copies")
    if public_state.get("tray_capacity") != TRAY_CAPACITY:
        raise ValueError("tray capacity differs from hidden contract")
    return projected, type_count


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    binding_error = _bind(payload, ground_truth, public_state)
    if binding_error:
        return _fail(binding_error)
    if ground_truth.get("control_condition") != public_state.get("control_condition"):
        return _fail("public interaction condition differs from Curio Tray contract")
    condition = ground_truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "")
    expected_source = {"simplified": "proxy_pick", "full": "pile_click"}.get(interaction)
    if expected_source is None:
        return _fail("Curio Tray interaction condition is invalid")
    try:
        items, type_count = _contract(ground_truth, public_state)
    except (TypeError, ValueError) as exc:
        return _fail(f"invalid Curio Tray contract: {exc}")

    item_by_id = {str(item["id"]): item for item in items}
    remaining = set(item_by_id)
    tray: list[str] = []
    transcript = payload.get("picks")
    if not isinstance(transcript, list) or len(transcript) > len(items):
        return _fail("pick transcript is missing or too long")
    triple_count = 0
    failed = False
    for sequence, event in enumerate(transcript, start=1):
        if failed:
            return _fail("transcript continues after a terminal tray overflow")
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return _fail(f"pick {sequence} has an invalid sequence")
        if event.get("input_source") != expected_source:
            return _fail(f"pick {sequence} uses the wrong interaction input")
        item_id = str(event.get("item_id") or "")
        if item_id not in remaining:
            return _fail(f"pick {sequence} repeats or names an unknown curio")
        if item_id not in set(_accessible(items, remaining)):
            return _fail(f"pick {sequence} selected an occluded curio")
        item_type = str(item_by_id[item_id]["type"])
        remaining.remove(item_id)
        tray.append(item_type)
        cleared_type: str | None = None
        outcome = "pick"
        if tray.count(item_type) == 3:
            tray = [value for value in tray if value != item_type]
            cleared_type = item_type
            outcome = "triple_clear"
            triple_count += 1
        if len(tray) >= TRAY_CAPACITY and remaining:
            failed = True
        expected = {
            "outcome": outcome,
            "cleared_type": cleared_type,
            "tray_after": tray,
            "tray_size_after": len(tray),
            "remaining_count": len(remaining),
        }
        for field, value in expected.items():
            if event.get(field) != value:
                return _fail(f"pick {sequence} has inconsistent {field}: expected {value!r}")
        if failed:
            break

    if payload.get("remaining_ids") != sorted(remaining):
        return _fail("submitted remaining curios do not match replay")
    if payload.get("tray") != tray:
        return _fail("submitted tray does not match replay")
    if payload.get("pick_count") != len(transcript):
        return _fail("submitted pick count does not match replay")
    if payload.get("triple_count") != triple_count:
        return _fail("submitted triple count does not match replay")
    completed = payload.get("completed") is True
    passed = completed and not failed and not remaining and not tray and triple_count == type_count
    return {
        "graded": True,
        "passed": passed,
        "feedback": (
            f"curio replay: {len(items) - len(remaining)}/{len(items)} picked; "
            f"{triple_count}/{type_count} triples cleared; tray {len(tray)}/{TRAY_CAPACITY}; "
            f"{'overflow' if failed else 'empty cabinet' if passed else 'incomplete'}"
        ),
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    return {
        "solution_order": ground_truth.get("solution_order") or [],
        "instruction": "Click the exposed curios in the supplied solution order, then appraise the empty tray.",
    }
