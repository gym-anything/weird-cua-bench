from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_ROOT = ROOT / "weird_captcha_gym" / "environments" / "pocket_locksmith_env"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = _load(
    "pocket_locksmith_test_generator",
    ROOT / "weird_captcha_gym" / "shared_scripts" / "incubator_generators" / "pocket_locksmith.py",
)
grader = _load(
    "pocket_locksmith_test_grader",
    ROOT / "weird_captcha_gym" / "shared_runtime" / "server" / "incubator_graders" / "pocket_locksmith.py",
)
materializer = _load(
    "pocket_locksmith_test_materializer",
    ROOT / "weird_captcha_gym" / "tools" / "materialize_controlled_tasks.py",
)


BASE_TASK = json.loads(
    (ENV_ROOT / "tasks" / "pocket_locksmith_seed_0001" / "task.json").read_text(encoding="utf-8")
)
CONTROLS = json.loads((ENV_ROOT / "controls.json").read_text(encoding="utf-8"))


def _task(level: int, interaction: str) -> dict:
    task = copy.deepcopy(BASE_TASK)
    task["id"] = f"pocket_locksmith_d{level}_{interaction}_seed_0001@0.2"
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": "live",
        "difficulty_parameters": copy.deepcopy(CONTROLS["difficulty"][str(level)]["parameters"]),
    }
    return task


def _success_payload(public: dict, truth: dict, interaction: str) -> dict:
    events = []
    current = [float(value) for value in truth["initial_torsions"]]
    step = float(truth["torsion_step_deg"])
    for index, target in enumerate(truth["target_torsions"]):
        count = round((float(target) - current[index]) / step)
        side = 1 if count >= 0 else -1
        for _ in range(abs(count)):
            before = current[index]
            after = before + side * step
            events.append(
                {
                    "seq": len(events) + 1,
                    "type": "torsion",
                    "bond_id": f"bond-{index + 1}",
                    "before": before,
                    "after": after,
                    "side": side,
                    "input_source": "torsion_button" if interaction == "simplified" else "torsion_drag",
                    **(
                        {}
                        if interaction == "simplified"
                        else {
                            "camera": copy.deepcopy(public["camera"]),
                            "screen": list(grader.handle_visible(public, grader.forward_kinematics(truth["base_points"], current), public["camera"], index, side)[1]),
                        }
                    ),
                }
            )
            current[index] = after
    events.append(
        {
            "seq": len(events) + 1,
            "type": "certify",
            "accepted": True,
            "camera": copy.deepcopy(public["camera"]),
            "torsions": current,
        }
    )
    return {
        "mechanic_id": "pocket_locksmith",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "events": events,
        "completed": True,
    }


def test_controls_have_both_surfaces_and_materialize_ten_variants(tmp_path):
    materializer.validate_controls(CONTROLS, ENV_ROOT)
    written = materializer.materialize_environment(ENV_ROOT, tmp_path)
    assert len(written) == 10
    assert {path.name for path in written} == {
        f"pocket_locksmith_d{level}_{interaction}_seed_0001"
        for level in range(1, 6)
        for interaction in ("simplified", "full")
    }
    for path in written:
        task = json.loads((path / "task.json").read_text(encoding="utf-8"))
        condition = task["metadata"]["control_condition"]
        assert condition["real_time"] == "live"
        assert condition["interaction"] in {"simplified", "full"}
        assert task["name"].startswith("Pocket Locksmith · Difficulty ")


def test_all_profiles_have_safe_target_geometry_and_pairwise_world_identity():
    for level in range(1, 6):
        simplified_public, simplified_truth = generator.generate(_task(level, "simplified"), "pocket-locksmith-profile-seed")
        full_public, full_truth = generator.generate(_task(level, "full"), "pocket-locksmith-profile-seed")
        simplified_check = grader._world_check(simplified_public, simplified_truth, simplified_truth["target_torsions"])
        full_check = grader._world_check(full_public, full_truth, full_truth["target_torsions"])
        simplified_initial = grader._world_check(simplified_public, simplified_truth, simplified_truth["initial_torsions"])
        full_initial = grader._world_check(full_public, full_truth, full_truth["initial_torsions"])
        assert simplified_check["passed"], (level, simplified_check)
        assert full_check["passed"], (level, full_check)
        assert not simplified_initial["passed"], (level, simplified_initial)
        assert not full_initial["passed"], (level, full_initial)
        assert simplified_public["pocket"] == full_public["pocket"]
        assert simplified_public["ligand"] == full_public["ligand"]
        assert simplified_truth["target_torsions"] == full_truth["target_torsions"]
        assert "target_torsions" not in json.dumps(simplified_public, sort_keys=True)
        assert "target_points" not in json.dumps(simplified_public, sort_keys=True)


def test_simplified_replay_accepts_visible_connected_fit_and_rejects_forgery():
    public, truth = generator.generate(_task(4, "simplified"), "pocket-locksmith-grade-seed")
    payload = _success_payload(public, truth, "simplified")
    decision = grader.grade(payload, truth, public)
    assert decision["passed"] is True, decision
    assert decision["metrics"]["contacts"] == len(truth["contacts"])

    wrong_input = copy.deepcopy(payload)
    wrong_input["events"][0]["input_source"] = "torsion_drag"
    assert grader.grade(wrong_input, truth, public)["passed"] is False

    forged = copy.deepcopy(payload)
    forged["events"] = [{"seq": 1, "type": "certify", "accepted": True}]
    assert grader.grade(forged, truth, public)["passed"] is False

    failed = copy.deepcopy(payload)
    failed["events"][-1]["accepted"] = False
    assert grader.grade(failed, truth, public)["passed"] is False


def test_visible_contact_fit_is_not_rejected_by_private_target_torsions():
    public, truth = generator.generate(
        _task(4, "simplified"),
        "fairness-4-0",
    )
    current = [float(value) for value in truth["initial_torsions"]]
    probe = [-30.0, -75.0, 0.0]
    events = []
    # This is a reachable state with all visible contact regions occupied and
    # no clashes, but it is not the generator's private construction pose.
    step = float(truth["torsion_step_deg"])
    for bond_index, (before_target, after_target) in enumerate(zip(current, probe, strict=True)):
        count = round((after_target - before_target) / step)
        side = 1 if count >= 0 else -1
        for _ in range(abs(count)):
            before = current[bond_index]
            current[bond_index] += side * step
            events.append(
                {
                    "seq": len(events) + 1,
                    "type": "torsion",
                    "bond_id": f"bond-{bond_index + 1}",
                    "before": before,
                    "after": current[bond_index],
                    "side": side,
                    "input_source": "torsion_button",
                }
            )
    events.append(
        {
            "seq": len(events) + 1,
            "type": "certify",
            "accepted": True,
            "camera": copy.deepcopy(public["camera"]),
            "torsions": current,
        }
    )
    visible_fit = grader._world_check(public, truth, current)
    assert visible_fit["passed"], visible_fit
    assert any(error >= 15 for error in visible_fit["torsion_errors"])
    payload = {
        "mechanic_id": "pocket_locksmith",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "events": events,
        "completed": True,
    }
    assert grader.grade(payload, truth, public)["passed"] is True


def test_full_replay_rejects_hidden_or_unwitnessed_torsion_input():
    public, truth = generator.generate(_task(4, "full"), "pocket-locksmith-full-seed")
    payload = _success_payload(public, truth, "full")
    first_torsion = next(event for event in payload["events"] if event["type"] == "torsion")
    first_torsion.pop("screen")
    decision = grader.grade(payload, truth, public)
    assert decision["passed"] is False
    assert "handle" in decision["feedback"]


def test_no_inactive_private_angle_tolerance_in_difficulty_or_generated_truth():
    for level in range(1, 6):
        assert "torsion_tolerance_deg" not in CONTROLS["difficulty"][str(level)]["parameters"]
        public, truth = generator.generate(_task(level, "simplified"), "angle-contract")
        assert "torsion_tolerance_deg" not in truth
        assert "torsion_tolerance_deg" not in public["control_condition"]["difficulty_parameters"]
        # Construction angles remain an oracle/diagnostic aid; they are not a
        # second hidden goal in addition to the visible fit constraints.
        altered = copy.deepcopy(truth)
        altered["target_torsions"] = [value + 90 for value in truth["target_torsions"]]
        payload = _success_payload(public, truth, "simplified")
        assert grader.grade(payload, altered, public)["passed"] is True
