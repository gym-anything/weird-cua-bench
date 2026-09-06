from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
MECHANIC = "unwatched_wing"
ENVIRONMENT = BENCHMARK / "environments" / f"{MECHANIC}_env"
TASK_PATH = ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json"
CONTROLS_PATH = ENVIRONMENT / "controls.json"
GENERATOR_PATH = BENCHMARK / "shared_scripts" / "incubator_generators" / f"{MECHANIC}.py"
GRADER_PATH = BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py"
FRONTEND_PATH = BENCHMARK / "shared_runtime" / "app" / "mechanics" / f"{MECHANIC}.js"
FRONTEND_CSS_PATH = BENCHMARK / "shared_runtime" / "app" / "mechanics" / f"{MECHANIC}.css"
VERIFIER_PATH = ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "verifier.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("unwatched_wing_generator_test", GENERATOR_PATH)
GRADER = _load("unwatched_wing_grader_test", GRADER_PATH)
TASK = json.loads(TASK_PATH.read_text(encoding="utf-8"))
CONTROLS = json.loads(CONTROLS_PATH.read_text(encoding="utf-8"))


def _controlled_task(level: int, interaction: str, real_time: str = "live") -> dict:
    task = copy.deepcopy(TASK)
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(CONTROLS["difficulty"][str(level)]["parameters"]),
    }
    return task


def _world(public: dict) -> dict:
    world = copy.deepcopy(public)
    for key in ("task_id", "challenge_id", "control_condition", "prompt", "rules"):
        world.pop(key, None)
    return world


def _active_signature(public: dict) -> tuple:
    return (
        tuple(public["map"]),
        tuple(
            (tuple(item["cell"]), bool(item.get("probe_threshold")))
            for item in public["plinths"]
        ),
        tuple(public["dock"]["cell"]),
        tuple((item["plinth_id"], tuple(item["center"])) for item in public["wall_lights"]),
        tuple(public["required_pin_steps"]),
    )


def test_baseline_and_profiles_describe_distinct_current_configurations() -> None:
    assert CONTROLS["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    profiles = CONTROLS["difficulty"]
    assert [profiles[str(level)]["parameters"]["target_positions"] for level in range(1, 6)] == [3, 4, 5, 6, 7]
    assert [len(profiles[str(level)]["parameters"]["required_pin_steps"]) for level in range(1, 6)] == [0, 1, 1, 2, 3]
    assert [len(profiles[str(level)]["parameters"]["ambient_steps"]) for level in range(1, 6)] == [0, 0, 1, 2, 3]
    assert [profiles[str(level)]["parameters"]["decoy_count"] for level in range(1, 6)] == [0, 1, 1, 2, 3]
    assert CONTROLS["interaction"]["simplified"]["implemented"] is True
    assert CONTROLS["interaction"]["full"]["implemented"] is True


def test_all_ten_conditions_are_deterministic_and_interaction_world_paired() -> None:
    for level in range(1, 6):
        worlds = {}
        challenge_ids = set()
        for interaction in ("simplified", "full"):
            task = _controlled_task(level, interaction)
            public, truth = GENERATOR.generate(task, f"unwatched-matrix-{level}")
            assert (public, truth) == GENERATOR.generate(task, f"unwatched-matrix-{level}")
            assert "solution" not in public
            assert public["challenge_id"] == truth["challenge_id"]
            assert public["control_condition"] == truth["control_condition"]
            assert len(public["target_path"]) == CONTROLS["difficulty"][str(level)]["parameters"]["target_positions"]
            assert len(public["decoy_exhibits"]) == CONTROLS["difficulty"][str(level)]["parameters"]["decoy_count"]
            assert len(public["wall_lights"]) == len(CONTROLS["difficulty"][str(level)]["parameters"]["ambient_steps"])
            assert [index for index, item in enumerate(public["plinths"][:len(public["target_path"])]) if item["probe_threshold"]] == public["required_pin_steps"]
            assert truth["solution"]["target_route_indices"] == sorted(truth["solution"]["target_route_indices"])
            assert truth["solution"]["dock_route_index"] >= truth["solution"]["target_route_indices"][-1]
            worlds[interaction] = _world(public)
            challenge_ids.add(public["challenge_id"])
        assert worlds["simplified"] == worlds["full"]
        assert len(challenge_ids) == 1


def test_live_and_paused_conditions_do_not_change_the_generated_world() -> None:
    public_live, _ = GENERATOR.generate(_controlled_task(4, "full", "live"), "clock-pair")
    public_paused, _ = GENERATOR.generate(_controlled_task(4, "full", "paused"), "clock-pair")
    assert _world(public_live) == _world(public_paused)
    assert public_live["challenge_id"] == public_paused["challenge_id"]
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    assert "WeirdCaptchaTime" not in source
    assert "requestAnimationFrame" not in source


def test_fresh_seeds_change_the_active_decision_graph() -> None:
    for level in range(1, 6):
        signatures = set()
        for index in range(200):
            public, _truth = GENERATOR.generate(
                _controlled_task(level, "full"),
                f"unwatched-active-variation-{level}-{index}",
            )
            signatures.add(_active_signature(public))
            targets = public["plinths"][: len(public["target_path"])]
            decoys = public["plinths"][len(public["target_path"]):]
            for step in public["required_pin_steps"]:
                assert math.dist(
                    targets[step]["center"], targets[step + 1]["center"]
                ) > public["controls"]["hand_lamp_range"] + .5
            for decoy in decoys:
                for target in targets:
                    assert math.dist(decoy["cell"], target["cell"]) >= 2.25
                    assert decoy["cell"][0] != target["cell"][0]
                    assert decoy["cell"][1] != target["cell"][1]
        assert len(signatures) >= 100


def test_visible_surface_omits_tutorial_progress_and_task_time_timers() -> None:
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    stylesheet = FRONTEND_CSS_PATH.read_text(encoding="utf-8")
    prohibited = (
        "FRAME CONTACT",
        "PROBE MISSED",
        "PROBE FIXED",
        "NO ISOLATOR WITHIN REACH",
        "HELD /",
        "JUMPS",
        "BEARING",
        "SECTOR",
        "HOLDS POSITION",
        "W A S D",
        "OBSERVER STATE + DARKNESS",
        "TRANSFER VOID",
        "ABORT LOGGED",
        "window.setTimeout",
    )
    assert all(text not in source for text in prohibited)
    assert 'void submit(true)' in source
    assert '<i>PASS</i>' in source
    assert '<i>FAIL</i>' in source
    assert '<kbd>F</kbd>HAND LAMP' in source
    assert '<kbd>V</kbd>VIEWER' in source
    assert '<kbd>R</kbd>RECALL' in source
    assert '<kbd>E</kbd>ISOLATOR' in source
    assert "remaining -= delta;\n    }\n    afterAction();\n  }\n\n  function toggleLamp" in source
    assert "transition: opacity 120ms" not in stylesheet
    assert "visibility: visible" in stylesheet
    assert "@keyframes uw-verdict" not in stylesheet


def test_grader_binds_geometry_condition_and_input_surface() -> None:
    public, truth = GENERATOR.generate(_controlled_task(4, "simplified"), "surface-binding")
    base = {
        "mechanic_id": MECHANIC,
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "control_condition": truth["control_condition"],
        "interaction_mode": "simplified",
        "events": [{"sequence": 1, "kind": "abandon", "input_source": "keyboard"}],
    }
    wrong_surface = GRADER.grade(base, truth, public)
    assert wrong_surface["passed"] is False
    assert "wrong abandon input" in wrong_surface["feedback"]

    wrong_condition = copy.deepcopy(base)
    wrong_condition["control_condition"]["interaction"] = "full"
    condition_grade = GRADER.grade(wrong_condition, truth, public)
    assert condition_grade["passed"] is False
    assert "submitted control condition" in condition_grade["feedback"]

    tampered_public = copy.deepcopy(public)
    tampered_public["map"][0] = "." + tampered_public["map"][0][1:]
    geometry_grade = GRADER.grade({**base, "events": []}, truth, tampered_public)
    assert geometry_grade["passed"] is False
    assert "public map differs" in geometry_grade["feedback"]


def test_source_registry_and_exported_verifier_are_wired() -> None:
    assert TASK["name"] == "The Unwatched Wing"
    assert TASK["metadata"]["source_anchors"] == ["VGE-535", "VGE-536", "VGE-508"]
    assert TASK["metadata"]["capabilities"] == [
        "visual understanding: 3D",
        "temporal understanding and memory",
        "reasoning and planning",
        "exploration and interface understanding",
    ]
    provenance = json.loads(
        (BENCHMARK / "shared_runtime/assets/provenance/unwatched_wing_v0.json").read_text(
            encoding="utf-8"
        )
    )
    assert provenance["source_anchors"] == TASK["metadata"]["source_anchors"]
    assert {source["url"] for source in provenance["sources"]} == {
        "https://outerwilds.fandom.com/wiki/Tower_of_Quantum_Trials",
        "https://outerwilds.fandom.com/wiki/Quantum_Shards",
        "https://en.wikipedia.org/wiki/Antichamber",
        "https://antichamber.fandom.com/wiki/Main_Page",
    }
    manifest = json.loads((BENCHMARK / "benchmark_manifest.json").read_text(encoding="utf-8"))
    assert "unwatched_wing_env" in manifest["environments"]
    assert manifest["environment_count"] == len(manifest["environments"])
    real_time = json.loads((BENCHMARK / "real_time.json").read_text(encoding="utf-8"))
    assert real_time["environments"][MECHANIC] == {
        "play_time_seconds": 180,
        "observation_window_ms": 0,
        "frames_per_observation": 1,
    }
    verifier = VERIFIER_PATH.read_text(encoding="utf-8")
    assert "incubator_graders/unwatched_wing.py" not in verifier
    assert '"unwatched_wing.py"' in verifier
    assert "independent observer-state replay" in verifier
