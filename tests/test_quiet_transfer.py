from __future__ import annotations

import copy
import importlib.util
import json
import math
import shutil
from pathlib import Path


BENCHMARK = Path(__file__).resolve().parents[1] / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "quiet_transfer_env"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load(
    "quiet_transfer_test_generator",
    BENCHMARK / "shared_scripts" / "incubator_generators" / "quiet_transfer.py",
)
GRADER = _load(
    "quiet_transfer_test_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "quiet_transfer.py",
)
VERIFIER = _load(
    "quiet_transfer_test_verifier",
    ENVIRONMENT / "tasks" / "quiet_transfer_seed_0001" / "verifier.py",
)


def _task(level: int, interaction: str) -> dict:
    from weird_captcha_gym.tools.materialize_controlled_tasks import controlled_task
    base = json.loads((ENVIRONMENT / "tasks/quiet_transfer_seed_0001/task.json").read_text())
    controls = json.loads((ENVIRONMENT / "controls.json").read_text())
    task = controlled_task(base, mechanic_id="quiet_transfer", level=level,
                           interaction=interaction, profile=controls["difficulty"][str(level)],
                           task_dir_name=f"quiet_transfer_d{level}_{interaction}_seed_0001")
    task["_control_condition"] = copy.deepcopy(task["metadata"]["control_condition"])
    return task


def _accepted_submission(task: dict, seed: str) -> tuple[dict, dict, dict]:
    public, truth = GENERATOR.generate(task, seed)
    target = [float(value) for value in truth["target_curve"]]
    current = [float(value) for value in public["curve"]["initial"]]
    events: list[dict] = []

    def add(event_type: str, **fields) -> None:
        events.append({"seq": len(events) + 1, "type": event_type, **fields})

    source = "curve_drag" if public["interaction_mode"] == "full" else "nudge_buttons"
    def edit(index: int, target_value: float) -> None:
        while abs(current[index] - target_value) > 0.0005:
            before = current[index]
            if source == "nudge_buttons":
                step = public["curve"]["nudge_step"]
                grid = math.floor(before / step + 1e-7) + 1 if target_value > before else math.ceil(before / step - 1e-7) - 1
                after = round(max(0.05, min(0.95, grid * step)), 3)
            else:
                after = target_value
            add("curve_edit", index=index, before=before, after=after, input_source=source)
            current[index] = after

    trial = current[:]
    trial_index = max(1, (len(trial) - 1) // 2)
    if abs(trial[trial_index] - target[trial_index]) < 0.001:
        step = float(public["curve"]["nudge_step"])
        trial[trial_index] = min(
            float(public["curve"]["maximum"]),
            round(trial[trial_index] + 2.0 * step, 4),
        )
        if abs(trial[trial_index] - current[trial_index]) < 0.001:
            trial[trial_index] = max(
                float(public["curve"]["minimum"]),
                round(trial[trial_index] - 4.0 * step, 4),
            )
    if any(abs(trial[index] - current[index]) > 0.001 for index in range(1, len(trial) - 1)):
        for index in range(1, len(trial) - 1):
            if abs(trial[index] - current[index]) <= 0.001:
                continue
            edit(index, trial[index])
    add("run_start", curve=trial, input_source="run_button")
    states = GRADER.simulate(trial, public)
    for state in states[1:]:
        add("playback_sample", tick=state["tick"], state=state)
    add(
        "run_complete",
        ticks=public["curve"]["playback_ticks"],
        curve=trial,
        state=states[-1],
    )
    for index in range(1, len(target) - 1):
        if abs(target[index] - current[index]) <= 0.001:
            continue
        edit(index, target[index])
    add("run_start", curve=target, input_source="run_button")
    states = GRADER.simulate(target, public)
    for state in states[1:]:
        add("playback_sample", tick=state["tick"], state=state)
    add(
        "run_complete",
        ticks=public["curve"]["playback_ticks"],
        curve=target,
        state=states[-1],
    )
    result = {
        "mechanic_id": "quiet_transfer",
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction": public["interaction_mode"],
        "curve": target,
        "events": events,
        "completed": True,
    }
    return result, truth, public


def test_all_controlled_levels_and_modes_replay_with_their_active_parameters() -> None:
    for level in range(1, 6):
        for interaction in ("full", "simplified"):
            result, truth, public = _accepted_submission(_task(level, interaction), f"all-{level}-{interaction}")
            decision = GRADER.grade(result, truth, public)
            assert decision["passed"] is True, (level, interaction, decision)
            assert len(public["curve"]["initial"]) == int(
                json.loads((ENVIRONMENT / "controls.json").read_text())["difficulty"][str(level)]["parameters"]["knot_count"]
            )


def test_full_and_simplified_preserve_the_same_generated_world_and_goal() -> None:
    for level in range(1, 6):
        full, full_truth = GENERATOR.generate(_task(level, "full"), f"paired-{level}")
        simplified, simplified_truth = GENERATOR.generate(_task(level, "simplified"), f"paired-{level}")
        for state in (full, simplified):
            for field in ("task_id", "challenge_id", "prompt", "interaction_mode", "control_condition"):
                state.pop(field, None)
        for state in (full_truth, simplified_truth):
            for field in ("task_id", "challenge_id", "prompt", "interaction_mode", "control_condition"):
                state.pop(field, None)
        assert full == simplified
        assert full_truth == simplified_truth


def test_unconditioned_l3_baseline_matches_the_controlled_l3_full_world() -> None:
    base_task = json.loads(
        (ENVIRONMENT / "tasks" / "quiet_transfer_seed_0001" / "task.json").read_text(encoding="utf-8")
    )
    baseline, baseline_truth = GENERATOR.generate(base_task, "baseline-equivalence")
    controlled, controlled_truth = GENERATOR.generate(_task(3, "full"), "baseline-equivalence")
    for state in (baseline, controlled):
        for field in ("task_id", "challenge_id", "prompt", "interaction_mode", "control_condition"):
            state.pop(field, None)
    for state in (baseline_truth, controlled_truth):
        for field in ("task_id", "challenge_id", "prompt", "interaction_mode", "control_condition"):
            state.pop(field, None)
    assert baseline == controlled
    assert baseline_truth == controlled_truth


def test_grader_rejects_wrong_surface_stale_challenge_and_incomplete_playback() -> None:
    result, truth, public = _accepted_submission(_task(3, "full"), "negative-contract")

    wrong_surface = copy.deepcopy(result)
    wrong_surface["interaction"] = "simplified"
    assert GRADER.grade(wrong_surface, truth, public)["passed"] is False

    wrong_event_source = copy.deepcopy(result)
    next(edit for edit in wrong_event_source["events"] if edit["type"] == "curve_edit")["input_source"] = "nudge_buttons"
    assert GRADER.grade(wrong_event_source, truth, public)["passed"] is False

    stale = copy.deepcopy(result)
    stale["challenge_id"] = "stale-challenge"
    assert GRADER.grade(stale, truth, public)["passed"] is False

    incomplete = copy.deepcopy(result)
    incomplete["events"] = [event for event in incomplete["events"] if event["type"] != "playback_sample" and event["type"] != "run_complete"]
    assert GRADER.grade(incomplete, truth, public)["passed"] is False

    single_playback = copy.deepcopy(result)
    first_complete = next(
        index for index, event in enumerate(single_playback["events"]) if event["type"] == "run_complete"
    )
    single_playback["events"] = single_playback["events"][: first_complete + 1]
    single_playback["curve"] = list(single_playback["events"][-1]["curve"])
    assert GRADER.grade(single_playback, truth, public)["passed"] is False

    trailing_edit = copy.deepcopy(result)
    trailing_edit["events"].append(
        {
            "seq": len(trailing_edit["events"]) + 1,
            "type": "curve_edit",
            "index": 1,
            "before": trailing_edit["curve"][1],
            "after": trailing_edit["curve"][1] + 0.01,
            "input_source": "curve_drag",
        }
    )
    trailing_edit["curve"][1] += 0.01
    assert GRADER.grade(trailing_edit, truth, public)["passed"] is False

    partial_later_run = copy.deepcopy(result)
    partial_later_run["events"].extend(
        [
            {
                "seq": len(partial_later_run["events"]) + 1,
                "type": "run_start",
                "curve": partial_later_run["curve"],
                "input_source": "run_button",
            },
            {
                "seq": len(partial_later_run["events"]) + 2,
                "type": "playback_sample",
                "tick": 1,
                "state": GRADER.simulate(partial_later_run["curve"], public)[1],
            },
        ]
    )
    assert GRADER.grade(partial_later_run, truth, public)["passed"] is False


def test_grader_uses_the_public_goal_state_not_a_private_route_match() -> None:
    result, truth, public = _accepted_submission(_task(3, "full"), "public-goal-contract")
    altered_truth = copy.deepcopy(truth)
    altered_truth["target_curve"] = [float(value) for value in public["curve"]["initial"]]
    decision = GRADER.grade(result, altered_truth, public)
    assert decision["passed"] is True, decision
    assert "visible goal fidelity" in decision["feedback"]


def test_exported_verifier_replays_the_same_result(tmp_path: Path) -> None:
    result, truth, public = _accepted_submission(_task(3, "full"), "exported-verifier")
    exported_path = tmp_path / "task_result.json"
    exported_path.write_text(
        json.dumps({"result": result, "ground_truth": truth, "public_state": public}),
        encoding="utf-8",
    )

    def copy_from_env(source: str, destination: str) -> None:
        assert source == "/tmp/task_result.json"
        shutil.copyfile(exported_path, destination)

    decision = VERIFIER.verify_task(env_info={"copy_from_env": copy_from_env})
    assert decision["passed"] is True, decision


def test_sparse_drag_is_valid_but_proxy_teleport_is_not() -> None:
    for mode in ("full", "simplified"):
        result, truth, public = _accepted_submission(_task(3, mode), "sparse-drag")
        before = public["curve"]["initial"][1]
        source = "curve_drag" if mode == "full" else "nudge_buttons"
        edits = [
            {"type": "curve_edit", "index": 1, "before": before, "after": 0.95, "input_source": source},
            {"type": "curve_edit", "index": 1, "before": 0.95, "after": before, "input_source": source},
        ]
        result["events"] = edits + result["events"]
        for seq, event in enumerate(result["events"], 1):
            event["seq"] = seq
        decision = GRADER.grade(result, truth, public)
        assert decision["passed"] is (mode == "full"), decision


def test_malformed_completion_rejects_without_raising(tmp_path: Path) -> None:
    result, truth, public = _accepted_submission(_task(3, "full"), "malformed-completion")
    for field, value in (("curve", []), ("curve", result["curve"] + [0.5]), ("ticks", "bad"), ("ticks", 44.5)):
        malformed = copy.deepcopy(result)
        malformed["events"][-1][field] = value
        assert GRADER.grade(malformed, truth, public)["passed"] is False
        exported = tmp_path / "malformed.json"
        exported.write_text(json.dumps({"result": malformed, "ground_truth": truth, "public_state": public}))
        def copy_from_env(source: str, destination: str) -> None:
            shutil.copyfile(exported, destination)
        assert VERIFIER.verify_task(env_info={"copy_from_env": copy_from_env})["passed"] is False


def test_initial_knots_stay_inside_bounds_and_on_the_nudge_grid() -> None:
    for level in range(1, 6):
        for seed in range(100):
            public, truth = GENERATOR.generate(_task(level, "simplified"), f"bounds-{seed}")
            curve = public["curve"]
            for knot in curve["initial"][1:-1]:
                assert curve["minimum"] <= knot <= curve["maximum"]
                assert abs(knot / curve["nudge_step"] - round(knot / curve["nudge_step"])) < 1e-6
            assert GRADER.simulate(truth["target_curve"], public)[-1]["fidelity"] == 1.0
