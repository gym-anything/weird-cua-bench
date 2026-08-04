from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENV_ROOT = BENCHMARK / "environments" / "occlusion_shell_swindle_env"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = _load("occlusion_shell_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = _load("occlusion_shell_materializer", BENCHMARK / "tools" / "materialize_controlled_tasks.py")
GRADER = _load(
    "occlusion_shell_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "occlusion_shell_swindle.py",
)
VERIFIER_HELPERS = _load(
    "occlusion_shell_verifier_helpers",
    BENCHMARK / "shared_runtime" / "verifier_helpers.py",
)
CONTROLS = json.loads((ENV_ROOT / "controls.json").read_text(encoding="utf-8"))
BASE_TASK = json.loads(
    (ENV_ROOT / "tasks" / "occlusion_shell_swindle_seed_0001" / "task.json").read_text(encoding="utf-8")
)


def _task(level: int, interaction: str) -> dict:
    return MATERIALIZER.controlled_task(
        BASE_TASK,
        mechanic_id="occlusion_shell_swindle",
        level=level,
        interaction=interaction,
        profile=CONTROLS["difficulty"][str(level)],
        task_dir_name=f"occlusion_shell_swindle_d{level}_{interaction}_seed_0001",
    )


def _without_control_identity(value: dict) -> dict:
    result = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        result.pop(key, None)
    return result


def _passing_payload(truth: dict, interaction: str) -> dict:
    events: list[dict] = []
    choices: list[dict] = []
    total_ticks = observed_ms = samples = 0

    def push(kind: str, **details) -> None:
        events.append({"sequence": len(events) + 1, "kind": kind, **details})

    for round_index, round_state in enumerate(truth["rounds"]):
        push("round_start", round=round_index)
        if interaction == "simplified":
            push(
                "inspection_relay_arm",
                round=round_index,
                occluder_id=round_state["inspection"]["occluder_id"],
                point=round_state["inspection"]["port"],
                input_source="peephole_relay_choice",
            )
        sample_ticks = set(
            range(
                int(round_state["inspection"]["window_start"]),
                int(round_state["inspection"]["window_start"])
                + int(round_state["inspection"]["minimum_samples"]),
            )
        )
        for tick, frame in enumerate(round_state["frames"], start=1):
            elapsed = int(round_state["preview_ms"]) + tick * int(round_state["tick_ms"])
            push("round_tick", round=round_index, tick=tick, elapsed_ms=elapsed, shells=frame["shells"])
            if tick in sample_ticks:
                push(
                    "inspection_sample",
                    round=round_index,
                    tick=tick,
                    point=round_state["inspection"]["port"],
                    from_shell=round_state["inspection"]["from_shell"],
                    to_shell=round_state["inspection"]["to_shell"],
                    input_source="peephole_relay_choice" if interaction == "simplified" else "direct_cursor",
                )
                samples += 1
            total_ticks += 1
        stopped_at = int(round_state["preview_ms"]) + int(round_state["duration_ms"])
        push("round_stop", round=round_index, elapsed_ms=stopped_at)
        observed_ms += stopped_at
        carrier = round_state["final_carrier"]
        push(
            "round_select",
            round=round_index,
            shell_id=carrier,
            input_source="carrier_controls" if interaction == "simplified" else "direct_shell",
        )
        choices.append({"round": round_index, "shell_id": carrier})
    return {
        "mechanic_id": "occlusion_shell_swindle",
        "challenge_id": truth["challenge_id"],
        "events": events,
        "choices": choices,
        "total_ticks": total_ticks,
        "observed_ms": observed_ms,
        "rounds_completed": len(truth["rounds"]),
        "inspection_samples": samples,
        "rewind_count": 0,
    }


def test_controls_materialize_all_ten_conditions_and_preserve_l2_full(tmp_path: Path) -> None:
    MATERIALIZER.validate_controls(CONTROLS, ENV_ROOT)
    assert CONTROLS["baseline"] == {"difficulty": 2, "interaction": "full", "real_time": "live"}
    written = MATERIALIZER.materialize_environment(ENV_ROOT, tmp_path)
    assert len(written) == 10
    conditions = {
        (
            item["metadata"]["control_condition"]["difficulty"],
            item["metadata"]["control_condition"]["interaction"],
        )
        for item in (json.loads((path / "task.json").read_text(encoding="utf-8")) for path in written)
    }
    assert conditions == {(level, interaction) for level in range(1, 6) for interaction in ("simplified", "full")}

    original_public, original_truth = SETUP.generate_task_state(BASE_TASK, "shell-baseline-preservation")
    baseline_public, baseline_truth = SETUP.generate_task_state(_task(2, "full"), "shell-baseline-preservation")
    assert baseline_public["challenge_id"] == original_public["challenge_id"]
    assert baseline_truth["challenge_id"] == original_truth["challenge_id"]
    assert _without_control_identity(baseline_public) == _without_control_identity(original_public)
    assert _without_control_identity(baseline_truth) == _without_control_identity(original_truth)


def test_difficulty_profiles_change_the_visible_shell_problem_and_interaction_preserves_it() -> None:
    by_level = {}
    for level in range(1, 6):
        simplified_public, simplified_truth = SETUP.generate_task_state(_task(level, "simplified"), "shell-profile-shape")
        full_public, full_truth = SETUP.generate_task_state(_task(level, "full"), "shell-profile-shape")
        assert _without_control_identity(simplified_public) == _without_control_identity(full_public)
        assert _without_control_identity(simplified_truth) == _without_control_identity(full_truth)
        parameters = CONTROLS["difficulty"][str(level)]["parameters"]
        assert len(full_public["rounds"]) == parameters["round_count"]
        assert len(full_public["rounds"][0]["shell_ids"]) in parameters["shell_count_values"]
        assert len(full_public["rounds"][0].get("decoy_ports") or []) == parameters["decoy_port_count"]
        assert full_public["rounds"][0]["inspection"]["minimum_samples"] == parameters["inspection_minimum_samples"]
        by_level[level] = full_public["rounds"][0]

    assert len(by_level[1]["shell_ids"]) < len(by_level[5]["shell_ids"])
    assert by_level[1]["inspection"]["radius"] > by_level[5]["inspection"]["radius"]
    assert len(by_level[1].get("decoy_ports") or []) < len(by_level[5].get("decoy_ports") or [])
    assert SETUP.generate_task_state(_task(1, "full"), "shell-visible-label")[0]["submit_label"] == "CERTIFY ONE TRACK"
    assert SETUP.generate_task_state(_task(4, "full"), "shell-visible-label")[0]["submit_label"] == "CERTIFY 4 TRACKS"


def test_grader_accepts_the_selected_input_surface_and_rejects_the_other() -> None:
    for interaction in ("simplified", "full"):
        public_state, truth = SETUP.generate_task_state(_task(4, interaction), f"shell-{interaction}-replay")
        payload = _passing_payload(truth, interaction)
        assert GRADER.grade(payload, truth, public_state)["passed"] is True
        exported = {"result": payload, "ground_truth": truth, "public_state": public_state}
        assert VERIFIER_HELPERS.verify_external_mechanic(exported, "occlusion_shell_swindle")["passed"] is True

        forged = copy.deepcopy(payload)
        for event in forged["events"]:
            if event["kind"] == "inspection_sample":
                event["input_source"] = "direct_cursor" if interaction == "simplified" else "peephole_relay_choice"
                break
        assert GRADER.grade(forged, truth, public_state)["passed"] is False
        assert VERIFIER_HELPERS.verify_external_mechanic(
            {"result": forged, "ground_truth": truth, "public_state": public_state},
            "occlusion_shell_swindle",
        )["passed"] is False


def test_simplified_relay_samples_must_follow_the_genuine_visible_cover() -> None:
    public_state, truth = SETUP.generate_task_state(_task(4, "simplified"), "shell-relay-choice")
    assert truth["rounds"][0]["decoy_ports"]
    payload = _passing_payload(truth, "simplified")
    forged = copy.deepcopy(payload)
    decoy = truth["rounds"][0]["decoy_ports"][0]
    relay = next(event for event in forged["events"] if event["kind"] == "inspection_relay_arm")
    relay["occluder_id"] = decoy["occluder_id"]
    relay["point"] = decoy["port"]

    grader = GRADER.grade(forged, truth, public_state)
    assert grader["passed"] is False
    assert "selected genuine relay" in grader["feedback"]
    verifier = VERIFIER_HELPERS.verify_external_mechanic(
        {"result": forged, "ground_truth": truth, "public_state": public_state},
        "occlusion_shell_swindle",
    )
    assert verifier["passed"] is False
