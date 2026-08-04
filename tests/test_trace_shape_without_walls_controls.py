from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "trace_shape_without_walls_env"
MECHANIC = "trace_shape_without_walls"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = _load("trace_shape_control_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = _load(
    "trace_shape_control_materializer",
    BENCHMARK / "tools" / "materialize_controlled_tasks.py",
)
GRADER = _load(
    "trace_shape_control_grader",
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


def _without_identity(value: dict) -> dict:
    result = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        result.pop(key, None)
    return result


def test_l4_preserves_the_uncontrolled_generator_exactly() -> None:
    assert CONTROLS["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert BASE_TASK["natural_language"] == CONTROLS["difficulty"]["4"]["natural_language"]
    for seed in ("trace-shape-baseline-a", "trace-shape-baseline-b"):
        original_public, original_truth = SETUP.generate_task_state(BASE_TASK, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(_task(4, "full"), seed)
        assert _without_identity(baseline_public) == _without_identity(original_public)
        assert _without_identity(baseline_truth) == _without_identity(original_truth)


def test_profiles_change_the_running_problem_and_interaction_pairs_share_worlds() -> None:
    for level in range(1, 6):
        parameters = CONTROLS["difficulty"][str(level)]["parameters"]
        simplified_public, simplified_truth = SETUP.generate_task_state(
            _task(level, "simplified"), f"trace-shape-profile-{level}"
        )
        full_public, full_truth = SETUP.generate_task_state(
            _task(level, "full"), f"trace-shape-profile-{level}"
        )
        assert simplified_public["control_condition"]["interaction"] == "simplified"
        assert full_public["control_condition"]["interaction"] == "full"
        assert _without_identity(simplified_public) == _without_identity(full_public)
        assert _without_identity(simplified_truth) == _without_identity(full_truth)
        assert parameters["branch_count_min"] <= len(simplified_public["branches"]) <= parameters["branch_count_max"]
        assert parameters["corridor_radius_min"] <= simplified_public["corridor_radius"] <= parameters["corridor_radius_max"]
        assert parameters["sonar_radius_min"] <= simplified_public["sonar_radius"] <= parameters["sonar_radius_max"]
        assert parameters["drift_amplitude_x_min"] <= simplified_public["drift"]["amplitude_x"] <= parameters["drift_amplitude_x_max"]
        assert parameters["drift_amplitude_y_min"] <= simplified_public["drift"]["amplitude_y"] <= parameters["drift_amplitude_y_max"]
        requirements = simplified_public["requirements"]
        assert requirements["min_probe_samples"] == parameters["min_probe_samples"]
        assert requirements["min_probe_cells"] == parameters["min_probe_cells"]
        assert requirements["min_trace_ms"] == parameters["min_trace_ms"]
        assert requirements["max_raw_step"] == parameters["max_raw_step"]
        assert len(simplified_public["checkpoint_indices"]) == parameters["checkpoint_count"]

    l1_public, _ = SETUP.generate_task_state(_task(1, "full"), "trace-shape-adjacent")
    l4_public, _ = SETUP.generate_task_state(_task(4, "full"), "trace-shape-adjacent")
    l5_public, _ = SETUP.generate_task_state(_task(5, "full"), "trace-shape-adjacent")
    assert l1_public["corridor_radius"] > l4_public["corridor_radius"] > l5_public["corridor_radius"]
    assert l1_public["sonar_radius"] > l4_public["sonar_radius"] > l5_public["sonar_radius"]
    assert l1_public["drift"]["amplitude_x"] < l4_public["drift"]["amplitude_x"] < l5_public["drift"]["amplitude_x"]
    assert len(l1_public["branches"]) < len(l4_public["branches"]) < len(l5_public["branches"])
    assert len(l1_public["main_path"]) < len(l5_public["main_path"])


def test_grader_rejects_the_other_interaction_surface_and_stale_identity() -> None:
    for interaction, wrong_source in (
        ("simplified", "pointer_sonar"),
        ("full", "coordinate_sonar"),
    ):
        public, truth = SETUP.generate_task_state(_task(4, interaction), f"trace-shape-input-{interaction}")
        payload = {
            "mechanic_id": MECHANIC,
            "challenge_id": truth["challenge_id"],
            "interaction_mode": interaction,
            "events": [{
                "sequence": 1,
                "kind": "sonar_probe",
                "point": truth["start"],
                "input_source": wrong_source,
            }],
        }
        assert "wrong interaction input" in GRADER.grade(payload, truth, public)["feedback"]
        wrong_mode = copy.deepcopy(payload)
        wrong_mode["interaction_mode"] = "full" if interaction == "simplified" else "simplified"
        assert GRADER.grade(wrong_mode, truth, public)["feedback"] == "wrong interaction mode"
        stale = copy.deepcopy(payload)
        stale["challenge_id"] = "stale-trace-shape-challenge"
        assert GRADER.grade(stale, truth, public)["feedback"] == "stale challenge"


def test_browser_exposes_one_selected_surface_and_records_its_sources() -> None:
    source = (
        BENCHMARK / "shared_runtime" / "app" / "mechanics" / f"{MECHANIC}.js"
    ).read_text(encoding="utf-8")
    assert 'data-interaction="${clean(interaction)}"' in source
    assert 'if (interaction === "full")' in source
    assert 'id="trace-proxy-sonar"' in source
    assert 'id="trace-proxy-start"' in source
    assert 'id="trace-proxy-sample"' in source
    assert 'id="trace-proxy-end"' in source
    assert '"coordinate_sonar"' in source
    assert '"pointer_sonar"' in source
    assert 'interaction_mode: model.interaction' in source


def test_real_time_control_matches_the_shared_observation_settings() -> None:
    settings = json.loads((BENCHMARK / "real_time.json").read_text(encoding="utf-8"))["environments"][MECHANIC]
    assert CONTROLS["real_time"] == settings == {
        "play_time_seconds": 150,
        "observation_window_ms": 500,
        "frames_per_observation": 5,
    }
