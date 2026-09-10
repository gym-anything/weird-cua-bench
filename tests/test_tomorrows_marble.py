from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1] / "weird_captcha_gym"
ENV = ROOT / "environments" / "tomorrows_marble_env"
MECHANIC = "tomorrows_marble"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GEN = _load("tomorrows_marble_generator_test", ROOT / "shared_scripts/incubator_generators" / f"{MECHANIC}.py")
GRADE = _load("tomorrows_marble_grader_test", ROOT / "shared_runtime/server/incubator_graders" / f"{MECHANIC}.py")
CONTROLS = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
TASK = json.loads((ENV / "tasks" / "tomorrows_marble_seed_0001" / "task.json").read_text(encoding="utf-8"))


def _condition(level: int, interaction: str = "full", real_time: str = "live") -> dict:
    return {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(CONTROLS["difficulty"][str(level)]["parameters"]),
    }


def _state(level: int | None = None, interaction: str = "full", real_time: str = "live", seed: str = "test-seed"):
    level = int(level if level is not None else CONTROLS["baseline"]["difficulty"])
    task = copy.deepcopy(TASK)
    task["_control_condition"] = _condition(level, interaction, real_time)
    return GEN.generate(task, seed)


def _uncontrolled(public: dict) -> dict:
    result = copy.deepcopy(public)
    result.pop("control_condition", None)
    result.pop("interaction_mode", None)
    result.pop("real_time_mode", None)
    return result


def _payload(public: dict, truth: dict, schedule: list[dict] | None = None, *, source: str | None = None) -> dict:
    schedule = copy.deepcopy(schedule if schedule is not None else truth["solution_schedule"])
    source = source or ("timeline_click" if truth["control_condition"]["interaction"] == "simplified" else "timeline_drag")
    events = [
        {"seq": index, "type": "schedule", "input_source": source, "arrival_id": f"a{index}", "node": node}
        for index, node in enumerate(schedule, start=1)
    ]
    replay = GRADE.replay(schedule, public)
    events.append({"seq": len(events) + 1, "type": "run", "input_source": "run_button", "schedule": schedule, "summary": replay})
    return {
        "mechanic_id": MECHANIC,
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "interaction_mode": truth["control_condition"]["interaction"],
        "completed": True,
        "events": events,
    }


def test_baseline_uses_the_selected_public_task_and_preserves_world() -> None:
    base_public, _base_truth = GEN.generate(TASK, "same-seed")
    controlled_public, _controlled_truth = _state(seed="same-seed")
    assert base_public["public_name"] == "Tomorrow's Marble"
    assert base_public["source_anchors"] == ["XART-111"]
    assert "solution_schedule" not in base_public
    assert _uncontrolled(base_public) == _uncontrolled(controlled_public)


@pytest.mark.parametrize("level", range(1, 6))
@pytest.mark.parametrize("interaction", ["full", "simplified"])
@pytest.mark.parametrize("real_time", ["live", "paused"])
def test_ten_controlled_variants_keep_world_and_solution(level: int, interaction: str, real_time: str) -> None:
    public, truth = _state(level, interaction, real_time, seed="parity-seed")
    peer_public, peer_truth = _state(level, "simplified" if interaction == "full" else "full", "paused" if real_time == "live" else "live", seed="parity-seed")
    assert _uncontrolled(public) == _uncontrolled(peer_public)
    assert truth["solution_schedule"] == peer_truth["solution_schedule"]
    assert public["control_condition"]["interaction"] == interaction
    assert public["control_condition"]["real_time"] == real_time
    assert GRADE.grade(_payload(public, truth), truth, public)["passed"] is True


def test_transcript_requires_the_selected_input_surface_and_fresh_identity() -> None:
    public, truth = _state(3, "full", "live", seed="transcript-seed")
    payload = _payload(public, truth)
    assert GRADE.grade(payload, truth, public)["passed"] is True

    wrong_source = copy.deepcopy(payload)
    wrong_source["events"][0]["input_source"] = "timeline_click"
    assert GRADE.grade(wrong_source, truth, public)["passed"] is False

    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "old-challenge"
    assert GRADE.grade(stale, truth, public)["passed"] is False

    bad_summary = copy.deepcopy(payload)
    bad_summary["events"][-1]["summary"]["passed"] = False
    assert GRADE.grade(bad_summary, truth, public)["passed"] is False


def test_self_consistent_unassigned_loop_does_not_pass() -> None:
    public, truth = _state(3, "simplified", "paused", seed="unassigned-seed")
    schedule = copy.deepcopy(truth["solution_schedule"])
    schedule[0]["slot"] = (schedule[0]["slot"] + 1) % public["timeline_slots"]
    if schedule[0] == truth["solution_schedule"][1]:
        schedule[0]["slot"] = (schedule[0]["slot"] + 1) % public["timeline_slots"]
    payload = _payload(public, truth, schedule=schedule)
    assert GRADE.grade(payload, truth, public)["passed"] is False


def test_wrong_early_handoff_changes_later_departures() -> None:
    public, truth = _state(2, "full", "live", seed="stateful-dependency-seed")
    solution = sorted(truth["solution_schedule"], key=lambda node: (node["slot"], node["machine_index"], node["piece_index"]))
    occupied = {(node["machine_index"], node["piece_index"], node["slot"]) for node in solution}
    first = solution[0]
    replacement = next(
        {
            "machine_index": first["machine_index"],
            "piece_index": piece,
            "slot": first["slot"],
        }
        for piece in range(len(public["pieces"]))
        if (first["machine_index"], piece, first["slot"]) not in occupied
    )
    bad = copy.deepcopy(solution)
    bad[0] = replacement
    good_replay = GRADE.replay(solution, public)
    bad_replay = GRADE.replay(bad, public)
    assert good_replay["passed"] is True
    assert bad_replay["passed"] is False
    assert bad_replay["handoff_trace"][0]["matched"] is False
    assert bad_replay["later_departures_shifted"] is True
    assert any(
        bad_replay["departures"][index]["destination"] != good_replay["departures"][index]["destination"]
        for index in range(1, len(solution))
    )


def test_origin_identity_and_handoff_state_are_visible_in_the_runtime() -> None:
    mechanic = (ROOT / "shared_runtime" / "app" / "mechanics" / "tomorrows_marble.js").read_text(encoding="utf-8")
    assert "ORIGIN ·" in mechanic
    assert "is-origin-piece" in mechanic
    assert "tm-handoff-box" in mechanic
    assert "tm-map-hidden" in mechanic
    assert "tm-rule-reveal" in mechanic
    assert "handoff_trace" in mechanic


def test_normal_surface_does_not_render_development_guidance_or_answer_diagnostics() -> None:
    mechanic = (ROOT / "shared_runtime" / "app" / "mechanics" / "tomorrows_marble.js").read_text(encoding="utf-8")
    assert "tm-help" not in mechanic
    assert "tm-anchor-note" not in mechanic
    assert "missing.concat(orphan)" not in mechanic
    assert "REVISE AND RUN" not in mechanic
    assert "RUN TO TEST THE ECHO" not in mechanic
    assert 'model.schedule.length} / ${Number(state.required_entries' not in mechanic
    assert 'id="tm-ledger-count">ARRIVALS' in mechanic


def test_visible_rules_are_sufficient_for_independent_replay() -> None:
    public, truth = _state(5, "full", "live", seed="visible-rules-seed")
    replay = GRADE.replay(truth["solution_schedule"], public)
    assert replay["passed"] is True
    assert replay["arrival_count"] == public["required_entries"] == 12
    assert all("solution_schedule" not in value for value in (public,))
    assert all("destination" not in phase and "delay" not in phase for phase in public["handoff_program"])
    altered = copy.deepcopy(public)
    altered["machines"][0]["next_machine_index"] = (int(altered["machines"][0]["next_machine_index"]) + 1) % 4
    altered_replay = GRADE.replay(truth["solution_schedule"], altered)
    assert altered_replay["passed"] is False
    assert altered_replay["departures"] != replay["departures"]


def test_control_and_split_files_cover_the_required_matrix() -> None:
    split = json.loads((ROOT / "splits" / "tomorrows_marble_split.json").read_text(encoding="utf-8"))
    assert len(split["variations_tasks"]) == 20
    assert set(CONTROLS["baseline"]) == {"difficulty", "interaction", "real_time"}
    assert CONTROLS["baseline"] == {"difficulty": 2, "interaction": "full", "real_time": "live"}
    assert all(CONTROLS["difficulty"][str(level)]["parameters"]["required_entries"] > 0 for level in range(1, 6))


def test_profiles_make_handoff_dependency_active_at_each_level() -> None:
    profiles = [CONTROLS["difficulty"][str(level)]["parameters"] for level in range(1, 6)]
    assert profiles[1]["timeline_slots"] == 10
    assert profiles[1]["loop_count"] == 2
    assert profiles[1]["piece_count"] == 3
    assert profiles[1]["required_entries"] == 8
    assert [profile["handoff_memory"] for profile in profiles] == [1, 2, 3, 4, 5]
    assert [profile["handoff_carry_modulus"] for profile in profiles] == [2, 3, 3, 4, 5]
    assert all(profile["handoff_slot_shift"] > 0 for profile in profiles)
    assert all("handoff_program" in _state(level, seed=f"profile-{level}")[0] for level in range(1, 6))
