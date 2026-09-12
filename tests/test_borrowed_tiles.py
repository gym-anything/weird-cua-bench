from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "borrowed_tiles_env"
TASK_PATH = ENVIRONMENT / "tasks" / "borrowed_tiles_seed_0001" / "task.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = load_module(
    "borrowed_tiles_test_generator",
    BENCHMARK / "shared_scripts" / "incubator_generators" / "borrowed_tiles.py",
)
GRADER = load_module(
    "borrowed_tiles_test_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "borrowed_tiles.py",
)
MATERIALIZER = load_module(
    "borrowed_tiles_test_materializer",
    BENCHMARK / "tools" / "materialize_controlled_tasks.py",
)


def base_task() -> dict:
    return json.loads(TASK_PATH.read_text(encoding="utf-8"))


def controlled(level: int, interaction: str) -> dict:
    controls = json.loads((ENVIRONMENT / "controls.json").read_text(encoding="utf-8"))
    profile = controls["difficulty"][str(level)]
    task_dir = f"borrowed_tiles_d{level}_{interaction}_seed_0001"
    task = MATERIALIZER.controlled_task(
        base_task(),
        mechanic_id="borrowed_tiles",
        level=level,
        interaction=interaction,
        profile=profile,
        task_dir_name=task_dir,
    )
    task["_control_condition"] = copy.deepcopy(task["metadata"]["control_condition"])
    return task


def solved_payload(public: dict, truth: dict, interaction: str) -> dict:
    layout = {item["id"]: list(item["tiles"]) for item in truth["initial_sets"]}
    rack = list(truth["initial_rack"])
    actions = []
    source = "tile_click_drop" if interaction == "simplified" else "tile_drag"
    for source_action in truth["solution_actions"]:
        action = copy.deepcopy(source_action)
        action["input_source"] = source
        tile_id = action["tile_id"]
        origin = action["from"]
        if origin["zone"] == "rack":
            rack.remove(tile_id)
        else:
            layout[origin["set_id"]].remove(tile_id)
        destination = action["to"]
        layout.setdefault(destination["set_id"], []).append(tile_id)
        actions.append(action)
    return {
        "mechanic_id": "borrowed_tiles",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "actions": actions,
        "table_sets": [{"id": set_id, "tiles": tiles} for set_id, tiles in layout.items()],
        "rack_tiles": rack,
        "completed": True,
    }


@pytest.mark.parametrize("level", range(1, 6))
@pytest.mark.parametrize("interaction", ("simplified", "full"))
def test_every_control_variant_has_deterministic_visible_solution(level: int, interaction: str) -> None:
    task = controlled(level, interaction)
    public_one, truth_one = GENERATOR.generate(task, f"pytest-borrowed:{level}")
    public_two, truth_two = GENERATOR.generate(task, f"pytest-borrowed:{level}")
    assert public_one == public_two
    assert truth_one == truth_two

    payload = solved_payload(public_one, truth_one, interaction)
    grade = GRADER.grade(payload, truth_one, public_one)
    assert grade["passed"] is True, grade
    assert len(truth_one["solution_actions"]) == truth_one["module_count"] * 2
    assert len(payload["rack_tiles"]) == 0
    assert truth_one["required_borrow_count"] == truth_one["module_count"]
    assert all(action["input_source"] == ("tile_click_drop" if interaction == "simplified" else "tile_drag") for action in payload["actions"])


@pytest.mark.parametrize("interaction", ("simplified", "full"))
def test_wrong_input_surface_and_stale_challenge_are_rejected(interaction: str) -> None:
    task = controlled(4, interaction)
    public, truth = GENERATOR.generate(task, "pytest-borrowed-binding")
    payload = solved_payload(public, truth, interaction)

    wrong = copy.deepcopy(payload)
    wrong["actions"][0]["input_source"] = "tile_drag" if interaction == "simplified" else "tile_click_drop"
    assert GRADER.grade(wrong, truth, public)["passed"] is False

    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "stale-challenge"
    assert GRADER.grade(stale, truth, public)["passed"] is False


def test_controls_materialize_exactly_ten_tasks(tmp_path: Path) -> None:
    written = MATERIALIZER.materialize_environment(ENVIRONMENT, tmp_path)
    assert len(written) == 10
    assert {path.name for path in written} == {
        f"borrowed_tiles_d{level}_{interaction}_seed_0001"
        for level in range(1, 6)
        for interaction in ("simplified", "full")
    }
