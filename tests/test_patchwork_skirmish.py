from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "weird_captcha_gym/shared_scripts/incubator_generators/patchwork_skirmish.py"
GRADER_PATH = ROOT / "weird_captcha_gym/shared_runtime/server/incubator_graders/patchwork_skirmish.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = load_module("patchwork_test_generator", GENERATOR_PATH)
grader = load_module("patchwork_test_grader", GRADER_PATH)


def condition(level: int, interaction: str = "full", real_time: str = "live") -> dict:
    return {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(generator.PROFILES[level]),
    }


def generated(level: int = 4, interaction: str = "full", real_time: str = "live", seed: str = "patchwork-test"):
    return generator.generate(
        {"id": "patchwork_skirmish_test@0.1", "_control_condition": condition(level, interaction, real_time)},
        seed,
    )


def solved_payload(public_state: dict, ground_truth: dict, interaction: str = "full") -> dict:
    events = grader.plan(ground_truth["world"])
    if interaction == "simplified":
        events = [
            {**event, "input_source": "turn_button" if event["type"] == "end_turn" else "command_panel"}
            for event in events
        ]
    state = grader.initial_state(ground_truth["world"])
    for event in events:
        grader.apply_event(state, ground_truth["world"], event)
    return {
        "mechanic_id": "patchwork_skirmish",
        "task_id": ground_truth["task_id"],
        "challenge_id": ground_truth["challenge_id"],
        "events": events,
        "final_state": grader.summary(state),
    }


def test_all_ten_profiles_replay_and_pair_worlds():
    for level in range(1, 6):
        full, full_truth = generated(level, "full", seed=f"pair-{level}")
        simple, simple_truth = generated(level, "simplified", seed=f"pair-{level}")
        assert full["world"] == simple["world"]
        assert full_truth["world"] == simple_truth["world"]
        assert grader.grade(solved_payload(full, full_truth), full_truth, full)["passed"] is True
        assert grader.grade(solved_payload(simple, simple_truth, "simplified"), simple_truth, simple)["passed"] is True


def test_oracle_survives_a_seed_that_requires_response_aware_planning():
    public, truth = generated(2, "full", seed="stress-2-538")
    result = solved_payload(public, truth)
    assert grader.grade(result, truth, public)["passed"] is True


def test_seeded_footprints_are_connected_in_bounds_and_disjoint():
    for level in range(1, 6):
        for seed_index in range(20):
            public, truth = generated(level, seed=f"geometry-{level}-{seed_index}")
            world = truth["world"]
            seen: set[tuple[int, int]] = set()
            for unit in world["units"]:
                cells = {tuple(cell) for cell in unit["cells"]}
                assert len(cells) == unit["area"]
                assert all(0 <= row < world["height"] and 0 <= col < world["width"] for row, col in cells)
                assert len(cells & seen) == 0
                seen |= cells
                reached = {next(iter(cells))}
                changed = True
                while changed:
                    changed = False
                    for row, col in cells - reached:
                        if any((row + dr, col + dc) in reached for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))):
                            reached.add((row, col))
                            changed = True
                assert reached == cells


def test_controls_declare_baseline_and_all_materialized_axes():
    controls = json.loads((ROOT / "weird_captcha_gym/environments/patchwork_skirmish_env/controls.json").read_text())
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert set(controls["difficulty"]) == {"1", "2", "3", "4", "5"}
    assert controls["interaction"]["simplified"]["implemented"] is True
    assert controls["interaction"]["full"]["implemented"] is True
    assert controls["real_time"] == {"play_time_seconds": 180, "observation_window_ms": 0, "frames_per_observation": 1}


def test_grader_rejects_wrong_surface_stale_challenge_and_tampered_final_state():
    public, truth = generated(4, "simplified", seed="rejection")
    payload = solved_payload(public, truth, "simplified")
    first_non_turn = next(index for index, event in enumerate(payload["events"]) if event["type"] != "end_turn")
    wrong_surface = copy.deepcopy(payload)
    wrong_surface["events"][first_non_turn]["input_source"] = "board_direct"
    assert grader.grade(wrong_surface, truth, public)["passed"] is False

    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "stale-challenge"
    assert grader.grade(stale, truth, public)["passed"] is False

    tampered = copy.deepcopy(payload)
    unit_id = next(unit_id for unit_id, state in tampered["final_state"]["units"].items() if state["cells"])
    tampered["final_state"]["units"][unit_id]["cells"] = []
    assert grader.grade(tampered, truth, public)["passed"] is False


def test_base_task_is_the_uncontrolled_reference_configuration():
    task = json.loads((ROOT / "weird_captcha_gym/environments/patchwork_skirmish_env/tasks/patchwork_skirmish_seed_0001/task.json").read_text())
    public, truth = generator.generate(task, "reference-seed")
    controlled, controlled_truth = generated(4, "full", seed="reference-seed")
    assert public["world"] == controlled["world"]
    assert truth["world"] == controlled_truth["world"]
    assert task["metadata"]["source_anchors"] == ["TRW-033"]


def test_exported_verifier_delegates_to_authoritative_grader(tmp_path):
    public, truth = generated(4, "full", seed="verifier")
    result = solved_payload(public, truth)
    exported_path = tmp_path / "task_result.json"
    exported_path.write_text(json.dumps({"result": result, "public_state": public, "ground_truth": truth}))

    def copy_from_env(_source: str, destination: str):
        Path(destination).write_bytes(exported_path.read_bytes())

    verifier_path = ROOT / "weird_captcha_gym/environments/patchwork_skirmish_env/tasks/patchwork_skirmish_seed_0001/verifier.py"
    verifier = load_module("patchwork_task_verifier", verifier_path)
    outcome = verifier.verify_task(env_info={"copy_from_env": copy_from_env})
    assert outcome["passed"] is True
    assert outcome["score"] == 100
