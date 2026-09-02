from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "weird_captcha_gym" / "environments" / "nonogram_denouement_env"
GENERATOR_PATH = ROOT / "weird_captcha_gym" / "shared_scripts" / "incubator_generators" / "nonogram_denouement.py"
GRADER_PATH = ROOT / "weird_captcha_gym" / "shared_runtime" / "server" / "incubator_graders" / "nonogram_denouement.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("nonogram_denouement_generator_test", GENERATOR_PATH)
GRADER = _load("nonogram_denouement_grader_test", GRADER_PATH)


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/nonogram_denouement_seed_0001/task.json").read_text(encoding="utf-8"))
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
    }
    return task


def _payload(public: dict, truth: dict, interaction: str, *, answer: str | None = None) -> dict:
    solution = truth["solution"]
    size = len(solution)
    events = []

    def add(event: dict) -> None:
        events.append({"sequence": len(events) + 1, **event})

    if interaction == "full":
        for row_index, row in enumerate(solution):
            start = 0
            while start < size:
                ink = row[start] == 1
                end = start
                while end + 1 < size and (row[end + 1] == 1) == ink:
                    end += 1
                mode = "ink" if ink else "clear"
                after = 1 if ink else -1
                add({
                    "type": "mark",
                    "mode": mode,
                    "input_source": "direct_grid_stroke",
                    "pointer_button": "left" if ink else "right",
                    "cells": [
                        {"row": row_index, "col": col, "before": 0, "after": after}
                        for col in range(start, end + 1)
                    ],
                })
                start = end + 1
    else:
        for row_index, row in enumerate(solution):
            for col_index, ink in enumerate(row):
                add({
                    "type": "mark",
                    "mode": "ink" if ink else "clear",
                    "input_source": "proxy_mark_button",
                    "cells": [{"row": row_index, "col": col_index, "before": 0, "after": 1 if ink else -1}],
                })
    add({"type": "develop", "input_source": "develop_button"})
    direction = answer or truth["correct_direction"]
    answer_event = {
        "type": "answer",
        "direction": direction,
        "input_source": "direction_slug_drag" if interaction == "full" else "direction_proxy_button",
    }
    if interaction == "full":
        answer_event["gesture"] = {
            "start_direction": direction,
            "travel_px": 140.0,
            "sample_count": 7,
            "dropped_in_well": True,
        }
    add(answer_event)
    final_grid = [[1 if value else -1 for value in row] for row in solution]
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "final_grid": final_grid,
        "final_answer": direction,
        "completed": True,
    }


def test_all_ten_control_conditions_generate_the_same_world_and_grade() -> None:
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(_task(level, interaction), "same-visible-world")
            decision = GRADER.grade(_payload(public, truth, interaction), truth, public)
            assert decision["passed"] is True, (level, interaction, decision)
            worlds.append(public["puzzle"])
        assert worlds[0] == worlds[1]


def test_profiles_are_line_solvable_and_active_across_forty_seeds() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    for level in range(1, 6):
        parameters = controls["difficulty"][str(level)]["parameters"]
        seen_clues = set()
        seen_answers = set()
        for seed_index in range(40):
            public, truth = GENERATOR.generate(_task(level, "full"), f"profile-{level}-{seed_index}")
            profile = truth["logic_profile"]
            assert profile["solved"] is True
            assert parameters["logic_round_min"] <= profile["rounds"] <= parameters["logic_round_max"]
            assert public["puzzle"]["size"] == parameters["grid_size"]
            assert len(public["puzzle"]["route"]) == parameters["route_steps"]
            assert len(public["puzzle"]["markers"]) == parameters["marker_count"]
            assert len(public["puzzle"]["answer_options"]) == parameters["answer_direction_count"]
            assert public["puzzle"]["pulse_segment_ms"] == parameters["pulse_segment_ms"]
            seen_clues.add(json.dumps([public["puzzle"]["row_clues"], public["puzzle"]["col_clues"]]))
            seen_answers.add(truth["correct_direction"])
        assert len(seen_clues) >= 35
        assert len(seen_answers) >= 3


def test_live_and_paused_generation_have_identical_decision_state() -> None:
    live, _ = GENERATOR.generate(_task(3, "full", "live"), "time-equivalence")
    paused, _ = GENERATOR.generate(_task(3, "full", "paused"), "time-equivalence")
    assert live["puzzle"] == paused["puzzle"]
    assert live["parameters"] == paused["parameters"]
    assert live["control_condition"]["real_time"] == "live"
    assert paused["control_condition"]["real_time"] == "paused"


def test_wrong_answer_is_a_real_failure_and_retry_payload_can_pass() -> None:
    public, truth = GENERATOR.generate(_task(3, "full"), "wrong-answer")
    wrong = next(option for option in public["puzzle"]["answer_options"] if option != truth["correct_direction"])
    decision = GRADER.grade(_payload(public, truth, "full", answer=wrong), truth, public)
    assert decision["passed"] is False
    assert "direction" in decision["feedback"]
    assert GRADER.grade(_payload(public, truth, "full"), truth, public)["passed"] is True


def test_stale_identity_wrong_surface_and_forged_gestures_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(3, "full"), "negative-contract")
    payload = _payload(public, truth, "full")
    payload["challenge_id"] = "stale"
    assert GRADER.grade(payload, truth, public)["passed"] is False

    payload = _payload(public, truth, "full")
    payload["events"][0]["input_source"] = "proxy_mark_button"
    assert "input surface" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full")
    payload["events"][-1]["gesture"]["travel_px"] = 3
    assert "drag" in GRADER.grade(payload, truth, public)["feedback"]


def test_non_contiguous_strokes_and_forged_final_grid_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(2, "full"), "stroke-contract")
    payload = _payload(public, truth, "full")
    stroke = next(event for event in payload["events"] if event["type"] == "mark" and len(event["cells"]) >= 2)
    stroke["cells"][-1]["col"] = (stroke["cells"][-1]["col"] + 2) % public["puzzle"]["size"]
    assert "straight contiguous" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full")
    payload["final_grid"][0][0] *= -1
    assert "does not match transcript" in GRADER.grade(payload, truth, public)["feedback"]


def test_baseline_and_adjacent_profiles_change_deduction_and_observation() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    assert controls["baseline"] == {"difficulty": 3, "interaction": "full", "real_time": "live"}
    sizes = [controls["difficulty"][str(level)]["parameters"]["grid_size"] for level in range(1, 6)]
    minimum_rounds = [controls["difficulty"][str(level)]["parameters"]["logic_round_min"] for level in range(1, 6)]
    markers = [controls["difficulty"][str(level)]["parameters"]["marker_count"] for level in range(1, 6)]
    speeds = [controls["difficulty"][str(level)]["parameters"]["pulse_segment_ms"] for level in range(1, 6)]
    assert sizes == [5, 6, 8, 9, 10]
    assert minimum_rounds == [1, 2, 3, 4, 5]
    assert markers == [1, 1, 2, 3, 4]
    assert speeds == sorted(speeds, reverse=True)


def test_environment_contract_records_sources_temporal_window_and_twenty_variations() -> None:
    env = json.loads((ENV / "env.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/nonogram_denouement_seed_0001/task.json").read_text(encoding="utf-8"))
    split = json.loads((ROOT / "weird_captcha_gym/splits/nonogram_denouement_split.json").read_text(encoding="utf-8"))
    assert env["runner_options"] == {"observation_window_ms": 900, "frames_per_observation": 6, "play_time_seconds": 240}
    assert task["metadata"]["source_anchors"] == ["PLOG-022", "TRR-021"]
    assert task["metadata"]["status"] == "prototype_visual_candidate"
    assert task["difficulty"] == "medium"
    assert "Developer Tools" in task["natural_language"]
    assert len(split["variations_tasks"]) == 20


def test_visible_surface_obeys_the_no_tutorial_quality_gate() -> None:
    mechanic = (
        ROOT
        / "weird_captcha_gym/shared_runtime/app/mechanics/nonogram_denouement.js"
    ).read_text(encoding="utf-8")
    for forbidden_copy in (
        "NO TRAIL / READ THE CHANGE",
        "useful evidence is direction across frames",
        "The loop repeats",
        "direction selection does not expire",
        "LEFT STROKE / INK",
        "RIGHT STROKE / CLEAR",
        "SHIFT STROKE / RESET",
        "SELECT A CELL",
        "THEN USE THE MARK BANK",
        "Every row and column must reproduce its run index",
        "DECIDED CELLS",
        "READY TO DEVELOP",
        "CLUE MISMATCH",
        "RUN INDEX DISAGREES",
        "A clue-correct plate unlocks the second station",
        "Select one departure direction",
        "DROP DEPARTURE SLUG",
        "FRAME WINDOW",
        "FRESH PLATE LOADED",
    ):
        assert forbidden_copy not in mechanic
    for terse_control in ("INK", "CLEAR", "RESET", "DEVELOP", "CERTIFY"):
        assert terse_control in mechanic
    assert 'data-challenge-id="${esc(model.state.challenge_id)}"' in mechanic


def test_grid_grouping_uses_actual_row_and_column_coordinates() -> None:
    mechanic = (
        ROOT
        / "weird_captcha_gym/shared_runtime/app/mechanics/nonogram_denouement.js"
    ).read_text(encoding="utf-8")
    styles = (
        ROOT
        / "weird_captcha_gym/shared_runtime/app/mechanics/nonogram_denouement.css"
    ).read_text(encoding="utf-8")
    assert "nth-child(5n)" not in styles
    assert "(col + 1) % 5 === 0 && col + 1 < model.puzzle.size" in mechanic
    assert "(row + 1) % 5 === 0 && row + 1 < model.puzzle.size" in mechanic
    for class_name in ("is-major-col", "is-major-row"):
        assert class_name in mechanic
        assert f".nd-cell.{class_name}" in styles
        assert f".nd-proof-cell.{class_name}" in styles
