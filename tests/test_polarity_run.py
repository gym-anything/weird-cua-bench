from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENV = BENCH / "environments" / "polarity_run_env"
GENERATOR_PATH = BENCH / "shared_scripts" / "incubator_generators" / "polarity_run.py"
GRADER_PATH = BENCH / "shared_runtime" / "server" / "incubator_graders" / "polarity_run.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("polarity_run_generator_test", GENERATOR_PATH)
GRADER = _load("polarity_run_grader_test", GRADER_PATH)
CONTROLS = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
BASE_TASK = json.loads((ENV / "tasks/polarity_run_seed_0001/task.json").read_text(encoding="utf-8"))


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    task = copy.deepcopy(BASE_TASK)
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(CONTROLS["difficulty"][str(level)]["parameters"]),
    }
    return task


def _solution_payload(public: dict, truth: dict, interaction: str) -> dict:
    source = "polarity_button" if interaction == "simplified" else "polarity_dial_drag"
    events = [
        {
            **item,
            "seq": index,
            "type": "polarity_change",
            "input_source": source,
        }
        for index, item in enumerate(truth["solution_events"], start=1)
    ]
    replay = GRADER._replay(public, [{"tick": item["tick"], "polarity": item["polarity"]} for item in events])
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "gate_crossings": replay["crossings"],
        "terminal": {
            "passed": True,
            "tick": replay["completion_tick"],
            "gates": [item["gate_id"] for item in replay["crossings"]],
            "bead": replay["body"],
        },
        "completed": True,
    }


def test_all_ten_conditions_share_world_and_grade() -> None:
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(_task(level, interaction), f"same-world-{level}")
            assert GRADER.grade(_solution_payload(public, truth, interaction), truth, public)["passed"] is True
            worlds.append((public["charges"], public["walls"], public["gates"], public["target"], public["physics"]))
        assert worlds[0] == worlds[1]


def test_live_and_paused_are_identical_decision_worlds() -> None:
    live, live_truth = GENERATOR.generate(_task(4, "full", "live"), "clock-equivalence")
    paused, paused_truth = GENERATOR.generate(_task(4, "full", "paused"), "clock-equivalence")
    for key in ("charges", "walls", "gates", "target", "physics", "initial_bead"):
        assert live[key] == paused[key]
    assert live_truth["solution_events"] == paused_truth["solution_events"]
    assert live["control_condition"]["real_time"] == "live"
    assert paused["control_condition"]["real_time"] == "paused"


def test_profiles_change_the_active_decision_problem() -> None:
    generated = {
        level: GENERATOR.generate(_task(level, "full"), f"profile-{level}")[0]
        for level in range(1, 6)
    }
    assert [len(generated[level]["gates"]) for level in range(1, 6)] == [2, 3, 4, 5, 6]
    assert [generated[level]["gates"][0]["gap_half"] for level in range(1, 6)] == [145, 125, 105, 82, 64]
    assert [generated[level]["target"]["radius"] for level in range(1, 6)] == [50, 46, 42, 38, 35]


def test_profiles_have_level_accurate_catalog_instructions() -> None:
    expected = {
        1: "Guide the bead through two broad gates and into the exit ring.",
        2: "Guide the bead through three gates and into the smaller exit ring.",
        3: "Guide the bead through four force-field gates and into the exit ring.",
        4: "Guide the bead across five narrower force-field gates and into the tighter exit.",
        5: "Guide the bead across six tight force-field gates and into the smallest exit ring.",
    }
    assert {
        level: CONTROLS["difficulty"][str(level)]["natural_language"]
        for level in range(1, 6)
    } == expected


def test_seed_variation_is_deterministic_and_visible() -> None:
    identities = set()
    worlds = set()
    for index in range(25):
        public, truth = GENERATOR.generate(_task(3, "full"), f"breadth-{index}")
        public_again, truth_again = GENERATOR.generate(_task(3, "full"), f"breadth-{index}")
        assert public == public_again and truth == truth_again
        identities.add(public["challenge_id"])
        worlds.add(json.dumps({"charges": public["charges"], "initial": public["initial_bead"]}, sort_keys=True))
        assert "solution_events" not in json.dumps(public)
        assert "solution_trace" not in json.dumps(public)
    assert len(identities) == 25
    assert len(worlds) >= 8


def test_grader_rejects_stale_identity_wrong_surface_and_forgery() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "negative-contract")
    payload = _solution_payload(public, truth, "full")

    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "stale"
    assert "stale" in GRADER.grade(stale, truth, public)["feedback"]

    wrong_surface = copy.deepcopy(payload)
    wrong_surface["events"][0]["input_source"] = "polarity_button"
    assert "input surface" in GRADER.grade(wrong_surface, truth, public)["feedback"]

    forged = copy.deepcopy(payload)
    forged["terminal"]["bead"]["x"] += 10
    assert "terminal bead" in GRADER.grade(forged, truth, public)["feedback"]

    overbudget = copy.deepcopy(payload)
    overbudget["events"] = overbudget["events"] * 3
    assert "sequence" in GRADER.grade(overbudget, truth, public)["feedback"] or "budget" in GRADER.grade(overbudget, truth, public)["feedback"]


def test_registration_and_source_contract() -> None:
    env = json.loads((ENV / "env.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/polarity_run_seed_0001/task.json").read_text(encoding="utf-8"))
    split = json.loads((BENCH / "splits/polarity_run_split.json").read_text(encoding="utf-8"))
    manifest = json.loads((BENCH / "benchmark_manifest.json").read_text(encoding="utf-8"))
    real_time = json.loads((BENCH / "real_time.json").read_text(encoding="utf-8"))["environments"]
    assert CONTROLS["baseline"] == {"difficulty": 3, "interaction": "full", "real_time": "live"}
    assert env["runner_options"] == {"observation_window_ms": 600, "frames_per_observation": 5, "play_time_seconds": 180}
    assert task["name"] == "Polarity Run"
    assert task["metadata"]["source_anchors"] == ["XUIF-263"]
    assert task["metadata"]["capabilities"] == [
        "visual_understanding_2d",
        "temporal_understanding_and_memory",
        "reasoning_and_planning",
    ]
    assert len(split["variations_tasks"]) == 20
    assert set(split["variations_tasks"]) == {
        f"polarity_run_d{level}_{mode}_seed_0001{suffix}"
        for level in range(1, 6) for mode in ("full", "simplified") for suffix in ("", "_tpaused")
    }
    assert manifest["environment_count"] == len(manifest["environments"])
    assert manifest["environments"].count("polarity_run_env") == 1
    assert real_time["polarity_run"] == env["runner_options"]


def test_browser_module_binds_both_surfaces_and_visible_physics() -> None:
    source = (BENCH / "shared_runtime/app/mechanics/polarity_run.js").read_text(encoding="utf-8")
    styles = (BENCH / "shared_runtime/app/mechanics/polarity_run.css").read_text(encoding="utf-8")
    for token in (
        "polarity_button",
        "polarity_dial_drag",
        "polarity-dial",
        "polarity_change",
        "force_strength",
        "gateCrossings",
        "pointerdown",
        "pointermove",
        "pointerup",
        "rejectDialKeyboard",
        "dialDragMoved",
    ):
        assert token in source
    for selector in (".polarity-run-canvas", ".polarity-run-console", ".polarity-dial-knob", ".polarity-button"):
        assert selector in styles
    assert "solution_events" not in source
