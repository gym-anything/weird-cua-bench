from __future__ import annotations

import copy
import math
from typing import Any


MECHANIC_ID = "reflow_vitrine"
VALUES = {
    "axis": ["row", "column"], "main": ["start", "center", "end", "space"],
    "cross": ["start", "center", "end", "stretch"], "gap": [4, 8, 12, 16],
    "padding": [4, 8, 12, 16], "wrap": ["nowrap", "wrap"], "grow": [0, 1, 2],
}


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _bind(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> str | None:
    if any(str(item.get("mechanic_id") or "") != MECHANIC_ID for item in (payload, truth, public)):
        return "mechanic mismatch"
    for key in ("task_id", "challenge_id"):
        expected = str(truth.get(key) or "")
        if not expected or str(payload.get(key) or "") != expected or str(public.get(key) or "") != expected:
            return f"stale or mismatched {key}"
    return None


def _base(child_id: str, frames: dict[str, dict[str, Any]], items: dict[str, dict[str, Any]]) -> tuple[float, float]:
    if child_id in frames:
        return float(frames[child_id]["base_w"]), float(frames[child_id]["base_h"])
    return float(items[child_id]["w"]), float(items[child_id]["h"])


def _layout(frames_list: list[dict[str, Any]], items_list: list[dict[str, Any]], config: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    frames = {frame["id"]: frame for frame in frames_list}
    items = {item["id"]: item for item in items_list}
    boxes: dict[str, dict[str, Any]] = {}

    def arrange(frame_id: str, x: float, y: float, width: float, height: float) -> None:
        frame, props = frames[frame_id], config[frame_id]
        boxes[frame_id] = {"x": x, "y": y, "w": width, "h": height, "kind": "frame"}
        pad = float(props["padding"])
        pad_x = min(pad, max(0.0, (width - 8.0) / 2))
        pad_y = min(pad, max(0.0, (height - 8.0) / 2))
        ix, iy = x + pad_x, y + pad_y
        iw, ih = max(8.0, width - 2 * pad_x), max(8.0, height - 2 * pad_y)
        row = props["axis"] == "row"
        main_available, cross_available = (iw, ih) if row else (ih, iw)
        ordered = [child for child in props["order"] if child in frame["children"]]
        ordered += [child for child in frame["children"] if child not in ordered]
        if not ordered:
            return
        gap = float(props["gap"])
        lines: list[list[str]] = [[]]
        used = 0.0
        for child in ordered:
            bw, bh = _base(child, frames, items)
            child_main = bw if row else bh
            needed = child_main if not lines[-1] else gap + child_main
            if props["wrap"] == "wrap" and lines[-1] and used + needed > main_available:
                lines.append([]); used = 0.0; needed = child_main
            lines[-1].append(child); used += needed
        line_cross = [max((_base(child, frames, items)[1 if row else 0] for child in line), default=8.0) for line in lines]
        cross_gap = gap if len(lines) > 1 else 0.0
        if len(lines) > 1:
            cross_gap = min(cross_gap, max(0.0, (cross_available - 2.0 * len(lines)) / (len(lines) - 1)))
        cross_space = max(0.001 * len(lines), cross_available - cross_gap * (len(lines) - 1))
        if props["cross"] == "stretch":
            share = cross_space / len(lines)
            line_cross = [share for _line in lines]
        elif sum(line_cross) > cross_space:
            scale = cross_space / sum(line_cross)
            line_cross = [value * scale for value in line_cross]
        total_cross = sum(line_cross) + cross_gap * (len(lines) - 1)
        cross_extra = max(0.0, cross_available - total_cross)
        cross_cursor = 0.0 if props["cross"] in {"start", "stretch"} else cross_extra / 2 if props["cross"] == "center" else cross_extra
        for line_index, line in enumerate(lines):
            bases = [_base(child, frames, items) for child in line]
            main_sizes = [size[0] if row else size[1] for size in bases]
            main_gap = gap if len(line) > 1 else 0.0
            if len(line) > 1:
                main_gap = min(main_gap, max(0.0, (main_available - 2.0 * len(line)) / (len(line) - 1)))
            item_space = max(0.001 * len(line), main_available - main_gap * (len(line) - 1))
            if sum(main_sizes) > item_space:
                scale = item_space / sum(main_sizes)
                main_sizes = [value * scale for value in main_sizes]
            extra = max(0.0, item_space - sum(main_sizes))
            grows = [int(config[child]["grow"]) if child in frames else 0 for child in line]
            grow_total = sum(grows)
            if grow_total:
                main_sizes = [value + extra * grow / grow_total for value, grow in zip(main_sizes, grows)]
                main_cursor = 0.0
            elif props["main"] == "space" and len(line) > 1:
                main_gap += extra / (len(line) - 1)
                main_cursor = 0.0
            else:
                main_cursor = 0.0 if props["main"] in {"start", "space"} else extra / 2 if props["main"] == "center" else extra
            for child, base_size, main_size in zip(line, bases, main_sizes):
                natural_cross = base_size[1] if row else base_size[0]
                cross_size = line_cross[line_index] if props["cross"] == "stretch" else min(natural_cross, line_cross[line_index])
                local_cross = 0.0 if props["cross"] in {"start", "stretch"} else (line_cross[line_index] - cross_size) / 2 if props["cross"] == "center" else line_cross[line_index] - cross_size
                if row:
                    cx, cy, cw, ch = ix + main_cursor, iy + cross_cursor + local_cross, main_size, cross_size
                else:
                    cx, cy, cw, ch = ix + cross_cursor + local_cross, iy + main_cursor, cross_size, main_size
                if child in frames:
                    arrange(child, cx, cy, cw, ch)
                else:
                    boxes[child] = {"x": cx, "y": cy, "w": cw, "h": ch, "kind": items[child]["kind"], "tone": items[child]["tone"]}
                main_cursor += main_size + main_gap
            cross_cursor += line_cross[line_index] + cross_gap

    arrange("window", 0.0, 0.0, 360.0, 260.0)
    return boxes


def _raster(boxes: dict[str, dict[str, Any]], width: int = 120, height: int = 86) -> list[int]:
    pixels = [14] * (width * height)

    def edge(value: float, span: float, size: int, upper: bool) -> int:
        scaled = float(value) / span * size
        nearest = round(scaled)
        if abs(scaled - nearest) < 1e-9:
            scaled = float(nearest)
        return int(math.ceil(scaled) if upper else math.floor(scaled))

    for key, box in sorted(boxes.items(), key=lambda pair: (pair[1]["kind"] != "frame", pair[0])):
        del key
        raw_left = edge(float(box["x"]), 360.0, width, False)
        raw_top = edge(float(box["y"]), 260.0, height, False)
        raw_right = edge(float(box["x"]) + float(box["w"]), 360.0, width, True)
        raw_bottom = edge(float(box["y"]) + float(box["h"]), 260.0, height, True)
        left, top = max(0, min(width, raw_left)), max(0, min(height, raw_top))
        right, bottom = max(0, min(width, raw_right)), max(0, min(height, raw_bottom))
        if right <= left or bottom <= top:
            continue
        if box["kind"] == "frame":
            if 0 <= raw_top < height:
                for px in range(left, right):
                    pixels[raw_top * width + px] = 48
            if 0 < raw_bottom <= height:
                for px in range(left, right):
                    pixels[(raw_bottom - 1) * width + px] = 48
            if 0 <= raw_left < width:
                for py in range(top, bottom):
                    pixels[py * width + raw_left] = 48
            if 0 < raw_right <= width:
                for py in range(top, bottom):
                    pixels[py * width + raw_right - 1] = 48
        else:
            tone = int(box.get("tone", 180))
            for py in range(top, bottom):
                for px in range(left, right):
                    pixels[py * width + px] = tone
    return pixels


def _ssim(left: list[int], right: list[int]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    count = len(left)
    mean_l, mean_r = sum(left) / count, sum(right) / count
    var_l = sum((value - mean_l) ** 2 for value in left) / count
    var_r = sum((value - mean_r) ** 2 for value in right) / count
    covariance = sum((a - mean_l) * (b - mean_r) for a, b in zip(left, right)) / count
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    return ((2 * mean_l * mean_r + c1) * (2 * covariance + c2)) / ((mean_l**2 + mean_r**2 + c1) * (var_l + var_r + c2))


def _gesture(event: dict[str, Any], minimum: float) -> None:
    gesture = event.get("gesture")
    if not isinstance(gesture, dict):
        raise ValueError("direct manipulation lacks pointer geometry")
    for field in ("start_u", "start_v", "end_u", "end_v", "travel_px"):
        value = gesture.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError("direct manipulation has invalid pointer geometry")
    if not all(0 <= float(gesture[field]) <= 1 for field in ("start_u", "start_v", "end_u", "end_v")):
        raise ValueError("direct manipulation left its visible control")
    if float(gesture["travel_px"]) < minimum:
        raise ValueError("direct manipulation did not travel far enough")
    samples = gesture.get("sample_count")
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 1:
        raise ValueError("direct manipulation has no delivered pointer sample")


def _contract(truth: dict[str, Any], public: dict[str, Any]):
    frames, items = truth.get("frames"), truth.get("items")
    initial, target, target_layout = truth.get("initial_config"), truth.get("target_config"), truth.get("target_layout")
    parameters = truth.get("parameters")
    if not all(isinstance(value, expected) for value, expected in ((frames, list), (items, list), (initial, dict), (target, dict), (target_layout, dict), (parameters, dict))):
        raise ValueError("generated layout contract is incomplete")
    if public.get("frames") != frames or public.get("items") != items or public.get("initial_config") != initial or public.get("target_layout") != target_layout:
        raise ValueError("public render state differs from generated truth")
    if public.get("parameters") != parameters or public.get("control_condition") != truth.get("control_condition"):
        raise ValueError("public controls differ from generated truth")
    expected_target = _layout(frames, items, target)
    for node_id, box in target_layout.items():
        if node_id not in expected_target or any(abs(float(box[field]) - float(expected_target[node_id][field])) > 0.001 for field in ("x", "y", "w", "h")):
            raise ValueError("target photograph geometry is inconsistent")
    condition = truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "full")
    if interaction not in {"simplified", "full"}:
        raise ValueError("interaction mode is invalid")
    mutable = public.get("mutable_properties")
    if not isinstance(mutable, list) or not all(prop in {*VALUES, "order"} for prop in mutable):
        raise ValueError("mutable property list is invalid")
    return frames, items, copy.deepcopy(initial), target_layout, parameters, interaction, set(mutable)


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    binding = _bind(payload, truth, public)
    if binding:
        return _fail(binding)
    try:
        frames, items, config, target_layout, parameters, interaction, mutable = _contract(truth, public)
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"invalid reflow contract: {exc}")
    if payload.get("interaction_mode") != interaction:
        return _fail("submitted interaction mode differs from task condition")
    events = payload.get("events")
    if not isinstance(events, list) or len(events) > int(parameters["edit_budget"]):
        return _fail("edit transcript exceeds the visible ledger")
    frames_by_id = {frame["id"]: frame for frame in frames}
    history: list[dict[str, Any]] = []
    try:
        for sequence, event in enumerate(events, 1):
            if not isinstance(event, dict) or event.get("sequence") != sequence:
                raise ValueError(f"event {sequence} has an invalid sequence")
            event_type = event.get("type")
            if event_type == "revert":
                if event.get("input_source") != "revert_button" or not history:
                    raise ValueError(f"event {sequence} has an invalid revert")
                config = history.pop()
                continue
            frame_id, prop = str(event.get("frame_id") or ""), str(event.get("property") or "")
            if frame_id not in frames_by_id or prop not in mutable:
                raise ValueError(f"event {sequence} names an unavailable frame rule")
            history.append(copy.deepcopy(config))
            if event_type == "set" and prop != "order":
                value = event.get("value")
                if value not in VALUES[prop] or value == config[frame_id][prop]:
                    raise ValueError(f"event {sequence} has an invalid or unchanged value")
                expected_source = "value_button" if interaction == "simplified" else "inspector_fader_drag" if prop in {"gap", "padding", "grow"} else "inspector_dropdown"
                if event.get("input_source") != expected_source:
                    raise ValueError(f"event {sequence} uses the wrong input surface")
                if expected_source == "inspector_fader_drag":
                    _gesture(event, 12)
                elif "gesture" in event:
                    raise ValueError(f"event {sequence} adds false pointer proof")
                config[frame_id][prop] = value
            elif event_type == "reorder" and prop == "order":
                order = list(config[frame_id]["order"])
                child_id = str(event.get("child_id") or "")
                source_index, target_index = event.get("from_index"), event.get("to_index")
                if not isinstance(source_index, int) or not isinstance(target_index, int) or source_index == target_index:
                    raise ValueError(f"event {sequence} has invalid order indices")
                if not 0 <= source_index < len(order) or not 0 <= target_index < len(order) or order[source_index] != child_id:
                    raise ValueError(f"event {sequence} disagrees with the current child order")
                expected_source = "order_nudge_button" if interaction == "simplified" else "child_strip_drag"
                if event.get("input_source") != expected_source:
                    raise ValueError(f"event {sequence} uses the wrong input surface")
                if interaction == "full":
                    _gesture(event, 20)
                elif "gesture" in event:
                    raise ValueError(f"event {sequence} adds false drag proof")
                order.insert(target_index, order.pop(source_index))
                config[frame_id]["order"] = order
            else:
                raise ValueError(f"event {sequence} has an invalid edit type")
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"reflow replay rejected: {exc}")
    boxes = _layout(frames, items, config)
    score = _ssim(_raster(target_layout), _raster(boxes))
    submitted_score = payload.get("similarity")
    if isinstance(submitted_score, bool) or not isinstance(submitted_score, (int, float)) or not math.isfinite(float(submitted_score)) or abs(float(submitted_score) - score) > 0.00001:
        return _fail("submitted similarity disagrees with independent raster replay")
    if payload.get("final_config") != config:
        return _fail("submitted frame rules differ from the edit transcript")
    completed = score >= float(parameters["similarity_threshold"])
    if payload.get("completed") is not completed:
        return _fail("submitted completion flag disagrees with the similarity threshold")
    return {
        "graded": True,
        "passed": completed,
        "feedback": f"replayed {len(events)}/{parameters['edit_budget']} edits; grayscale structural similarity {score:.5f} against threshold {float(parameters['similarity_threshold']):.5f}",
    }
