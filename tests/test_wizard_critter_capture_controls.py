from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "wizard_critter_capture_env"
MECHANIC = "wizard_critter_capture"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = _load("wizard_controls_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = _load("wizard_controls_materializer", BENCHMARK / "tools" / "materialize_controlled_tasks.py")
GRADER = _load(
    "wizard_controls_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py",
)
CONTROLS = json.loads((ENVIRONMENT / "controls.json").read_text(encoding="utf-8"))
BASE_TASK = json.loads(
    (ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json").read_text(encoding="utf-8")
)


def _task(level: int, interaction: str) -> dict:
    return MATERIALIZER.controlled_task(
        BASE_TASK,
        mechanic_id=MECHANIC,
        level=level,
        interaction=interaction,
        profile=CONTROLS["difficulty"][str(level)],
        task_dir_name=f"{MECHANIC}_d{level}_{interaction}_seed_0001",
    )


def _without_control_identity(state: dict) -> dict:
    result = copy.deepcopy(state)
    for key in ("task_id", "challenge_id", "control_condition"):
        result.pop(key, None)
    return result


def _without_surface_specific_copy(state: dict) -> dict:
    result = _without_control_identity(state)
    result.pop("prompt", None)
    result.pop("rules", None)
    return result


def test_wizard_profiles_preserve_l4_and_share_every_fixed_seed_world() -> None:
    MATERIALIZER.validate_controls(CONTROLS, ENVIRONMENT)
    assert CONTROLS["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert BASE_TASK["natural_language"] == CONTROLS["difficulty"]["4"]["natural_language"]

    for seed in ("wizard-baseline-a", "wizard-baseline-b"):
        original_public, original_truth = SETUP.generate_task_state(BASE_TASK, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(_task(4, "full"), seed)
        assert _without_control_identity(baseline_public) == _without_control_identity(original_public)
        assert _without_control_identity(baseline_truth) == _without_control_identity(original_truth)

    for level in range(1, 6):
        simplified_public, simplified_truth = SETUP.generate_task_state(_task(level, "simplified"), f"wizard-profile-{level}")
        full_public, full_truth = SETUP.generate_task_state(_task(level, "full"), f"wizard-profile-{level}")
        assert simplified_public["challenge_id"] == full_public["challenge_id"]
        assert _without_surface_specific_copy(simplified_public) == _without_surface_specific_copy(full_public)
        assert _without_control_identity(simplified_truth) == _without_control_identity(full_truth)
        assert "SPEND REQUIRED FREEZE" in simplified_public["prompt"]
        assert "HOLD F" not in simplified_public["prompt"].upper()
        assert "SPEND REQUIRED FREEZE" in simplified_public["rules"][2]
        assert "HOLD F" in full_public["rules"][2].upper()
        assert len(full_public["critters"]) == CONTROLS["difficulty"][str(level)]["parameters"]["critter_count"]

    l4_public, _ = SETUP.generate_task_state(_task(4, "full"), "wizard-l4-reference")
    l5_public, _ = SETUP.generate_task_state(_task(5, "full"), "wizard-l5-reference")
    assert l4_public["requirements"]["target_reference_visibility"] == "persistent"
    assert l5_public["requirements"]["target_reference_visibility"] == "preview_only"
    assert l5_public["requirements"]["minimum_freeze_ticks"] > l4_public["requirements"]["minimum_freeze_ticks"]
    assert l5_public["requirements"]["net_count"] < l4_public["requirements"]["net_count"]


def test_wizard_grader_rejects_a_transcript_bound_to_the_other_surface() -> None:
    public, truth = SETUP.generate_task_state(_task(4, "simplified"), "wizard-wrong-surface")
    wrong_mode_payload = {
        "mechanic_id": MECHANIC,
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction": "full",
        "events": [],
    }
    rejected = GRADER.grade(wrong_mode_payload, truth, public)
    assert rejected == {"graded": True, "passed": False, "score": 0, "feedback": "wrong interaction surface"}
