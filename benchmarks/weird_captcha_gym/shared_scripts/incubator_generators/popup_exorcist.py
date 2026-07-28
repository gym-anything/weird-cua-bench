from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "popup_exorcist"
THEMES = ("update", "coupon", "cleaner", "forecast", "player", "survey", "prize")
TITLE_CHOICES = ("SERVICE NOTICE", "BACKGROUND TASK", "DESKTOP MESSAGE", "SYSTEM ASSISTANT")
SPARSE_SLOTS = (
    (18, 20),
    (446, 24),
    (232, 218),
    (28, 222),
    (458, 210),
)


def _seed(seed: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{MECHANIC_ID}|v2".encode()).digest()[:8], "big")


def _position(
    rng: random.Random,
    *,
    index: int,
    width: int,
    height: int,
    profile: str,
) -> tuple[int, int]:
    maximum_x = 690 - width
    maximum_y = 365 - height
    if profile in {"sparse", "spread"}:
        slot_x, slot_y = SPARSE_SLOTS[index % len(SPARSE_SLOTS)]
        jitter = 4 if profile == "sparse" else 12
        return (
            max(18, min(maximum_x, slot_x + rng.randint(-jitter, jitter))),
            max(20, min(maximum_y, slot_y + rng.randint(-jitter, jitter))),
        )
    if profile == "dense":
        return rng.randint(84, max(84, maximum_x - 34)), rng.randint(42, max(42, maximum_y - 22))
    if profile == "very_dense":
        return rng.randint(116, max(116, maximum_x - 56)), rng.randint(58, max(58, maximum_y - 34))
    if profile != "legacy":
        raise ValueError(f"unsupported popup layout profile {profile!r}")
    return rng.randint(18, maximum_x), rng.randint(20, maximum_y)


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed(seed))
    condition = task.get("_control_condition")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    popup_count = int(parameters.get("popup_count", len(THEMES)))
    layout_profile = str(parameters.get("layout_profile", "legacy"))
    width_min = int(parameters.get("window_width_min", 205))
    width_max = int(parameters.get("window_width_max", 270))
    height_min = int(parameters.get("window_height_min", 126))
    height_max = int(parameters.get("window_height_max", 178))
    parasite_min = int(parameters.get("parasite_index_min", 1))
    parasite_max = int(parameters.get("parasite_index_max_exclusive", 6))
    parasite_count = int(parameters.get("parasite_count", 1))
    parasite_cue = str(parameters.get("parasite_cue", "none"))
    echo_count = int(parameters.get("echo_count", 2))
    maximum_resistance_strikes = int(parameters.get("maximum_resistance_strikes", 3))
    containment = copy.deepcopy(parameters.get("containment") or {"x": 530, "y": 292, "w": 160, "h": 88})
    if not 3 <= popup_count <= 11:
        raise ValueError("popup_count must be between 3 and 11")
    if not (160 <= width_min <= width_max <= 300 and 100 <= height_min <= height_max <= 210):
        raise ValueError("popup window dimensions are outside the supported field")
    if not 0 <= parasite_min < parasite_max <= popup_count:
        raise ValueError("parasite index range is invalid")
    if not 1 <= parasite_count <= 3 or parasite_count > parasite_max - parasite_min:
        raise ValueError("parasite_count is outside the configured index range")
    if parasite_cue not in {"none", "subtle", "explicit"}:
        raise ValueError("parasite cue is invalid")
    if not 1 <= echo_count <= 3:
        raise ValueError("echo_count must be between 1 and 3")
    if not 2 <= maximum_resistance_strikes <= 6:
        raise ValueError("maximum resistance strikes must be between 2 and 6")

    raw_stages = copy.deepcopy(parameters.get("containment_stages") or [containment])
    if not isinstance(raw_stages, list) or len(raw_stages) != parasite_count:
        raise ValueError("one containment stage is required for every parasite strain")
    containment_stages: list[dict[str, int]] = []
    for raw_stage in raw_stages:
        try:
            stage = {
                "x": int(raw_stage["x"]),
                "y": int(raw_stage["y"]),
                "w": int(raw_stage["w"]),
                "h": int(raw_stage["h"]),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("containment bounds are invalid") from exc
        if not (
            0 <= stage["x"] < 700
            and 0 <= stage["y"] < 390
            and 64 <= stage["w"] <= 260
            and 48 <= stage["h"] <= 150
        ):
            raise ValueError("containment well is outside the supported field")
        if stage["x"] + stage["w"] > 700 or stage["y"] + stage["h"] > 390:
            raise ValueError("containment well exceeds the field")
        containment_stages.append(stage)

    if parasite_count == 1:
        # Preserve the original generator's random draw order exactly.
        parasite_indices = [rng.randrange(parasite_min, parasite_max)]
    else:
        parasite_indices = sorted(rng.sample(range(parasite_min, parasite_max), parasite_count))
    parasite_index_set = set(parasite_indices)
    popups = []
    popup_ids_by_index: dict[int, str] = {}
    for index in range(popup_count):
        theme = THEMES[index % len(THEMES)]
        width, height = rng.randint(width_min, width_max), rng.randint(height_min, height_max)
        popup_id = f"window-{hashlib.sha256(f'{seed}|window|{index}'.encode()).hexdigest()[:8]}"
        popup_ids_by_index[index] = popup_id
        title = rng.choice(TITLE_CHOICES)
        x, y = _position(rng, index=index, width=width, height=height, profile=layout_profile)
        popup = {
            "id": popup_id,
            "theme": theme,
            "title": title,
            "x": x,
            "y": y,
            "w": width,
            "h": height,
            "z": index + 2,
            "runtime_behavior": "replicate" if index in parasite_index_set else "close",
        }
        if index in parasite_index_set and parasite_cue != "none":
            popup["anomaly_cue"] = parasite_cue
        popups.append(popup)
    stage_batches: list[list[str]] = []
    if parasite_count > 1:
        # Higher profiles are sequential waves. Exactly one parasite belongs to
        # each wave, and later candidates do not enter the visible desktop until
        # the previous strain has been contained.
        stage_by_index = {
            parasite_index: stage_index
            for stage_index, parasite_index in enumerate(parasite_indices)
        }
        decoy_indices = [
            index for index in range(popup_count) if index not in parasite_index_set
        ]
        for decoy_offset, decoy_index in enumerate(decoy_indices):
            stage_by_index[decoy_index] = decoy_offset % parasite_count
        stage_batches = [[] for _ in parasite_indices]
        for index, popup in enumerate(popups):
            stage_index = stage_by_index[index]
            popup["stage_index"] = stage_index
            stage_batches[stage_index].append(str(popup["id"]))
    rng.shuffle(popups)
    parasite_ids = [popup_ids_by_index[index] for index in parasite_indices]
    parasite_id = parasite_ids[0]
    if parasite_count == 1:
        # Preserve the original echo identities at the assigned baseline.
        infection_groups = {
            parasite_id: [
                f"echo-{hashlib.sha256(f'{seed}|echo|{index}'.encode()).hexdigest()[:9]}"
                for index in range(echo_count)
            ]
        }
    else:
        infection_groups = {
            parent_id: [
                f"echo-{hashlib.sha256(f'{seed}|echo|{parent_index}|{index}'.encode()).hexdigest()[:9]}"
                for index in range(echo_count)
            ]
            for parent_index, parent_id in enumerate(parasite_ids)
        }
    echo_ids = [echo_id for parent_id in parasite_ids for echo_id in infection_groups[parent_id]]
    condition_token = (
        f"|d{condition['difficulty']}"
        if condition and int(condition.get("difficulty") or 0) != 2
        else ""
    )
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|challenge{condition_token}".encode()).hexdigest()[:12]
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "End the infestation.",
        "asset_manifest": "shared_runtime/assets/provenance/reviewed_overhaul_v1.json",
        "generator": {"name": "parasite_containment_v2", "variant_count": 7 * 5040 * 2048},
        "popups": popups,
        "echo_ids": echo_ids,
        "containment": containment_stages[0],
    }
    truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "seed": seed,
        "challenge_id": challenge_id,
        "popup_ids": [item["id"] for item in popups],
        "parasite_id": parasite_id,
        "echo_ids": echo_ids,
        "containment": public["containment"],
    }
    if maximum_resistance_strikes != 3:
        public["maximum_resistance_strikes"] = maximum_resistance_strikes
        truth["maximum_resistance_strikes"] = maximum_resistance_strikes
    if parasite_count > 1:
        public["parasite_count"] = parasite_count
        public["parasite_ids"] = list(parasite_ids)
        public["infection_groups"] = copy.deepcopy(infection_groups)
        public["containment_stages"] = copy.deepcopy(containment_stages)
        public["stage_batches"] = copy.deepcopy(stage_batches)
        truth["parasite_ids"] = list(parasite_ids)
        truth["infection_groups"] = copy.deepcopy(infection_groups)
        truth["containment_stages"] = copy.deepcopy(containment_stages)
        truth["stage_batches"] = copy.deepcopy(stage_batches)
    if condition:
        public["control_condition"] = copy.deepcopy(condition)
        truth["control_condition"] = copy.deepcopy(condition)
    return public, truth
