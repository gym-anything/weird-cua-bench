from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENV_ROOT = BENCHMARK / "environments" / "clockwork_clutch_safe_env"
TASK_ROOT = ENV_ROOT / "tasks" / "clockwork_clutch_safe_seed_0001"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = load_module("clockwork_controlled_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = load_module(
    "clockwork_controlled_materializer",
    BENCHMARK / "tools" / "materialize_controlled_tasks.py",
)
GRADER = load_module(
    "clockwork_controlled_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "clockwork_clutch_safe.py",
)
VERIFIER = load_module("clockwork_controlled_verifier", TASK_ROOT / "verifier.py")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def controlled_task(level: int, interaction: str) -> dict:
    controls = read_json(ENV_ROOT / "controls.json")
    return MATERIALIZER.controlled_task(
        read_json(TASK_ROOT / "task.json"),
        mechanic_id="clockwork_clutch_safe",
        level=level,
        interaction=interaction,
        profile=controls["difficulty"][str(level)],
        task_dir_name=f"clockwork_clutch_safe_d{level}_{interaction}_seed_0001",
    )


def without_control_identity(value: dict) -> dict:
    normalized = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        normalized.pop(key, None)
    return normalized


def passing_payload(public: dict, truth: dict, input_source: str) -> dict:
    shafts = copy.deepcopy(public["shafts"])
    physics = public["physics"]
    active = len(shafts)
    last_tick = 0
    events = [{"seq": 1, "type": "drive", "tick": 0, "running": True}]
    for release in truth["release_schedule"]:
        tick = int(release["tick"])
        factor = float(physics["load_numerator"]) / active
        for shaft in shafts:
            if shaft["engaged"]:
                shaft["angle_deg"] = (
                    float(shaft["angle_deg"])
                    + (tick - last_tick)
                    * float(shaft["ratio"])
                    * float(physics["drive_deg_per_tick"])
                    * factor
                ) % 360
        index = int(release["shaft"])
        before = bool(shafts[index]["engaged"])
        shafts[index]["engaged"] = not before
        active -= 1
        events.append({
            "seq": len(events) + 1,
            "type": "clutch",
            "tick": tick,
            "shaft": index,
            "before": before,
            "after": bool(shafts[index]["engaged"]),
            "angle_deg": round(float(shafts[index]["angle_deg"]), 3),
            "active_after": active,
            "input_source": input_source,
        })
        last_tick = tick
    angles = [round(float(shaft["angle_deg"]), 3) for shaft in shafts]
    events.append({"seq": len(events) + 1, "type": "drive", "tick": last_tick, "running": False, "angles": angles})
    events.append({
        "seq": len(events) + 1,
        "type": "unlock",
        "tick": last_tick,
        "angles": angles,
        "engaged": [bool(shaft["engaged"]) for shaft in shafts],
        "accepted": True,
    })
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": events,
        "completed": True,
    }


def test_clockwork_controls_materialize_both_interactions_without_changing_other_axes(tmp_path: Path) -> None:
    controls = read_json(ENV_ROOT / "controls.json")
    MATERIALIZER.validate_controls(controls, ENV_ROOT)
    assert controls["baseline"] == {"difficulty": 3, "interaction": "simplified", "real_time": "live"}
    assert controls["real_time"] == {"play_time_seconds": 180, "observation_window_ms": 600, "frames_per_observation": 5}
    assert read_json(TASK_ROOT / "task.json")["difficulty"] == "medium"
    written = MATERIALIZER.materialize_environment(ENV_ROOT, tmp_path)
    assert len(written) == 10
    assert {path.name for path in written} == {
        f"clockwork_clutch_safe_d{level}_{interaction}_seed_0001"
        for level in range(1, 6)
        for interaction in ("simplified", "full")
    }


def test_clockwork_interaction_modes_preserve_the_same_seed_world_and_baseline() -> None:
    base_task = read_json(TASK_ROOT / "task.json")
    original_public, original_truth = SETUP.generate_task_state(base_task, "clockwork-control-equivalence")
    for level in range(1, 6):
        simplified_public, simplified_truth = SETUP.generate_task_state(
            controlled_task(level, "simplified"),
            "clockwork-control-equivalence",
        )
        full_public, full_truth = SETUP.generate_task_state(
            controlled_task(level, "full"),
            "clockwork-control-equivalence",
        )
        assert without_control_identity(simplified_public) == without_control_identity(full_public)
        assert without_control_identity(simplified_truth) == without_control_identity(full_truth)
        if level == 3:
            assert without_control_identity(simplified_public) == without_control_identity(original_public)
            assert without_control_identity(simplified_truth) == without_control_identity(original_truth)


def test_clockwork_level_three_matches_the_legacy_fixed_seed_contract() -> None:
    public, truth = SETUP.generate_task_state(
        controlled_task(3, "simplified"),
        "clockwork-control-equivalence",
    )
    assert public["shafts"] == [
        {"id": "seal-1", "ratio": 1.5, "angle_deg": 94.5, "engaged": True},
        {"id": "seal-2", "ratio": -1.75, "angle_deg": 54.75, "engaged": True},
        {"id": "seal-3", "ratio": 1.0, "angle_deg": 304.2, "engaged": True},
        {"id": "seal-4", "ratio": -1.25, "angle_deg": 156.75, "engaged": True},
    ]
    assert public["physics"] == {
        "tick_ms": 85,
        "drive_deg_per_tick": 1.8,
        "load_numerator": 4,
        "phase_tolerance_deg": 13.0,
        "max_ticks": 170,
    }
    assert truth["release_schedule"] == [
        {"tick": 31, "shaft": 2},
        {"tick": 60, "shaft": 3},
        {"tick": 91, "shaft": 1},
        {"tick": 116, "shaft": 0},
    ]


def test_clockwork_profiles_change_the_actual_phase_problem_and_preserve_level_three() -> None:
    controls = read_json(ENV_ROOT / "controls.json")
    expected_counts = [1, 2, 4, 4, 4]
    expected_drive = [1.2, 1.5, 1.8, 2.1, 2.3]
    expected_tolerance = [30.0, 20.0, 13.0, 9.0, 6.0]
    expected_angle_readout = [True, True, True, False, False]
    expected_speed_readout = [True, True, True, True, False]
    expected_reengagement = [True, True, True, True, False]

    for seed_index in range(10):
        seed = f"clockwork-profile-order-{seed_index:02d}"
        original_public, original_truth = SETUP.generate_task_state(
            read_json(TASK_ROOT / "task.json"),
            seed,
        )
        levels = [
            SETUP.generate_task_state(controlled_task(level, "simplified"), seed)
            for level in range(1, 6)
        ]
        assert without_control_identity(levels[2][0]) == without_control_identity(original_public)
        assert without_control_identity(levels[2][1]) == without_control_identity(original_truth)
        assert [len(public["shafts"]) for public, _truth in levels] == expected_counts
        assert [public["physics"]["drive_deg_per_tick"] for public, _truth in levels] == expected_drive
        assert [public["physics"]["phase_tolerance_deg"] for public, _truth in levels] == expected_tolerance
        assert [public["physics"].get("show_angle_readout", True) for public, _truth in levels] == expected_angle_readout
        assert [public["physics"].get("show_speed_readout", True) for public, _truth in levels] == expected_speed_readout
        assert [public["physics"].get("reengagement_allowed", True) for public, _truth in levels] == expected_reengagement

        for level, (public, truth) in enumerate(levels, start=1):
            parameters = controls["difficulty"][str(level)]["parameters"]
            physics = public["physics"]
            assert truth["physics"] == physics
            assert len(truth["release_schedule"]) == parameters["shaft_count"]
            assert {item["shaft"] for item in truth["release_schedule"]} == set(range(parameters["shaft_count"]))
            for release, window in zip(truth["release_schedule"], parameters["release_tick_ranges"]):
                assert window[0] <= release["tick"] <= window[1]
            assert physics["load_numerator"] == len(public["shafts"])
            payload = passing_payload(public, truth, "clutch_button")
            decision = GRADER.grade(payload, truth, public)
            assert decision["passed"] is True, (level, seed, decision)


def test_clockwork_grader_and_task_verifier_bind_each_interaction_surface(tmp_path: Path) -> None:
    sources = {"simplified": "clutch_button", "full": "clutch_lever_drag"}
    for level in range(1, 6):
        for interaction, source in sources.items():
            public, truth = SETUP.generate_task_state(
                controlled_task(level, interaction),
                f"clockwork-d{level}-{interaction}-grade",
            )
            payload = passing_payload(public, truth, source)
            assert GRADER.grade(payload, truth, public)["passed"] is True

            wrong = copy.deepcopy(payload)
            clutch = next(event for event in wrong["events"] if event["type"] == "clutch")
            clutch["input_source"] = sources["full" if interaction == "simplified" else "simplified"]
            rejected = GRADER.grade(wrong, truth, public)
            assert rejected["passed"] is False
            assert "wrong interaction input" in rejected["feedback"]

            exported_path = tmp_path / f"d{level}-{interaction}.json"
            exported_path.write_text(
                json.dumps({"result": payload, "ground_truth": truth, "public_state": public}),
                encoding="utf-8",
            )

            def copy_from_env(_source: str, destination: str) -> None:
                Path(destination).write_bytes(exported_path.read_bytes())

            verified = VERIFIER.verify_task(env_info={"copy_from_env": copy_from_env})
            assert verified["passed"] is True
            assert verified["score"] == 100


def test_clockwork_grader_rejects_contract_tampering_and_level_five_reengagement() -> None:
    public, truth = SETUP.generate_task_state(
        controlled_task(5, "simplified"),
        "clockwork-irreversible-contract",
    )
    payload = passing_payload(public, truth, "clutch_button")

    forged_contract = copy.deepcopy(public)
    forged_contract["physics"]["phase_tolerance_deg"] = 40.0
    rejected_contract = GRADER.grade(payload, truth, forged_contract)
    assert rejected_contract["passed"] is False
    assert "public drive physics differs" in rejected_contract["feedback"]

    forged_reengagement = copy.deepcopy(payload)
    first_index = next(
        index for index, item in enumerate(forged_reengagement["events"])
        if item["type"] == "clutch"
    )
    release = forged_reengagement["events"][first_index]
    forged_reengagement["events"].insert(
        first_index + 1,
        {
            "type": "clutch",
            "tick": release["tick"],
            "shaft": release["shaft"],
            "before": False,
            "after": True,
            "angle_deg": release["angle_deg"],
            "active_after": release["active_after"] + 1,
            "input_source": "clutch_button",
        },
    )
    for sequence, item in enumerate(forged_reengagement["events"], start=1):
        item["seq"] = sequence
    rejected_reengagement = GRADER.grade(forged_reengagement, truth, public)
    assert rejected_reengagement["passed"] is False
    assert rejected_reengagement["feedback"] == "released clutch cannot be re-engaged in this difficulty profile"
