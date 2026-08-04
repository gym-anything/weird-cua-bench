from __future__ import annotations

import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "trajectory_catcher"
CANVAS_WIDTH = 900
CANVAS_HEIGHT = 480
FAMILIES = ("ballistic_arc", "sine_drift", "cubic_hook")
PALETTES = ("flight-recorder", "night-range", "oxide-plotter")
VARIANT_COUNT = 3**3 * 2**3 * 10_000_000_000

# L4 reproduces the historical generator byte-for-byte apart from the explicit
# controlled-condition envelope added to its public and hidden state.  Keep
# these values in sync with trajectory_catcher_env/controls.json.
BASELINE_PARAMETERS: dict[str, Any] = {
    "round_count": 3,
    "family_pool": list(FAMILIES),
    "duration_min_ms": 6000,
    "duration_max_ms": 6600,
    "duration_step_ms": 100,
    "wall_enter_min_ms": 1550,
    "wall_enter_max_ms": 1850,
    "wall_timing_step_ms": 50,
    "wall_exit_min_ms": 4300,
    "wall_exit_max_exclusive_ms": 4851,
    "minimum_post_exit_ms": 1150,
    "minimum_observation_ms": 1000,
    "commit_margin_ms": 180,
    "base_y_min": 218,
    "base_y_max": 262,
    "amplitude_min": 52,
    "amplitude_max": 78,
    "wobble_min": 11,
    "wobble_max": 20,
    "phase_min": -0.42,
    "phase_max": 0.42,
    "projectile_radius_min": 9,
    "projectile_radius_max": 13,
    "alignment_tolerance_deg": 22,
    "capture_depth": 64,
    "aperture_min": 60,
    "aperture_max": 120,
    "aperture_step": 10,
    "initial_catcher": {"x": 450.0, "y": 427.0, "angle_deg": 0, "aperture": 70},
    "rotation_step_deg": 15,
    "replay_limit": 1,
}


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _path(round_data: dict[str, Any], t_ms: float) -> tuple[float, float]:
    duration = float(round_data["duration_ms"])
    u = _clamp(t_ms / duration, 0.0, 1.0)
    travel = u if round_data["direction"] == "ltr" else 1.0 - u
    x = 70.0 + travel * 760.0
    base = float(round_data["base_y"])
    amplitude = float(round_data["amplitude"])
    wobble = float(round_data["wobble"])
    phase = float(round_data["phase"])
    if round_data["family"] == "ballistic_arc":
        y = base + amplitude * (4.0 * u * (1.0 - u) - 0.48) + wobble * math.sin(math.tau * u + phase)
    elif round_data["family"] == "sine_drift":
        y = base + amplitude * math.sin(math.tau * (u + phase)) + wobble * math.sin(6.0 * math.pi * u)
    else:
        centered = 2.0 * u - 1.0
        y = base + amplitude * (centered**3 - 0.34 * centered) + wobble * math.sin(4.0 * math.pi * u + phase)
    return x, y


def _velocity_angle(round_data: dict[str, Any], t_ms: float) -> float:
    before = _path(round_data, max(0.0, t_ms - 6.0))
    after = _path(round_data, min(float(round_data["duration_ms"]), t_ms + 6.0))
    return math.degrees(math.atan2(after[1] - before[1], after[0] - before[0])) % 360.0


def _local(point: tuple[float, float], catcher: dict[str, Any]) -> tuple[float, float]:
    radians = math.radians(float(catcher["angle_deg"]))
    cosine, sine = math.cos(radians), math.sin(radians)
    dx, dy = point[0] - float(catcher["x"]), point[1] - float(catcher["y"])
    return dx * cosine + dy * sine, -dx * sine + dy * cosine


def _angle_error(first: float, second: float) -> float:
    return abs((first - second + 90.0) % 180.0 - 90.0)


def _swept_catch(round_data: dict[str, Any], catcher: dict[str, Any]) -> tuple[bool, float | None]:
    if not catcher.get("armed"):
        return False, None
    start = float(round_data["wall_exit_ms"])
    end = float(round_data["duration_ms"])
    step = 5.0
    projectile_radius = float(round_data["projectile_radius"])
    clear_half_aperture = float(catcher["aperture"]) / 2.0 - projectile_radius
    clear_half_depth = float(round_data["capture_depth"]) / 2.0 - projectile_radius
    current_t = start
    while current_t <= end + 1e-6:
        local = _local(_path(round_data, current_t), catcher)
        aligned = _angle_error(_velocity_angle(round_data, current_t), float(catcher["angle_deg"])) <= float(round_data["alignment_tolerance_deg"]) + 1e-9
        if clear_half_aperture >= 0 and clear_half_depth >= 0 and abs(local[0]) <= clear_half_depth and abs(local[1]) <= clear_half_aperture and aligned:
            return True, current_t
        current_t += step
    return False, None


def _integer(parameters: dict[str, Any], key: str) -> int:
    return int(parameters[key])


def _controlled_parameters(task: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    condition = task.get("_control_condition")
    if condition is None:
        return None, BASELINE_PARAMETERS
    if not isinstance(condition, dict):
        raise ValueError("controlled trajectory catcher condition is not an object")
    if int(condition.get("difficulty") or 0) not in {1, 2, 3, 4, 5}:
        raise ValueError("controlled trajectory catcher has an invalid difficulty")
    if str(condition.get("interaction") or "") not in {"simplified", "full"}:
        raise ValueError("controlled trajectory catcher has an invalid interaction")
    parameters = dict(condition.get("difficulty_parameters") or {})
    if not parameters:
        raise ValueError("controlled trajectory catcher is missing difficulty parameters")
    required = set(BASELINE_PARAMETERS)
    missing = sorted(required - set(parameters))
    if missing:
        raise ValueError(f"controlled trajectory catcher is missing parameters: {', '.join(missing)}")
    return condition, parameters


def _round(
    rng: random.Random,
    seed: str,
    index: int,
    family: str,
    parameters: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    duration = rng.randrange(
        _integer(parameters, "duration_min_ms"),
        _integer(parameters, "duration_max_ms") + 1,
        _integer(parameters, "duration_step_ms"),
    )
    wall_enter = rng.randrange(
        _integer(parameters, "wall_enter_min_ms"),
        _integer(parameters, "wall_enter_max_ms") + 1,
        _integer(parameters, "wall_timing_step_ms"),
    )
    wall_exit = rng.randrange(
        _integer(parameters, "wall_exit_min_ms"),
        min(_integer(parameters, "wall_exit_max_exclusive_ms"), duration - _integer(parameters, "minimum_post_exit_ms")),
        _integer(parameters, "wall_timing_step_ms"),
    )
    direction = rng.choice(("ltr", "rtl"))
    base_y = rng.randint(_integer(parameters, "base_y_min"), _integer(parameters, "base_y_max"))
    amplitude = rng.randint(_integer(parameters, "amplitude_min"), _integer(parameters, "amplitude_max"))
    wobble = rng.randint(_integer(parameters, "wobble_min"), _integer(parameters, "wobble_max"))
    phase = round(rng.uniform(float(parameters["phase_min"]), float(parameters["phase_max"])), 3)
    projectile_radius = rng.randint(_integer(parameters, "projectile_radius_min"), _integer(parameters, "projectile_radius_max"))
    initial_catcher = dict(parameters["initial_catcher"])
    round_data: dict[str, Any] = {
        "id": f"flight-{index + 1}-{hashlib.sha256(f'{seed}|flight|{index}'.encode()).hexdigest()[:5]}",
        "sequence": index,
        "family": family,
        "direction": direction,
        "duration_ms": duration,
        "wall_enter_ms": wall_enter,
        "wall_exit_ms": wall_exit,
        "minimum_observation_ms": _integer(parameters, "minimum_observation_ms"),
        "commit_margin_ms": _integer(parameters, "commit_margin_ms"),
        "base_y": base_y,
        "amplitude": amplitude,
        "wobble": wobble,
        "phase": phase,
        "projectile_radius": projectile_radius,
        "alignment_tolerance_deg": _integer(parameters, "alignment_tolerance_deg"),
        "capture_depth": _integer(parameters, "capture_depth"),
        "initial_catcher": {"x": float(initial_catcher["x"]), "y": float(initial_catcher["y"]), "angle_deg": _integer(initial_catcher, "angle_deg"), "aperture": _integer(initial_catcher, "aperture")},
        "aperture_min": _integer(parameters, "aperture_min"),
        "aperture_max": _integer(parameters, "aperture_max"),
        "aperture_step": _integer(parameters, "aperture_step"),
        "rotation_step_deg": _integer(parameters, "rotation_step_deg"),
        "replay_limit": _integer(parameters, "replay_limit"),
    }
    enter_x = _path(round_data, wall_enter)[0]
    exit_x = _path(round_data, wall_exit)[0]
    round_data["wall"] = {
        "x": round(min(enter_x, exit_x) - 24, 2),
        "width": round(abs(exit_x - enter_x) + 48, 2),
        "y": 18,
        "height": CANVAS_HEIGHT - 36,
    }
    # These values choose a safe generated reference crossing; they are not a
    # difficulty profile because they do not change the visible flight or the
    # player's catch contract.
    catch_time = min(duration - 520, wall_exit + rng.randrange(520, 801, 40))
    catch_x, catch_y = _path(round_data, catch_time)
    tangent = _velocity_angle(round_data, catch_time)
    angle = int(round(tangent / _integer(parameters, "rotation_step_deg")) * _integer(parameters, "rotation_step_deg")) % 180
    feasible_apertures = tuple(
        value for value in (80, 90, 100, 110)
        if int(round_data["aperture_min"]) <= value <= int(round_data["aperture_max"])
    )
    if not feasible_apertures:
        raise RuntimeError("trajectory catcher profile has no feasible capture aperture")
    aperture = rng.choice(feasible_apertures)
    solution = {
        "x": round(catch_x, 2),
        "y": round(catch_y, 2),
        "angle_deg": angle,
        "aperture": aperture,
        "catch_time_ms": catch_time,
    }
    solved = {**solution, "armed": True}
    caught, actual_time = _swept_catch(round_data, solved)
    if not caught:
        raise RuntimeError("generated catcher solution does not intersect the swept flight")
    solution["actual_crossing_ms"] = round(float(actual_time), 2)
    safe_initials = (
        round_data["initial_catcher"],
        {"x": 450.0, "y": 52.0, "angle_deg": 0, "aperture": _integer(initial_catcher, "aperture")},
        {"x": 82.0, "y": 430.0, "angle_deg": 90, "aperture": _integer(parameters, "aperture_min")},
        {"x": 818.0, "y": 54.0, "angle_deg": 90, "aperture": _integer(parameters, "aperture_min")},
    )
    round_data["initial_catcher"] = next(
        candidate for candidate in safe_initials
        if not _swept_catch(round_data, {**candidate, "armed": True})[0]
    )
    return round_data, solution


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition, parameters = _controlled_parameters(task)
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    challenge_salt = MECHANIC_ID if condition is None else f"{MECHANIC_ID}|d{int(condition['difficulty'])}"
    challenge_id = hashlib.sha256(f"{seed}|{challenge_salt}".encode("utf-8")).hexdigest()[:12]
    historical_challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode("utf-8")).hexdigest()[:12]
    task_id = str(task.get("id") or "trajectory_catcher_seed_0001@0.1")
    families = [str(value) for value in parameters["family_pool"]]
    if not families or any(value not in FAMILIES for value in families):
        raise ValueError("trajectory catcher family pool is invalid")
    rng.shuffle(families)
    rounds: list[dict[str, Any]] = []
    solutions: list[dict[str, Any]] = []
    for index in range(_integer(parameters, "round_count")):
        family = families[index % len(families)]
        generated, solution = _round(rng, seed, index, family, parameters)
        rounds.append(generated)
        solutions.append({"round_id": generated["id"], **solution})
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "prompt": task.get("natural_language") or "Watch each flight. Place the full capture tunnel on its hidden continuation, match its direction, and arm before emergence.",
        "generator": {"name": "analytic_hidden_flight_catcher_v1", "variant_count": VARIANT_COUNT},
        "range_id": f"TR-{historical_challenge_id[:4].upper()}-{rng.randint(100, 999)}",
        "palette": rng.choice(PALETTES),
        "canvas": {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT},
        "rounds": rounds,
        "round_count": len(rounds),
        "submit_label": "FILE FLIGHT LOG",
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "canvas": public_state["canvas"],
        "rounds": rounds,
        "solutions": solutions,
        "round_count": len(rounds),
        "variant_count": VARIANT_COUNT,
    }
    for round_data, solution in zip(rounds, solutions):
        for sample in range(0, int(round_data["duration_ms"]) + 1, 25):
            x, y = _path(round_data, sample)
            assert 40 <= x <= CANVAS_WIDTH - 40 and 42 <= y <= CANVAS_HEIGHT - 42
        assert round_data["wall_exit_ms"] - round_data["wall_enter_ms"] >= int(round_data["minimum_observation_ms"])
        assert solution["catch_time_ms"] > round_data["wall_exit_ms"]
        assert _swept_catch(round_data, {**solution, "armed": True})[0]
        assert not _swept_catch(round_data, {**round_data["initial_catcher"], "armed": True})[0]
    if condition is not None:
        public_state["control_condition"] = condition
        ground_truth["control_condition"] = condition
    return public_state, ground_truth
