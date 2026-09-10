from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "pocket_animation_studio"
ASSET_MANIFEST = "shared_runtime/assets/provenance/pocket_animation_studio_v0.json"

FIELD_NAMES: dict[str, tuple[str, ...]] = {
    "circle": ("x", "y", "radius"),
    "rect": ("x", "y", "width", "height"),
    "line": ("x1", "y1", "x2", "y2", "width"),
}
PALETTE = ("#f8d66d", "#70e7cf", "#ff7f8a", "#a995ff", "#7fc8ff", "#f4a261")
SHAPE_KINDS = ("circle", "rect", "line")


def _seed_value(seed: str) -> int:
    return int(hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode("utf-8")).hexdigest()[:16], 16)


def _condition(task: dict[str, Any]) -> dict[str, Any] | None:
    value = task.get("_control_condition")
    return copy.deepcopy(value) if isinstance(value, dict) else None


def _parameters(condition: dict[str, Any] | None) -> dict[str, Any]:
    if condition:
        return dict(condition.get("difficulty_parameters") or {})
    # The historical/reference task is the approved L4 configuration.
    return {
        "shape_count": 4,
        "sample_count": 24,
        "duration_ms": 4200,
        "allowed_expression_types": ["const", "linear", "reverse", "wave"],
        "wave_cycles": 2,
        "motion_amplitude": 34,
        "include_line": True,
    }


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _expr(kind: str, a: float, b: float = 0.0, frequency: int = 1) -> dict[str, Any]:
    return {
        "kind": str(kind),
        "a": round(float(a), 3),
        "b": round(float(b), 3),
        "frequency": int(max(1, frequency)),
    }


def evaluate_expression(expression: dict[str, Any], time_fraction: float) -> float:
    kind = str(expression.get("kind") or "const")
    a = float(expression.get("a") or 0.0)
    b = float(expression.get("b") or 0.0)
    frequency = max(1, int(expression.get("frequency") or 1))
    t = max(0.0, min(1.0, float(time_fraction)))
    if kind == "linear":
        value = a + b * t
    elif kind == "reverse":
        value = a + b * (1.0 - t)
    elif kind == "wave":
        value = a + b * math.sin(2.0 * math.pi * frequency * t)
    else:
        value = a
    return round(_clamp(value), 4)


def render_program(program: list[dict[str, Any]], time_fraction: float) -> list[dict[str, Any]]:
    rendered: list[dict[str, Any]] = []
    for shape in program:
        kind = str(shape.get("kind") or "")
        expressions = shape.get("expressions") or {}
        if kind not in FIELD_NAMES or any(field not in expressions for field in FIELD_NAMES[kind]):
            continue
        item: dict[str, Any] = {
            "id": str(shape.get("id") or ""),
            "kind": kind,
            "color": str(shape.get("color") or "#ffffff"),
        }
        item.update({
            field: evaluate_expression(expressions[field], time_fraction)
            for field in FIELD_NAMES[kind]
        })
        rendered.append(item)
    return rendered


def _make_expression(
    rng: random.Random,
    field: str,
    shape_index: int,
    parameters: dict[str, Any],
    *,
    moving: bool = True,
) -> dict[str, Any]:
    allowed = tuple(str(item) for item in parameters.get("allowed_expression_types") or ("const", "linear"))
    if not moving:
        allowed = ("const",)
    kind = rng.choice(allowed)
    if field in {"radius", "width", "height", "line_width", "stroke", "x2", "y2"}:
        base = rng.uniform(12.0, 86.0)
    else:
        base = rng.uniform(15.0, 85.0)
    amplitude = min(float(parameters.get("motion_amplitude", 34)), 38.0)
    if kind == "const":
        return _expr(kind, base)
    if kind in {"linear", "reverse"}:
        direction = rng.choice((-1.0, 1.0))
        travel = rng.uniform(amplitude * 0.38, amplitude)
        # Keep both endpoints away from the canvas edge so every reference
        # object remains visibly present throughout the loop.
        if base + direction * travel > 90.0:
            direction = -1.0
        if base + direction * travel < 10.0:
            direction = 1.0
        return _expr(kind, base, direction * travel)
    frequency = rng.randint(1, max(1, int(parameters.get("wave_cycles", 1))))
    wave_amplitude = min(amplitude * 0.42, rng.uniform(8.0, 18.0))
    return _expr("wave", base, wave_amplitude * rng.choice((-1.0, 1.0)), frequency)


def _make_program(rng: random.Random, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    shape_count = max(1, int(parameters.get("shape_count", 4)))
    kinds: list[str] = []
    if bool(parameters.get("include_line", True)):
        kinds.append("line")
    kinds.extend(("circle", "rect"))
    while len(kinds) < shape_count:
        kinds.append(rng.choice(SHAPE_KINDS))
    rng.shuffle(kinds)

    program: list[dict[str, Any]] = []
    for index in range(shape_count):
        kind = kinds[index]
        expressions = {
            field: _make_expression(
                rng,
                field,
                index,
                parameters,
                moving=(field not in {"width", "height", "radius", "width"} or index % 2 == 0),
            )
            for field in FIELD_NAMES[kind]
        }
        # A line's width and a shape's footprint are deliberately calmer than
        # its position. The moving coordinates remain the temporal problem.
        for field in ("radius", "width", "height"):
            if field in expressions and index % 2:
                expressions[field] = _make_expression(rng, field, index, parameters, moving=False)
        program.append({
            "id": f"shape-{index + 1}",
            "kind": kind,
            "color": PALETTE[index % len(PALETTE)],
            "expressions": expressions,
        })
    return program


def _public_shape(shape: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": shape["id"],
        "kind": shape["kind"],
        "color": shape["color"],
        "fields": list(FIELD_NAMES[shape["kind"]]),
    }


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = _condition(task)
    parameters = _parameters(condition)
    rng = random.Random(_seed_value(seed))
    target_program = _make_program(rng, parameters)
    sample_count = max(10, int(parameters.get("sample_count", 24)))
    duration_ms = max(1500, int(parameters.get("duration_ms", 4200)))
    reference_frames = [
        {
            "t": round(index / (sample_count - 1), 6),
            "objects": render_program(target_program, index / (sample_count - 1)),
        }
        for index in range(sample_count)
    ]
    challenge_suffix = f"|d{condition.get('difficulty')}|{task.get('id')}" if condition else "|base"
    challenge_id = hashlib.sha256(
        f"{seed}|{MECHANIC_ID}{challenge_suffix}".encode("utf-8")
    ).hexdigest()[:12]
    prompt = task.get("natural_language") or (
        "Rebuild the moving scene in the studio: drag shape and expression blocks into the program, "
        "run the entire preview, and certify the match."
    )
    public_state: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task.get("id"),
        "challenge_id": challenge_id,
        "prompt": prompt,
        "submit_label": "CERTIFY MATCH",
        "asset_manifest": ASSET_MANIFEST,
        "generator": {
            "name": "pocket_animation_studio_procedural_v1",
            "variant_count": 3 * len(PALETTE) * (sample_count ** 2),
        },
        "reference": {
            "width": 460,
            "height": 270,
            "duration_ms": duration_ms,
            "sample_count": sample_count,
            "frames": reference_frames,
            "title": rng.choice(("THE PAPER ALCHEMIST", "TINY ORBIT", "WINDOW GARDEN", "POCKET PARADE")),
            "palette": rng.randrange(6),
        },
        "studio": {
            "width": 460,
            "height": 270,
            "duration_ms": duration_ms,
            "shapes": [_public_shape(shape) for shape in target_program],
            "palette": list(PALETTE),
            "expression_types": [str(item) for item in parameters.get("allowed_expression_types") or ("const", "linear")],
            "field_labels": {
                "x": "X", "y": "Y", "x1": "X1", "y1": "Y1", "x2": "X2", "y2": "Y2",
                "radius": "R", "width": "W", "height": "H",
            },
        },
    }
    ground_truth: dict[str, Any] = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task.get("id"),
        "seed": seed,
        "challenge_id": challenge_id,
        "target_program": target_program,
        "target_frames": reference_frames,
        "duration_ms": duration_ms,
        "sample_count": sample_count,
        "tolerance": float(parameters.get("render_tolerance", 2.6)),
        "variant_count": 3 * len(PALETTE) * (sample_count ** 2),
    }
    if condition:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth

