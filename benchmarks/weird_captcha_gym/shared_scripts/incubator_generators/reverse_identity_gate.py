from __future__ import annotations

import hashlib
import random
from typing import Any


MECHANIC_ID = "reverse_identity_gate"
STATIONS = (
    {"id": 0, "glyph": "◢", "name": "PORT ARM", "color": "#ff684d"},
    {"id": 1, "glyph": "◇", "name": "OPTIC HEAD", "color": "#65ddc4"},
    {"id": 2, "glyph": "⌁", "name": "DRIVE CORE", "color": "#f6c453"},
    {"id": 3, "glyph": "◩", "name": "STARBOARD ARM", "color": "#78a8ff"},
)
PALETTES = ("carbon", "bone", "oxide", "midnight")
VARIANT_COUNT = 24 * 18 * 4**8 * 360**8


def _angular_error(first: int, second: int) -> int:
    return abs((first - second + 180) % 360 - 180)


def _receiver_angle(rng: random.Random, pulse: int) -> int:
    for _ in range(100):
        candidate = rng.randrange(0, 360, 5)
        if _angular_error(candidate, pulse) >= 90:
            return candidate
    raise ValueError("could not generate a separated receiver phase")


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    digest = hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    task_id = str(task.get("id") or "reverse_identity_gate_seed_0001@0.1")
    challenge_id = hashlib.sha256(f"{seed}|distributed-robot-handshake-v2".encode("utf-8")).hexdigest()[:12]

    first = list(range(4))
    second = list(range(4))
    rng.shuffle(first)
    for _ in range(50):
        rng.shuffle(second)
        if second[0] != first[-1]:
            break
    sequence = first + second
    stages = []
    for index, station in enumerate(sequence):
        pulse_start = rng.randrange(0, 360)
        speed = rng.choice((-3, -2, 2, 3))
        stages.append({
            "index": index,
            "station": station,
            "pulse_start_deg": pulse_start,
            "pulse_speed_deg_per_tick": speed,
            "receiver_initial_deg": _receiver_angle(rng, pulse_start),
            "load": rng.randrange(2, 10),
        })

    physics = {
        "tick_ms": 50,
        "receiver_control_deg_per_tick": 5,
        "capture_tolerance_deg": 13,
        "hold_ticks": 16,
        "charge_decay_per_tick": 2,
        "maximum_ticks_per_stage": 900,
    }
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Prove you are a robot.",
        "submit_label": "VERIFY IDENTITY",
        "asset_manifest": "shared_runtime/assets/provenance/revived_pilots_v2.json",
        "generator": {
            "name": "distributed_four_tab_robot_handshake_v2",
            "variant_count": VARIANT_COUNT,
            "variant_count_kind": "station-order/load/phase/direction space",
        },
        "stations": list(STATIONS),
        "stages": stages,
        "physics": physics,
        "palette": rng.choice(PALETTES),
        "rules": {
            "deployment": "Each limb is an explicit same-origin browser tab created from the loaded challenge.",
            "relay": "Drive the receiver with A/D and hold the mouse contact while the moving phases overlap.",
            "recovery": "Broken phase contact visibly drains charge but does not silently fail the challenge.",
        },
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "stations": list(STATIONS),
        "stages": stages,
        "physics": physics,
        "palette": public_state["palette"],
        "variant_count": VARIANT_COUNT,
        "variant_count_kind": public_state["generator"]["variant_count_kind"],
    }
    return public_state, ground_truth
