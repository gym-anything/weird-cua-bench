from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENV = BENCH / "environments/five_second_rule_env"
GENERATOR_PATH = BENCH / "shared_scripts/incubator_generators/five_second_rule.py"
GRADER_PATH = BENCH / "shared_runtime/server/incubator_graders/five_second_rule.py"
MATERIALIZER_PATH = BENCH / "tools/materialize_controlled_tasks.py"


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = _module("five_second_rule_generator", GENERATOR_PATH)
grader = _module("five_second_rule_grader", GRADER_PATH)
materializer = _module("five_second_rule_materializer", MATERIALIZER_PATH)


def _task() -> dict:
    return json.loads((ENV / "tasks/five_second_rule_seed_0001/task.json").read_text(encoding="utf-8"))


def _condition(level: int, interaction: str) -> dict:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    return {
        "difficulty": level,
        "interaction": interaction,
        "real_time": "live",
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
    }


def _generated(level: int = 4, interaction: str = "full", seed: str = "five-second-test"):
    task = _task()
    task["_control_condition"] = _condition(level, interaction)
    return generator.generate(task, seed)


def _token(round_spec: dict, token_id: str) -> dict:
    return next(item for item in round_spec["tokens"] if item["id"] == token_id)


def _position(token: dict, t: float) -> dict[str, float]:
    motion = token.get("motion")
    if not motion:
        return {"x": token["x"], "y": token["y"]}
    return {
        "x": motion["x0"] + motion["vx"] * t / 1000,
        "y": motion["y0"] + motion["amplitude"] * math.sin(t / motion["period_ms"] * 2 * math.pi + motion["phase"]),
    }


def _visible_relay_candidates(round_spec: dict) -> tuple[list[str], list[str]]:
    tokens = round_spec["tokens"]
    depth = round_spec["relay"]["relation_depth"]
    if depth < 2:
        first_label = round_spec["instruction"][0].removeprefix("FIRST TAP THE ").removesuffix(".")
        first_candidates = [
            token for token in tokens
            if f'{token["color"]} {token["shape"]}' == first_label
        ]
    else:
        relation = {
            2: "IMMEDIATELY LEFT OF",
            3: "DOWN-LEFT OF",
            4: "ON THE 45° DIAGONAL DOWN-LEFT OF",
        }[depth]
        anchor_label = (
            round_spec["instruction"][0]
            .removeprefix(f"FIRST TAP THE TOKEN {relation} THE ")
            .removesuffix(".")
        )
        anchors = [
            token for token in tokens
            if f'{token["color"]} {token["shape"]}' == anchor_label
        ]
        assert len(anchors) == 1
        anchor = anchors[0]
        if depth == 2:
            first_candidates = [
                token for token in tokens
                if token["x"] < anchor["x"] and token["y"] == anchor["y"]
            ]
        elif depth == 3:
            first_candidates = [
                token for token in tokens
                if token["x"] < anchor["x"] and token["y"] > anchor["y"]
            ]
        else:
            first_candidates = [
                token for token in tokens
                if token["x"] < anchor["x"]
                and token["y"] > anchor["y"]
                and abs((anchor["x"] - token["x"]) - (token["y"] - anchor["y"])) <= 1
            ]
    if depth == 0:
        second_label = round_spec["instruction"][1].removeprefix("THEN TAP THE ").removesuffix(".")
        second_candidates = [
            token for token in tokens
            if f'{token["color"]} {token["shape"]}' == second_label
        ]
    else:
        mark = (
            round_spec["instruction"][1]
            .removeprefix("THEN TAP THE OTHER TOKEN WITH ITS ")
            .removesuffix(" MARK.")
        )
        first_ids = {token["id"] for token in first_candidates}
        second_candidates = [
            token for token in tokens
            if token["id"] not in first_ids and token["mark"] == mark
        ]
    return (
        [token["id"] for token in first_candidates],
        [token["id"] for token in second_candidates],
    )


def _solution(public: dict, truth: dict, interaction: str) -> dict:
    sequence = 0
    records = []

    def event(data: dict) -> dict:
        nonlocal sequence
        sequence += 1
        return {"sequence": sequence, **data}

    sources = {
        "full": {"gate_tag": "direct_tag", "sync_hold": "direct_hold", "vector_flick": "direct_flick", "relay_pair": "direct_tap", "shutter_drop": "direct_drag"},
        "simplified": {"gate_tag": "proxy_tag", "sync_hold": "proxy_hold", "vector_flick": "proxy_flick", "relay_pair": "proxy_tap", "shutter_drop": "proxy_drop"},
    }[interaction]
    for spec in truth["rounds"]:
        family = spec["family"]
        events = []
        if family == "gate_tag":
            target_id = spec["predicate"]["target_id"]
            target = _token(spec, target_id)
            t = (spec["gate"]["x"] - target["motion"]["x0"]) / target["motion"]["vx"] * 1000
            data = {"type": "tag", "target_id": target_id, "t_ms": t, "input_source": sources[family]}
            if interaction == "full":
                data["point"] = _position(target, t)
            events.append(event(data))
        elif family == "sync_hold":
            target_id = spec["predicate"]["target_id"]
            data = {"type": "hold", "target_id": target_id, "start_ms": spec["cue"]["start_ms"], "end_ms": spec["cue"]["end_ms"], "input_source": sources[family]}
            if interaction == "full":
                target = _token(spec, target_id)
                data["start_point"] = {"x": target["x"], "y": target["y"]}
            events.append(event(data))
        elif family == "vector_flick":
            target_id = spec["predicate"]["target_id"]
            target = _token(spec, target_id)
            t = 1720
            data = {"type": "flick", "target_id": target_id, "t_ms": t, "input_source": sources[family]}
            direction = spec["flick"]["flick_direction"]
            if interaction == "full":
                vectors = {"NORTH": (0, -1), "EAST": (1, 0), "SOUTH": (0, 1), "WEST": (-1, 0)}
                dx, dy = vectors[direction]
                travel = spec["flick"]["min_travel_px"] + 12
                data["start_point"] = {"x": target["x"], "y": target["y"]}
                data["end_point"] = {"x": target["x"] + dx * travel, "y": target["y"] + dy * travel}
            else:
                data["direction"] = direction
            events.append(event(data))
        elif family == "relay_pair":
            for t, target_id in ((600, spec["predicate"]["first_id"]), (800, spec["predicate"]["second_id"])):
                data = {"type": "tap", "target_id": target_id, "t_ms": t, "input_source": sources[family]}
                if interaction == "full":
                    target = _token(spec, target_id)
                    data["point"] = {"x": target["x"], "y": target["y"]}
                events.append(event(data))
        else:
            target_id = spec["predicate"]["target_id"]
            bay_id = spec["predicate"]["bay_id"]
            target = _token(spec, target_id)
            bay = next(item for item in spec["bays"] if item["id"] == bay_id)
            data = {"type": "drop", "target_id": target_id, "bay_id": bay_id, "t_ms": 1580, "input_source": sources[family]}
            if interaction == "full":
                data["start_point"] = {"x": target["x"], "y": target["y"]}
                data["end_point"] = {"x": bay["x"], "y": bay["y"]}
            events.append(event(data))
        records.append({"round_id": spec["id"], "family": family, "events": events})
    return {
        "mechanic_id": "five_second_rule",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "world_fingerprint": truth["world_fingerprint"],
        "interaction_mode": interaction,
        "rounds": records,
        "completed": True,
    }


def test_source_metadata_and_environment_contract() -> None:
    task = _task()
    assert task["name"] == "Five-Second Rule"
    assert task["metadata"]["source_anchors"] == ["CAPW-052", "TRV-110"]
    assert "Developer Tools" in task["natural_language"]
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert controls["real_time"] == {"play_time_seconds": 90, "observation_window_ms": 600, "frames_per_observation": 6}
    assert {controls["difficulty"][str(level)]["parameters"]["round_duration_ms"] for level in range(1, 6)} == {5000}


def test_all_profiles_generate_five_two_line_rounds_and_are_reachable() -> None:
    fingerprints = set()
    for level in range(1, 6):
        for interaction in ("simplified", "full"):
            for seed_index in range(12):
                public, truth = _generated(level, interaction, f"reach-{level}-{seed_index}")
                assert len(public["rounds"]) == 5
                assert all(len(item["instruction"]) == 2 and item["duration_ms"] == 5000 for item in public["rounds"])
                decision = grader.grade(_solution(public, truth, interaction), truth, public)
                assert decision["passed"] is True, decision
            fingerprints.add(public["world_fingerprint"])
    assert len(fingerprints) == 5


def test_parameter_key_order_does_not_change_the_generated_world() -> None:
    task = _task()
    condition = _condition(4, "full")
    task["_control_condition"] = condition
    public, truth = generator.generate(task, "canonical-parameter-order")
    reordered = copy.deepcopy(task)
    reordered["_control_condition"]["difficulty_parameters"] = dict(
        reversed(list(condition["difficulty_parameters"].items()))
    )
    reordered_public, reordered_truth = generator.generate(
        reordered, "canonical-parameter-order"
    )
    assert reordered_public == public
    assert reordered_truth == truth


def test_relay_visible_answers_are_unique_and_action_boxes_never_overlap() -> None:
    for level in range(1, 6):
        for seed_index in range(200):
            public, _truth = _generated(level, "full", f"relay-visible-{level}-{seed_index}")
            relay = next(item for item in public["rounds"] if item["family"] == "relay_pair")
            first_candidates, second_candidates = _visible_relay_candidates(relay)
            assert first_candidates == [relay["predicate"]["first_id"]]
            assert second_candidates == [relay["predicate"]["second_id"]]
            for index, left in enumerate(relay["tokens"]):
                for right in relay["tokens"][index + 1:]:
                    dx = abs(left["x"] - right["x"])
                    dy = abs(left["y"] - right["y"])
                    assert not (dx < 86 and dy < 92), (level, left, right)


def test_interaction_pair_preserves_world_and_rejects_cross_mode_transcript() -> None:
    for level in range(1, 6):
        public_full, truth_full = _generated(level, "full", f"same-world-{level}")
        public_simple, truth_simple = _generated(level, "simplified", f"same-world-{level}")
        assert public_full["world_fingerprint"] == public_simple["world_fingerprint"]
        assert public_full["rounds"] == public_simple["rounds"]
        payload = _solution(public_full, truth_full, "full")
        payload["interaction_mode"] = "simplified"
        assert grader.grade(payload, truth_full, public_full)["passed"] is False


def test_replay_rejects_stale_identity_forged_time_and_wrong_geometry() -> None:
    public, truth = _generated(4, "full", "negative-contract")
    valid = _solution(public, truth, "full")
    assert grader.grade(valid, truth, public)["passed"] is True

    stale = copy.deepcopy(valid)
    stale["challenge_id"] = "stale"
    assert grader.grade(stale, truth, public)["passed"] is False

    gate_record = next(item for item in valid["rounds"] if item["family"] == "gate_tag")
    forged_time = copy.deepcopy(valid)
    next(item for item in forged_time["rounds"] if item["family"] == "gate_tag")["events"][0]["t_ms"] = 0
    assert grader.grade(forged_time, truth, public)["passed"] is False

    forged_point = copy.deepcopy(valid)
    next(item for item in forged_point["rounds"] if item["family"] == "gate_tag")["events"][0]["point"] = {"x": 0, "y": 0}
    assert grader.grade(forged_point, truth, public)["passed"] is False
    assert gate_record["events"][0]["point"] != {"x": 0, "y": 0}


def test_materializer_writes_all_ten_task_conditions(tmp_path: Path) -> None:
    written = materializer.materialize_environment(ENV, tmp_path)
    assert len(written) == 10
    for level in range(1, 6):
        for interaction in ("simplified", "full"):
            task_dir = tmp_path / "five_second_rule_env/tasks" / f"five_second_rule_d{level}_{interaction}_seed_0001"
            task = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
            condition = task["metadata"]["control_condition"]
            assert condition["difficulty"] == level
            assert condition["interaction"] == interaction
            assert "visible task-page controls" in task["natural_language"]
