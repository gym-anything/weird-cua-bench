from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENV = BENCH / "environments" / "terrarium_order_of_operations_env"
GENERATOR_PATH = BENCH / "shared_scripts" / "incubator_generators" / "terrarium_order_of_operations.py"
GRADER_PATH = BENCH / "shared_runtime" / "server" / "incubator_graders" / "terrarium_order_of_operations.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("terrarium_order_generator_test", GENERATOR_PATH)
GRADER = _load("terrarium_order_grader_test", GRADER_PATH)


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/terrarium_order_of_operations_seed_0001/task.json").read_text(encoding="utf-8"))
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
    }
    return task


def _replay(solution: list[str], order: list[str], echo_budget: int):
    predecessor = {solution[index]: (solution[index - 1] if index else None) for index in range(len(solution))}
    state = {module_id: {"active": False, "scarred": False, "stage": 0} for module_id in solution}
    results = []
    echoes = 0
    for sequence, module_id in enumerate(order, 1):
        required = predecessor[module_id]
        healthy = required is None or (state[required]["active"] and not state[required]["scarred"])
        scarred = not healthy
        state[module_id] = {"active": True, "scarred": scarred, "stage": 0}
        cascade = []
        for candidate in solution:
            current = state[candidate]
            if current["active"] and not current["scarred"]:
                before = current["stage"]
                current["stage"] = min(2, before + 1)
                if before != current["stage"]:
                    cascade.append({"module_id": candidate, "before": before, "after": current["stage"]})
        clue = bool(scarred and echoes < echo_budget)
        echo_id = required if clue else None
        if clue:
            echoes += 1
        final_cascade = []
        if sequence == len(solution):
            for candidate in solution:
                current = state[candidate]
                if current["active"] and not current["scarred"]:
                    before = current["stage"]
                    current["stage"] = 3
                    if before != 3:
                        final_cascade.append({"module_id": candidate, "before": before, "after": 3})
        results.append({"scarred": scarred, "clue_shown": clue, "echo_module_id": echo_id, "cascade": cascade, "final_cascade": final_cascade})
    return results, state


def _payload(public: dict, truth: dict, interaction: str, order: list[str] | None = None) -> dict:
    order = list(order or truth["solution_order"])
    results, final_state = _replay(truth["solution_order"], order, int(truth["parameters"]["echo_budget"]))
    events = []
    for index, (module_id, result) in enumerate(zip(order, results), 1):
        event = {
            "sequence": index,
            "type": "inoculate",
            "module_id": module_id,
            "input_source": "direct_capsule_drag" if interaction == "full" else "tray_inoculate_button",
            "result": result,
        }
        if interaction == "full":
            event["gesture"] = {"start_u": .5, "start_v": .5, "end_u": .5, "end_v": .5, "travel_px": 240.0, "sample_count": 10}
        events.append(event)
    all_max = all(state["active"] and not state["scarred"] and state["stage"] == 3 for state in final_state.values())
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "order": order,
        "final_state": final_state,
        "completed": all_max,
    }


def test_all_ten_conditions_share_world_and_grade() -> None:
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(_task(level, interaction), "matrix-world")
            decision = GRADER.grade(_payload(public, truth, interaction), truth, public)
            assert decision["passed"] is True, (level, interaction, decision)
            worlds.append(public["terrarium"])
        assert worlds[0] == worlds[1]


def test_hundred_seed_generation_is_deterministic_and_solvable() -> None:
    for level in range(1, 6):
        seen_orders = set()
        for seed_index in range(100):
            seed = f"terrarium-seed-{level}-{seed_index}"
            public, truth = GENERATOR.generate(_task(level, "full"), seed)
            public_again, truth_again = GENERATOR.generate(_task(level, "full"), seed)
            assert public == public_again
            assert truth == truth_again
            assert GRADER.grade(_payload(public, truth, "full"), truth, public)["passed"] is True
            seen_orders.add(tuple(truth["solution_order"]))
        assert len(seen_orders) >= 80


def test_wrong_order_stunts_habitats_and_cannot_pass() -> None:
    public, truth = GENERATOR.generate(_task(3, "full"), "wrong-order")
    wrong = list(reversed(truth["solution_order"]))
    payload = _payload(public, truth, "full", wrong)
    decision = GRADER.grade(payload, truth, public)
    assert decision["passed"] is False
    assert sum(1 for state in payload["final_state"].values() if state["scarred"]) >= len(wrong) - 1
    assert any(event["result"]["clue_shown"] for event in payload["events"])


def test_stale_identity_wrong_surface_duplicate_and_forged_cascade_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(3, "full"), "negative-contract")
    payload = _payload(public, truth, "full")
    payload["challenge_id"] = "stale"
    assert GRADER.grade(payload, truth, public)["passed"] is False

    payload = _payload(public, truth, "full")
    payload["events"][0]["input_source"] = "tray_inoculate_button"
    assert "input surface" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full")
    payload["events"][1]["module_id"] = payload["events"][0]["module_id"]
    assert "repeated" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full")
    payload["events"][0]["gesture"]["travel_px"] = 0
    assert "stationary" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full")
    payload["events"][0]["gesture"]["sample_count"] = 0
    assert "pointer sample" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full")
    payload["events"][0]["result"]["cascade"][0]["after"] = 99
    assert "cascade claim" in GRADER.grade(payload, truth, public)["feedback"]


def test_sparse_full_drag_is_accepted_by_the_grader() -> None:
    public, truth = GENERATOR.generate(_task(3, "full"), "sparse-drag")
    payload = _payload(public, truth, "full")
    for event in payload["events"]:
        event["gesture"]["sample_count"] = 1
    assert GRADER.grade(payload, truth, public)["passed"] is True


def test_full_drag_visible_edges_are_accepted_and_outside_geometry_is_rejected() -> None:
    public, truth = GENERATOR.generate(_task(3, "full"), "visible-edge-drag")
    payload = _payload(public, truth, "full")
    edge_points = [
        (0.0, 0.0, 0.5, 0.5),
        (1.0, 1.0, 0.5, 0.5),
        (0.5, 0.5, 0.0, 0.0),
        (0.5, 0.5, 1.0, 1.0),
        (0.0, 1.0, 1.0, 0.0),
        (1.0, 0.0, 0.0, 1.0),
    ]
    for event, (start_u, start_v, end_u, end_v) in zip(payload["events"], edge_points, strict=True):
        event["gesture"].update({
            "start_u": start_u,
            "start_v": start_v,
            "end_u": end_u,
            "end_v": end_v,
        })
    assert GRADER.grade(payload, truth, public)["passed"] is True

    for field, value in (("start_u", -0.001), ("start_v", 1.001), ("end_u", -0.001), ("end_v", 1.001)):
        outside = _payload(public, truth, "full")
        outside["events"][0]["gesture"][field] = value
        decision = GRADER.grade(outside, truth, public)
        assert decision["passed"] is False
        assert "visible" in decision["feedback"]


def test_live_and_paused_preserve_the_same_decision_world() -> None:
    live, _ = GENERATOR.generate(_task(4, "full", "live"), "time-equivalence")
    paused, _ = GENERATOR.generate(_task(4, "full", "paused"), "time-equivalence")
    assert live["terrarium"] == paused["terrarium"]
    assert live["parameters"] == paused["parameters"]
    assert live["control_condition"]["real_time"] == "live"
    assert paused["control_condition"]["real_time"] == "paused"


def test_every_difficulty_clears_the_action_lock_within_one_observation_window() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    env = json.loads((ENV / "env.json").read_text(encoding="utf-8"))
    observation_window_ms = env["runner_options"]["observation_window_ms"]
    cascade_durations = [
        controls["difficulty"][str(level)]["parameters"]["cascade_ms"]
        for level in range(1, 6)
    ]

    assert cascade_durations == [900, 900, 900, 820, 760]
    assert all(duration <= observation_window_ms for duration in cascade_durations)
    assert controls["difficulty"]["3"]["parameters"] == {
        "module_count": 6,
        "echo_budget": 2,
        "echo_mode": "transient",
        "stage_mode": "rings",
        "cascade_ms": 900,
    }


def test_baseline_sources_controls_and_registration() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    env = json.loads((ENV / "env.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/terrarium_order_of_operations_seed_0001/task.json").read_text(encoding="utf-8"))
    split = json.loads((BENCH / "splits/terrarium_order_of_operations_split.json").read_text(encoding="utf-8"))
    manifest = json.loads((BENCH / "benchmark_manifest.json").read_text(encoding="utf-8"))
    real_time = json.loads((BENCH / "real_time.json").read_text(encoding="utf-8"))["environments"]
    assert controls["baseline"] == {"difficulty": 3, "interaction": "full", "real_time": "live"}
    assert [controls["difficulty"][str(level)]["parameters"]["module_count"] for level in range(1, 6)] == [4, 5, 6, 7, 8]
    assert [controls["difficulty"][str(level)]["parameters"]["echo_budget"] for level in range(1, 6)] == [4, 5, 2, 1, 1]
    assert env["runner_options"] == {"observation_window_ms": 900, "frames_per_observation": 6, "play_time_seconds": 240}
    assert task["name"] == "Terrarium Order of Operations"
    assert task["difficulty"] == "medium"
    assert task["metadata"]["source_anchors"] == ["WEB-203"]
    assert task["metadata"]["status"] == "prototype_visual_candidate"
    assert len(split["variations_tasks"]) == 20
    assert manifest["environments"].count("terrarium_order_of_operations_env") == 1
    assert real_time["terrarium_order_of_operations"] == env["runner_options"]


def test_browser_module_exposes_distinct_bound_input_surfaces() -> None:
    source = (BENCH / "shared_runtime/app/mechanics/terrarium_order_of_operations.js").read_text(encoding="utf-8")
    styles = (BENCH / "shared_runtime/app/mechanics/terrarium_order_of_operations.css").read_text(encoding="utf-8")
    assert "direct_capsule_drag" in source
    assert "tray_inoculate_button" in source
    assert "RETRY SAME WORLD" in source
    assert "runtime_causal_links" in source
    assert "proof.sample_count >= 1" in source
    assert 'model.parameters.echo_mode !== "sigil"' in source
    assert ".too-root-network line { stroke: transparent;" in styles
    assert ".too-root-network line.is-alive { stroke:" in styles
