from __future__ import annotations

import hashlib
import random
from typing import Any


MECHANIC_ID = "moving_checkbox_evasive_button"
PALETTES = ("oxide", "blueprint", "amber", "verdigris")
ROUTE_LEVELS = (132, 176, 220, 264, 308, 352, 396)
OFFSET_VALUES = tuple(range(-120, 121, 20))
VARIANT_COUNT = len(PALETTES) * len(ROUTE_LEVELS) ** 3 * len(OFFSET_VALUES) ** 4 * 48


def _different_offset(rng: random.Random, target: int) -> int:
    options = [value for value in OFFSET_VALUES if abs(value - target) >= 60]
    return rng.choice(options)


def _route_levels(rng: random.Random) -> list[int]:
    for _ in range(100):
        route = rng.sample(ROUTE_LEVELS, 3)
        if all(abs(route[index] - route[index - 1]) >= 44 for index in range(1, 3)):
            return route
    raise ValueError("could not choose separated scroll-cage portals")


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    digest = hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    task_id = str(task.get("id") or "moving_checkbox_evasive_button_seed_0001@0.1")
    challenge_id = hashlib.sha256(f"{seed}|scroll-cage-checkbox-v2".encode("utf-8")).hexdigest()[:12]

    solution_offsets = [rng.choice(OFFSET_VALUES) for _ in range(4)]
    for _ in range(100):
        initial_offsets = [_different_offset(rng, target) for target in solution_offsets]
        residuals = [solution_offsets[index] - initial_offsets[index] for index in range(4)]
        if all(abs(residuals[index] - residuals[index + 1]) > 18 for index in range(3)):
            break
    else:
        raise ValueError("could not generate three initially closed scroll portals")
    route = _route_levels(rng)
    boundaries = []
    for index, screen_y in enumerate(route):
        boundaries.append({
            "id": f"gate-{index + 1}",
            "x": 257 + index * 243,
            "left_shaft": index,
            "right_shaft": index + 1,
            "left_base_y": screen_y + solution_offsets[index],
            "right_base_y": screen_y + solution_offsets[index + 1],
            "opening_half_height": 38,
            "alignment_tolerance": 18,
        })

    clamp_y = max(104, min(416, route[-1] + rng.choice((-72, -52, 52, 72))))
    initial_y = max(94, min(426, route[0] + rng.choice((-66, -48, 48, 66))))
    initial_velocity = rng.choice(((2, 1), (2, -1), (1, 2), (1, -2)))
    scene = {
        "width": 1000,
        "height": 520,
        "shaft_lefts": [35, 278, 521, 764],
        "shaft_width": 201,
        "offset_min": -120,
        "offset_max": 120,
        "offset_step": 20,
        "initial_offsets": initial_offsets,
        "boundaries": boundaries,
        "target": {
            "x": 132,
            "y": initial_y,
            "vx": initial_velocity[0],
            "vy": initial_velocity[1],
            "radius": 15,
        },
        "clamp": {"x": 914, "y": clamp_y, "capture_radius": 46},
    }
    physics = {
        "tick_ms": 50,
        "cursor_radius": 148,
        "cursor_acceleration": 3,
        "friction_milli": 920,
        "max_speed": 10,
        "wall_restitution_milli": 680,
        "top": 54,
        "bottom": 466,
        "maximum_ticks": 3600,
    }
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Check the box.",
        "submit_label": "VERIFY",
        "asset_manifest": "shared_runtime/assets/provenance/revived_pilots_v2.json",
        "generator": {
            "name": "fixed_step_scroll_cage_checkbox_v2",
            "variant_count": VARIANT_COUNT,
            "variant_count_kind": "palette/portal-route/scroll-solution/initial-state space",
        },
        "scene": scene,
        "physics": physics,
        "palette": rng.choice(PALETTES),
        "rules": {
            "scroll": "Each shaft carries its own portal halves; scrolling changes which passages physically meet.",
            "field": "The visible cursor field repels the checkbox under fixed-step dynamics.",
            "capture": "The checkbox can be checked only after the final clamp physically captures it.",
        },
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "scene": scene,
        "physics": physics,
        "solution_offsets": solution_offsets,
        "route_screen_y": route,
        "palette": public_state["palette"],
        "variant_count": VARIANT_COUNT,
        "variant_count_kind": public_state["generator"]["variant_count_kind"],
    }
    return public_state, ground_truth
