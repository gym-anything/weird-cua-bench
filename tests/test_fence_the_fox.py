from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "weird_captcha_gym" / "environments" / "fence_the_fox_env"
GENERATOR_PATH = ROOT / "weird_captcha_gym" / "shared_scripts" / "incubator_generators" / "fence_the_fox.py"
GRADER_PATH = ROOT / "weird_captcha_gym" / "shared_runtime" / "server" / "incubator_graders" / "fence_the_fox.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("fence_the_fox_generator_test", GENERATOR_PATH)
GRADER = _load("fence_the_fox_grader_test", GRADER_PATH)


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/fence_the_fox_seed_0001/task.json").read_text(encoding="utf-8"))
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
    }
    return task


def _solution(public: dict, truth: dict, interaction: str) -> dict:
    events = []
    for turn_index, item in enumerate(truth["canonical_trace"]):
        event = copy.deepcopy(item)
        event["input_source"] = "cell_click" if interaction == "simplified" else "stake_driver"
        if interaction == "full":
            driver_path = []
            for angle_index in truth["driver_patterns"][turn_index]:
                angle = angle_index * math.pi / 6 - math.pi / 2
                driver_path.append([
                    round(math.cos(angle) * 0.68, 3),
                    round(math.sin(angle) * 0.68, 3),
                ])
            driver_path.append([0.0, 0.0])
            event["gesture"] = {
                "travel_px": 144.0,
                "sample_count": 8,
                "start": [120.0, 360.0],
                "end": [640.0, 360.0],
                "drop_cell": copy.deepcopy(item["placed"]),
                "driver_path": driver_path,
            }
        events.append(event)
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": events,
        "final_fox": copy.deepcopy(events[-1]["fox_from"]),
        "player_fences": [copy.deepcopy(event["placed"]) for event in events],
        "turns": len(events),
        "terminal_outcome": "trapped",
        "completed": True,
    }


def _world(public: dict) -> dict:
    return {
        "radius": public["radius"],
        "cells": public["cells"],
        "fox_start": public["fox_start"],
        "initial_fences": public["initial_fences"],
        "stake_budget": public["stake_budget"],
        "wind_start": public["wind_start"],
        "runtime_wind_sequence": public["runtime_wind_sequence"],
        "runtime_driver_patterns": public["runtime_driver_patterns"],
        "parameters": public["parameters"],
        "palette": public["palette"],
    }


def test_all_ten_control_conditions_share_world_and_grade() -> None:
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(_task(level, interaction), f"fox-matrix-{level}")
            decision = GRADER.grade(_solution(public, truth, interaction), truth, public)
            assert decision["passed"] is True, (level, interaction, decision)
            worlds.append(_world(public))
        assert worlds[0] == worlds[1]


def test_multiple_seeds_are_reachable_at_every_level() -> None:
    fingerprints = set()
    for level in range(1, 6):
        parameters = _task(level, "simplified")["_control_condition"]["difficulty_parameters"]
        for seed_index in range(3):
            public, truth = GENERATOR.generate(_task(level, "simplified"), f"fox-reach-{level}-{seed_index}")
            decision = GRADER.grade(_solution(public, truth, "simplified"), truth, public)
            assert decision["passed"] is True, (level, seed_index, decision)
            assert parameters["minimum_plan_turns"] <= truth["solver_plan_turns"] <= parameters["maximum_plan_turns"]
            if parameters["radius"] == 3:
                assert truth["shortest_plan_certified"] is True
                assert truth["shortest_plan_turns"] == truth["solver_plan_turns"]
                assert truth["shortest_plan_proof"] == "exhaustive_breadth_first_search"
            else:
                assert truth["shortest_plan_certified"] is False
                assert truth["shortest_plan_turns"] is None
                assert truth["shortest_plan_proof"] == "bounded_beam_discovery"
            fingerprints.add(json.dumps(_world(public), sort_keys=True))
    assert len(fingerprints) == 15


def test_live_and_paused_preserve_the_decision_problem() -> None:
    live, _ = GENERATOR.generate(_task(3, "full", "live"), "fox-clock-equivalence")
    paused, _ = GENERATOR.generate(_task(3, "full", "paused"), "fox-clock-equivalence")
    assert _world(live) == _world(paused)
    assert live["control_condition"]["real_time"] == "live"
    assert paused["control_condition"]["real_time"] == "paused"


def test_wrong_surface_stale_identity_and_forged_fox_reply_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(3, "full"), "fox-negative")
    payload = _solution(public, truth, "full")
    payload["events"][0]["input_source"] = "cell_click"
    assert GRADER.grade(payload, truth, public)["passed"] is False

    payload = _solution(public, truth, "full")
    payload["challenge_id"] = "stale-field"
    assert GRADER.grade(payload, truth, public)["passed"] is False

    payload = _solution(public, truth, "full")
    payload["events"][0]["fox_to"] = [0, 0]
    assert GRADER.grade(payload, truth, public)["passed"] is False

    payload = _solution(public, truth, "full")
    payload["events"][0]["gesture"]["travel_px"] = 2
    payload["events"][0]["gesture"]["sample_count"] = 1
    assert GRADER.grade(payload, truth, public)["passed"] is False

    payload = _solution(public, truth, "full")
    payload["events"][0]["gesture"]["driver_path"] = [[0.0, 0.0]]
    assert GRADER.grade(payload, truth, public)["passed"] is False

    payload = _solution(public, truth, "full")
    payload["events"][0]["wind_start"] = (payload["events"][0]["wind_start"] + 1) % 6
    assert GRADER.grade(payload, truth, public)["passed"] is False


def test_profiles_change_topology_and_planning_depth() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    for level in range(1, 6):
        public, truth = GENERATOR.generate(_task(level, "simplified"), f"fox-profile-{level}")
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert public["radius"] == parameters["radius"]
        assert len(public["initial_fences"]) == parameters["initial_fence_count"]
        assert parameters["minimum_plan_turns"] <= truth["solver_plan_turns"] <= parameters["maximum_plan_turns"]
        assert truth["solver_plan_turns"] <= public["stake_budget"]
    assert controls["difficulty"]["1"]["parameters"]["radius"] < controls["difficulty"]["5"]["parameters"]["radius"]
    assert controls["difficulty"]["1"]["parameters"]["maximum_plan_turns"] < controls["difficulty"]["5"]["parameters"]["minimum_plan_turns"]


def test_baseline_source_and_repository_contract() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    env = json.loads((ENV / "env.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/fence_the_fox_seed_0001/task.json").read_text(encoding="utf-8"))
    split = json.loads((ROOT / "weird_captcha_gym/splits/fence_the_fox_split.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "weird_captcha_gym/benchmark_manifest.json").read_text(encoding="utf-8"))
    real_time = json.loads((ROOT / "weird_captcha_gym/real_time.json").read_text(encoding="utf-8"))
    mechanic = (ROOT / "weird_captcha_gym/shared_runtime/app/mechanics/fence_the_fox.js").read_text(encoding="utf-8")
    assert controls["baseline"] == {"difficulty": 3, "interaction": "simplified", "real_time": "live"}
    assert env["runner_options"] == {"observation_window_ms": 480, "frames_per_observation": 1, "play_time_seconds": 180}
    assert task["name"] == "Fence the Fox"
    assert task["metadata"]["source_anchors"] == ["SOC-181"]
    assert task["metadata"]["status"] == "prototype_visual_candidate"
    assert len(split["variations_tasks"]) == 20
    assert "fence_the_fox_env" in manifest["environments"]
    assert manifest["environment_count"] == len(manifest["environments"])
    assert real_time["environments"]["fence_the_fox"] == controls["real_time"]
    assert 'beginAction?.("fence-the-fox-cell")' in mechanic
    assert 'beginAction?.("fence-the-fox-stake-driver")' in mechanic
    assert "settleAction(action)" in mechanic
    assert "settleAction(drag.action)" in mechanic
    assert not any(
        selector in mechanic
        for selector in (
            "fox-right-rail",
            "fox-policy-card",
            "fox-wind-card",
            "fox-rule-strip",
            "fox-legend",
        )
    )


def test_generated_prompt_is_complete_and_interaction_specific() -> None:
    for interaction, instruction in (
        ("simplified", "Click an open hex"),
        ("full", "Drag the reusable stake to an open hex"),
    ):
        public, _truth = GENERATOR.generate(_task(3, interaction), "fox-prompt-contract")
        prompt = public["prompt"]
        assert instruction in prompt
        assert "shortest open route" in prompt
        assert "ties follow the current wind order" in prompt.lower()
        assert "more shortest continuations" in prompt
        assert "more open neighbors" in prompt
        assert "wind order changes after every fox step" in prompt
        assert "Win by cutting every open route to the rim" in prompt
        assert all(direction in prompt for direction in ("E", "NE", "NW", "W", "SW", "SE"))


def test_baseline_requires_post_initial_observation_and_full_driver_path() -> None:
    for seed_index in range(4):
        public, truth = GENERATOR.generate(
            _task(3, "full"),
            f"fox-interaction-first-{seed_index}",
        )
        assert truth["post_initial_wind_influenced"] is True
        assert public["generator"]["post_initial_wind_influenced"] is True
        assert len(set(truth["wind_sequence"])) > 1
        assert truth["wind_sequence"] == public["runtime_wind_sequence"]
        assert truth["driver_patterns"] == public["runtime_driver_patterns"]
        assert all(len(pattern) == 2 for pattern in truth["driver_patterns"])
