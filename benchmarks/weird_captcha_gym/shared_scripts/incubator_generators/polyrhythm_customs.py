from __future__ import annotations

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


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    beat_ms = rng.choice((380, 400, 420))
    lead_ms = rng.choice((380, 420, 460))
    patterns = [
        [0, 4, 8, 12, 16],
        [1, 6, 11, 16],
        [2, 5, 9, 13, 17],
        [3, 7, 10, 14],
    ]
    rng.shuffle(patterns)

    chord_slots = rng.sample((6, 8, 10, 12, 13, 14), 2)
    chord_specs: list[dict[str, Any]] = []
    slots_by_lane = [set(pattern) for pattern in patterns]
    chord_by_lane_slot: dict[tuple[int, int], str] = {}
    for chord_index, slot in enumerate(chord_slots, start=1):
        pair = sorted(rng.sample(range(len(LANES)), 2))
        chord_id = f"chord-{chord_index}"
        for lane_index in pair:
            slots_by_lane[lane_index].add(slot)
            chord_by_lane_slot[(lane_index, slot)] = chord_id
        chord_specs.append(
            {
                "id": chord_id,
                "lanes": [LANES[index]["id"] for index in pair],
                "start_ms": lead_ms + slot * beat_ms,
            }
        )

    hold_lanes = rng.sample(range(len(LANES)), 2)
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

    notes: list[dict[str, Any]] = []
    for lane_index, lane in enumerate(LANES):
        for note_index, slot in enumerate(sorted(slots_by_lane[lane_index])):
            chord_id = chord_by_lane_slot.get((lane_index, slot))
            jitter = 0 if chord_id else rng.randrange(-24, 25, 4)
            is_hold = hold_slots.get(lane_index) == slot
            duration_ms = rng.randrange(650, 751, 20) if is_hold else rng.randrange(90, 131, 10)
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
    performance_ms = max(int(note["start_ms"]) + int(note["duration_ms"]) for note in notes) + 520
    preview_order = list(range(len(LANES)))
    rng.shuffle(preview_order)
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|v2".encode("utf-8")).hexdigest()[:12]
    task_id = str(task.get("id") or "")
    settings = {
        "performance_ms": performance_ms,
        "preview_scale": 0.44,
        "preview_gap_ms": 280,
        "countdown_ms": 1_650,
        "start_window_ms": 240,
        "duration_tolerance_ms": 340,
        "chord_window_ms": 180,
        "pass_accuracy": 0.86,
    }
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Inspect four lanes separately. Then perform their combined clearance on A, S, D, and F.",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_puzzles_v1.json",
        "generator": {"name": "polyrhythm_customs_v2", "variant_count": 12_000_000_000},
        "lanes": [dict(lane) for lane in LANES],
        "score": notes,
        "preview_order": preview_order,
        "settings": settings,
        "rules": {
            "start_window_ms": settings["start_window_ms"],
            "duration_tolerance_ms": settings["duration_tolerance_ms"],
            "chord_window_ms": settings["chord_window_ms"],
            "pass_accuracy_percent": 86,
        },
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "lanes": [dict(lane) for lane in LANES],
        "expected_notes": notes,
        "chords": chord_specs,
        "settings": settings,
        "variant_count": 12_000_000_000,
    }
    assert 18 <= len(notes) <= 22
    assert sum(note["kind"] == "hold" for note in notes) == 2
    assert len(chord_specs) == 2
    assert all(sum(note.get("chord_id") == chord["id"] for note in notes) == 2 for chord in chord_specs)
    return public_state, ground_truth
