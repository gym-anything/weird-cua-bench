from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment, validate_controls


ROOT = Path(__file__).resolve().parents[1]
ENV_ROOT = ROOT / "weird_captcha_gym" / "environments" / "ribbon_consensus_env"
GENERATOR_PATH = ROOT / "weird_captcha_gym" / "shared_scripts" / "incubator_generators" / "ribbon_consensus.py"
GRADER_PATH = ROOT / "weird_captcha_gym" / "shared_runtime" / "server" / "incubator_graders" / "ribbon_consensus.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base_task() -> dict:
    return json.loads((ENV_ROOT / "tasks" / "ribbon_consensus_seed_0001" / "task.json").read_text())


def _condition(controls: dict, level: int, interaction: str = "simplified", real_time: str = "live") -> dict:
    return {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
    }


def _passing_payload(generator, grader, public: dict, truth: dict, interaction: str) -> dict:
    parameters = truth["parameters"]
    columns = copy.deepcopy(truth["initial_columns"])
    events = []
    for sequence, action in enumerate(truth["repair_actions"], start=1):
        start_column = columns[action["row_id"]][action["break_index"]]
        shifted = generator._valid_shift(columns[action["row_id"]], action["break_index"], action["delta"], truth["stage"]["column_count"])
        assert shifted is not None
        columns[action["row_id"]] = shifted
        score = grader.score_alignment(
            truth["rows"],
            columns,
            parameters["gap_open_penalty"],
            parameters["gap_extend_penalty"],
        )
        event = {
            "sequence": sequence,
            "kind": "shift",
            "row_id": action["row_id"],
            "break_index": action["break_index"],
            "delta": action["delta"],
            "input_source": "proxy_shift" if interaction == "simplified" else "tile_run_drag",
            "score_after": score,
            "breakdown_after": score,
        }
        if interaction == "full":
            cell = truth["stage"]["cell_width"]
            event["gesture"] = {
                "sample_count": 3,
                "travel_px": cell,
                "start_column": start_column,
                "end_column": start_column + action["delta"],
                "pointer_path": [
                    {"x": 108 + start_column * cell + cell / 2, "y": 26},
                    {"x": 108 + (start_column + action["delta"] * 0.5) * cell + cell / 2, "y": 26},
                    {"x": 108 + (start_column + action["delta"]) * cell + cell / 2, "y": 26},
                ],
            }
        events.append(event)
    final_score = grader.score_alignment(
        truth["rows"],
        columns,
        parameters["gap_open_penalty"],
        parameters["gap_extend_penalty"],
    )
    return {
        "mechanic_id": "ribbon_consensus",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "final_columns": columns,
        "final_score": final_score["score"],
        "score_breakdown": final_score,
        "move_count": len(events),
        "completed": True,
    }


def test_controls_materialize_both_surfaces_and_all_profiles(tmp_path):
    controls = json.loads((ENV_ROOT / "controls.json").read_text())
    validate_controls(controls, ENV_ROOT)
    output = tmp_path / "controlled"
    paths = materialize_environment(ENV_ROOT, output)
    assert len(paths) == 10
    assert {path.name.split("_")[2] for path in paths} == {"d1", "d2", "d3", "d4", "d5"}
    assert {path.name.split("_")[3] for path in paths} == {"full", "simplified"}
    for path in paths:
        task = json.loads((path / "task.json").read_text())
        condition = task["metadata"]["control_condition"]
        assert condition["interaction"] in {"simplified", "full"}
        assert condition["real_time"] == "live"
        assert "Solve only from screenshots and visible controls" in task["natural_language"]
        assert (path / "setup_task.sh").read_text().count(path.name) >= 1


def test_generator_changes_active_problem_by_level_and_hides_target():
    controls = json.loads((ENV_ROOT / "controls.json").read_text())
    generator = _load("ribbon_consensus_generator_test", GENERATOR_PATH)
    base = _base_task()
    profiles = []
    for level in range(1, 6):
        task = copy.deepcopy(base)
        task["_control_condition"] = _condition(controls, level)
        public, truth = generator.generate(task, "profile-seed-0001")
        profiles.append(public)
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert len(public["rows"]) == parameters["row_count"]
        assert all(len(row["tiles"]) == parameters["sequence_length"] for row in public["rows"])
        assert public["max_edits"] == parameters["max_edits"]
        assert public["parameters"] == parameters
        assert all("target_columns" not in row for row in public["rows"])
        assert "target_columns" not in public
        assert truth["target_columns"] != truth["initial_columns"]
    assert [len(item["rows"]) for item in profiles] == [3, 4, 4, 5, 6]
    assert [len(item["rows"][0]["tiles"]) for item in profiles] == [7, 9, 11, 13, 15]


def test_simplified_and_full_share_generated_world():
    controls = json.loads((ENV_ROOT / "controls.json").read_text())
    generator = _load("ribbon_consensus_generator_equivalence_test", GENERATOR_PATH)
    task = _base_task()
    task_simplified = {**task, "_control_condition": _condition(controls, 4, "simplified")}
    task_full = {**task, "_control_condition": _condition(controls, 4, "full")}
    public_s, truth_s = generator.generate(task_simplified, "same-world-seed")
    public_f, truth_f = generator.generate(task_full, "same-world-seed")
    for state in (public_s, public_f):
        state.pop("control_condition", None)
    public_f.pop("control_condition", None)
    truth_s.pop("control_condition", None)
    truth_f.pop("control_condition", None)
    assert public_s == public_f
    assert truth_s == truth_f


def test_grader_replays_both_input_surfaces_and_rejects_wrong_transcripts():
    controls = json.loads((ENV_ROOT / "controls.json").read_text())
    generator = _load("ribbon_consensus_generator_grader_test", GENERATOR_PATH)
    grader = _load("ribbon_consensus_grader_test", GRADER_PATH)
    for interaction in ("simplified", "full"):
        task = _base_task()
        task["_control_condition"] = _condition(controls, 4, interaction)
        public, truth = generator.generate(task, "grader-seed-0001")
        payload = _passing_payload(generator, grader, public, truth, interaction)
        assert grader.grade(payload, truth, public)["passed"] is True

        wrong_source = copy.deepcopy(payload)
        wrong_source["events"][0]["input_source"] = "tile_run_drag" if interaction == "simplified" else "proxy_shift"
        assert grader.grade(wrong_source, truth, public)["passed"] is False

        stale = copy.deepcopy(payload)
        stale["challenge_id"] = "stale-challenge"
        assert grader.grade(stale, truth, public)["passed"] is False


def test_full_gesture_binds_to_rendered_column_and_pointer_path():
    controls = json.loads((ENV_ROOT / "controls.json").read_text())
    generator = _load("ribbon_consensus_generator_gesture_test", GENERATOR_PATH)
    grader = _load("ribbon_consensus_grader_gesture_test", GRADER_PATH)
    task = _base_task()
    task["_control_condition"] = _condition(controls, 4, "full")
    public, truth = generator.generate(task, "gesture-seed-0001")
    payload = _passing_payload(generator, grader, public, truth, "full")
    first = payload["events"][0]
    action = truth["repair_actions"][0]
    rendered_column = truth["initial_columns"][action["row_id"]][action["break_index"]]
    assert first["gesture"]["start_column"] == rendered_column
    assert first["gesture"]["end_column"] == rendered_column + action["delta"]
    assert len(first["gesture"]["pointer_path"]) == first["gesture"]["sample_count"]

    tampered = copy.deepcopy(payload)
    tampered["events"][0]["gesture"]["start_column"] = rendered_column + 1
    assert grader.grade(tampered, truth, public)["passed"] is False


def test_real_time_and_runtime_contract_are_static():
    real_time = json.loads((ROOT / "weird_captcha_gym" / "real_time.json").read_text())
    assert real_time["environments"]["ribbon_consensus"] == {
        "play_time_seconds": 180,
        "observation_window_ms": 0,
        "frames_per_observation": 1,
    }
    env = json.loads((ENV_ROOT / "env.json").read_text())
    assert env["runner_options"] == {
        "observation_window_ms": 0,
        "frames_per_observation": 1,
        "play_time_seconds": 180,
    }
    mechanic = (ROOT / "weird_captcha_gym" / "shared_runtime" / "app" / "mechanics" / "ribbon_consensus.js").read_text()
    assert "proxy_shift" in mechanic and "tile_run_drag" in mechanic
    assert "requestAnimationFrame" not in mechanic


def test_frontend_theme_marker_matches_external_mechanic_css():
    mechanic = (ROOT / "weird_captcha_gym" / "shared_runtime" / "app" / "mechanics" / "ribbon_consensus.js").read_text()
    styles = (ROOT / "weird_captcha_gym" / "shared_runtime" / "app" / "mechanics" / "ribbon_consensus.css").read_text()
    assert 'document.body.dataset.mechanic = "ribbon-consensus"' in mechanic
    assert 'body[data-mechanic="ribbon-consensus"]' in styles


def test_malformed_numeric_submissions_fail_without_crashing(tmp_path):
    controls = json.loads((ENV_ROOT / "controls.json").read_text())
    generator = _load("ribbon_numeric_generator", GENERATOR_PATH)
    grader = _load("ribbon_numeric_grader", GRADER_PATH)
    verifier = _load("ribbon_numeric_verifier", ENV_ROOT / "tasks" / "ribbon_consensus_seed_0001" / "verifier.py")
    task = {**_base_task(), "_control_condition": _condition(controls, 4, "full")}
    public, truth = generator.generate(task, "numeric-rejection")
    payload = _passing_payload(generator, grader, public, truth, "full")
    for field in ("break_index", "delta", "sample_count", "start_column", "end_column", "travel_px", "pointer_x", "final_score", "move_count"):
        bad = copy.deepcopy(payload)
        if field in ("break_index", "delta"):
            bad["events"][0][field] = float("inf")
        elif field in ("final_score", "move_count"):
            bad[field] = float("inf")
        elif field == "pointer_x":
            bad["events"][0]["gesture"]["pointer_path"][0]["x"] = 10 ** 400
        else:
            bad["events"][0]["gesture"][field] = float("inf")
        assert grader.grade(bad, truth, public)["passed"] is False, field
        exported = json.dumps({"result": bad, "public_state": public, "ground_truth": truth})
        def copy_from_env(_source, destination):
            Path(destination).write_text(exported)
        assert verifier.verify_task(env_info={"copy_from_env": copy_from_env})["passed"] is False, field
