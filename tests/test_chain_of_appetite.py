from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENV = BENCH / "environments" / "chain_of_appetite_env"
GENERATOR_PATH = BENCH / "shared_scripts" / "incubator_generators" / "chain_of_appetite.py"
GRADER_PATH = BENCH / "shared_runtime" / "server" / "incubator_graders" / "chain_of_appetite.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("chain_of_appetite_generator_test", GENERATOR_PATH)
GRADER = _load("chain_of_appetite_grader_test", GRADER_PATH)


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/chain_of_appetite_seed_0001/task.json").read_text(encoding="utf-8"))
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
    }
    return task


def _payload(public: dict, truth: dict, interaction: str, moves: list[dict] | None = None) -> dict:
    state = copy.deepcopy(truth["initial_monsters"])
    events = []
    grid_size = int(public["grid_size"])
    source = "paired_clicks" if interaction == "simplified" else "creature_drag"
    for move in moves if moves is not None else truth["solution_moves"]:
        by_id = {monster["id"]: monster for monster in state}
        actor = by_id[move["actor_id"]]
        victim = by_id[move["victim_id"]]
        event = {
            "sequence": len(events) + 1,
            "actor_id": actor["id"],
            "victim_id": victim["id"],
            "from": [actor["row"], actor["column"]],
            "to": [victim["row"], victim["column"]],
            "actor_body": actor["body"],
            "mouth_before": actor["mouth"],
            "victim_body": victim["body"],
            "inherited_mouth": victim["mouth"],
            "input_source": source,
        }
        if interaction == "full":
            distance = math.hypot(actor["column"] - victim["column"], actor["row"] - victim["row"])
            event["gesture"] = {
                "start_u": (actor["column"] + 0.5) / grid_size,
                "start_v": (actor["row"] + 0.5) / grid_size,
                "end_u": (victim["column"] + 0.5) / grid_size,
                "end_v": (victim["row"] + 0.5) / grid_size,
                "travel_px": max(40.0, distance * 90.0),
                "sample_count": 8,
            }
        state = GENERATOR.apply_move(state, actor["id"], victim["id"])
        available = GENERATOR.legal_moves(state)
        event["remaining_after"] = len(state)
        event["outcome"] = "solved" if len(state) == 1 else "deadlock" if not available else "running"
        events.append(event)
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "final_monsters": state,
        "remaining": len(state),
        "completed": len(state) == 1,
    }


def test_all_ten_conditions_share_world_and_grade() -> None:
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(_task(level, interaction), f"chain-matrix-{level}")
            decision = GRADER.grade(_payload(public, truth, interaction), truth, public)
            assert decision["passed"] is True, decision
            worlds.append((public["grid_size"], public["monsters"], public["colors"], public["parameters"], public["palette"]))
        assert worlds[0] == worlds[1]


def test_backward_generation_is_deterministic_varied_solvable_and_has_deadlock() -> None:
    for level in range(1, 6):
        identities = set()
        initial_layouts = set()
        for index in range(12):
            seed = f"chain-scale-{level}-{index}"
            public, truth = GENERATOR.generate(_task(level, "simplified"), seed)
            public_again, truth_again = GENERATOR.generate(_task(level, "simplified"), seed)
            assert public == public_again and truth == truth_again
            assert "solution_moves" not in public and "failure_moves" not in public
            assert len(public["monsters"]) == public["parameters"]["monster_count"]
            assert len({(monster["row"], monster["column"]) for monster in public["monsters"]}) == len(public["monsters"])
            assert len(truth["solution_moves"]) == len(public["monsters"]) - 1
            assert truth["failure_moves"]

            solved = copy.deepcopy(truth["initial_monsters"])
            for move in truth["solution_moves"]:
                solved = GENERATOR.apply_move(solved, move["actor_id"], move["victim_id"])
            assert len(solved) == 1

            failed = copy.deepcopy(truth["initial_monsters"])
            for move in truth["failure_moves"]:
                failed = GENERATOR.apply_move(failed, move["actor_id"], move["victim_id"])
            assert len(failed) > 1 and GENERATOR.legal_moves(failed) == []
            assert GRADER.grade(_payload(public, truth, "simplified", truth["failure_moves"]), truth, public)["passed"] is False
            identities.add(public["challenge_id"])
            initial_layouts.add(tuple((item["row"], item["column"], item["body"], item["mouth"]) for item in public["monsters"]))
        assert len(identities) == 12
        assert len(initial_layouts) >= 10


def test_baseline_and_adjacent_profiles_change_the_visible_decision_problem() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    assert controls["baseline"] == {"difficulty": 4, "interaction": "simplified", "real_time": "live"}
    profiles = [controls["difficulty"][str(level)]["parameters"] for level in range(1, 6)]
    assert [item["monster_count"] for item in profiles] == [5, 7, 9, 12, 15]
    assert [item["grid_size"] for item in profiles] == [3, 4, 4, 5, 5]
    assert [item["color_count"] for item in profiles] == [3, 3, 4, 5, 6]
    assert [item["hint_mode"] for item in profiles] == ["none", "none", "none", "none", "none"]
    for level, expected in enumerate(profiles, start=1):
        public, _ = GENERATOR.generate(_task(level, "simplified"), "profile-contract")
        assert public["parameters"] == expected
        assert len(public["monsters"]) == expected["monster_count"]
        assert len(public["colors"]) == expected["color_count"]
        assert public["grid_size"] == expected["grid_size"]


def test_live_and_paused_preserve_the_same_static_world() -> None:
    live, _ = GENERATOR.generate(_task(4, "full", "live"), "time-equivalence")
    paused, _ = GENERATOR.generate(_task(4, "full", "paused"), "time-equivalence")
    for key in ("grid_size", "monsters", "colors", "palette", "parameters", "rule"):
        assert live[key] == paused[key]
    assert live["control_condition"]["real_time"] == "live"
    assert paused["control_condition"]["real_time"] == "paused"


def test_stale_wrong_surface_forged_state_and_short_drag_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "negative-contract")

    payload = _payload(public, truth, "full")
    payload["challenge_id"] = "stale"
    assert "stale" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full")
    payload["events"][0]["input_source"] = "paired_clicks"
    assert "wrong interaction" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full")
    payload["events"][0]["gesture"]["travel_px"] = 1
    assert "too short" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full")
    payload["events"][0]["gesture"]["sample_count"] = 2
    assert "too short" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full")
    payload["events"][0]["mouth_before"] = "forged"
    assert "mouth_before" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full")
    payload["final_monsters"][0]["mouth"] = public["colors"][0]
    if payload["final_monsters"][0]["mouth"] == truth["solution_final"][0]["mouth"]:
        payload["final_monsters"][0]["mouth"] = public["colors"][1]
    assert "final tray" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full", truth["solution_moves"][:-1])
    payload["completed"] = True
    assert "completion" in GRADER.grade(payload, truth, public)["feedback"]


def test_full_drag_visible_circle_boundaries_match_grader_at_every_grid_size() -> None:
    for level in (1, 2, 4):
        public, truth = GENERATOR.generate(_task(level, "full"), f"drag-boundary-d{level}")
        grid_size = int(public["grid_size"])
        geometry = public["interaction_geometry"]
        assert geometry == truth["interaction_geometry"]
        assert geometry == {
            "drag_target_shape": "circle",
            "drag_target_radius_cells": 0.4,
            "min_drag_travel_px": 32,
            "min_drag_samples": 3,
        }
        radius = geometry["drag_target_radius_cells"] / grid_size

        for endpoint, coordinate in (("start", "u"), ("end", "u")):
            inside = _payload(public, truth, "full")
            event = inside["events"][0]
            field = f"{endpoint}_{coordinate}"
            center = float(event["gesture"][field])
            direction = -1.0 if center > 0.5 else 1.0
            event["gesture"][field] = center + direction * radius * 0.99
            event["gesture"]["sample_count"] = geometry["min_drag_samples"]
            accepted = GRADER.grade(inside, truth, public)
            assert accepted["passed"] is True, (level, endpoint, accepted)

            outside = _payload(public, truth, "full")
            outside_event = outside["events"][0]
            outside_center = float(outside_event["gesture"][field])
            outside_direction = -1.0 if outside_center > 0.5 else 1.0
            outside_event["gesture"][field] = outside_center + outside_direction * radius * 1.01
            rejected = GRADER.grade(outside, truth, public)
            assert rejected["passed"] is False
            assert "outside the visible" in rejected["feedback"]


def test_interaction_geometry_is_challenge_bound() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "geometry-binding")
    payload = _payload(public, truth, "full")
    public["interaction_geometry"]["drag_target_radius_cells"] = 0.49
    decision = GRADER.grade(payload, truth, public)
    assert decision["passed"] is False
    assert "interaction geometry" in decision["feedback"]


def test_registration_sources_observation_and_visible_only_rules() -> None:
    env = json.loads((ENV / "env.json").read_text(encoding="utf-8"))
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/chain_of_appetite_seed_0001/task.json").read_text(encoding="utf-8"))
    split = json.loads((BENCH / "splits/chain_of_appetite_split.json").read_text(encoding="utf-8"))
    manifest = json.loads((BENCH / "benchmark_manifest.json").read_text(encoding="utf-8"))
    real_time = json.loads((BENCH / "real_time.json").read_text(encoding="utf-8"))["environments"]
    provenance = json.loads((BENCH / "shared_runtime/assets/provenance/chain_of_appetite_v0.json").read_text(encoding="utf-8"))
    expected_time = {"observation_window_ms": 0, "frames_per_observation": 1, "play_time_seconds": 180}
    assert env["runner_options"] == expected_time
    assert controls["real_time"] == {"play_time_seconds": 180, "observation_window_ms": 0, "frames_per_observation": 1}
    assert real_time["chain_of_appetite"] == {"play_time_seconds": 180, "observation_window_ms": 0, "frames_per_observation": 1}
    assert task["name"] == "Chain of Appetite"
    assert task["metadata"]["source_anchors"] == ["TRP-709", "TRP-737", "PHY-056"]
    assert provenance["source_anchors"] == task["metadata"]["source_anchors"]
    assert manifest["environment_count"] == len(manifest["environments"])
    assert manifest["environments"].count("chain_of_appetite_env") == 1
    assert len(split["variations_tasks"]) == 20
    for profile in controls["difficulty"].values():
        text = profile["natural_language"]
        assert "Solve only from screenshots and visible controls" in text
        assert "Developer Tools" in text and "unrelated" in text


def test_browser_module_exposes_distinct_bound_surfaces_without_task_timers() -> None:
    source = (BENCH / "shared_runtime/app/mechanics/chain_of_appetite.js").read_text(encoding="utf-8")
    styles = (BENCH / "shared_runtime/app/mechanics/chain_of_appetite.css").read_text(encoding="utf-8")
    solver = (BENCH / "tools/incubator_solvers/chain_of_appetite.py").read_text(encoding="utf-8")
    for token in ("paired_clicks", "creature_drag", "start_u", "travel_px", "data-monster-id", "elementsFromPoint", "pointMatchesMonster", "clientWidth"):
        assert token in source
    for token in ("is-selected", "is-dragging", "mouth-ember", "body-ember"):
        assert token in styles
    for forbidden in (
        "FEEDING PROTOCOL",
        "CHAIN LEDGER",
        "VISIBLE ROUTE",
        "MOUTH DOES NOT MATCH BODY",
        "ROUTE BLOCKED",
        "DEADLOCK RECORDED",
        "FRESH TRAY",
        "LUNCH LIGHTS",
        "SIGHTLINES ON",
        "is-legal-target",
        "is-line-target",
        'aria-label="Creature with',
    ):
        assert forbidden not in source
        assert forbidden not in styles
    assert source.count("<strong>PASS</strong>") == 1
    assert source.count("<strong>FAIL</strong>") == 1
    assert "setTimeout" not in source and "setInterval" not in source and "requestAnimationFrame" not in source
    assert "page.mouse.down()" in solver and "page.mouse.move(end_x, end_y, steps=8)" in solver
