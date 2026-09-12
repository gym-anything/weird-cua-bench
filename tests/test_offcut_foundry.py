from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

from weird_captcha_gym.realtime import load_real_time_settings
from weird_captcha_gym.shared_scripts.setup_task import generate_task_state


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "offcut_foundry_env"
BASE_TASK = json.loads((ENVIRONMENT / "tasks" / "offcut_foundry_seed_0001" / "task.json").read_text())
CONTROLS = json.loads((ENVIRONMENT / "controls.json").read_text())


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("offcut_foundry_generator", BENCHMARK / "shared_scripts" / "incubator_generators" / "offcut_foundry.py")
GRADER = _load("offcut_foundry_grader", BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "offcut_foundry.py")
MATERIALIZER = _load("offcut_foundry_materializer", BENCHMARK / "tools" / "materialize_controlled_tasks.py")


def _task(level: int, interaction: str) -> dict:
    return MATERIALIZER.controlled_task(
        BASE_TASK,
        mechanic_id="offcut_foundry",
        level=level,
        interaction=interaction,
        profile=CONTROLS["difficulty"][str(level)],
        task_dir_name=f"offcut_foundry_d{level}_{interaction}_seed_0001",
    )


def _without_condition(value: dict) -> dict:
    result = copy.deepcopy(value)
    result.pop("control_condition", None)
    result.pop("interaction", None)
    result.pop("task_id", None)
    result.pop("prompt", None)
    return result


def _payload(truth: dict, interaction: str) -> dict:
    events: list[dict] = []

    def add(kind: str, source: str, **details: object) -> None:
        events.append({"sequence": len(events) + 1, "kind": kind, "input_source": source, **details})

    if interaction == "full":
        for piece in truth["pieces"]:
            piece_id = piece["id"]
            cells = list(truth["placements"][piece_id])
            add("cut", "direct_trace", piece_id=piece_id, cells=cells, trace=cells)
    else:
        for piece in truth["pieces"]:
            piece_id = piece["id"]
            cells = list(truth["placements"][piece_id])
            add("piece_select", "proxy_piece_select", piece_id=piece_id)
            for cell_id in cells:
                add("select_cell", "proxy_cell", cell_id=cell_id, selected=True)
            add("cut", "proxy_extract", piece_id=piece_id, cells=cells, trace=cells)
    add("certify", "certify_button")
    return {
        "mechanic_id": truth["mechanic_id"],
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "control_condition": copy.deepcopy(truth.get("control_condition")),
        "events": events,
    }


def test_materializes_ten_conditions_and_registers_static_clock(tmp_path: Path) -> None:
    MATERIALIZER.validate_controls(CONTROLS, ENVIRONMENT)
    assert CONTROLS["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert CONTROLS["real_time"] == load_real_time_settings("offcut_foundry").__dict__
    written = MATERIALIZER.materialize_environment(ENVIRONMENT, tmp_path)
    conditions = {
        (json.loads((path / "task.json").read_text())["metadata"]["control_condition"]["difficulty"],
         json.loads((path / "task.json").read_text())["metadata"]["control_condition"]["interaction"])
        for path in written
    }
    assert conditions == {(level, mode) for level in range(1, 6) for mode in ("simplified", "full")}


def test_l4_full_is_the_uncontrolled_reference() -> None:
    original_public, original_truth = generate_task_state(BASE_TASK, "offcut-baseline")
    controlled_public, controlled_truth = generate_task_state(_task(4, "full"), "offcut-baseline")
    assert _without_condition(original_public) == _without_condition(controlled_public)
    assert _without_condition(original_truth) == _without_condition(controlled_truth)
    assert controlled_truth["parameters"] == CONTROLS["difficulty"]["4"]["parameters"]


def test_modes_share_world_and_replay_through_surface_specific_grader() -> None:
    for level in range(1, 6):
        simple_public, simple_truth = generate_task_state(_task(level, "simplified"), f"offcut-world-{level}")
        full_public, full_truth = generate_task_state(_task(level, "full"), f"offcut-world-{level}")
        assert simple_public["challenge_id"] == full_public["challenge_id"]
        assert _without_condition(simple_public) == _without_condition(full_public)
        assert _without_condition(simple_truth) == _without_condition(full_truth)
        assert GRADER.grade(_payload(simple_truth, "simplified"), simple_truth, simple_public)["passed"] is True
        assert GRADER.grade(_payload(full_truth, "full"), full_truth, full_public)["passed"] is True
        crossed = _payload(full_truth, "full")
        crossed["control_condition"] = copy.deepcopy(simple_truth["control_condition"])
        assert GRADER.grade(crossed, simple_truth, simple_public)["passed"] is False
        wrong_surface = _payload(simple_truth, "simplified")
        wrong_surface["events"][0]["input_source"] = "direct_trace"
        assert GRADER.grade(wrong_surface, simple_truth, simple_public)["passed"] is False


def test_adjacent_profiles_change_the_visible_decision_problem() -> None:
    worlds = {}
    for level in range(1, 6):
        public, truth = generate_task_state(_task(level, "full"), "offcut-profile-comparison")
        profile = CONTROLS["difficulty"][str(level)]["parameters"]
        worlds[level] = (public, truth)
        assert public["board"]["rows"] == profile["rows"]
        assert public["board"]["columns"] == profile["columns"]
        assert len(public["pieces"]) == profile["piece_count"]
        assert len(public["board"]["decoy_marks"]) == profile["decoy_count"]
        assert public["requirements"]["undo_budget"] == profile["undo_budget"]
    assert worlds[1][0]["board"]["rows"] < worlds[4][0]["board"]["rows"] < worlds[5][0]["board"]["rows"]
    assert len(worlds[1][0]["pieces"]) < len(worlds[3][0]["pieces"]) < len(worlds[5][0]["pieces"])
    assert worlds[1][0]["requirements"]["undo_budget"] > worlds[4][0]["requirements"]["undo_budget"]
    assert len(worlds[1][0]["board"]["decoy_marks"]) < len(worlds[5][0]["board"]["decoy_marks"])


def test_grader_requires_exact_final_partition_and_visible_certification() -> None:
    public, truth = generate_task_state(_task(4, "full"), "offcut-negative")
    passing = _payload(truth, "full")
    assert GRADER.grade(passing, truth, public)["passed"] is True
    missing_certification = copy.deepcopy(passing)
    missing_certification["events"].pop()
    assert GRADER.grade(missing_certification, truth, public)["passed"] is False
    wrong_task = copy.deepcopy(passing)
    wrong_task["challenge_id"] = "stale"
    assert GRADER.grade(wrong_task, truth, public)["passed"] is False
    wrong_surface = copy.deepcopy(passing)
    wrong_surface["events"][0]["input_source"] = "proxy_extract"
    assert GRADER.grade(wrong_surface, truth, public)["passed"] is False
    incomplete = copy.deepcopy(passing)
    incomplete["events"] = incomplete["events"][:-2]
    incomplete["events"][-1]["sequence"] = len(incomplete["events"])
    assert GRADER.grade(incomplete, truth, public)["passed"] is False
