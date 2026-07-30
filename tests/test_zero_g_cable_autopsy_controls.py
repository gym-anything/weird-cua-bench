from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "zero_g_cable_autopsy_env"
MECHANIC = "zero_g_cable_autopsy"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = load_module("zero_g_control_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = load_module(
    "zero_g_control_materializer",
    BENCHMARK / "tools" / "materialize_controlled_tasks.py",
)
GRADER = load_module(
    "zero_g_control_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py",
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


CONTROLS = read_json(ENVIRONMENT / "controls.json")
BASE_TASK = read_json(ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json")


def controlled_task(level: int, interaction: str) -> dict:
    return MATERIALIZER.controlled_task(
        BASE_TASK,
        mechanic_id=MECHANIC,
        level=level,
        interaction=interaction,
        profile=CONTROLS["difficulty"][str(level)],
        task_dir_name=f"{MECHANIC}_d{level}_{interaction}_seed_0001",
    )


def without_control_identity(value: dict) -> dict:
    result = copy.deepcopy(value)
    result.pop("task_id", None)
    result.pop("control_condition", None)
    return result


def test_controls_preserve_the_original_l4_simplified_world() -> None:
    MATERIALIZER.validate_controls(CONTROLS, ENVIRONMENT)
    assert CONTROLS["baseline"] == {"difficulty": 4, "interaction": "simplified", "real_time": "live"}
    for seed in ("zero-g-preservation-a", "zero-g-preservation-b", "zero-g-preservation-c"):
        original_public, original_truth = SETUP.generate_task_state(BASE_TASK, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(controlled_task(4, "simplified"), seed)
        assert without_control_identity(baseline_public) == without_control_identity(original_public)
        assert without_control_identity(baseline_truth) == without_control_identity(original_truth)


def test_profiles_materialize_ten_shared_world_conditions() -> None:
    for level in range(1, 6):
        simplified_public, simplified_truth = SETUP.generate_task_state(
            controlled_task(level, "simplified"), f"zero-g-profile-{level}"
        )
        full_public, full_truth = SETUP.generate_task_state(
            controlled_task(level, "full"), f"zero-g-profile-{level}"
        )
        assert without_control_identity(simplified_public) == without_control_identity(full_public)
        assert without_control_identity(simplified_truth) == without_control_identity(full_truth)
        parameters = CONTROLS["difficulty"][str(level)]["parameters"]
        assert len(simplified_public["nodes"]) == parameters["node_count"]
        assert len(simplified_public["contacts"]) == parameters["alarm_count"]
        assert simplified_public["controls"]["move_step"] == parameters["move_step"]
        assert simplified_truth["qualification"]["minimum_total_substeps"] == parameters["minimum_total_substeps"]
        assert simplified_truth["solution"]["attachments"] == {"A": 0, "B": parameters["node_count"] - 1}
        assert {ring["endpoint_index"] for ring in simplified_public["rings"]} == {0, parameters["node_count"] - 1}


def test_controlled_grader_rejects_a_transcript_labelled_for_the_other_surface() -> None:
    public_state, ground_truth = SETUP.generate_task_state(
        controlled_task(4, "simplified"), "zero-g-wrong-surface"
    )
    result = GRADER.grade(
        {
            "mechanic_id": MECHANIC,
            "task_id": ground_truth["task_id"],
            "challenge_id": ground_truth["challenge_id"],
            "interaction_mode": "full",
            "events": [],
        },
        ground_truth,
        public_state,
    )
    assert result["passed"] is False
    assert result["feedback"] == "cable transcript used the wrong interaction mode"


def test_static_observation_settings_match_the_shared_real_time_registry() -> None:
    assert CONTROLS["real_time"] == {
        "play_time_seconds": 180,
        "observation_window_ms": 0,
        "frames_per_observation": 1,
    }
    registry = read_json(BENCHMARK / "real_time.json")
    assert registry["environments"][MECHANIC] == CONTROLS["real_time"]
    source = (BENCHMARK / "shared_runtime" / "app" / "mechanics" / f"{MECHANIC}.js").read_text(encoding="utf-8")
    assert "time_mode" not in source
