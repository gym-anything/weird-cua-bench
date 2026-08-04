from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENV_ROOT = BENCHMARK / "environments" / "impossible_panorama_env"
MECHANIC = "impossible_panorama"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = _load("impossible_panorama_control_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = _load(
    "impossible_panorama_control_materializer",
    BENCHMARK / "tools" / "materialize_controlled_tasks.py",
)
GRADER = _load(
    "impossible_panorama_control_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "impossible_panorama.py",
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _controls() -> dict:
    return _read(ENV_ROOT / "controls.json")


def _base_task() -> dict:
    return _read(ENV_ROOT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json")


def _task(level: int, interaction: str) -> dict:
    controls = _controls()
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
    for key in ("task_id", "challenge_id", "control_condition"):
        result.pop(key, None)
    return result


def test_materializer_writes_the_ten_panorama_variants(tmp_path: Path) -> None:
    written = MATERIALIZER.materialize_environment(ENV_ROOT, tmp_path)
    assert len(written) == 10
    assert {
        (task["metadata"]["control_condition"]["difficulty"], task["metadata"]["control_condition"]["interaction"])
        for task in (_read(path / "task.json") for path in written)
    } == {(level, interaction) for level in range(1, 6) for interaction in ("simplified", "full")}


def test_l4_preserves_the_original_panorama_exactly() -> None:
    seed = "impossible-panorama-baseline-preservation"
    original_public, original_truth = SETUP.generate_task_state(_base_task(), seed)
    baseline_public, baseline_truth = SETUP.generate_task_state(_task(4, "full"), seed)
    assert _without_control_identity(baseline_public) == _without_control_identity(original_public)
    assert _without_control_identity(baseline_truth) == _without_control_identity(original_truth)


def test_profiles_bind_world_complexity_and_interaction_pairs() -> None:
    controls = _controls()
    for level in range(1, 6):
        simplified_public, simplified_truth = SETUP.generate_task_state(_task(level, "simplified"), "panorama-pair")
        full_public, full_truth = SETUP.generate_task_state(_task(level, "full"), "panorama-pair")
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert simplified_public["challenge_id"] == full_public["challenge_id"]
        assert _without_control_identity(simplified_public) == _without_control_identity(full_public)
        assert _without_control_identity(simplified_truth) == _without_control_identity(full_truth)
        assert simplified_truth["control_condition"]["difficulty_parameters"] == parameters
        assert len(simplified_public["objects"]) == parameters["sector_columns"] * parameters["sector_rows"]
        assert len(simplified_public["landmarks"]) == parameters["landmark_count"]
        assert len(simplified_public["routes"]) == parameters["route_count"]
        if level != 4:
            solution = simplified_truth["solution"]
            zoom = float(solution["zoom"])
            world, viewport = simplified_public["world"], simplified_public["viewport"]
            half_width, half_height = viewport["width"] / (2 * zoom), viewport["height"] / (2 * zoom)
            target_base = solution["target_base"]
            assert half_width <= target_base["x"] <= world["width"] - half_width
            assert half_height <= target_base["y"] <= world["height"] - half_height


def test_grader_rejects_cross_mode_and_tampered_profile_transcripts() -> None:
    public, truth = SETUP.generate_task_state(_task(3, "simplified"), "panorama-source-binding")
    payload = {
        "mechanic_id": MECHANIC,
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "interaction": "full",
        "events": [{"seq": 1, "t_ms": 0, "type": "verify"}],
        "final_state": {},
    }
    assert GRADER.grade(payload, truth, public)["feedback"] == "panorama transcript belongs to the other interaction mode"

    payload["interaction"] = "simplified"
    payload["events"] = [{
        "seq": 1,
        "t_ms": 0,
        "type": "pan_start",
        "pointer": {"x": 0, "y": 0},
        "camera": truth["initial_camera"],
        "input_source": "canvas_drag",
    }]
    assert "wrong interaction input" in GRADER.grade(payload, truth, public)["feedback"]

    altered_truth, altered_public = copy.deepcopy(truth), copy.deepcopy(public)
    for state in (altered_truth, altered_public):
        state["control_condition"]["difficulty_parameters"]["reticle_radius"] += 1
    assert GRADER.grade(payload, altered_truth, altered_public)["feedback"] == "panorama difficulty condition differs from generated contract"
