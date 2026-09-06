from __future__ import annotations

import copy
import math

import pytest

from weird_captcha_gym.shared_scripts.setup_task import generate_task_state
from weird_captcha_gym.shared_runtime.server.incubator_graders import board_game_captcha as grader
from weird_captcha_gym.tools.materialize_gyroscopic_variant import materialize, variant_task


def gravity_task(level=5, interaction="full"):
    return variant_task(level, interaction, "nearest_hole_gravity")


@pytest.mark.parametrize("level", range(1, 6))
def test_gravity_variant_preserves_world(level):
    task = gravity_task(level)
    full, truth = generate_task_state(task, "42")
    simple, _ = generate_task_state(gravity_task(level, "simplified"), "42")
    del task["metadata"]["control_condition"]["difficulty_parameters"]["hole_gravity"]
    baseline, _ = generate_task_state(task, "42")
    for key in ("stage", "start", "goal", "walls", "hazards", "switches", "requirements", "theme"):
        assert full[key] == simple[key] == baseline[key]
    assert full["physics"] == truth["physics"] == simple["physics"]
    assert full["physics"]["hole_gravity"] == 0.5
    assert "external_tilt" not in full["physics"]
    assert {k: v for k, v in full["physics"].items() if k != "hole_gravity"} == baseline["physics"]
    assert full["challenge_id"] != baseline["challenge_id"]


@pytest.mark.parametrize("value", [0, -1, 1, True, {}, float("nan"), float("inf")])
def test_invalid_gravity_rejected(value):
    task = gravity_task()
    task["metadata"]["control_condition"]["difficulty_parameters"]["hole_gravity"] = value
    with pytest.raises(ValueError):
        generate_task_state(task, "42")


def test_gravity_requires_holes_and_excludes_rotation():
    for params in ({"hazard_count": 0}, {"external_tilt": {"amplitude": 0.22, "period_ms": 14000}}):
        task = gravity_task()
        task["metadata"]["control_condition"]["difficulty_parameters"].update(params)
        with pytest.raises(ValueError):
            generate_task_state(task, "42")


def test_nearest_center_only_constant_magnitude_and_ties():
    contract = {"physics": {"hole_gravity": 0.5}, "hazards": [
        {"id": "left", "position": [100, 100]}, {"id": "right", "position": [500, 100]},
    ]}
    for position, expected_id, expected in [
        ([200, 100], "left", [-0.5, 0]),
        ([290, 100], "left", [-0.5, 0]),
        ([300, 100], "left", [-0.5, 0]),
        ([301, 100], "right", [0.5, 0]),
        ([500, 150], "right", [0, -0.5]),
    ]:
        vector, well_id = grader._hole_gravity(contract, position)
        assert well_id == expected_id
        assert vector == expected
        assert math.hypot(*vector) == 0.5
    vector, well_id = grader._hole_gravity(contract, [200, 200])
    assert well_id == "left"
    assert math.hypot(*vector) == pytest.approx(0.5)
    assert vector[0] == vector[1] < 0
    assert grader._hole_gravity(contract, [100, 100]) == ([0, 0], "left")


def test_neutral_pulls_toward_hole_and_countersteering_overcomes_it():
    _, truth = generate_task_state(gravity_task(), "42")
    truth.update(start=[350, 260], walls=[], hazards=[{"id": "well", "position": [550, 260], "radius": 20}])
    def state():
        return dict(position=list(truth["start"]), velocity=[0, 0], switch_index=0,
                    collisions=0, deaths=0, completed=False)
    neutral, balanced, escape = state(), state(), state()
    for tick in range(20):
        grader._tick(neutral, [0, 0], truth, tick_index=tick)
        grader._tick(balanced, [-0.5, 0], truth, tick_index=tick)
        grader._tick(escape, [-1, 0], truth, tick_index=tick)
    assert neutral["position"][0] > truth["start"][0]
    assert balanced["position"] == truth["start"]
    assert escape["position"][0] < truth["start"][0]


def test_replay_requires_correct_hole_force_and_physics():
    public, truth = generate_task_state(gravity_task(), "42")
    state = dict(position=list(truth["start"]), velocity=[0, 0], switch_index=0,
                 collisions=0, deaths=0, completed=False)
    before = {key: list(state[key]) for key in ("position", "velocity")}
    force, well_id = grader._hole_gravity(truth, state["position"])
    outcome = grader._tick(state, [0, 0], truth)
    event = dict(sequence=1, kind="physics_tick", t_ms=35, dt_ms=35, tilt=[0, 0],
                 gravity_tilt=force, gravity_well_id=well_id, before=before,
                 after={key: list(state[key]) for key in ("position", "velocity")}, **outcome)
    payload = dict(mechanic_id=public["mechanic_id"], task_id=public["task_id"],
                   challenge_id=public["challenge_id"], events=[event],
                   final_position=state["position"], final_velocity=state["velocity"],
                   switch_index=state["switch_index"], deaths=state["deaths"], collisions=state["collisions"],
                   manual_resets=0, tick_count=1, control_changes=0, seal_count=0, completed=False)
    assert grader.grade(payload, truth, public)["feedback"].startswith("tilt replay:")
    for field, value in (("gravity_tilt", [0, 0]), ("gravity_well_id", "wrong")):
        bad = copy.deepcopy(payload)
        bad["events"][0][field] = value
        assert "misreports hole gravity" in grader.grade(bad, truth, public)["feedback"]
    bad = copy.deepcopy(payload)
    del bad["events"][0]["gravity_tilt"]
    assert "misreports hole gravity" in grader.grade(bad, truth, public)["feedback"]
    bad = copy.deepcopy(payload)
    bad["events"][0]["after"] = before
    assert "collision physics" in grader.grade(bad, truth, public)["feedback"]


def test_materializer_keeps_variant_separate(tmp_path):
    gravity = materialize(tmp_path, variant="nearest_hole_gravity")
    rotating = materialize(tmp_path)
    assert gravity.name != rotating.name
    assert gravity.name in (gravity / "setup_task.sh").read_text()
    assert (gravity / "verifier.py").read_text() == (rotating / "verifier.py").read_text()
