from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "pocket_radio_repair"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _finite_point(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 2 and all(isinstance(item, (int, float)) and math.isfinite(float(item)) for item in value)


def _inside(point: Any, width: float = 900.0, height: float = 560.0) -> bool:
    return _finite_point(point) and -30 <= float(point[0]) <= width + 30 and -30 <= float(point[1]) <= height + 30


def _world(public: dict[str, Any], covers: dict[str, dict], screws: dict[str, dict], components: dict[str, dict]) -> dict[str, Any]:
    cover_list = list(covers.values())
    screw_list = list(screws.values())
    component_list = list(components.values())
    covers_installed = all(item["installed"] for item in cover_list)
    screws_installed = all(item["installed"] for item in screw_list)
    components_fixed = all(item["installed"] and item["repaired"] for item in component_list)
    passed = covers_installed and screws_installed and components_fixed
    return {"passed": passed, "covers": sum(item["installed"] for item in cover_list), "cover_total": len(cover_list), "screws": sum(item["installed"] for item in screw_list), "screw_total": len(screw_list), "components": sum(item["repaired"] for item in component_list), "component_total": len(component_list)}


def _expected_sources(interaction: str) -> dict[str, str]:
    if interaction == "simplified":
        return {"select_tool": "tool_button", "loosen_screw": "screw_button", "open_cover": "cover_button", "clean_component": "clean_button", "replace_component": "replace_button", "install_cover": "cover_button", "install_screw": "screw_button", "test": "test_button"}
    return {"tool_drag": "tool_drag", "screw_rotate": "screw_rotate", "lift_cover": "cover_drag", "clean_gesture": "clean_gesture", "replace_component": "component_drag", "install_cover": "cover_drag", "install_screw": "screw_drag", "test": "test_button"}


def _check_direct_points(item: dict[str, Any], keys: tuple[str, ...]) -> bool:
    points = [item.get(key) for key in keys]
    return all(_inside(point) for point in points)


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    if any(item.get("mechanic_id") != MECHANIC_ID for item in (payload, truth, public)):
        return _fail("mechanic mismatch")
    if payload.get("task_id") != truth.get("task_id") or payload.get("challenge_id") != truth.get("challenge_id"):
        return _fail("stale task or challenge")
    if public.get("task_id") != truth.get("task_id") or public.get("challenge_id") != truth.get("challenge_id"):
        return _fail("public state is not bound to this radio")
    if public.get("control_condition") != truth.get("control_condition"):
        return _fail("radio control condition differs from the task")
    condition = truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "full")
    expected = _expected_sources(interaction)
    if interaction not in {"simplified", "full"}:
        return _fail("invalid radio interaction")
    events = payload.get("events")
    if not isinstance(events, list) or len(events) > 3000:
        return _fail("radio transcript malformed")

    tools = {str(item["id"]): dict(item) for item in truth.get("tools") or []}
    covers = {str(item["id"]): dict(item) for item in truth.get("covers") or []}
    screws = {str(item["id"]): dict(item) for item in truth.get("screws") or []}
    components = {str(item["id"]): dict(item) for item in truth.get("components") or []}
    selected_tool: str | None = None
    test_event: dict[str, Any] | None = None
    action_counts: dict[str, int] = {}

    def fail(message: str) -> dict[str, Any]:
        return _fail(message)

    def cover_ready_to_open(cover: dict[str, Any]) -> bool:
        if any(screws[screw_id]["installed"] for screw_id in cover["screw_ids"]):
            return False
        layer = int(cover["layer"])
        return all(not item["installed"] for item in covers.values() if int(item["layer"]) < layer)

    def component_accessible(component: dict[str, Any]) -> bool:
        cover = covers[component["cover_id"]]
        if cover["installed"]:
            return False
        layer = int(cover["layer"])
        return all(not item["installed"] for item in covers.values() if int(item["layer"]) < layer)

    def cover_ready_to_install(cover: dict[str, Any]) -> bool:
        if cover["installed"]:
            return False
        layer = int(cover["layer"])
        if any(not item["installed"] or not item["repaired"] for item in components.values() if item["cover_id"] == cover["id"]):
            return False
        return all(item["installed"] for item in covers.values() if int(item["layer"]) > layer)

    for sequence, item in enumerate(events, 1):
        if not isinstance(item, dict) or item.get("seq") != sequence:
            return fail(f"event {sequence} sequence invalid")
        action = str(item.get("type") or "")
        action_counts[action] = action_counts.get(action, 0) + 1
        if action not in expected:
            if action == "abandon":
                return fail("radio abandoned")
            return fail(f"unknown or wrong-surface action {action!r}")
        if item.get("input_source") != expected[action]:
            return fail(f"{action} used the wrong interaction surface")

        if action == "select_tool":
            tool_id = str(item.get("tool_id") or "")
            if tool_id not in tools:
                return fail("unknown tool selected")
            selected_tool = tool_id
        elif action == "tool_drag":
            tool_id, screw_id = str(item.get("tool_id") or ""), str(item.get("screw_id") or "")
            if tool_id not in tools or screw_id not in screws or tools[tool_id]["id"] != screws[screw_id]["tool_id"]:
                return fail("tool was not dragged to that fastener")
            if not _check_direct_points(item, ("start", "end")):
                return fail("tool drag has no visible path")
            index = list(screws).index(screw_id)
            expected_point = (float(screws[screw_id]["x"]), float(screws[screw_id]["y"])) if screws[screw_id]["installed"] else (770.0, 170.0 + index * 30.0)
            if math.hypot(float(item["end"][0]) - expected_point[0], float(item["end"][1]) - expected_point[1]) > 70:
                return fail("tool drag missed the visible fastener")
            selected_tool = tool_id
        elif action in {"loosen_screw", "screw_rotate"}:
            screw_id, tool_id = str(item.get("screw_id") or ""), str(item.get("tool_id") or selected_tool or "")
            if screw_id not in screws or tool_id not in tools or screws[screw_id]["installed"] is not True:
                return fail("fastener is unavailable")
            if tool_id != screws[screw_id]["tool_id"]:
                return fail("wrong screwdriver for fastener")
            cover = covers[screws[screw_id]["cover_id"]]
            if cover["installed"] is not True:
                return fail("fastener is not on an installed cover")
            if action == "screw_rotate":
                try:
                    turn = float(item.get("turn_degrees"))
                except (TypeError, ValueError):
                    return fail("direct screwdriver rotation is missing")
                if turn < float(truth.get("turn_degrees", 360)) * 0.7 or not _check_direct_points(item, ("start", "end")):
                    return fail("visible screwdriver rotation was too short")
            screws[screw_id]["installed"] = False
            selected_tool = tool_id
        elif action in {"open_cover", "lift_cover"}:
            cover_id = str(item.get("cover_id") or "")
            if cover_id not in covers or not cover_ready_to_open(covers[cover_id]):
                return fail("cover opened before its fasteners or outer access was cleared")
            if action == "lift_cover" and not _check_direct_points(item, ("start", "end")):
                return fail("cover lift has no visible drag")
            covers[cover_id]["installed"] = False
        elif action == "clean_component":
            component_id = str(item.get("component_id") or "")
            if component_id not in components or not component_accessible(components[component_id]) or components[component_id]["condition"] != "dirty":
                return fail("dirty component is not currently accessible")
            strokes = int(item.get("stroke_count", 0)) if isinstance(item.get("stroke_count", 0), (int, float)) else 0
            if action == "clean_component" and interaction == "simplified":
                if strokes < int(truth.get("clean_strokes", 1)):
                    return fail("cleaning did not cover the visible grime")
            components[component_id]["repaired"] = True
        elif action == "clean_gesture":
            component_id = str(item.get("component_id") or "")
            if component_id not in components or not component_accessible(components[component_id]) or components[component_id]["condition"] != "dirty":
                return fail("dirty component is not currently accessible")
            try:
                length = float(item.get("stroke_length"))
            except (TypeError, ValueError):
                return fail("cleaning gesture is missing its path")
            if length < int(truth.get("clean_strokes", 1)) * 22:
                return fail("cleaning gesture did not scrub the visible component")
            if not _check_direct_points(item, ("start", "end")):
                return fail("cleaning gesture left the visible component")
            components[component_id]["repaired"] = True
        elif action == "replace_component":
            component_id = str(item.get("component_id") or "")
            if component_id not in components or not component_accessible(components[component_id]) or components[component_id]["condition"] != "missing" or components[component_id]["installed"]:
                return fail("replacement part is not currently needed")
            if interaction == "full" and not _check_direct_points(item, ("start", "end")):
                return fail("replacement drag has no visible path")
            components[component_id]["installed"] = True
            components[component_id]["repaired"] = True
        elif action == "install_cover":
            cover_id = str(item.get("cover_id") or "")
            if cover_id not in covers or not cover_ready_to_install(covers[cover_id]):
                return fail("cover cannot be seated yet")
            if interaction == "full" and not _check_direct_points(item, ("start", "end")):
                return fail("cover replacement has no visible drag")
            covers[cover_id]["installed"] = True
        elif action == "install_screw":
            screw_id, tool_id = str(item.get("screw_id") or ""), str(item.get("tool_id") or selected_tool or "")
            if screw_id not in screws or tool_id not in tools or screws[screw_id]["installed"]:
                return fail("fastener is not loose")
            cover = covers[screws[screw_id]["cover_id"]]
            if not cover["installed"] or tool_id != screws[screw_id]["tool_id"] or any(not components[item_id]["repaired"] for item_id in components if components[item_id]["cover_id"] == cover["id"]):
                return fail("fastener cannot be installed before its repaired cover")
            if interaction == "full" and not _check_direct_points(item, ("start", "end")):
                return fail("fastener replacement has no visible drag")
            screws[screw_id]["installed"] = True
            selected_tool = tool_id
        elif action == "test":
            test_event = item

    if test_event is None or payload.get("completed") is not True:
        return fail("the radio was not power-tested")
    result = _world(public, covers, screws, components)
    if bool(test_event.get("accepted")) != bool(result["passed"]):
        return fail("visible power-test verdict disagrees with replay")
    if not result["passed"]:
        return fail(f"radio incomplete: covers {result['covers']}/{result['cover_total']}, fasteners {result['screws']}/{result['screw_total']}, repaired parts {result['components']}/{result['component_total']}")
    return {"graded": True, "passed": True, "feedback": f"radio restored: {result['cover_total']} covers, {result['screw_total']} fasteners, {result['component_total']} repaired components", "metrics": {"action_count": len(events), "covers": result["cover_total"], "fasteners": result["screw_total"], "components": result["component_total"], "distinct_tools": len({item.get("tool_id") for item in events if item.get("tool_id")})}}
