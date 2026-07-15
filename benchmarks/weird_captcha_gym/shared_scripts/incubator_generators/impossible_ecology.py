from __future__ import annotations

import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "impossible_ecology"
FIELDS = ("CLIMATE", "FOOD", "LIGHT")
SIGNATURES = tuple((field, sign) for field in FIELDS for sign in (-1, 1))
COLORS = ("#9dff70", "#63e7ff", "#ffcc63", "#ff7aa8", "#c499ff")
PALETTES = (
    {"name": "moss", "paper": "#08120c", "grid": "#244b31", "ink": "#dff3d5", "danger": "#ff5f56"},
    {"name": "brine", "paper": "#071319", "grid": "#255063", "ink": "#d8f5f4", "danger": "#ff6a65"},
    {"name": "ember", "paper": "#171008", "grid": "#694426", "ink": "#f5e8cf", "danger": "#ff5d51"},
    {"name": "violet", "paper": "#100b18", "grid": "#533769", "ink": "#eee1f7", "danger": "#ff6573"},
)


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _round(value: float) -> float:
    return round(float(value) + 1e-12, 5)


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    arena = {"width": 1000, "height": 430, "margin": 24}
    center = [arena["width"] / 2, arena["height"] / 2]
    rotation = rng.uniform(-math.pi, math.pi)
    signatures = list(SIGNATURES)
    rng.shuffle(signatures)
    selected = signatures[:5]
    colors = list(COLORS)
    rng.shuffle(colors)

    organisms: list[dict[str, Any]] = []
    targets: list[dict[str, Any]] = []
    for index in range(5):
        angle = rotation + index * math.tau / 5
        tangent = [-math.sin(angle), math.cos(angle)]
        radial = [math.cos(angle), math.sin(angle)]
        initial_radius = rng.uniform(78, 96)
        tangential_jitter = rng.uniform(-14, 14)
        position = [
            center[0] + radial[0] * initial_radius + tangent[0] * tangential_jitter,
            center[1] + radial[1] * initial_radius + tangent[1] * tangential_jitter,
        ]
        target_radius = rng.uniform(164, 174)
        target = [center[0] + radial[0] * target_radius, center[1] + radial[1] * target_radius]
        primary_field, primary_sign = selected[index]
        responses: dict[str, float] = {}
        for field in FIELDS:
            if field == primary_field:
                responses[field] = _round(primary_sign * rng.uniform(1.18, 1.34))
            else:
                responses[field] = _round(rng.choice((-1, 1)) * rng.uniform(.11, .19))
        organism_id = f"organism-{index + 1}"
        organisms.append({
            "id": organism_id,
            "label": chr(65 + index),
            "color": colors[index],
            "radius": 14,
            "initial_position": [_round(value) for value in position],
            "responses": responses,
        })
        targets.append({
            "id": f"sanctuary-{index + 1}",
            "organism_id": organism_id,
            "label": chr(65 + index),
            "color": colors[index],
            "center": [_round(value) for value in target],
            "radius": 38,
        })

    controls = {
        "tick_ms": 50,
        "damping": .83,
        "max_speed": 4.8,
        "capture_speed": 5.0,
        "capture_margin": 1.0,
        "pointer_sample_distance": 3.0,
        "max_ticks": 1400,
        "calibration_field_ms": 620,
    }
    obstacle = {"id": "nursery", "center": center, "radius": 48}
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode("utf-8")).hexdigest()[:12]
    task_id = str(task.get("id") or "impossible_ecology_seed_0001@0.1")
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Learn the coupled field responses, then shepherd every organism into its matching sanctuary.",
        "submit_label": "CERTIFY STABLE ECOLOGY",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "generator": {"name": "coupled_field_ecology_shepherd_v2", "variant_count": 24_000_000_000},
        "palette": rng.choice(PALETTES),
        "arena": arena,
        "fields": list(FIELDS),
        "organisms": organisms,
        "targets": targets,
        "obstacle": obstacle,
        "controls": controls,
        "rules": [
            "Select one global field, then hold the pointer inside the arena.",
            "Each uncaptured organism is attracted or repelled differently; all move at once.",
            "A matching sanctuary locks an organism permanently. Stabilize all five.",
        ],
        "render_boundary": "The static browser receives response coefficients to run the local simulation. They are never rendered numerically; the independent grader replays every field, pointer, and physics tick.",
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "arena": arena,
        "fields": list(FIELDS),
        "organisms": organisms,
        "targets": targets,
        "obstacle": obstacle,
        "controls": controls,
        "variant_count": public_state["generator"]["variant_count"],
    }
    for organism, target in zip(organisms, targets):
        assert organism["id"] == target["organism_id"]
        assert max(abs(value) for value in organism["responses"].values()) > 1.1
        assert math.dist(organism["initial_position"], center) > obstacle["radius"] + organism["radius"] + 12
        assert math.dist(target["center"], center) > 150
    assert len({(max(item["responses"], key=lambda field: abs(item["responses"][field])), 1 if item["responses"][max(item["responses"], key=lambda field: abs(item["responses"][field]))] > 0 else -1) for item in organisms}) == 5
    return public_state, ground_truth
