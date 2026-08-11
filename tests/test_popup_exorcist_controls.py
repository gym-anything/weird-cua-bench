from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import random
from pathlib import Path

from weird_captcha_gym.realtime import load_real_time_settings
from weird_captcha_gym.shared_scripts.setup_task import generate_task_state


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENV_ROOT = BENCHMARK / "environments" / "popup_exorcist_env"
BASE_TASK_PATH = ENV_ROOT / "tasks" / "popup_exorcist_seed_0001" / "task.json"
CONTROLS_PATH = ENV_ROOT / "controls.json"
MATERIALIZER_PATH = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
GRADER_PATH = BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "popup_exorcist.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MATERIALIZER = load_module("popup_control_materializer", MATERIALIZER_PATH)
GRADER = load_module("popup_control_grader", GRADER_PATH)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def controlled_task(level: int, interaction: str) -> dict:
    controls = read_json(CONTROLS_PATH)
    return MATERIALIZER.controlled_task(
        read_json(BASE_TASK_PATH),
        mechanic_id="popup_exorcist",
        level=level,
        interaction=interaction,
        profile=controls["difficulty"][str(level)],
        task_dir_name=f"popup_exorcist_d{level}_{interaction}_seed_0001",
    )


def without_identity(value: dict) -> dict:
    result = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        result.pop(key, None)
    return result


def stable_hash(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def legacy_generate(task: dict, seed: str) -> tuple[dict, dict]:
    rng = random.Random(
        int.from_bytes(
            hashlib.sha256(f"{seed}|popup_exorcist|v2".encode()).digest()[:8],
            "big",
        )
    )
    themes = ("update", "coupon", "cleaner", "forecast", "player", "survey", "prize")
    parasite_index = rng.randrange(1, 6)
    popups = []
    for index, theme in enumerate(themes):
        width, height = rng.randint(205, 270), rng.randint(126, 178)
        popup_id = (
            f"window-{hashlib.sha256(f'{seed}|window|{index}'.encode()).hexdigest()[:8]}"
        )
        popups.append(
            {
                "id": popup_id,
                "theme": theme,
                "title": rng.choice(
                    (
                        "SERVICE NOTICE",
                        "BACKGROUND TASK",
                        "DESKTOP MESSAGE",
                        "SYSTEM ASSISTANT",
                    )
                ),
                "x": rng.randint(18, 690 - width),
                "y": rng.randint(20, 365 - height),
                "w": width,
                "h": height,
                "z": index + 2,
                "runtime_behavior": "replicate" if index == parasite_index else "close",
            }
        )
    rng.shuffle(popups)
    parasite_id = next(
        item["id"] for item in popups if item["runtime_behavior"] == "replicate"
    )
    echo_ids = [
        f"echo-{hashlib.sha256(f'{seed}|echo|{index}'.encode()).hexdigest()[:9]}"
        for index in range(2)
    ]
    challenge_id = hashlib.sha256(
        f"{seed}|popup_exorcist|challenge".encode()
    ).hexdigest()[:12]
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": "popup_exorcist",
        "task_id": task["id"],
        "challenge_id": challenge_id,
        "prompt": "End the infestation.",
        "asset_manifest": "shared_runtime/assets/provenance/reviewed_overhaul_v1.json",
        "generator": {
            "name": "parasite_containment_v2",
            "variant_count": 7 * 5040 * 2048,
        },
        "popups": popups,
        "echo_ids": echo_ids,
        "containment": {"x": 530, "y": 292, "w": 160, "h": 88},
    }
    truth = {
        "mechanic_id": "popup_exorcist",
        "task_id": task["id"],
        "seed": seed,
        "challenge_id": challenge_id,
        "popup_ids": [item["id"] for item in popups],
        "parasite_id": parasite_id,
        "echo_ids": echo_ids,
        "containment": public["containment"],
    }
    return public, truth


def passing_payload(public: dict, truth: dict, interaction: str) -> dict:
    source = {
        "simplified": {
            "focus": "window_select",
            "close": "selected_close_button",
            "drag": "selected_contain_button",
        },
        "full": {
            "focus": "window_pointer",
            "close": "window_close_button",
            "drag": "window_drag",
        },
    }[interaction]
    parents = [str(item) for item in (truth.get("parasite_ids") or [truth["parasite_id"]])]
    groups = truth.get("infection_groups") or {parents[0]: truth["echo_ids"]}
    stages = truth.get("containment_stages") or [truth["containment"]]
    stage_batches = truth.get("stage_batches") or [truth["popup_ids"]]
    popup_by_id = {str(item["id"]): item for item in public["popups"]}
    live = set(str(item) for item in stage_batches[0])
    events = []
    last_echo = ""
    for stage_index, parasite in enumerate(parents):
        echo_ids = [str(item) for item in groups[parasite]]
        echo = echo_ids[-1]
        last_echo = echo
        parasite_spec = popup_by_id[parasite]
        well = stages[stage_index]
        echo_index = echo_ids.index(echo)
        horizontal = (
            74 + (echo_index // 2) * 22
            if echo_index % 2
            else -58 - (echo_index // 2) * 18
        )
        start = [
            max(
                8,
                min(
                    690 - int(parasite_spec["w"]),
                    int(parasite_spec["x"]) + horizontal,
                ),
            ),
            max(
                10,
                min(
                    365 - int(parasite_spec["h"]),
                    int(parasite_spec["y"]) + 54 + echo_index * 22,
                ),
            ),
        ]
        end = [
            round(well["x"] + well["w"] / 2 - parasite_spec["w"] / 2),
            round(well["y"] + well["h"] / 2 - parasite_spec["h"] / 2),
        ]
        samples = [
            [
                round(start[0] + (end[0] - start[0]) * index / 12),
                round(start[1] + (end[1] - start[1]) * index / 12),
            ]
            for index in range(13)
        ]
        events.extend(
            [
                {
                    "kind": "focus",
                    "window_id": parasite,
                    "input_source": source["focus"],
                },
                {
                    "kind": "close",
                    "window_id": parasite,
                    "input_source": source["close"],
                },
                {
                    "kind": "spawn",
                    "parent_id": parasite,
                    "echo_ids": echo_ids,
                    "input_source": "parasite_replication",
                },
                {
                    "kind": "focus",
                    "window_id": echo,
                    "input_source": source["focus"],
                },
                {
                    "kind": "drag",
                    "window_id": echo,
                    "samples": samples,
                    "input_source": source["drag"],
                },
                {
                    "kind": "contain",
                    "window_id": echo,
                    "input_source": source["drag"],
                },
            ]
        )
        live.update(echo_ids)
        if stage_index < len(parents) - 1:
            live.difference_update(
                {
                    *[str(item) for item in stage_batches[stage_index]],
                    *echo_ids,
                }
            )
            activated = [str(item) for item in stage_batches[stage_index + 1]]
            events.append(
                {
                    "kind": "stage",
                    "stage_index": stage_index + 1,
                    "activated_ids": activated,
                    "input_source": "containment_field",
                }
            )
            live.update(activated)
    events.append(
        {
            "kind": "purge",
            "contained_id": last_echo,
            "remaining_before": sorted(live),
            "input_source": "containment_field",
        }
    )
    return {
        "mechanic_id": "popup_exorcist",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "events": [{"sequence": index, **event} for index, event in enumerate(events, start=1)],
    }


def test_popup_controls_define_l2_full_baseline_and_canonical_static_observation() -> None:
    controls = read_json(CONTROLS_PATH)
    MATERIALIZER.validate_controls(controls, ENV_ROOT)
    assert controls["baseline"] == {
        "difficulty": 2,
        "interaction": "full",
        "real_time": "live",
    }
    assert read_json(BASE_TASK_PATH)["difficulty"] == "easy"
    assert controls["real_time"] == load_real_time_settings("popup_exorcist").__dict__
    assert controls["real_time"] == {
        "play_time_seconds": 120,
        "observation_window_ms": 0,
        "frames_per_observation": 1,
    }


def test_popup_baseline_preserves_the_existing_generated_world() -> None:
    seed = "popup-baseline-preservation"
    original_public, original_truth = legacy_generate(read_json(BASE_TASK_PATH), seed)
    baseline_public, baseline_truth = generate_task_state(controlled_task(2, "full"), seed)
    assert baseline_public["challenge_id"] == original_public["challenge_id"]
    assert baseline_truth["challenge_id"] == original_truth["challenge_id"]
    assert without_identity(baseline_public) == without_identity(original_public)
    assert without_identity(baseline_truth) == without_identity(original_truth)
    assert stable_hash(without_identity(baseline_public)) == stable_hash(
        without_identity(original_public)
    )
    assert stable_hash(without_identity(baseline_truth)) == stable_hash(
        without_identity(original_truth)
    )


def test_popup_difficulty_profiles_change_search_occlusion_and_dependent_containment() -> None:
    generated = [
        generate_task_state(controlled_task(level, "full"), "popup-profile-contract")
        for level in range(1, 6)
    ]
    public = [item[0] for item in generated]
    truth = [item[1] for item in generated]
    assert [len(item["popups"]) for item in public] == [3, 7, 9, 10, 11]
    assert [len(item["echo_ids"]) for item in public] == [3, 2, 1, 2, 3]
    assert [
        1 + len(item["echo_ids"]) // item.get("parasite_count", 1)
        for item in public
    ] == [4, 3, 2, 2, 2]
    assert [item.get("parasite_count", 1) for item in public] == [1, 1, 1, 2, 3]
    assert [len(item.get("containment_stages") or [item["containment"]]) for item in public] == [
        1,
        1,
        1,
        2,
        3,
    ]
    assert [
        [len(batch) for batch in item.get("stage_batches") or [item["popups"]]]
        for item in public
    ] == [[3], [7], [9], [5, 5], [4, 4, 3]]
    for state in public[3:]:
        parasite_ids = {
            item["id"]
            for item in state["popups"]
            if item["runtime_behavior"] == "replicate"
        }
        for batch in state["stage_batches"]:
            assert len(parasite_ids.intersection(batch)) == 1
    assert [item.get("maximum_resistance_strikes", 3) for item in public] == [5, 3, 3, 3, 2]
    assert [next(item for item in state["popups"] if item["runtime_behavior"] == "replicate").get("anomaly_cue", "none") for state in public] == [
        "explicit",
        "none",
        "none",
        "none",
        "none",
    ]
    assert len({item["challenge_id"] for item in truth}) == 5
    for state in public:
        wells = state.get("containment_stages") or [state["containment"]]
        for popup in state["popups"]:
            for well in wells:
                center_x_min, center_x_max = popup["w"] / 2, 700 - popup["w"] / 2
                center_y_min, center_y_max = popup["h"] / 2, 390 - popup["h"] / 2
                assert max(center_x_min, well["x"]) <= min(
                    center_x_max, well["x"] + well["w"]
                )
                assert max(center_y_min, well["y"]) <= min(
                    center_y_max, well["y"] + well["h"]
                )


def test_popup_interaction_pair_shares_world_and_grader_rejects_cross_mode_sources() -> None:
    for level in range(1, 6):
        simplified_public, simplified_truth = generate_task_state(
            controlled_task(level, "simplified"),
            "popup-interaction-pair",
        )
        full_public, full_truth = generate_task_state(
            controlled_task(level, "full"),
            "popup-interaction-pair",
        )
        assert without_identity(simplified_public) == without_identity(full_public)
        assert without_identity(simplified_truth) == without_identity(full_truth)
        assert simplified_truth["challenge_id"] == full_truth["challenge_id"]

    for level in range(1, 6):
        for interaction in ("simplified", "full"):
            public, truth = generate_task_state(
                controlled_task(level, interaction),
                f"popup-source-binding-{level}",
            )
            payload = passing_payload(public, truth, interaction)
            assert GRADER.grade(payload, truth, public)["passed"] is True

            forged = copy.deepcopy(payload)
            close = next(event for event in forged["events"] if event["kind"] == "close")
            close["input_source"] = (
                "window_close_button"
                if interaction == "simplified"
                else "selected_close_button"
            )
            rejected = GRADER.grade(forged, truth, public)
            assert rejected["passed"] is False
            assert "wrong interaction input" in rejected["feedback"]

            stale = copy.deepcopy(payload)
            stale["challenge_id"] = "stale-popup-challenge"
            assert GRADER.grade(stale, truth, public)["feedback"] == "stale challenge"


def test_popup_grader_enforces_resistance_limit_and_all_higher_level_strains() -> None:
    public, truth = generate_task_state(
        controlled_task(5, "full"),
        "popup-multistrain-negative",
    )
    payload = passing_payload(public, truth, "full")
    parents = truth["parasite_ids"]
    first_parent = parents[0]
    prefix = payload["events"][:3]
    for strike in range(1, int(truth["maximum_resistance_strikes"]) + 1):
        prefix.extend(
            [
                {
                    "sequence": 0,
                    "kind": "focus",
                    "window_id": first_parent,
                    "input_source": "window_pointer",
                },
                {
                    "sequence": 0,
                    "kind": "close",
                    "window_id": first_parent,
                    "input_source": "window_close_button",
                },
                {
                    "sequence": 0,
                    "kind": "resist",
                    "window_id": first_parent,
                    "strike": strike,
                    "input_source": "window_close_button",
                },
            ]
        )
    for index, event in enumerate(prefix, start=1):
        event["sequence"] = index
    exhausted = {**payload, "events": prefix}
    assert GRADER.grade(exhausted, truth, public)["feedback"] == (
        "maximum parasite resistance reached"
    )

    one_strain_only = copy.deepcopy(payload)
    first_contain = next(
        index
        for index, event in enumerate(one_strain_only["events"])
        if event["kind"] == "contain"
    )
    one_strain_only["events"] = one_strain_only["events"][: first_contain + 1]
    one_strain_only["events"].append(
        {
            "sequence": len(one_strain_only["events"]) + 1,
            "kind": "purge",
            "contained_id": one_strain_only["events"][-1]["window_id"],
            "remaining_before": [],
            "input_source": "containment_field",
        }
    )
    assert GRADER.grade(one_strain_only, truth, public)["feedback"] == (
        "next popup wave was not activated immediately"
    )

    future_parent = parents[1]
    premature_discovery = copy.deepcopy(payload)
    premature_discovery["events"] = copy.deepcopy(payload["events"][:5])
    premature_discovery["events"][0] = {
        "sequence": 1,
        "kind": "focus",
        "window_id": future_parent,
        "input_source": "window_pointer",
    }
    assert GRADER.grade(premature_discovery, truth, public)["feedback"] == (
        "focused window was not live"
    )


def test_popup_full_drag_requires_visible_origin_and_multiple_samples() -> None:
    public, truth = generate_task_state(
        controlled_task(5, "full"),
        "popup-drag-path-negative",
    )
    payload = passing_payload(public, truth, "full")
    drag_index = next(
        index
        for index, event in enumerate(payload["events"])
        if event["kind"] == "drag"
    )

    one_sample = copy.deepcopy(payload)
    one_sample["events"][drag_index]["samples"] = [
        one_sample["events"][drag_index]["samples"][-1]
    ]
    assert GRADER.grade(one_sample, truth, public)["feedback"] == (
        "full window drag requires an anchored multi-sample path"
    )

    unanchored = copy.deepcopy(payload)
    original_samples = unanchored["events"][drag_index]["samples"]
    unanchored["events"][drag_index]["samples"] = original_samples[1:]
    assert GRADER.grade(unanchored, truth, public)["feedback"] == (
        "full window drag was not anchored to the visible window"
    )


def test_popup_mechanic_has_no_task_level_live_or_paused_branch() -> None:
    source = (
        BENCHMARK / "shared_runtime" / "app" / "mechanics" / "popup_exorcist.js"
    ).read_text(encoding="utf-8")
    for forbidden in ("time_mode", "WEIRD_CAPTCHA_TIME_MODE", "WeirdCaptchaTime"):
        assert forbidden not in source


def test_popup_result_submission_is_not_gated_by_purge_animation_time() -> None:
    source = (
        BENCHMARK / "shared_runtime" / "app" / "mechanics" / "popup_exorcist.js"
    ).read_text(encoding="utf-8")
    submit_start = source.index("async function submit(containedId)")
    submit_end = source.index("\n  function tryContain", submit_start)
    submit_source = source[submit_start:submit_end]
    fetch_index = submit_source.index('fetch("/result"')
    assert "await new Promise" not in submit_source[:fetch_index]


def test_popup_profiles_remain_deterministic_reachable_and_interaction_invariant_across_seeds() -> None:
    challenge_ids: set[str] = set()
    for seed_index in range(40):
        seed = f"popup-scale-{seed_index:03d}"
        for level in range(1, 6):
            simplified_public, simplified_truth = generate_task_state(
                controlled_task(level, "simplified"),
                seed,
            )
            full_public, full_truth = generate_task_state(
                controlled_task(level, "full"),
                seed,
            )
            assert without_identity(simplified_public) == without_identity(full_public)
            assert without_identity(simplified_truth) == without_identity(full_truth)
            assert simplified_truth["challenge_id"] == full_truth["challenge_id"]
            challenge_ids.add(simplified_truth["challenge_id"])
            wells = simplified_public.get("containment_stages") or [
                simplified_public["containment"]
            ]
            for popup in simplified_public["popups"]:
                for well in wells:
                    center_x_min, center_x_max = popup["w"] / 2, 700 - popup["w"] / 2
                    center_y_min, center_y_max = popup["h"] / 2, 390 - popup["h"] / 2
                    assert max(center_x_min, well["x"]) <= min(
                        center_x_max, well["x"] + well["w"]
                    )
                    assert max(center_y_min, well["y"]) <= min(
                        center_y_max, well["y"] + well["h"]
                    )
    assert len(challenge_ids) == 200
