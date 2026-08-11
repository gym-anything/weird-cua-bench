from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "rorschach_fixed_rubric_env"
MECHANIC = "rorschach_fixed_rubric"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = _load("rorschach_control_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = _load("rorschach_control_materializer", BENCHMARK / "tools" / "materialize_controlled_tasks.py")
GRADER = _load(
    "rorschach_control_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py",
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


CONTROLS = _read(ENVIRONMENT / "controls.json")
BASE = _read(ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json")


def _task(level: int, interaction: str) -> dict:
    return MATERIALIZER.controlled_task(
        BASE,
        mechanic_id=MECHANIC,
        level=level,
        interaction=interaction,
        profile=CONTROLS["difficulty"][str(level)],
        task_dir_name=f"{MECHANIC}_d{level}_{interaction}_seed_0001",
    )


def _without_identity(value: dict) -> dict:
    copied = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        copied.pop(key, None)
    return copied


def _passing_payload(public: dict, truth: dict, interaction: str) -> dict:
    events: list[dict] = []
    observed: list[str] = []
    fold_samples = pressure_holds = thermal_pulses = stamp_moves = 0
    tick_total = 0

    def record(kind: str, **details: object) -> None:
        events.append({"sequence": len(events) + 1, "kind": kind, **details})

    cycles = {
        (str(cycle["blot_id"]), str(cycle["tool"])): cycle
        for cycle in truth["cycles"]
    }
    for blot in truth["blot_rects"]:
        blot_id = str(blot["id"])
        for tool in truth["required_tools"]:
            record("select", blot_id=blot_id)
            if interaction == "simplified":
                record("proxy_probe", tool=tool, input_source="labelled_tool_proxy")
            elif tool == "FOLD":
                record("fold_start", value=0, input_source="direct_fold_sweep")
                record("fold_move", value=260, input_source="direct_fold_sweep")
                fold_samples += 1
                record("fold_end", value=260, input_source="direct_fold_sweep")
            elif tool == "PRESSURE":
                record("pressure_down", input_source="direct_pressure_hold")
                record(
                    "pressure_up",
                    duration_ms=int(truth["pressure_min_ms"]) + 20,
                    input_source="direct_pressure_hold",
                )
                pressure_holds += 1
            else:
                record("thermal_pulse", polarity="COOL", input_source="direct_cooling_pulse")
                thermal_pulses += 1
            record("probe", blot_id=blot_id, tool=tool)
            for frame in cycles[(blot_id, tool)]["frames"]:
                tick = int(frame["tick"])
                record(
                    "tick",
                    blot_id=blot_id,
                    tool=tool,
                    tick=tick,
                    elapsed_ms=tick * int(public["tick_ms"]),
                    snapshot=frame["snapshot"],
                )
                tick_total += 1
            record("cycle_complete", blot_id=blot_id, tool=tool, elapsed_ms=int(truth["ticks_per_cycle"]) * 65)
            observed.append(f"{blot_id}|{tool}")

    culprit = str(truth["culprit_id"])
    if interaction == "simplified":
        record("select", blot_id=culprit)
        record("proxy_stamp", blot_id=culprit, input_source="selected_card_stamp_proxy")
    else:
        record("stamp_down", point=[400, 330], input_source="direct_stamp_drag")
        record("stamp_move", point=[130, 145], input_source="direct_stamp_drag")
        stamp_moves += 1
        target = next(rect for rect in truth["blot_rects"] if rect["id"] == culprit)
        record(
            "stamp_up",
            point=[int(target["x"]) + int(target["width"]) // 2, int(target["y"]) + int(target["height"]) // 2],
            input_source="direct_stamp_drag",
        )
    return {
        "mechanic_id": MECHANIC,
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction": interaction,
        "events": events,
        "observation_keys": sorted(observed),
        "observation_count": len(observed),
        "tick_total": tick_total,
        "fold_samples": fold_samples,
        "pressure_holds": pressure_holds,
        "thermal_pulses": thermal_pulses,
        "stamp_moves": stamp_moves,
        "stamped_id": culprit,
        "reset_count": 0,
        "completed": True,
    }


def test_rorschach_controls_materialize_and_preserve_the_original_l4_full_world(tmp_path: Path) -> None:
    MATERIALIZER.validate_controls(CONTROLS, ENVIRONMENT)
    written = MATERIALIZER.materialize_environment(ENVIRONMENT, tmp_path)
    assert len(written) == 10
    for seed in ("rorschach-baseline-a", "rorschach-baseline-b", "rorschach-baseline-c"):
        original_public, original_truth = SETUP.generate_task_state(BASE, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(_task(4, "full"), seed)
        assert _without_identity(baseline_public) == _without_identity(original_public)
        assert _without_identity(baseline_truth) == _without_identity(original_truth)


def test_rorschach_profiles_change_the_response_matrix_and_keep_interaction_worlds_identical() -> None:
    expected = {
        1: (2, 1, 5),
        2: (3, 1, 5),
        3: (4, 2, 6),
        4: (5, 2, 7),
        5: (5, 3, 9),
    }
    for level, (specimen_count, tool_count, ticks) in expected.items():
        simple_public, simple_truth = SETUP.generate_task_state(_task(level, "simplified"), f"rorschach-profile-{level}")
        full_public, full_truth = SETUP.generate_task_state(_task(level, "full"), f"rorschach-profile-{level}")
        assert _without_identity(simple_public) == _without_identity(full_public)
        assert _without_identity(simple_truth) == _without_identity(full_truth)
        assert len(simple_public["blots"]) == specimen_count
        assert len(simple_public["required_tools"]) == tool_count
        assert len(simple_public["cycles"]) == specimen_count * tool_count
        assert simple_public["ticks_per_cycle"] == ticks
        assert simple_public["tick_ms"] == CONTROLS["difficulty"][str(level)]["parameters"]["tick_ms"]
        assert simple_truth["fold_min_distance"] == CONTROLS["difficulty"][str(level)]["parameters"]["fold_min_distance"]
        assert simple_truth["pressure_min_ms"] == CONTROLS["difficulty"][str(level)]["parameters"]["pressure_min_ms"]
        assert simple_public["observations_required"] == specimen_count * tool_count
        assert sum(
            set(simple_truth["signatures"]).issubset(set(values))
            for values in simple_truth["response_signatures"].values()
        ) == 1


def test_rorschach_grader_accepts_all_ten_surfaces_and_rejects_cross_surface_transcripts() -> None:
    for level in range(1, 6):
        simple_public, simple_truth = SETUP.generate_task_state(_task(level, "simplified"), f"rorschach-replay-{level}")
        full_public, full_truth = SETUP.generate_task_state(_task(level, "full"), f"rorschach-replay-{level}")
        simple_payload = _passing_payload(simple_public, simple_truth, "simplified")
        full_payload = _passing_payload(full_public, full_truth, "full")
        assert GRADER.grade(simple_payload, simple_truth, simple_public)["passed"] is True
        assert GRADER.grade(full_payload, full_truth, full_public)["passed"] is True

        # Preserve the selected task identity while replaying events generated
        # from the other input surface.  This exercises the input-surface
        # binding instead of merely failing the stale-challenge check.
        wrong_direct = copy.deepcopy(full_payload)
        wrong_direct["task_id"] = simple_public["task_id"]
        wrong_direct["challenge_id"] = simple_public["challenge_id"]
        wrong_direct["interaction"] = "simplified"
        direct_result = GRADER.grade(wrong_direct, simple_truth, simple_public)
        assert direct_result["passed"] is False
        assert direct_result["feedback"] == "material operation used the wrong interaction input"
        wrong_proxy = copy.deepcopy(simple_payload)
        wrong_proxy["task_id"] = full_public["task_id"]
        wrong_proxy["challenge_id"] = full_public["challenge_id"]
        wrong_proxy["interaction"] = "full"
        proxy_result = GRADER.grade(wrong_proxy, full_truth, full_public)
        assert proxy_result["passed"] is False
        assert proxy_result["feedback"] == "material test proxy is not valid for the selected specimen"


def test_rorschach_grader_binds_each_profile_response_cadence() -> None:
    for level in range(1, 6):
        for interaction in ("simplified", "full"):
            public, truth = SETUP.generate_task_state(
                _task(level, interaction), f"rorschach-cadence-{level}-{interaction}"
            )
            payload = _passing_payload(public, truth, interaction)
            assert GRADER.grade(payload, truth, public)["passed"] is True
            accelerated = copy.deepcopy(payload)
            first_tick = next(event for event in accelerated["events"] if event["kind"] == "tick")
            first_tick["elapsed_ms"] = int(public["tick_ms"]) - 1
            rejected = GRADER.grade(accelerated, truth, public)
            assert rejected["passed"] is False
            assert rejected["feedback"] == "transient response was not observed long enough"


def test_rorschach_response_cycle_registers_and_settles_the_shared_paused_action() -> None:
    source = (BENCHMARK / "shared_runtime" / "app" / "mechanics" / f"{MECHANIC}.js").read_text(
        encoding="utf-8"
    )
    assert 'model.helpers.beginAction?.(`material-response:${blotId}:${tool}`)' in source
    assert "const action = model.activeAction;" in source
    assert "model.activeAction = null;" in source
    assert "action?.settle();" in source
    assert "model.activeAction?.settle();" in source
