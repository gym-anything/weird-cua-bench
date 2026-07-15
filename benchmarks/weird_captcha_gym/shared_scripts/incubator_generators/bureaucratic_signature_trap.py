from __future__ import annotations

import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "bureaucratic_signature_trap"


def _seed(seed: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{MECHANIC_ID}|v3".encode()).digest()[:8], "big")


def _original_trace(rng: random.Random, aperture: dict[str, int]) -> list[list[float]]:
    """Create a closed, multi-loop autograph that a generic circle cannot match."""

    center_x, center_y = float(aperture["x"]), float(aperture["y"])
    radius = float(aperture["radius"]) * rng.uniform(0.61, 0.66)
    frequencies = rng.choice(((2, 3), (3, 4), (3, 5)))
    phase_x = rng.uniform(0.18, 1.25)
    phase_y = rng.uniform(-0.45, 0.45)
    rotation = rng.uniform(-0.48, 0.48)
    cosine, sine = math.cos(rotation), math.sin(rotation)
    points: list[list[float]] = []
    sample_count = 108
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
    aperture = {"x": 356 + rng.randint(-18, 18), "y": 208 + rng.randint(-12, 12), "radius": 72}
    layers = []
    colors = ["cyan", "amber", "rose", "violet"]
    for index, color in enumerate(colors):
        target = {"x": rng.randint(-28, 28), "y": rng.randint(-20, 20)}
        initial = {
            "x": target["x"] + rng.choice((-1, 1)) * rng.randint(78, 138),
            "y": target["y"] + rng.choice((-1, 1)) * rng.randint(44, 84),
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
    original = _original_trace(rng, aperture)
    contract = {
        "stage": {"width": 700, "height": 390},
        "aperture": aperture,
        "layers": layers,
        "alignment_tolerance": 8,
        "max_drag_step": 55,
        "original_trace": original,
        "signature": {
            "min_samples": 34,
            "max_samples": 700,
            "max_step": 36,
            "start_tolerance": 22,
            "end_tolerance": 24,
            "mean_deviation": 14,
            "p90_deviation": 23,
            "coverage_tolerance": 20,
            "minimum_coverage": 0.84,
            "minimum_length_ratio": 0.72,
            "maximum_length_ratio": 1.38,
        },
    }
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|challenge-v3".encode()).hexdigest()[:12]
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "challenge_id": challenge_id,
        "prompt": "Register the carbon stack. Trace the buried original in one stroke.",
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
    return public, truth
