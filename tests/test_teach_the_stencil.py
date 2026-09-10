from __future__ import annotations

import copy
import importlib.util
import json
import shutil
from pathlib import Path

from weird_captcha_gym.shared_runtime import verifier_helpers
from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment, validate_controls


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENV = BENCHMARK / "environments" / "teach_the_stencil_env"
MECHANIC = "teach_the_stencil"
BASE_TASK_PATH = ENV / "tasks" / "teach_the_stencil_seed_0001" / "task.json"
GENERATOR_PATH = BENCHMARK / "shared_scripts" / "incubator_generators" / f"{MECHANIC}.py"
GRADER_PATH = BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py"
VERIFIER_PATH = BASE_TASK_PATH.parent / "verifier.py"
SOLVER_PATH = BENCHMARK / "tools" / "incubator_solvers" / f"{MECHANIC}.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = _load(BENCHMARK / "shared_scripts" / "setup_task.py", "teach_stencil_setup")
GENERATOR = _load(GENERATOR_PATH, "teach_stencil_generator")
GRADER = _load(GRADER_PATH, "teach_stencil_grader")
SOLVER = _load(SOLVER_PATH, "teach_stencil_solver")


def _controls() -> dict:
    return json.loads((ENV / "controls.json").read_text(encoding="utf-8"))


def _base_task() -> dict:
    return json.loads(BASE_TASK_PATH.read_text(encoding="utf-8"))


def _task(level: int, interaction: str, task_id: str | None = None) -> dict:
    task = copy.deepcopy(_base_task())
    task["id"] = task_id or f"{MECHANIC}_d{level}_{interaction}_test@0.2"
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": "live",
        "difficulty_parameters": copy.deepcopy(_controls()["difficulty"][str(level)]["parameters"]),
    }
    return task


def _representative_points(public: dict, truth: dict) -> dict[int, list[tuple[int, int]]]:
    width = int(truth["width"])
    by_class: dict[int, list[tuple[int, int]]] = {class_id: [] for class_id in range(len(truth["class_names"]))}
    for index, label in enumerate(truth["target_labels"]):
        by_class[int(label)].append((index % width, index // width))
    result: dict[int, list[tuple[int, int]]] = {}
    for class_id, points in by_class.items():
        mean = [sum(float(public["plate"]["pixels"][point[1] * width + point[0]][channel]) for point in points) / len(points) for channel in range(4)]
        def distance(point: tuple[int, int]) -> float:
            feature = public["plate"]["pixels"][point[1] * width + point[0]]
            return sum((float(feature[channel]) / 255.0 - float(mean[channel]) / 255.0) ** 2 for channel in range(3)) + 0.65 * (float(feature[3]) - float(mean[3])) ** 2
        result[class_id] = sorted(points, key=distance)
    return result


def _valid_payload(level: int = 2, interaction: str = "simplified") -> tuple[dict, dict, dict]:
    public, truth = SETUP.generate_task_state(_task(level, interaction), "teach-stencil-test-seed")
    by_class = _representative_points(public, truth)
    events: list[dict] = []
    samples: list[tuple[int, list[float]]] = []
    used: set[tuple[int, int]] = set()
    source = "proxy_stamp" if interaction == "simplified" else "brush_drag"

    def add(kind: str, **details: object) -> None:
        events.append({"seq": len(events) + 1, "type": kind, **details})

    def paint(class_id: int, point: tuple[int, int]) -> None:
        add("select_class", class_id=class_id, input_source="palette_button")
        add("paint", class_id=class_id, points=[{"x": point[0], "y": point[1]}], input_source=source)
        samples.append((class_id, public["plate"]["pixels"][point[1] * truth["width"] + point[0]]))
        used.add(point)

    required = int(truth["required_samples_per_class"])
    for class_id, points in by_class.items():
        for point in points[:required]:
            paint(class_id, point)
    add("live_update", input_source="live_update_button")
    current = SOLVER._predict(public, samples)
    for _ in range(max(int(truth["minimum_corrections"]), int(truth["minimum_updates"]) - 1, 0)):
        class_id, point, current = SOLVER._candidate_correction(public, samples, by_class, used, current)
        paint(class_id, point)
        add("live_update", input_source="live_update_button")
    add("certify", input_source="certify_button")
    payload = {
        "mechanic_id": MECHANIC,
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "control_condition": public["control_condition"],
        "input_surface": interaction,
        "events": events,
        "completed": True,
    }
    return payload, truth, public


def test_control_contract_has_five_active_profiles_and_both_surfaces() -> None:
    controls = _controls()
    validate_controls(controls, ENV)
    assert controls["baseline"] == {"difficulty": 2, "interaction": "simplified", "real_time": "live"}
    assert controls["interaction"]["simplified"]["implemented"] is True
    assert controls["interaction"]["full"]["implemented"] is True
    assert [controls["difficulty"][str(level)]["parameters"]["width"] for level in range(1, 6)] == [52, 72, 84, 96, 108]
    assert [controls["difficulty"][str(level)]["parameters"]["minimum_updates"] for level in range(1, 6)] == [1] * 5
    assert [controls["difficulty"][str(level)]["parameters"]["minimum_corrections"] for level in range(1, 6)] == [0] * 5
    assert not any(controls["difficulty"][str(level)]["parameters"].get("requires_consequential_corrections", False) for level in range(1, 6))


def test_original_seed_uses_the_declared_baseline_configuration() -> None:
    public, truth = SETUP.generate_task_state(_base_task(), "original-seed-baseline")
    condition = truth["control_condition"]
    assert condition["difficulty"] == 2
    assert condition["interaction"] == "simplified"
    assert condition["real_time"] == "live"
    assert public["plate"]["width"] == 72
    assert public["plate"]["height"] == 46
    assert public["classes"][-1]["key"] == "vein"


def test_original_configuration_is_preserved_at_its_moved_level() -> None:
    original_public, original_truth = SETUP.generate_task_state(_base_task(), "same-original-world")
    moved = _task(2, "simplified", task_id="moved-original")
    moved_public, moved_truth = SETUP.generate_task_state(moved, "same-original-world")
    for state in (original_public, moved_public, original_truth, moved_truth):
        state.pop("task_id", None)
        state.pop("control_condition", None)
    original_public.pop("challenge_id", None)
    moved_public.pop("challenge_id", None)
    original_truth.pop("challenge_id", None)
    moved_truth.pop("challenge_id", None)
    assert original_public == moved_public
    assert original_truth == moved_truth


def test_materializer_writes_all_ten_target_variants(tmp_path: Path) -> None:
    written = materialize_environment(ENV, tmp_path)
    assert len(written) == 10
    assert {path.name for path in written} == {
        f"{MECHANIC}_d{level}_{interaction}_seed_0001"
        for level in range(1, 6)
        for interaction in ("simplified", "full")
    }
    for task_dir in written:
        task = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
        assert task["metadata"]["control_condition"]["real_time"] == "live"
        assert (task_dir / "verifier.py").is_file()


def test_canonical_registry_split_lists_live_and_paused_variants() -> None:
    split = json.loads((BENCHMARK / "splits" / f"{MECHANIC}_split.json").read_text(encoding="utf-8"))
    assert split == json.loads((ENV / f"{MECHANIC}_split.json").read_text(encoding="utf-8"))
    assert split["env_folder"] == "weird_captcha_gym/environments/teach_the_stencil_env"
    assert split["train_tasks"] == ["teach_the_stencil_seed_0001"]
    assert len(split["variations_tasks"]) == 20
    assert all(name.endswith("_tpaused") or "_d" in name for name in split["variations_tasks"])


def test_interaction_pair_preserves_world_and_goal() -> None:
    simplified_public, simplified_truth = SETUP.generate_task_state(_task(3, "simplified"), "paired-world")
    full_public, full_truth = SETUP.generate_task_state(_task(3, "full"), "paired-world")
    for state in (simplified_public, simplified_truth, full_public, full_truth):
        state.pop("task_id", None)
        state.pop("control_condition", None)
    simplified_public.pop("challenge_id", None)
    full_public.pop("challenge_id", None)
    simplified_truth.pop("challenge_id", None)
    full_truth.pop("challenge_id", None)
    assert simplified_public == full_public
    assert simplified_truth == full_truth


def test_generator_changes_active_difficulty_parameters() -> None:
    fingerprints = []
    class_counts = []
    for level in range(1, 6):
        public, truth = SETUP.generate_task_state(_task(level, "simplified"), "difficulty-activity")
        fingerprints.append(public["plate"]["world_fingerprint"])
        class_counts.append(len(public["classes"]))
        assert public["plate"]["width"] == _controls()["difficulty"][str(level)]["parameters"]["width"]
        assert truth["threshold"] == _controls()["difficulty"][str(level)]["parameters"]["threshold"]
        assert len(truth["target_labels"]) == public["plate"]["width"] * public["plate"]["height"]
    assert len(set(fingerprints)) == 5
    assert class_counts == [3, 5, 6, 6, 6]


def test_independent_grader_replays_valid_training_and_rejects_shortcuts() -> None:
    payload, truth, public = _valid_payload()
    decision = GRADER.grade(payload, truth, public)
    assert decision["passed"] is True, decision

    shortcut = copy.deepcopy(payload)
    shortcut["target_labels"] = truth["target_labels"]
    assert GRADER.grade(shortcut, truth, public)["passed"] is False

    wrong_surface = copy.deepcopy(payload)
    for event in wrong_surface["events"]:
        if event["type"] == "paint":
            event["input_source"] = "brush_drag"
            break
    rejected = GRADER.grade(wrong_surface, truth, public)
    assert rejected["passed"] is False
    assert "wrong interaction" in rejected["feedback"]

    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "stale-teach-stencil"
    assert GRADER.grade(stale, truth, public)["feedback"] == "stale task or challenge"


def test_full_input_requires_travel() -> None:
    full_payload, full_truth, full_public = _valid_payload(level=3, interaction="full")
    full_decision = GRADER.grade(full_payload, full_truth, full_public)
    assert full_decision["passed"] is False
    assert "real drag" in full_decision["feedback"]
    assert len(GRADER._brush_points((20.4, 20.4), 5, 72, 46)) > len(GRADER._brush_points((20.4, 20.4), 1, 72, 46))
    assert GRADER._eraser_radius(5) > GRADER._eraser_radius(1)


def test_accurate_first_update_does_not_require_correction_history() -> None:
    for level in range(1, 6):
        payload, truth, public = _valid_payload(level=level)
        assert sum(event["type"] == "live_update" for event in payload["events"]) == 1
        # Old saved configurations must not reintroduce the history gate.
        truth.update(requires_consequential_corrections=True, minimum_updates=5, minimum_corrections=4)
        decision = GRADER.grade(payload, truth, public)
        assert decision["passed"], (level, decision)
        incorrect = copy.deepcopy(truth)
        incorrect["target_labels"] = [(label + 1) % len(public["classes"]) for label in truth["target_labels"]]
        rejected = GRADER.grade(payload, incorrect, public)
        assert not rejected["passed"]
        assert "mean class IoU" in rejected["feedback"]


def test_full_surface_rejects_a_short_two_point_drag() -> None:
    payload, truth, public = _valid_payload(level=2, interaction="full")
    event = next(event for event in payload["events"] if event["type"] == "paint")
    point = event["points"][0]
    event["points"].append({"x": point["x"] + 1, "y": point["y"]})
    decision = GRADER.grade(payload, truth, public)
    assert not decision["passed"]
    assert "real drag" in decision["feedback"]


def test_exported_verifier_uses_the_independent_grader(tmp_path: Path) -> None:
    payload, truth, public = _valid_payload()
    exported = {"result": payload, "ground_truth": truth, "public_state": public}
    export_path = tmp_path / "task_result.json"
    export_path.write_text(json.dumps(exported), encoding="utf-8")
    verifier = _load(VERIFIER_PATH, "teach_stencil_verifier")

    def copy_from_env(source: str, destination: str) -> None:
        assert source == "/tmp/task_result.json"
        shutil.copyfile(export_path, destination)

    decision = verifier.verify_task(env_info={"copy_from_env": copy_from_env})
    assert decision["passed"] is True, decision


def test_static_real_time_contract_is_shared() -> None:
    controls = _controls()
    settings = json.loads((BENCHMARK / "real_time.json").read_text(encoding="utf-8"))["environments"][MECHANIC]
    env = json.loads((ENV / "env.json").read_text(encoding="utf-8"))
    assert controls["real_time"] == settings == env["runner_options"]
    assert settings == {"play_time_seconds": 180, "observation_window_ms": 0, "frames_per_observation": 1}
