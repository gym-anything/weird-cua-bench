from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENV = BENCH / "environments" / "twin_groove_seal_env"
TASK = json.loads(
    (ENV / "tasks" / "twin_groove_seal_seed_0001" / "task.json").read_text(
        encoding="utf-8"
    )
)
CONTROLS = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load(
    BENCH / "shared_scripts" / "incubator_generators" / "twin_groove_seal.py",
    "twin_groove_seal_test_generator",
)
GRADER = _load(
    BENCH / "shared_runtime" / "server" / "incubator_graders" / "twin_groove_seal.py",
    "twin_groove_seal_test_grader",
)


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    task = copy.deepcopy(TASK)
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(
            CONTROLS["difficulty"][str(level)]["parameters"]
        ),
    }
    return task


def _solved_payload(public: dict, truth: dict) -> dict:
    payload = GRADER.cheat(public, truth)
    payload.update({key: truth[key] for key in ("mechanic_id", "task_id", "challenge_id")})
    return payload


def _without_control_condition(value):
    if isinstance(value, dict):
        return {
            key: _without_control_condition(item)
            for key, item in value.items()
            if key != "control_condition"
        }
    if isinstance(value, list):
        return [_without_control_condition(item) for item in value]
    return value


def test_all_difficulty_interaction_pairs_replay_and_live_paused_parity() -> None:
    for level in range(1, 6):
        for interaction in ("simplified", "full"):
            live, live_truth = GENERATOR.generate(
                _task(level, interaction, "live"), f"matrix-{level}-{interaction}"
            )
            paused, paused_truth = GENERATOR.generate(
                _task(level, interaction, "paused"), f"matrix-{level}-{interaction}"
            )
            live_world = copy.deepcopy(live)
            paused_world = copy.deepcopy(paused)
            live_world["control_condition"].pop("real_time")
            paused_world["control_condition"].pop("real_time")
            live_truth_world = copy.deepcopy(live_truth)
            paused_truth_world = copy.deepcopy(paused_truth)
            live_truth_world["control_condition"].pop("real_time")
            paused_truth_world["control_condition"].pop("real_time")
            assert live_world == paused_world
            assert live_truth_world == paused_truth_world
            assert live["control_condition"]["real_time"] == "live"
            assert paused["control_condition"]["real_time"] == "paused"
            result = GRADER.grade(_solved_payload(live, live_truth), live_truth, live)
            assert result["passed"] is True, (level, interaction, result)


def test_same_seed_interaction_pair_shares_world_and_goal() -> None:
    for level in range(1, 6):
        full, full_truth = GENERATOR.generate(_task(level, "full"), f"same-seed-pair-{level}")
        simplified, simplified_truth = GENERATOR.generate(
            _task(level, "simplified"), f"same-seed-pair-{level}"
        )
        assert _without_control_condition(full) == _without_control_condition(simplified)
        assert _without_control_condition(full_truth) == _without_control_condition(simplified_truth)
        assert full["control_condition"]["interaction"] == "full"
        assert simplified["control_condition"]["interaction"] == "simplified"


def test_wrong_surface_and_incomplete_release_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(3, "full"), "negative-transcript")
    wrong_surface = _solved_payload(public, truth)
    wrong_surface["actions"][0]["input_source"] = "proxy_controls"
    assert GRADER.grade(wrong_surface, truth, public)["passed"] is False

    incomplete = {
        "mechanic_id": truth["mechanic_id"],
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "actions": [
            {
                "sequence": 1,
                "type": "release",
                "input_source": "release_button",
                "before": truth["start"],
                "after": truth["start"],
            }
        ],
        "final_state": truth["start"],
        "completed": False,
    }
    assert GRADER.grade(incomplete, truth, public)["passed"] is False


def test_controls_registration_and_source_anchor() -> None:
    assert CONTROLS["baseline"] == {
        "difficulty": 3,
        "interaction": "full",
        "real_time": "live",
    }
    assert CONTROLS["real_time"] == {
        "play_time_seconds": 180,
        "observation_window_ms": 0,
        "frames_per_observation": 1,
    }
    assert CONTROLS["interaction"]["simplified"]["implemented"] is True
    assert CONTROLS["interaction"]["full"]["implemented"] is True
    assert "TRP-201" in TASK["metadata"]["source_anchors"]
    manifest = json.loads((BENCH / "benchmark_manifest.json").read_text(encoding="utf-8"))
    assert "twin_groove_seal_env" in manifest["environments"]
    real_time = json.loads((BENCH / "real_time.json").read_text(encoding="utf-8"))
    assert real_time["environments"]["twin_groove_seal"] == CONTROLS["real_time"]


def test_nonfinite_trajectory_states_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(3, "full"), "finite-state-contract")
    for value in (float("nan"), float("inf"), float("-inf"), "NaN", "Infinity"):
        for field in ("before", "after", "final_state"):
            for component in (0, 1):
                payload = copy.deepcopy(_solved_payload(public, truth))
                state = payload[field] if field == "final_state" else payload["actions"][0][field]
                state["rear"][component] = value
                assert GRADER.grade(payload, truth, public)["passed"] is False, (value, field, component)


def test_rigid_link_length_is_preserved_from_start_through_solution() -> None:
    for level in range(1, 6):
        for seed in range(5):
            public, truth = GENERATOR.generate(_task(level, "full"), f"rigid-link-{seed}")
            for state in [public["start"], *truth["solution_states"]]:
                distance = math.dist(*GENERATOR._state_points(state))
                assert math.isclose(distance, public["shoe_length"], abs_tol=0.001), (level, seed, distance)
            decision = GRADER.grade(_solved_payload(public, truth), truth, public)
            assert decision["passed"], (level, seed, decision)
