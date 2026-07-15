from __future__ import annotations

import hashlib
import random
from typing import Any


MECHANIC_ID = "microgame_gauntlet"
ROUND_TYPES = ("pressure", "chord", "dial", "intercept", "route")
CHORDS = (("A", "L"), ("D", "K"), ("F", "J"), ("Q", "P"), ("S", "K"))
PULSE_POSITIONS = ((14, 25), (34, 18), (59, 22), (83, 30), (20, 70), (45, 79), (70, 72), (88, 62))
ROUTE_TEMPLATES = (
    ((8, 75), (19, 55), (29, 29), (42, 48), (53, 73), (64, 42), (73, 18), (84, 39), (92, 16)),
    ((8, 22), (18, 46), (29, 73), (40, 52), (51, 25), (62, 48), (72, 76), (83, 55), (93, 79)),
    ((8, 52), (18, 23), (30, 42), (41, 74), (52, 49), (63, 20), (74, 43), (84, 74), (93, 48)),
)


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    order = list(ROUND_TYPES)
    rng.shuffle(order)
    pulse_positions = list(PULSE_POSITIONS)
    rng.shuffle(pulse_positions)
    pulse_count = rng.choice((7, 8))
    pulse_ids = [f"P{index + 1}-{rng.randint(20, 98)}" for index in range(pulse_count)]
    chord_sequence = rng.sample(CHORDS, 3)
    dial_start = rng.randrange(0, 360, 30)
    dial_target = (dial_start + rng.choice((120, 150, 180, 210, 240))) % 360
    route_template = rng.choice(ROUTE_TEMPLATES)
    route_points = [
        {"x": max(7, min(93, x + rng.randint(-2, 2))), "y": max(12, min(82, y + rng.randint(-2, 2))), "index": index}
        for index, (x, y) in enumerate(route_template)
    ]
    rounds: list[dict[str, Any]] = []
    for sequence, round_type in enumerate(order):
        base: dict[str, Any] = {
            "id": f"R{sequence + 1}-{hashlib.sha256(f'{seed}|{round_type}'.encode()).hexdigest()[:5]}",
            "type": round_type,
            "sequence": sequence,
            "energy_cost": 8,
        }
        if round_type == "pressure":
            base.update({
                "title": "PRESSURE / PULSE BANK",
                "instruction": "Hold SPACE continuously. While held, click the lit pulse sockets in order; release only after the bank is dark.",
                "pulses": [
                    {"id": pulse_ids[index], "x": pulse_positions[index][0], "y": pulse_positions[index][1], "order": index}
                    for index in range(pulse_count)
                ],
            })
        elif round_type == "chord":
            base.update({
                "title": "THREE-STAGE MAGNETIC CHORD",
                "instruction": "Charge and release all three two-key chords in the displayed order. An early release discharges the bank.",
                "chords": [list(chord) for chord in chord_sequence],
                "required_ticks": 4,
                "tick_ms": 145,
            })
        elif round_type == "dial":
            base.update({
                "title": "INERTIAL BRAKE DIAL",
                "instruction": "Drag around the flywheel to spin it. Release, let it coast, then brake inside the striped target sector.",
                "start_angle": dial_start,
                "target_angle": dial_target,
                "target_tolerance": 13,
                "friction": 0.945,
                "tick_ms": 95,
            })
        elif round_type == "intercept":
            packets = [
                {
                    "id": f"PK-{index + 1}",
                    "speed": round(rng.uniform(4.4 + index * .45, 6.0 + index * .55), 2),
                    "gate_center": rng.randint(30, 70),
                    "gate_half_width": rng.choice((5, 6)),
                }
                for index in range(3)
            ]
            base.update({
                "title": "TRIPLE MOVING-PACKET INTERCEPT",
                "instruction": "Arm once, then catch three packets. The capture gate and packet speed change after every hit.",
                "packets": packets,
                "tick_ms": 105,
            })
        else:
            base.update({
                "title": "BALANCE-ROUTE COURIER",
                "instruction": "Drag the reactor capsule through every numbered hoop without leaving the visible route corridor.",
                "points": route_points,
                "checkpoint_radius": 6,
                "corridor_radius": 8,
            })
        rounds.append(base)

    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode("utf-8")).hexdigest()[:12]
    task_id = str(task.get("id") or "")
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Complete all five reactor trials without exhausting stability.",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "generator": {"name": "mixed_input_verification_reactor_v2", "variant_count": 19_000_000_000},
        "reactor_id": f"VR-{challenge_id.upper()}",
        "rounds": rounds,
        "starting_energy": 100,
        "fault_penalty": 12,
        "reset_penalty": 4,
        "submit_label": "CERTIFY REACTOR",
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "rounds": rounds,
        "round_order": [round_data["id"] for round_data in rounds],
        "starting_energy": 100,
        "fault_penalty": 12,
        "reset_penalty": 4,
        "variant_count": 8_000_000_000,
    }
    assert {round_data["type"] for round_data in rounds} == set(ROUND_TYPES)
    assert len({round_data["id"] for round_data in rounds}) == 5
    return public_state, ground_truth
