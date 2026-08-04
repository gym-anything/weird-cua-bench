from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

from weird_captcha_gym.realtime import load_real_time_settings


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCH / "environments" / "jigsaw_slider_alignment_env"
MECHANIC = "jigsaw_slider_alignment"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = _load("jigsaw_alignment_setup", BENCH / "shared_scripts" / "setup_task.py")
MATERIALIZER = _load("jigsaw_alignment_materializer", BENCH / "tools" / "materialize_controlled_tasks.py")
GRADER = _load(
    "jigsaw_alignment_grader", BENCH / "shared_runtime" / "server" / "incubator_graders" / "jigsaw_slider_alignment.py"
)
CONTROLS = json.loads((ENVIRONMENT / "controls.json").read_text(encoding="utf-8"))
BASE = json.loads((ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json").read_text(encoding="utf-8"))
ENV_SPEC = json.loads((ENVIRONMENT / "env.json").read_text(encoding="utf-8"))


def _task(level: int, interaction: str) -> dict:
    name = f"{MECHANIC}_d{level}_{interaction}_seed_0001"
    return MATERIALIZER.controlled_task(
        BASE,
        mechanic_id=MECHANIC,
        level=level,
        interaction=interaction,
        profile=CONTROLS["difficulty"][str(level)],
        task_dir_name=name,
    )


def _without_identity(value: dict) -> dict:
    result = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        result.pop(key, None)
    return result


def test_baseline_preserves_original_generated_world_and_contract() -> None:
    for seed in ("jigsaw-baseline-preservation-a", "jigsaw-baseline-preservation-b", "jigsaw-baseline-preservation-c"):
        original_public, original_truth = SETUP.generate_task_state(BASE, seed)
        controlled_public, controlled_truth = SETUP.generate_task_state(_task(4, "full"), seed)
        assert _without_identity(controlled_public) == _without_identity(original_public)
        assert _without_identity(controlled_truth) == _without_identity(original_truth)
        assert controlled_public["control_condition"] == controlled_truth["control_condition"]
        assert controlled_public["control_condition"]["difficulty"] == 4
        assert controlled_public["control_condition"]["interaction"] == "full"


def test_all_profiles_materialize_deterministically_and_keep_interaction_worlds_equal() -> None:
    for level in range(1, 6):
        full_task = _task(level, "full")
        simple_task = _task(level, "simplified")
        full_public, full_truth = SETUP.generate_task_state(full_task, "jigsaw-profile-pair")
        repeated_public, repeated_truth = SETUP.generate_task_state(full_task, "jigsaw-profile-pair")
        simple_public, simple_truth = SETUP.generate_task_state(simple_task, "jigsaw-profile-pair")
        assert full_public == repeated_public
        assert full_truth == repeated_truth
        assert _without_identity(full_public) == _without_identity(simple_public)
        assert _without_identity(full_truth) == _without_identity(simple_truth)
        assert full_public["control_condition"]["difficulty"] == level
        assert simple_public["control_condition"]["interaction"] == "simplified"


def test_profiles_drive_visible_and_replayed_parameters() -> None:
    for level in range(1, 6):
        parameters = CONTROLS["difficulty"][str(level)]["parameters"]
        public, truth = SETUP.generate_task_state(_task(level, "full"), "jigsaw-profile-parameters")
        tolerance = public["tolerances"]
        inertia = public["inertia"]
        assert tolerance["x_milli"] == parameters["rail_tolerance_milli"]
        assert tolerance["depth_milli"] == parameters["depth_tolerance_milli"]
        assert tolerance["rotation_deg"] == parameters["rotation_tolerance_deg"]
        assert tolerance["hold_ms"] == parameters["hold_ms"]
        assert tolerance["minimum_scan_samples"] == parameters["minimum_scan_samples"]
        assert inertia["velocity_threshold_milli_s"] == parameters["velocity_threshold_milli_s"]
        assert inertia["friction_milli"] == parameters["friction_milli"]
        assert truth["target_depth_milli"] in parameters["target_depth_values"]
        assert public["scene"]["piece"]["initial_rotation_deg"] in parameters["initial_rotations_deg"]
        rail_distance = abs(public["scene"]["rail"]["initial_milli"] - truth["target_rail_milli"])
        depth_distance = abs(public["scene"]["depth"]["initial_milli"] - truth["target_depth_milli"])
        assert parameters["rail_distance_min_milli"] <= rail_distance <= parameters["rail_distance_max_milli"]
        assert parameters["depth_distance_min_milli"] <= depth_distance <= parameters["depth_distance_max_milli"]


def test_controlled_grader_rejects_a_direct_drag_under_the_proxy_condition() -> None:
    public, truth = SETUP.generate_task_state(_task(4, "full"), "jigsaw-wrong-surface")
    public = copy.deepcopy(public)
    truth = copy.deepcopy(truth)
    public["control_condition"]["interaction"] = "simplified"
    truth["control_condition"]["interaction"] = "simplified"
    scene = public["scene"]
    payload = {
        "mechanic_id": MECHANIC,
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": [
            {
                "sequence": 1,
                "type": "rail_start",
                "input_source": "direct_rail_drag",
                "rail_milli": scene["rail"]["initial_milli"],
                "depth_milli": scene["depth"]["initial_milli"],
                "rotation_deg": scene["piece"]["initial_rotation_deg"],
            },
            {"sequence": 2, "type": "rail_end"},
            {"sequence": 3, "type": "scan_end"},
        ],
    }
    outcome = GRADER.grade(payload, truth, public)
    assert outcome["passed"] is False
    assert "wrong rail interaction" in outcome["feedback"]


def test_controlled_grader_rejects_a_proxy_action_under_the_full_condition_and_stale_identity() -> None:
    public, truth = SETUP.generate_task_state(_task(4, "full"), "jigsaw-wrong-surface")
    scene = public["scene"]
    proxy_payload = {
        "mechanic_id": MECHANIC,
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": [
            {
                "sequence": 1,
                "type": "rail_nudge",
                "delta_milli": 5_000,
                "input_source": "rail_nudge_button",
                "rail_milli": scene["rail"]["initial_milli"] + 5_000,
                "depth_milli": scene["depth"]["initial_milli"],
                "rotation_deg": scene["piece"]["initial_rotation_deg"],
            },
            {"sequence": 2, "type": "scan_start", "input_source": "optical_lock_button", "rail_milli": scene["rail"]["initial_milli"] + 5_000, "depth_milli": scene["depth"]["initial_milli"], "rotation_deg": scene["piece"]["initial_rotation_deg"]},
            {"sequence": 3, "type": "scan_end", "duration_ms": 1, "sample_count": 0, "input_source": "optical_lock_button", "rail_milli": scene["rail"]["initial_milli"] + 5_000, "depth_milli": scene["depth"]["initial_milli"], "rotation_deg": scene["piece"]["initial_rotation_deg"]},
        ],
    }
    wrong_surface = GRADER.grade(proxy_payload, truth, public)
    assert wrong_surface["passed"] is False
    assert "proxy outside simplified interaction" in wrong_surface["feedback"]

    stale_payload = copy.deepcopy(proxy_payload)
    stale_payload["challenge_id"] = "stale-challenge"
    stale = GRADER.grade(stale_payload, truth, public)
    assert stale == {"graded": True, "passed": False, "feedback": "stale challenge"}


def test_simplified_coarse_rail_release_uses_the_shared_inertia_replay() -> None:
    public, truth = SETUP.generate_task_state(_task(4, "simplified"), "jigsaw-proxy-inertia")
    scene = public["scene"]
    inertia = public["inertia"]
    rail_min = int(scene["rail"]["minimum_milli"])
    rail_max = int(scene["rail"]["maximum_milli"])
    rail = int(scene["rail"]["initial_milli"])
    depth = int(scene["depth"]["initial_milli"])
    rotation = int(scene["piece"]["initial_rotation_deg"])
    requested = 50_000 if rail <= (rail_min + rail_max) // 2 else -50_000
    applied = max(rail_min, min(rail_max, rail + requested)) - rail
    velocity = GRADER._js_round(applied * 1000 / 200) if applied else 0
    assert abs(velocity) >= int(inertia["velocity_threshold_milli_s"])

    events = []

    def append(kind: str, **details: int | str) -> None:
        events.append(
            {
                "sequence": len(events) + 1,
                "type": kind,
                "rail_milli": rail,
                "depth_milli": depth,
                "rotation_deg": rotation,
                **details,
            }
        )

    rail += applied
    append(
        "rail_nudge",
        input_source="rail_nudge_button",
        requested_delta_milli=requested,
        delta_milli=applied,
        virtual_drag_ms=200,
        velocity_milli_s=velocity,
    )
    while True:
        delta = GRADER._js_round(velocity * int(inertia["tick_ms"]) / 1000)
        next_rail = max(rail_min, min(rail_max, rail + delta))
        applied = next_rail - rail
        velocity_after = GRADER._js_round(velocity * int(inertia["friction_milli"]) / 1000)
        reason = None
        if applied == 0:
            velocity_after, reason = 0, "boundary"
        elif abs(velocity_after) < int(inertia["stop_velocity_milli_s"]):
            reason = "friction"
        rail = next_rail
        append("inertia_sample", delta_milli=applied, velocity_after_milli_s=velocity_after)
        velocity = velocity_after
        if reason:
            append("inertia_end", reason=reason)
            break

    outcome = GRADER.grade(
        {
            "mechanic_id": MECHANIC,
            "task_id": public["task_id"],
            "challenge_id": public["challenge_id"],
            "events": events,
            "final_rail_milli": rail,
            "final_depth_milli": depth,
            "final_rotation_deg": rotation,
            "completed": False,
        },
        truth,
        public,
    )
    assert outcome == {
        "graded": True,
        "passed": False,
        "feedback": "transcript does not end with a released optical lock",
    }
    assert len([event for event in events if event["type"] == "inertia_sample"]) > 0


def test_materializer_writes_the_full_ten_condition_matrix(tmp_path: Path) -> None:
    written = MATERIALIZER.materialize_environment(ENVIRONMENT, tmp_path)
    assert len(written) == 10
    conditions = {
        (
            json.loads((path / "task.json").read_text(encoding="utf-8"))["metadata"]["control_condition"]["difficulty"],
            json.loads((path / "task.json").read_text(encoding="utf-8"))["metadata"]["control_condition"]["interaction"],
        )
        for path in written
    }
    assert conditions == {(level, interaction) for level in range(1, 6) for interaction in ("simplified", "full")}


def test_controls_use_the_shared_realtime_configuration() -> None:
    assert CONTROLS["real_time"] == load_real_time_settings(MECHANIC).__dict__


def test_baseline_keeps_the_original_1280_by_720_observation_surface() -> None:
    screens = [
        item
        for item in ENV_SPEC["observation"]
        if item.get("type") in {"rgb_screen", "frame_window"}
    ]
    assert len(screens) == 1
    assert screens[0]["resolution"] == [1280, 720]
