from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "weird_captcha_gym" / "shared_scripts" / "incubator_generators" / "loopmakers_trial.py"
GRADER_PATH = ROOT / "weird_captcha_gym" / "shared_runtime" / "server" / "incubator_graders" / "loopmakers_trial.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GEN = load_module("loopmakers_trial_test_generator", GENERATOR_PATH)
GRADE = load_module("loopmakers_trial_test_grader", GRADER_PATH)


def task(condition=None):
    metadata = {}
    if condition is not None:
        difficulty, interaction = condition
        metadata["control_condition"] = {
            "difficulty": difficulty,
            "difficulty_parameters": GEN.profile_for(difficulty) | {"difficulty": None},
            "interaction": interaction,
            "real_time": "live",
        }
        metadata["control_condition"]["difficulty_parameters"].pop("difficulty")
    return {"id": "loopmakers_trial_test@0.2", "metadata": metadata}


def valid_transcript(public, truth, interaction):
    points = copy.deepcopy(public["points"])
    targets = {point["id"]: point for point in truth["solution_points"]}
    params = public["control_condition"]["difficulty_parameters"] if interaction == "simplified" else {}
    events = []
    for point in points[1:-1]:
        target = targets[point["id"]]
        if interaction == "full":
            events.append({"seq": len(events) + 1, "type": "adjust", "point_id": point["id"], "action": "drag", "input_source": "point_drag", "before": copy.deepcopy(point), "after": copy.deepcopy(target)})
            point.update(target)
            continue
        dx = round((target["x"] - point["x"]) / params["radius_step"])
        dy = round((target["y"] - point["y"]) / params["height_step"])
        for action, count in (("widen" if dx > 0 else "tighten", abs(dx)), ("lower" if dy > 0 else "raise", abs(dy))):
            for _ in range(count):
                before = copy.deepcopy(point)
                if action == "widen": point["x"] += params["radius_step"]
                if action == "tighten": point["x"] -= params["radius_step"]
                if action == "lower": point["y"] += params["height_step"]
                if action == "raise": point["y"] -= params["height_step"]
                events.append({"seq": len(events) + 1, "type": "adjust", "point_id": point["id"], "action": action, "input_source": "proxy_controls", "before": before, "after": copy.deepcopy(point)})
    summary = GEN.simulate(points, public["features"], public["physics"])
    events.append({"seq": len(events) + 1, "type": "test_run", "input_source": "test_button", "points": copy.deepcopy(points), "summary": summary})
    return {"mechanic_id": "loopmakers_trial", "task_id": public["task_id"], "challenge_id": public["challenge_id"], "interaction_mode": interaction, "completed": True, "events": events}


def test_public_name_sources_and_no_private_solution():
    public, truth = GEN.generate(task((3, "full")), "seed-test-0001")
    assert public["public_name"] == truth["public_name"] == "Loopmaker's Trial"
    assert public["asset_manifest"] == "shared_runtime/assets/provenance/loopmakers_trial_v0.json"
    assert (ROOT / "weird_captcha_gym" / public["asset_manifest"]).is_file()
    assert public["source_anchors"] == ["XUIF-261", "XUIF-229"]
    assert "solution_points" not in public
    assert public["challenge_id"] == truth["challenge_id"]


def test_baseline_matches_d3_full_world():
    base_public, base_truth = GEN.generate(task(), "seed-test-0001")
    full_public, full_truth = GEN.generate(task((3, "full")), "seed-test-0001")
    for field in ("challenge_id", "points", "features", "physics", "geometry_hash"):
        assert base_public[field] == full_public[field]
    assert base_truth["solution_points"] == full_truth["solution_points"]
    assert base_truth["world_hash"] == full_truth["world_hash"]


def test_five_profiles_and_interaction_pairs_preserve_world():
    for difficulty in range(1, 6):
        simplified, simplified_truth = GEN.generate(task((difficulty, "simplified")), f"seed-d{difficulty}")
        full, full_truth = GEN.generate(task((difficulty, "full")), f"seed-d{difficulty}")
        assert simplified["challenge_id"] == full["challenge_id"]
        assert simplified["points"] == full["points"]
        assert simplified["features"] == full["features"]
        assert simplified["physics"] == full["physics"]
        assert simplified_truth["solution_points"] == full_truth["solution_points"]
        assert len(simplified["points"]) == 10 + difficulty
        assert len(simplified["features"]) == 2 + difficulty


def test_canonical_routes_vary_across_seeds_and_still_pass():
    for difficulty in range(1, 6):
        hashes = set()
        for index in range(24):
            public, truth = GEN.generate(task((difficulty, "full")), f"target-variation-{difficulty}-{index}")
            hashes.add(truth["world_hash"])
            assert GEN.simulate(truth["solution_points"], truth["features"], truth["physics"])["passed"] is True
            assert public["geometry_hash"] != truth["world_hash"]
        assert len(hashes) > 1


def test_all_profiles_accept_their_visible_edit_transcript():
    for difficulty in range(1, 6):
        for interaction in ("simplified", "full"):
            public, truth = GEN.generate(task((difficulty, interaction)), f"seed-d{difficulty}")
            payload = valid_transcript(public, truth, interaction)
            decision = GRADE.grade(payload, truth, public)
            assert decision["passed"] is True, (difficulty, interaction, decision)


def test_initial_routes_are_diagnostic_and_controls_have_clearance():
    import math

    for difficulty in range(1, 6):
        for index in range(100):
            public, truth = GEN.generate(task((difficulty, "full")), f"initial-audit-{difficulty}-{index}")
            assert GEN.simulate(public["points"], public["features"], public["physics"])["passed"] is False
            assert GEN.simulate(truth["solution_points"], truth["features"], truth["physics"])["passed"] is True
            distances = [
                math.dist((left["x"], left["y"]), (right["x"], right["y"]))
                for left_index, left in enumerate(public["points"])
                for right in public["points"][left_index + 1:]
            ]
            assert min(distances) >= 24.0


def test_wrong_input_surface_is_rejected():
    public, truth = GEN.generate(task((3, "simplified")), "seed-wrong-surface")
    payload = valid_transcript(public, truth, "simplified")
    payload["events"][0]["input_source"] = "point_drag"
    decision = GRADE.grade(payload, truth, public)
    assert decision["passed"] is False


def test_stale_geometry_in_test_run_is_rejected():
    public, truth = GEN.generate(task((3, "full")), "seed-stale-run")
    payload = valid_transcript(public, truth, "full")
    payload["events"][-1]["points"][1]["x"] += 3
    decision = GRADE.grade(payload, truth, public)
    assert decision["passed"] is False


def test_controls_and_split_materialize_the_contract():
    controls = json.loads((ROOT / "weird_captcha_gym/environments/loopmakers_trial_env/controls.json").read_text())
    split = json.loads((ROOT / "weird_captcha_gym/splits/loopmakers_trial_split.json").read_text())
    assert controls["baseline"] == {"difficulty": 3, "interaction": "full", "real_time": "live"}
    assert all(controls["difficulty"][str(level)]["parameters"] for level in range(1, 6))
    assert controls["interaction"]["simplified"]["implemented"] is True
    assert controls["interaction"]["full"]["implemented"] is True
    assert len(split["variations_tasks"]) == 20


def test_certification_requires_test_after_last_edit():
    public, truth = GEN.generate(task((3, "full")), "stale-certification")
    payload = valid_transcript(public, truth, "full")
    point = payload["events"][-1]["points"][1]
    payload["events"].append({"seq": len(payload["events"]) + 1, "type": "adjust", "point_id": point["id"], "action": "drag", "input_source": "point_drag", "before": copy.deepcopy(point), "after": dict(point, y=point["y"]+10)})
    assert not GRADE.grade(payload, truth, public)["passed"]


def test_locked_endpoints_rejected_on_both_surfaces():
    for interaction in ("full", "simplified"):
        public, truth = GEN.generate(task((3, interaction)), "locked-endpoints")
        for point in (public["points"][0], public["points"][-1]):
            payload = valid_transcript(public, truth, interaction)
            payload["events"][0] = {"seq": 1, "type": "adjust", "point_id": point["id"], "action": "drag" if interaction == "full" else "raise", "input_source": "point_drag" if interaction == "full" else "proxy_controls", "before": point, "after": dict(point, y=point["y"]-10)}
            assert "locked" in GRADE.grade(payload, truth, public)["feedback"]


def test_proxy_boundary_clamps_match_browser_and_reject_arbitrary_steps():
    for level in range(1, 6):
        public, truth = GEN.generate(task((level, "simplified")), "boundary-clamp")
        for action, axis, bound, sign, step_key in (("raise", "y", 14, -1, "height_step"), ("lower", "y", 444, 1, "height_step"), ("tighten", "x", 18, -1, "radius_step"), ("widen", "x", 882, 1, "radius_step")):
            point = copy.deepcopy(public["points"][1])
            step = public["control_condition"]["difficulty_parameters"][step_key]
            events = []
            while point[axis] != bound:
                before = copy.deepcopy(point)
                point[axis] = max(bound, point[axis]-step) if sign < 0 else min(bound, point[axis]+step)
                events.append({"seq": len(events)+1, "type": "adjust", "point_id": point["id"], "action": action, "input_source": "proxy_controls", "before": before, "after": copy.deepcopy(point)})
            payload = {"mechanic_id": "loopmakers_trial", "task_id": public["task_id"], "challenge_id": public["challenge_id"], "events": events}
            assert GRADE.grade(payload, truth, public)["feedback"] == "no completed physical test run was submitted"
            events[-1]["after"][axis] = bound-sign*2
            assert "impossible increment" in GRADE.grade(payload, truth, public)["feedback"]


def test_malformed_edit_coordinates_rejected():
    public, truth = GEN.generate(task((3, "full")), "malformed-edit")
    for field in ("before", "after"):
        payload = valid_transcript(public, truth, "full")
        payload["events"][0][field] = [42]
        assert not GRADE.grade(payload, truth, public)["passed"]
