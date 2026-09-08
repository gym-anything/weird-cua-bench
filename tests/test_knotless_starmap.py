from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

from weird_captcha_gym.shared_scripts import setup_task


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "weird_captcha_gym" / "environments" / "knotless_starmap_env"
MECHANIC = "knotless_starmap"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load(
    "knotless_starmap_generator_test",
    ROOT / "weird_captcha_gym" / "shared_scripts" / "incubator_generators" / f"{MECHANIC}.py",
)
GRADER = _load(
    "knotless_starmap_grader_test",
    ROOT / "weird_captcha_gym" / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py",
)


def _base_task() -> dict:
    return json.loads((ENV / "tasks" / f"{MECHANIC}_seed_0001" / "task.json").read_text())


def _controlled_task(level: int, interaction: str) -> dict:
    controls = json.loads((ENV / "controls.json").read_text())
    task = copy.deepcopy(_base_task())
    task["natural_language"] = controls["difficulty"][str(level)]["natural_language_by_interaction"][interaction]
    task.setdefault("metadata", {})["control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": "live",
        "difficulty_parameters": controls["difficulty"][str(level)]["parameters"],
    }
    return task


def _without_identity(value: dict) -> dict:
    result = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        result.pop(key, None)
    return result


def _payload(public: dict, truth: dict, interaction: str) -> dict:
    events = []
    sequence = 1
    for vertex in truth["world"]["vertices"]:
        vertex_id = str(vertex["id"])
        before = [vertex["x"], vertex["y"]]
        after = truth["solution_positions"][vertex_id]
        if interaction == "simplified":
            events.append({
                "seq": sequence,
                "type": "select",
                "vertex_id": vertex_id,
                "input_source": "proxy_click",
            })
            sequence += 1
        move = {
            "seq": sequence,
            "type": "vertex_move",
            "vertex_id": vertex_id,
            "input_source": "direct_drag" if interaction == "full" else "proxy_click",
            "before": before,
            "after": after,
        }
        if interaction == "full":
            move["path"] = [before, after]
        events.append(move)
        sequence += 1
    return {
        "mechanic_id": MECHANIC,
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "control_condition": public.get("control_condition"),
        "events": events,
        "completed": True,
        "reported_crossings": 0,
    }


def test_profiles_are_seeded_and_full_simplified_share_the_same_world() -> None:
    for level in range(1, 6):
        full_public, full_truth = setup_task.generate_task_state(
            _controlled_task(level, "full"), f"starmap-profile-{level}"
        )
        simplified_public, simplified_truth = setup_task.generate_task_state(
            _controlled_task(level, "simplified"), f"starmap-profile-{level}"
        )
        assert simplified_public["challenge_id"] == full_public["challenge_id"]
        simplified_identity = _without_identity(simplified_public)
        full_identity = _without_identity(full_public)
        simplified_identity.pop("prompt")
        full_identity.pop("prompt")
        assert simplified_identity == full_identity
        simplified_truth_identity = _without_identity(simplified_truth)
        full_truth_identity = _without_identity(full_truth)
        simplified_truth_identity.pop("prompt")
        full_truth_identity.pop("prompt")
        assert simplified_truth_identity == full_truth_identity
        assert full_public["world"]["initial_crossings"] >= full_public["control_condition"]["difficulty_parameters"]["minimum_crossings"]
        assert full_truth["solution_positions"]
        again, again_truth = setup_task.generate_task_state(
            _controlled_task(level, "full"), f"starmap-profile-{level}"
        )
        assert again == full_public
        assert again_truth == full_truth


def test_grader_replays_both_surfaces_and_rejects_stale_or_collapsed_submissions() -> None:
    for level in range(1, 6):
        for interaction in ("full", "simplified"):
            public, truth = setup_task.generate_task_state(
                _controlled_task(level, interaction), f"starmap-grade-{level}"
            )
            payload = _payload(public, truth, interaction)
            accepted = GRADER.grade(payload, truth, public)
            assert accepted["passed"] is True, (level, interaction, accepted)

            stale = copy.deepcopy(payload)
            stale["challenge_id"] = "stale-starmap-challenge"
            assert GRADER.grade(stale, truth, public)["passed"] is False

            wrong_source = copy.deepcopy(payload)
            move = next(event for event in wrong_source["events"] if event["type"] == "vertex_move")
            move["input_source"] = "proxy_click" if interaction == "full" else "direct_drag"
            assert GRADER.grade(wrong_source, truth, public)["passed"] is False

            collapsed = copy.deepcopy(payload)
            moves = [event for event in collapsed["events"] if event["type"] == "vertex_move"]
            duplicate = truth["solution_positions"][truth["world"]["vertices"][0]["id"]]
            moves[-1]["after"] = list(duplicate)
            if interaction == "full":
                moves[-1]["path"][-1] = list(duplicate)
            assert GRADER.grade(collapsed, truth, public)["passed"] is False


def test_baseline_matches_the_uncontrolled_task_and_renderer_records_input_surface() -> None:
    controls = json.loads((ENV / "controls.json").read_text())
    original_public, original_truth = setup_task.generate_task_state(_base_task(), "starmap-baseline")
    controlled_public, controlled_truth = setup_task.generate_task_state(
        _controlled_task(3, "full"), "starmap-baseline"
    )
    assert _without_identity(original_public) == _without_identity(controlled_public)
    assert _without_identity(original_truth) == _without_identity(controlled_truth)
    assert controls["baseline"] == {"difficulty": 3, "interaction": "full", "real_time": "live"}
    renderer = (ROOT / "weird_captcha_gym" / "shared_runtime" / "app" / "mechanics" / f"{MECHANIC}.js").read_text()
    assert 'input_source: "direct_drag"' in renderer
    assert 'input_source: "proxy_click"' in renderer
    assert "crossingIndices" in renderer


def test_zero_crossings_do_not_hide_incident_overlap_or_crowded_vertices() -> None:
    # A triangle isolates incident overlap: it has no nonincident edge pairs.
    public, truth = setup_task.generate_task_state(_base_task(), "starmap-geometry-fixture")
    vertices = [
        {"id": "v0", "x": 200, "y": 200},
        {"id": "v1", "x": 400, "y": 200},
        {"id": "v2", "x": 300, "y": 350},
    ]
    for state in (public, truth):
        state["world"]["vertices"] = copy.deepcopy(vertices)
        state["world"]["edges"] = [["v0", "v1"], ["v1", "v2"], ["v2", "v0"]]
    truth["solution_positions"] = {v["id"]: [v["x"], v["y"]] for v in vertices}
    payload = _payload(public, truth, "full")
    assert GRADER.grade(payload, truth, public)["passed"]
    for destination, reason in [([300, 200], "overlapping edge segments"), ([210, 210], "collapsed vertices")]:
        invalid = copy.deepcopy(payload)
        invalid["events"][-1]["after"] = destination
        invalid["events"][-1]["path"][-1] = destination
        assert invalid["reported_crossings"] == 0
        decision = GRADER.grade(invalid, truth, public)
        assert decision["passed"] is False
        assert reason in decision["feedback"]
    # Acceptance is not keyed to the stored witness coordinates.
    alternative = copy.deepcopy(payload)
    for event in alternative["events"]:
        point = event["after"]
        event["after"] = [point[0] + 70, point[1] + 40]
        event["path"][-1] = event["after"]
    assert GRADER.grade(alternative, truth, public)["passed"]
