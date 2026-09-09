from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "rising_causeway"

PALETTES = (
    {"name": "basalt-rose", "sky": "#171d2d", "haze": "#35435a", "stone": "#807b8c", "edge": "#3e4052", "red": "#ef5d63", "yellow": "#f2ca55", "blue": "#5dd6e7", "glow": "#d6f6e7"},
    {"name": "moss-copper", "sky": "#152523", "haze": "#36524a", "stone": "#8d8974", "edge": "#454b42", "red": "#f26f5c", "yellow": "#e6c75d", "blue": "#62cfe0", "glow": "#d9edb4"},
    {"name": "violet-iron", "sky": "#211c31", "haze": "#514061", "stone": "#91859b", "edge": "#4c405d", "red": "#f26775", "yellow": "#e6bd56", "blue": "#68d6e8", "glow": "#e3d3ff"},
    {"name": "amber-slate", "sky": "#282019", "haze": "#69513f", "stone": "#9a917f", "edge": "#55483e", "red": "#f46a56", "yellow": "#f0cc60", "blue": "#63d6dc", "glow": "#fff0bf"},
)

PROFILES: dict[int, dict[str, Any]] = {
    1: {"red_stage_target": 1, "chamber_length": 13.5, "stair_height": 0.65, "corridor_half_width": 2.35, "launcher_count": 1, "decoy_actuator_count": 0, "terminal_radius": 0.8, "move_speed": 4.8, "look_sensitivity": 0.008},
    2: {"red_stage_target": 2, "chamber_length": 15.0, "stair_height": 0.8, "corridor_half_width": 2.15, "launcher_count": 1, "decoy_actuator_count": 1, "terminal_radius": 0.75, "move_speed": 4.7, "look_sensitivity": 0.008},
    3: {"red_stage_target": 2, "chamber_length": 16.5, "stair_height": 0.9, "corridor_half_width": 1.95, "launcher_count": 2, "decoy_actuator_count": 2, "terminal_radius": 0.7, "move_speed": 4.6, "look_sensitivity": 0.008},
    4: {"red_stage_target": 3, "chamber_length": 18.0, "stair_height": 1.05, "corridor_half_width": 1.75, "launcher_count": 3, "decoy_actuator_count": 3, "terminal_radius": 0.62, "move_speed": 4.5, "look_sensitivity": 0.008},
    5: {"red_stage_target": 3, "chamber_length": 20.0, "stair_height": 1.2, "corridor_half_width": 1.55, "launcher_count": 4, "decoy_actuator_count": 4, "terminal_radius": 0.55, "move_speed": 4.35, "look_sensitivity": 0.008},
}


def _seed_int(seed: str, salt: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).digest()[:8], "big")


def _pt(x: float, y: float, z: float) -> list[float]:
    return [round(float(x), 3), round(float(y), 3), round(float(z), 3)]


def _actuator(identifier: str, kind: str, x: float, y: float, z: float, *, facing: str = "front", label: str | None = None) -> dict[str, Any]:
    return {"id": identifier, "kind": kind, "position": _pt(x, y, z), "facing": facing, "label": label or kind.upper()}


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = copy.deepcopy(task.get("_control_condition"))
    difficulty = int((condition or {}).get("difficulty", 4))
    if difficulty not in PROFILES:
        raise ValueError(f"unknown Rising Causeway difficulty {difficulty}")
    profile = copy.deepcopy(PROFILES[difficulty])
    if condition is not None:
        for name, value in (condition.get("difficulty_parameters") or {}).items():
            if name in profile:
                profile[name] = copy.deepcopy(value)

    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    palette = copy.deepcopy(PALETTES[rng.randrange(len(PALETTES))])
    mirror = -1 if rng.randrange(2) else 1
    length = float(profile["chamber_length"])
    stair_height = float(profile["stair_height"])
    corridor = float(profile["corridor_half_width"])
    required_red_stage = int(profile["red_stage_target"])
    # The visible chamber mirror determines which end is the high end.  The
    # browser can enforce the same collision consequence without receiving a
    # private answer field; the solver still has to read the projected route.
    required_stair_end = "left" if mirror < 0 else "right"
    stair_sign = -1 if required_stair_end == "left" else 1
    required_launcher_index = rng.randrange(int(profile["launcher_count"]))
    actuator_z = 2.25

    # The causeway is a small volumetric world.  Its dimensions are derived
    # from the selected profile, but the same boxes and contact surfaces are
    # exported to the browser and to the independent grader.  Red extension
    # stages add contiguous support boxes; they are not just a flag on a
    # one-dimensional x threshold.
    bridge_start = 3.85
    red_segment_length = 0.56
    bridge_end = bridge_start + red_segment_length * required_red_stage
    stair_start = bridge_end
    stair_end = stair_start + 2.70
    launcher_start = stair_end + 0.80
    launcher_end = launcher_start + 1.25 + 0.60 * (int(profile["launcher_count"]) - 1)
    launch_duration_ms = 840
    gravity = 9.8
    flight_seconds = launch_duration_ms / 1000.0
    red_extensions = [
        {
            "id": f"red-extension-{index + 1}",
            "x0": round(bridge_start + index * red_segment_length, 3),
            "x1": round(bridge_start + (index + 1) * red_segment_length, 3),
            "y0": round(-corridor, 3),
            "y1": round(corridor, 3),
            "z": 0.0,
            "required_stage": index + 1,
        }
        for index in range(required_red_stage)
    ]
    stair_steps = []
    step_width = (stair_end - stair_start) / 3.0
    for index in range(3):
        rising_height = stair_height * (index + 1) / 3.0
        descending_height = stair_height * (3 - index) / 3.0
        stair_steps.append({
            "id": f"stair-step-{index + 1}",
            "x0": round(stair_start + index * step_width, 3),
            "x1": round(stair_start + (index + 1) * step_width, 3),
            "y0": round(-corridor, 3),
            "y1": round(corridor, 3),
            "z_left": round(rising_height if required_stair_end == "left" else descending_height, 3),
            "z_right": round(rising_height if required_stair_end == "right" else descending_height, 3),
        })

    actuator_y = mirror * (corridor * 0.35 + 0.35)
    red = _actuator("red-main", "red", 3.25, actuator_y, actuator_z, facing="front", label="EXTEND")
    yellow = _actuator("yellow-triple", "yellow", 6.25, actuator_y, actuator_z, facing="front", label="STAIR")
    actuators = [red, yellow]
    for index in range(int(profile["decoy_actuator_count"])):
        x = 4.6 + (index % 2) * 1.15
        y = -mirror * (corridor + 0.85 + 0.25 * (index % 3))
        kind = ("red-decoy" if index % 2 == 0 else "yellow-decoy")
        actuators.append(_actuator(f"decoy-{index + 1:02d}", kind, x, y, actuator_z - 0.12 * (index % 2), facing="front", label="DECOY"))

    launchers: list[dict[str, Any]] = []
    for index in range(int(profile["launcher_count"])):
        y = mirror * ((index - (int(profile["launcher_count"]) - 1) / 2) * min(1.0, corridor * 0.56))
        launcher_x = launcher_start + 0.48 + index * 0.60
        kind = "floor" if (index + difficulty) % 2 == 0 else "wall"
        if index == required_launcher_index:
            # L2 is the explicitly wall-launcher profile in controls.json.
            # Keep that contract in the generated world; the other profiles
            # retain their seeded orientation variation.
            kind = "wall" if difficulty == 2 else ("wall" if required_launcher_index % 2 else "floor")
        if kind == "wall":
            contact_y = mirror * (corridor - 0.28)
            landing_y = contact_y + mirror * (1.85 + 0.14 * difficulty)
            normal = "sideways"
            normal_vector = [0.0, float(mirror), 0.0]
        else:
            contact_y = max(-corridor + 0.22, min(corridor - 0.22, y))
            landing_y = contact_y
            normal = "upward"
            normal_vector = [0.0, 0.0, 1.0]
        landing_z = stair_height + (0.65 if kind == "floor" else 0.45)
        contact = _pt(launcher_x, contact_y, stair_height)
        landing_x = launcher_end + 1.10 + index * 0.18
        velocity = [
            (landing_x - contact[0]) / flight_seconds,
            (landing_y - contact[1]) / flight_seconds,
            (landing_z - contact[2] + 0.5 * gravity * flight_seconds * flight_seconds) / flight_seconds,
        ]
        launcher = {
            "id": f"launcher-{index + 1:02d}",
            "kind": kind,
            "normal": normal,
            "normal_vector": normal_vector,
            "position": _pt(launcher_x, contact_y, stair_height + 0.12),
            "contact": contact,
            "landing": _pt(landing_x, landing_y, landing_z),
            "launch_velocity": _pt(*velocity),
            "radius": 0.52,
            "facing": "floor" if kind == "floor" else ("left" if mirror < 0 else "right"),
            "tone": index % 3,
        }
        launchers.append(launcher)

    required_launcher = launchers[required_launcher_index]
    terminal = {
        "position": _pt(length - 0.3, required_launcher["landing"][1], required_launcher["landing"][2]),
        "visual_position": _pt(length - 0.3, required_launcher["landing"][1], required_launcher["landing"][2] + 1.38),
        "radius": round(float(profile["terminal_radius"]), 3),
        "height": 1.2,
    }
    start = {"position": _pt(1.2, 0.0, 0.0), "heading": 0.0, "pitch": -0.035, "support_z": 0.0}
    rules = {
        "player_radius": 0.28,
        "eye_height": 1.38,
        "tick_ms": 40,
        "move_speed": float(profile["move_speed"]),
        "look_sensitivity": float(profile["look_sensitivity"]),
        "corridor_half_width": corridor,
        "outer_y_half_width": round(corridor + 2.8, 3),
        "bridge_start": bridge_start,
        "bridge_end": bridge_end,
        "stair_start": stair_start,
        "stair_end": stair_end,
        "launcher_start": launcher_start,
        "launcher_end": launcher_end,
        "launch_duration_ms": launch_duration_ms,
        "flight_duration_ms": launch_duration_ms,
        "gravity": gravity,
        "max_step_up": 0.46,
        "max_step_down": 0.72,
        "contact_radius": 0.56,
        "terminal_radius": float(profile["terminal_radius"]),
        "red_stage_target": required_red_stage,
        "stair_height": stair_height,
    }
    segments = [
        {"id": "approach", "x0": 0.0, "x1": 3.85, "z": 0.0},
        {"id": "red-bridge", "x0": bridge_start, "x1": bridge_end, "z": 0.0, "requires_red_stage": required_red_stage},
        {"id": "stair-run", "x0": stair_start, "x1": stair_end, "z": stair_height, "requires_stair_end": required_stair_end},
        {"id": "launch-approach", "x0": stair_end, "x1": launcher_end, "z": stair_height},
        {"id": "landing-run", "x0": required_launcher["landing"][0] - 0.8, "x1": length + 0.8, "z": required_launcher["landing"][2], "landing_y": required_launcher["landing"][1]},
    ]
    landing_platforms = []
    for launcher in launchers:
        landing_platforms.append({
            "id": f"landing-{launcher['id']}",
            "x0": round(float(launcher["landing"][0]) - 0.8, 3),
            "x1": round(length + 0.8, 3),
            "y0": round(float(launcher["landing"][1]) - corridor * 0.78, 3),
            "y1": round(float(launcher["landing"][1]) + corridor * 0.78, 3),
            "z": float(launcher["landing"][2]),
            "launcher_id": launcher["id"],
        })
    chamber = {
        "length": round(length, 3),
        "corridor_half_width": corridor,
        "mirror": mirror,
        "segments": segments,
        "geometry": {
            "approach_surface": {"x0": 0.0, "x1": bridge_start, "y0": round(-corridor, 3), "y1": round(corridor, 3), "z": 0.0},
            "red_extensions": red_extensions,
            "stair_steps": stair_steps,
            "launch_surface": {"x0": stair_end, "x1": launcher_end, "y0": round(-corridor, 3), "y1": round(corridor, 3), "z": stair_height},
            "landing_platforms": landing_platforms,
            "outer_walls": {"y0": round(-corridor - 0.45, 3), "y1": round(corridor + 0.45, 3), "height": 2.8},
        },
        "actuators": actuators,
        "launchers": launchers,
        "terminal": terminal,
        "start": start,
        "rules": rules,
        "horizon_seed": rng.randrange(1_000_000),
        "stone_variation": [rng.randrange(6) for _ in range(12)],
    }
    task_id = str(task.get("id") or "rising_causeway_seed_0001@0.1")
    condition_token = f"|difficulty={difficulty}" if condition else ""
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|chamber-v1{condition_token}".encode("utf-8")).hexdigest()[:14]
    public_state: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "asset_manifest": "shared_runtime/assets/provenance/rising_causeway_v0.json",
        "prompt": task.get("natural_language") or "Read the chamber and reach the far terminal.",
        "generator": {
            "name": "rising_causeway_procedural_v1",
            "variant_count": 960,
        },
        "palette": palette,
        "world": {
            "chamber": chamber,
            "red_stage_max": required_red_stage,
            "yellow_options": ["left", "right"],
            "launcher_gallery": launchers,
        },
    }
    ground_truth: dict[str, Any] = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "world": public_state["world"],
        "required_red_stage": required_red_stage,
        "required_stair_end": required_stair_end,
        "required_launcher_id": required_launcher["id"],
        "launch_target": required_launcher["landing"],
        "variant_count": 960,
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth


__all__ = ["MECHANIC_ID", "PROFILES", "generate"]
