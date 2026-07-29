from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "wonky_text_hostile_rendering"
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PLATE_COLORS = ("cyan", "magenta", "amber", "violet", "lime")


def _seed(seed: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{MECHANIC_ID}|v2".encode()).digest()[:8], "big")


def _delta(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _profile(task: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return the selected controlled profile without changing the legacy task."""

    condition = task.get("_control_condition")
    if condition is None:
        return None, {
            "plate_count": 3,
            "token_length": 5,
            "harmonic_values": (2, 3, 4),
            "warp_min": 14.0,
            "warp_max": 24.0,
            "tolerance": 7.5,
            "degrees_per_pixel": 0.62,
            "min_initial_delta_degrees": 55.0,
            "max_event_count": 100,
            "proxy_step_degrees": 5.0,
        }
    if not isinstance(condition, dict):
        raise ValueError("registration control condition must be an object")
    parameters = condition.get("difficulty_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("registration difficulty parameters are missing")
    try:
        profile = {
            "plate_count": int(parameters["plate_count"]),
            "token_length": int(parameters["token_length"]),
            "harmonic_values": tuple(int(value) for value in parameters["harmonic_values"]),
            "warp_min": float(parameters["warp_min"]),
            "warp_max": float(parameters["warp_max"]),
            "tolerance": float(parameters["tolerance"]),
            "degrees_per_pixel": float(parameters["degrees_per_pixel"]),
            "min_initial_delta_degrees": float(parameters["min_initial_delta_degrees"]),
            "max_event_count": int(parameters["max_event_count"]),
            "proxy_step_degrees": float(parameters["proxy_step_degrees"]),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("registration difficulty parameters are incomplete") from exc
    if (
        not 1 <= profile["plate_count"] <= len(PLATE_COLORS)
        or not 3 <= profile["token_length"] <= 7
        or not profile["harmonic_values"]
        or any(not 1 <= value <= 8 for value in profile["harmonic_values"])
        or not 4.0 <= profile["warp_min"] <= profile["warp_max"] <= 40.0
        or not 3.0 <= profile["tolerance"] <= 20.0
        or not 0.35 <= profile["degrees_per_pixel"] <= 1.0
        or not 20.0 <= profile["min_initial_delta_degrees"] <= 120.0
        or not 4 <= profile["max_event_count"] <= 250
        or not 1.0 <= profile["proxy_step_degrees"] <= 15.0
    ):
        raise ValueError("registration difficulty parameters are outside supported bounds")
    return copy.deepcopy(condition), profile


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed(seed))
    condition, profile = _profile(task)
    token = "".join(rng.choice(ALPHABET) for _ in range(profile["token_length"]))
    plates = []
    for index, color in enumerate(PLATE_COLORS[:profile["plate_count"]]):
        target = rng.randrange(0, 360, 5)
        initial = rng.randrange(0, 360, 5)
        while _delta(initial, target) < profile["min_initial_delta_degrees"]:
            initial = rng.randrange(0, 360, 5)
        plates.append({
            "id": f"plate-{index}",
            "color": color,
            "target": target,
            "initial": initial,
            "harmonic": rng.choice(profile["harmonic_values"]),
            "warp": round(rng.uniform(profile["warp_min"], profile["warp_max"]), 2),
        })
    contract = {
        "token": token,
        "plates": plates,
        "tolerance": profile["tolerance"],
        "degrees_per_pixel": profile["degrees_per_pixel"],
        "max_drag_delta": 180,
    }
    difficulty = int((condition or {}).get("difficulty") or 3)
    difficulty_identity = "" if difficulty == 3 else f"|difficulty-{difficulty}"
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|challenge{difficulty_identity}".encode()).hexdigest()[:12]
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "challenge_id": challenge_id,
        "prompt": str(task.get("natural_language") or "Register all three color plates, lock them, then press."),
        "asset_manifest": "shared_runtime/assets/provenance/reviewed_overhaul_v1.json",
        "generator": {
            "name": "anamorphic_registration_press_v2",
            "variant_count": len(ALPHABET) ** profile["token_length"] * 72 ** profile["plate_count"],
        },
        "press": contract,
    }
    truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "seed": seed,
        "challenge_id": challenge_id,
        "press": contract,
    }
    if condition is not None:
        public["control_condition"] = copy.deepcopy(condition)
        truth["control_condition"] = copy.deepcopy(condition)
    return public, truth
