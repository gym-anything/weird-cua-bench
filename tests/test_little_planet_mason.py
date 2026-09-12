from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "weird_captcha_gym" / "shared_scripts" / "incubator_generators" / "little_planet_mason.py"
GRADER_PATH = ROOT / "weird_captcha_gym" / "shared_runtime" / "server" / "incubator_graders" / "little_planet_mason.py"
TASK_PATH = ROOT / "weird_captcha_gym" / "environments" / "little_planet_mason_env" / "tasks" / "little_planet_mason_seed_0001" / "task.json"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def task_with_condition(level: int, interaction: str) -> dict:
    task = json.loads(TASK_PATH.read_text(encoding="utf-8"))
    controls = json.loads((TASK_PATH.parents[2] / "controls.json").read_text(encoding="utf-8"))
    task["_control_condition"] = {"difficulty": level, "interaction": interaction, "real_time": "live", "difficulty_parameters": controls["difficulty"][str(level)]["parameters"]}
    return task


def solution_payload(public: dict, truth: dict, interaction: str, order: list[str] | None = None) -> dict:
    events = []
    sequence = 0
    angles = {str(block["id"]): 0.0 for block in truth["blocks"]}
    blocks = {str(block["id"]): block for block in truth["blocks"]}
    for block_id in order or truth["solution_order"]:
        block = blocks[block_id]
        if interaction == "simplified":
            sequence += 1
            events.append({"sequence": sequence, "kind": "select", "block_id": block_id, "input_source": "tray_select"})
        target = float(block["target_angle"])
        turns = int(round((((target + math.pi) % (2 * math.pi)) - math.pi) / (math.pi / 12)))
        for _ in range(abs(turns)):
            sequence += 1
            delta = math.pi / 12 * (1 if turns >= 0 else -1)
            before = angles[block_id]
            after = ((before + delta + math.pi) % (2 * math.pi)) - math.pi
            angles[block_id] = after
            events.append({"sequence": sequence, "kind": "rotate", "block_id": block_id, "input_source": "rotate_button" if interaction == "simplified" else "block_right_click", "delta": delta, "angle_before": before, "angle_after": after})
        sequence += 1
        events.append({"sequence": sequence, "kind": "place", "block_id": block_id, "input_source": "socket_click" if interaction == "simplified" else "direct_drag", "drop": list(block["target"]), "settled": list(block["target"]), "angle": angles[block_id], "support": block["support"], "accepted": True})
    return {"mechanic_id": truth["mechanic_id"], "task_id": truth["task_id"], "challenge_id": truth["challenge_id"], "interaction_mode": interaction, "events": events, "completed": True}


def test_generator_is_deterministic_and_covers_profiles():
    generator = load(GENERATOR_PATH, "little_planet_mason_test_generator")
    seen = set()
    for level in range(1, 6):
        for interaction in ("full", "simplified"):
            public, truth = generator.generate(task_with_condition(level, interaction), "fuzz-seed-17")
            again, again_truth = generator.generate(task_with_condition(level, interaction), "fuzz-seed-17")
            assert public == again
            assert truth == again_truth
            assert public["blocks"] == truth["blocks"]
            assert len(truth["solution_order"]) == public["requirements"]["block_count"]
            assert len(public["blocks"]) == public["requirements"]["block_count"] + public["control_condition"]["difficulty_parameters"]["decoy_count"]
            seen.add((level, interaction, truth["challenge_id"]))
    assert len(seen) == 10


def test_full_and_simplified_share_the_same_world():
    generator = load(GENERATOR_PATH, "little_planet_mason_pair_generator")
    full_public, full_truth = generator.generate(task_with_condition(4, "full"), "same-world-seed")
    simple_public, simple_truth = generator.generate(task_with_condition(4, "simplified"), "same-world-seed")
    assert full_public["blocks"] == simple_public["blocks"]
    assert full_truth["blocks"] == simple_truth["blocks"]
    assert full_truth["solution_order"] == simple_truth["solution_order"]
    assert full_truth["control_condition"]["interaction"] == "full"
    assert simple_truth["control_condition"]["interaction"] == "simplified"


def test_independent_grader_accepts_oracle_and_rejects_wrong_surface():
    generator = load(GENERATOR_PATH, "little_planet_mason_grader_generator")
    grader = load(GRADER_PATH, "little_planet_mason_test_grader")
    for interaction in ("full", "simplified"):
        public, truth = generator.generate(task_with_condition(3, interaction), f"grade-{interaction}")
        payload = solution_payload(public, truth, interaction)
        assert grader.grade(payload, truth, public)["passed"] is True
        wrong = dict(payload)
        wrong["interaction_mode"] = "simplified" if interaction == "full" else "full"
        wrong["events"] = [dict(event, input_source=("socket_click" if event.get("kind") == "place" else event.get("input_source"))) for event in payload["events"]]
        assert grader.grade(wrong, truth, public)["passed"] is False


def test_grader_accepts_independent_planet_supports_but_rejects_false_settling():
    generator = load(GENERATOR_PATH, "little_planet_mason_order_generator")
    grader = load(GRADER_PATH, "little_planet_mason_order_grader")
    public, truth = generator.generate(task_with_condition(4, "full"), "order-seed")
    blocks = {str(block["id"]): block for block in truth["blocks"]}
    ring_zero = [block_id for block_id in truth["solution_order"] if blocks[block_id]["support"] == "planet"]
    ring_one = [block_id for block_id in truth["solution_order"] if blocks[block_id]["support"] != "planet"]
    alternate = list(reversed(ring_zero)) + list(reversed(ring_one))
    assert grader.grade(solution_payload(public, truth, "full", alternate), truth, public)["passed"] is True
    payload = solution_payload(public, truth, "full", alternate)
    first_place = next(event for event in payload["events"] if event["kind"] == "place")
    first_place["settled"] = [first_place["settled"][0] + 1.0, first_place["settled"][1]]
    assert grader.grade(payload, truth, public)["passed"] is False
