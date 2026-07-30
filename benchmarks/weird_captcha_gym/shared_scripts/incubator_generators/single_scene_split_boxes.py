from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "single_scene_split_boxes"
PALETTES = ("abyssal_cyan", "ember_violet", "acid_noir", "polar_signal")
MOTIFS = ("orbital_marsh", "night_freight", "glass_reef", "signal_dunes")
PHASE_TICKS = (-4, -3, -2, -1, 0, 1, 2, 3, 4)
VARIANT_COUNT = 7_431_782_400


def _tile_id(seed: str, source_index: int) -> str:
    return f"shard-{hashlib.sha256(f'{seed}|tile|{source_index}'.encode('utf-8')).hexdigest()[:6]}"


def _shuffled_slots(rng: random.Random, source_count: int = 9, minimum_displaced: int = 8) -> list[int]:
    source_indices = list(range(source_count))
    for _attempt in range(100):
        shuffled = source_indices[:]
        rng.shuffle(shuffled)
        if sum(index != source for index, source in enumerate(shuffled)) >= minimum_displaced:
            return shuffled
    raise ValueError("could not produce a meaningfully shattered mosaic")


def _phase_offsets(
    rng: random.Random,
    source_count: int = 9,
    phase_ticks: tuple[int, ...] = PHASE_TICKS,
    minimum_nonzero: int = 7,
    minimum_distinct: int = 5,
) -> list[int]:
    for _attempt in range(100):
        phases = [rng.choice(phase_ticks) for _ in range(source_count)]
        if (
            sum(value != 0 for value in phases) >= minimum_nonzero
            and len(set(phases)) >= minimum_distinct
            and 0 in phases
        ):
            return phases
    raise ValueError("could not produce varied temporal offsets")


def _int_parameter(parameters: dict[str, Any], name: str, default: int) -> int:
    value = parameters.get(name, default)
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    return int(value)


def _phase_values(parameters: dict[str, Any]) -> tuple[int, ...]:
    raw = parameters.get("phase_values", PHASE_TICKS)
    if not isinstance(raw, (list, tuple)) or not raw or any(isinstance(value, bool) or not isinstance(value, int) for value in raw):
        raise ValueError("phase_values must be a non-empty integer list")
    values = tuple(int(value) for value in raw)
    if 0 not in values:
        raise ValueError("phase_values must include master phase zero")
    return values


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    digest = hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    task_id = str(task.get("id") or "single_scene_split_boxes_seed_0001@0.1")
    condition = task.get("_control_condition")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    rows = _int_parameter(parameters, "rows", 3)
    columns = _int_parameter(parameters, "columns", 3)
    if not 2 <= rows <= 4 or not 2 <= columns <= 4:
        raise ValueError("split-box grids must be between two and four rows and columns")
    source_count = rows * columns
    minimum_displaced = _int_parameter(parameters, "minimum_displaced", 8)
    rotation_minimum = _int_parameter(parameters, "rotation_minimum", 3)
    rotation_maximum = _int_parameter(parameters, "rotation_maximum", 5)
    phase_values = _phase_values(parameters)
    minimum_phase_nonzero = _int_parameter(parameters, "minimum_phase_nonzero", 7)
    minimum_phase_distinct = _int_parameter(parameters, "minimum_phase_distinct", 5)
    decoy_count = _int_parameter(parameters, "decoy_count", 5)
    speed_scale_milli = _int_parameter(parameters, "speed_scale_milli", 1000)
    phase_tick_ms = _int_parameter(parameters, "phase_tick_ms", 180)
    hold_ms = _int_parameter(parameters, "hold_ms", 700)
    sample_ms = _int_parameter(parameters, "sample_ms", 100)
    minimum_samples = _int_parameter(parameters, "minimum_samples", 6)
    if not 1 <= minimum_displaced < source_count:
        raise ValueError("minimum_displaced must leave at least one source tile")
    if not 0 <= rotation_minimum <= rotation_maximum <= source_count:
        raise ValueError("rotation profile is outside the source grid")
    if not 0 <= minimum_phase_nonzero < source_count or not 1 <= minimum_phase_distinct <= len(phase_values):
        raise ValueError("phase profile is outside the source grid")
    if decoy_count < 0 or speed_scale_milli <= 0 or phase_tick_ms <= 0 or hold_ms <= 0 or sample_ms <= 0 or minimum_samples <= 0:
        raise ValueError("split-box profile contains a non-positive timing or motion value")

    # The historical uncontrolled and controlled L4 states intentionally use
    # the same challenge identity for a fixed seed.  Other controlled levels
    # need distinct IDs even when a materializer exercises every profile with
    # one shared seed.  Interaction is deliberately excluded so the paired
    # simplified and full surfaces still describe the same challenge.
    challenge_seed = seed
    if condition and int(condition.get("difficulty") or 4) != 4:
        challenge_seed = f"{seed}|difficulty:{int(condition['difficulty'])}"
    challenge_id = hashlib.sha256(f"{challenge_seed}|live-shattered-scene".encode("utf-8")).hexdigest()[:12]
    palette = PALETTES[rng.randrange(len(PALETTES))]
    motif = MOTIFS[rng.randrange(len(MOTIFS))]
    source_by_slot = _shuffled_slots(rng, source_count, minimum_displaced)
    rotation_sources = set(rng.sample(range(source_count), rng.randint(rotation_minimum, rotation_maximum)))
    source_phases = _phase_offsets(
        rng,
        source_count,
        phase_values,
        minimum_phase_nonzero,
        minimum_phase_distinct,
    )
    tiles: list[dict[str, Any]] = []
    for slot, source_index in enumerate(source_by_slot):
        tiles.append(
            {
                "id": _tile_id(seed, source_index),
                "source": {"row": source_index // columns, "column": source_index % columns},
                "initial_slot": slot,
                "initial_rotation": 180 if source_index in rotation_sources else 0,
                "initial_phase": source_phases[source_index],
            }
        )

    def scaled(value: int) -> int:
        return value * speed_scale_milli // 1000

    scene = {
        "width": 900,
        "height": 600,
        "rows": rows,
        "columns": columns,
        "period_ms": 12000,
        "phase_tick_ms": phase_tick_ms,
        "field_seed": rng.randrange(1, 2_000_000_000),
        "horizon": rng.randint(285, 365),
        "target": {
            "radius": rng.randint(24, 34),
            "speed_x_milli": scaled(rng.randint(460, 690)),
            "speed_y_milli": scaled(rng.randint(240, 410)),
            "phase": rng.randrange(0, 12000),
        },
        "decoys": [
            {
                "radius": rng.randint(10, 19),
                "speed_x_milli": scaled(rng.randint(180, 390)),
                "speed_y_milli": scaled(rng.randint(110, 260)),
                "phase": rng.randrange(0, 12000),
                "depth_milli": rng.choice((350, 520, 740, 900)),
            }
            for _ in range(decoy_count)
        ],
        "motif": motif,
    }
    requirements = {
        "hold_ms": hold_ms,
        "sample_ms": sample_ms,
        "minimum_samples": minimum_samples,
        "minimum_spatial_touches": len(
            {
                tile["id"]
                for tile in tiles
                if tile["initial_slot"] != (tile["source"]["row"] * columns + tile["source"]["column"])
            }
        ),
        "minimum_rotation_touches": len(rotation_sources),
        "minimum_phase_touches": sum(value != 0 for value in source_phases),
    }
    phase_range = {"minimum": min(phase_values), "maximum": max(phase_values)}
    sync_rule = f"Hold scene sync continuously for roughly {hold_ms} ms after all seams stabilize."
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language")
        or "Rebuild the live scene in space, orientation, and time. Hold SYNC while every seam remains continuous.",
        "submit_label": "HOLD SCENE SYNC",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "generator": {
            "name": "live_shattered_scene_synchronizer_v1",
            "variant_count": VARIANT_COUNT,
            "variant_count_kind": "palette/motif/permutation/rotation/phase construction space",
        },
        "scene": scene,
        "tiles": tiles,
        "phase_range": phase_range,
        "requirements": requirements,
        "palette": palette,
        "rules": {
            "space": "Drag one tile onto another to swap their mosaic positions.",
            "rotation": "Select a tile and flip it 180 degrees when its fragment is inverted.",
            "time": "Scrub each selected shard onto the master chronograph so motion crosses every seam.",
            "sync": sync_rule,
        },
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "scene": scene,
        "tiles": tiles,
        "phase_range": phase_range,
        "requirements": requirements,
        "solution_slots": {_tile_id(seed, source_index): source_index for source_index in range(source_count)},
        "solution_rotation": 0,
        "solution_phase": 0,
        "initial_rotation_sources": sorted(rotation_sources),
        "initial_phase_sources": [index for index, value in enumerate(source_phases) if value != 0],
        "palette": palette,
        "motif": motif,
        "variant_count": VARIANT_COUNT,
        "variant_count_kind": "palette/motif/permutation/rotation/phase construction space",
    }
    if condition:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
