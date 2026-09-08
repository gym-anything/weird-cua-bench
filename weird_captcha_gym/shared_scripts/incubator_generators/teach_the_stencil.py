from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "teach_the_stencil"


PROFILES: dict[int, dict[str, Any]] = {
    1: {
        "width": 52,
        "height": 34,
        "class_names": ["paper", "leaf", "petal"],
        "noise": 0.06,
        "threshold": 0.72,
        "minimum_updates": 1,
        "minimum_corrections": 0,
        "required_samples_per_class": 1,
        "sample_budget": 36,
    },
    # This is the exact effective configuration of the original uncontrolled
    # seed.  The original seed is assigned to L2 so its generated world is not
    # changed merely to support a preferred baseline label.  generator_level
    # preserves the old feature-generation branch while the public difficulty
    # assignment moves to L2.
    2: {
        "width": 72,
        "height": 46,
        "class_names": ["paper", "leaf", "stem", "petal", "vein"],
        "noise": 0.13,
        "threshold": 0.82,
        "minimum_updates": 1,
        "minimum_corrections": 0,
        "required_samples_per_class": 2,
        "sample_budget": 72,
        "generator_level": 3,
    },
    3: {
        "width": 84,
        "height": 54,
        "class_names": ["paper", "leaf", "stem", "petal", "vein", "shadow"],
        "noise": 0.17,
        "threshold": 0.84,
        "minimum_updates": 1,
        "minimum_corrections": 0,
        "required_samples_per_class": 3,
        "sample_budget": 96,
        "requires_consequential_corrections": False,
    },
    4: {
        "width": 96,
        "height": 62,
        "class_names": ["paper", "leaf", "stem", "petal", "vein", "shadow"],
        "noise": 0.21,
        "threshold": 0.86,
        "minimum_updates": 1,
        "minimum_corrections": 0,
        "required_samples_per_class": 5,
        "sample_budget": 120,
        "requires_consequential_corrections": False,
    },
    5: {
        "width": 108,
        "height": 70,
        "class_names": ["paper", "leaf", "stem", "petal", "vein", "shadow"],
        "noise": 0.24,
        "threshold": 0.86,
        "minimum_updates": 1,
        "minimum_corrections": 0,
        "required_samples_per_class": 5,
        "sample_budget": 144,
        "requires_consequential_corrections": False,
    },
}


MATERIALS: dict[str, dict[str, Any]] = {
    "paper": {"color": (222, 211, 183), "texture": 0.22, "swatch": "#ead8ae", "description": "warm plate"},
    "leaf": {"color": (64, 119, 72), "texture": 0.66, "swatch": "#6fbf78", "description": "leaf tissue"},
    "stem": {"color": (101, 83, 55), "texture": 0.50, "swatch": "#b48555", "description": "stem and branch"},
    "petal": {"color": (190, 92, 126), "texture": 0.80, "swatch": "#ee8eb0", "description": "flower petal"},
    "vein": {"color": (190, 157, 52), "texture": 0.91, "swatch": "#f1c963", "description": "fine vein"},
    "shadow": {"color": (84, 70, 88), "texture": 0.35, "swatch": "#9b8ba9", "description": "cast shadow"},
}


def _seed_int(seed: str) -> int:
    return int(hashlib.sha256(f"{seed}|teach-the-stencil".encode("utf-8")).hexdigest()[:16], 16)


def _profile(task: dict[str, Any]) -> tuple[int, dict[str, Any], dict[str, Any] | None]:
    condition = copy.deepcopy((task.get("_control_condition") or (task.get("metadata") or {}).get("control_condition")) or None)
    level = int((condition or {}).get("difficulty") or 2)
    if level not in PROFILES:
        level = 3
    profile = copy.deepcopy(PROFILES[level])
    supplied = (condition or {}).get("difficulty_parameters") or {}
    # Controlled task metadata is authoritative, while retaining a safe default
    # for the original unmaterialized seed task.
    for key in profile:
        if key in supplied:
            profile[key] = copy.deepcopy(supplied[key])
    return level, profile, condition


def _ellipse(mask: list[int], width: int, height: int, cx: float, cy: float, rx: float, ry: float, angle: float, label: int) -> None:
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    left = max(0, int(cx - rx - 2))
    right = min(width - 1, int(cx + rx + 2))
    top = max(0, int(cy - ry - 2))
    bottom = min(height - 1, int(cy + ry + 2))
    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            dx, dy = x - cx, y - cy
            local_x = dx * cos_a + dy * sin_a
            local_y = -dx * sin_a + dy * cos_a
            if (local_x / max(rx, 1e-6)) ** 2 + (local_y / max(ry, 1e-6)) ** 2 <= 1.0:
                mask[y * width + x] = label


def _line(mask: list[int], width: int, height: int, x1: float, y1: float, x2: float, y2: float, thickness: float, label: int) -> None:
    distance = max(1.0, math.hypot(x2 - x1, y2 - y1))
    steps = int(distance * 1.8)
    for step in range(steps + 1):
        t = step / max(1, steps)
        _ellipse(mask, width, height, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, thickness, thickness, 0.0, label)


def _draw_plate(width: int, height: int, names: list[str], rng: random.Random) -> list[int]:
    mask = [0] * (width * height)
    index = {name: names.index(name) for name in names}
    paper = index["paper"]
    # A shallow plate rim leaves a clear visual field around the botanical study.
    _ellipse(mask, width, height, width * 0.50, height * 0.53, width * 0.47, height * 0.46, 0.0, paper)

    def paint(name: str, *args: float) -> None:
        if name not in index:
            return
        if len(args) == 5:
            _ellipse(mask, width, height, *args, index[name])

    center_x = width * (0.49 + rng.uniform(-0.04, 0.04))
    base_y = height * 0.83
    top_y = height * 0.20
    if "shadow" in index:
        for _ in range(3 + (width // 40)):
            paint("shadow", rng.uniform(width * 0.20, width * 0.80), rng.uniform(height * 0.42, height * 0.78), rng.uniform(width * 0.09, width * 0.18), rng.uniform(height * 0.025, height * 0.055), rng.uniform(-0.4, 0.4))

    # Main stem and asymmetrical branches.
    if "stem" in index:
        _line(mask, width, height, center_x, base_y, center_x + rng.uniform(-3, 3), top_y, 3.2, index["stem"])
        branches = [
            (center_x, height * 0.61, center_x - width * 0.22, height * 0.39),
            (center_x + 1, height * 0.53, center_x + width * 0.22, height * 0.31),
            (center_x - 1, height * 0.40, center_x - width * 0.15, height * 0.23),
        ]
        for x1, y1, x2, y2 in branches:
            _line(mask, width, height, x1, y1, x2, y2, 1.8, index["stem"])

    leaf_points = [
        (center_x - width * 0.20, height * 0.47, width * 0.13, height * 0.075, -0.48),
        (center_x + width * 0.19, height * 0.38, width * 0.14, height * 0.08, 0.48),
        (center_x - width * 0.14, height * 0.28, width * 0.12, height * 0.07, -0.25),
        (center_x + width * 0.10, height * 0.20, width * 0.105, height * 0.064, 0.55),
        (center_x + width * 0.27, height * 0.57, width * 0.12, height * 0.07, 0.26),
    ]
    for cx, cy, rx, ry, angle in leaf_points:
        paint("leaf", cx, cy, rx, ry, angle)
        if "vein" in index:
            _line(mask, width, height, cx - math.cos(angle) * rx * 0.9, cy - math.sin(angle) * rx * 0.9, cx + math.cos(angle) * rx * 0.9, cy + math.sin(angle) * rx * 0.9, 0.75, index["vein"])

    # Two flowers use repeated petal geometry so the image remains legible at
    # every raster size while retaining seed-specific placement.
    flower_centers = [(center_x - width * 0.23, height * 0.22), (center_x + width * 0.25, height * 0.30)]
    if "petal" in index:
        for fx, fy in flower_centers:
            radius = min(width, height) * 0.075
            for petal_index in range(5):
                angle = petal_index * (math.tau / 5.0) + rng.uniform(-0.08, 0.08)
                px = fx + math.cos(angle) * radius * 0.72
                py = fy + math.sin(angle) * radius * 0.72
                paint("petal", px, py, radius * 0.62, radius * 0.36, angle)
            if "vein" in index:
                _ellipse(mask, width, height, fx, fy, radius * 0.27, radius * 0.27, 0.0, index["vein"])

    # Veins stay visible over leaves; a few intentionally cross a similar-color
    # region at harder levels so corrective labels have a global consequence.
    if "vein" in index:
        for cx, cy, rx, ry, angle in leaf_points:
            for side in (-0.35, 0.0, 0.35):
                dx = math.cos(angle + side) * rx * 0.55
                dy = math.sin(angle + side) * ry * 0.55
                _line(mask, width, height, cx, cy, cx + dx, cy + dy, 0.45, index["vein"])

    # Restore a few paper flecks as visible negative space inside the plate.
    for _ in range(3 + len(names)):
        _ellipse(mask, width, height, rng.uniform(width * 0.16, width * 0.84), rng.uniform(height * 0.14, height * 0.85), rng.uniform(0.7, 1.6), rng.uniform(0.5, 1.2), rng.uniform(-1, 1), paper)
    return mask


def _pixel_features(mask: list[int], width: int, height: int, names: list[str], level: int, seed_int: int, noise: float) -> list[list[float]]:
    result: list[list[float]] = []
    for index, label in enumerate(mask):
        name = names[label]
        base_r, base_g, base_b = MATERIALS[name]["color"]
        x, y = index % width, index // width
        n1 = math.sin((x + 1) * 0.91 + (y + 3) * 0.37 + seed_int * 0.000001)
        n2 = math.sin((x + 5) * 0.17 - (y + 1) * 1.11 + seed_int * 0.0000007)
        cluster = math.sin((x * 0.23 + y * 0.31) + label * 1.7 + seed_int * 0.0000003)
        amplitude = 255 * noise * (0.42 + 0.28 * abs(cluster))
        # Harder levels pull nearby material colors toward one another, making a
        # single lucky scribble less representative of the whole material.
        mix = max(0.0, level - 2) * 0.025
        neutral = (base_r + base_g + base_b) / 3.0
        r = base_r * (1 - mix) + neutral * mix + n1 * amplitude
        g = base_g * (1 - mix) + neutral * mix + n2 * amplitude
        b = base_b * (1 - mix) + neutral * mix + (n1 - n2) * amplitude * 0.65
        texture = float(MATERIALS[name]["texture"]) + cluster * noise * 0.23 + n2 * noise * 0.08
        result.append([round(max(0.0, min(255.0, r)), 2), round(max(0.0, min(255.0, g)), 2), round(max(0.0, min(255.0, b)), 2), round(max(0.0, min(1.0, texture)), 4)])
    return result


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    level, profile, condition = _profile(task)
    rng = random.Random(_seed_int(seed))
    width, height = int(profile["width"]), int(profile["height"])
    names = list(profile["class_names"])
    mask = _draw_plate(width, height, names, rng)
    feature_level = int(profile.get("generator_level") or level)
    features = _pixel_features(mask, width, height, names, feature_level, _seed_int(seed), float(profile["noise"]))
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|d{level}".encode("utf-8")).hexdigest()[:16]
    world_fingerprint = hashlib.sha256(repr((width, height, names, features)).encode("utf-8")).hexdigest()[:16]
    classes = [
        {
            "id": index,
            "name": name.title(),
            "key": name,
            "swatch": MATERIALS[name]["swatch"],
            "description": MATERIALS[name]["description"],
        }
        for index, name in enumerate(names)
    ]
    public_state: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task.get("id"),
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Teach the visible materials and certify the plate.",
        "submit_label": "CERTIFY MASK",
        "generator": {"name": "teach_the_stencil_botanical_plate_v1", "variant_count": 250000},
        "plate": {"width": width, "height": height, "pixels": features, "world_fingerprint": world_fingerprint},
        "classes": classes,
        "tools": {"brush_sizes": [1, 2, 3, 4, 5], "default_brush_size": 1},
        "classifier": {"name": "local-nearest-centroid", "feature_channels": ["red", "green", "blue", "surface texture"], "live_update": True},
        "control_condition": copy.deepcopy(condition) if condition else {"difficulty": level, "interaction": "simplified", "real_time": "live", "difficulty_parameters": copy.deepcopy(profile)},
        "asset_manifest": "shared_runtime/assets/provenance/teach_the_stencil_xcog_257_v0.json",
    }
    ground_truth: dict[str, Any] = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task.get("id"),
        "seed": seed,
        "challenge_id": challenge_id,
        "world_fingerprint": world_fingerprint,
        "width": width,
        "height": height,
        "class_names": names,
        "target_labels": mask,
        "target_features": features,
        "threshold": float(profile["threshold"]),
        "minimum_updates": int(profile["minimum_updates"]),
        "minimum_corrections": int(profile["minimum_corrections"]),
        "requires_consequential_corrections": bool(profile.get("requires_consequential_corrections", False)),
        "required_samples_per_class": int(profile["required_samples_per_class"]),
        "sample_budget": int(profile["sample_budget"]),
        "control_condition": copy.deepcopy(condition) if condition else {"difficulty": level, "interaction": "simplified", "real_time": "live", "difficulty_parameters": copy.deepcopy(profile)},
    }
    return public_state, ground_truth
