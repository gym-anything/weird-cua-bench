from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "surveyors_toybox_env"
MECHANIC = "surveyors_toybox"
VIEWS = ("overhead", "front", "side")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = _load("surveyors_toybox_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = _load("surveyors_toybox_materializer", BENCHMARK / "tools" / "materialize_controlled_tasks.py")
GRADER = _load(
    "surveyors_toybox_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py",
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _base_task() -> dict:
    return _read(ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json")


def _controls() -> dict:
    return _read(ENVIRONMENT / "controls.json")


def _task(level: int, interaction: str) -> dict:
    return MATERIALIZER.controlled_task(
        _base_task(),
        mechanic_id=MECHANIC,
        level=level,
        interaction=interaction,
        profile=_controls()["difficulty"][str(level)],
        task_dir_name=f"{MECHANIC}_d{level}_{interaction}_seed_0001",
    )


def _without_identity(value: dict) -> dict:
    result = copy.deepcopy(value)
    for field in ("task_id", "challenge_id", "control_condition"):
        result.pop(field, None)
    return result


def _canonical(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _passing_payload(public: dict, truth: dict, interaction: str) -> dict:
    annotations = copy.deepcopy(truth["initial_annotations"])
    events: list[dict] = []

    def append(kind: str, **details) -> None:
        events.append({"sequence": len(events) + 1, "kind": kind, **details})

    def adjust(target_id: str, field: str, delta: float) -> None:
        box = annotations[target_id]
        if field == "cx": box["center"][0] += delta
        elif field == "cy": box["center"][1] += delta
        elif field == "cz": box["center"][2] += delta
        elif field == "hx": box["half"][0] = max(0.18, box["half"][0] + delta)
        elif field == "hy": box["half"][1] = max(0.18, box["half"][1] + delta)
        elif field == "hz": box["half"][2] = max(0.18, box["half"][2] + delta)
        else: box["yaw"] += delta

    for target_id in truth["target_ids"]:
        expected = truth["target_boxes"][target_id]
        if interaction == "full":
            values = (
                ("cx", float(expected["center"][0]) - annotations[target_id]["center"][0]),
                ("cy", float(expected["center"][1]) - annotations[target_id]["center"][1]),
                ("cz", float(expected["center"][2]) - annotations[target_id]["center"][2]),
                ("hx", float(expected["half"][0]) - annotations[target_id]["half"][0]),
                ("hy", float(expected["half"][1]) - annotations[target_id]["half"][1]),
                ("hz", float(expected["half"][2]) - annotations[target_id]["half"][2]),
                ("yaw", float(expected["yaw"]) - annotations[target_id]["yaw"]),
            )
            for field, delta in values:
                if abs(delta) > 1e-8:
                    append("adjust_box", target_id=target_id, field=field, delta=delta, input_source="direct_drag")
                    adjust(target_id, field, delta)
        else:
            for field, target in (
                ("cx", expected["center"][0]), ("cy", expected["center"][1]), ("cz", expected["center"][2]),
                ("hx", expected["half"][0]), ("hy", expected["half"][1]), ("hz", expected["half"][2]),
                ("yaw", expected["yaw"]),
            ):
                step = 5.0 if field == "yaw" else (0.05 if field.startswith("h") else 0.1)
                for _ in range(100):
                    current = annotations[target_id]["yaw"] if field == "yaw" else (
                        annotations[target_id]["half"][{"hx": 0, "hy": 1, "hz": 2}[field]]
                        if field.startswith("h") else annotations[target_id]["center"][{"cx": 0, "cy": 1, "cz": 2}[field]]
                    )
                    if abs(float(target) - current) <= (2.0 if field == "yaw" else 0.03):
                        break
                    delta = step if float(target) > current else -step
                    append("adjust_box", target_id=target_id, field=field, delta=delta, input_source="proxy_controls")
                    adjust(target_id, field, delta)

    for frame in range(int(truth["requirements"]["frame_count"])):
        append("frame_select", frame=frame)
        for target_id in truth["target_ids"]:
            for view in VIEWS:
                append(
                    "link",
                    target_id=target_id,
                    frame=frame,
                    view=view,
                    mark_id=truth["expected_links"][f"{frame}:{view}:{target_id}"],
                    input_source="direct_mark" if interaction == "full" else "proxy_controls",
                )
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "annotations": annotations,
        "links": truth["expected_links"],
        "events": events,
    }


def test_controls_materialize_ten_deterministic_tasks_and_validate_contract(tmp_path: Path) -> None:
    controls = _controls()
    MATERIALIZER.validate_controls(controls, ENVIRONMENT)
    first = MATERIALIZER.materialize_environment(ENVIRONMENT, tmp_path / "first")
    second = MATERIALIZER.materialize_environment(ENVIRONMENT, tmp_path / "second")
    assert len(first) == len(second) == 10
    first_tasks = sorted((tmp_path / "first" / ENVIRONMENT.name / "tasks").glob("*/task.json"))
    second_tasks = sorted((tmp_path / "second" / ENVIRONMENT.name / "tasks").glob("*/task.json"))
    assert [path.read_bytes() for path in first_tasks] == [path.read_bytes() for path in second_tasks]


def test_l4_matches_uncontrolled_world_and_modes_share_the_same_world() -> None:
    for seed in ("surveyors-baseline-a", "surveyors-baseline-b"):
        original_public, original_truth = SETUP.generate_task_state(_base_task(), seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(_task(4, "full"), seed)
        assert _without_identity(original_public) == _without_identity(baseline_public)
        assert _without_identity(original_truth) == _without_identity(baseline_truth)
    for level in range(1, 6):
        simplified_public, simplified_truth = SETUP.generate_task_state(_task(level, "simplified"), f"surveyors-d{level}")
        full_public, full_truth = SETUP.generate_task_state(_task(level, "full"), f"surveyors-d{level}")
        assert _without_identity(simplified_public) == _without_identity(full_public)
        simplified_truth_world = _without_identity(simplified_truth)
        full_truth_world = _without_identity(full_truth)
        simplified_truth_world.pop("interaction_mode", None)
        full_truth_world.pop("interaction_mode", None)
        assert simplified_truth_world == full_truth_world
        assert simplified_public["control_condition"]["difficulty"] == level


def test_active_profiles_change_the_3d_decision_problem() -> None:
    expected = {
        1: (1, 1, 1, 32), 2: (2, 2, 1, 28), 3: (2, 3, 2, 24), 4: (3, 4, 2, 18), 5: (4, 6, 3, 12),
    }
    for level, (targets, distractors, frames, density) in expected.items():
        public, truth = SETUP.generate_task_state(_task(level, "full"), f"surveyors-profile-{level}")
        assert len(public["targets"]) == targets
        assert len(truth["objects"]) == targets + distractors
        assert len(public["point_cloud"]) == (targets + distractors) * density + max(5, (targets + distractors) * 2)
        assert len(public["camera_frames"]) == frames
        assert public["requirements"]["target_count"] == targets
        assert public["requirements"]["frame_count"] == frames
        expected_tolerance = _controls()["difficulty"][str(level)]["parameters"].get("fit_tolerance", 0.16)
        assert public["requirements"]["fit_tolerance"] == expected_tolerance
    l3, _ = SETUP.generate_task_state(_task(3, "full"), "surveyors-adjacent")
    l4, _ = SETUP.generate_task_state(_task(4, "full"), "surveyors-adjacent")
    l5, _ = SETUP.generate_task_state(_task(5, "full"), "surveyors-adjacent")
    assert l3["requirements"]["target_count"] < l4["requirements"]["target_count"] < l5["requirements"]["target_count"]
    assert l3["generator"]["name"] == l4["generator"]["name"] == l5["generator"]["name"]
    assert l3["requirements"]["required_links"] < l4["requirements"]["required_links"] < l5["requirements"]["required_links"]


def test_grader_replays_both_input_surfaces_and_rejects_skew() -> None:
    for level in range(1, 6):
        for interaction in ("simplified", "full"):
            public, truth = SETUP.generate_task_state(_task(level, interaction), f"surveyors-grade-{level}-{interaction}")
            payload = _passing_payload(public, truth, interaction)
            accepted = GRADER.grade(payload, truth, public)
            assert accepted["passed"] is True, (level, interaction, accepted)
            wrong_mode = copy.deepcopy(payload)
            wrong_mode["interaction_mode"] = "full" if interaction == "simplified" else "simplified"
            assert GRADER.grade(wrong_mode, truth, public)["passed"] is False
            wrong_source = copy.deepcopy(payload)
            event = next(item for item in wrong_source["events"] if item["kind"] == "adjust_box")
            event["input_source"] = "direct_drag" if interaction == "simplified" else "proxy_controls"
            rejected = GRADER.grade(wrong_source, truth, public)
            assert rejected["passed"] is False
            assert "wrong interaction input" in rejected["feedback"]


def test_public_camera_links_are_frame_scoped() -> None:
    public, truth = SETUP.generate_task_state(_task(4, "full"), "surveyors-frame-scope")
    payload = _passing_payload(public, truth, "full")
    wrong = copy.deepcopy(payload)
    link = next(event for event in wrong["events"] if event["kind"] == "link")
    link["mark_id"] = truth["expected_links"][f"1:{link['view']}:{link['target_id']}"]
    assert GRADER.grade(wrong, truth, public)["passed"] is False


def test_camera_plates_have_neutral_marks_and_visible_scene_subjects() -> None:
    public, _ = SETUP.generate_task_state(_task(4, "full"), "surveyors-camera-scene")
    target_colors = {target["color"] for target in public["targets"]}
    target_glyphs = {target["glyph"] for target in public["targets"]}
    for frame in public["camera_frames"]:
        for view in VIEWS:
            plate = frame["views"][view]
            assert plate["scene_objects"]
            assert all("id" not in subject for subject in plate["scene_objects"])
            assert all(mark["color"] not in target_colors for mark in plate["marks"])
            assert all(mark["glyph"] not in target_glyphs for mark in plate["marks"])


def test_grader_accepts_visible_pan_zoom_events_and_binds_their_surface() -> None:
    for interaction, source in (("simplified", "proxy_controls"), ("full", "direct_drag")):
        public, truth = SETUP.generate_task_state(_task(4, interaction), f"surveyors-view-{interaction}")
        payload = _passing_payload(public, truth, interaction)
        payload["events"] = [
            {"sequence": 1, "kind": "zoom", "delta": 0.1, "input_source": source},
            {"sequence": 2, "kind": "pan", "delta_x": 28, "delta_y": 0, "input_source": source},
        ] + [{**event, "sequence": event["sequence"] + 2} for event in payload["events"]]
        accepted = GRADER.grade(payload, truth, public)
        assert accepted["passed"] is True, accepted
        payload["events"][0]["input_source"] = "proxy_controls" if source == "direct_drag" else "direct_drag"
        assert GRADER.grade(payload, truth, public)["passed"] is False
