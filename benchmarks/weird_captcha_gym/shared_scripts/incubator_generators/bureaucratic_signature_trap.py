from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "bureaucratic_signature_trap"


def _seed(seed: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{MECHANIC_ID}|v3".encode()).digest()[:8], "big")


def _original_trace(
    rng: random.Random,
    aperture: dict[str, int],
    *,
    frequency_pairs: tuple[tuple[int, int], ...] = ((2, 3), (3, 4), (3, 5)),
    sample_count: int = 108,
    radius_scale_min: float = 0.61,
    radius_scale_max: float = 0.66,
) -> list[list[float]]:
    """Create a closed, multi-loop autograph that a generic circle cannot match."""

    center_x, center_y = float(aperture["x"]), float(aperture["y"])
    radius = float(aperture["radius"]) * rng.uniform(radius_scale_min, radius_scale_max)
    frequencies = rng.choice(frequency_pairs)
    phase_x = rng.uniform(0.18, 1.25)
    phase_y = rng.uniform(-0.45, 0.45)
    rotation = rng.uniform(-0.48, 0.48)
    cosine, sine = math.cos(rotation), math.sin(rotation)
    points: list[list[float]] = []
    for index in range(sample_count + 1):
        angle = math.tau * index / sample_count
        raw_x = radius * math.sin(frequencies[0] * angle + phase_x)
        raw_y = radius * math.sin(frequencies[1] * angle + phase_y)
        x = center_x + raw_x * cosine - raw_y * sine
        y = center_y + raw_x * sine + raw_y * cosine
        points.append([round(x, 2), round(y, 2)])
    # Close on the exact same pixel so start/end comparison is deterministic.
    points[-1] = points[0][:]
    assert all(math.hypot(point[0] - center_x, point[1] - center_y) <= float(aperture["radius"]) * 0.94 for point in points)
    return points


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed(seed))
    condition = task.get("_control_condition")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    layer_count = int(parameters.get("layer_count", 4))
    aperture_radius = int(parameters.get("aperture_radius", 72))
    alignment_tolerance = parameters.get("alignment_tolerance", 8)
    initial_x_min = int(parameters.get("initial_x_offset_min", 78))
    initial_x_max = int(parameters.get("initial_x_offset_max", 138))
    initial_y_min = int(parameters.get("initial_y_offset_min", 44))
    initial_y_max = int(parameters.get("initial_y_offset_max", 84))
    frequency_pairs = tuple(
        (int(pair[0]), int(pair[1]))
        for pair in parameters.get("trace_frequency_pairs", ((2, 3), (3, 4), (3, 5)))
    )
    trace_sample_count = int(parameters.get("trace_sample_count", 108))
    trace_radius_scale_min = float(parameters.get("trace_radius_scale_min", 0.61))
    trace_radius_scale_max = float(parameters.get("trace_radius_scale_max", 0.66))
    if not 1 <= layer_count <= 5:
        raise ValueError("carbon layer_count must be between one and five")
    if not 56 <= aperture_radius <= 104 or not 4 <= alignment_tolerance <= 24:
        raise ValueError("carbon aperture or alignment tolerance is outside supported bounds")
    if not 24 <= initial_x_min <= initial_x_max <= 138 or not 16 <= initial_y_min <= initial_y_max <= 84:
        raise ValueError("carbon initial displacement is outside supported bounds")
    if (
        not frequency_pairs
        or any(first < 1 or second < 1 or first > 8 or second > 8 for first, second in frequency_pairs)
        or not 60 <= trace_sample_count <= 180
        or not 0.45 <= trace_radius_scale_min <= trace_radius_scale_max <= 0.66
    ):
        raise ValueError("carbon autograph geometry is outside supported bounds")
    aperture = {
        "x": 356 + rng.randint(-18, 18),
        "y": 208 + rng.randint(-12, 12),
        "radius": aperture_radius,
    }
    layers = []
    colors = ["cyan", "amber", "rose", "violet", "mint"]
    for index, color in enumerate(colors[:layer_count]):
        target = {"x": rng.randint(-28, 28), "y": rng.randint(-20, 20)}
        initial = {
            "x": target["x"] + rng.choice((-1, 1)) * rng.randint(initial_x_min, initial_x_max),
            "y": target["y"] + rng.choice((-1, 1)) * rng.randint(initial_y_min, initial_y_max),
        }
        layers.append(
            {
                "id": f"sheet-{hashlib.sha256(f'{seed}|sheet|{index}'.encode()).hexdigest()[:8]}",
                "color": color,
                "fragment": index,
                "initial": initial,
                "target": target,
            }
        )
    original = _original_trace(
        rng,
        aperture,
        frequency_pairs=frequency_pairs,
        sample_count=trace_sample_count,
        radius_scale_min=trace_radius_scale_min,
        radius_scale_max=trace_radius_scale_max,
    )
    contract = {
        "stage": {"width": 700, "height": 390},
        "aperture": aperture,
        "layers": layers,
        "alignment_tolerance": alignment_tolerance,
        "max_drag_step": 55,
        "original_trace": original,
        "signature": {
            "min_samples": int(parameters.get("signature_min_samples", 34)),
            "max_samples": 700,
            "max_step": parameters.get("signature_max_step", 36),
            "start_tolerance": parameters.get("signature_start_tolerance", 22),
            "end_tolerance": parameters.get("signature_end_tolerance", 24),
            "mean_deviation": parameters.get("signature_mean_deviation", 14),
            "p90_deviation": parameters.get("signature_p90_deviation", 23),
            "coverage_tolerance": parameters.get("signature_coverage_tolerance", 20),
            "minimum_coverage": parameters.get("signature_minimum_coverage", 0.84),
            "minimum_length_ratio": parameters.get("signature_minimum_length_ratio", 0.72),
            "maximum_length_ratio": parameters.get("signature_maximum_length_ratio", 1.38),
        },
    }
    signature = contract["signature"]
    if (
        not 16 <= int(signature["min_samples"]) <= trace_sample_count + 1
        or not 16 <= float(signature["max_step"]) <= 55
        or not 8 <= float(signature["start_tolerance"]) <= 40
        or not 8 <= float(signature["end_tolerance"]) <= 40
        or not 6 <= float(signature["mean_deviation"]) <= 28
        or not float(signature["mean_deviation"]) <= float(signature["p90_deviation"]) <= 42
        or not 8 <= float(signature["coverage_tolerance"]) <= 34
        or not 0.5 <= float(signature["minimum_coverage"]) <= 0.98
        or not 0.4 <= float(signature["minimum_length_ratio"]) < 1
        or not 1 < float(signature["maximum_length_ratio"]) <= 1.8
    ):
        raise ValueError("carbon signature acceptance contract is outside supported bounds")
    difficulty = int((condition or {}).get("difficulty") or 4)
    difficulty_identity = "" if difficulty == 4 else f"|difficulty-{difficulty}"
    challenge_id = hashlib.sha256(
        f"{seed}|{MECHANIC_ID}|challenge-v3{difficulty_identity}".encode()
    ).hexdigest()[:12]
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "challenge_id": challenge_id,
        "prompt": (
            str(task.get("natural_language"))
            if condition is not None and task.get("natural_language")
            else "Register the carbon stack. Trace the buried original in one stroke."
        ),
        "asset_manifest": "shared_runtime/assets/provenance/reviewed_overhaul_v1.json",
        "generator": {"name": "carbon_autograph_registration_v3", "variant_count": 10**12},
        "form": contract,
    }
    truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "seed": seed,
        "challenge_id": challenge_id,
        "form": contract,
    }
    if condition is not None:
        public["control_condition"] = copy.deepcopy(condition)
        truth["control_condition"] = copy.deepcopy(condition)
    return public, truth
