from __future__ import annotations

import copy
import hashlib
import itertools
import math
import random
from typing import Any


MECHANIC_ID = "two_lamp_dyeworks"
WAVELENGTHS_NM = (420, 455, 490, 525, 560, 595, 630, 665, 700)
BASE_REFLECTANCE = (0.88, 0.90, 0.92, 0.94, 0.95, 0.95, 0.94, 0.92, 0.90)
ABSORPTION_STRENGTH = 0.18
CIE_1931 = {
    "x": (0.134, 0.336, 0.095, 0.004, 0.594, 1.056, 0.642, 0.165, 0.011),
    "y": (0.004, 0.038, 0.208, 0.793, 0.995, 0.631, 0.265, 0.061, 0.004),
    "z": (0.646, 1.772, 1.287, 0.272, 0.004, 0.001, 0.000, 0.000, 0.000),
}
ILLUMINANTS = {
    "daylight": (0.76, 0.90, 1.04, 1.08, 1.05, 1.00, 0.94, 0.89, 0.84),
    "sodium": (0.05, 0.07, 0.11, 0.25, 0.92, 1.40, 0.78, 0.18, 0.05),
}
LAMP_CASTS = {
    "daylight": (1.00, 1.00, 0.98),
    "sodium": (1.05, 0.78, 0.42),
}
PIGMENTS = {
    "woad": {
        "name": "WOAD BLUE",
        "short": "W",
        "bottle": "#285b72",
        "absorption": (0.08, 0.05, 0.04, 0.12, 0.28, 0.55, 0.82, 0.92, 1.00),
    },
    "madder": {
        "name": "MADDER RED",
        "short": "M",
        "bottle": "#8b3435",
        "absorption": (0.78, 0.90, 0.88, 0.65, 0.38, 0.16, 0.08, 0.07, 0.08),
    },
    "weld": {
        "name": "WELD YELLOW",
        "short": "Y",
        "bottle": "#a07b22",
        "absorption": (1.00, 0.90, 0.70, 0.25, 0.08, 0.04, 0.03, 0.03, 0.04),
    },
    "logwood": {
        "name": "LOGWOOD VIOLET",
        "short": "L",
        "bottle": "#533b68",
        "absorption": (0.30, 0.18, 0.10, 0.46, 0.86, 0.84, 0.48, 0.25, 0.18),
    },
}


def _reflectance(recipe: tuple[int, ...], pigment_ids: tuple[str, ...]) -> tuple[float, ...]:
    values = []
    for band, base in enumerate(BASE_REFLECTANCE):
        optical_density = sum(
            recipe[index] * float(PIGMENTS[pigment_id]["absorption"][band])
            for index, pigment_id in enumerate(pigment_ids)
        )
        values.append(max(0.025, base * math.exp(-ABSORPTION_STRENGTH * optical_density)))
    return tuple(values)


def _xyz(reflectance: tuple[float, ...], illuminant: str) -> tuple[float, float, float]:
    spectrum = ILLUMINANTS[illuminant]
    normalizer = 1.0 / sum(spectrum[index] * CIE_1931["y"][index] for index in range(len(spectrum)))
    return tuple(
        normalizer
        * sum(
            spectrum[index] * reflectance[index] * CIE_1931[channel][index]
            for index in range(len(spectrum))
        )
        for channel in ("x", "y", "z")
    )


def _lab(reflectance: tuple[float, ...], illuminant: str) -> tuple[float, float, float]:
    xyz = _xyz(reflectance, illuminant)
    white = _xyz((1.0,) * len(WAVELENGTHS_NM), illuminant)

    def transform(value: float) -> float:
        boundary = 216.0 / 24389.0
        return value ** (1.0 / 3.0) if value > boundary else ((24389.0 / 27.0) * value + 16.0) / 116.0

    fx, fy, fz = (transform(xyz[index] / white[index]) for index in range(3))
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def _lab_to_display(lab: tuple[float, float, float], illuminant: str) -> tuple[int, int, int]:
    lightness, green_red, blue_yellow = lab
    fy = (lightness + 16.0) / 116.0
    fx = fy + green_red / 500.0
    fz = fy - blue_yellow / 200.0
    delta = 6.0 / 29.0

    def inverse(value: float) -> float:
        return value**3 if value > delta else 3.0 * delta * delta * (value - 4.0 / 29.0)

    x = 0.95047 * inverse(fx)
    y = inverse(fy)
    z = 1.08883 * inverse(fz)
    linear = (
        3.2406 * x - 1.5372 * y - 0.4986 * z,
        -0.9689 * x + 1.8758 * y + 0.0415 * z,
        0.0557 * x - 0.2040 * y + 1.0570 * z,
    )

    def encode(value: float, cast: float) -> int:
        value = min(1.0, max(0.0, value))
        encoded = 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1.0 / 2.4) - 0.055
        return round(255.0 * min(1.0, max(0.0, encoded * cast)))

    return tuple(encode(linear[index], LAMP_CASTS[illuminant][index]) for index in range(3))


def _delta_e(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return math.sqrt(sum((left[index] - right[index]) ** 2 for index in range(3)))


def _recipe_record(recipe: tuple[int, ...], pigment_ids: tuple[str, ...]) -> dict[str, Any]:
    reflectance = _reflectance(recipe, pigment_ids)
    labs = {illuminant: _lab(reflectance, illuminant) for illuminant in ILLUMINANTS}
    return {
        "recipe": recipe,
        "reflectance": reflectance,
        "lab": labs,
        "display": {
            illuminant: _lab_to_display(labs[illuminant], illuminant)
            for illuminant in ILLUMINANTS
        },
    }


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{channel:02x}" for channel in rgb)


def _choose_target(
    rng: random.Random,
    pigment_ids: tuple[str, ...],
    parameters: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None, int]:
    maximum_units = int(parameters["maximum_units_per_pigment"])
    vat_capacity = int(parameters["vat_capacity_units"])
    all_recipes = [
        recipe
        for recipe in itertools.product(range(maximum_units + 1), repeat=len(pigment_ids))
        if sum(recipe) <= vat_capacity
    ]
    records = {recipe: _recipe_record(recipe, pigment_ids) for recipe in all_recipes}
    minimum_total = int(parameters["target_total_min"])
    maximum_total = int(parameters["target_total_max"])
    minimum_components = int(parameters["target_components_min"])
    maximum_components = int(parameters["target_components_max"])
    candidates = [
        records[recipe]
        for recipe in all_recipes
        if minimum_total <= sum(recipe) <= maximum_total
        and minimum_components <= sum(units > 0 for units in recipe) <= maximum_components
        and 24.0 <= records[recipe]["lab"]["daylight"][0] <= 96.0
    ]
    candidate_recipes = {candidate["recipe"] for candidate in candidates}
    metamer_daylight_max = parameters.get("metamer_daylight_max_de")
    metamer_sodium_min = parameters.get("metamer_sodium_min_de")
    original_eligible: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for target in candidates:
        all_decoys = []
        lot_spec_decoys = []
        for other in records.values():
            recipe = other["recipe"]
            if recipe == target["recipe"]:
                continue
            day_delta = _delta_e(target["lab"]["daylight"], other["lab"]["daylight"])
            sodium_delta = _delta_e(target["lab"]["sodium"], other["lab"]["sodium"])
            if metamer_daylight_max is None:
                all_decoys.append((day_delta, -sodium_delta, other))
                if recipe in candidate_recipes:
                    lot_spec_decoys.append((day_delta, -sodium_delta, other))
            elif day_delta <= float(metamer_daylight_max) and sodium_delta >= float(metamer_sodium_min):
                all_decoys.append((day_delta, -sodium_delta, other))
                if recipe in candidate_recipes:
                    lot_spec_decoys.append((day_delta, -sodium_delta, other))
        if metamer_daylight_max is None:
            all_decoys.sort(key=lambda item: (item[0], item[1]))
            lot_spec_decoys.sort(key=lambda item: (item[0], item[1]))
            original_eligible.append((target, lot_spec_decoys[0][2] if lot_spec_decoys else None))
        elif all_decoys:
            lot_spec_decoys.sort(key=lambda item: (item[0], item[1]))
            original_eligible.append((target, lot_spec_decoys[0][2] if lot_spec_decoys else None))
    if not original_eligible:
        raise ValueError("could not construct a two-illuminant dye target for the selected profile")
    original_index = rng.randrange(len(original_eligible))
    target, decoy = original_eligible[original_index]
    lot_spec_eligible = [entry for entry in original_eligible if entry[1] is not None]
    if not lot_spec_eligible:
        raise ValueError("could not construct a lot-compliant two-illuminant alternative")
    if decoy is None:
        target, decoy = lot_spec_eligible[original_index % len(lot_spec_eligible)]
    return target, decoy, len(lot_spec_eligible)


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = task.get("_control_condition")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    defaults = {
        "pigment_count": 4,
        "target_components_min": 3,
        "target_components_max": 4,
        "target_total_min": 8,
        "target_total_max": 11,
        "maximum_units_per_pigment": 5,
        "vat_capacity_units": 13,
        "fresh_vats": 3,
        "tolerance_delta_e": 4.2,
        "metamer_daylight_max_de": 4.2,
        "metamer_sodium_min_de": 8.0,
        "graduation_support": "numbered",
    }
    for key, value in defaults.items():
        parameters.setdefault(key, value)
    pigment_count = int(parameters["pigment_count"])
    if not 2 <= pigment_count <= len(PIGMENTS):
        raise ValueError("pigment_count must be between two and four")
    if not 1 <= int(parameters["target_components_min"]) <= int(parameters["target_components_max"]) <= pigment_count:
        raise ValueError("target component bounds are invalid")
    if not 1 <= int(parameters["maximum_units_per_pigment"]) <= 6:
        raise ValueError("maximum pigment units are invalid")
    if not 1 <= int(parameters["fresh_vats"]) <= 6:
        raise ValueError("fresh vat count is invalid")
    if not 1.0 <= float(parameters["tolerance_delta_e"]) <= 12.0:
        raise ValueError("delta-E tolerance is invalid")

    difficulty = int((condition or {}).get("difficulty") or 4)
    # Keep the established seed namespace so unaffected profiles retain their
    # exact generated rack and target. Version 2 narrows only the decoy pool to
    # recipes that satisfy the same visible lot specification as the target.
    digest = hashlib.sha256(f"{seed}|{MECHANIC_ID}|d{difficulty}|v1".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    pigment_ids = list(PIGMENTS)
    rng.shuffle(pigment_ids)
    pigment_ids = tuple(pigment_ids[:pigment_count])
    target, decoy, eligible_count = _choose_target(rng, pigment_ids, parameters)
    task_id = str(task.get("id") or "two_lamp_dyeworks_seed_0001@0.1")
    challenge_id = hashlib.sha256(
        f"{seed}|{MECHANIC_ID}|d{difficulty}|{task_id}|{target['recipe']}".encode("utf-8")
    ).hexdigest()[:18]
    pigment_records = [
        {
            "id": pigment_id,
            "name": PIGMENTS[pigment_id]["name"],
            "short": PIGMENTS[pigment_id]["short"],
            "bottle": PIGMENTS[pigment_id]["bottle"],
            "absorption": list(PIGMENTS[pigment_id]["absorption"]),
        }
        for pigment_id in pigment_ids
    ]
    prompt = task.get("natural_language") or (
        "Match the pinned ribbon with one irreversible dye mixture. Stir and dip, then inspect the strip under both lamps."
    )
    public_state: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": prompt,
        "submit_label": "SEAL THE DYE LOT",
        "asset_manifest": "shared_runtime/assets/provenance/two_lamp_dyeworks_v0.json",
        "generator": {
            "name": "two_lamp_dyeworks_v2",
            "eligible_target_count": eligible_count,
            "variant_count": eligible_count * math.factorial(pigment_count),
            "variant_count_kind": "eligible lot-spec spectral recipes times pigment-rack order",
        },
        "pigments": pigment_records,
        "target": {
            "display": {illuminant: _hex(target["display"][illuminant]) for illuminant in ILLUMINANTS},
            "lab": {illuminant: [round(value, 8) for value in target["lab"][illuminant]] for illuminant in ILLUMINANTS},
        },
        "spectral_model": {
            "wavelengths_nm": list(WAVELENGTHS_NM),
            "base_reflectance": list(BASE_REFLECTANCE),
            "absorption_strength": ABSORPTION_STRENGTH,
            "cie_1931": {key: list(value) for key, value in CIE_1931.items()},
            "illuminants": {key: list(value) for key, value in ILLUMINANTS.items()},
            "lamp_casts": {key: list(value) for key, value in LAMP_CASTS.items()},
        },
        "parameters": copy.deepcopy(parameters),
        "lamp_labels": {"daylight": "NORTH-LIGHT", "sodium": "SODIUM"},
        "initial_lamp": "daylight",
        "grading_rule": (
            f"A freshly dipped strip must use {int(parameters['target_components_min'])}–"
            f"{int(parameters['target_components_max'])} active dye families, contain "
            f"{int(parameters['target_total_min'])}–{int(parameters['target_total_max'])} total units, "
            "and fall within the stated CIE colour tolerance under both illuminants."
        ),
    }
    target_recipe = {pigment_ids[index]: target["recipe"][index] for index in range(pigment_count)}
    ground_truth: dict[str, Any] = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "pigment_ids": list(pigment_ids),
        "target_recipe": target_recipe,
        "target_recipe_vector": list(target["recipe"]),
        "target_reflectance": [round(value, 12) for value in target["reflectance"]],
        "target_lab": {illuminant: [round(value, 8) for value in target["lab"][illuminant]] for illuminant in ILLUMINANTS},
        "target_display": {illuminant: _hex(target["display"][illuminant]) for illuminant in ILLUMINANTS},
        "parameters": copy.deepcopy(parameters),
        "canonical_plan": [
            {"pigment": pigment_id, "units": target_recipe[pigment_id]}
            for pigment_id in pigment_ids
            if target_recipe[pigment_id] > 0
        ],
        "near_metamer": None,
        "spectral_contract": {
            "wavelengths_nm": list(WAVELENGTHS_NM),
            "base_reflectance": list(BASE_REFLECTANCE),
            "absorption_strength": ABSORPTION_STRENGTH,
            "cie_1931": {key: list(value) for key, value in CIE_1931.items()},
            "illuminants": {key: list(value) for key, value in ILLUMINANTS.items()},
            "lamp_casts": {key: list(value) for key, value in LAMP_CASTS.items()},
            "pigments": copy.deepcopy(pigment_records),
        },
        "variant_count": eligible_count * math.factorial(pigment_count),
        "variant_count_kind": "eligible lot-spec spectral recipes times pigment-rack order",
    }
    if decoy is not None:
        ground_truth["near_metamer"] = {
            "recipe": {pigment_ids[index]: decoy["recipe"][index] for index in range(pigment_count)},
            "daylight_delta_e": round(_delta_e(target["lab"]["daylight"], decoy["lab"]["daylight"]), 6),
            "sodium_delta_e": round(_delta_e(target["lab"]["sodium"], decoy["lab"]["sodium"]), 6),
        }
    if condition:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
