from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "reflow_vitrine"
FRAME_LIBRARY = (
    ("window", "WINDOW CHASSIS", None, 360, 260),
    ("left_bay", "LEFT BAY", "window", 124, 210),
    ("shelf_stack", "SHELF STACK", "window", 188, 210),
    ("top_shelf", "TOP SHELF", "shelf_stack", 164, 76),
    ("bottom_shelf", "BOTTOM SHELF", "shelf_stack", 164, 92),
    ("pedestal", "MANNEQUIN PLINTH", "left_bay", 98, 126),
    ("header_rail", "HANGING RAIL", "window", 220, 48),
)
ITEM_LIBRARY = (
    {"id": "mannequin", "name": "MANNEQUIN", "kind": "mannequin", "parent": "pedestal", "w": 44, "h": 106, "tone": 214, "accent": "#e9bc8a"},
    {"id": "lamp", "name": "ARC LAMP", "kind": "lamp", "parent": "left_bay", "w": 38, "h": 72, "tone": 174, "accent": "#f1c85a"},
    {"id": "postcard", "name": "POSTCARD", "kind": "card", "parent": "top_shelf", "w": 48, "h": 34, "tone": 224, "accent": "#d85f61"},
    {"id": "scarf", "name": "SCARF", "kind": "scarf", "parent": "top_shelf", "w": 64, "h": 30, "tone": 142, "accent": "#5c8bb8"},
    {"id": "vase", "name": "VASE", "kind": "vase", "parent": "bottom_shelf", "w": 36, "h": 56, "tone": 194, "accent": "#75a990"},
    {"id": "shoe", "name": "SHOE", "kind": "shoe", "parent": "bottom_shelf", "w": 58, "h": 28, "tone": 108, "accent": "#7f4a41"},
    {"id": "orb", "name": "GLASS ORB", "kind": "orb", "parent": "header_rail", "w": 34, "h": 34, "tone": 238, "accent": "#9ad8d1"},
    {"id": "banner", "name": "SILK BANNER", "kind": "banner", "parent": "header_rail", "w": 66, "h": 26, "tone": 154, "accent": "#be7db6"},
    {"id": "box", "name": "LACQUER BOX", "kind": "box", "parent": "shelf_stack", "w": 52, "h": 32, "tone": 124, "accent": "#a5793f"},
)
VALUES = {
    "axis": ["row", "column"],
    "main": ["start", "center", "end", "space"],
    "cross": ["start", "center", "end", "stretch"],
    "gap": [4, 8, 12, 16],
    "padding": [4, 8, 12, 16],
    "wrap": ["nowrap", "wrap"],
    "grow": [0, 1, 2],
}
PROPERTY_SETS = {
    "core": ["axis", "main", "gap", "order"],
    "expanded": ["axis", "main", "cross", "gap", "padding", "order"],
    "complete": ["axis", "main", "cross", "gap", "padding", "wrap", "grow", "order"],
}
DEFAULT_PARAMETERS = {
    "frame_count": 6,
    "corruption_count": 4,
    "edit_budget": 11,
    "property_set": "complete",
    "diagnostic_mode": "none",
    "show_frame_guides": False,
    "similarity_threshold": 0.997,
}
MIN_SINGLE_CORRUPTION_PIXELS = 24
MIN_SINGLE_CORRUPTION_SCORE_MARGIN = 0.0015


def _condition(task: dict[str, Any]) -> dict[str, Any] | None:
    value = task.get("_control_condition")
    return copy.deepcopy(value) if isinstance(value, dict) else None


def _parameters(task: dict[str, Any]) -> dict[str, Any]:
    condition = _condition(task)
    return copy.deepcopy(condition["difficulty_parameters"] if condition else DEFAULT_PARAMETERS)


def _validate(parameters: dict[str, Any]) -> None:
    if set(parameters) != set(DEFAULT_PARAMETERS):
        raise ValueError("difficulty parameters do not match the reflow contract")
    for key, low, high in (("frame_count", 3, 7), ("corruption_count", 1, 5), ("edit_budget", 3, 20)):
        value = parameters.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"{key} must be an integer in [{low}, {high}]")
    if parameters["corruption_count"] > parameters["frame_count"] or parameters["edit_budget"] < parameters["corruption_count"]:
        raise ValueError("corruption count and edit budget are inconsistent")
    if parameters.get("property_set") not in PROPERTY_SETS:
        raise ValueError("property_set is invalid")
    if parameters.get("diagnostic_mode") != "none":
        raise ValueError("diagnostic_mode must not expose partial correctness")
    if parameters.get("show_frame_guides") is not False:
        raise ValueError("show_frame_guides must remain disabled")
    threshold = parameters.get("similarity_threshold")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0.99 <= float(threshold) <= 0.999:
        raise ValueError("similarity_threshold must be in [0.99, 0.999]")


def _world_tree(frame_count: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    active_rows = FRAME_LIBRARY[:frame_count]
    active = {row[0] for row in active_rows}
    raw_parent = {row[0]: row[2] for row in FRAME_LIBRARY}

    def nearest(parent: str | None) -> str:
        current = parent
        while current not in active:
            current = raw_parent.get(current)
        return str(current)

    frames = [
        {"id": frame_id, "name": name, "parent": nearest(parent) if parent else None, "base_w": width, "base_h": height, "children": []}
        for frame_id, name, parent, width, height in active_rows
    ]
    by_id = {frame["id"]: frame for frame in frames}
    for frame in frames[1:]:
        by_id[frame["parent"]]["children"].append(frame["id"])
    items = [copy.deepcopy(item) for item in ITEM_LIBRARY[: frame_count + 2]]
    for item in items:
        item["parent"] = nearest(str(item["parent"]))
        by_id[item["parent"]]["children"].append(item["id"])
    return frames, items


def _config(frames: list[dict[str, Any]], rng: random.Random) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, frame in enumerate(frames):
        result[frame["id"]] = {
            "axis": rng.choice(VALUES["axis"]),
            "main": rng.choice(VALUES["main"]),
            "cross": rng.choice(VALUES["cross"]),
            "gap": rng.choice(VALUES["gap"]),
            "padding": rng.choice(VALUES["padding"]),
            "wrap": rng.choice(VALUES["wrap"]),
            "grow": 0 if index == 0 else rng.choice(VALUES["grow"]),
            "order": rng.sample(list(frame["children"]), len(frame["children"])),
        }
    return result


def _base(child_id: str, frames: dict[str, dict[str, Any]], items: dict[str, dict[str, Any]]) -> tuple[float, float]:
    if child_id in frames:
        return float(frames[child_id]["base_w"]), float(frames[child_id]["base_h"])
    item = items[child_id]
    return float(item["w"]), float(item["h"])


def solve_layout(frames_list: list[dict[str, Any]], items_list: list[dict[str, Any]], config: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    frames = {frame["id"]: frame for frame in frames_list}
    items = {item["id"]: item for item in items_list}
    boxes: dict[str, dict[str, Any]] = {}

    def arrange(frame_id: str, x: float, y: float, width: float, height: float) -> None:
        frame = frames[frame_id]
        props = config[frame_id]
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
                lines.append([])
                used = 0.0
                needed = child_main
            lines[-1].append(child)
            used += needed
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


def rasterize(boxes: dict[str, dict[str, Any]], width: int = 120, height: int = 86) -> list[int]:
    pixels = [14] * (width * height)

    def edge(value: float, span: float, size: int, upper: bool) -> int:
        scaled = float(value) / span * size
        nearest = round(scaled)
        if abs(scaled - nearest) < 1e-9:
            scaled = float(nearest)
        return int(math.ceil(scaled) if upper else math.floor(scaled))

    def bounds(box: dict[str, Any]) -> tuple[int, int, int, int, int, int, int, int]:
        raw_left = edge(float(box["x"]), 360.0, width, False)
        raw_top = edge(float(box["y"]), 260.0, height, False)
        raw_right = edge(float(box["x"]) + float(box["w"]), 360.0, width, True)
        raw_bottom = edge(float(box["y"]) + float(box["h"]), 260.0, height, True)
        return (
            raw_left, raw_top, raw_right, raw_bottom,
            max(0, min(width, raw_left)), max(0, min(height, raw_top)),
            max(0, min(width, raw_right)), max(0, min(height, raw_bottom)),
        )

    for _key, box in sorted(boxes.items(), key=lambda pair: (pair[1]["kind"] != "frame", pair[0])):
        raw_left, raw_top, raw_right, raw_bottom, left, top, right, bottom = bounds(box)
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
                offset = py * width
                for px in range(left, right):
                    pixels[offset + px] = tone
    return pixels


def structural_similarity(left: list[int], right: list[int]) -> float:
    """Use the exact global structural-similarity statistic used by the grader."""
    if len(left) != len(right) or not left:
        return 0.0
    count = len(left)
    mean_l, mean_r = sum(left) / count, sum(right) / count
    var_l = sum((value - mean_l) ** 2 for value in left) / count
    var_r = sum((value - mean_r) ** 2 for value in right) / count
    covariance = sum((a - mean_l) * (b - mean_r) for a, b in zip(left, right)) / count
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    return ((2 * mean_l * mean_r + c1) * (2 * covariance + c2)) / (
        (mean_l * mean_l + mean_r * mean_r + c1) * (var_l + var_r + c2)
    )


def _alternative(prop: str, value: Any, rng: random.Random) -> Any:
    choices = [copy.deepcopy(item) for item in VALUES[prop] if item != value]
    return rng.choice(choices)


def _visible_pixel_difference(left: list[int], right: list[int]) -> int:
    return sum(abs(a - b) >= 8 for a, b in zip(left, right))


def _boxes_are_contained(boxes: dict[str, dict[str, Any]]) -> bool:
    tolerance = 0.001
    return all(
        float(box["x"]) >= -tolerance
        and float(box["y"]) >= -tolerance
        and float(box["x"]) + float(box["w"]) <= 360.0 + tolerance
        and float(box["y"]) + float(box["h"]) <= 260.0 + tolerance
        and float(box["w"]) > 0
        and float(box["h"]) > 0
        for box in boxes.values()
    )


def _construct(parameters: dict[str, Any], stable: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any], float]:
    frames, items = _world_tree(parameters["frame_count"])
    mutable = PROPERTY_SETS[parameters["property_set"]]
    threshold = float(parameters["similarity_threshold"])
    for attempt in range(160):
        rng = random.Random(int(hashlib.sha256(f"{stable}:{attempt}".encode()).hexdigest()[:16], 16))
        target = _config(frames, rng)
        target_boxes = solve_layout(frames, items, target)
        if not _boxes_are_contained(target_boxes):
            continue
        target_raster = rasterize(target_boxes)
        current = copy.deepcopy(target)
        selected: list[dict[str, Any]] = []
        used_keys: set[tuple[str, str]] = set()
        used_frames: set[str] = set()
        current_score = 1.0
        for step in range(parameters["corruption_count"]):
            candidates = []
            for frame in frames:
                frame_id = frame["id"]
                for prop in mutable:
                    if (frame_id, prop) in used_keys or (prop == "grow" and frame_id == "window"):
                        continue
                    candidate = copy.deepcopy(current)
                    if prop == "order":
                        order = list(candidate[frame_id]["order"])
                        if len(order) < 2:
                            continue
                        swap = rng.randrange(len(order) - 1)
                        order[swap], order[swap + 1] = order[swap + 1], order[swap]
                        candidate[frame_id]["order"] = order
                        new_value: Any = order
                    else:
                        new_value = _alternative(prop, candidate[frame_id][prop], rng)
                        candidate[frame_id][prop] = new_value
                    single = copy.deepcopy(target)
                    single[frame_id][prop] = copy.deepcopy(new_value)
                    single_boxes = solve_layout(frames, items, single)
                    single_raster = rasterize(single_boxes)
                    single_score = structural_similarity(target_raster, single_raster)
                    visible_pixels = _visible_pixel_difference(target_raster, single_raster)
                    if (
                        not _boxes_are_contained(single_boxes)
                        or single_score >= threshold - MIN_SINGLE_CORRUPTION_SCORE_MARGIN
                        or visible_pixels < MIN_SINGLE_CORRUPTION_PIXELS
                    ):
                        continue
                    score = structural_similarity(target_raster, rasterize(solve_layout(frames, items, candidate)))
                    if score < current_score - 0.0004:
                        candidates.append((score, frame_id in used_frames, rng.random(), frame_id, prop, new_value, candidate, single_score, visible_pixels))
            if not candidates:
                break
            need_new_frame = len(used_frames) < min(parameters["corruption_count"] - 1, len(frames))
            pool = [candidate for candidate in candidates if not candidate[1]] if need_new_frame and any(not candidate[1] for candidate in candidates) else candidates
            pool.sort(key=lambda candidate: (candidate[0], candidate[2]))
            choice = pool[min(len(pool) - 1, rng.randrange(min(4, len(pool))))]
            current_score, _reused, _jitter, frame_id, prop, new_value, current, single_score, visible_pixels = choice
            used_keys.add((frame_id, prop))
            used_frames.add(frame_id)
            selected.append({
                "frame_id": frame_id,
                "property": prop,
                "target": copy.deepcopy(target[frame_id][prop]),
                "initial": copy.deepcopy(new_value),
                "single_error_similarity": round(single_score, 8),
                "visible_pixel_difference": visible_pixels,
            })
        minimum_distinct_frames = min(parameters["corruption_count"] - 1, len(frames))
        if len(selected) == parameters["corruption_count"] and len(used_frames) >= minimum_distinct_frames and current_score < threshold - 0.004:
            initial_boxes = solve_layout(frames, items, current)
            if _boxes_are_contained(initial_boxes):
                return frames, items, target, current, selected, target_boxes, current_score
    raise RuntimeError("could not construct a sufficiently visible reflow corruption set")


def generate(task: dict[str, Any], seed: str):
    parameters = _parameters(task)
    _validate(parameters)
    stable = hashlib.sha256(f"{MECHANIC_ID}:{seed}:{parameters}".encode("utf-8")).hexdigest()
    frames, items, target, initial, corruptions, target_boxes, initial_score = _construct(parameters, stable)
    task_id = str(task.get("id") or "reflow_vitrine")
    challenge_id = f"rv-{stable[:18]}"
    condition = _condition(task)
    public_state = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": "Restore the target window.",
        "frames": copy.deepcopy(frames),
        "items": copy.deepcopy(items),
        "initial_config": copy.deepcopy(initial),
        "target_layout": copy.deepcopy(target_boxes),
        "parameters": copy.deepcopy(parameters),
        "mutable_properties": copy.deepcopy(PROPERTY_SETS[parameters["property_set"]]),
        "allowed_values": copy.deepcopy(VALUES),
        "visual_seed": int(stable[18:26], 16),
        "status": "ready",
        "asset_manifest": str((task.get("metadata") or {}).get("asset_manifest") or "shared_runtime/assets/provenance/reflow_vitrine_v0.json"),
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "frames": copy.deepcopy(frames),
        "items": copy.deepcopy(items),
        "initial_config": copy.deepcopy(initial),
        "target_config": copy.deepcopy(target),
        "target_layout": copy.deepcopy(target_boxes),
        "corruptions": copy.deepcopy(corruptions),
        "parameters": copy.deepcopy(parameters),
        "initial_similarity": round(initial_score, 8),
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
