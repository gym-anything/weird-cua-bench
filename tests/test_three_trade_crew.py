from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
MECHANIC = "three_trade_crew"
TASK_PATH = BENCH / "environments" / f"{MECHANIC}_env" / "tasks" / f"{MECHANIC}_seed_0001" / "task.json"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = load(BENCH / "shared_scripts" / "incubator_generators" / f"{MECHANIC}.py", "three_trade_generator_test")
GRADER = load(BENCH / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py", "three_trade_grader_test")
TASK = json.loads(TASK_PATH.read_text(encoding="utf-8"))


def generated(level: int, interaction: str = "full", real_time: str = "live", seed: str | None = None):
    task = copy.deepcopy(TASK)
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": GENERATOR._profile(level),
    }
    return GENERATOR.generate(task, seed or f"three-trade-test-{level}")


def solved_payload(public: dict, truth: dict, interaction: str) -> dict:
    actions = truth["solution_actions"]
    events = []
    selections = []
    selected = None
    for sequence, action in enumerate(actions, start=1):
        if action["worker_id"] != selected:
            selected = action["worker_id"]
            selections.append({
                "worker_id": selected,
                "input_source": "keyboard_select" if interaction == "full" else "worker_card",
                "movement_index": sequence - 1,
            })
        event = copy.deepcopy(action)
        event["sequence"] = sequence
        event["input_source"] = "keyboard_move" if interaction == "full" else "direction_button"
        events.append(event)
    final = GENERATOR.replay_solution(truth["initial_board"], actions)
    return {
        "mechanic_id": MECHANIC,
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "interaction_mode": interaction,
        "selection_events": selections,
        "events": events,
        "final_board": {"workers": final["workers"], "crates": final["crates"]},
        "completed": True,
    }


def test_all_difficulty_profiles_have_independent_solved_routes():
    for level in range(1, 6):
        for interaction in ("full", "simplified"):
            public, truth = generated(level, interaction)
            assert public["parameters"] == GENERATOR._profile(level)
            assert len(truth["solution_actions"]) <= public["parameters"]["action_budget"]
            assert "solution_actions" not in public
            decision = GRADER.grade(solved_payload(public, truth, interaction), truth, public)
            assert decision["passed"], (level, interaction, decision)


def test_seeded_worlds_are_structural_variants_and_each_route_still_solves():
    worlds = []
    routes = []
    layouts = set()
    walls_by_layout = {}
    for index in range(8):
        public, truth = generated(4, seed=f"three-trade-variant-{index}")
        worlds.append(json.dumps(public["board"], sort_keys=True))
        routes.append(tuple((item["worker_id"], item["direction"]) for item in truth["solution_actions"]))
        layouts.add(public["board"]["variant_layout"])
        walls_by_layout.setdefault(public["board"]["variant_layout"], json.dumps(public["board"]["walls"], sort_keys=True))
        decision = GRADER.grade(solved_payload(public, truth, "full"), truth, public)
        assert decision["passed"], (index, decision)
    assert len(set(worlds)) >= 2
    assert layouts == {"baseline-lanes", "staggered-lanes"}
    assert len(set(routes)) >= 2
    assert len(set(walls_by_layout.values())) == 2


def test_level_order_has_real_gate_and_budget_changes():
    shared_public, _ = generated(3)
    sequential_public, sequential_truth = generated(4)
    hardest_public, hardest_truth = generated(5)
    assert shared_public["parameters"]["gate_scheme"] == "shared"
    assert sequential_public["parameters"]["gate_scheme"] == "sequential"
    assert [door["switch_id"] for door in shared_public["board"]["doors"]] == ["switch-yellow", "switch-yellow"]
    assert [door["switch_id"] for door in sequential_public["board"]["doors"]] == ["switch-yellow", "switch-purple"]
    assert len(sequential_truth["solution_actions"]) <= sequential_public["parameters"]["action_budget"]
    assert len(hardest_truth["solution_actions"]) <= hardest_public["parameters"]["action_budget"]
    assert hardest_public["parameters"]["door_count"] == 3
    assert hardest_public["parameters"]["top_goal_column"] > sequential_public["parameters"]["top_goal_column"]


def test_interaction_mode_is_bound_to_the_transcript():
    public, truth = generated(4, "full")
    payload = solved_payload(public, truth, "full")
    assert GRADER.grade(payload, truth, public)["passed"] is True
    forged = copy.deepcopy(payload)
    forged["interaction_mode"] = "simplified"
    assert GRADER.grade(forged, truth, public)["passed"] is False
    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "stale-challenge"
    assert GRADER.grade(stale, truth, public)["passed"] is False


def test_public_metadata_and_registries_are_present():
    controls = json.loads((BENCH / "environments" / f"{MECHANIC}_env" / "controls.json").read_text(encoding="utf-8"))
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert set(controls["difficulty"]) == {"1", "2", "3", "4", "5"}
    assert controls["interaction"]["full"]["implemented"] is True
    assert controls["interaction"]["simplified"]["implemented"] is True
    assert controls["real_time"] == {"play_time_seconds": 180, "observation_window_ms": 0, "frames_per_observation": 1}

    manifest = json.loads((BENCH / "benchmark_manifest.json").read_text(encoding="utf-8"))
    assert f"{MECHANIC}_env" in manifest["environments"]
    real_time = json.loads((BENCH / "real_time.json").read_text(encoding="utf-8"))
    assert real_time["environments"][MECHANIC] == controls["real_time"]
    split = json.loads((BENCH / "splits" / f"{MECHANIC}_split.json").read_text(encoding="utf-8"))
    assert len(split["variations_tasks"]) == 20
    provenance = json.loads((BENCH / "shared_runtime" / "assets" / "provenance" / f"{MECHANIC}_v0.json").read_text(encoding="utf-8"))
    assert provenance["source_anchors"] == ["IND-010"]
    assert provenance["mechanic_id"] == MECHANIC
    assert json.loads(TASK_PATH.read_text(encoding="utf-8"))["metadata"]["capabilities"] == ["visual understanding: 2D", "reasoning and planning"]
