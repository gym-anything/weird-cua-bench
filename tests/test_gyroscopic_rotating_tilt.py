from __future__ import annotations

import copy
import math

import pytest

from weird_captcha_gym.shared_scripts.setup_task import generate_task_state
from weird_captcha_gym.shared_runtime.server.incubator_graders import board_game_captcha as grader
from weird_captcha_gym.tools.materialize_gyroscopic_variant import materialize, variant_task


def initial(truth):
    return dict(position=list(truth["start"]), velocity=[0.0, 0.0],
                switch_index=0, deaths=0, collisions=0, completed=False)


@pytest.mark.parametrize("level", range(1, 6))
def test_variant_preserves_world_and_controls(level):
    full, truth = generate_task_state(variant_task(level, "full"), "42")
    simplified, simple_truth = generate_task_state(variant_task(level, "simplified"), "42")
    baseline_task = variant_task(level, "full")
    del baseline_task["metadata"]["control_condition"]["difficulty_parameters"]["external_tilt"]
    baseline, _ = generate_task_state(baseline_task, "42")
    for key in ("stage", "start", "goal", "walls", "hazards", "switches", "requirements", "theme"):
        assert full[key] == simplified[key] == baseline[key]
    assert full["physics"] == truth["physics"] == simplified["physics"] == simple_truth["physics"]
    assert {k: v for k, v in full["physics"].items() if k != "external_tilt"} == baseline["physics"]
    assert "external_tilt" not in baseline["physics"]
    assert full["challenge_id"] != baseline["challenge_id"]
    assert generate_task_state(variant_task(level, "full"), "42") == (full, truth)


@pytest.mark.parametrize("value", [{}, {"amplitude": float("nan"), "period_ms": 14000},
                                  {"amplitude": True, "period_ms": 14000},
                                  {"amplitude": 1, "period_ms": 14000},
                                  {"amplitude": 0.22, "period_ms": 0}])
def test_invalid_disturbance_is_rejected(value):
    task = variant_task()
    task["metadata"]["control_condition"]["difficulty_parameters"]["external_tilt"] = value
    with pytest.raises(ValueError):
        generate_task_state(task, "42")


def test_centered_control_moves_ball_and_can_be_countered():
    _, truth = generate_task_state(variant_task(), "42")
    truth.update(start=[450, 260], walls=[], hazards=[], switches=[{"position": [1, 1], "radius": 1}])
    drifting, countered = initial(truth), initial(truth)
    for tick in range(86):
        grader._tick(drifting, [0, 0], truth, tick_index=tick)
        external = grader._external_tilt(truth, tick)
        assert math.hypot(*external) < 0.24
        grader._tick(countered, [-external[0], -external[1]], truth, tick_index=tick)
    assert math.dist(drifting["position"], truth["start"]) > 70
    assert countered["position"] == truth["start"]
    assert countered["velocity"] == [0, 0]
    first = grader._external_tilt(truth, 0)
    assert grader._external_tilt(truth, 100) != first
    assert grader._external_tilt(truth, 400) == first


def test_grader_rejects_forged_external_tilt_and_omitted_force():
    public, truth = generate_task_state(variant_task(), "42")
    state = initial(truth)
    before = {k: list(state[k]) for k in ("position", "velocity")}
    outcome = grader._tick(state, [0, 0], truth)
    event = dict(sequence=1, kind="physics_tick", t_ms=35, dt_ms=35, tilt=[0, 0],
                 external_tilt=grader._external_tilt(truth, 0), before=before,
                 after={k: list(state[k]) for k in ("position", "velocity")}, **outcome)
    payload = dict(mechanic_id=public["mechanic_id"], task_id=public["task_id"],
                   challenge_id=public["challenge_id"], events=[event],
                   final_position=state["position"], final_velocity=state["velocity"],
                   switch_index=state["switch_index"], deaths=state["deaths"],
                   collisions=state["collisions"], manual_resets=0, tick_count=1,
                   control_changes=0, seal_count=0, completed=False)
    assert grader.grade(payload, truth, public)["feedback"].startswith("tilt replay:")
    forged = copy.deepcopy(payload)
    forged["events"][0]["external_tilt"] = [0, 0]
    assert "misreports external tilt" in grader.grade(forged, truth, public)["feedback"]
    forged = copy.deepcopy(payload)
    forged["events"][0]["after"] = before
    assert "collision physics" in grader.grade(forged, truth, public)["feedback"]


def test_materialized_variant_keeps_task_contract(tmp_path):
    path = materialize(tmp_path)
    assert path.name == "board_game_captcha_d5_full_rotating_tilt_seed_0001"
    for name in ("task.json", "setup_task.sh", "export_result.sh", "verifier.py"):
        assert (path / name).is_file()
    assert path.name in (path / "setup_task.sh").read_text()
    with pytest.raises(FileExistsError):
        materialize(tmp_path)
