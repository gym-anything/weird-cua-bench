from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "weird_captcha_gym" / "environments" / "einstein_loop_env"
GENERATOR_PATH = ROOT / "weird_captcha_gym" / "shared_scripts" / "incubator_generators" / "einstein_loop.py"
GRADER_PATH = ROOT / "weird_captcha_gym" / "shared_runtime" / "server" / "incubator_graders" / "einstein_loop.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("einstein_loop_generator_test", GENERATOR_PATH)
GRADER = _load("einstein_loop_grader_test", GRADER_PATH)


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/einstein_loop_seed_0001/task.json").read_text(encoding="utf-8"))
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
    }
    return task


def _ordered_cycle(public: dict, truth: dict) -> tuple[list[str], list[str]]:
    solution = set(truth["solution_edge_ids"])
    graph: dict[str, list[tuple[str, str]]] = {}
    for edge in public["puzzle"]["edges"]:
        if edge["id"] in solution:
            start, end = edge["vertices"]
            graph.setdefault(start, []).append((end, edge["id"]))
            graph.setdefault(end, []).append((start, edge["id"]))
    start = min(graph, key=lambda value: int(value[1:]))
    vertices = [start]
    edges = []
    previous = None
    current = start
    while True:
        following, edge_id = next(item for item in graph[current] if item[0] != previous)
        vertices.append(following)
        edges.append(edge_id)
        previous, current = current, following
        if current == start:
            break
    assert set(edges) == solution
    return vertices, edges


def _payload(public: dict, truth: dict, interaction: str) -> dict:
    if interaction == "simplified":
        events = [
            {
                "sequence": index,
                "type": "edge_update",
                "mode": "loop",
                "input_source": "edge_proxy_button",
                "edges": [{"id": edge_id, "before": 0, "after": 1}],
            }
            for index, edge_id in enumerate(truth["solution_edge_ids"], 1)
        ]
    else:
        vertices, edges = _ordered_cycle(public, truth)
        point_map = {vertex["id"]: (vertex["x"], vertex["y"]) for vertex in public["puzzle"]["vertices"]}
        travel = sum(math.dist(point_map[left], point_map[right]) for left, right in zip(vertices, vertices[1:]))
        events = [{
            "sequence": 1,
            "type": "edge_update",
            "mode": "loop",
            "input_source": "direct_edge_drag",
            "edges": [{"id": edge_id, "before": 0, "after": 1} for edge_id in edges],
            "gesture": {
                "start_vertex_id": vertices[0],
                "end_vertex_id": vertices[-1],
                "travel_px": round(travel, 3),
                "sample_count": len(edges) + 1,
            },
        }]
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "final_loop_edge_ids": sorted(truth["solution_edge_ids"], key=lambda value: int(value[1:])),
        "final_crossed_edge_ids": [],
        "completed": True,
    }


def test_all_ten_conditions_share_world_across_interactions_and_grade() -> None:
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(_task(level, interaction), f"same-world-{level}")
            decision = GRADER.grade(_payload(public, truth, interaction), truth, public)
            assert decision["passed"] is True, (level, interaction, decision)
            worlds.append(public["puzzle"])
        assert worlds[0] == worlds[1]


def test_profiles_generate_congruent_connected_unique_hat_puzzles() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    for level in range(1, 6):
        parameters = controls["difficulty"][str(level)]["parameters"]
        fingerprints = set()
        for seed_index in range(8):
            public, truth = GENERATOR.generate(_task(level, "full"), f"profile-{level}-{seed_index}")
            puzzle = public["puzzle"]
            profile = truth["generation_profile"]
            assert len(puzzle["faces"]) == parameters["tile_count"]
            assert all(len(face["vertices"]) == 14 for face in puzzle["faces"])
            assert len(puzzle["clues"]) == max(3, math.ceil(parameters["tile_count"] * parameters["clue_fraction"]))
            assert profile["internal_solution_edges"] >= parameters["minimum_internal_loop_edges"]
            assert profile["unique_solution_count"] == 1
            count, solution = GENERATOR._count_solutions(
                puzzle,
                {clue["face_id"]: clue["value"] for clue in puzzle["clues"]},
            )
            assert count == 1
            assert solution == set(truth["solution_edge_ids"])
            assert GENERATOR._single_cycle(truth["solution_edge_ids"], puzzle)
            fingerprints.add(json.dumps(puzzle, sort_keys=True))
        assert len(fingerprints) == 8


def test_generation_is_deterministic_and_time_mode_does_not_change_world() -> None:
    first = GENERATOR.generate(_task(3, "full"), "deterministic")
    second = GENERATOR.generate(_task(3, "full"), "deterministic")
    assert first == second
    live, _ = GENERATOR.generate(_task(3, "full", "live"), "time-equivalence")
    paused, _ = GENERATOR.generate(_task(3, "full", "paused"), "time-equivalence")
    assert live["puzzle"] == paused["puzzle"]
    assert live["parameters"] == paused["parameters"]
    assert live["control_condition"]["real_time"] == "live"
    assert paused["control_condition"]["real_time"] == "paused"


def test_original_task_is_exactly_the_declared_d3_generated_world() -> None:
    original = json.loads(
        (ENV / "tasks/einstein_loop_seed_0001/task.json").read_text(encoding="utf-8")
    )
    original_public, original_truth = GENERATOR.generate(original, "baseline-equivalence")
    controlled = _task(3, "full")
    materialized_parameters = controlled["_control_condition"]["difficulty_parameters"]
    controlled["_control_condition"]["difficulty_parameters"] = {
        key: materialized_parameters[key] for key in sorted(materialized_parameters)
    }
    controlled_public, controlled_truth = GENERATOR.generate(
        controlled, "baseline-equivalence"
    )
    assert original_public["parameters"] == controlled_public["parameters"]
    assert original_public["puzzle"] == controlled_public["puzzle"]
    assert original_truth["solution_edge_ids"] == controlled_truth["solution_edge_ids"]


def test_stale_identity_wrong_surface_and_forged_drag_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(3, "full"), "negative-contract")
    payload = _payload(public, truth, "full")
    payload["challenge_id"] = "stale"
    assert GRADER.grade(payload, truth, public)["passed"] is False

    payload = _payload(public, truth, "full")
    payload["events"][0]["input_source"] = "edge_proxy_button"
    assert "input surface" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full")
    payload["events"][0]["gesture"]["travel_px"] = 1
    assert "travel" in GRADER.grade(payload, truth, public)["feedback"]


def test_wrong_loop_and_forged_final_edge_set_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(2, "simplified"), "wrong-loop")
    payload = _payload(public, truth, "simplified")
    wrong = next(edge["id"] for edge in public["puzzle"]["edges"] if edge["id"] not in truth["solution_edge_ids"])
    payload["events"].append({
        "sequence": len(payload["events"]) + 1,
        "type": "edge_update",
        "mode": "loop",
        "input_source": "edge_proxy_button",
        "edges": [{"id": wrong, "before": 0, "after": 1}],
    })
    payload["final_loop_edge_ids"] = sorted([*truth["solution_edge_ids"], wrong], key=lambda value: int(value[1:]))
    assert GRADER.grade(payload, truth, public)["passed"] is False

    payload = _payload(public, truth, "simplified")
    payload["final_loop_edge_ids"] = payload["final_loop_edge_ids"][:-1]
    assert "do not match transcript" in GRADER.grade(payload, truth, public)["feedback"]


def test_baseline_profiles_interaction_and_static_clock_contract() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    env = json.loads((ENV / "env.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/einstein_loop_seed_0001/task.json").read_text(encoding="utf-8"))
    split = json.loads((ROOT / "weird_captcha_gym/splits/einstein_loop_split.json").read_text(encoding="utf-8"))
    real_time = json.loads((ROOT / "weird_captcha_gym/real_time.json").read_text(encoding="utf-8"))["environments"]["einstein_loop"]
    assert controls["baseline"] == {"difficulty": 3, "interaction": "full", "real_time": "live"}
    assert [controls["difficulty"][str(level)]["parameters"]["tile_count"] for level in range(1, 6)] == [6, 9, 13, 17, 22]
    assert [controls["difficulty"][str(level)]["parameters"]["clue_fraction"] for level in range(1, 6)] == sorted(
        [controls["difficulty"][str(level)]["parameters"]["clue_fraction"] for level in range(1, 6)], reverse=True
    )
    assert controls["real_time"] == real_time == {"play_time_seconds": 300, "observation_window_ms": 0, "frames_per_observation": 1}
    assert env["runner_options"] == real_time
    assert task["metadata"]["source_anchors"] == ["PLOG-014", "PLOG-200", "PLOG-201"]
    assert task["metadata"]["status"] == "prototype_visual_candidate"
    assert "Developer Tools" in task["natural_language"]
    assert len(split["variations_tasks"]) == 20


def test_browser_surface_contains_real_svg_geometry_and_bound_input_modes() -> None:
    script = (ROOT / "weird_captcha_gym/shared_runtime/app/mechanics/einstein_loop.js").read_text(encoding="utf-8")
    styles = (ROOT / "weird_captcha_gym/shared_runtime/app/mechanics/einstein_loop.css").read_text(encoding="utf-8")
    for token in (
        'data-challenge-id="${esc(model.state.challenge_id)}"',
        "direct_edge_drag",
        "direct_edge_context",
        "edge_proxy_button",
        "data-vertex-hit",
        "data-edge-hit",
        "pointercancel",
        "setPointerCapture",
    ):
        assert token in script
    for selector in (".el-face", ".el-edge-loop", ".el-edge-hit", ".el-clue", ".el-verdict.is-pass", ".el-verdict.is-fail"):
        assert selector in styles
    assert "el-rule-mark" not in script
    assert "el-rule-mark" not in styles
    assert "closed line" not in script
    assert "visible edges around a clue" not in script
