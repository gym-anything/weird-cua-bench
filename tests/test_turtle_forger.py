from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "weird_captcha_gym" / "environments" / "turtle_forger_env"
GENERATOR_PATH = ROOT / "weird_captcha_gym" / "shared_scripts" / "incubator_generators" / "turtle_forger.py"
GRADER_PATH = ROOT / "weird_captcha_gym" / "shared_runtime" / "server" / "incubator_graders" / "turtle_forger.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("turtle_forger_generator_test", GENERATOR_PATH)
GRADER = _load("turtle_forger_grader_test", GRADER_PATH)


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/turtle_forger_seed_0001/task.json").read_text(encoding="utf-8"))
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
    }
    return task


def _solution(public: dict, truth: dict, interaction: str) -> dict:
    program = list(truth["canonical_program"])
    events = []
    source = "palette_click" if interaction == "simplified" else "card_drag"
    for index, key in enumerate(program):
        event = {
            "sequence": index + 1,
            "type": "add",
            "command_key": key,
            "at": index,
            "input_source": source,
        }
        if interaction == "full":
            event["gesture"] = {"travel_px": 96.0, "sample_count": 6}
        events.append(event)
    palette = {command["key"]: command for command in truth["command_palette"]}
    rendered = GRADER._execute(
        [palette[key] for key in program],
        truth["start"],
        int(truth["parameters"]["max_expanded_steps"]),
        int(truth["canvas"]["stroke_width"]),
    )
    similarity, _precision, _coverage = GRADER._score(rendered, truth["target_segments"])
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "edit_events": events,
        "final_program": program,
        "run_count": 1,
        "rendered_segments": rendered,
        "similarity": similarity,
        "scan_count": 1,
        "completed": True,
    }


def _world(public: dict) -> dict:
    return {
        "canvas": public["canvas"],
        "start": public["start"],
        "command_palette": public["command_palette"],
        "runtime_target_segments": public["runtime_target_segments"],
        "parameters": public["parameters"],
    }


def test_all_ten_control_conditions_generate_and_grade() -> None:
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(_task(level, interaction), f"turtle-d{level}")
            decision = GRADER.grade(_solution(public, truth, interaction), truth, public)
            assert decision["passed"] is True, (level, interaction, decision)
            worlds.append(_world(public))
        assert worlds[0] == worlds[1]


def test_hundred_seed_reachability_in_both_interaction_modes() -> None:
    for level in range(1, 6):
        for seed_index in range(100):
            for interaction in ("simplified", "full"):
                public, truth = GENERATOR.generate(_task(level, interaction), f"reach-{level}-{seed_index}")
                decision = GRADER.grade(_solution(public, truth, interaction), truth, public)
                assert decision["passed"] is True, (level, interaction, seed_index, decision)


def test_live_and_paused_generation_preserve_the_decision_problem() -> None:
    live, _ = GENERATOR.generate(_task(3, "full", "live"), "clock-equivalence")
    paused, _ = GENERATOR.generate(_task(3, "full", "paused"), "clock-equivalence")
    assert _world(live) == _world(paused)
    assert live["control_condition"]["real_time"] == "live"
    assert paused["control_condition"]["real_time"] == "paused"


def test_wrong_surface_stale_identity_and_weak_drag_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(3, "full"), "negative-contract")
    payload = _solution(public, truth, "full")
    payload["edit_events"][0]["input_source"] = "palette_click"
    assert GRADER.grade(payload, truth, public)["passed"] is False
    payload = _solution(public, truth, "full")
    payload["challenge_id"] = "stale"
    assert GRADER.grade(payload, truth, public)["passed"] is False
    payload = _solution(public, truth, "full")
    payload["edit_events"][0]["gesture"] = {"travel_px": 4, "sample_count": 1}
    assert GRADER.grade(payload, truth, public)["passed"] is False


def test_forged_proof_geometry_and_similarity_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(3, "simplified"), "forged-proof")
    payload = _solution(public, truth, "simplified")
    payload["rendered_segments"][0]["x2"] += 3
    assert GRADER.grade(payload, truth, public)["passed"] is False
    payload = _solution(public, truth, "simplified")
    payload["similarity"] = .5
    assert GRADER.grade(payload, truth, public)["passed"] is False


def test_baseline_and_source_contract_are_fixed() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    env = json.loads((ENV / "env.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/turtle_forger_seed_0001/task.json").read_text(encoding="utf-8"))
    split = json.loads((ROOT / "weird_captcha_gym/splits/turtle_forger_split.json").read_text(encoding="utf-8"))
    assert controls["baseline"] == {"difficulty": 3, "interaction": "full", "real_time": "live"}
    assert controls["difficulty"]["3"]["parameters"] == {
        "pattern_profile": "compound_seal", "loop_depth": 1, "colour_count": 2,
        "subpath_count": 2, "grid_mode": "major", "stroke_ms": 520,
        "gap_ms": 145, "program_capacity": 16, "palette_decoys": 4,
        "max_expanded_steps": 64,
    }
    assert env["runner_options"] == {"observation_window_ms": 900, "frames_per_observation": 6, "play_time_seconds": 180}
    assert task["metadata"]["source_anchors"] == ["TAE-241", "TAE-268"]
    assert task["metadata"]["status"] == "prototype_visual_candidate"
    assert len(split["variations_tasks"]) == 20


def test_profiles_change_dependencies_not_only_repetition() -> None:
    public1, truth1 = GENERATOR.generate(_task(1, "full"), "profile-audit")
    public5, truth5 = GENERATOR.generate(_task(5, "full"), "profile-audit")
    assert public1["parameters"]["loop_depth"] == 0
    assert public5["parameters"]["loop_depth"] == 2
    assert len({segment["colour"] for segment in truth1["target_segments"]}) == 1
    assert len({segment["colour"] for segment in truth5["target_segments"]}) == 3
    assert "pen-up" not in truth1["canonical_program"]
    assert truth5["canonical_program"].count("pen-up") == 2
    assert truth5["canonical_program"].count("repeat-3") >= 2


def test_live_scan_has_a_visible_repeat_strategy_without_changing_profiles() -> None:
    source = (
        ROOT
        / "weird_captcha_gym/shared_runtime/app/mechanics/turtle_forger.js"
    ).read_text(encoding="utf-8")
    assert "AUTO REPLAY OFF" in source
    assert "AUTO REPLAY · MASTER RESTARTED FROM STROKE 01" in source
    assert "model.scanCycle += 1" in source
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    assert controls["difficulty"]["3"]["parameters"] == {
        "pattern_profile": "compound_seal", "loop_depth": 1, "colour_count": 2,
        "subpath_count": 2, "grid_mode": "major", "stroke_ms": 520,
        "gap_ms": 145, "program_capacity": 16, "palette_decoys": 4,
        "max_expanded_steps": 64,
    }
