from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "quiet_transfer"
STAGE = {"width": 900, "height": 430}

# The unconditioned task is deliberately the approved L3/full baseline.  The
# materializer supplies the same parameters plus a control condition for the
# ten controlled variants.
BASELINE_PARAMETERS: dict[str, Any] = {
    "knot_count": 9,
    "playback_ticks": 44,
    "tick_ms": 32,
    "spring_strength": 1.0,
    "fidelity_threshold": 0.86,
    "initial_jitter": 0.15,
    "nudge_step": 0.02,
    "show_numeric_state": True,
    "show_target_outline": True,
    "base_width": 0.085,
    "well_separation": 0.72,
    # These goal parameters are part of the original L3 baseline design.  The
    # seed-specific route produces a visible final wave-state goal; it is not
    # used as an undisclosed curve answer by the grader.
    "target_variation": 0.09,
    "target_bends": 3,
}


def _seed_int(seed: str) -> int:
    return int.from_bytes(
        hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode("utf-8")).digest()[:8],
        "big",
    )


def _round_step(value: float, step: float) -> float:
    return round(round(float(value) / step) * step, 4)


def _smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, float(value)))
    return value * value * (3.0 - 2.0 * value)


def _seeded_target_curve(
    *,
    source: float,
    destination: float,
    knot_count: int,
    step: float,
    seed: str,
    variation: float,
    bends: int,
) -> list[float]:
    """Build the seed-specific route used to derive the visible goal state.

    The smoothstep path is only a useful visual starting point.  A separate
    seed stream adds a phase-shifted, bounded route signature at the visible
    knot locations.  Quantising the result keeps the simplified nudge surface
    exactly equivalent to direct dragging.  The browser renders the terminal
    state produced by this route as the public goal.
    """
    route_rng = random.Random(_seed_int(f"{seed}|target-route"))
    phase_a = route_rng.random() * math.tau
    phase_b = route_rng.random() * math.tau
    span = destination - source
    target: list[float] = []
    for index in range(knot_count):
        if index == 0:
            target.append(source)
            continue
        if index == knot_count - 1:
            target.append(destination)
            continue
        fraction = index / (knot_count - 1)
        baseline = source + span * _smoothstep(fraction)
        envelope = math.sin(math.pi * fraction) ** 1.15
        wave = (
            0.58 * math.sin((bends + 1) * math.pi * fraction + phase_a)
            + 0.28 * math.sin((bends + 2) * math.pi * fraction + phase_b)
            + 0.14 * route_rng.uniform(-1.0, 1.0)
        )
        value = _round_step(baseline + variation * envelope * wave, step)
        target.append(max(0.05, min(0.95, value)))
    return target


def _interpolate_curve(curve: list[float], tick: int, ticks: int) -> float:
    if ticks <= 0:
        return float(curve[-1])
    position = max(0.0, min(1.0, float(tick) / float(ticks))) * (len(curve) - 1)
    index = min(len(curve) - 2, max(0, int(math.floor(position))))
    fraction = position - index
    return float(curve[index]) * (1.0 - fraction) + float(curve[index + 1]) * fraction


def _terminal_state(curve: list[float], playback_ticks: int, wave_model: dict[str, float]) -> dict[str, float]:
    """Replay the route once to materialize the public, visible goal state."""
    dt = float(wave_model["dt"])
    spring = float(wave_model["spring_strength"])
    damping = float(wave_model["velocity_damping"])
    excitation = float(wave_model["excitation_gain"])
    width_damping = float(wave_model["width_damping"])
    width_restore = float(wave_model["width_restore"])
    base_width = float(wave_model["base_width"])
    center = float(curve[0])
    velocity = 0.0
    width = base_width
    width_velocity = 0.0
    previous_trap = float(curve[0])
    previous_previous_trap = float(curve[0])
    for current_tick in range(1, max(0, int(playback_ticks)) + 1):
        trap = _interpolate_curve(curve, current_tick, playback_ticks)
        acceleration = trap - 2.0 * previous_trap + previous_previous_trap
        velocity += (3.5 * spring * (trap - center) - damping * velocity) * dt
        center += velocity * dt
        width_velocity += (
            abs(acceleration) * excitation
            - width_damping * width_velocity
            - width_restore * (width - base_width)
        ) * dt
        width += width_velocity * dt
        previous_previous_trap, previous_trap = previous_trap, trap
    return {
        "center": center,
        "velocity": velocity,
        "width": width,
        "width_velocity": width_velocity,
        "phase": velocity * 4.0 + width_velocity * 8.0,
    }


def _profile(task: dict[str, Any]) -> tuple[dict[str, Any], int, str, bool]:
    condition = task.get("_control_condition")
    if condition:
        parameters = copy.deepcopy(condition.get("difficulty_parameters") or {})
        difficulty = int(condition.get("difficulty") or 3)
        interaction = str(condition.get("interaction") or "full")
        return parameters, difficulty, interaction, True
    return copy.deepcopy(BASELINE_PARAMETERS), 3, "full", False


def _wave_model(parameters: dict[str, Any]) -> dict[str, float]:
    return {
        "dt": 0.09,
        "spring_strength": float(parameters["spring_strength"]),
        "velocity_damping": 1.85,
        "excitation_gain": 7.0,
        "width_damping": 2.2,
        "width_restore": 9.0,
        "base_width": float(parameters["base_width"]),
    }


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed_int(seed))
    parameters, difficulty, interaction, conditioned = _profile(task)
    knot_count = int(parameters["knot_count"])
    playback_ticks = int(parameters["playback_ticks"])
    tick_ms = int(parameters["tick_ms"])
    step = float(parameters["nudge_step"])
    target_variation = float(parameters.get("target_variation", 0.0))
    target_bends = int(parameters.get("target_bends", 0))
    if not 5 <= knot_count <= 15 or playback_ticks < 24 or tick_ms < 15:
        raise ValueError("quiet-transfer profile is outside supported limits")
    if not 0.5 <= float(parameters["spring_strength"]) <= 1.6:
        raise ValueError("quiet-transfer spring strength is outside supported limits")
    if not 0.5 <= float(parameters["fidelity_threshold"]) < 1.0:
        raise ValueError("quiet-transfer fidelity threshold is invalid")
    if not 0.0 <= target_variation <= 0.25:
        raise ValueError("quiet-transfer target variation is outside supported limits")
    if not 1 <= target_bends <= 8:
        raise ValueError("quiet-transfer target bend count is outside supported limits")

    # World geometry is shared by both interaction surfaces.  The two wells
    # are deliberately separated enough that a visually plausible endpoint
    # can still leave the packet moving or spread out.
    source = _round_step(rng.uniform(0.12, 0.20), step)
    destination = _round_step(source + float(parameters["well_separation"]), step)
    destination = min(0.90, max(source + 0.52, destination))
    destination = _round_step(destination, step)

    target_curve = _seeded_target_curve(
        source=source,
        destination=destination,
        knot_count=knot_count,
        step=step,
        seed=seed,
        variation=target_variation,
        bends=target_bends,
    )

    jitter = float(parameters["initial_jitter"])
    phase = rng.random() * math.tau
    initial_curve = []
    for index, target in enumerate(target_curve):
        if index == 0:
            initial_curve.append(source)
            continue
        if index == knot_count - 1:
            initial_curve.append(destination)
            continue
        wave = math.sin(index * 1.71 + phase) * 0.55 + rng.uniform(-0.45, 0.45)
        value = target + jitter * wave
        # The proxy nudge surface must be able to reach the same public target
        # as direct dragging.  Keep the generated seed on its declared grid;
        # otherwise a fixed-size nudge can remain forever offset from a
        # quantized target by a hidden fractional remainder.
        # Round inside the editable interval, not to an out-of-bounds knot
        # (for example 0.05 rounds to 0.04 on the L3 0.02 grid).
        lower_grid = math.ceil(0.05 / step - 1e-9) * step
        upper_grid = math.floor(0.95 / step + 1e-9) * step
        initial_curve.append(round(max(lower_grid, min(upper_grid, _round_step(value, step))), 4))

    palette = rng.choice(
        (
            {"ink": "#07151d", "cyan": "#7de8e1", "violet": "#9b8cff", "gold": "#ffd166"},
            {"ink": "#130d1f", "cyan": "#64e6ff", "violet": "#d48bff", "gold": "#f9d56e"},
            {"ink": "#081b19", "cyan": "#84f0c4", "violet": "#91a7ff", "gold": "#f4c95d"},
        )
    )
    task_id = str(task.get("id") or f"{MECHANIC_ID}_seed_0001@0.1")
    if conditioned:
        condition_token = f"|d{difficulty}|{interaction}|{task_id}"
    else:
        condition_token = "|baseline"
    challenge_id = hashlib.sha256(
        f"{seed}|{MECHANIC_ID}{condition_token}".encode("utf-8")
    ).hexdigest()[:12]
    wave_model = _wave_model(parameters)
    goal_state = _terminal_state(target_curve, playback_ticks, wave_model)
    curve_config = {
        "knot_count": knot_count,
        "minimum": 0.05,
        "maximum": 0.95,
        "nudge_step": step,
        "playback_ticks": playback_ticks,
        "tick_ms": tick_ms,
    }
    requirements = {
        "fidelity_threshold": float(parameters["fidelity_threshold"]),
        "minimum_playbacks": 2,
        "revision_required": True,
        "destination_position": destination,
        "base_width": float(parameters["base_width"]),
        "goal_state": goal_state,
        "numeric_state_readout": bool(parameters["show_numeric_state"]),
        "target_outline": bool(parameters["show_target_outline"]),
    }
    prompt = task.get("natural_language") or "Match the dashed wave state with a revised transfer."
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": prompt,
        "submit_label": "CERTIFY QUIET TRANSFER",
        "stage": STAGE,
        "difficulty_level": difficulty,
        "interaction_mode": interaction,
        "source": {"position": source, "label": "SOURCE WELL"},
        "destination": {"position": destination, "label": "QUIET DESTINATION"},
        "curve": {**curve_config, "initial": initial_curve},
        "wave_model": wave_model,
        "requirements": requirements,
        "palette": palette,
        "generator": {
            "name": "reduced_order_quiet_wave_transfer_v1",
            "variant_count": 10**10,
            "variation_kind": "seeded well spacing, visible terminal goal state, perturbation, palette, and wave phase",
        },
        "asset_manifest": "shared_runtime/assets/provenance/quiet_transfer_v0.json",
    }
    truth = {
        **copy.deepcopy(public),
        "seed": seed,
        "target_curve": target_curve,
        "target_phase": round(phase, 5),
    }
    if conditioned:
        condition = copy.deepcopy(task["_control_condition"])
        public["control_condition"] = condition
        truth["control_condition"] = copy.deepcopy(condition)
    return public, truth
