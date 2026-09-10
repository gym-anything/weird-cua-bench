from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENV = BENCHMARK / "environments" / "lanternfin_dive_env"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load(BENCHMARK / "shared_scripts/incubator_generators/lanternfin_dive.py", "lanternfin_generator_test")
GRADER = _load(BENCHMARK / "shared_runtime/server/incubator_graders/lanternfin_dive.py", "lanternfin_grader_test")
SOLVER = _load(BENCHMARK / "tools/incubator_solvers/lanternfin_dive.py", "lanternfin_solver_test")
BASE_TASK = json.loads((ENV / "tasks/lanternfin_dive_seed_0001/task.json").read_text())
CONTROLS = json.loads((ENV / "controls.json").read_text())


def _task(level: int, interaction: str) -> dict:
    task = copy.deepcopy(BASE_TASK)
    task["id"] = f"lanternfin_test_d{level}_{interaction}@0.2"
    task["_control_condition"] = {
        "difficulty": level,
        "difficulty_parameters": copy.deepcopy(CONTROLS["difficulty"][str(level)]["parameters"]),
        "interaction": interaction,
        "real_time": "live",
    }
    return task


def test_generator_is_deterministic_and_pair_modes_share_the_world() -> None:
    for level in range(1, 6):
        simplified, simplified_truth = GENERATOR.generate(_task(level, "simplified"), "lanternfin-pair-seed")
        full, full_truth = GENERATOR.generate(_task(level, "full"), "lanternfin-pair-seed")
        assert simplified["initial"] == full["initial"]
        assert simplified["target"] == full["target"]
        assert simplified["physics"] == full["physics"]
        assert simplified_truth["target"] == full_truth["target"]
        assert simplified["control_condition"]["interaction"] == "simplified"
        assert full["control_condition"]["interaction"] == "full"
        assert GENERATOR.generate(_task(level, "full"), "lanternfin-pair-seed") == (full, full_truth)
        assert full["target"]["y"] != 0 and full["target"]["z"] != 0


def test_profiles_change_the_active_3d_control_contract() -> None:
    profiles = [GENERATOR.generate(_task(level, "full"), "lanternfin-profile-seed")[0] for level in range(1, 6)]
    assert [state["physics"]["hold_ticks"] for state in profiles] == [5, 7, 9, 12, 18]
    assert [state["physics"]["max_ticks"] for state in profiles] == [260, 340, 430, 560, 720]
    assert [state["physics"]["arrival_radius"] for state in profiles] == [0.17, 0.15, 0.13, 0.115, 0.095]
    assert profiles[0]["target"]["x"] < profiles[-1]["target"]["x"]


def _oracle_payload() -> tuple[dict, dict, dict]:
    public, truth = GENERATOR.generate(_task(4, "full"), "lanternfin-test-pass")
    fish = copy.deepcopy(public["initial"])
    controls = {channel: 0 for channel in SOLVER.CHANNELS}
    events = []
    hold = 0
    tick = 0
    for tick in range(public["physics"]["max_ticks"]):
        desired = SOLVER._desired({"fish": fish, "target": public["target"], "physics": public["physics"], "interaction": "full"})
        for channel in SOLVER.CHANNELS:
            if controls[channel] == desired[channel]:
                continue
            value = int(desired[channel])
            events.append({
                "seq": len(events) + 1,
                "type": "torque",
                "tick": tick,
                "channel": channel,
                "value": value,
                "before": {channel: controls[channel]},
                "after": value,
                "input_source": "torque_keyboard" if value else "torque_neutral_keyboard",
            })
            controls[channel] = value
        GRADER._step(fish, controls, public["physics"])
        hold = hold + 1 if GRADER._arrival(fish, public["target"], public["physics"]) else 0
        if hold >= public["physics"]["hold_ticks"]:
            break
    events.append({
        "seq": len(events) + 1,
        "type": "certify",
        "tick": tick + 1,
        "state": copy.deepcopy(fish),
        "hold_ticks": hold,
        "accepted": hold >= public["physics"]["hold_ticks"] and GRADER._arrival(fish, public["target"], public["physics"]),
        "input_source": "certify_button",
    })
    payload = {
        "mechanic_id": "lanternfin_dive",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "events": events,
        "completed": True,
    }
    return payload, truth, public


def test_independent_grader_accepts_an_ordinary_full_input_replay() -> None:
    payload, truth, public = _oracle_payload()
    result = GRADER.grade(payload, truth, public)
    assert result["graded"] is True
    assert result["passed"] is True


def test_grader_rejects_cross_surface_transcripts_and_false_certification() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "lanternfin-negative-seed")
    false_cert = {
        "mechanic_id": "lanternfin_dive",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "events": [{
            "seq": 1,
            "type": "certify",
            "tick": 0,
            "state": public["initial"],
            "hold_ticks": 0,
            "accepted": False,
            "input_source": "certify_button",
        }],
        "completed": False,
    }
    assert GRADER.grade(false_cert, truth, public)["passed"] is False
    wrong_surface = {
        "mechanic_id": "lanternfin_dive",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "events": [{
            "seq": 1,
            "type": "torque",
            "tick": 0,
            "channel": "tail",
            "value": 1,
            "before": {"tail": 0},
            "after": 1,
            "input_source": "torque_button",
        }],
        "completed": False,
    }
    assert "wrong interaction" in GRADER.grade(wrong_surface, truth, public)["feedback"]


def test_body_roll_rotates_visible_fins_and_dorsal_axis() -> None:
    frontend = BENCHMARK / "shared_runtime/app/mechanics/lanternfin_dive.js"
    script = r'''
const fs = require('fs'), vm = require('vm');
let source = fs.readFileSync(process.argv[1], 'utf8');
source = source.replace('window.WeirdCaptchaMechanics =', 'window.testBasis = fishBasis; window.WeirdCaptchaMechanics =');
const sandbox = {window: {}}; vm.runInNewContext(source,sandbox);
const basis = sandbox.window.testBasis;
for (const yaw of [-.4,0,.8]) for (const pitch of [-.3,0,.2]) {
  const zero = basis({yaw,pitch,roll:0});
  for (const roll of [-.9,.5]) {
    const rotated = basis({yaw,pitch,roll});
    for (const axis of ['x','y','z']) {
      if (Math.abs(rotated.forward[axis]-zero.forward[axis]) > 1e-10) throw Error('roll changed forward');
      if (Math.abs(rotated.right[axis]-(Math.cos(roll)*zero.right[axis]-Math.sin(roll)*zero.up[axis])) > 1e-10) throw Error('body roll is not rendered');
      if (Math.abs(rotated.up[axis]-(Math.cos(roll)*zero.up[axis]+Math.sin(roll)*zero.right[axis])) > 1e-10) throw Error('dorsal bank is not rendered');
    }
  }
}
'''
    subprocess.run(["node", "-e", script, str(frontend)], text=True, capture_output=True, check=True)


def test_controller_docks_with_residual_motion_and_delayed_decisions() -> None:
    for period in (1, 2, 3):
        for level in range(1, 6):
            for seed in range(100):
                public, _ = GENERATOR.generate(_task(level, "full"), str(seed))
                fish = copy.deepcopy(public["initial"])
                hold = 0
                snapshot = {"fish": fish, "target": public["target"], "physics": public["physics"]}
                for tick in range(public["physics"]["max_ticks"]):
                    if tick % period == 0:
                        controls = {channel: 0 for channel in SOLVER.CHANNELS} if SOLVER._coast_safe(snapshot) else SOLVER._desired(snapshot)
                    GRADER._step(fish, controls, public["physics"])
                    hold = hold + 1 if GRADER._arrival(fish, public["target"], public["physics"]) else 0
                    if hold >= public["physics"]["hold_ticks"] and SOLVER._coast_safe(snapshot):
                        break
                else:
                    raise AssertionError((period, level, seed, fish))
                for _ in range(80):
                    GRADER._step(fish, {channel: 0 for channel in SOLVER.CHANNELS}, public["physics"])
                    assert GRADER._arrival(fish, public["target"], public["physics"]), (period, level, seed)
