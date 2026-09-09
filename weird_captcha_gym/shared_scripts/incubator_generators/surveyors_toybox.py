from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "surveyors_toybox"
VIEWS = ("overhead", "front", "side")
AXIS = {"x": 0, "y": 1, "z": 2}


def _seed(seed: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode()).digest()[:8], "big")


def _rotate_xz(center: list[float], half: list[float], yaw: float) -> list[list[float]]:
    angle = math.radians(yaw)
    cosine, sine = math.cos(angle), math.sin(angle)
    corners: list[list[float]] = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                lx, lz = sx * half[0], sz * half[2]
                corners.append([
                    center[0] + lx * cosine - lz * sine,
                    center[1] + sy * half[1],
                    center[2] + lx * sine + lz * cosine,
                ])
    return corners


def _project(view: dict[str, Any], point: list[float], bias: list[float] | None = None) -> list[float]:
    bias = bias or [0.0, 0.0]
    return [
        round(
            float(view["origin"][row])
            + float(bias[row])
            + float(view["scale"]) * float(view["signs"][row]) * float(point[AXIS[view["axes"][row]]]),
            4,
        )
        for row in range(2)
    ]


def _mark_rect(view: dict[str, Any], obj: dict[str, Any], bias: list[float]) -> dict[str, float]:
    screens = [_project(view, corner, bias) for corner in _rotate_xz(obj["center"], obj["half"], obj["yaw"])]
    xs, ys = [point[0] for point in screens], [point[1] for point in screens]
    return {
        "x": round(min(xs) - 3.0, 3),
        "y": round(min(ys) - 3.0, 3),
        "w": round(max(xs) - min(xs) + 6.0, 3),
        "h": round(max(ys) - min(ys) + 6.0, 3),
    }


def _scene_subject(view: dict[str, Any], obj: dict[str, Any], bias: list[float], style_index: int) -> dict[str, Any]:
    """Return an unlabeled 2D camera subject for the visible image plate.

    The object identity is deliberately omitted.  The browser uses these
    shapes as the underlying depot image, while the separately shuffled mark
    rectangles are neutral annotation overlays.  A solver must match the
    requested scan cluster to the subject's projected shape and location.
    """
    projected = [_project(view, corner, bias) for corner in _rotate_xz(obj["center"], obj["half"], obj["yaw"])]
    xs, ys = [point[0] for point in projected], [point[1] for point in projected]
    styles = ("cargo", "van", "drum", "pallet", "rover")
    tones = ("#6b8179", "#7b8d87", "#647b86", "#8b806c", "#718079")
    accents = ("#d1b27b", "#b9c9bb", "#d18f70", "#c8b88d", "#9bb9ad")
    return {
        "rect": {
            "x": round(min(xs), 3), "y": round(min(ys), 3),
            "w": round(max(xs) - min(xs), 3), "h": round(max(ys) - min(ys), 3),
        },
        "style": styles[style_index % len(styles)],
        "tone": tones[style_index % len(tones)],
        "accent": accents[style_index % len(accents)],
        "yaw_hint": round(math.sin(math.radians(obj["yaw"])), 3),
    }


def _sample_points(rng: random.Random, obj: dict[str, Any], density: int, palette: str) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    angle = math.radians(obj["yaw"])
    cosine, sine = math.cos(angle), math.sin(angle)
    count = max(8, int(density))
    for index in range(count):
        face = index % 6
        u = ((index * 37 + 11) % 101) / 100.0 * 2.0 - 1.0
        v = ((index * 61 + 23) % 97) / 96.0 * 2.0 - 1.0
        if face == 0:
            local = [obj["half"][0], u * obj["half"][1], v * obj["half"][2]]
        elif face == 1:
            local = [-obj["half"][0], u * obj["half"][1], v * obj["half"][2]]
        elif face == 2:
            local = [u * obj["half"][0], obj["half"][1], v * obj["half"][2]]
        elif face == 3:
            local = [u * obj["half"][0], -obj["half"][1], v * obj["half"][2]]
        elif face == 4:
            local = [u * obj["half"][0], v * obj["half"][1], obj["half"][2]]
        else:
            local = [u * obj["half"][0], v * obj["half"][1], -obj["half"][2]]
        point = [
            obj["center"][0] + local[0] * cosine - local[2] * sine,
            obj["center"][1] + local[1],
            obj["center"][2] + local[0] * sine + local[2] * cosine,
        ]
        points.append({"x": round(point[0], 3), "y": round(point[1], 3), "z": round(point[2], 3), "color": palette})
    return points


def _profile(condition: dict[str, Any] | None) -> tuple[int, dict[str, Any]]:
    if condition is None:
        return 4, {}
    try:
        level = int(condition.get("difficulty"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Surveyor's Toybox difficulty must be 1 through 5") from exc
    if level not in {1, 2, 3, 4, 5}:
        raise ValueError("Surveyor's Toybox difficulty must be 1 through 5")
    return level, dict(condition.get("difficulty_parameters") or {})


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = task.get("_control_condition")
    level, parameters = _profile(condition)
    interaction = str((condition or {}).get("interaction") or "full")
    if interaction not in {"simplified", "full"}:
        raise ValueError("Surveyor's Toybox interaction must be simplified or full")

    defaults = {
        "target_count": 3,
        "distractor_count": 4,
        "frame_count": 2,
        "point_density": 18,
        "fit_tolerance": 0.16,
        "yaw_tolerance": 8.0,
        "initial_error": 0.30,
    }
    values = {**defaults, **parameters} if level != 4 else defaults
    target_count = int(values["target_count"])
    distractor_count = int(values["distractor_count"])
    frame_count = int(values["frame_count"])
    point_density = int(values["point_density"])
    fit_tolerance = float(values["fit_tolerance"])
    yaw_tolerance = float(values["yaw_tolerance"])
    initial_error = float(values["initial_error"])
    if not 1 <= target_count <= 4 or not 0 <= distractor_count <= 6:
        raise ValueError("Surveyor's Toybox object counts are outside the supported range")
    if target_count + distractor_count > 10 or not 1 <= frame_count <= 3:
        raise ValueError("Surveyor's Toybox frames or object count are invalid")
    if not 10 <= point_density <= 36 or not 0.09 <= fit_tolerance <= 0.30:
        raise ValueError("Surveyor's Toybox point density or fit tolerance is invalid")
    if not 4 <= yaw_tolerance <= 18 or not 0.08 <= initial_error <= 0.5:
        raise ValueError("Surveyor's Toybox heading or starting error is invalid")

    rng = random.Random(_seed(seed))
    palettes = [
        {"paper": "#e9e4d5", "ink": "#15242b", "cloud": "#77e7d0", "accent": "#ffbd63", "line": "#92a69a"},
        {"paper": "#e7edf0", "ink": "#142b36", "cloud": "#7fd0f0", "accent": "#ff8f70", "line": "#9aaeb9"},
        {"paper": "#efe7db", "ink": "#272331", "cloud": "#b3df78", "accent": "#f487b5", "line": "#b5a997"},
    ]
    palette = rng.choice(palettes)
    appearances = [
        ("amber tug", "#ee9d3e", "▰"),
        ("teal crate", "#49c5ad", "◆"),
        ("coral rover", "#f36d70", "✦"),
        ("violet cart", "#9c7ed6", "⬟"),
        ("mint drum", "#79cfa1", "●"),
        ("cobalt pod", "#628fca", "▲"),
        ("rose pallet", "#d777a9", "▣"),
        ("ochre case", "#c8a24e", "◇"),
        ("indigo bin", "#6470b9", "▰"),
        ("lime dolly", "#a4cf58", "◆"),
    ]
    positions = [
        [-2.65, 1.15, -1.65], [-1.0, 1.55, 1.75], [1.55, 1.0, -1.55],
        [2.55, 1.85, 1.15], [-2.4, 2.4, 1.5], [0.15, 1.2, 0.1],
        [2.0, 2.55, -0.15], [-0.15, 2.9, 2.0], [-3.1, 2.85, 0.0],
        [0.8, 1.85, -2.15],
    ]
    rng.shuffle(positions)
    total = target_count + distractor_count
    objects: list[dict[str, Any]] = []
    for index in range(total):
        label, color, glyph = appearances[index]
        base = positions[index]
        center = [round(base[0] + rng.uniform(-0.13, 0.13), 3), round(base[1] + rng.uniform(-0.1, 0.1), 3), round(base[2] + rng.uniform(-0.13, 0.13), 3)]
        half = [round(rng.uniform(0.30, 0.52), 3), round(rng.uniform(0.24, 0.42), 3), round(rng.uniform(0.32, 0.56), 3)]
        yaw = round(rng.choice((-38, -24, -12, 14, 27, 41)) + rng.uniform(-3, 3), 2)
        objects.append({
            "id": f"crate-{index + 1}", "center": center, "half": half, "yaw": yaw,
            "label": label, "color": color, "glyph": glyph, "target": index < target_count,
        })

    views = {
        "overhead": {"axes": ["x", "z"], "signs": [1, 1], "origin": [170, 113], "scale": 28, "label": "OVERHEAD / XZ"},
        "front": {"axes": ["x", "y"], "signs": [1, -1], "origin": [170, 170], "scale": 28, "label": "FRONT / XY"},
        "side": {"axes": ["z", "y"], "signs": [1, -1], "origin": [170, 170], "scale": 28, "label": "SIDE / ZY"},
    }
    camera_frames: list[dict[str, Any]] = []
    expected_links: dict[str, str] = {}
    for frame in range(frame_count):
        bias = [round((frame - (frame_count - 1) / 2) * 5.0, 3), round((frame - (frame_count - 1) / 2) * -2.5, 3)]
        frame_views: dict[str, Any] = {}
        for view_id in VIEWS:
            shuffled = list(objects)
            rng.shuffle(shuffled)
            marks = []
            scene_objects = [_scene_subject(views[view_id], obj, bias, index) for index, obj in enumerate(objects)]
            for slot, obj in enumerate(shuffled):
                mark_id = f"photo-{frame + 1}-{view_id[:2]}-{slot + 1}"
                mark = {
                    "id": mark_id, "color": "#ed815e", "glyph": str(slot + 1),
                    "rect": _mark_rect(views[view_id], obj, bias),
                }
                marks.append(mark)
                if obj["target"]:
                    expected_links[f"{frame}:{view_id}:{obj['id']}"] = mark_id
            frame_views[view_id] = {
                "label": views[view_id]["label"], "marks": marks, "bias": bias,
                "scene_objects": scene_objects,
            }
        camera_frames.append({"frame_index": frame, "label": f"SYNC FRAME {frame + 1}", "views": frame_views})

    point_cloud: list[dict[str, Any]] = []
    for obj in objects:
        point_cloud.extend(_sample_points(rng, obj, point_density, obj["color"]))
    noise_count = max(5, total * 2)
    for _ in range(noise_count):
        point_cloud.append({"x": round(rng.uniform(-3.75, 3.75), 3), "y": round(rng.uniform(0.55, 3.95), 3), "z": round(rng.uniform(-2.75, 2.75), 3), "color": palette["line"]})

    target_ids = [obj["id"] for obj in objects if obj["target"]]
    initial_annotations: dict[str, Any] = {}
    for index, obj in enumerate(objects[:target_count]):
        direction = (-1 if index % 2 else 1)
        initial_annotations[obj["id"]] = {
            "center": [round(obj["center"][0] + direction * initial_error, 3), round(obj["center"][1] - initial_error * 0.65, 3), round(obj["center"][2] + initial_error * 0.8, 3)],
            "half": [round(max(0.18, obj["half"][0] + direction * initial_error * 0.45), 3), round(max(0.18, obj["half"][1] - initial_error * 0.35), 3), round(max(0.18, obj["half"][2] + initial_error * 0.3), 3)],
            "yaw": round(obj["yaw"] + direction * initial_error * 38, 2),
        }

    task_id = str(task.get("id") or "surveyors_toybox_seed_0001@0.1")
    condition_token = f"|d{level}" if condition is not None else ""
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}{condition_token}".encode()).hexdigest()[:12]
    requirements = {
        "max_events": 1800, "fit_tolerance": fit_tolerance, "yaw_tolerance": yaw_tolerance,
        "target_count": target_count, "frame_count": frame_count, "required_views": list(VIEWS),
        "required_links": target_count * frame_count * len(VIEWS),
    }
    public = {
        "benchmark": "weird_captcha_gym", "mechanic_id": MECHANIC_ID, "task_id": task_id, "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Fit the requested 3D cuboids and link each synchronized photograph mark to its scan object.",
        "submit_label": "CERTIFY SURVEY", "palette": palette, "targets": [{"id": obj["id"], "label": obj["label"], "color": obj["color"], "glyph": obj["glyph"]} for obj in objects[:target_count]],
        "point_cloud": point_cloud, "views": views, "camera_frames": camera_frames, "initial_annotations": initial_annotations,
        "world": {"bounds": {"x": [-4, 4], "y": [0, 4.5], "z": [-3, 3]}, "point_radius": 3},
        "requirements": requirements,
        "generator": {"name": "toy_depot_cross_modal_cuboid_v1", "variant_count": 10 * 6 * 3 * 3 * 10_000,
                       "variant_count_kind": "10 seeded object arrangements × six headings × three palettes × three frame counts × bounded point perturbations"},
        "asset_manifest": "shared_runtime/assets/provenance/surveyors_toybox_v0.json",
        "render_boundary": "The browser receives the scan points, visible synchronized camera scenes, neutral camera marks and calibration needed to render the task. It does not receive target box truth or the image-to-object correspondence map; the server independently replays box edits and link events.",
    }
    truth = {
        **public, "seed": seed, "target_ids": target_ids,
        "objects": objects, "target_boxes": {obj["id"]: {"center": obj["center"], "half": obj["half"], "yaw": obj["yaw"]} for obj in objects[:target_count]},
        "expected_links": expected_links, "interaction_mode": interaction,
        "initial_annotations": copy.deepcopy(initial_annotations),
    }
    if condition is not None:
        public["control_condition"] = copy.deepcopy(condition)
        truth["control_condition"] = copy.deepcopy(condition)
    return public, truth
