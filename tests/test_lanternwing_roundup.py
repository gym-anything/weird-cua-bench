from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENV = BENCHMARK / "environments" / "lanternwing_roundup_env"
MECHANIC = "lanternwing_roundup"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load(BENCHMARK / "shared_scripts/incubator_generators/lanternwing_roundup.py", "lanternwing_generator_test")
GRADER = _load(BENCHMARK / "shared_runtime/server/incubator_graders/lanternwing_roundup.py", "lanternwing_grader_test")
CONTROLS = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
BASE_TASK = json.loads((ENV / "tasks/lanternwing_roundup_seed_0001/task.json").read_text(encoding="utf-8"))


def _task(level: int, interaction: str) -> dict:
    task = copy.deepcopy(BASE_TASK)
    task["id"] = f"lanternwing_test_d{level}_{interaction}@0.2"
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": "live",
        "difficulty_parameters": copy.deepcopy(CONTROLS["difficulty"][str(level)]["parameters"]),
    }
    return task


def test_profiles_are_deterministic_and_modes_share_the_same_3d_world() -> None:
    for level in range(1, 6):
        simplified, simplified_truth = GENERATOR.generate(_task(level, "simplified"), "lanternwing-pair-seed")
        full, full_truth = GENERATOR.generate(_task(level, "full"), "lanternwing-pair-seed")
        assert simplified["challenge_id"] == full["challenge_id"]
        assert simplified["world"] == full["world"]
        assert simplified["physics"] == full["physics"]
        assert simplified["creatures"] == full["creatures"]
        assert simplified["wanted"] == full["wanted"]
        assert simplified_truth["target_ids"] == full_truth["target_ids"]
        assert GENERATOR.generate(_task(level, "full"), "lanternwing-pair-seed") == (full, full_truth)


def test_active_profiles_change_the_interception_problem() -> None:
    states = [GENERATOR.generate(_task(level, "full"), "lanternwing-profile-seed")[0] for level in range(1, 6)]
    assert [len(state["wanted"]) for state in states] == [1, 1, 2, 3, 4]
    assert [len(state["creatures"]) for state in states] == [1, 2, 3, 5, 7]
    assert [state["physics"]["capture_radius"] for state in states] == [.78, .68, .58, .5, .42]
    assert [len(state["world"]["obstacles"]) for state in states] == [0, 1, 2, 3, 5]
    assert states[0]["physics"]["gravity"] < states[-1]["physics"]["gravity"]


def test_grader_binds_task_identity_and_interaction_surface() -> None:
    public, truth = GENERATOR.generate(_task(4, "simplified"), "lanternwing-negative-seed")
    wrong_surface = {
        "mechanic_id": MECHANIC,
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "interaction": "full",
        "events": [],
    }
    assert GRADER.grade(wrong_surface, truth, public)["feedback"] == "no visible certification"

    stale = dict(wrong_surface, challenge_id="stale")
    assert GRADER.grade(stale, truth, public)["feedback"] == "stale task or challenge"


def test_source_and_runtime_keep_the_ballistic_contract_visible() -> None:
    browser = (BENCHMARK / "shared_runtime/app/mechanics/lanternwing_roundup.js").read_text(encoding="utf-8")
    grader = (BENCHMARK / "shared_runtime/server/incubator_graders/lanternwing_roundup.py").read_text(encoding="utf-8")
    assert "p.vy -= Number(model.state.physics.gravity) * dt" in browser
    assert "math.dist" in grader
    assert "canvas_throw" in browser and "throw_button" in browser
    assert "wrong interaction surface" in grader
