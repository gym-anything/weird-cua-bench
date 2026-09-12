from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "weird_captcha_gym" / "environments" / "lasso_freight_env"
MECHANIC = "lasso_freight"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GEN = _load("lasso_freight_generator_test", ROOT / "weird_captcha_gym/shared_scripts/incubator_generators/lasso_freight.py")
GRADE = _load("lasso_freight_grader_test", ROOT / "weird_captcha_gym/shared_runtime/server/incubator_graders/lasso_freight.py")
CONTROLS = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
BASE = json.loads((ENV / "tasks/lasso_freight_seed_0001/task.json").read_text(encoding="utf-8"))


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    task = copy.deepcopy(BASE)
    condition = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(CONTROLS["difficulty"][str(level)]["parameters"]),
    }
    task["_control_condition"] = condition
    return task


def _solve_payload(public: dict, truth: dict, interaction: str) -> dict:
    yard, capacity, _ = GRADE._initial(truth)
    tug = yard["start"]
    cargo = [dict(item, position=list(item["position"])) for item in yard["cargo"]]
    rope = [tug]
    actions = []
    source = "keyboard" if interaction == "full" else "control_buttons"
    for sequence, issued in enumerate(truth["solution"], 1):
        before = GRADE._snapshot(tug, cargo, rope)
        if issued in GRADE.DELTAS:
            action_type = "move"
            tug, outcome = GRADE._replay_move(tug, cargo, rope, yard, issued, capacity)
        else:
            action_type = "lasso"
            cargo_id, outcome = GRADE._replay_lasso(cargo, rope)
            if cargo_id:
                outcome = f"snag:{cargo_id}"
        after = GRADE._snapshot(tug, cargo, rope)
        actions.append({
            "sequence": sequence,
            "t_ms": sequence,
            "type": action_type,
            "issued": issued,
            "input_source": source,
            "before": before,
            "outcome": outcome,
            "after": after,
        })
    return {
        "mechanic_id": MECHANIC,
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "actions": actions,
        "final_state": GRADE._snapshot(tug, cargo, rope),
        "completed": True,
    }


@pytest.mark.parametrize("level", range(1, 6))
@pytest.mark.parametrize("interaction", ["simplified", "full"])
@pytest.mark.parametrize("real_time", ["live", "paused"])
def test_control_matrix_replays_same_world(level: int, interaction: str, real_time: str) -> None:
    task = _task(level, interaction, real_time)
    public, truth = GEN.generate(task, "matrix-seed")
    peer_task = _task(level, "full" if interaction == "simplified" else "simplified", "paused" if real_time == "live" else "live")
    peer_public, peer_truth = GEN.generate(peer_task, "matrix-seed")
    assert public["board"] == peer_public["board"]
    assert truth["solution"] == peer_truth["solution"]
    assert public["control_condition"]["real_time"] == real_time
    decision = GRADE.grade(_solve_payload(public, truth, interaction), truth, public)
    assert decision["passed"] is True, decision


def test_wrong_interaction_source_is_rejected() -> None:
    task = _task(4, "full")
    public, truth = GEN.generate(task, "source-separation")
    payload = _solve_payload(public, truth, "simplified")
    decision = GRADE.grade(payload, truth, public)
    assert decision["passed"] is False
    assert "interaction" in decision["feedback"]


def test_invalid_lasso_without_a_closed_path_is_rejected() -> None:
    task = _task(3, "full")
    public, truth = GEN.generate(task, "invalid-lasso")
    yard, _capacity, _ = GRADE._initial(truth)
    before = GRADE._snapshot(yard["start"], [dict(item, position=list(item["position"])) for item in yard["cargo"]], [yard["start"]])
    after = before
    payload = {
        "mechanic_id": MECHANIC,
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "actions": [{"sequence": 1, "t_ms": 1, "type": "lasso", "issued": "LASSO", "input_source": "keyboard", "before": before, "outcome": "lasso_empty", "after": after}],
        "final_state": after,
        "completed": True,
    }
    decision = GRADE.grade(payload, truth, public)
    assert decision["passed"] is False


def test_uncontrolled_task_matches_approved_d4_baseline() -> None:
    public, truth = GEN.generate(BASE, "uncontrolled-baseline")
    d4 = CONTROLS["difficulty"]["4"]["parameters"]
    assert public["board"]["width"] == d4["board_width"]
    assert public["board"]["height"] == d4["board_height"]
    assert len(public["board"]["cargo"]) == d4["cargo_count"]
    assert public["rope_capacity"] == d4["rope_capacity"]
    assert len(truth["solution"]) >= d4["solution_length_min"]
    assert len(truth["solution"]) <= d4["solution_length_max"]


def test_controls_and_registry_contract() -> None:
    assert CONTROLS["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert set(CONTROLS["difficulty"]) == {"1", "2", "3", "4", "5"}
    assert CONTROLS["interaction"]["simplified"]["implemented"] is True
    assert CONTROLS["interaction"]["full"]["implemented"] is True
    manifest = json.loads((ROOT / "weird_captcha_gym/benchmark_manifest.json").read_text(encoding="utf-8"))
    assert "lasso_freight_env" in manifest["environments"]
    assert manifest["environment_count"] == len(manifest["environments"])
    timing = json.loads((ROOT / "weird_captcha_gym/real_time.json").read_text(encoding="utf-8"))["environments"][MECHANIC]
    assert timing == CONTROLS["real_time"] == {
        "play_time_seconds": 120,
        "observation_window_ms": 0,
        "frames_per_observation": 1,
    }
