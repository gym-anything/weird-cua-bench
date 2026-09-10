from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "restless_piston"
ASSET_MANIFEST = "shared_runtime/assets/provenance/restless_piston_v0.json"

MODE_LABELS = {
    "nothing": "Nothing",
    "volume": "Volume (V)",
    "temperature": "Temperature (T)",
    "pressure_v": "Pressure with V varying",
    "pressure_t": "Pressure with T varying",
}
MODE_ACTIONS = {
    "nothing": ("pump", "heat", "wall"),
    "volume": ("pump", "heat"),
    "temperature": ("pump", "wall"),
    "pressure_v": ("pump", "heat"),
    "pressure_t": ("pump", "wall"),
}

# This is also the exact configuration of the original, uncontrolled task.
# The controlled L3 profile below intentionally uses the same values so that
# the baseline can be compared at a fixed seed without a hidden world change.
BASE_PARAMETERS: dict[str, Any] = {
    "action_count": 5,
    "mode_pool": ["nothing", "volume", "temperature", "pressure_v"],
    "particle_count": 30,
    "pump_delta": 2,
    "heat_delta": 10.0,
    "wall_delta": 0.06,
    "pressure_tolerance": 0.33,
    "temperature_tolerance": 5.0,
    "volume_tolerance": 0.026,
    "settle_ticks": 6,
    "max_ticks": 220,
    "gauge_noise_ratio": 0.07,
    "tick_ms": 80,
    "min_volume": 0.56,
    "max_volume": 1.20,
    "min_temperature": 230.0,
    "max_temperature": 430.0,
}


def _seed(seed: str) -> int:
    return int(hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode()).hexdigest()[:16], 16)


def _identity(task: dict[str, Any], seed: str) -> tuple[random.Random, dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed(seed))
    task_id = str(task.get("id") or f"{MECHANIC_ID}_seed_0001@0.1")
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode()).hexdigest()[:12]
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "asset_manifest": ASSET_MANIFEST,
        "source_anchors": ["XUIF-237"],
        "prompt": task.get("natural_language") or "Reach the operating conditions without chasing the noisy gauge.",
    }
    truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "seed": seed,
        "source_anchors": ["XUIF-237"],
    }
    return rng, public, truth


def _pressure(particles: int, temperature: float, volume: float) -> float:
    return float(particles) * float(temperature) / (float(volume) * 1000.0)


def _condition(task: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    condition = copy.deepcopy(task.get("_control_condition"))
    parameters = dict((condition or {}).get("difficulty_parameters") or BASE_PARAMETERS)
    if not condition:
        parameters = copy.deepcopy(BASE_PARAMETERS)
    return condition, parameters


def _apply_action(
    state: dict[str, float],
    action: str,
    direction: int,
    parameters: dict[str, Any],
    mode: str,
    reference_pressure: float,
) -> bool:
    if action not in MODE_ACTIONS.get(mode, ()):
        return False
    sign = 1 if int(direction) > 0 else -1
    if action == "pump":
        state["particles"] += sign * int(parameters["pump_delta"])
        if state["particles"] < 6 or state["particles"] > 92:
            return False
    elif action == "heat":
        state["temperature"] += sign * float(parameters["heat_delta"])
        if not float(parameters["min_temperature"]) <= state["temperature"] <= float(parameters["max_temperature"]):
            return False
    elif action == "wall":
        state["volume"] += sign * float(parameters["wall_delta"])
        if not float(parameters["min_volume"]) <= state["volume"] <= float(parameters["max_volume"]):
            return False

    if mode == "pressure_v" and action in {"pump", "heat"}:
        state["volume"] = _pressure_volume(state, reference_pressure)
        if not float(parameters["min_volume"]) <= state["volume"] <= float(parameters["max_volume"]):
            return False
    if mode == "pressure_t" and action in {"pump", "wall"}:
        if state["particles"] <= 0:
            return False
        state["temperature"] = reference_pressure * 1000.0 * state["volume"] / state["particles"]
        if not float(parameters["min_temperature"]) <= state["temperature"] <= float(parameters["max_temperature"]):
            return False
    return True


def _pressure_volume(state: dict[str, float], reference_pressure: float) -> float:
    return float(state["particles"]) * float(state["temperature"]) / (float(reference_pressure) * 1000.0)


def _generate_plan(
    rng: random.Random,
    parameters: dict[str, Any],
    mode: str,
) -> tuple[dict[str, float], list[dict[str, Any]], float]:
    allowed = tuple(MODE_ACTIONS[mode])
    count = int(parameters["action_count"])
    if count < 1 or not allowed:
        raise ValueError("restless piston profile has no usable actions")
    for _attempt in range(1200):
        initial = {
            "particles": float(max(8, int(parameters["particle_count"]) + rng.randint(-2, 2))),
            "temperature": float(rng.randint(282, 322)),
            "volume": round(rng.uniform(0.72, 0.91), 3),
        }
        reference_pressure = _pressure(initial["particles"], initial["temperature"], initial["volume"])
        state = dict(initial)
        plan: list[dict[str, Any]] = []
        # The first actions cover distinct control families whenever the
        # profile permits it. Later actions are dependent corrections on the
        # state produced by those earlier actions.
        action_types = list(allowed[: min(len(allowed), count)])
        while len(action_types) < count:
            action_types.append(rng.choice(allowed))
        rng.shuffle(action_types)
        valid = True
        for action in action_types:
            direction = rng.choice((-1, 1))
            before = dict(state)
            if not _apply_action(state, action, direction, parameters, mode, reference_pressure):
                valid = False
                break
            plan.append({"action": action, "direction": direction, "before": before, "after": dict(state)})
        if not valid:
            continue
        changed = [key for key in ("particles", "temperature", "volume") if abs(state[key] - initial[key]) > 1e-6]
        if len(changed) < (2 if count >= 2 else 1):
            continue
        return initial, plan, reference_pressure
    raise RuntimeError(f"could not author a feasible {mode} piston plan")


def _particle_cloud(rng: random.Random, count: int) -> list[dict[str, Any]]:
    colors = ("#f6c85f", "#7fd6d0", "#f08770", "#c59cff")
    particles = []
    for index in range(count):
        angle = rng.random() * math.tau
        speed = rng.uniform(0.0045, 0.011)
        particles.append({
            "id": f"molecule-{index + 1}",
            "x": round(rng.uniform(0.05, 0.95), 5),
            "y": round(rng.uniform(0.08, 0.92), 5),
            "vx": round(math.cos(angle) * speed, 6),
            "vy": round(math.sin(angle) * speed, 6),
            "radius": rng.choice((4, 5, 6)),
            "color": colors[index % len(colors)],
        })
    return particles


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng, public, truth = _identity(task, seed)
    condition, parameters = _condition(task)
    mode_pool = tuple(str(item) for item in parameters.get("mode_pool") or ())
    if not mode_pool or any(item not in MODE_LABELS for item in mode_pool):
        raise ValueError("restless piston mode pool is invalid")
    if condition:
        challenge_id = hashlib.sha256(
            f"{seed}|{MECHANIC_ID}|d{condition['difficulty']}|{condition['interaction']}|{task.get('id')}".encode()
        ).hexdigest()[:12]
        public["challenge_id"] = challenge_id
        truth["challenge_id"] = challenge_id
    required_mode = rng.choice(mode_pool)
    initial, plan, reference_pressure = _generate_plan(rng, parameters, required_mode)
    final = dict(plan[-1]["after"] if plan else initial)
    pressure = _pressure(final["particles"], final["temperature"], final["volume"])
    tolerances = {
        "pressure": float(parameters["pressure_tolerance"]),
        "temperature": float(parameters["temperature_tolerance"]),
        "volume": float(parameters["volume_tolerance"]),
    }
    particles = _particle_cloud(rng, int(initial["particles"]))
    physics = {
        "tick_ms": int(parameters["tick_ms"]),
        "max_ticks": int(parameters["max_ticks"]),
        "min_volume": float(parameters["min_volume"]),
        "max_volume": float(parameters["max_volume"]),
        "min_temperature": float(parameters["min_temperature"]),
        "max_temperature": float(parameters["max_temperature"]),
        "pump_delta": int(parameters["pump_delta"]),
        "heat_delta": float(parameters["heat_delta"]),
        "wall_delta": float(parameters["wall_delta"]),
        "gauge_noise_ratio": float(parameters["gauge_noise_ratio"]),
        "settle_ticks": int(parameters["settle_ticks"]),
    }
    goal = {
        "required_mode": required_mode,
        "required_mode_label": MODE_LABELS[required_mode],
        "pressure": round(pressure, 3),
        "temperature": round(final["temperature"], 2),
        "volume": round(final["volume"], 4),
        "tolerances": tolerances,
        "settle_ticks": int(parameters["settle_ticks"]),
    }
    initial_public = {
        "particles": int(initial["particles"]),
        "temperature": round(initial["temperature"], 2),
        "volume": round(initial["volume"], 4),
        "pressure": round(_pressure(initial["particles"], initial["temperature"], initial["volume"]), 3),
    }
    active_mode_options = [
        {"id": key, "label": MODE_LABELS[key]}
        for key in mode_pool
    ]
    public.update({
        "generator": {"name": "restless_ideal_gas_piston_v1", "variant_count": 10**15},
        "mode_options": active_mode_options,
        "initial": initial_public,
        "reference_pressure": round(reference_pressure, 8),
        "goal": goal,
        "physics": physics,
        "particles": particles,
        "chamber": {"width": 640, "height": 300, "min_volume": physics["min_volume"], "max_volume": physics["max_volume"]},
    })
    # Controlled tasks expose their input surface through the shared
    # control_condition.  Keeping that surface-only value out of the public
    # world makes the full/simplified pair fingerprint the same generated
    # chamber.  The original seed still carries a fallback for direct play.
    if not condition:
        public["interaction_mode"] = "simplified"
    truth.update({
        "initial": initial,
        "goal": goal,
        "physics": physics,
        "reference_pressure": reference_pressure,
        "mode_options": list(mode_pool),
        "planned_actions": [{"action": item["action"], "direction": item["direction"]} for item in plan],
        "interaction_mode": str((condition or {}).get("interaction") or "simplified"),
    })
    if condition:
        public["control_condition"] = copy.deepcopy(condition)
        truth["control_condition"] = copy.deepcopy(condition)
    return public, truth
