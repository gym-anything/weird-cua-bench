from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "clockwork_doppelganger_customs"
PALETTES = ("timecard-amber", "customs-blue", "oxide-green", "carbon-red")
VARIANT_COUNT = 3 * 3 * 4 * 10_000_000_000

DEFAULT_LOOP_VALUES = (5900, 6100, 6300)
DEFAULT_TRACK_Y_VALUES = (250, 270, 290)
DEFAULT_CATCH_TIME_VALUES = (750, 800, 850)
DEFAULT_SPEED_VALUES = (0.205, 0.215, 0.225)


def _seed_int(seed: str, salt: str) -> int:
    return int(hashlib.sha256(f"{seed}|{salt}".encode()).hexdigest()[:16], 16)


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    condition = task.get("_control_condition")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    role_count = int(parameters.get("role_count", 3))
    record_ms = int(parameters.get("record_duration_ms", 2300))
    phase_step_ms = int(parameters.get("phase_step_ms", 50))
    sample_interval_ms = int(parameters.get("sample_interval_ms", 80))
    cycle_sample_interval_ms = int(parameters.get("cycle_sample_interval_ms", 100))
    loop_values = tuple(int(value) for value in parameters.get("loop_duration_ms_values", DEFAULT_LOOP_VALUES))
    track_y_values = tuple(int(value) for value in parameters.get("track_y_values", DEFAULT_TRACK_Y_VALUES))
    catch_time_values = tuple(int(value) for value in parameters.get("catch_time_ms_values", DEFAULT_CATCH_TIME_VALUES))
    speed_values = tuple(float(value) for value in parameters.get("speed_px_per_ms_values", DEFAULT_SPEED_VALUES))
    if not 1 <= role_count <= 3:
        raise ValueError("clockwork role_count must be between one and three")
    if not loop_values or any(value < 3000 or value > 9000 for value in loop_values):
        raise ValueError("clockwork loop durations are outside supported limits")
    if not track_y_values or any(value < 180 or value > 330 for value in track_y_values):
        raise ValueError("clockwork track positions are outside supported limits")
    if not catch_time_values or any(value < 500 or value > 1100 for value in catch_time_values):
        raise ValueError("clockwork catch times are outside supported limits")
    if not speed_values or any(value < 0.15 or value > 0.30 for value in speed_values):
        raise ValueError("clockwork conveyor speeds are outside supported limits")
    if not 1500 <= record_ms <= 3000 or phase_step_ms not in {25, 50, 75, 100}:
        raise ValueError("clockwork recording settings are outside supported limits")
    if not 45 <= sample_interval_ms <= 120 or not 60 <= cycle_sample_interval_ms <= 140:
        raise ValueError("clockwork sampling settings are outside supported limits")
    # Control profiles get distinct challenge identities without changing the
    # uncontrolled RNG stream or the visible world chosen from it.  Interaction
    # is deliberately absent: the full and simplified surfaces share one world.
    condition_token = f"|d{int(condition['difficulty'])}" if condition else ""
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}{condition_token}".encode()).hexdigest()[:12]
    world_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode()).hexdigest()[:12]
    task_id = str(task.get("id") or "clockwork_doppelganger_customs_seed_0001@0.1")
    loop_ms = rng.choice(loop_values)
    track_y = rng.choice(track_y_values)
    catch_time = rng.choice(catch_time_values)
    speed = rng.choice(speed_values)
    start_x = 72
    pickup = {"x": round(start_x + speed * catch_time, 2), "y": track_y}
    vertical = rng.choice((-1, 1))
    handoff_a = {"x": 348 + rng.randint(-12, 12), "y": track_y + vertical * 82}
    stamp = {"x": 505 + rng.randint(-10, 10), "y": track_y - vertical * 58}
    handoff_b = {"x": 642 + rng.randint(-12, 12), "y": track_y + vertical * 72}
    exit_point = {"x": 790, "y": track_y}
    stations = {"pickup": pickup, "handoff_a": handoff_a, "stamp": stamp, "handoff_b": handoff_b, "exit": exit_point}
    conveyor = {"start_x": start_x, "track_y": track_y, "speed_px_per_ms": speed, "catch_time_ms": catch_time}
    controls = {"record_duration_ms": record_ms, "loop_duration_ms": loop_ms, "phase_step_ms": phase_step_ms, "sample_interval_ms": sample_interval_ms, "cycle_sample_interval_ms": cycle_sample_interval_ms}
    qualification = {
        "minimum_record_samples": int(parameters.get("minimum_record_samples", 24)),
        "maximum_record_sample_gap_ms": int(parameters.get("maximum_record_sample_gap_ms", 240)),
        "maximum_pointer_step_px": int(parameters.get("maximum_pointer_step_px", 98)),
        "minimum_path_travel_px": int(parameters.get("minimum_path_travel_px", 90)),
        "action_path_tolerance_px": int(parameters.get("action_path_tolerance_px", 48)),
        "grab_radius_px": int(parameters.get("grab_radius_px", 38)),
        "station_radius_px": int(parameters.get("station_radius_px", 42)),
        "handoff_window_ms": int(parameters.get("handoff_window_ms", 230)),
        "minimum_cycle_samples": int(parameters.get("minimum_cycle_samples", 45)),
        "maximum_cycle_sample_gap_ms": int(parameters.get("maximum_cycle_sample_gap_ms", 260)),
    }
    if (
        qualification["minimum_record_samples"] < 12
        or qualification["maximum_record_sample_gap_ms"] < sample_interval_ms
        or qualification["maximum_pointer_step_px"] < 35
        or qualification["minimum_path_travel_px"] < 50
        or qualification["action_path_tolerance_px"] < 20
        or qualification["grab_radius_px"] < 24
        or qualification["station_radius_px"] < 24
        or qualification["handoff_window_ms"] < 100
        or qualification["minimum_cycle_samples"] < 20
        or qualification["maximum_cycle_sample_gap_ms"] < cycle_sample_interval_ms
    ):
        raise ValueError("clockwork qualification settings are outside supported limits")
    roles = [
        {"slot": 0, "title": "CATCH / PASS A", "required_actions": ["grab", "release"], "guide": [pickup, handoff_a]},
        {"slot": 1, "title": "STAMP / PASS B", "required_actions": ["grab", "stamp", "release"], "guide": [handoff_a, stamp, handoff_b]},
        {"slot": 2, "title": "DELIVER / RELEASE", "required_actions": ["grab", "release"], "guide": [handoff_b, exit_point]},
    ]
    nominal = [
        {"grab": 350, "release": 1750},
        {"grab": 350, "stamp": 1050, "release": 1850},
        {"grab": 350, "release": 1650},
    ]
    if role_count == 1:
        roles = [{"slot": 0, "title": "CATCH / STAMP / RELEASE", "required_actions": ["grab", "stamp", "release"], "guide": [pickup, stamp, exit_point]}]
        nominal = [{"grab": 300, "stamp": 900, "release": 1450}]
    elif role_count == 2:
        roles = [
            {"slot": 0, "title": "CATCH / PASS", "required_actions": ["grab", "release"], "guide": [pickup, handoff_a]},
            {"slot": 1, "title": "STAMP / RELEASE", "required_actions": ["grab", "stamp", "release"], "guide": [handoff_a, stamp, exit_point]},
        ]
        nominal = [{"grab": 300, "release": 1250}, {"grab": 300, "stamp": 900, "release": 1700}]
    handoff_gap_ms = int(parameters.get("handoff_gap_ms", 100))
    if not 60 <= handoff_gap_ms <= qualification["handoff_window_ms"]:
        raise ValueError("clockwork handoff gap is outside its visible transfer window")
    phases = [int(round((catch_time - nominal[0]["grab"]) / phase_step_ms) * phase_step_ms)]
    for slot in range(1, len(roles)):
        release_before = phases[slot - 1] + nominal[slot - 1]["release"]
        phases.append(int(round((release_before + handoff_gap_ms - nominal[slot]["grab"]) / phase_step_ms) * phase_step_ms))
    if phases[0] < 0 or any(phase < 0 for phase in phases) or phases[-1] + nominal[-1]["release"] >= loop_ms - 150:
        raise ValueError("clockwork phase profile does not fit within the master loop")
    for role in roles:
        guide_length = sum(math.hypot(float(after["x"]) - float(before["x"]), float(after["y"]) - float(before["y"])) for before, after in zip(role["guide"], role["guide"][1:]))
        assert guide_length >= qualification["minimum_path_travel_px"]
    public_state = {
        "benchmark": "weird_captcha_gym", "mechanic_id": MECHANIC_ID, "task_id": task_id,
        "challenge_id": challenge_id, "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "prompt": task.get("natural_language") or "Record three short operator loops, phase them together, and pass one passport through catch, stamp, and delivery.",
        "generator": {"name": "concurrent_recorded_ghost_customs_v1", "variant_count": VARIANT_COUNT},
        "desk_id": f"CLK-{world_id[:4].upper()}-{rng.randint(100,999)}", "palette": rng.choice(PALETTES),
        "canvas": {"width": 860, "height": 420}, "stations": stations, "conveyor": conveyor,
        "roles": roles, "controls": controls, "qualification": qualification, "submit_label": "FILE CUSTOMS LOG",
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID, "task_id": task_id, "seed": seed, "challenge_id": challenge_id,
        "canvas": public_state["canvas"], "stations": stations, "conveyor": conveyor, "roles": roles,
        "controls": controls, "qualification": qualification,
        "solution": {"nominal_action_times": nominal, "phases_ms": phases, "handoff_gap_ms": handoff_gap_ms},
        "variant_count": VARIANT_COUNT,
    }
    if condition:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
