from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "reflected_rival_env"
TASK_PATH = ENVIRONMENT / "tasks" / "reflected_rival_seed_0001" / "task.json"
CONTROLS_PATH = ENVIRONMENT / "controls.json"
GENERATOR_PATH = BENCHMARK / "shared_scripts" / "incubator_generators" / "reflected_rival.py"
GRADER_PATH = BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "reflected_rival.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("reflected_rival_generator_test", GENERATOR_PATH)
GRADER = _load("reflected_rival_grader_test", GRADER_PATH)
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


def _payload(public: dict, truth: dict) -> dict:
    """Create a visible-input transcript by replaying the constructive route."""

    board = truth["board"]
    state = {
        "tick": 0,
        "player_lane": int(board["player_start_lane"]),
        "rival_lane": int(board["rival_start_lane"]),
        "player_progress": 0.0,
        "rival_progress": 0.0,
        "player_finish_tick": None,
        "rival_finish_tick": None,
    }
    commands = [int(value) for value in truth["solution_commands"]]
    next_command = 1
    actions = []
    source = "direction_buttons" if truth["control_condition"]["interaction"] == "simplified" else "keyboard"
    while state["tick"] < int(board["max_ticks"]):
        player_segment = min(int(board["segment_count"]) - 1, int(state["player_progress"]))
        if next_command < int(board["segment_count"]) and player_segment >= next_command:
            direction = commands[next_command]
            next_command += 1
            if direction:
                actions.append(
                    {
                        "sequence": len(actions) + 1,
                        "tick": state["tick"],
                        "direction": "left" if direction < 0 else "right",
                        "input_source": source,
                    }
                )
                GRADER._move(state, "left" if direction < 0 else "right", board)
        GRADER._advance(state, board)
        if state["player_finish_tick"] is not None and state["rival_finish_tick"] is not None:
            break
    return {
        "mechanic_id": "reflected_rival",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "actions": actions,
        "final_tick": state["tick"],
        "completed": True,
    }


def _world(public: dict) -> dict:
    return copy.deepcopy(public["board"])


def test_controls_and_split_cover_both_execution_schedules(tmp_path) -> None:
    from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment
    assert CONTROLS["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert set(CONTROLS["difficulty"]) == {"1", "2", "3", "4", "5"}
    assert all(CONTROLS["interaction"][mode]["implemented"] for mode in ("simplified", "full"))
    split = json.loads((BENCHMARK / "splits" / "reflected_rival_split.json").read_text(encoding="utf-8"))
    written = materialize_environment(BENCHMARK / "environments/reflected_rival_env", tmp_path)
    assert len(written) == 10
    assert len(split["variations_tasks"]) == 20
    assert set(split["variations_tasks"]) == {p.name + suffix for p in written for suffix in ("", "_tpaused")}
    assert all(
        json.loads((p / "task.json").read_text(encoding="utf-8"))["metadata"]["control_condition"]["real_time"]
        == "live"
        for p in written
    )


@pytest.mark.parametrize("level", range(1, 6))
def test_interactions_share_the_generated_world_and_replay_wins(level: int) -> None:
    full_public, full_truth = GENERATOR.generate(_controlled_task(level, "full"), f"reflected-pair-{level}")
    simple_public, simple_truth = GENERATOR.generate(_controlled_task(level, "simplified"), f"reflected-pair-{level}")
    assert _world(full_public) == _world(simple_public)
    assert full_truth["constructive_replay"]["player_wins"] is True
    assert simple_truth["constructive_replay"]["player_wins"] is True
    for public, truth in ((full_public, full_truth), (simple_public, simple_truth)):
        assert public["board"] == truth["board"]
        assert "solution_commands" not in public
        result = _payload(public, truth)
        graded = GRADER.grade(result, truth, public)
        assert graded["passed"] is True, graded


def test_baseline_matches_l4_full_world_and_live_paused_are_time_only() -> None:
    baseline_public, baseline_truth = GENERATOR.generate(TASK, "reflected-baseline")
    controlled_public, _controlled_truth = GENERATOR.generate(_controlled_task(4, "full"), "reflected-baseline")
    paused_public, _paused_truth = GENERATOR.generate(_controlled_task(4, "full", "paused"), "reflected-baseline")
    assert baseline_public["board"] == controlled_public["board"]
    assert paused_public["board"] == controlled_public["board"]
    assert baseline_truth["board"] == controlled_public["board"]


def test_grader_rejects_stale_surface_and_malformed_transcripts() -> None:
    public, truth = GENERATOR.generate(_controlled_task(4, "simplified"), "reflected-negative")
    result = _payload(public, truth)
    for change in (
        {"challenge_id": "stale"},
        {"task_id": "other"},
        {"actions": []},
        {"completed": False},
        {"final_tick": 0},
    ):
        assert GRADER.grade(dict(result, **change), truth, public)["passed"] is False
    wrong_source = copy.deepcopy(result)
    wrong_source["actions"][0]["input_source"] = "keyboard"
    assert GRADER.grade(wrong_source, truth, public)["passed"] is False
    forged_public = copy.deepcopy(public)
    forged_public["board"]["course"][0]["cells"][0]["multiplier"] += 0.1
    assert GRADER.grade(result, truth, forged_public)["passed"] is False


def test_source_contract_and_task_prompt_keep_the_visible_ui_boundary() -> None:
    source = (BENCHMARK / "shared_runtime" / "app" / "mechanics" / "reflected_rival.js").read_text(encoding="utf-8")
    prompt = str(TASK["natural_language"])
    for phrase in ("data-rr-direction", "data-rr-abandon", "ArrowLeft", "WHITE", "BLUE"):
        assert phrase in source
    for phrase in ("screenshots", "visible controls", "Developer Tools", "DOM", "terminal", "unrelated tabs"):
        assert phrase in prompt
    assert "WeirdCaptchaTime" not in source


@pytest.mark.parametrize("bad_tick", [True, 1.5, "1", float("inf"), None])
def test_grader_rejects_noninteger_ticks_without_coercion(bad_tick) -> None:
    public, truth = GENERATOR.generate(_controlled_task(4, "full"), "reflected-numeric")
    result = _payload(public, truth)
    assert not GRADER.grade(dict(result, final_tick=bad_tick), truth, public)["passed"]
    result["actions"][0]["tick"] = bad_tick
    assert not GRADER.grade(result, truth, public)["passed"]


def test_terminal_replay_matches_browser_stop_and_rejects_later_input() -> None:
    public, truth = GENERATOR.generate(_controlled_task(4, "full"), "reflected-terminal")
    result = _payload(public, truth)
    state = GRADER.replay(truth["board"], result["actions"], result["final_tick"])
    assert GRADER.grade(result, truth, public)["passed"]
    stopped_progress = state["player_progress"], state["rival_progress"]
    GRADER._advance(state, truth["board"])
    assert stopped_progress == (state["player_progress"], state["rival_progress"])
    assert not GRADER.grade(dict(result, final_tick=result["final_tick"] + 1), truth, public)["passed"]
    result["actions"].append({"sequence": len(result["actions"]) + 1,
                              "tick": result["final_tick"], "direction": "left",
                              "input_source": "keyboard"})
    assert not GRADER.grade(result, truth, public)["passed"]
