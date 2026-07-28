from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENV_ROOT = BENCHMARK / "environments" / "bomb_manual_from_hell_env"
MECHANIC = "bomb_manual_from_hell"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


SETUP = load_module("bomb_manual_controlled_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = load_module(
    "bomb_manual_controlled_materializer",
    BENCHMARK / "tools" / "materialize_controlled_tasks.py",
)
GRADER = load_module(
    "bomb_manual_controlled_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py",
)
VERIFIER_HELPERS = load_module(
    "bomb_manual_controlled_verifier_helpers",
    BENCHMARK / "shared_runtime" / "verifier_helpers.py",
)


def controls() -> dict:
    return read_json(ENV_ROOT / "controls.json")


def base_task() -> dict:
    return read_json(ENV_ROOT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json")


def controlled_task(level: int, interaction: str) -> dict:
    specification = controls()
    return MATERIALIZER.controlled_task(
        base_task(),
        mechanic_id=MECHANIC,
        level=level,
        interaction=interaction,
        profile=specification["difficulty"][str(level)],
        task_dir_name=f"{MECHANIC}_d{level}_{interaction}_seed_0001",
    )


def without_condition_identity(value: dict) -> dict:
    normalized = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        normalized.pop(key, None)
    return normalized


def claim_pose(pose: dict) -> dict:
    return {
        "x": round(float(pose["x"]), 3),
        "y": round(float(pose["y"]), 3),
        "angle_deg": float(pose["angle_deg"]) % 360,
        "flipped": bool(pose["flipped"]),
    }


def passing_payload(public: dict, truth: dict, interaction: str) -> dict:
    rotation_source = "binder_rotation_buttons" if interaction == "simplified" else "plate_right_click"
    flip_source = "binder_flip_button" if interaction == "simplified" else "plate_shift_right_click"
    lock_source = "seat_button" if interaction == "simplified" else "plate_drop"
    events: list[dict] = []

    def record(event_type: str, **details) -> None:
        events.append({"seq": len(events) + 1, "t_ms": len(events) + 1, "type": event_type, **details})

    poses: dict[str, dict] = {}
    locked: list[str] = []
    for index, plate in enumerate(truth["plates"]):
        plate_id = str(plate["id"])
        pose = GRADER._pose(plate["initial_pose"])
        target = GRADER._pose(truth["target_poses"][plate_id])
        assert pose is not None and target is not None
        if pose["flipped"] is not target["flipped"]:
            record(
                "plate_flip",
                plate_id=plate_id,
                from_flipped=pose["flipped"],
                to_flipped=not pose["flipped"],
                input_source=flip_source,
            )
            pose["flipped"] = not pose["flipped"]
        rotation_step = int(truth["requirements"]["rotation_step_deg"])
        turns = int(((target["angle_deg"] - pose["angle_deg"]) % 360) / rotation_step)
        for _ in range(turns):
            before = pose["angle_deg"]
            pose["angle_deg"] = (before + rotation_step) % 360
            record(
                "plate_rotate",
                plate_id=plate_id,
                from_deg=before,
                to_deg=pose["angle_deg"],
                delta_deg=rotation_step,
                input_source=rotation_source,
            )

        start = [pose["x"], pose["y"]]
        record("drag_start", plate_id=plate_id, point=start, pose=claim_pose(pose), input_source="plate_drag")
        pose["x"], pose["y"] = target["x"], target["y"]
        record(
            "drag_end",
            plate_id=plate_id,
            point=[target["x"], target["y"]],
            pose=claim_pose(pose),
            input_source="plate_drag",
        )
        before_lock = claim_pose(pose)
        error = GRADER._max_anchor_error(plate, pose)
        pose = GRADER._snap_translation(plate, pose)
        record(
            "plate_lock",
            plate_id=plate_id,
            before_pose=before_lock,
            accepted=True,
            max_error=round(error, 3),
            after_pose=claim_pose(pose),
            input_source=lock_source,
        )
        poses[plate_id] = pose
        locked.append(plate_id)
        if index + 1 < len(truth["plates"]):
            record("plate_select", plate_id=truth["plates"][index + 1]["id"], reason="binder_advance")

    correct_wire = next(wire for wire in truth["wires"] if wire["id"] == truth["correct_wire_id"])
    record(
        "wire_select",
        wire_id=truth["correct_wire_id"],
        point=[truth["observation_x"], correct_wire["y"]],
        input_source="wire_canvas",
    )
    record("cut", wire_id=truth["correct_wire_id"], cut_count=1, input_source="cut_button")
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": events,
        "completed": True,
        "locked_plate_ids": sorted(locked),
        "plate_poses": {plate_id: claim_pose(pose) for plate_id, pose in poses.items()},
        "selected_wire_id": truth["correct_wire_id"],
        "cut_count": 1,
        "misseat_count": 0,
    }


def test_bomb_manual_control_spec_records_the_existing_simplified_interface() -> None:
    specification = controls()
    MATERIALIZER.validate_controls(specification, ENV_ROOT)
    assert specification["baseline"] == {"difficulty": 4, "interaction": "simplified", "real_time": "live"}
    assert specification["interaction"]["simplified"]["implemented"] is True
    assert specification["interaction"]["full"]["implemented"] is True
    realtime = read_json(BENCHMARK / "real_time.json")["environments"][MECHANIC]
    assert specification["real_time"] == realtime


def test_bomb_manual_materializer_writes_every_difficulty_and_both_interactions(tmp_path: Path) -> None:
    written = MATERIALIZER.materialize_environment(ENV_ROOT, tmp_path)
    assert len(written) == 10
    conditions = [read_json(path / "task.json")["metadata"]["control_condition"] for path in written]
    assert {(condition["difficulty"], condition["interaction"]) for condition in conditions} == {
        (level, interaction)
        for level in range(1, 6)
        for interaction in ("simplified", "full")
    }
    specification = controls()
    for condition in conditions:
        assert condition["difficulty_parameters"] == specification["difficulty"][str(condition["difficulty"])]["parameters"]


def test_bomb_manual_interaction_modes_preserve_each_generated_world_and_the_current_baseline() -> None:
    for seed_index in range(4):
        seed = f"bomb-manual-interaction-{seed_index}"
        original_public, original_truth = SETUP.generate_task_state(base_task(), seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(controlled_task(4, "simplified"), seed)
        assert baseline_public["challenge_id"] == original_public["challenge_id"]
        assert baseline_truth["challenge_id"] == original_truth["challenge_id"]
        assert without_condition_identity(baseline_public) == without_condition_identity(original_public)
        assert without_condition_identity(baseline_truth) == without_condition_identity(original_truth)

        challenge_ids = set()
        for level in range(1, 6):
            simplified_public, simplified_truth = SETUP.generate_task_state(controlled_task(level, "simplified"), seed)
            full_public, full_truth = SETUP.generate_task_state(controlled_task(level, "full"), seed)
            assert simplified_public["control_condition"]["interaction"] == "simplified"
            assert full_public["control_condition"]["interaction"] == "full"
            assert simplified_public["challenge_id"] == full_public["challenge_id"]
            assert without_condition_identity(simplified_public) == without_condition_identity(full_public)
            assert without_condition_identity(simplified_truth) == without_condition_identity(full_truth)
            challenge_ids.add(simplified_public["challenge_id"])
        assert len(challenge_ids) == 5


def test_bomb_manual_difficulty_profiles_change_the_visible_registration_problem() -> None:
    specification = controls()
    expected_counts = {
        1: (2, 5, 2, 2, 90, 36, 28),
        2: (3, 6, 3, 2, 90, 32, 26),
        3: (4, 8, 4, 3, 45, 28, 23),
        4: (5, 9, 5, 3, 45, 24, 21),
        5: (6, 11, 6, 4, 30, 18, 16),
    }
    for level, expected in expected_counts.items():
        public, truth = SETUP.generate_task_state(controlled_task(level, "simplified"), "bomb-profile-audit")
        plate_count, wire_count, aperture_count, anchor_count, rotation_step, snap_tolerance, aperture_radius = expected
        assert len(public["plates"]) == plate_count
        assert len(public["wires"]) == wire_count
        assert {len(plate["apertures"]) for plate in public["plates"]} == {aperture_count}
        assert {len(plate["anchors"]) for plate in public["plates"]} == {anchor_count}
        assert public["requirements"] == {
            "rotation_step_deg": rotation_step,
            "snap_tolerance_px": snap_tolerance,
            "aperture_radius_px": aperture_radius,
            "plate_count": plate_count,
        }
        assert public["control_condition"]["difficulty_parameters"] == specification["difficulty"][str(level)]["parameters"]
        aperture_intersection = set.intersection(
            *({item["wire_id"] for item in plate["apertures"]} for plate in public["plates"])
        )
        assert aperture_intersection == {truth["correct_wire_id"]}
        for plate in truth["plates"]:
            assert GRADER._max_anchor_error(plate, truth["target_poses"][plate["id"]]) <= .01

        parameters = specification["difficulty"][str(level)]["parameters"]
        mismatches = sum(
            plate["initial_pose"]["flipped"] is not truth["target_poses"][plate["id"]]["flipped"]
            for plate in truth["plates"]
        )
        if parameters["reflection_mismatch_count"] != "legacy_random":
            assert mismatches == parameters["reflection_mismatch_count"]
        offsets = [
            int(
                (
                    truth["target_poses"][plate["id"]]["angle_deg"]
                    - plate["initial_pose"]["angle_deg"]
                )
                % 360
                / rotation_step
            )
            for plate in truth["plates"]
        ]
        assert min(offsets) >= parameters["rotation_offset_steps_min"]
        assert max(offsets) <= parameters["rotation_offset_steps_max"]


def test_bomb_manual_grader_and_exported_verifier_accept_all_profiles_and_both_modes() -> None:
    for level in range(1, 6):
        for interaction in ("simplified", "full"):
            public, truth = SETUP.generate_task_state(
                controlled_task(level, interaction),
                f"bomb-grade-d{level}-{interaction}",
            )
            payload = passing_payload(public, truth, interaction)
            grade = GRADER.grade(payload, truth, public)
            assert grade["passed"] is True, grade
            verified = VERIFIER_HELPERS.verify_external_mechanic(
                {"result": payload, "ground_truth": truth, "public_state": public},
                MECHANIC,
            )
            assert verified["passed"] is True
            assert verified["score"] == 100

            wrong = copy.deepcopy(payload)
            lock = next(event for event in wrong["events"] if event["type"] == "plate_lock")
            lock["input_source"] = "plate_drop" if interaction == "simplified" else "seat_button"
            rejected = GRADER.grade(wrong, truth, public)
            assert rejected["passed"] is False
            assert "wrong interaction input" in rejected["feedback"]

            skewed_public = copy.deepcopy(public)
            skewed_public["control_condition"]["interaction"] = "full" if interaction == "simplified" else "simplified"
            skewed = GRADER.grade(payload, truth, skewed_public)
            assert skewed["passed"] is False
            assert "condition differs" in skewed["feedback"]
