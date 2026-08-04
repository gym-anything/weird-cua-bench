from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "magnetic_stripe_purgatory"
STAGE_WIDTH = 1000
STAGE_HEIGHT = 430
VARIANT_COUNT = 18_662_400_000

PALETTES = (
    {"name": "municipal_aqua", "desk": "#c9c5b4", "ink": "#192f3b", "signal": "#46d5dd", "warning": "#e86650", "card": "#e7e0c8"},
    {"name": "night_shift_amber", "desk": "#b9ad97", "ink": "#302b29", "signal": "#f4c767", "warning": "#cc5348", "card": "#eee3ca"},
    {"name": "violet_terminal", "desk": "#c7bcc8", "ink": "#31283e", "signal": "#79d7c5", "warning": "#e65f78", "card": "#eee3df"},
    {"name": "olive_bureau", "desk": "#bfc2a8", "ink": "#29372f", "signal": "#a8dc69", "warning": "#d7614d", "card": "#e9e3c9"},
)

BADGES = (
    {"code": "TRI", "symbol": "▲", "color": "#e36b55"},
    {"code": "ORB", "symbol": "●", "color": "#48bcca"},
    {"code": "BAR", "symbol": "▰", "color": "#d1aa43"},
)
FOURTH_BADGE = {"code": "DIA", "symbol": "◆", "color": "#9c78d1"}

PROFILES = (
    {"token": "quartz", "minimum_ms": 440, "maximum_ms": 700, "solver_ms": 565, "straightness_px": 15},
    {"token": "pendulum", "minimum_ms": 700, "maximum_ms": 1050, "solver_ms": 865, "straightness_px": 17},
    {"token": "glacier", "minimum_ms": 1050, "maximum_ms": 1420, "solver_ms": 1220, "straightness_px": 19},
)

# ``legacy`` is deliberately the original tuple above.  L4 takes that path
# with the original random draws, so the historical task remains a fixed-seed
# reference condition rather than a rebuilt approximation.
PROFILE_SETS = {
    "single_forgiving": (
        {"token": "steady", "minimum_ms": 620, "maximum_ms": 1240, "solver_ms": 930, "straightness_px": 28},
    ),
    "paired_broad": (
        {"token": "swift", "minimum_ms": 440, "maximum_ms": 820, "solver_ms": 620, "straightness_px": 25},
        {"token": "patient", "minimum_ms": 820, "maximum_ms": 1280, "solver_ms": 1040, "straightness_px": 25},
    ),
    "triplet_tempered": (
        {"token": "cadence_a", "minimum_ms": 480, "maximum_ms": 800, "solver_ms": 640, "straightness_px": 22},
        {"token": "cadence_b", "minimum_ms": 680, "maximum_ms": 1060, "solver_ms": 860, "straightness_px": 21},
        {"token": "cadence_c", "minimum_ms": 920, "maximum_ms": 1340, "solver_ms": 1120, "straightness_px": 20},
    ),
    "legacy": PROFILES,
    "four_narrow": (
        {"token": "flicker", "minimum_ms": 400, "maximum_ms": 590, "solver_ms": 490, "straightness_px": 12},
        {"token": "quartz_narrow", "minimum_ms": 540, "maximum_ms": 730, "solver_ms": 630, "straightness_px": 12},
        {"token": "pendulum_narrow", "minimum_ms": 760, "maximum_ms": 960, "solver_ms": 860, "straightness_px": 12},
        {"token": "glacier_narrow", "minimum_ms": 1040, "maximum_ms": 1250, "solver_ms": 1140, "straightness_px": 12},
    ),
}


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _entity_id(seed: str, kind: str, index: int) -> str:
    token = hashlib.sha256(f"{seed}|{kind}|{index}".encode("utf-8")).hexdigest()[:8]
    return f"{kind}-{token}"


def _reader_geometry(
    index: int,
    direction: str,
    rng: random.Random,
    *,
    interference_zone_count: int = 2,
    compact_layout: bool = False,
    interference_layout: str = "legacy_off_lane",
    straightness_px: int = 18,
) -> dict[str, Any]:
    if compact_layout:
        top = 5 + index * 106
        height = 98
        slot_y, slot_height, center_y = top + 19, 58, top + 65
    else:
        # Keep this historical geometry arithmetic intact for the original
        # three-reader configuration.
        top = 8 + index * 138
        height = 128
        slot_y, slot_height, center_y = top + 25, 78, top + 72
    zones: list[dict[str, Any]] = []
    if interference_layout == "legacy_off_lane":
        # Historical L4 and the uncontrolled task use this exact random-draw
        # sequence and off-rail display geometry. Do not change it: it is part
        # of the preserved baseline world.
        zone_xs = rng.sample(range(510, 825, 35), interference_zone_count)
        for zone_index, x in enumerate(sorted(zone_xs)):
            above = (zone_index + index + rng.randrange(2)) % 2 == 0
            zones.append(
                {
                    "id": f"static-{index + 1}-{zone_index + 1}",
                    "x": x,
                    "y": center_y - 45 if above else center_y + 24,
                    "width": rng.randint(46, 66),
                    "height": rng.randint(15, 19),
                }
            )
    elif interference_layout == "blocking_lane":
        # These fields deliberately cover the rail centre and extend beyond
        # one side of the allowed straightness corridor. The visible remaining
        # lane therefore gives every field one feasible detour side. Positions
        # are separated so consecutive detours can be made without a jump.
        base_xs = (510, 655, 800)
        safe_offset = min(16, int(straightness_px) - 4)
        if safe_offset < 8:
            raise ValueError("blocking static fields need at least an eight-pixel clearance route")
        for zone_index, base_x in enumerate(base_xs[:interference_zone_count]):
            force_upper_route = (index + zone_index + rng.randrange(2)) % 2 == 0
            if force_upper_route:
                zone_y = center_y - 3
            else:
                zone_y = center_y - int(straightness_px) - 3
            zones.append(
                {
                    "id": f"static-{index + 1}-{zone_index + 1}",
                    "x": base_x + rng.randrange(-9, 10),
                    "y": zone_y,
                    "width": rng.randint(50, 60),
                    "height": int(straightness_px) + 6,
                }
            )
    elif interference_layout != "none":
        raise ValueError("magnetic stripe interference layout is invalid")
    return {
        "rect": {"x": 214, "y": top, "width": 770, "height": height},
        "slot": {"x": 232, "y": slot_y, "width": 150, "height": slot_height},
        "track": {
            "x_start": 430,
            "x_end": 942,
            "y": center_y,
            "lane_half_height": 20,
            "direction": direction,
        },
        "interference_zones": zones,
    }


def _public_reader(reader: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(reader[key])
        for key in ("id", "label", "serial", "badge", "rect", "slot", "track", "interference_zones", "profile_token")
    }


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    task_id = str(task.get("id") or "magnetic_stripe_purgatory_seed_0001@0.1")
    condition = task.get("_control_condition")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    reader_count = int(parameters.get("reader_count", 3))
    profile_set = str(parameters.get("profile_set", "legacy"))
    interference_zone_count = int(parameters.get("interference_zone_count", 2))
    interference_layout = str(parameters.get("interference_layout", "legacy_off_lane"))
    compact_layout = bool(parameters.get("compact_layout", False))
    minimum_insert_moves = int(parameters.get("minimum_insert_moves", 4))
    minimum_insert_ms = int(parameters.get("minimum_insert_ms", 90))
    minimum_swipe_samples = int(parameters.get("minimum_swipe_samples", 14))
    minimum_coverage_milli = int(parameters.get("minimum_coverage_milli", 920))
    maximum_sample_gap_px = int(parameters.get("maximum_sample_gap_px", 58))
    maximum_backtrack_px = int(parameters.get("maximum_backtrack_px", 18))
    straightness_override = parameters.get("straightness_px")
    if not 1 <= reader_count <= 4:
        raise ValueError("magnetic stripe reader_count must be between one and four")
    if profile_set not in PROFILE_SETS or len(PROFILE_SETS[profile_set]) != reader_count:
        raise ValueError("magnetic stripe profile_set must provide one profile per reader")
    if not 0 <= interference_zone_count <= 3:
        raise ValueError("magnetic stripe interference_zone_count must be between zero and three")
    if interference_layout not in {"none", "legacy_off_lane", "blocking_lane"}:
        raise ValueError("magnetic stripe interference layout is invalid")
    if interference_layout == "none" and interference_zone_count != 0:
        raise ValueError("magnetic stripe no-field layout cannot generate static fields")
    if interference_layout == "blocking_lane" and interference_zone_count == 0:
        raise ValueError("magnetic stripe blocking layout requires at least one static field")
    if compact_layout != (reader_count == 4):
        raise ValueError("magnetic stripe compact_layout is required exactly for four readers")
    if not 1 <= minimum_insert_moves <= 12 or not 40 <= minimum_insert_ms <= 400:
        raise ValueError("magnetic stripe insertion controls are outside the supported range")
    if not 6 <= minimum_swipe_samples <= 24 or not 840 <= minimum_coverage_milli <= 970:
        raise ValueError("magnetic stripe swipe density or coverage is outside the supported range")
    if not 32 <= maximum_sample_gap_px <= 100 or not 6 <= maximum_backtrack_px <= 40:
        raise ValueError("magnetic stripe swipe path tolerances are outside the supported range")
    if straightness_override is not None and not 8 <= int(straightness_override) <= 32:
        raise ValueError("magnetic stripe straightness tolerance is outside the supported range")
    condition_token = ""
    if condition and int(condition.get("difficulty") or 0) != 4:
        condition_token = f"|d{int(condition['difficulty'])}"
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|calibration-v1{condition_token}".encode("utf-8")).hexdigest()[:14]
    palette = copy.deepcopy(rng.choice(PALETTES))

    directions = [rng.choice(("ltr", "rtl")) for _ in range(reader_count)]
    if reader_count > 1 and len(set(directions)) == 1:
        directions[rng.randrange(reader_count)] = "rtl" if directions[0] == "ltr" else "ltr"
    profiles = [copy.deepcopy(item) for item in PROFILE_SETS[profile_set]]
    rng.shuffle(profiles)
    badges = [copy.deepcopy(item) for item in BADGES]
    if reader_count == 4:
        badges.append(copy.deepcopy(FOURTH_BADGE))
    rng.shuffle(badges)

    readers: list[dict[str, Any]] = []
    for index in range(reader_count):
        profile = profiles[index]
        reader_straightness = int(straightness_override) if straightness_override is not None else int(profile["straightness_px"])
        geometry = _reader_geometry(
            index,
            directions[index],
            rng,
            interference_zone_count=interference_zone_count,
            compact_layout=compact_layout,
            interference_layout=interference_layout,
            straightness_px=reader_straightness,
        )
        reader = {
            "id": _entity_id(seed, "reader", index),
            "label": f"READER {index + 1}",
            "serial": f"R-{rng.randint(100, 999)}-{chr(65 + index)}",
            "badge": badges[index],
            **geometry,
            "profile_token": profile["token"],
            "calibration": {
                "minimum_ms": profile["minimum_ms"],
                "maximum_ms": profile["maximum_ms"],
                "solver_ms": profile["solver_ms"],
                "straightness_px": reader_straightness,
                "maximum_backtrack_px": maximum_backtrack_px,
                "minimum_samples": minimum_swipe_samples,
                "minimum_coverage_milli": minimum_coverage_milli,
                "maximum_sample_gap_px": maximum_sample_gap_px,
            },
        }
        readers.append(reader)

    # Card rack order is independent from reader order. Matching badge and
    # colour are the visible assignment; the direct reader id remains hidden.
    assignments = list(range(reader_count))
    rng.shuffle(assignments)
    cards: list[dict[str, Any]] = []
    for rack_index, reader_index in enumerate(assignments):
        reader = readers[reader_index]
        compact_card = compact_layout
        cards.append(
            {
                "id": _entity_id(seed, "card", rack_index),
                "label": f"CARD {chr(65 + rack_index)}",
                "account": f"{rng.randint(1000, 9999)} {rng.randint(1000, 9999)}",
                "holder": rng.choice(("M. STATIC", "A. RETRY", "J. CALIBRATE", "T. STRIPE")),
                "badge": copy.deepcopy(reader["badge"]),
                "initial_rect": {
                    "x": 24,
                    "y": (16 + rack_index * 100) if compact_card else (28 + rack_index * 132),
                    "width": 158,
                    "height": 70 if compact_card else 82,
                },
                "assigned_reader": str(reader["id"]),
            }
        )

    public_cards = [{key: copy.deepcopy(card[key]) for key in ("id", "label", "account", "holder", "badge", "initial_rect")} for card in cards]
    requirements = {
        "card_count": reader_count,
        "minimum_insert_moves": minimum_insert_moves,
        "minimum_insert_ms": minimum_insert_ms,
        "minimum_swipe_samples": minimum_swipe_samples,
        "attempt_limit": 0,
    }
    legacy_prompt = "Match each card to its badge reader. Learn each reader's temperament by swiping until all three lock."
    legacy_rules = [
        "Match each card badge to the reader carrying the same badge, then physically drag the card into its insertion slot.",
        "Swipe from the illuminated arrow end to the opposite end with a dense, straight, monotonic pointer path.",
        "Every reader has a different hidden timing temperament. Use TOO FAST, TOO SLOW, and BAD READ feedback; retries are unlimited.",
        "Accepted readers lock. Audit only after all three indicator lamps are accepted.",
    ]
    if condition and int(condition.get("difficulty") or 0) != 4:
        prompt = str(task.get("natural_language") or legacy_prompt)
        rules = [
            f"Match all {reader_count} card badges to their readers.",
            "Begin every swipe at its illuminated arrow, keep it straight and monotonic, and avoid visible static fields.",
            "Use TOO FAST, TOO SLOW, and BAD READ feedback to calibrate each hidden reader timing window.",
            f"Audit after all {reader_count} reader lamps are accepted.",
        ]
    else:
        prompt = legacy_prompt
        rules = legacy_rules
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": prompt,
        "submit_label": "RUN CALIBRATION AUDIT",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "generator": {
            "name": "multi_reader_card_calibration_desk_v1",
            "variant_count": VARIANT_COUNT,
            "variant_count_kind": "palette/card-order/assignment/direction/window/interference construction space",
        },
        "palette": palette,
        "stage": {"width": STAGE_WIDTH, "height": STAGE_HEIGHT},
        "cards": public_cards,
        "readers": [_public_reader(reader) for reader in readers],
        "requirements": requirements,
        "rules": rules,
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "palette": palette,
        "stage": public_state["stage"],
        "cards": copy.deepcopy(cards),
        "readers": copy.deepcopy(readers),
        "requirements": requirements,
        "variant_count": VARIANT_COUNT,
        "variant_count_kind": public_state["generator"]["variant_count_kind"],
    }
    if condition:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    assert len({reader["calibration"]["solver_ms"] for reader in readers}) == reader_count
    assert len({card["assigned_reader"] for card in cards}) == reader_count
    assert all(reader["calibration"]["minimum_ms"] < reader["calibration"]["solver_ms"] < reader["calibration"]["maximum_ms"] for reader in readers)
    return public_state, ground_truth
