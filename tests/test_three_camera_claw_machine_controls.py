from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "three_camera_claw_machine_env"
MECHANIC = "three_camera_claw_machine"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = _load("three_camera_claw_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = _load(
    "three_camera_claw_materializer",
    BENCHMARK / "tools" / "materialize_controlled_tasks.py",
)
GRADER = _load(
    "three_camera_claw_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py",
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _base_task() -> dict:
    return _read(ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json")


def _task(level: int, interaction: str) -> dict:
    controls = _read(ENVIRONMENT / "controls.json")
    return MATERIALIZER.controlled_task(
        _base_task(),
        mechanic_id=MECHANIC,
        level=level,
        interaction=interaction,
        profile=controls["difficulty"][str(level)],
        task_dir_name=f"{MECHANIC}_d{level}_{interaction}_seed_0001",
    )


def _without_control_identity(value: dict) -> dict:
    result = copy.deepcopy(value)
    for field in ("task_id", "challenge_id", "control_condition"):
        result.pop(field, None)
    return result


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def test_three_camera_claw_controls_preserve_l4_and_bind_input_surfaces(tmp_path: Path) -> None:
    controls = _read(ENVIRONMENT / "controls.json")
    MATERIALIZER.validate_controls(controls, ENVIRONMENT)
    assert controls["baseline"] == {"difficulty": 4, "interaction": "simplified", "real_time": "live"}

    historical = _read(ENVIRONMENT / "historical_l4_baseline_fixture.json")
    assert historical["source_commit"] == "94805e33c4e8e52130b9b62712c54e54bcbedd88"
    assert historical["generator_path"] == (
        "weird_captcha_gym/shared_scripts/incubator_generators/three_camera_claw_machine.py"
    )
    assert historical["identity_fields_removed_for_controlled_comparison"] == [
        "task_id",
        "challenge_id",
        "control_condition",
    ]

    for record in historical["seeds"]:
        seed = record["seed"]
        original_public, original_truth = SETUP.generate_task_state(_base_task(), seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(_task(4, "simplified"), seed)
        assert original_public["challenge_id"] == record["historical_challenge_id"]
        assert _canonical_sha256(original_public) == record["historical_public_state_sha256"]
        assert _canonical_sha256(original_truth) == record["historical_ground_truth_sha256"]
        assert _canonical_sha256(_without_control_identity(original_public)) == record["normalized_public_state_sha256"]
        assert _canonical_sha256(_without_control_identity(original_truth)) == record["normalized_ground_truth_sha256"]
        assert _without_control_identity(original_public) == _without_control_identity(baseline_public)
        assert _without_control_identity(original_truth) == _without_control_identity(baseline_truth)
        assert _canonical_sha256(_without_control_identity(baseline_public)) == record["normalized_public_state_sha256"]
        assert _canonical_sha256(_without_control_identity(baseline_truth)) == record["normalized_ground_truth_sha256"]

    expected_obstacle_counts = {"open": 0, "crossbar": 1, "crossbar_post": 2, "dense": 4}
    for level in range(1, 6):
        simplified_public, simplified_truth = SETUP.generate_task_state(_task(level, "simplified"), f"three-camera-level-{level}")
        full_public, full_truth = SETUP.generate_task_state(_task(level, "full"), f"three-camera-level-{level}")
        assert _without_control_identity(simplified_public) == _without_control_identity(full_public)
        assert _without_control_identity(simplified_truth) == _without_control_identity(full_truth)
        assert simplified_public["control_condition"]["difficulty"] == level
        if level == 4:
            assert len(full_public["objects"]) == 3
            assert len(full_public["obstacles"]) == 3
            assert [full_public["cameras"][view]["delay"] for view in ("top", "front", "side")] == [0, 2, 4]
        else:
            parameters = controls["difficulty"][str(level)]["parameters"]
            assert len(full_public["objects"]) == int(parameters["distractor_count"]) + 1
            assert len(full_public["obstacles"]) == expected_obstacle_counts[parameters["obstacle_profile"]]
            assert [full_public["cameras"][view]["delay"] for view in ("top", "front", "side")] == parameters["camera_delay_ticks"]
            assert full_public["world"]["acceleration"] == parameters["acceleration"]
            assert full_public["world"]["damping"] == parameters["damping"]
            assert full_public["world"]["capture_distance"] == parameters["capture_distance"]

        expected_source = {"simplified": "control_buttons", "full": "keyboard"}
        for interaction, public, truth in (
            ("simplified", simplified_public, simplified_truth),
            ("full", full_public, full_truth),
        ):
            wrong_mode = {
                "mechanic_id": MECHANIC,
                "task_id": public["task_id"],
                "challenge_id": public["challenge_id"],
                "interaction_mode": "full" if interaction == "simplified" else "simplified",
                "events": [],
            }
            assert GRADER.grade(wrong_mode, truth, public)["passed"] is False
            wrong_source = {
                "mechanic_id": MECHANIC,
                "task_id": public["task_id"],
                "challenge_id": public["challenge_id"],
                "interaction_mode": interaction,
                "events": [{"sequence": 1, "kind": "control", "axis": "x", "direction": 1, "input_source": expected_source["full" if interaction == "simplified" else "simplified"]}],
            }
            rejected = GRADER.grade(wrong_source, truth, public)
            assert rejected["passed"] is False
            assert "wrong interaction input" in rejected["feedback"]

    first, second = tmp_path / "first", tmp_path / "second"
    MATERIALIZER.materialize_environment(ENVIRONMENT, first)
    MATERIALIZER.materialize_environment(ENVIRONMENT, second)
    first_tasks = sorted(first.glob(f"{ENVIRONMENT.name}/tasks/*/task.json"))
    second_tasks = sorted(second.glob(f"{ENVIRONMENT.name}/tasks/*/task.json"))
    assert len(first_tasks) == len(second_tasks) == 10
    assert [path.read_bytes() for path in first_tasks] == [path.read_bytes() for path in second_tasks]
