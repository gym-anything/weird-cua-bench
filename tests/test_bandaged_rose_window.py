from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENV = BENCH / "environments" / "bandaged_rose_window_env"
GENERATOR_PATH = BENCH / "shared_scripts" / "incubator_generators" / "bandaged_rose_window.py"
GRADER_PATH = BENCH / "shared_runtime" / "server" / "incubator_graders" / "bandaged_rose_window.py"
VERIFIER_PATH = ENV / "tasks" / "bandaged_rose_window_seed_0001" / "verifier.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("bandaged_rose_generator_test", GENERATOR_PATH)
GRADER = _load("bandaged_rose_grader_test", GRADER_PATH)
CONTROLS = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))


def _task(level: int, interaction: str, time_mode: str = "live") -> dict:
    profile = CONTROLS["difficulty"][str(level)]
    return {
        "id": f"bandaged_rose_window_d{level}_{interaction}_seed_0001_t{time_mode}",
        "_control_condition": {
            "difficulty": level,
            "interaction": interaction,
            "time_mode": time_mode,
            "difficulty_parameters": copy.deepcopy(profile["parameters"]),
        },
    }


def _replay_payload(public: dict, truth: dict) -> dict:
    state = tuple(truth["rose"]["initial_state"])
    events = []
    source = "proxy_buttons" if truth["control_condition"]["interaction"] == "simplified" else "rim_drag"
    for sequence, move in enumerate(truth["solution_moves"], start=1):
        disc = GENERATOR.DISC_IDS.index(move["disc_id"])
        assert GENERATOR.legal(state, disc)
        after = GENERATOR.turn(state, disc, int(move["direction"]))
        events.append({
            "sequence": sequence,
            "disc_id": move["disc_id"],
            "direction": int(move["direction"]),
            "input_source": source,
            "outcome": "turned",
            "before_state": list(state),
            "after_state": list(after),
            "turns_after": sequence,
        })
        state = after
    return {
        "mechanic_id": "bandaged_rose_window",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "events": events,
        "final_state": list(state),
        "successful_turns": len(events),
        "refused_turns": 0,
        "completed": True,
    }


def test_exact_frontiers_match_the_rotascope_state_graph() -> None:
    expected = {0: 1, 1: 6, 2: 18, 3: 39, 4: 90, 5: 144, 6: 240, 7: 348, 8: 540, 9: 756, 10: 1284, 11: 2052, 12: 3648, 13: 5268, 14: 8568}
    assert {depth: len(states) for depth, states in GENERATOR._state_graph()[2].items()} == expected


def test_all_difficulty_and_interaction_conditions_generate_exact_solvable_contracts() -> None:
    for level in range(1, 6):
        expected_depth = CONTROLS["difficulty"][str(level)]["parameters"]["scramble_depth"]
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(_task(level, interaction), "matrix-seed")
            assert public["rose"]["optimal_distance"] == expected_depth
            assert len(truth["solution_moves"]) == expected_depth
            assert "solution_moves" not in public
            decision = GRADER.grade(_replay_payload(public, truth), truth, public)
            assert decision["passed"] is True, decision
            world = copy.deepcopy(public["rose"])
            worlds.append(world)
        assert worlds[0] == worlds[1]


def test_live_and_paused_schedule_do_not_change_static_world() -> None:
    live_public, live_truth = GENERATOR.generate(_task(4, "full", "live"), "clock-seed")
    paused_public, paused_truth = GENERATOR.generate(_task(4, "full", "paused"), "clock-seed")
    assert live_public["rose"] == paused_public["rose"]
    assert live_truth["solution_moves"] == paused_truth["solution_moves"]
    assert CONTROLS["real_time"] == {"play_time_seconds": 180, "observation_window_ms": 0, "frames_per_observation": 1}


def test_refused_turn_is_replayed_as_silent_no_change() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "refusal-seed")
    state = tuple(truth["rose"]["initial_state"])
    illegal = next(index for index in range(3) if not GENERATOR.legal(state, index))
    payload = {
        "mechanic_id": "bandaged_rose_window",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "events": [{
            "sequence": 1,
            "disc_id": GENERATOR.DISC_IDS[illegal],
            "direction": 1,
            "input_source": "rim_drag",
            "outcome": "refused",
            "before_state": list(state),
            "after_state": list(state),
            "turns_after": 0,
        }],
        "final_state": list(state),
        "successful_turns": 0,
        "refused_turns": 1,
        "completed": False,
    }
    decision = GRADER.grade(payload, truth, public)
    assert decision["passed"] is False
    assert "incomplete after 0 successful and 1 refused" in decision["feedback"]


def test_grader_rejects_wrong_surface_stale_identity_and_forged_physics() -> None:
    public, truth = GENERATOR.generate(_task(3, "simplified"), "tamper-seed")
    payload = _replay_payload(public, truth)
    wrong_surface = copy.deepcopy(payload)
    wrong_surface["events"][0]["input_source"] = "rim_drag"
    assert GRADER.grade(wrong_surface, truth, public)["passed"] is False
    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "old"
    assert GRADER.grade(stale, truth, public)["feedback"] == "stale challenge"
    forged = copy.deepcopy(payload)
    forged["events"][0]["after_state"] = forged["events"][0]["before_state"]
    assert "physics" in GRADER.grade(forged, truth, public)["feedback"]


def test_solved_state_is_not_a_pre_submit_interaction_oracle() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "no-solved-oracle-seed")
    payload = _replay_payload(public, truth)
    state = tuple(payload["final_state"])
    source = "rim_drag"
    for direction in (1, -1):
        before = state
        state = GENERATOR.turn(state, 0, direction)
        payload["events"].append({
            "sequence": len(payload["events"]) + 1,
            "disc_id": "north",
            "direction": direction,
            "input_source": source,
            "outcome": "turned",
            "before_state": list(before),
            "after_state": list(state),
            "turns_after": len(payload["events"]) + 1,
        })
    payload["final_state"] = list(state)
    payload["successful_turns"] = len(payload["events"])
    assert state == tuple(truth["rose"]["solved_state"])
    assert GRADER.grade(payload, truth, public)["passed"] is True


def test_generation_is_deterministic_and_varied() -> None:
    first = GENERATOR.generate(_task(5, "full"), "same-seed")
    second = GENERATOR.generate(_task(5, "full"), "same-seed")
    assert first == second
    states = {
        tuple(GENERATOR.generate(_task(4, "full"), f"seed-{index}")[0]["rose"]["initial_state"])
        for index in range(40)
    }
    assert len(states) >= 35


def test_full_mode_handles_are_clear_of_every_glass_piece() -> None:
    public, _truth = GENERATOR.generate(_task(4, "full"), "handle-clearance-seed")
    slots = [item["center"] for item in public["rose"]["slots"]]
    for disc in public["rose"]["discs"]:
        angle = math.radians(disc["handle_angle"])
        handle = (
            disc["center"][0] + math.cos(angle) * disc["handle_radius"],
            disc["center"][1] + math.sin(angle) * disc["handle_radius"],
        )
        assert min(math.dist(handle, slot) for slot in slots) >= 95


def test_files_registries_policy_and_independent_verifier() -> None:
    task = json.loads((ENV / "tasks" / "bandaged_rose_window_seed_0001" / "task.json").read_text(encoding="utf-8"))
    policy = (task["description"] + " " + task["natural_language"]).lower()
    for phrase in ("screenshots and visible controls", "developer tools", "dom", "terminal", "address-bar", "reload", "external applications", "unrelated tab"):
        assert phrase in policy
    assert task["name"] == "Bandaged Rose Window"
    assert task["metadata"]["source_anchors"] == ["TRP-035", "PHY-028"]
    assert task["metadata"]["capabilities"] == [
        "visual understanding: 2D",
        "reasoning and planning",
        "exploration and interface understanding",
    ]
    manifest = json.loads((BENCH / "benchmark_manifest.json").read_text(encoding="utf-8"))
    assert manifest["environment_count"] == len(manifest["environments"])
    assert manifest["environments"].count("bandaged_rose_window_env") == 1
    clocks = json.loads((BENCH / "real_time.json").read_text(encoding="utf-8"))["environments"]
    assert clocks["bandaged_rose_window"] == CONTROLS["real_time"]
    verifier_source = VERIFIER_PATH.read_text(encoding="utf-8")
    assert "incubator_graders" not in verifier_source
    assert "def _legal" in verifier_source and "def _turn" in verifier_source
    frontend = (BENCH / "shared_runtime" / "app" / "mechanics" / "bandaged_rose_window.js").read_text(encoding="utf-8")
    assert "proxy_buttons" in frontend and "rim_drag" in frontend
    assert "outcome: allowed ? \"turned\" : \"refused\"" in frontend
    assert "pointermove" in frontend and "setPointerCapture" in frontend and "releasePointerCapture" in frontend
    assert "rose-fail-card" in frontend and ">RETRY<" in frontend
    assert "delete root.dataset.freshFailure" in frontend
    assert "heart frees a circle" not in frontend and "foreign points bandage it" not in frontend
    for forbidden in (
        "READY TO SEAL",
        "TURN BUDGET SPENT",
        "THREE RIM HANDLES",
        "ONE NOTCH PER TURN",
        "SUCCESSFUL TURNS",
        "Refused turns",
        "RESTORATION REJECTED",
        "THE ROSE IS STILL BROKEN",
    ):
        assert forbidden not in frontend
    assert all(profile["parameters"] == {"scramble_depth": depth} for profile, depth in zip(CONTROLS["difficulty"].values(), (2, 4, 7, 10, 14)))
    public, _truth = GENERATOR.generate(_task(1, "full"), "visible-gate-seed")
    assert "move_budget" not in public["rose"] and "legal_hint" not in public["rose"] and "rules" not in public
    task_surface = " ".join(profile["natural_language"].split("Solve only", 1)[0] for profile in CONTROLS["difficulty"].values()).lower()
    for forbidden in ("sixth", "silhouette", "budget", "refused", "free circle"):
        assert forbidden not in task_surface
    assert "setTimeout" not in frontend


def test_provenance_declares_no_shipped_source_assets() -> None:
    provenance = json.loads((BENCH / "shared_runtime" / "assets" / "provenance" / "bandaged_rose_window_v0.json").read_text(encoding="utf-8"))
    assert provenance["mechanic_id"] == "bandaged_rose_window"
    assert provenance["source_anchors"] == ["TRP-035", "PHY-028"]
    assert provenance["assets"] == []
    assert len(provenance["sources"]) == 4
