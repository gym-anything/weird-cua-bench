from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load(
    ROOT / "weird_captcha_gym" / "shared_scripts" / "incubator_generators" / "collision_chimes.py",
    "collision_chimes_test_generator",
)
GRADER = _load(
    ROOT / "weird_captcha_gym" / "shared_runtime" / "server" / "incubator_graders" / "collision_chimes.py",
    "collision_chimes_test_grader",
)


def _base_task() -> dict:
    return json.loads(
        (
            ROOT
            / "weird_captcha_gym"
            / "environments"
            / "collision_chimes_env"
            / "tasks"
            / "collision_chimes_seed_0001"
            / "task.json"
        ).read_text(encoding="utf-8")
    )


def _task(level: int, interaction: str) -> dict:
    controls = json.loads(
        (
            ROOT / "weird_captcha_gym" / "environments" / "collision_chimes_env" / "controls.json"
        ).read_text(encoding="utf-8")
    )
    task = _base_task()
    task["id"] = f"collision_chimes_d{level}_{interaction}_seed_0001@0.2"
    condition = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": "live",
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
    }
    task["metadata"] = {**task["metadata"], "control_condition": condition}
    task["_control_condition"] = condition
    return task


def _solution_payload(task: dict, public: dict, truth: dict) -> dict:
    cells = []
    edits = []
    source_add, source_cycle = (
        ("cell_drag", "cell_click")
        if task["_control_condition"]["interaction"] == "full"
        else ("add_button", "cycle_button")
    )
    sequence = 0
    for goal in truth["solution_cells"]:
        cell = {"id": goal["id"], "row": goal["row"], "col": goal["col"], "direction": 0}
        cells.append(cell)
        sequence += 1
        edits.append(
            {
                "sequence": sequence,
                "type": "add",
                "id": cell["id"],
                "row": cell["row"],
                "col": cell["col"],
                "direction": 0,
                "input_source": source_add,
            }
        )
        for _ in range(int(goal["direction"])):
            before = cell["direction"]
            cell["direction"] = (before + 1) % 4
            sequence += 1
            edits.append(
                {
                    "sequence": sequence,
                    "type": "cycle",
                    "id": cell["id"],
                    "row": cell["row"],
                    "col": cell["col"],
                    "before_direction": before,
                    "after_direction": cell["direction"],
                    "input_source": source_cycle,
                }
            )
    cells.sort(key=lambda item: item["id"])
    return {
        "mechanic_id": "collision_chimes",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "input_surface": task["_control_condition"]["interaction"],
        "edit_events": edits,
        "cells": cells,
        "wall_events": GENERATOR.simulate(cells, public["contract"]["grid_size"], public["contract"]["beats"]),
        "beats_run": public["contract"]["beats"],
        "run_completed": True,
        "completed": True,
    }


def test_all_profiles_are_deterministic_and_pair_worlds_match() -> None:
    for level in range(1, 6):
        full_public, full_truth = GENERATOR.generate(_task(level, "full"), "collision-chimes-fixed-seed")
        simple_public, simple_truth = GENERATOR.generate(_task(level, "simplified"), "collision-chimes-fixed-seed")
        assert full_public["challenge_id"] == simple_public["challenge_id"]
        assert full_public["contract"] == simple_public["contract"]
        assert full_truth["solution_cells"] == simple_truth["solution_cells"]
        assert full_public["contract"]["target_events"] == GENERATOR.simulate(
            full_truth["solution_cells"], full_public["contract"]["grid_size"], full_public["contract"]["beats"]
        )


def test_both_input_surfaces_replay_and_wrong_surface_is_rejected() -> None:
    for interaction in ("full", "simplified"):
        task = _task(4, interaction)
        public, truth = GENERATOR.generate(task, "collision-chimes-grader-seed")
        payload = _solution_payload(task, public, truth)
        result = GRADER.grade(payload, truth, public)
        assert result["graded"] is True and result["passed"] is True
        wrong = dict(payload, input_surface="simplified" if interaction == "full" else "full")
        assert GRADER.grade(wrong, truth, public)["passed"] is False


def test_failure_configuration_has_a_different_wall_ledger() -> None:
    task = _task(4, "full")
    public, truth = GENERATOR.generate(task, "collision-chimes-failure-seed")
    assert GENERATOR.simulate(
        truth["failure_cells"], public["contract"]["grid_size"], public["contract"]["beats"]
    ) != public["contract"]["target_events"]

