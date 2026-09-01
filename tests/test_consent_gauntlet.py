from __future__ import annotations

import copy
import importlib.util
import json
import math
import os
from pathlib import Path

from weird_captcha_gym.dashboard.capability_annotations import build_capability_annotations
from weird_captcha_gym.dashboard.catalog import build_catalog


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "weird_captcha_gym/environments/consent_gauntlet_env"
GENERATOR_PATH = ROOT / "weird_captcha_gym/shared_scripts/incubator_generators/consent_gauntlet.py"
GRADER_PATH = ROOT / "weird_captcha_gym/shared_runtime/server/incubator_graders/consent_gauntlet.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("consent_generator_test", GENERATOR_PATH)
GRADER = _load("consent_grader_test", GRADER_PATH)


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/consent_gauntlet_seed_0001/task.json").read_text(encoding="utf-8"))
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
    }
    return task


def _solution(public: dict, truth: dict, interaction: str) -> dict:
    surface = copy.deepcopy(public["surface"])
    states = {item["id"]: item["initial_state"] for item in surface["purposes"]}
    purposes = {item["id"]: item for item in surface["purposes"]}
    drawers = {item["id"]: item for item in surface["drawers"]}
    current_drawer = surface["drawers"][0]["id"]
    events = []

    def add(event: dict) -> None:
        events.append({"sequence": len(events) + 1, "task_time_ms": (len(events) + 1) * 50.0, **event})

    def gateway_proof(option: dict, stage: str, stage_started_ms: float) -> dict:
        event_time = (len(events) + 1) * 50.0
        phase = float(surface["phase_deg"]) + (33 if stage == "final" else 0)
        if public["parameters"]["moving_gateways"]:
            phase += (
                (event_time - stage_started_ms)
                * public["parameters"]["orbit_speed_deg_per_second"]
                / 1000
            )
        radians = math.radians(phase + option["angle_offset_deg"])
        center_x = 0.5 + math.cos(radians) * 0.37
        center_y = 0.5 + math.sin(radians) * 0.31
        return {
            "pointer_offset_norm": 0.0,
            "phase_deg": phase,
            "pointer_x_norm": center_x,
            "pointer_y_norm": center_y,
            "card_center_x_norm": center_x,
            "card_center_y_norm": center_y,
            "card_width_norm": 0.14,
            "card_height_norm": 0.08,
        }

    correct_entry = next(item for item in surface["entry_options"] if item["action"] == "manage")
    add({"type": "gateway", "id": correct_entry["id"], "input_source": "orbit_card" if interaction == "full" else "option_proxy", **(gateway_proof(correct_entry, "entry", 0.0) if interaction == "full" else {})})

    source_ids = [item["source_id"] for item in surface["links"]]
    order = source_ids + [item["id"] for item in surface["purposes"] if item["id"] not in source_ids]
    for purpose_id in order:
        purpose = purposes[purpose_id]
        drawer_id = purpose["drawer_id"]
        if drawer_id != current_drawer:
            add({"type": "drawer", "id": drawer_id, "before": current_drawer, "after": drawer_id, "input_source": "drawer_tab" if interaction == "full" else "drawer_navigator"})
            current_drawer = drawer_id
        target = truth["targets"][purpose_id]
        if states[purpose_id] == target:
            continue
        before = states[purpose_id]
        states[purpose_id] = target
        effects = []
        for link in surface["links"]:
            if link["source_id"] != purpose_id:
                continue
            target_id = link["target_id"]
            target_before = states[target_id]
            states[target_id] = not target_before
            effects.append({"link_id": link["id"], "id": target_id, "before": target_before, "after": states[target_id]})
        event = {"type": "purpose", "id": purpose_id, "before": before, "after": target, "input_source": "switch_drag" if interaction == "full" else "switch_direction_button", "effects": effects}
        if interaction == "full":
            event["gesture"] = {"start_fraction": 0.82 if before else 0.18, "end_fraction": 0.82 if target else 0.18, "travel_px": 80, "sample_count": 5}
        add(event)

    for purpose in surface["purposes"]:
        purpose_id = purpose["id"]
        drawer_id = purpose["drawer_id"]
        if drawer_id != current_drawer:
            add({"type": "drawer", "id": drawer_id, "before": current_drawer, "after": drawer_id, "input_source": "drawer_tab" if interaction == "full" else "drawer_navigator"})
            current_drawer = drawer_id
        target = truth["targets"][purpose_id]
        if states[purpose_id] == target:
            continue
        before = states[purpose_id]
        states[purpose_id] = target
        event = {"type": "purpose", "id": purpose_id, "before": before, "after": target, "input_source": "switch_drag" if interaction == "full" else "switch_direction_button", "effects": []}
        if interaction == "full":
            event["gesture"] = {"start_fraction": 0.82 if before else 0.18, "end_fraction": 0.82 if target else 0.18, "travel_px": 80, "sample_count": 5}
        add(event)

    add({"type": "review", "id": "review", "input_source": "review_button"})
    final_stage_started_ms = events[-1]["task_time_ms"]
    correct_final = next(item for item in surface["final_options"] if item["action"] == "commit")
    add({"type": "gateway", "id": correct_final["id"], "input_source": "orbit_card" if interaction == "full" else "option_proxy", **(gateway_proof(correct_final, "final", final_stage_started_ms) if interaction == "full" else {})})
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "final_state": {"stage": "final", "current_drawer": current_drawer, "purpose_states": states},
        "elapsed_task_ms": events[-1]["task_time_ms"] + 25.0,
        "completed": True,
    }


def test_all_ten_control_conditions_generate_same_world_and_grade() -> None:
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(_task(level, interaction), "same-world")
            decision = GRADER.grade(_solution(public, truth, interaction), truth, public)
            assert decision["passed"] is True, (level, interaction, decision)
            worlds.append(public["surface"])
        assert worlds[0] == worlds[1]


def test_thirty_fresh_seeds_are_reachable_in_both_modes() -> None:
    for level in range(1, 6):
        for seed_index in range(30):
            for interaction in ("simplified", "full"):
                public, truth = GENERATOR.generate(_task(level, interaction), f"reach-{level}-{seed_index}")
                assert GRADER.grade(_solution(public, truth, interaction), truth, public)["passed"] is True


def test_live_and_paused_generation_preserve_the_decision_world() -> None:
    live, _ = GENERATOR.generate(_task(3, "full", "live"), "clock-pair")
    paused, _ = GENERATOR.generate(_task(3, "full", "paused"), "clock-pair")
    assert live["surface"] == paused["surface"]
    assert live["parameters"] == paused["parameters"]
    assert live["control_condition"]["real_time"] == "live"
    assert paused["control_condition"]["real_time"] == "paused"


def test_stale_wrong_surface_and_stationary_forgery_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "negative-contract")
    payload = _solution(public, truth, "full")
    payload["challenge_id"] = "stale"
    assert GRADER.grade(payload, truth, public)["passed"] is False
    payload = _solution(public, truth, "full")
    payload["events"][0]["input_source"] = "option_proxy"
    assert "gateway surface" in GRADER.grade(payload, truth, public)["feedback"]
    payload = _solution(public, truth, "full")
    switch = next(item for item in payload["events"] if item["type"] == "purpose")
    switch["gesture"]["travel_px"] = 0
    switch["gesture"]["sample_count"] = 1
    assert "gesture" in GRADER.grade(payload, truth, public)["feedback"]


def test_linked_effect_and_final_state_are_independently_replayed() -> None:
    public, truth = GENERATOR.generate(_task(5, "full"), "linked-contract")
    payload = _solution(public, truth, "full")
    linked = next(item for item in payload["events"] if item.get("effects"))
    linked["effects"][0]["after"] = not linked["effects"][0]["after"]
    assert "linked-switch" in GRADER.grade(payload, truth, public)["feedback"]
    payload = _solution(public, truth, "full")
    purpose_id = next(iter(payload["final_state"]["purpose_states"]))
    payload["final_state"]["purpose_states"][purpose_id] = not payload["final_state"]["purpose_states"][purpose_id]
    assert "does not match" in GRADER.grade(payload, truth, public)["feedback"]


def test_gateway_geometry_phase_and_event_time_are_independently_replayed() -> None:
    public, truth = GENERATOR.generate(_task(3, "full"), "gateway-contract")
    payload = _solution(public, truth, "full")
    gateway = next(item for item in payload["events"] if item["type"] == "gateway")
    gateway["card_center_x_norm"] += 0.04 if gateway["card_center_x_norm"] < 0.9 else -0.04
    assert "orbital geometry" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _solution(public, truth, "full")
    gateway = next(item for item in payload["events"] if item["type"] == "gateway")
    gateway["phase_deg"] += 20
    assert "task-time replay" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _solution(public, truth, "full")
    payload["events"][1]["task_time_ms"] = -1
    assert "task-time order" in GRADER.grade(payload, truth, public)["feedback"]


def test_baseline_metadata_and_public_information_boundary() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/consent_gauntlet_seed_0001/task.json").read_text(encoding="utf-8"))
    split = json.loads((ROOT / "weird_captcha_gym/splits/consent_gauntlet_split.json").read_text(encoding="utf-8"))
    assert controls["baseline"] == {"difficulty": 3, "interaction": "full", "real_time": "live"}
    assert controls["difficulty"]["3"]["parameters"] == {
        "purpose_count": 6, "negative_count": 2, "drawer_count": 2,
        "entry_option_count": 5, "final_option_count": 5,
        "reset_trap_count": 1, "link_count": 0,
        "moving_gateways": True, "orbit_speed_deg_per_second": 14,
    }
    public, _ = GENERATOR.generate(_task(3, "full"), "public-boundary")
    assert all("target" not in item for item in public["surface"]["purposes"])
    assert task["metadata"]["source_anchors"] == ["BUI-040"]
    assert task["metadata"]["status"] == "prototype_visual_candidate"
    assert len(split["variations_tasks"]) == 20


def test_adjacent_profiles_change_the_decision_or_control_problem() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))["difficulty"]
    assert [controls[str(level)]["parameters"]["negative_count"] for level in range(1, 6)] == [0, 1, 2, 3, 5]
    assert [controls[str(level)]["parameters"]["drawer_count"] for level in range(1, 6)] == [1, 1, 2, 3, 3]
    assert [controls[str(level)]["parameters"]["link_count"] for level in range(1, 6)] == [0, 0, 0, 1, 2]
    assert [controls[str(level)]["parameters"]["moving_gateways"] for level in range(1, 6)] == [False, False, True, True, True]


def test_environment_is_registered_end_to_end() -> None:
    benchmark = ROOT / "weird_captcha_gym"
    manifest = json.loads((benchmark / "benchmark_manifest.json").read_text(encoding="utf-8"))
    assert "consent_gauntlet_env" in manifest["environments"]
    assert manifest["environment_count"] == len(manifest["environments"])

    expected_clock = {
        "play_time_seconds": 180,
        "observation_window_ms": 720,
        "frames_per_observation": 5,
    }
    real_time = json.loads((benchmark / "real_time.json").read_text(encoding="utf-8"))
    env = json.loads((ENV / "env.json").read_text(encoding="utf-8"))
    assert real_time["environments"]["consent_gauntlet"] == expected_clock
    assert env["runner"] == "weird_captcha"
    assert env["runner_options"] == expected_clock

    for hook in (
        ENV / "scripts/install_puzzle_runtime.sh",
        ENV / "scripts/setup_puzzle_runtime.sh",
        ENV / "tasks/consent_gauntlet_seed_0001/setup_task.sh",
        ENV / "tasks/consent_gauntlet_seed_0001/export_result.sh",
    ):
        assert os.access(hook, os.X_OK), hook


