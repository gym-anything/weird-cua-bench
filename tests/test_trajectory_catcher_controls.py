from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "trajectory_catcher_env"


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MATERIALIZER = _module(
    "trajectory_catcher_materializer",
    BENCHMARK / "tools" / "materialize_controlled_tasks.py",
)
SETUP = _module(
    "trajectory_catcher_setup",
    BENCHMARK / "shared_scripts" / "setup_task.py",
)
GRADER = _module(
    "trajectory_catcher_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "trajectory_catcher.py",
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _base_task() -> dict:
    return _read(ENVIRONMENT / "tasks" / "trajectory_catcher_seed_0001" / "task.json")


def _controlled_task(level: int, interaction: str) -> dict:
    controls = _read(ENVIRONMENT / "controls.json")
    return MATERIALIZER.controlled_task(
        _base_task(),
        mechanic_id="trajectory_catcher",
        level=level,
        interaction=interaction,
        profile=controls["difficulty"][str(level)],
        task_dir_name=f"trajectory_catcher_d{level}_{interaction}_seed_0001",
    )


def _without_condition_and_identity(value: dict) -> dict:
    result = copy.deepcopy(value)
    result.pop("control_condition", None)
    result["task_id"] = "historical-task"
    result["challenge_id"] = "historical-challenge"
    return result


def test_controls_validate_and_l4_preserves_the_historical_fixed_seed() -> None:
    controls = _read(ENVIRONMENT / "controls.json")
    MATERIALIZER.validate_controls(controls, ENVIRONMENT)
    assert controls["baseline"] == {"difficulty": 4, "interaction": "simplified", "real_time": "live"}

    original_public, original_truth = SETUP.generate_task_state(_base_task(), "trajectory-baseline-proof")
    controlled_public, controlled_truth = SETUP.generate_task_state(
        _controlled_task(4, "simplified"), "trajectory-baseline-proof"
    )
    assert _without_condition_and_identity(controlled_public) == _without_condition_and_identity(original_public)
    assert _without_condition_and_identity(controlled_truth) == _without_condition_and_identity(original_truth)


def test_all_profiles_share_worlds_between_interfaces_and_change_the_flight_problem() -> None:
    expected_round_counts = {1: 1, 2: 2, 3: 2, 4: 3, 5: 4}
    fingerprints: dict[int, str] = {}
    for level, expected_rounds in expected_round_counts.items():
        simplified_public, simplified_truth = SETUP.generate_task_state(
            _controlled_task(level, "simplified"), "trajectory-profile-proof"
        )
        full_public, full_truth = SETUP.generate_task_state(
            _controlled_task(level, "full"), "trajectory-profile-proof"
        )
        assert simplified_public["round_count"] == expected_rounds
        assert _without_condition_and_identity(simplified_public) == _without_condition_and_identity(full_public)
        assert _without_condition_and_identity(simplified_truth) == _without_condition_and_identity(full_truth)
        fingerprints[level] = json.dumps(
            _without_condition_and_identity(simplified_public), sort_keys=True
        )
    assert len(set(fingerprints.values())) == 5


def test_grader_rejects_a_controlled_transcript_bound_to_the_other_input_surface() -> None:
    public_state, ground_truth = SETUP.generate_task_state(
        _controlled_task(4, "full"), "trajectory-mode-binding"
    )
    decision = GRADER.grade(
        {
            "mechanic_id": "trajectory_catcher",
            "task_id": ground_truth["task_id"],
            "challenge_id": ground_truth["challenge_id"],
            "interaction": "simplified",
            "events": [],
        },
        ground_truth,
        public_state,
    )
    assert decision["passed"] is False
    assert decision["feedback"] == "flight transcript belongs to the other interaction mode"
