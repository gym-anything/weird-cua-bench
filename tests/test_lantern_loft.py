from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "weird_captcha_gym" / "shared_scripts" / "incubator_generators" / "lantern_loft.py"
GRADER_PATH = ROOT / "weird_captcha_gym" / "shared_runtime" / "server" / "incubator_graders" / "lantern_loft.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("lantern_loft_test_generator", GENERATOR_PATH)
GRADER = _load("lantern_loft_test_grader", GRADER_PATH)


def _task(difficulty: int, interaction: str) -> dict:
    return {
        "id": f"lantern-test-d{difficulty}-{interaction}@0.1",
        "_control_condition": {
            "difficulty": difficulty,
            "interaction": interaction,
            "difficulty_parameters": dict(GENERATOR.PROFILES[difficulty]),
        },
    }


def _passing_payload(public: dict, truth: dict) -> dict:
    condition = truth["control_condition"]
    events = []
    sequence = 0
    timestamp = 0
    for move in truth["solution_slides"]:
        sequence += 1
        events.append(
            {
                "seq": sequence,
                "t_ms": timestamp,
                "kind": "slide",
                "module_id": move["module_id"],
                "from_slot": move["from_slot"],
                "to_slot": move["to_slot"],
                "input_source": "drag" if condition["interaction"] == "full" else "proxy_slide",
            }
        )
        timestamp += 1
    for source, target in zip(truth["route_slots"], truth["route_slots"][1:]):
        sequence += 1
        events.append(
            {
                "seq": sequence,
                "t_ms": timestamp,
                "kind": "step",
                "from_slot": source,
                "to_slot": target,
                "input_source": "surface_click" if condition["interaction"] == "full" else "proxy_step",
            }
        )
        timestamp += 1
    sequence += 1
    events.append({"seq": sequence, "t_ms": timestamp, "kind": "finish", "input_source": "physical_contact"})
    return {
        "mechanic_id": "lantern_loft",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "interaction": public["control_condition"]["interaction"],
        "completed": True,
        "events": events,
    }


def test_all_difficulties_and_both_input_surfaces_share_the_world():
    for difficulty in range(1, 6):
        full_public, full_truth = GENERATOR.generate(_task(difficulty, "full"), f"lantern-regression-{difficulty}")
        simple_public, simple_truth = GENERATOR.generate(_task(difficulty, "simplified"), f"lantern-regression-{difficulty}")
        assert full_public["world"] == simple_public["world"]
        assert full_truth["world"] == simple_truth["world"]
        assert len(full_truth["route_slots"]) == GENERATOR.PROFILES[difficulty]["route_count"]
        assert len(full_truth["solution_slides"]) == GENERATOR.PROFILES[difficulty]["slide_count"]
        assert full_public["world"]["rules"]["max_height_delta"] == 1


def test_solution_replays_and_contract_mismatches_fail():
    for interaction in ("full", "simplified"):
        public, truth = GENERATOR.generate(_task(4, interaction), f"lantern-replay-{interaction}")
        payload = _passing_payload(public, truth)
        decision = GRADER.grade(payload, truth, public)
        assert decision["passed"] is True

        wrong_surface = json.loads(json.dumps(payload))
        wrong_surface["events"][0]["input_source"] = "proxy_slide" if interaction == "full" else "drag"
        assert GRADER.grade(wrong_surface, truth, public)["passed"] is False

        missing_surface = json.loads(json.dumps(payload))
        missing_surface.pop("interaction")
        assert GRADER.grade(missing_surface, truth, public)["passed"] is False

        stale = json.loads(json.dumps(payload))
        stale["challenge_id"] = "stale-lantern"
        assert GRADER.grade(stale, truth, public)["passed"] is False

        illegal = json.loads(json.dumps(payload))
        illegal["events"][0]["to_slot"] = (illegal["events"][0]["to_slot"] + 2) % 9
        assert GRADER.grade(illegal, truth, public)["passed"] is False


def test_target_metadata_and_registry_are_present():
    controls = json.loads((ROOT / "weird_captcha_gym" / "environments" / "lantern_loft_env" / "controls.json").read_text())
    task = json.loads((ROOT / "weird_captcha_gym" / "environments" / "lantern_loft_env" / "tasks" / "lantern_loft_seed_0001" / "task.json").read_text())
    manifest = json.loads((ROOT / "weird_captcha_gym" / "benchmark_manifest.json").read_text())
    real_time = json.loads((ROOT / "weird_captcha_gym" / "real_time.json").read_text())
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert task["metadata"]["source_anchors"] == ["PHY-059"]
    assert task["metadata"]["capabilities"] == ["visual understanding (3D)", "reasoning and planning"]
    assert "lantern_loft_env" in manifest["environments"]
    assert real_time["environments"]["lantern_loft"]["observation_window_ms"] == 0
    assert real_time["environments"]["lantern_loft"]["frames_per_observation"] == 1
