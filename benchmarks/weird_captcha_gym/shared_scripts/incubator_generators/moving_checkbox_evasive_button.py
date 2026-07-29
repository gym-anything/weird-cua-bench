from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "moving_checkbox_evasive_button"
PALETTES = ("oxide", "blueprint", "amber", "verdigris")
ROUTE_LEVELS = (132, 176, 220, 264, 308, 352, 396)
OFFSET_VALUES = tuple(range(-120, 121, 20))
VARIANT_COUNT = len(PALETTES) * len(ROUTE_LEVELS) ** 3 * len(OFFSET_VALUES) ** 4 * 48


def _different_offset(rng: random.Random, target: int, offset_values: tuple[int, ...]) -> int:
    options = [value for value in offset_values if abs(value - target) >= 60]
    return rng.choice(options)


def _route_levels(rng: random.Random, gate_count: int) -> list[int]:
    for _ in range(100):
        route = rng.sample(ROUTE_LEVELS, gate_count)
        if all(abs(route[index] - route[index - 1]) >= 44 for index in range(1, gate_count)):
            return route
    raise ValueError("could not choose separated scroll-cage portal routes")


def _control_parameters(task: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    condition = task.get("_control_condition")
    if not isinstance(condition, dict):
        return {}, None
    parameters = condition.get("difficulty_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("scroll-cage difficulty parameters are missing")
    return dict(parameters), copy.deepcopy(condition)


def _shaft_layout(shaft_count: int) -> tuple[list[int], int]:
    if not 2 <= shaft_count <= 5:
        raise ValueError("scroll-cage shaft count must be between two and five")
    left_margin, gap, right_margin = 35, 42, 35
    shaft_width = (1000 - left_margin - right_margin - gap * (shaft_count - 1)) // shaft_count
    if shaft_width < 120:
        raise ValueError("scroll-cage shaft width is too narrow")
    return [left_margin + index * (shaft_width + gap) for index in range(shaft_count)], shaft_width


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    parameters, condition = _control_parameters(task)
    digest = hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    task_id = str(task.get("id") or "moving_checkbox_evasive_button_seed_0001@0.1")
    difficulty = int(condition.get("difficulty", 4)) if condition is not None else 4
    challenge_variant = "scroll-cage-checkbox-v2" if difficulty == 4 else f"scroll-cage-checkbox-v2-d{difficulty}"
    challenge_id = hashlib.sha256(f"{seed}|{challenge_variant}".encode("utf-8")).hexdigest()[:12]

    shaft_count = int(parameters.get("shaft_count", 4))
    gate_count = shaft_count - 1
    opening_half_height = int(parameters.get("opening_half_height", 38))
    alignment_tolerance = int(parameters.get("alignment_tolerance", 18))
    capture_radius = int(parameters.get("capture_radius", 46))
    cursor_radius = int(parameters.get("cursor_radius", 148))
    cursor_acceleration = int(parameters.get("cursor_acceleration", 3))
    friction_milli = int(parameters.get("friction_milli", 920))
    max_speed = int(parameters.get("max_speed", 10))
    maximum_ticks = int(parameters.get("maximum_ticks", 3600))
    if not (20 <= opening_half_height <= 64 and 8 <= alignment_tolerance <= 32 and 34 <= capture_radius <= 68):
        raise ValueError("scroll-cage geometry is outside supported limits")
    if not (120 <= cursor_radius <= 190 and 2 <= cursor_acceleration <= 4 and 880 <= friction_milli <= 950 and 6 <= max_speed <= 12):
        raise ValueError("scroll-cage pointer physics is outside supported limits")
    if not 600 <= maximum_ticks <= 3600:
        raise ValueError("scroll-cage maximum tick budget is outside supported limits")

    shaft_lefts, shaft_width = _shaft_layout(shaft_count)
    offset_values = OFFSET_VALUES
    solution_offsets = [rng.choice(offset_values) for _ in range(shaft_count)]
    for _ in range(100):
        initial_offsets = [_different_offset(rng, target, offset_values) for target in solution_offsets]
        residuals = [solution_offsets[index] - initial_offsets[index] for index in range(shaft_count)]
        if all(abs(residuals[index] - residuals[index + 1]) > alignment_tolerance for index in range(gate_count)):
            break
    else:
        raise ValueError("could not generate initially closed scroll-cage portals")
    route = _route_levels(rng, gate_count)
    boundaries = []
    for index, screen_y in enumerate(route):
        boundaries.append({
            "id": f"gate-{index + 1}",
            "x": shaft_lefts[index] + shaft_width + 21,
            "left_shaft": index,
            "right_shaft": index + 1,
            "left_base_y": screen_y + solution_offsets[index],
            "right_base_y": screen_y + solution_offsets[index + 1],
            "opening_half_height": opening_half_height,
            "alignment_tolerance": alignment_tolerance,
        })

    clamp_y = max(104, min(416, route[-1] + rng.choice((-72, -52, 52, 72))))
    initial_y = max(94, min(426, route[0] + rng.choice((-66, -48, 48, 66))))
    initial_velocity = rng.choice(((2, 1), (2, -1), (1, 2), (1, -2)))
    initial_x = 132 if shaft_count == 4 else shaft_lefts[0] + shaft_width // 2
    clamp_x = 914 if shaft_count == 4 else shaft_lefts[-1] + shaft_width * 3 // 4
    scene = {
        "width": 1000,
        "height": 520,
        "shaft_lefts": shaft_lefts,
        "shaft_width": shaft_width,
        "offset_min": -120,
        "offset_max": 120,
        "offset_step": 20,
        "initial_offsets": initial_offsets,
        "boundaries": boundaries,
        "target": {
            "x": initial_x,
            "y": initial_y,
            "vx": initial_velocity[0],
            "vy": initial_velocity[1],
            "radius": 15,
        },
        "clamp": {"x": clamp_x, "y": clamp_y, "capture_radius": capture_radius},
    }
    physics = {
        "tick_ms": 50,
        "cursor_radius": cursor_radius,
        "cursor_acceleration": cursor_acceleration,
        "friction_milli": friction_milli,
        "max_speed": max_speed,
        "wall_restitution_milli": 680,
        "top": 54,
        "bottom": 466,
        "maximum_ticks": maximum_ticks,
    }
    variant_count = len(PALETTES) * len(ROUTE_LEVELS) ** gate_count * len(offset_values) ** shaft_count * 48
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
            "variant_count": variant_count,
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
        "variant_count": variant_count,
        "variant_count_kind": public_state["generator"]["variant_count_kind"],
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
