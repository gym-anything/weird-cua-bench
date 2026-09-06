from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from weird_captcha_gym.tools.materialize_controlled_tasks import controlled_task, materialize_environment


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENV = BENCH / "environments/ballast_lantern_env"
MECHANIC_ID = "ballast_lantern"
GENERATOR_PATH = BENCH / "shared_scripts/incubator_generators/ballast_lantern.py"
GRADER_PATH = BENCH / "shared_runtime/server/incubator_graders/ballast_lantern.py"
SOLVER_PATH = BENCH / "tools/incubator_solvers/ballast_lantern.py"
VERIFIER_PATH = ENV / "tasks/ballast_lantern_seed_0001/verifier.py"
FRONTEND_PATH = BENCH / "shared_runtime/app/mechanics/ballast_lantern.js"
STYLES_PATH = BENCH / "shared_runtime/app/mechanics/ballast_lantern.css"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("ballast_generator_test", GENERATOR_PATH)
GRADER = _load("ballast_grader_test", GRADER_PATH)
# The solver drives a real browser, so it imports playwright at module scope.
# playwright is not a test dependency, so skip this module rather than fail
# collection where it is absent.
pytest.importorskip("playwright.sync_api")
SOLVER = _load("ballast_solver_test", SOLVER_PATH)
VERIFIER = _load("ballast_verifier_test", VERIFIER_PATH)


def _base_task() -> dict:
    return json.loads((ENV / "tasks/ballast_lantern_seed_0001/task.json").read_text(encoding="utf-8"))


def _controls() -> dict:
    return json.loads((ENV / "controls.json").read_text(encoding="utf-8"))


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    task = _base_task()
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(_controls()["difficulty"][str(level)]["parameters"]),
    }
    return task


def _payload(public: dict, truth: dict, interaction: str) -> dict:
    source = "keyboard_hold" if interaction == "full" else "winch_button"
    events = []
    for sequence, event in enumerate(truth["reference_schedule"], 1):
        engaged = event["engaged"]
        events.append({
            "sequence": sequence,
            "type": "winch",
            "tick": event["tick"],
            "engaged": engaged,
            "input_source": source,
            "phase": ("keydown" if engaged else "keyup") if interaction == "full" else ("haul" if engaged else "coast"),
        })
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "terminal_tick": truth["reference_final_state"]["tick"],
        "final_state": copy.deepcopy(truth["reference_final_state"]),
        "completed": True,
    }


def _failure_payload(public: dict, truth: dict, interaction: str) -> dict:
    parameters, motion, crate = truth["parameters"], truth["motion"], truth["crate"]
    sim = GENERATOR.initial_simulation(parameters, motion, crate)
    source = "keyboard_hold" if interaction == "full" else "winch_button"
    events = [
        {"sequence": 1, "type": "winch", "tick": 0, "engaged": True, "input_source": source, "phase": "keydown" if interaction == "full" else "haul"},
        {"sequence": 2, "type": "winch", "tick": 1, "engaged": False, "input_source": source, "phase": "keyup" if interaction == "full" else "coast"},
    ]
    while sim["status"] == "active":
        GENERATOR.advance_tick(sim, sim["tick"] == 0, parameters, motion, crate)
    return {
        "mechanic_id": public["mechanic_id"], "task_id": public["task_id"],
        "challenge_id": public["challenge_id"], "interaction_mode": interaction,
        "events": events, "terminal_tick": sim["tick"], "final_state": sim, "completed": False,
    }


@pytest.mark.parametrize("interaction", ["full", "simplified"])
def test_live_input_transcripts_are_not_limited_to_240_transitions(interaction):
    public, truth = GENERATOR.generate(_task(5, interaction), "frequent-input")
    payload = _payload(public, truth, interaction)
    # Each pair returns to the same winch state before the first physics tick.
    # These are legal input events, not extra simulation advancement.
    source = "keyboard_hold" if interaction == "full" else "winch_button"
    prefix = [{"type": "winch", "tick": 0, "engaged": engaged,
               "input_source": source,
               "phase": ("keydown" if engaged else "keyup") if interaction == "full" else ("haul" if engaged else "coast")}
              for _ in range(121) for engaged in (True, False)]
    payload["events"] = prefix + payload["events"]
    for sequence, event in enumerate(payload["events"], 1):
        event["sequence"] = sequence
    assert GRADER.grade(payload, truth, public)["passed"] is True
    payload["final_state"]["cage_y"] += 1
    assert GRADER.grade(payload, truth, public)["passed"] is False
    payload["events"] = [{}] * 10_001
    assert "oversized" in GRADER.grade(payload, truth, public)["feedback"]


def _trunc_div(numerator: int, denominator: int) -> int:
    return numerator // denominator if numerator >= 0 else -((-numerator) // denominator)


def _independent_specimen_only_replay(truth: dict) -> dict:
    parameters, motion, crate = truth["parameters"], truth["motion"], truth["crate"]
    sim = GENERATOR.initial_simulation(parameters, motion, crate)
    engaged = False
    decision_interval = max(1, 600 // parameters["tick_ms"])
    while sim["status"] == "active":
        if sim["tick"] % decision_interval == 0:
            predicted_target = sim["specimen_y"] + sim["specimen_velocity"] * 6
            desired_velocity = max(
                -105,
                min(105, _trunc_div(predicted_target - sim["cage_y"], 14)),
            )
            engaged = sim["cage_velocity"] < desired_velocity
        GENERATOR.advance_tick(sim, engaged, parameters, motion, crate)
    return sim


def _independent_reference_allocation_replay(truth: dict) -> tuple[int, int]:
    parameters, motion, crate = truth["parameters"], truth["motion"], truth["crate"]
    sim = GENERATOR.initial_simulation(parameters, motion, crate)
    schedule = {event["tick"]: event["engaged"] for event in truth["reference_schedule"]}
    engaged = False
    crate_fill_ticks = 0
    exclusive_crate_fill_ticks = 0
    while sim["status"] == "active":
        if sim["tick"] in schedule:
            engaged = schedule[sim["tick"]]
        previous_crate_meter = sim["crate_meter"]
        GENERATOR.advance_tick(sim, engaged, parameters, motion, crate)
        if sim["crate_meter"] > previous_crate_meter:
            crate_fill_ticks += 1
            if not sim["specimen_inside"]:
                exclusive_crate_fill_ticks += 1
    assert sim == truth["reference_final_state"]
    return crate_fill_ticks, exclusive_crate_fill_ticks


def test_all_ten_difficulty_interaction_pairs_in_live_and_paused_settings() -> None:
    for level in range(1, 6):
        pair_worlds = []
        for interaction in ("simplified", "full"):
            clock_worlds = []
            for real_time in ("live", "paused"):
                public, truth = GENERATOR.generate(_task(level, interaction, real_time), "matrix-parity")
                outcome = GRADER.grade(_payload(public, truth, interaction), truth, public)
                assert outcome["passed"] is True, (level, interaction, real_time, outcome)
                assert truth["reference_final_state"]["status"] == "secured"
                assert truth["reference_final_state"]["crate_meter"] == public["parameters"]["crate_meter_max"]
                clock_worlds.append({key: public[key] for key in ("challenge_id", "track_units", "parameters", "motion", "crate", "initial_state")})
            assert clock_worlds[0] == clock_worlds[1]
            pair_worlds.append(clock_worlds[0])
        assert pair_worlds[0] == pair_worlds[1]


def test_seeded_generation_varies_drift_crate_and_terminal_schedule() -> None:
    challenges, laws, crate_sites, schedules = set(), set(), set(), set()
    for index in range(120):
        public, truth = GENERATOR.generate(_task(5, "full"), f"scale-{index}")
        challenges.add(public["challenge_id"])
        laws.add(public["motion"]["law"])
        crate_sites.add((public["crate"]["spawn_tick"], public["crate"]["y"]))
        schedules.add(tuple((item["tick"], item["engaged"]) for item in truth["reference_schedule"]))
        assert GRADER.grade(_payload(public, truth, "full"), truth, public)["passed"] is True
        assert 8 <= len(truth["reference_schedule"]) <= 220
    assert len(challenges) == 120
    assert laws == {"steady_sinker", "darter", "floater", "oscillator"}
    assert len(crate_sites) >= 100
    assert len(schedules) == 120


def test_baseline_is_first_built_l4_full_live_configuration() -> None:
    controls = _controls()
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert controls["difficulty"]["4"]["parameters"] == GENERATOR.BASELINE_PARAMETERS
    original_public, original_truth = GENERATOR.generate(_base_task(), "fixed-baseline")
    l4_public, l4_truth = GENERATOR.generate(_task(4, "full"), "fixed-baseline")
    keys = ("challenge_id", "track_units", "parameters", "motion", "crate", "initial_state")
    assert {key: original_public[key] for key in keys} == {key: l4_public[key] for key in keys}
    assert original_truth["reference_schedule"] == l4_truth["reference_schedule"]


def test_profiles_change_active_prediction_and_allocation_problem() -> None:
    profiles = _controls()["difficulty"]
    assert [profiles[str(level)]["parameters"]["cage_half_height"] for level in range(1, 6)] == [1250, 1100, 950, 800, 740]
    assert [len(profiles[str(level)]["parameters"]["motion_law_pool"]) for level in range(1, 6)] == [1, 2, 4, 4, 4]
    assert [profiles[str(level)]["parameters"]["trail_samples"] for level in range(1, 6)] == [6, 5, 4, 3, 2]
    assert [profiles[str(level)]["parameters"]["crate_min_separation"] for level in range(1, 6)] == [800, 1100, 1600, 2200, 2400]
    assert [profiles[str(level)]["parameters"]["capture_drain_per_tick"] for level in range(1, 6)] == [6, 8, 10, 14, 14]
    assert profiles["5"]["parameters"]["max_ticks"] == profiles["4"]["parameters"]["max_ticks"]
    assert profiles["5"]["parameters"]["crate_fill_per_tick"] == profiles["4"]["parameters"]["crate_fill_per_tick"]
    for level in range(1, 6):
        public, truth = GENERATOR.generate(_task(level, "full"), f"profile-{level}")
        assert truth["crate"]["spawn_tick"] >= public["parameters"]["crate_spawn_tick_min"]
        assert truth["reference_final_state"]["status"] == "secured"


def test_accepted_worlds_force_competing_target_service_across_the_ladder() -> None:
    for level in range(1, 6):
        for index in range(40):
            _, truth = GENERATOR.generate(_task(level, "full"), f"coupling-{level}-{index}")
            metrics = truth["reference_metrics"]
            specimen_only = _independent_specimen_only_replay(truth)
            crate_ticks, exclusive_ticks = _independent_reference_allocation_replay(truth)
            assert specimen_only["status"] != "secured"
            assert metrics["specimen_only_final_status"] == specimen_only["status"]
            assert metrics["specimen_only_crate_meter"] == specimen_only["crate_meter"]
            assert metrics["specimen_only_crate_completed"] is (
                specimen_only["crate_meter"] >= truth["parameters"]["crate_meter_max"]
            )
            assert crate_ticks == metrics["crate_fill_ticks"]
            assert exclusive_ticks == metrics["exclusive_crate_fill_ticks"]
            assert exclusive_ticks >= metrics["required_exclusive_crate_fill_ticks"]
            assert metrics["competing_target_certified"] is True
            assert 1 <= metrics["generation_attempts"] <= 512


def test_recent_frames_are_needed_and_action_values_expire() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "temporal-witness")
    p, motion, crate = truth["parameters"], truth["motion"], truth["crate"]
    sim = GENERATOR.initial_simulation(p, motion, crate)
    states = []
    engaged = False
    schedule = {item["tick"]: item["engaged"] for item in truth["reference_schedule"]}
    while sim["status"] == "active" and sim["tick"] < 180:
        if sim["tick"] in schedule:
            engaged = schedule[sim["tick"]]
        states.append((sim["tick"], sim["cage_y"], sim["cage_velocity"], sim["specimen_y"], sim["specimen_velocity"], engaged))
        GENERATOR.advance_tick(sim, engaged, p, motion, crate)
    assert any(first[3] != second[3] and first[4] == second[4] for first, second in zip(states, states[1:]))
    assert any(first[2] != second[2] for first, second in zip(states, states[1:]))
    assert any(first[5] != second[5] for first, second in zip(states, states[1:]))
    assert public["parameters"]["tick_ms"] * 12 == 600


def test_failure_partial_credit_wrong_surface_stale_and_forged_state_are_rejected() -> None:
    for interaction in ("simplified", "full"):
        public, truth = GENERATOR.generate(_task(4, interaction), f"failure-{interaction}")
        failed = _failure_payload(public, truth, interaction)
        outcome = GRADER.grade(failed, truth, public)
        assert outcome["passed"] is False
        assert outcome["graded"] is True
        assert failed["final_state"]["status"] in {"escaped", "specimen_only", "timeout"}
    public, truth = GENERATOR.generate(_task(4, "full"), "tamper")
    valid = _payload(public, truth, "full")
    wrong_mode = copy.deepcopy(valid)
    wrong_mode["interaction_mode"] = "simplified"
    assert GRADER.grade(wrong_mode, truth, public)["passed"] is False
    stale = copy.deepcopy(valid)
    stale["challenge_id"] = "stale-ballast"
    assert "stale" in GRADER.grade(stale, truth, public)["feedback"]
    forged = copy.deepcopy(valid)
    forged["final_state"]["crate_meter"] = truth["parameters"]["crate_meter_max"] - 1
    assert "final shaft state" in GRADER.grade(forged, truth, public)["feedback"]
    proxy = copy.deepcopy(valid)
    proxy["events"][0]["input_source"] = "winch_button"
    assert "wrong interaction" in GRADER.grade(proxy, truth, public)["feedback"]
    bad_phase = copy.deepcopy(valid)
    bad_phase["events"][0]["phase"] = "haul"
    assert "wrong control phase" in GRADER.grade(bad_phase, truth, public)["feedback"]


def test_materialization_registration_capabilities_and_visible_only_boundary(tmp_path: Path) -> None:
    written = materialize_environment(ENV, tmp_path)
    assert len(written) == 10
    task, controls = _base_task(), _controls()
    required = (
        "isolated agent sandbox", "provided gateway", "developer tools", "console", "debugger", "inspector",
        "network", "source", "dom", "page-state inspection", "terminal", "shell",
        "address-bar", "url/query edits", "reload", "navigation", "extensions", "external applications", "unrelated tabs",
    )
    assert task["metadata"]["source_anchors"] == ["VGE-601", "VGE-602"]
    assert task["metadata"]["capabilities"] == [
        "visual understanding: 2D", "temporal understanding and memory", "reasoning and planning",
    ]
    for field in (task["description"], task["natural_language"]):
        for term in required:
            assert term in field.lower()
    for level, profile in controls["difficulty"].items():
        for term in required:
            assert term in profile["natural_language"].lower()
        generated = controlled_task(task, mechanic_id=MECHANIC_ID, level=int(level), interaction="full", profile=profile, task_dir_name=f"ballast-test-d{level}-full")
        assert generated["metadata"]["control_condition"]["difficulty_parameters"] == profile["parameters"]
        simplified = controlled_task(task, mechanic_id=MECHANIC_ID, level=int(level), interaction="simplified", profile=profile, task_dir_name=f"ballast-test-d{level}-simplified")
        assert simplified["natural_language"].startswith("Secure both the drifting specimen")
        assert "Click HAUL" in simplified["natural_language"] and "COAST" in simplified["natural_language"]
    manifest = json.loads((BENCH / "benchmark_manifest.json").read_text(encoding="utf-8"))
    real_time = json.loads((BENCH / "real_time.json").read_text(encoding="utf-8"))
    assert "ballast_lantern_env" in manifest["environments"]
    assert real_time["environments"][MECHANIC_ID] == {"play_time_seconds": 90, "observation_window_ms": 600, "frames_per_observation": 6}
    assert controls["real_time"] == real_time["environments"][MECHANIC_ID]
    assert SOLVER.MECHANIC_ID == GENERATOR.MECHANIC_ID == GRADER.MECHANIC_ID == MECHANIC_ID
    assert callable(VERIFIER.verify_task)


def test_frontend_uses_real_geometry_timer_and_bound_input_surfaces() -> None:
    frontend = FRONTEND_PATH.read_text(encoding="utf-8")
    styles = STYLES_PATH.read_text(encoding="utf-8")
    assert "window.requestAnimationFrame(frame)" in frontend
    assert "performance.now() - model.started" in frontend
    assert "sim.cage_y = position" in frontend
    assert "sim.specimen_y = position" in frontend
    assert '"keyboard_hold"' in frontend and '"winch_button"' in frontend
    assert 'event.code !== "Space"' in frontend
    assert ".ballast-haul" in frontend and ".ballast-coast" in frontend
    assert "cage.style.bottom = pct(sim.cage_y)" in frontend
    assert ".ballast-cage[data-specimen=\"true\"]" in styles
    assert ".ballast-crate[data-inside=\"true\"]" in styles
    forbidden_visible_copy = (
        "Hold to haul", "Set the winch channel", "upper meter drains", "WATCH THE DRIFT",
        "LEAD THE SIGNAL", "BRAKE THE MOMENTUM", "BALLAST LEFT BEHIND",
        "SPECIMEN SIGNAL LOST", "SHIFT EXPIRED", "FRESH SHAFT ISSUED",
        "ballast-specimen-meter", "ballast-crate-meter", "ballast-specimen-readout",
        "ballast-crate-readout", "ballast-tick", "ballast-velocity",
    )
    for token in forbidden_visible_copy:
        assert token not in frontend
