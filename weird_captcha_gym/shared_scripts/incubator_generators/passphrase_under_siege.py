from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "passphrase_under_siege"
ASSET_MANIFEST = "shared_runtime/assets/provenance/passphrase_under_siege_v0.json"
STAMP_CONSONANTS = "BRKLMNPRSTV"
STAMP_VOWELS = "AEIOU"
COLOR_POOL = (
    "#A2C4E6",
    "#B1D3F5",
    "#C2A4D1",
    "#E1B4C2",
    "#A3D2F1",
    "#F2C1A4",
    "#D4A1B2",
    "#B2E1C3",
)
THEMES = (
    {"ink": "#2a2118", "paper": "#ead9b7", "seal": "#a9362b", "night": "#181a20"},
    {"ink": "#18252b", "paper": "#d8dfd4", "seal": "#8d2f4c", "night": "#10191d"},
    {"ink": "#29221f", "paper": "#decba8", "seal": "#315f68", "night": "#181514"},
)

DEFAULT_PARAMETERS: dict[str, Any] = {
    "minimum_length": 18,
    "exact_length": 34,
    "stamp_length": 4,
    "include_color": True,
    "include_gauge": True,
    "digit_sum_target": 42,
    "bold_vowels": True,
    "stamp_bold": False,
    "stamp_italic": True,
    "stamp_font": True,
    "gauge_size_px": 28,
    "color_font": False,
    "ember_count": 2,
    "ember_ttl_ms": 4600,
    "ember_interval_ms": 2300,
    "feed_required": 1,
    "feed_interval_ms": 0,
    "hunger_ms": 22000,
}


def _seed(seed: str) -> int:
    digest = hashlib.sha256(f"{seed}|{MECHANIC_ID}|v1".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _stamp(rng: random.Random, length: int) -> str:
    chars: list[str] = []
    for index in range(length):
        alphabet = STAMP_CONSONANTS if index % 2 == 0 else STAMP_VOWELS
        available = [char for char in alphabet if char not in chars]
        chars.append(rng.choice(available or list(alphabet)))
    return "".join(chars)


def _digit_sum(value: str) -> int:
    return sum(int(char) for char in value if char.isdigit())


def _validate(parameters: dict[str, Any]) -> None:
    integer_ranges = {
        "minimum_length": (5, 80),
        "exact_length": (0, 80),
        "stamp_length": (2, 8),
        "digit_sum_target": (9, 90),
        "gauge_size_px": (0, 40),
        "ember_count": (0, 5),
        "ember_ttl_ms": (2500, 9000),
        "ember_interval_ms": (800, 6000),
        "feed_required": (0, 4),
        "feed_interval_ms": (0, 15000),
        "hunger_ms": (0, 60000),
    }
    for name, (minimum, maximum) in integer_ranges.items():
        value = parameters.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"{name} is outside the supported range")
    for name in (
        "include_color",
        "include_gauge",
        "bold_vowels",
        "stamp_bold",
        "stamp_italic",
        "stamp_font",
        "color_font",
    ):
        if not isinstance(parameters.get(name), bool):
            raise ValueError(f"{name} must be boolean")
    exact_length = int(parameters["exact_length"])
    if exact_length and exact_length < int(parameters["minimum_length"]):
        raise ValueError("exact length cannot be below minimum length")
    if int(parameters["feed_required"]) and int(parameters["hunger_ms"]) < 10000:
        raise ValueError("hatchling hunger window is not human-manageable")
    if not int(parameters["feed_required"]) and int(parameters["hunger_ms"]):
        raise ValueError("hunger window requires a feeding action")
    if int(parameters["feed_required"]) <= 1 and int(parameters["feed_interval_ms"]):
        raise ValueError("a feed interval requires at least two feeding actions")
    if int(parameters["gauge_size_px"]) and not parameters["include_gauge"]:
        raise ValueError("gauge formatting requires a gauge clue")
    if parameters["color_font"] and not parameters["include_color"]:
        raise ValueError("colour formatting requires a colour clue")


def _rules(parameters: dict[str, Any]) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = [
        {
            "id": "minimum_length",
            "title": "OPEN A FILE",
            "text": f"Use at least {parameters['minimum_length']} characters.",
        },
        {"id": "uppercase", "title": "CAPITAL AUTHORITY", "text": "Include an uppercase letter."},
        {"id": "special_mark", "title": "CLERK'S MARK", "text": "Include the seal mark !"},
        {
            "id": "digit_sum",
            "title": "LEDGER SUM",
            "text": f"All digits in the passphrase must add to {parameters['digit_sum_target']}.",
        },
        {
            "id": "stamp",
            "title": "SMUDGED STAMP",
            "text": "Transcribe the ink impression exactly.",
            "widget": "stamp",
        },
    ]
    if parameters["include_color"]:
        rules.append(
            {
                "id": "color",
                "title": "CHIP REGISTER",
                "text": "Include the register code printed on this colour chip, including #.",
                "widget": "color",
            }
        )
    if parameters["include_gauge"]:
        rules.append(
            {
                "id": "gauge",
                "title": "PRESSURE COPY",
                "text": "Read the dial's integer pressure and include it with a G prefix (for example G7).",
                "widget": "gauge",
            }
        )
    if parameters["include_color"] or parameters["include_gauge"]:
        order = "stamp, colour chip" + (", then gauge" if parameters["include_gauge"] else "")
        rules.append(
            {
                "id": "clue_order",
                "title": "DESK ORDER",
                "text": f"File the clues in this order: {order}.",
            }
        )
    if int(parameters["exact_length"]):
        rules.append(
            {
                "id": "exact_length",
                "title": "MARGIN LIMIT",
                "text": f"The finished text must contain exactly {parameters['exact_length']} characters.",
            }
        )
    if parameters["bold_vowels"]:
        rules.append(
            {
                "id": "bold_vowels",
                "title": "VOWEL WEIGHT",
                "text": "Bold every vowel and no other character.",
            }
        )
    if parameters["stamp_bold"]:
        rules.append(
            {
                "id": "stamp_bold",
                "title": "STAMP WEIGHT",
                "text": "Bold the stamp code and no other character.",
            }
        )
    if parameters["stamp_italic"]:
        rules.append(
            {
                "id": "stamp_italic",
                "title": "STAMP SLANT",
                "text": "Italicise the stamp code and no other character.",
            }
        )
    if parameters["stamp_font"]:
        rules.append(
            {
                "id": "stamp_font",
                "title": "STAMP FACE",
                "text": "Set the stamp code in Ledger Serif; leave unlisted ranges in Clerk Mono.",
            }
        )
    if int(parameters["gauge_size_px"]):
        rules.append(
            {
                "id": "gauge_size",
                "title": "GAUGE MAGNITUDE",
                "text": f"Set only the gauge digits to {parameters['gauge_size_px']} px.",
            }
        )
    if parameters["color_font"]:
        rules.append(
            {
                "id": "color_font",
                "title": "CHIP FACE",
                "text": "Set the complete colour code in Ledger Serif without changing other characters.",
            }
        )
    if int(parameters["feed_required"]):
        interval_ms = int(parameters["feed_interval_ms"])
        cadence = (
            f" The next grain ripens {interval_ms / 1000:g} seconds after each delivery."
            if interval_ms
            else ""
        )
        rules.append(
            {
                "id": "hatchling",
                "title": "HATCHLING CLAUSE",
                "text": (
                    f"Keep the hatchling alive and feed it {parameters['feed_required']} grain token(s)."
                    f"{cadence}"
                ),
                "widget": "hatchling",
            }
        )
    if int(parameters["ember_count"]):
        rules.append(
            {
                "id": "embers",
                "title": "EMBER CLAUSE",
                "text": f"Quench all {parameters['ember_count']} moving ember(s) before any reaches the text.",
                "widget": "ember",
            }
        )
    return rules


def _embers(rng: random.Random, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    paths: list[dict[str, Any]] = []
    count = int(parameters["ember_count"])
    ttl_ms = int(parameters["ember_ttl_ms"])
    interval_ms = int(parameters["ember_interval_ms"])
    for index in range(count):
        from_left = (index + rng.randrange(2)) % 2 == 0
        start_x = rng.uniform(0.08, 0.22) if from_left else rng.uniform(0.78, 0.92)
        end_x = rng.uniform(0.78, 0.92) if from_left else rng.uniform(0.08, 0.22)
        start_y = rng.uniform(0.18, 0.70)
        end_y = min(0.82, max(0.14, start_y + rng.uniform(-0.28, 0.28)))
        paths.append(
            {
                "id": f"ember-{index + 1}-{rng.randrange(1000, 9999)}",
                "spawn_offset_ms": 700 + index * interval_ms,
                "ttl_ms": ttl_ms,
                "start": [round(start_x, 5), round(start_y, 5)],
                "end": [round(end_x, 5), round(end_y, 5)],
                "damage_slot": rng.randrange(7, 29),
            }
        )
    return paths


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed(seed))
    condition = task.get("_control_condition")
    parameters = copy.deepcopy(DEFAULT_PARAMETERS)
    parameters.update(dict((condition or {}).get("difficulty_parameters") or {}))
    _validate(parameters)
    difficulty = int((condition or {}).get("difficulty") or 4)

    stamp = _stamp(rng, int(parameters["stamp_length"]))
    color = rng.choice(COLOR_POOL) if parameters["include_color"] else ""
    gauge_value = rng.randint(10, 12) if difficulty == 5 else rng.randint(2, 9)
    gauge = f"G{gauge_value}" if parameters["include_gauge"] else ""
    required_digit_sum = _digit_sum(color) + _digit_sum(gauge)
    if required_digit_sum > int(parameters["digit_sum_target"]):
        raise ValueError("generated visible clues exceed the digit-sum target")

    embers = _embers(rng, parameters)
    rules = _rules(parameters)
    theme = copy.deepcopy(rng.choice(THEMES))
    challenge_id = hashlib.sha256(
        f"{seed}|{MECHANIC_ID}|challenge|d{difficulty}".encode()
    ).hexdigest()[:12]
    prompt = task.get("natural_language") or (
        "Satisfy every live card in one passphrase, defend the text, seal it, and retype it exactly."
    )
    clues = {
        "stamp": stamp,
        "color": color,
        "gauge_value": gauge_value if parameters["include_gauge"] else None,
        "gauge_token": gauge,
    }
    hatchling = {
        "x_norm": 0.835,
        "y_norm": 0.34,
        "radius_x_norm": 0.0375,
        "radius_y_norm": 0.065,
        "grain_tokens": [f"grain-{index + 1}" for index in range(max(3, int(parameters["feed_required"])))],
    }
    public: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "challenge_id": challenge_id,
        "prompt": prompt,
        "asset_manifest": ASSET_MANIFEST,
        "generator": {
            "name": "seeded_siege_ledger_v1",
            "variant_count": 3 * len(COLOR_POOL) * 11**int(parameters["stamp_length"]) * 9,
        },
        "difficulty": difficulty,
        "contract": parameters,
        "rules": rules,
        "clues": clues,
        "embers": embers,
        "hatchling": hatchling,
        "theme": theme,
    }
    truth: dict[str, Any] = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "seed": seed,
        "challenge_id": challenge_id,
        "difficulty": difficulty,
        "contract": copy.deepcopy(parameters),
        "rule_ids": [rule["id"] for rule in rules],
        "clues": copy.deepcopy(clues),
        "embers": copy.deepcopy(embers),
        "hatchling": copy.deepcopy(hatchling),
    }
    if condition:
        public["control_condition"] = copy.deepcopy(condition)
        truth["control_condition"] = copy.deepcopy(condition)
    return public, truth
