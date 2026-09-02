from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any, Callable


MECHANIC_ID = "reveal_to_identify"
STAGE = {"width": 900, "height": 500}
VARIANT_COUNT = 18_400_000_000


def _seed(seed: str) -> int:
    return int(hashlib.sha256(f"{seed}|{MECHANIC_ID}|darkroom-v1".encode()).hexdigest()[:16], 16)


def _line(x1: float, y1: float, x2: float, y2: float, width: float = 8, stroke: str = "ink") -> dict[str, Any]:
    return {"kind": "line", "points": [x1, y1, x2, y2], "width": width, "stroke": stroke}


def _ellipse(cx: float, cy: float, rx: float, ry: float, fill: str = "body", stroke: str = "ink", width: float = 7) -> dict[str, Any]:
    return {"kind": "ellipse", "cx": cx, "cy": cy, "rx": rx, "ry": ry, "fill": fill, "stroke": stroke, "width": width}


def _rect(x: float, y: float, width: float, height: float, radius: float = 0, fill: str = "body", stroke: str = "ink", line_width: float = 7) -> dict[str, Any]:
    return {"kind": "rect", "x": x, "y": y, "width": width, "height": height, "radius": radius, "fill": fill, "stroke": stroke, "line_width": line_width}


def _poly(points: list[list[float]], fill: str = "body", stroke: str = "ink", width: float = 7) -> dict[str, Any]:
    return {"kind": "poly", "points": points, "fill": fill, "stroke": stroke, "width": width}


def _arc(cx: float, cy: float, radius: float, start: float, end: float, width: float = 9, stroke: str = "ink") -> dict[str, Any]:
    return {"kind": "arc", "cx": cx, "cy": cy, "radius": radius, "start": start, "end": end, "width": width, "stroke": stroke}


def _bicycle(_rng: random.Random) -> tuple[list[dict[str, Any]], list[list[float]]]:
    parts = [
        _ellipse(-165, 86, 82, 82, "none", "ink", 11), _ellipse(155, 86, 82, 82, "none", "ink", 11),
        _line(-165, 86, -62, 82, 11), _line(-62, 82, 18, -38, 11), _line(18, -38, 73, 85, 11),
        _line(73, 85, -62, 82, 11), _line(-62, 82, -10, -17, 11), _line(-10, -17, 18, -38, 10),
        _line(73, 85, 115, -55, 11), _line(115, -55, 155, 86, 11), _line(102, -58, 139, -68, 9),
        _line(-35, -22, -2, -22, 10), _ellipse(-61, 83, 18, 18, "accent", "ink", 5),
        _line(-61, 83, -91, 111, 6), _line(-61, 83, -29, 55, 6),
    ]
    return parts, [[-165, 86], [0, 8], [135, -25], [155, 86]]


def _watering_can(_rng: random.Random) -> tuple[list[dict[str, Any]], list[list[float]]]:
    parts = [
        _rect(-128, -22, 230, 154, 28, "body", "ink", 9),
        _ellipse(-14, -22, 112, 91, "none", "ink", 14),
        _poly([[90, 28], [226, -70], [247, -45], [108, 74]], "accent", "ink", 8),
        _ellipse(244, -60, 35, 47, "accent", "ink", 7),
        _line(212, -87, 268, -35, 5, "paper"), _line(218, -96, 278, -46, 4, "paper"),
        _rect(-96, -49, 165, 31, 13, "accent", "ink", 6),
        _line(-79, 36, 59, 36, 5, "paper"), _line(-79, 72, 59, 72, 5, "paper"),
    ]
    return parts, [[-75, 72], [-5, -88], [132, 12], [245, -59]]


def _teapot(_rng: random.Random) -> tuple[list[dict[str, Any]], list[list[float]]]:
    parts = [
        _ellipse(-5, 45, 139, 101, "body", "ink", 9), _rect(-66, -73, 122, 31, 14, "accent", "ink", 7),
        _ellipse(-5, -82, 14, 14, "accent", "ink", 5),
        _poly([[103, -1], [220, -69], [247, -35], [128, 55]], "accent", "ink", 8),
        _arc(-113, 17, 100, math.pi / 2, math.pi * 1.56, 16), _arc(-113, 17, 68, math.pi / 2, math.pi * 1.56, 8, "paper"),
        _line(-83, 92, 72, 92, 6, "paper"), _ellipse(-5, 45, 48, 30, "accent", "none", 0),
    ]
    return parts, [[-154, 17], [-5, -82], [55, 45], [220, -47]]


def _telescope(_rng: random.Random) -> tuple[list[dict[str, Any]], list[list[float]]]:
    parts = [
        _poly([[-205, -82], [150, -41], [135, 42], [-220, 2]], "body", "ink", 9),
        _ellipse(148, 1, 27, 44, "glass", "ink", 8), _ellipse(-211, -40, 24, 44, "accent", "ink", 7),
        _rect(-29, 31, 79, 47, 8, "accent", "ink", 7), _ellipse(10, 76, 21, 14, "dark", "ink", 5),
        _line(10, 82, -113, 181, 13), _line(10, 82, 13, 194, 13), _line(10, 82, 133, 181, 13),
        _line(-130, 181, -96, 181, 10), _line(-4, 194, 31, 194, 10), _line(116, 181, 149, 181, 10),
    ]
    return parts, [[-208, -40], [5, -7], [146, 0], [10, 130]]


def _camera(_rng: random.Random) -> tuple[list[dict[str, Any]], list[list[float]]]:
    parts = [
        _rect(-190, -80, 380, 224, 34, "body", "ink", 10), _rect(-103, -123, 109, 49, 9, "accent", "ink", 7),
        _rect(80, -116, 60, 37, 8, "dark", "ink", 6), _ellipse(4, 30, 103, 103, "dark", "ink", 10),
        _ellipse(4, 30, 72, 72, "glass", "paper", 7), _ellipse(4, 30, 31, 31, "accent", "ink", 5),
        _ellipse(-138, -34, 15, 15, "accent", "ink", 4), _rect(137, -42, 37, 91, 8, "accent", "ink", 5),
    ]
    return parts, [[-137, -34], [-45, -103], [4, 30], [151, 3]]


def _gramophone(_rng: random.Random) -> tuple[list[dict[str, Any]], list[list[float]]]:
    parts = [
        _rect(-170, 23, 262, 159, 12, "body", "ink", 9), _ellipse(-40, 88, 67, 67, "dark", "paper", 6),
        _ellipse(-40, 88, 18, 18, "accent", "ink", 4), _line(15, 79, 79, 40, 8, "paper"),
        _line(79, 40, 119, -61, 19), _poly([[111, -70], [255, -158], [278, 29], [128, -28]], "accent", "ink", 10),
        _ellipse(260, -64, 42, 96, "body", "ink", 8), _rect(-154, 158, 230, 28, 6, "dark", "ink", 5),
    ]
    return parts, [[-40, 88], [88, -6], [189, -68], [260, -64]]


def _windmill(_rng: random.Random) -> tuple[list[dict[str, Any]], list[list[float]]]:
    blades: list[dict[str, Any]] = []
    for angle in (0, math.pi / 2, math.pi, math.pi * 1.5):
        direction = [math.cos(angle), math.sin(angle)]
        side = [-direction[1], direction[0]]
        points = [
            [direction[0] * 28 + side[0] * 13, direction[1] * 28 + side[1] * 13],
            [direction[0] * 184 + side[0] * 42, direction[1] * 184 + side[1] * 42],
            [direction[0] * 205 - side[0] * 21, direction[1] * 205 - side[1] * 21],
            [direction[0] * 33 - side[0] * 12, direction[1] * 33 - side[1] * 12],
        ]
        blades.append(_poly([[round(x, 2), round(y - 50, 2)] for x, y in points], "accent", "ink", 7))
    parts = [
        _poly([[-88, 195], [-50, -45], [51, -45], [98, 195]], "body", "ink", 10),
        _rect(-50, 80, 100, 115, 4, "dark", "ink", 6), *blades, _ellipse(0, -50, 28, 28, "dark", "paper", 6),
    ]
    return parts, [[0, -205], [-175, -50], [0, -50], [0, 150]]


def _umbrella(_rng: random.Random) -> tuple[list[dict[str, Any]], list[list[float]]]:
    parts = [
        _arc(0, -34, 182, math.pi, math.tau, 14),
        _poly([[-182, -34], [-121, -11], [-60, -35], [0, -10], [61, -35], [121, -11], [182, -34], [0, -145]], "body", "ink", 8),
        _line(0, -145, 0, 136, 11), _arc(39, 135, 39, 0, math.pi, 11),
        _line(-121, -11, 0, -145, 4, "paper"), _line(-60, -35, 0, -145, 4, "paper"),
        _line(61, -35, 0, -145, 4, "paper"), _line(121, -11, 0, -145, 4, "paper"),
    ]
    return parts, [[-145, -55], [0, -130], [82, -40], [23, 155]]


def _typewriter(_rng: random.Random) -> tuple[list[dict[str, Any]], list[list[float]]]:
    parts = [
        _poly([[-202, 9], [182, 9], [222, 146], [-225, 146]], "body", "ink", 10),
        _rect(-143, -132, 274, 151, 7, "paper", "ink", 8), _line(-128, -86, 111, -86, 5, "accent"),
        _line(-128, -47, 89, -47, 5, "accent"), _rect(-173, -8, 330, 34, 6, "accent", "ink", 6),
        _line(-192, -8, 190, -8, 11), _ellipse(-206, -8, 14, 14, "accent", "ink", 4),
    ]
    for row, count in enumerate((10, 9, 8)):
        y = 48 + row * 34
        start = -(count - 1) * 18
        for index in range(count):
            parts.append(_ellipse(start + index * 36, y, 11, 9, "dark", "paper", 3))
    return parts, [[-201, -8], [0, -90], [0, 49], [170, 128]]


def _sewing_machine(_rng: random.Random) -> tuple[list[dict[str, Any]], list[list[float]]]:
    parts = [
        _rect(-214, 131, 430, 42, 10, "dark", "ink", 7), _rect(-137, -122, 274, 80, 33, "body", "ink", 9),
        _rect(57, -70, 92, 184, 24, "body", "ink", 9), _poly([[-137, -57], [-45, -57], [-45, 82], [58, 82], [58, 125], [-137, 125]], "body", "ink", 9),
        _ellipse(101, -83, 54, 54, "accent", "ink", 8), _ellipse(101, -83, 24, 24, "dark", "paper", 5),
        _line(-25, 2, -25, 126, 8), _line(-58, 125, 14, 125, 7, "paper"), _ellipse(-91, -84, 13, 13, "accent", "ink", 4),
    ]
    return parts, [[-95, -84], [99, -83], [-25, 70], [125, 140]]


def _lighthouse(_rng: random.Random) -> tuple[list[dict[str, Any]], list[list[float]]]:
    parts = [
        _poly([[-105, 190], [-68, -62], [70, -62], [109, 190]], "body", "ink", 10),
        _rect(-93, -105, 186, 46, 8, "accent", "ink", 8), _rect(-56, -180, 112, 76, 7, "glass", "ink", 8),
        _poly([[-82, -180], [0, -229], [82, -180]], "accent", "ink", 8), _ellipse(0, -141, 21, 21, "paper", "ink", 5),
        _rect(-25, 92, 50, 98, 20, "dark", "ink", 6), _line(-88, 24, 89, 24, 14, "accent"),
        _line(-75, -101, -131, -101, 8), _line(75, -101, 131, -101, 8),
    ]
    return parts, [[0, -210], [0, -140], [75, 24], [0, 142]]


def _binoculars(_rng: random.Random) -> tuple[list[dict[str, Any]], list[list[float]]]:
    parts = [
        _poly([[-190, -72], [-43, -109], [-28, 132], [-199, 106]], "body", "ink", 9),
        _poly([[190, -72], [43, -109], [28, 132], [199, 106]], "body", "ink", 9),
        _ellipse(-111, 101, 91, 55, "glass", "ink", 9), _ellipse(111, 101, 91, 55, "glass", "ink", 9),
        _ellipse(-104, -82, 67, 42, "accent", "ink", 8), _ellipse(104, -82, 67, 42, "accent", "ink", 8),
        _rect(-46, -34, 92, 103, 18, "dark", "ink", 7), _ellipse(0, -46, 31, 31, "accent", "ink", 6),
    ]
    return parts, [[-111, 101], [-105, -83], [0, -46], [111, 101]]


def _lantern(_rng: random.Random) -> tuple[list[dict[str, Any]], list[list[float]]]:
    parts = [
        _arc(0, -73, 130, math.pi, math.tau, 15), _rect(-96, -92, 192, 242, 26, "dark", "ink", 10),
        _poly([[-67, -55], [68, -55], [53, 112], [-54, 112]], "glass", "ink", 8),
        _poly([[-20, 93], [0, -8], [21, 93]], "accent", "paper", 5), _ellipse(0, 71, 39, 61, "accent", "none", 0),
        _rect(-119, 142, 238, 38, 13, "body", "ink", 7), _rect(-83, -121, 166, 32, 10, "body", "ink", 6),
        _line(-70, -52, -70, 113, 6, "paper"), _line(70, -52, 70, 113, 6, "paper"),
    ]
    return parts, [[0, -190], [0, -106], [0, 57], [0, 158]]


def _violin(_rng: random.Random) -> tuple[list[dict[str, Any]], list[list[float]]]:
    parts = [
        _ellipse(0, 83, 91, 106, "body", "ink", 9), _ellipse(0, -39, 70, 85, "body", "ink", 9),
        _ellipse(-61, 21, 42, 50, "dark", "none", 0), _ellipse(61, 21, 42, 50, "dark", "none", 0),
        _rect(-22, -183, 44, 191, 9, "accent", "ink", 7), _rect(-45, -241, 90, 63, 22, "body", "ink", 7),
        _rect(-42, 35, 84, 19, 5, "dark", "paper", 4), _line(-9, -225, -9, 155, 3, "paper"),
        _line(-3, -225, -3, 155, 3, "paper"), _line(3, -225, 3, 155, 3, "paper"), _line(9, -225, 9, 155, 3, "paper"),
        _arc(-27, 27, 22, -math.pi / 2, math.pi / 2, 5, "paper"), _arc(27, 27, 22, math.pi / 2, math.pi * 1.5, 5, "paper"),
    ]
    return parts, [[0, -222], [0, -95], [0, 44], [0, 138]]


TEMPLATES: dict[str, Callable[[random.Random], tuple[list[dict[str, Any]], list[list[float]]]]] = {
    "bicycle": _bicycle,
    "watering_can": _watering_can,
    "teapot": _teapot,
    "telescope": _telescope,
    "camera": _camera,
    "gramophone": _gramophone,
    "windmill": _windmill,
    "umbrella": _umbrella,
    "typewriter": _typewriter,
    "sewing_machine": _sewing_machine,
    "lighthouse": _lighthouse,
    "binoculars": _binoculars,
    "lantern": _lantern,
    "violin": _violin,
}

ALIASES = {
    "bicycle": ["bicycle", "bike"],
    "watering_can": ["watering can"],
    "teapot": ["teapot", "tea pot"],
    "telescope": ["telescope"],
    "camera": ["camera"],
    "gramophone": ["gramophone", "phonograph", "record player"],
    "windmill": ["windmill"],
    "umbrella": ["umbrella"],
    "typewriter": ["typewriter"],
    "sewing_machine": ["sewing machine"],
    "lighthouse": ["lighthouse"],
    "binoculars": ["binoculars"],
    "lantern": ["lantern"],
    "violin": ["violin", "fiddle"],
}

PALETTES = [
    {"paper": "#fff3c4", "ink": "#251914", "body": "#d55e35", "accent": "#ecc769", "dark": "#3d5d63", "glass": "#92c9c1", "wash": "#5f2c28"},
    {"paper": "#f5ecd9", "ink": "#18202a", "body": "#326b70", "accent": "#e69e45", "dark": "#273642", "glass": "#9cc8b7", "wash": "#4b324a"},
    {"paper": "#f6e7bd", "ink": "#201b24", "body": "#88649b", "accent": "#e8bd58", "dark": "#31525f", "glass": "#8cc8cf", "wash": "#5e2939"},
    {"paper": "#f4ead3", "ink": "#161e19", "body": "#5a7c48", "accent": "#d77b3f", "dark": "#2e4744", "glass": "#9dc5b6", "wash": "#59312d"},
]

DEFAULT_PARAMETERS = {
    "object_pool": ["bicycle", "watering_can", "teapot", "telescope", "camera", "gramophone", "lighthouse", "umbrella", "binoculars", "lantern"],
    "reveal_budget": 6,
    "reveal_radius": 78,
    "clutter_count": 8,
    "foreground_marks": 0,
    "rotation_max_deg": 7,
    "scale_min": 0.94,
    "scale_max": 1.05,
}


def _transform(point: list[float], subject: dict[str, float]) -> list[float]:
    angle = math.radians(float(subject["rotation_deg"]))
    scale = float(subject["scale"])
    x, y = point[0] * scale, point[1] * scale
    return [
        round(float(subject["cx"]) + x * math.cos(angle) - y * math.sin(angle), 2),
        round(float(subject["cy"]) + x * math.sin(angle) + y * math.cos(angle), 2),
    ]


def _decorations(rng: random.Random, count: int, foreground_count: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index in range(count + foreground_count):
        foreground = index >= count
        kind = rng.choice(("line", "ellipse", "poly"))
        x, y = rng.randint(28, STAGE["width"] - 28), rng.randint(25, STAGE["height"] - 25)
        if kind == "line":
            length = rng.randint(34, 122 if foreground else 80)
            angle = rng.uniform(0, math.tau)
            primitive = _line(
                round(x - math.cos(angle) * length / 2, 2), round(y - math.sin(angle) * length / 2, 2),
                round(x + math.cos(angle) * length / 2, 2), round(y + math.sin(angle) * length / 2, 2),
                rng.randint(3, 10 if foreground else 6), "wash" if foreground else "accent",
            )
        elif kind == "ellipse":
            primitive = _ellipse(x, y, rng.randint(8, 30), rng.randint(5, 18), "wash" if foreground else "accent", "none", 0)
        else:
            size = rng.randint(12, 34)
            primitive = _poly([[x, y - size], [x + size, y + size], [x - size, y + size]], "wash" if foreground else "accent", "none", 0)
        primitive["layer"] = "foreground" if foreground else "background"
        primitive["alpha"] = round(rng.uniform(0.24, 0.48) if foreground else rng.uniform(0.14, 0.34), 3)
        items.append(primitive)
    return items


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed(seed))
    condition = copy.deepcopy(task.get("_control_condition"))
    parameters = copy.deepcopy(DEFAULT_PARAMETERS)
    parameters.update(copy.deepcopy((condition or {}).get("difficulty_parameters") or {}))
    object_pool = list(parameters.get("object_pool") or [])
    if not object_pool or any(item not in TEMPLATES for item in object_pool):
        raise ValueError("reveal-to-identify object pool is invalid")
    budget = int(parameters.get("reveal_budget", 0))
    radius = int(parameters.get("reveal_radius", 0))
    clutter_count = int(parameters.get("clutter_count", 0))
    foreground_marks = int(parameters.get("foreground_marks", 0))
    if not 3 <= budget <= 8 or not 36 <= radius <= 110 or not 0 <= clutter_count <= 40 or not 0 <= foreground_marks <= 8:
        raise ValueError("reveal-to-identify parameters are outside supported limits")
    label = rng.choice(object_pool)
    primitives, local_salient = TEMPLATES[label](rng)
    rotation_limit = float(parameters.get("rotation_max_deg", 0))
    subject = {
        "cx": rng.randint(430, 470),
        "cy": rng.randint(246, 270),
        "scale": round(rng.uniform(float(parameters.get("scale_min", 0.9)), float(parameters.get("scale_max", 1.0))), 4),
        "rotation_deg": round(rng.uniform(-rotation_limit, rotation_limit), 3),
    }
    palette = copy.deepcopy(rng.choice(PALETTES))
    decorations = _decorations(rng, clutter_count, foreground_marks)
    scene = {
        "palette": palette,
        "subject": subject,
        "subject_primitives": primitives,
        "decorations": decorations,
        "grain_seed": rng.randrange(1_000_000),
    }
    salient_points = [
        [
            round(min(max(transformed[0], radius), STAGE["width"] - radius), 2),
            round(min(max(transformed[1], radius), STAGE["height"] - radius), 2),
        ]
        for transformed in (_transform(point, subject) for point in local_salient)
    ]
    for x, y in salient_points:
        if not (radius <= x <= STAGE["width"] - radius and radius <= y <= STAGE["height"] - radius):
            raise AssertionError("salient inspection point leaves the revealable plate")
    task_id = str(task.get("id") or "reveal_to_identify_seed_0001@0.1")
    difficulty = int((condition or {}).get("difficulty") or 2)
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|d{difficulty}|{task_id}".encode()).hexdigest()[:14]
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": "Choose useful reveal locations, inspect the hidden object, then enter its common English name.",
        "submit_label": "FILE IDENTIFICATION",
        "asset_manifest": "shared_runtime/assets/provenance/reveal_to_identify_v0.json",
        "generator": {"name": "procedural_darkroom_object_plate_v1", "variant_count": VARIANT_COUNT},
        "stage": copy.deepcopy(STAGE),
        "scene": copy.deepcopy(scene),
        "reveal": {"budget": budget, "radius": radius},
        "answer_constraints": {"maximum_characters": 32, "alphabetic_words_only": True},
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "stage": copy.deepcopy(STAGE),
        "scene": copy.deepcopy(scene),
        "reveal": {"budget": budget, "radius": radius},
        "answer": ALIASES[label][0],
        "accepted_answers": copy.deepcopy(ALIASES[label]),
        "object_code": label,
        "salient_points": salient_points,
        "parameters": copy.deepcopy(parameters),
        "variant_count": VARIANT_COUNT,
    }
    if condition:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
