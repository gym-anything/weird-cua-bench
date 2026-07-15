from __future__ import annotations

import hashlib
import random
from typing import Any


MECHANIC_ID = "rorschach_fixed_rubric"
TOOLS = ("FOLD", "PRESSURE", "COOL")
TICKS_PER_CYCLE = 7
STAGE_WIDTH = 1000
STAGE_HEIGHT = 420
OBJECTIVES = {
    "retains_fold": "RETAINS ITS FOLD AFTER RELEASE",
    "symmetric_rebound": "REBOUNDS SYMMETRICALLY AFTER PRESSURE",
    "cooling_inversion": "INVERTS ITS LOBE FLOW UNDER COOLING",
}
SIGNATURE_FOR_TOOL = {"FOLD": "retains_fold", "PRESSURE": "symmetric_rebound", "COOL": "cooling_inversion"}


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _normal_metrics(tool: str, tick: int, phase: int) -> dict[str, int]:
    if tool == "FOLD":
        fold = 72 - abs(4 - tick) * 16 if tick <= 4 else max(0, 60 - tick * 8)
        return {"left": 100 - tick, "right": 100 + tick, "fold": max(0, fold), "hue": phase, "flow": 8}
    if tool == "PRESSURE":
        return {"left": 100 - 3 * tick, "right": 100 + 3 * tick, "fold": 0, "hue": phase, "flow": 12}
    return {"left": 100 - tick, "right": 100 - tick, "fold": 0, "hue": phase + 4 * tick, "flow": 15}


def _signature_metrics(signature: str, tool: str, tick: int, phase: int) -> dict[str, int]:
    if signature == "retains_fold" and tool == "FOLD":
        return {"left": 96, "right": 104, "fold": min(84, 12 * tick), "hue": phase, "flow": 5}
    if signature == "symmetric_rebound" and tool == "PRESSURE":
        squeeze = max(72, 100 - 8 * min(tick, 4))
        rebound = 100 if tick >= 6 else squeeze
        return {"left": rebound, "right": rebound, "fold": 0, "hue": phase, "flow": 22}
    if signature == "cooling_inversion" and tool == "COOL":
        return {"left": 100 + 2 * tick, "right": 100 - 2 * tick, "fold": 0, "hue": (phase + 26 * tick) % 360, "flow": -10 - 3 * tick}
    return _normal_metrics(tool, tick, phase)


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    required_tools = rng.sample(list(TOOLS), 2)
    signatures = [SIGNATURE_FOR_TOOL[tool] for tool in required_tools]
    blot_ids = [f"blot-{index + 1}" for index in range(5)]
    culprit_id = rng.choice(blot_ids)
    blots = []
    blot_rects = []
    phases: dict[str, int] = {}
    for index, blot_id in enumerate(blot_ids):
        phase = rng.randrange(-12, 13)
        phases[blot_id] = phase
        rect = {"id": blot_id, "x": 20 + index * 192, "y": 24, "width": 172, "height": 250}
        blot_rects.append(rect)
        blots.append({
            "id": blot_id,
            "specimen": f"MAT-{rng.choice('ABCDEFGH')}{rng.randint(10, 99)}",
            "rect": rect,
            "visual_seed": rng.randrange(10_000),
        })

    shuffled_distractors = [blot_id for blot_id in blot_ids if blot_id != culprit_id]
    rng.shuffle(shuffled_distractors)
    response_signatures: dict[str, list[str]] = {
        culprit_id: signatures[:],
        shuffled_distractors[0]: [signatures[0]],
        shuffled_distractors[1]: [signatures[1]],
        shuffled_distractors[2]: [],
        shuffled_distractors[3]: [rng.choice(signatures)],
    }
    cycles = []
    for blot_id in blot_ids:
        for tool in required_tools:
            signature = SIGNATURE_FOR_TOOL[tool]
            frames = []
            for tick in range(1, TICKS_PER_CYCLE + 1):
                metrics = (
                    _signature_metrics(signature, tool, tick, phases[blot_id])
                    if signature in response_signatures[blot_id]
                    else _normal_metrics(tool, tick, phases[blot_id])
                )
                frames.append({"tick": tick, "snapshot": {"blot_id": blot_id, **metrics}})
            cycles.append({"blot_id": blot_id, "tool": tool, "frames": frames})

    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode("utf-8")).hexdigest()[:12]
    task_id = str(task.get("id") or "rorschach_fixed_rubric_seed_0001@0.1")
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": "Interrogate every specimen; initial appearance is non-diagnostic.",
        "objective": f"STAMP THE ONLY BLOT THAT {OBJECTIVES[signatures[0]]} AND {OBJECTIVES[signatures[1]]}.",
        "submit_label": "CERTIFY MATERIAL STAMP",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "generator": {"name": "specimen_bound_material_interrogation_v2", "variant_count": 11_800_000_000},
        "stage": {"width": STAGE_WIDTH, "height": STAGE_HEIGHT},
        "blots": blots,
        "blot_rects": blot_rects,
        "stamp_dock_rect": {"x": 398, "y": 320, "width": 204, "height": 76},
        "required_tools": required_tools,
        "cycles": cycles,
        "observations_required": len(blot_ids) * len(required_tools),
        "ticks_per_cycle": TICKS_PER_CYCLE,
        "tick_ms": 105,
        "fold_min_distance": 190,
        "pressure_min_ms": 620,
        "rubric_labels": [OBJECTIVES[signature] for signature in signatures],
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "required_tools": required_tools,
        "cycles": cycles,
        "observations_required": public_state["observations_required"],
        "ticks_per_cycle": TICKS_PER_CYCLE,
        "stage": public_state["stage"],
        "blot_rects": blot_rects,
        "stamp_dock_rect": public_state["stamp_dock_rect"],
        "fold_min_distance": public_state["fold_min_distance"],
        "pressure_min_ms": public_state["pressure_min_ms"],
        "culprit_id": culprit_id,
        "signatures": signatures,
        "response_signatures": response_signatures,
        "variant_count": public_state["generator"]["variant_count"],
    }
    assert len(blots) == 5 and len(cycles) == 10
    assert sum(set(signatures).issubset(set(values)) for values in response_signatures.values()) == 1
    return public_state, ground_truth
