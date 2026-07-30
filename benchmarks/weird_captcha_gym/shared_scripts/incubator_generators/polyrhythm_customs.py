from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "polyrhythm_customs"
LANES = (
    {"id": "lane-a", "key": "A", "label": "AMBER", "glyph": "◆"},
    {"id": "lane-s", "key": "S", "label": "SIGNAL", "glyph": "●"},
    {"id": "lane-d", "key": "D", "label": "DOCK", "glyph": "▰"},
    {"id": "lane-f", "key": "F", "label": "FOG", "glyph": "✦"},
)


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}|v2".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _controlled_profile(task: dict[str, Any]) -> dict[str, Any] | None:
    condition = task.get("_control_condition")
    if condition is None:
        return None
    parameters = dict(condition.get("difficulty_parameters") or {})
    if not parameters:
        raise ValueError("controlled polyrhythm task has no difficulty parameters")
    return parameters


def _int_tuple(parameters: dict[str, Any], name: str, default: tuple[int, ...]) -> tuple[int, ...]:
    raw = parameters.get(name, default)
    if not isinstance(raw, list) or not raw:
        if raw is default:
            return default
        raise ValueError(f"polyrhythm {name} must be a non-empty list")
    values = tuple(int(value) for value in raw)
    if any(value <= 0 for value in values):
        raise ValueError(f"polyrhythm {name} values must be positive")
    return values


def _pattern_rows(parameters: dict[str, Any], lane_count: int) -> list[list[int]]:
    raw = parameters.get("patterns")
    if raw is None:
        return [
            [0, 4, 8, 12, 16],
            [1, 6, 11, 16],
            [2, 5, 9, 13, 17],
            [3, 7, 10, 14],
        ][:lane_count]
    if not isinstance(raw, list) or len(raw) != lane_count:
        raise ValueError("polyrhythm patterns must contain one non-empty row per active lane")
    rows = [[int(slot) for slot in row] for row in raw]
    if any(not row or any(slot < 0 for slot in row) or row != sorted(set(row)) for row in rows):
        raise ValueError("polyrhythm pattern slots must be unique non-negative integers")
    return rows


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    condition = task.get("_control_condition")
    parameters = _controlled_profile(task) or {}
    lane_count = int(parameters.get("lane_count", len(LANES)))
    if not 2 <= lane_count <= len(LANES):
        raise ValueError("polyrhythm lane_count must be between two and four")
    active_lanes = [dict(lane) for lane in LANES[:lane_count]]
    beat_values = _int_tuple(parameters, "beat_ms_values", (380, 400, 420))
    lead_values = _int_tuple(parameters, "lead_ms_values", (380, 420, 460))
    beat_ms = rng.choice(beat_values)
    lead_ms = rng.choice(lead_values)
    patterns = _pattern_rows(parameters, lane_count)
    rng.shuffle(patterns)

    raw_chord_slots = parameters.get("chord_slot_choices", [6, 8, 10, 12, 13, 14])
    if not isinstance(raw_chord_slots, list):
        raise ValueError("polyrhythm chord_slot_choices must be a list")
    chord_slot_choices = tuple(int(slot) for slot in raw_chord_slots)
    chord_count = int(parameters.get("chord_count", 2))
    hold_count = int(parameters.get("hold_count", 2))
    if not 0 <= chord_count <= len(chord_slot_choices) or not 0 <= hold_count <= lane_count:
        raise ValueError("polyrhythm chord or hold profile is outside supported limits")
    chord_slots = rng.sample(chord_slot_choices, chord_count)
    chord_specs: list[dict[str, Any]] = []
    slots_by_lane = [set(pattern) for pattern in patterns]
    chord_by_lane_slot: dict[tuple[int, int], str] = {}
    for chord_index, slot in enumerate(chord_slots, start=1):
        pair = sorted(rng.sample(range(len(active_lanes)), 2))
        chord_id = f"chord-{chord_index}"
        for lane_index in pair:
            slots_by_lane[lane_index].add(slot)
            chord_by_lane_slot[(lane_index, slot)] = chord_id
        chord_specs.append(
            {
                "id": chord_id,
                "lanes": [active_lanes[index]["id"] for index in pair],
                "start_ms": lead_ms + slot * beat_ms,
            }
        )

    hold_lanes = rng.sample(range(len(active_lanes)), hold_count)
    hold_slots: dict[int, int] = {}
    for lane_index in hold_lanes:
        ordered = sorted(slots_by_lane[lane_index])
        candidates = [
            slot
            for slot, following in zip(ordered, ordered[1:])
            if following - slot >= 2 and (lane_index, slot) not in chord_by_lane_slot
        ]
        if not candidates:
            candidates = [slot for slot in ordered[:-1] if (lane_index, slot) not in chord_by_lane_slot]
        hold_slots[lane_index] = rng.choice(candidates)

    tap_jitter_min = int(parameters.get("tap_jitter_min_ms", -24))
    tap_jitter_max = int(parameters.get("tap_jitter_max_ms", 24))
    tap_jitter_step = int(parameters.get("tap_jitter_step_ms", 4))
    tap_duration_min = int(parameters.get("tap_duration_min_ms", 90))
    tap_duration_max = int(parameters.get("tap_duration_max_ms", 130))
    tap_duration_step = int(parameters.get("tap_duration_step_ms", 10))
    hold_duration_min = int(parameters.get("hold_duration_min_ms", 650))
    hold_duration_max = int(parameters.get("hold_duration_max_ms", 750))
    hold_duration_step = int(parameters.get("hold_duration_step_ms", 20))
    if (
        tap_jitter_step <= 0
        or tap_duration_step <= 0
        or hold_duration_step <= 0
        or tap_jitter_min > tap_jitter_max
        or tap_duration_min <= 0
        or tap_duration_min > tap_duration_max
        or hold_duration_min <= 0
        or hold_duration_min > hold_duration_max
    ):
        raise ValueError("polyrhythm timing profile is malformed")
    notes: list[dict[str, Any]] = []
    for lane_index, lane in enumerate(active_lanes):
        for note_index, slot in enumerate(sorted(slots_by_lane[lane_index])):
            chord_id = chord_by_lane_slot.get((lane_index, slot))
            jitter = 0 if chord_id else rng.randrange(tap_jitter_min, tap_jitter_max + 1, tap_jitter_step)
            is_hold = hold_slots.get(lane_index) == slot
            duration_ms = (
                rng.randrange(hold_duration_min, hold_duration_max + 1, hold_duration_step)
                if is_hold
                else rng.randrange(tap_duration_min, tap_duration_max + 1, tap_duration_step)
            )
            notes.append(
                {
                    "id": f"note-{lane_index}-{note_index}",
                    "lane": lane["id"],
                    "start_ms": lead_ms + slot * beat_ms + jitter,
                    "duration_ms": duration_ms,
                    "kind": "hold" if is_hold else "tap",
                    "chord_id": chord_id,
                }
            )
    notes.sort(key=lambda note: (int(note["start_ms"]), str(note["lane"])))
    performance_padding_ms = int(parameters.get("performance_padding_ms", 520))
    if performance_padding_ms < 0:
        raise ValueError("polyrhythm performance_padding_ms must be non-negative")
    performance_ms = max(int(note["start_ms"]) + int(note["duration_ms"]) for note in notes) + performance_padding_ms
    preview_order = list(range(len(active_lanes)))
    rng.shuffle(preview_order)
    condition_token = ""
    if condition and int(condition["difficulty"]) != 4:
        condition_token = f"|d{int(condition['difficulty'])}"
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|v2{condition_token}".encode("utf-8")).hexdigest()[:12]
    task_id = str(task.get("id") or "")
    settings = {
        "performance_ms": performance_ms,
        "preview_scale": float(parameters.get("preview_scale", 0.44)),
        "preview_gap_ms": int(parameters.get("preview_gap_ms", 280)),
        "countdown_ms": int(parameters.get("countdown_ms", 1_650)),
        "start_window_ms": int(parameters.get("start_window_ms", 240)),
        "duration_tolerance_ms": int(parameters.get("duration_tolerance_ms", 340)),
        "chord_window_ms": int(parameters.get("chord_window_ms", 180)),
        "pass_accuracy": float(parameters.get("pass_accuracy", 0.86)),
    }
    if (
        settings["preview_scale"] <= 0
        or settings["preview_gap_ms"] < 0
        or settings["countdown_ms"] <= 0
        or settings["start_window_ms"] <= 0
        or settings["duration_tolerance_ms"] <= 0
        or settings["chord_window_ms"] <= 0
        or not 0 < settings["pass_accuracy"] <= 1
    ):
        raise ValueError("polyrhythm public timing settings are malformed")
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Inspect four lanes separately. Then perform their combined clearance on A, S, D, and F.",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_puzzles_v1.json",
        "generator": {"name": "polyrhythm_customs_v2", "variant_count": 12_000_000_000},
        "lanes": active_lanes,
        "score": notes,
        "preview_order": preview_order,
        "settings": settings,
        "rules": {
            "start_window_ms": settings["start_window_ms"],
            "duration_tolerance_ms": settings["duration_tolerance_ms"],
            "chord_window_ms": settings["chord_window_ms"],
            "pass_accuracy_percent": round(settings["pass_accuracy"] * 100),
        },
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "lanes": active_lanes,
        "expected_notes": notes,
        "chords": chord_specs,
        "settings": settings,
        "variant_count": 12_000_000_000,
    }
    if condition:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    if not condition:
        assert 18 <= len(notes) <= 22
    assert sum(note["kind"] == "hold" for note in notes) == hold_count
    assert len(chord_specs) == chord_count
    assert all(sum(note.get("chord_id") == chord["id"] for note in notes) == 2 for chord in chord_specs)
    return public_state, ground_truth
