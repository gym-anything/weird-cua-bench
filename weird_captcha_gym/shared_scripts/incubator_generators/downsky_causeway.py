from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "downsky_causeway"


PALETTES = (
    {"name": "apricot", "sky": "#d9f1f2", "haze": "#f8d8bc", "top": "#f4bd83", "edge": "#b86d5b", "accent": "#7559c7"},
    {"name": "mint", "sky": "#c9ece6", "haze": "#f5d8c4", "top": "#b9dd9a", "edge": "#568a76", "accent": "#e2768e"},
    {"name": "lilac", "sky": "#ded9f4", "haze": "#f4d4c9", "top": "#c9a9e8", "edge": "#785a9b", "accent": "#efae4f"},
    {"name": "lemon", "sky": "#edf0c6", "haze": "#f6cdb6", "top": "#e7d77c", "edge": "#aa8a42", "accent": "#5f86ca"},
    {"name": "bluebell", "sky": "#c7e2f2", "haze": "#e9c9d8", "top": "#8dc1d2", "edge": "#4a7594", "accent": "#e47673"},
)


PROFILES: dict[int, dict[str, Any]] = {
    1: {
        "route_count": 3,
        "branch_count": 0,
        "regular_branch_count": 0,
        "terminal_shelf": False,
        "platform_width": 13.2,
        "platform_depth": 10.2,
        "route_step_x": 11.0,
        "route_y_offsets": (0.0, 0.7, 0.0),
        "vertical_drop": 0.9,
        "walkable_gap": 0.45,
        "max_drop": 1.55,
        "move_speed": 4.6,
        "look_sensitivity": 0.008,
    },
    2: {
        "route_count": 4,
        "branch_count": 1,
        "regular_branch_count": 1,
        "terminal_shelf": False,
        "platform_width": 11.8,
        "platform_depth": 9.0,
        "route_step_x": 10.2,
        "route_y_offsets": (0.0, 1.4, -1.4, 0.0),
        "vertical_drop": 0.95,
        "walkable_gap": 0.55,
        "max_drop": 1.65,
        "move_speed": 4.6,
        "look_sensitivity": 0.008,
    },
    3: {
        "route_count": 5,
        "branch_count": 2,
        "regular_branch_count": 2,
        "terminal_shelf": False,
        "platform_width": 10.4,
        "platform_depth": 8.2,
        "route_step_x": 9.8,
        "route_y_offsets": (0.0, 2.0, -2.0, 1.8, 0.0),
        "vertical_drop": 1.0,
        "walkable_gap": 0.62,
        "max_drop": 1.72,
        "move_speed": 4.6,
        "look_sensitivity": 0.008,
    },
    # The pre-control reference configuration. This is intentionally not the
    # default level: the construction audit assigns it L4 after comparing the
    # active route topology and landing precision with the adjacent profiles.
    4: {
        "route_count": 7,
        "branch_count": 4,
        "regular_branch_count": 3,
        "terminal_shelf": True,
        "platform_width": 8.8,
        "platform_depth": 7.2,
        "route_step_x": 9.45,
        "route_y_offsets": (0.0, 2.5, -2.6, 2.2, -2.0, 2.2, 0.0),
        "vertical_drop": 1.05,
        "walkable_gap": 0.72,
        "max_drop": 1.78,
        "move_speed": 4.6,
        "look_sensitivity": 0.008,
    },
    5: {
        "route_count": 9,
        "branch_count": 5,
        "regular_branch_count": 4,
        "terminal_shelf": True,
        "platform_width": 7.9,
        "platform_depth": 6.5,
        "route_step_x": 8.65,
        "route_y_offsets": (0.0, 1.6, -1.7, 1.6, -1.5, 1.5, -1.6, 1.4, 0.0),
        "vertical_drop": 1.08,
        "walkable_gap": 0.78,
        "max_drop": 1.82,
        "move_speed": 4.6,
        "look_sensitivity": 0.008,
    },
}


def _seed_int(seed: str, salt: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).digest()[:8], "big")


def _center_distance_to_rect(x: float, y: float, platform: dict[str, Any]) -> float:
    cx, cy = map(float, platform["center"][:2])
    width, depth = map(float, platform["size"])
    dx = max(abs(x - cx) - width / 2, 0.0)
    dy = max(abs(y - cy) - depth / 2, 0.0)
    return math.hypot(dx, dy)


def _platform(
    platform_id: str,
    x: float,
    y: float,
    z: float,
    width: float,
    depth: float,
    palette: dict[str, str],
    rng: random.Random,
    kind: str = "terrace",
) -> dict[str, Any]:
    return {
        "id": platform_id,
        "center": [round(x, 3), round(y, 3), round(z, 3)],
        "size": [round(width, 3), round(depth, 3)],
        "thickness": round(0.34 + rng.random() * 0.08, 3),
        "tone": rng.randrange(5),
        "kind": kind,
        "stripe": rng.randrange(4),
    }


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = copy.deepcopy(task.get("_control_condition"))
    difficulty = int((condition or {}).get("difficulty", 4))
    if difficulty not in PROFILES:
        raise ValueError(f"unknown Downsky difficulty {difficulty}")
    profile = copy.deepcopy(PROFILES[difficulty])
    if condition is not None:
        supplied_parameters = condition.get("difficulty_parameters") or {}
        for name, value in supplied_parameters.items():
            if name in profile:
                profile[name] = copy.deepcopy(value)
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    palette = copy.deepcopy(PALETTES[rng.randrange(len(PALETTES))])
    mirror = -1 if rng.randrange(2) else 1
    base_y = rng.uniform(-1.0, 1.0)
    route_count = int(profile["route_count"])
    width = float(profile["platform_width"])
    depth = float(profile["platform_depth"])
    step_x = float(profile["route_step_x"])
    drops = float(profile["vertical_drop"])
    y_offsets = list(profile["route_y_offsets"])
    z_start = 13.0 + rng.uniform(-0.25, 0.25)

    route: list[dict[str, Any]] = []
    for index in range(route_count):
        x = 7.0 + index * step_x
        y = base_y + y_offsets[index % len(y_offsets)] * mirror
        z = z_start - index * drops
        kind = "exit" if index == route_count - 1 else "terrace"
        route.append(_platform(f"terrace-{index + 1:02d}", x, y, z, width, depth, palette, rng, kind))

    platforms = list(route)
    branch_ids: list[str] = []
    regular_branch_count = int(profile.get("regular_branch_count", profile["branch_count"]))
    branch_indices = list(range(1, route_count - 1, max(1, (route_count - 1) // max(1, regular_branch_count))))[
        :regular_branch_count
    ]
    for branch_number, route_index in enumerate(branch_indices, start=1):
        source = route[route_index]
        sign = -1 if (branch_number + (1 if mirror < 0 else 0)) % 2 else 1
        branch_depth = max(4.4, depth * 0.72)
        branch_y = float(source["center"][1]) + sign * (depth / 2 + branch_depth / 2 + float(profile["walkable_gap"]) * 0.78)
        branch_x = float(source["center"][0]) + width * 0.24
        branch_z = float(source["center"][2]) - drops * (0.65 + rng.random() * 0.1)
        branch_id = f"side-terrace-{branch_number:02d}"
        branch_ids.append(branch_id)
        platforms.append(_platform(branch_id, branch_x, branch_y, branch_z, width * 0.7, branch_depth, palette, rng))

    # A small lower shelf near the pavilion creates a tempting but visibly
    # terminal descent on the harder profiles without changing the intended
    # route's physical reachability. branch_count is the public total; the
    # separate regular count keeps this exact geometry explicit.
    if bool(profile.get("terminal_shelf", False)):
        source = route[-2]
        lower_id = "side-terrace-final"
        branch_ids.append(lower_id)
        platforms.append(_platform(
            lower_id,
            float(source["center"][0]) + width * 0.2,
            float(source["center"][1]) - mirror * (depth * 1.25),
            float(source["center"][2]) - drops * 0.8,
            width * 0.62,
            depth * 0.62,
            palette,
            rng,
        ))

    if len(branch_ids) != int(profile["branch_count"]):
        raise ValueError(
            f"profile branch_count={profile['branch_count']} generated {len(branch_ids)} shelves"
        )

    start = {
        "platform_id": route[0]["id"],
        "position": [float(route[0]["center"][0]), float(route[0]["center"][1]), float(route[0]["center"][2])],
        "heading": math.atan2(float(route[1]["center"][1]) - float(route[0]["center"][1]), float(route[1]["center"][0]) - float(route[0]["center"][0])),
        "pitch": -0.04,
    }
    exit_platform = route[-1]
    clouds = []
    for index in range(8 + difficulty * 2):
        clouds.append({
            "x": round(rng.uniform(-12, 78), 2),
            "y": round(rng.uniform(-26, 30), 2),
            "z": round(rng.uniform(5.0, 19.0), 2),
            "scale": round(rng.uniform(0.65, 1.65), 2),
            "tone": rng.randrange(4),
        })

    rules = {
        "player_radius": 0.34,
        "eye_height": 1.42,
        "move_speed": float(profile["move_speed"]),
        "tick_ms": 40,
        "max_drop": float(profile["max_drop"]),
        "walkable_gap": float(profile["walkable_gap"]),
        "look_sensitivity": float(profile["look_sensitivity"]),
        "fall_depth": 4.5,
        # One floor-disc radius for rendering, browser contact, and replay.
        # Preserve the original browser's centered-contact requirement.
        "finish_radius": 0.3,
        "world_floor_z": -1.0,
    }
    task_id = str(task.get("id") or "downsky_causeway_seed_0001@0.1")
    difficulty_token = f"|difficulty={difficulty}" if condition else ""
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|causeway-v2{difficulty_token}".encode("utf-8")).hexdigest()[:14]
    public_state: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "asset_manifest": "shared_runtime/assets/provenance/downsky_causeway_v0.json",
        "prompt": task.get("natural_language") or "Reach the illuminated pavilion.",
        "generator": {
            "name": "downsky_causeway_procedural_v2",
            "variant_count": len(PALETTES) * 2 * 4,
        },
        "palette": palette,
        "world": {
            "platforms": platforms,
            "clouds": clouds,
            "start": start,
            "exit_platform_id": exit_platform["id"],
            "rules": rules,
            "horizon_seed": rng.randrange(1_000_000),
        },
    }
    ground_truth: dict[str, Any] = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "world": public_state["world"],
        "route_platform_ids": [item["id"] for item in route],
        "route_waypoints": [item["center"] for item in route],
        "branch_platform_ids": branch_ids,
        "variant_count": public_state["generator"]["variant_count"],
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth


__all__ = ["MECHANIC_ID", "PROFILES", "generate"]
