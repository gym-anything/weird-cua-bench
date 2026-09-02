from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENV = BENCH / "environments" / "reveal_to_identify_env"
GENERATOR_PATH = BENCH / "shared_scripts" / "incubator_generators" / "reveal_to_identify.py"
GRADER_PATH = BENCH / "shared_runtime" / "server" / "incubator_graders" / "reveal_to_identify.py"
VERIFIER_PATH = ENV / "tasks/reveal_to_identify_seed_0001/verifier.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("reveal_to_identify_generator_test", GENERATOR_PATH)
GRADER = _load("reveal_to_identify_grader_test", GRADER_PATH)
VERIFIER = _load("reveal_to_identify_verifier_test", VERIFIER_PATH)


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = json.loads(
        (ENV / "tasks/reveal_to_identify_seed_0001/task.json").read_text(encoding="utf-8")
    )
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(
            controls["difficulty"][str(level)]["parameters"]
        ),
    }
    return task


def _payload(public: dict, truth: dict, interaction: str, answer: str | None = None) -> dict:
    source = "plate_click" if interaction == "full" else "coordinate_reveal"
    points = copy.deepcopy(truth["salient_points"])
    events = [
        {
            "sequence": index,
            "kind": "reveal",
            "point": copy.deepcopy(point),
            "radius": truth["reveal"]["radius"],
            "remaining_after": truth["reveal"]["budget"] - index,
            "input_source": source,
        }
        for index, point in enumerate(points, 1)
    ]
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "revealed_centers": points,
        "reveal_count": len(events),
        "remaining_budget": truth["reveal"]["budget"] - len(events),
        "answer": truth["answer"] if answer is None else answer,
        "completed": True,
    }


def _world(public: dict) -> dict:
    return {
        "stage": public["stage"],
        "scene": public["scene"],
        "reveal": public["reveal"],
        "generator": public["generator"],
    }


def test_all_ten_control_conditions_share_the_world_and_grade() -> None:
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(
                _task(level, interaction), f"reveal-matrix-{level}"
            )
            decision = GRADER.grade(_payload(public, truth, interaction), truth, public)
            assert decision["passed"] is True, (level, interaction, decision)
            worlds.append(_world(public))
        assert worlds[0] == worlds[1]


def test_generation_is_deterministic_diverse_and_solvable_at_every_level() -> None:
    fingerprints = set()
    labels = set()
    for level in range(1, 6):
        task = _task(level, "full")
        pool = set(task["_control_condition"]["difficulty_parameters"]["object_pool"])
        level_labels = set()
        for seed_index in range(20):
            seed = f"reveal-reach-{level}-{seed_index}"
            public, truth = GENERATOR.generate(task, seed)
            public_again, truth_again = GENERATOR.generate(task, seed)
            assert public == public_again
            assert truth == truth_again
            assert truth["object_code"] in pool
            assert len(truth["salient_points"]) <= truth["reveal"]["budget"]
            assert GRADER.grade(_payload(public, truth, "full"), truth, public)["passed"]
            fingerprints.add(json.dumps(_world(public), sort_keys=True))
            labels.add(truth["object_code"])
            level_labels.add(truth["object_code"])
        assert len(level_labels) >= min(4, len(pool))
    assert len(fingerprints) == 100
    assert len(labels) >= 12


def test_public_state_contains_no_semantic_answer_or_solver_points() -> None:
    public, truth = GENERATOR.generate(_task(2, "full"), "reveal-hidden-answer")
    assert truth["answer"]
    assert truth["accepted_answers"]
    assert truth["salient_points"]
    for private_key in ("answer", "accepted_answers", "object_code", "salient_points"):
        assert private_key not in public


def test_stale_wrong_surface_tampering_and_wrong_answer_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(2, "full"), "reveal-negative")

    payload = _payload(public, truth, "full")
    payload["challenge_id"] = "stale-plate"
    assert "stale" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full")
    payload["events"][0]["input_source"] = "coordinate_reveal"
    assert "interaction surface" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full")
    payload["events"][0]["point"] = [-1, 250]
    payload["revealed_centers"][0] = [-1, 250]
    assert "leaves the plate" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full")
    payload["events"][0]["remaining_after"] += 1
    assert "false remaining budget" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full")
    payload["events"][0]["radius"] += 0.5
    assert "wrong disc radius" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full", answer="not the object")
    assert GRADER.grade(payload, truth, public)["passed"] is False

    altered_public = copy.deepcopy(public)
    altered_public["reveal"]["budget"] += 1
    assert "public reveal differs" in GRADER.grade(
        _payload(public, truth, "full"), truth, altered_public
    )["feedback"]


def test_no_reveal_over_budget_and_forged_summaries_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(5, "simplified"), "reveal-budget")
    payload = _payload(public, truth, "simplified")
    payload.update(
        events=[], revealed_centers=[], reveal_count=0,
        remaining_budget=truth["reveal"]["budget"],
    )
    assert GRADER.grade(payload, truth, public)["passed"] is False

    payload = _payload(public, truth, "simplified")
    payload["events"].append(copy.deepcopy(payload["events"][-1]))
    payload["events"][-1]["sequence"] += 1
    payload["revealed_centers"].append(copy.deepcopy(payload["revealed_centers"][-1]))
    payload["reveal_count"] += 1
    payload["remaining_budget"] -= 1
    assert GRADER.grade(payload, truth, public)["passed"] is False

    payload = _payload(public, truth, "simplified")
    payload["revealed_centers"][0][0] += 1
    assert "centers do not match" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "simplified")
    payload["reveal_count"] -= 1
    assert "count does not match" in GRADER.grade(payload, truth, public)["feedback"]


def test_exported_task_verifier_is_independent_and_rejects_tampering() -> None:
    public, truth = GENERATOR.generate(_task(3, "full"), "reveal-independent-verifier")
    payload = _payload(public, truth, "full")
    accepted = VERIFIER.verify_exported_bundle(
        {"result": payload, "ground_truth": truth, "public_state": public}
    )
    assert accepted == {
        "passed": True,
        "score": 100,
        "feedback": "independent reveal verifier: 4/5 discs replayed; identification accepted",
    }

    forged = copy.deepcopy(payload)
    forged["events"][0]["radius"] += 1
    forged["server_grade"] = {"passed": True, "score": 100}
    rejected = VERIFIER.verify_exported_bundle(
        {"result": forged, "ground_truth": truth, "public_state": public}
    )
    assert rejected["passed"] is False
    assert "radius is invalid" in rejected["feedback"]

    verifier_source = VERIFIER_PATH.read_text(encoding="utf-8")
    assert "incubator_graders" not in verifier_source
    assert "GRADER_PATH" not in verifier_source


def test_live_and_paused_preserve_the_static_decision_world() -> None:
    live, live_truth = GENERATOR.generate(
        _task(4, "full", "live"), "reveal-time-equivalence"
    )
    paused, paused_truth = GENERATOR.generate(
        _task(4, "full", "paused"), "reveal-time-equivalence"
    )
    assert _world(live) == _world(paused)
    assert live_truth["answer"] == paused_truth["answer"]
    assert live_truth["salient_points"] == paused_truth["salient_points"]
    assert live["control_condition"]["real_time"] == "live"
    assert paused["control_condition"]["real_time"] == "paused"


def test_difficulty_profiles_change_the_actual_reveal_problem() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    profiles = [controls["difficulty"][str(level)]["parameters"] for level in range(1, 6)]
    assert [len(item["object_pool"]) for item in profiles] == [6, 10, 14, 14, 14]
    assert [item["reveal_budget"] for item in profiles] == [7, 6, 5, 5, 4]
    assert [item["reveal_radius"] for item in profiles] == [96, 78, 62, 50, 43]
    assert [item["clutter_count"] for item in profiles] == [4, 8, 14, 22, 32]
    assert [item["foreground_marks"] for item in profiles] == [0, 0, 1, 3, 5]
    assert [item["rotation_max_deg"] for item in profiles] == [4, 7, 12, 18, 24]


def test_baseline_source_registration_and_static_clock_contract() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    env = json.loads((ENV / "env.json").read_text(encoding="utf-8"))
    task = json.loads(
        (ENV / "tasks/reveal_to_identify_seed_0001/task.json").read_text(encoding="utf-8")
    )
    split = json.loads((BENCH / "splits/reveal_to_identify_split.json").read_text(encoding="utf-8"))
    manifest = json.loads((BENCH / "benchmark_manifest.json").read_text(encoding="utf-8"))
    real_time = json.loads((BENCH / "real_time.json").read_text(encoding="utf-8"))["environments"]
    mechanic = (BENCH / "shared_runtime/app/mechanics/reveal_to_identify.js").read_text(encoding="utf-8")

    assert controls["baseline"] == {"difficulty": 2, "interaction": "full", "real_time": "live"}
    assert controls["real_time"] == {
        "play_time_seconds": 120,
        "observation_window_ms": 0,
        "frames_per_observation": 1,
    }
    assert env["runner_options"] == controls["real_time"]
    assert task["name"] == "Reveal to Identify"
    assert task["difficulty"] == "easy"
    assert task["metadata"]["source_anchors"] == ["GWP-002", "GWP-003"]
    assert task["metadata"]["status"] == "prototype_visual_candidate"
    assert len(split["variations_tasks"]) == 20
    assert manifest["environments"].count("reveal_to_identify_env") == 1
    assert manifest["environment_count"] == len(manifest["environments"])
    assert real_time["reveal_to_identify"] == controls["real_time"]
    assert 'beginAction?.("reveal-to-identify-plate-click")' in mechanic
    assert 'beginAction?.("reveal-to-identify-coordinate")' in mechanic
    assert "setTimeout" not in mechanic
    assert "requestAnimationFrame" not in mechanic

    for path in (
        ENV / "scripts/install_puzzle_runtime.sh",
        ENV / "scripts/setup_puzzle_runtime.sh",
        ENV / "tasks/reveal_to_identify_seed_0001/setup_task.sh",
        ENV / "tasks/reveal_to_identify_seed_0001/export_result.sh",
    ):
        assert os.access(path, os.X_OK), path
