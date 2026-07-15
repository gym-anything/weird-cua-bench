from __future__ import annotations

from typing import Any


MECHANIC_ID = "rorschach_fixed_rubric"


def _fail(feedback: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": feedback}


def _point(value: Any, width: int, height: int) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2 or any(isinstance(item, bool) for item in value):
        raise ValueError("stamp point is malformed")
    x, y = int(value[0]), int(value[1])
    if not (0 <= x <= width and 0 <= y <= height):
        raise ValueError("stamp point leaves material stage")
    return x, y


def _inside(point: tuple[int, int], rect: dict[str, Any]) -> bool:
    return (
        int(rect["x"]) <= point[0] <= int(rect["x"]) + int(rect["width"])
        and int(rect["y"]) <= point[1] <= int(rect["y"]) + int(rect["height"])
    )


def _blot_at(point: tuple[int, int], rects: list[dict[str, Any]]) -> str | None:
    for rect in rects:
        if _inside(point, rect):
            return str(rect.get("id") or "")
    return None


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    challenge_id = str(ground_truth.get("challenge_id") or "")
    task_id = str(ground_truth.get("task_id") or "")
    if any(str(source.get("mechanic_id") or "") != MECHANIC_ID for source in (payload, ground_truth, public_state)):
        return _fail("mechanic mismatch")
    if not challenge_id or str(payload.get("challenge_id") or "") != challenge_id or str(public_state.get("challenge_id") or "") != challenge_id:
        return _fail("stale challenge")
    if not task_id or str(payload.get("task_id") or "") != task_id or str(public_state.get("task_id") or "") != task_id:
        return _fail("task identity mismatch")
    try:
        required_tools = [str(tool) for tool in ground_truth.get("required_tools") or []]
        if len(required_tools) != 2 or len(set(required_tools)) != 2 or not set(required_tools).issubset({"FOLD", "PRESSURE", "COOL"}):
            raise ValueError("required material tools are malformed")
        if public_state.get("required_tools") != ground_truth.get("required_tools") or public_state.get("cycles") != ground_truth.get("cycles"):
            raise ValueError("public response rig differs from hidden contract")
        stage = dict(ground_truth.get("stage") or {})
        width, height = int(stage["width"]), int(stage["height"])
        rects = [dict(item) for item in ground_truth.get("blot_rects") or []]
        blot_ids = [str(item["id"]) for item in rects]
        if len(blot_ids) != 5 or len(set(blot_ids)) != 5:
            raise ValueError("five material specimens are required")
        cycles = {(str(item["blot_id"]), str(item["tool"])): dict(item) for item in ground_truth.get("cycles") or []}
        required_pairs = {(blot_id, tool) for blot_id in blot_ids for tool in required_tools}
        if set(cycles) != required_pairs:
            raise ValueError("specimen-bound response cycles are incomplete")
        ticks_per_cycle = int(ground_truth.get("ticks_per_cycle"))
        if ticks_per_cycle < 5 or any(len(cycle.get("frames") or []) != ticks_per_cycle for cycle in cycles.values()):
            raise ValueError("response cycle frames are malformed")
        dock = dict(ground_truth.get("stamp_dock_rect") or {})
        fold_min_distance = int(ground_truth.get("fold_min_distance"))
        pressure_min_ms = int(ground_truth.get("pressure_min_ms"))
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"invalid specimen interrogation contract: {exc}")

    events = payload.get("events")
    if not isinstance(events, list) or not (1 <= len(events) <= 1600):
        return _fail("material transcript is missing or outside limits")

    selected_id: str | None = None
    observed: set[tuple[str, str]] = set()
    active: dict[str, Any] | None = None
    ready_tool: str | None = None
    fold: dict[str, Any] | None = None
    pressure_down = False
    stamp: dict[str, int] | None = None
    stamped_id: str | None = None
    tick_total = fold_samples = pressure_holds = thermal_pulses = stamp_moves = 0
    reset_count = 0

    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return _fail(f"event {sequence} sequence mismatch")
        kind = str(event.get("kind") or "")
        if kind == "reset":
            selected_id = None
            observed.clear()
            active = None
            ready_tool = None
            fold = None
            pressure_down = False
            stamp = None
            stamped_id = None
            tick_total = fold_samples = pressure_holds = thermal_pulses = stamp_moves = 0
            reset_count += 1
            continue
        if kind == "select":
            blot_id = str(event.get("blot_id") or "")
            if active is not None or fold is not None or pressure_down or stamp is not None or blot_id not in blot_ids:
                return _fail("specimen selection overlaps an active physical operation")
            selected_id = blot_id
            ready_tool = None
            continue
        if selected_id is None and kind not in {"stamp_down", "stamp_move", "stamp_up"}:
            return _fail("a specimen must be selected before using a material tool")

        if kind == "fold_start":
            value = int(event.get("value"))
            if "FOLD" not in required_tools or active is not None or fold is not None or pressure_down or value > 35 or (selected_id, "FOLD") in observed:
                return _fail("fold gesture is not valid for the selected specimen")
            fold = {"start": value, "last": value, "moves": 0}
            continue
        if kind == "fold_move":
            value = int(event.get("value"))
            if fold is None or not 0 <= value <= 300 or value < int(fold["last"]):
                return _fail("fold-axis motion is invalid")
            fold["last"] = value
            fold["moves"] += 1
            fold_samples += 1
            continue
        if kind == "fold_end":
            value = int(event.get("value"))
            if fold is None or value != fold["last"] or fold["moves"] < 3 or value - fold["start"] < fold_min_distance:
                return _fail("fold axis was not physically swept far enough")
            fold = None
            ready_tool = "FOLD"
            continue
        if kind == "fold_cancel":
            value = int(event.get("value"))
            if fold is None or value != fold["last"] or (fold["moves"] >= 3 and value - fold["start"] >= fold_min_distance):
                return _fail("cancelled fold gesture is inconsistent")
            fold = None
            continue
        if kind == "pressure_down":
            if "PRESSURE" not in required_tools or active is not None or pressure_down or (selected_id, "PRESSURE") in observed:
                return _fail("pressure hold is not valid for the selected specimen")
            pressure_down = True
            continue
        if kind == "pressure_up":
            duration = int(event.get("duration_ms"))
            if not pressure_down or not pressure_min_ms <= duration <= 5000:
                return _fail("pressure hold duration is outside the physical window")
            pressure_down = False
            pressure_holds += 1
            ready_tool = "PRESSURE"
            continue
        if kind == "pressure_cancel":
            duration = int(event.get("duration_ms"))
            if not pressure_down or not 0 <= duration < pressure_min_ms:
                return _fail("cancelled pressure gesture is inconsistent")
            pressure_down = False
            continue
        if kind == "thermal_pulse":
            if "COOL" not in required_tools or active is not None or pressure_down or (selected_id, "COOL") in observed:
                return _fail("cooling pulse is not valid for the selected specimen")
            thermal_pulses += 1
            ready_tool = "COOL"
            continue
        if kind == "probe":
            tool = str(event.get("tool") or "")
            blot_id = str(event.get("blot_id") or "")
            key = (blot_id, tool)
            if active is not None or blot_id != selected_id or ready_tool != tool or key not in required_pairs or key in observed:
                return _fail("material probe does not follow the selected specimen gesture")
            active = {"key": key, "next_tick": 1, "elapsed": 0}
            ready_tool = None
            continue
        if kind == "tick":
            if active is None:
                return _fail("response sample has no active specimen probe")
            blot_id, tool = active["key"]
            tick = int(active["next_tick"])
            frames = cycles[(blot_id, tool)]["frames"]
            if event.get("blot_id") != blot_id or event.get("tool") != tool or event.get("tick") != tick or event.get("snapshot") != frames[tick - 1].get("snapshot"):
                return _fail("specimen response sample was tampered or reordered")
            elapsed = int(event.get("elapsed_ms"))
            if elapsed < tick * 65 or elapsed < active["elapsed"]:
                return _fail("transient response was not observed long enough")
            active["elapsed"] = elapsed
            active["next_tick"] += 1
            tick_total += 1
            continue
        if kind == "cycle_complete":
            if active is None or active["next_tick"] != ticks_per_cycle + 1:
                return _fail("specimen response cycle completed early")
            blot_id, tool = active["key"]
            if event.get("blot_id") != blot_id or event.get("tool") != tool:
                return _fail("specimen response cycle identity mismatch")
            observed.add((blot_id, tool))
            active = None
            continue
        if kind in {"stamp_down", "stamp_move", "stamp_up"}:
            try:
                point = _point(event.get("point"), width, height)
            except ValueError as exc:
                return _fail(str(exc))
            if kind == "stamp_down":
                if active is not None or observed != required_pairs or not _inside(point, dock):
                    return _fail("stamp did not leave its dock after every specimen probe")
                stamp = {"moves": 0}
            elif kind == "stamp_move":
                if stamp is None:
                    return _fail("stamp move has no physical stamp")
                stamp["moves"] += 1
                stamp_moves += 1
            else:
                if stamp is None or stamp["moves"] < 3:
                    return _fail("stamp was not physically dragged")
                stamped_id = _blot_at(point, rects)
                stamp = None
            continue
        return _fail(f"event {sequence} has unknown kind")

    observation_keys = sorted(f"{blot_id}|{tool}" for blot_id, tool in observed)
    expected_payload = {
        "observation_keys": observation_keys,
        "observation_count": len(observed),
        "tick_total": tick_total,
        "fold_samples": fold_samples,
        "pressure_holds": pressure_holds,
        "thermal_pulses": thermal_pulses,
        "stamp_moves": stamp_moves,
        "stamped_id": stamped_id,
        "reset_count": reset_count,
    }
    for field, value in expected_payload.items():
        if payload.get(field) != value:
            return _fail(f"submitted {field} does not match material replay")
    culprit_id = str(ground_truth.get("culprit_id") or "")
    passed = (
        observed == required_pairs
        and active is None
        and ready_tool is None
        and fold is None
        and not pressure_down
        and stamp is None
        and tick_total == len(required_pairs) * ticks_per_cycle
        and stamped_id == culprit_id
    )
    return {
        "graded": True,
        "passed": passed,
        "score": 100 if passed else 0,
        "feedback": (
            f"specimen-bound replay: probes {len(observed)}/{len(required_pairs)}; response samples "
            f"{tick_total}/{len(required_pairs) * ticks_per_cycle}; stamp={'correct' if stamped_id == culprit_id else 'incorrect'}"
        ),
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {
        "required_tools": ground_truth.get("required_tools"),
        "culprit_id": ground_truth.get("culprit_id"),
        "signatures": ground_truth.get("signatures"),
    }
