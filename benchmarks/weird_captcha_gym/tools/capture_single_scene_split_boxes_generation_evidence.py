#!/usr/bin/env python3
"""Record deterministic generation evidence for Live Shattered-Scene Synchronizer."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "single_scene_split_boxes_env"
BASE_TASK = ENVIRONMENT / "tasks" / "single_scene_split_boxes_seed_0001" / "task.json"
HISTORICAL_FIXTURE = ENVIRONMENT / "historical_l4_baseline_fixture.json"
MATERIALIZER_PATH = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
SETUP_PATH = BENCHMARK / "shared_scripts" / "setup_task.py"
MECHANIC = "single_scene_split_boxes"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalized(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        result.pop(key, None)
    return result


def digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def controlled_task(materializer, controls: dict[str, Any], base_task: dict[str, Any], level: int, interaction: str) -> dict[str, Any]:
    profile = controls["difficulty"][str(level)]
    return materializer.controlled_task(
        base_task,
        mechanic_id=MECHANIC,
        level=level,
        interaction=interaction,
        profile={
            "label": profile["label"],
            "natural_language": profile["natural_language"],
            "parameters": profile["parameters"],
        },
        task_dir_name=f"single_scene_split_boxes_d{level}_{interaction}_seed_0001",
    )


def scene_rows(state: dict[str, Any]) -> int:
    return int(state["scene"].get("rows") or state["control_condition"]["difficulty_parameters"]["rows"])


def scene_columns(state: dict[str, Any]) -> int:
    return int(state["scene"].get("columns") or state["control_condition"]["difficulty_parameters"]["columns"])


def profile_record(setup, materializer, controls: dict[str, Any], base_task: dict[str, Any], level: int) -> dict[str, Any]:
    seed = f"split-boxes-profile-{level}"
    simplified_task = controlled_task(materializer, controls, base_task, level, "simplified")
    full_task = controlled_task(materializer, controls, base_task, level, "full")
    simplified_public, simplified_truth = setup.generate_task_state(simplified_task, seed)
    full_public, full_truth = setup.generate_task_state(full_task, seed)
    if normalized(simplified_public) != normalized(full_public) or normalized(simplified_truth) != normalized(full_truth):
        raise AssertionError(f"L{level} interaction modes changed the generated world")

    parameters = controls["difficulty"][str(level)]["parameters"]
    condition = full_public["control_condition"]
    requirements = full_public["requirements"]
    scene = full_public["scene"]
    rotations = sum(int(tile["initial_rotation"]) == 180 for tile in full_public["tiles"])
    phases = [int(tile["initial_phase"]) for tile in full_public["tiles"]]
    profile_matches = {
        "condition_parameters": condition["difficulty_parameters"] == parameters,
        "grid": (scene_rows(full_public), scene_columns(full_public)) == (parameters["rows"], parameters["columns"]),
        "tile_count": len(full_public["tiles"]) == parameters["rows"] * parameters["columns"],
        "decoy_count": len(scene["decoys"]) == parameters["decoy_count"],
        "rotation_range": parameters["rotation_minimum"] <= rotations <= parameters["rotation_maximum"],
        "minimum_displacement": requirements["minimum_spatial_touches"] >= parameters["minimum_displaced"],
        "phase_range": (full_public["phase_range"]["minimum"], full_public["phase_range"]["maximum"])
        == (min(parameters["phase_values"]), max(parameters["phase_values"])),
        "phase_nonzero": sum(phase != 0 for phase in phases) >= parameters["minimum_phase_nonzero"],
        "phase_distinct": len(set(phases)) >= parameters["minimum_phase_distinct"],
        "phase_tick_ms": scene["phase_tick_ms"] == parameters["phase_tick_ms"],
        "hold_ms": requirements["hold_ms"] == parameters["hold_ms"],
        "sample_ms": requirements["sample_ms"] == parameters["sample_ms"],
        "minimum_samples": requirements["minimum_samples"] == parameters["minimum_samples"],
    }
    if not all(profile_matches.values()):
        raise AssertionError(f"L{level} parameters are inactive: {profile_matches}")

    faster_parameters = copy.deepcopy(parameters)
    faster_parameters["speed_scale_milli"] = int(parameters["speed_scale_milli"]) * 2
    speed_probe = materializer.controlled_task(
        base_task,
        mechanic_id=MECHANIC,
        level=level,
        interaction="full",
        profile={
            "label": controls["difficulty"][str(level)]["label"],
            "natural_language": controls["difficulty"][str(level)]["natural_language"],
            "parameters": faster_parameters,
        },
        task_dir_name=f"single_scene_split_boxes_speed_probe_d{level}",
    )
    speed_public, _speed_truth = setup.generate_task_state(speed_probe, seed)
    motion_changed = (
        speed_public["scene"]["target"]["speed_x_milli"] != scene["target"]["speed_x_milli"]
        or speed_public["scene"]["target"]["speed_y_milli"] != scene["target"]["speed_y_milli"]
    )
    if not motion_changed:
        raise AssertionError(f"L{level} speed_scale_milli did not affect target motion")

    return {
        "difficulty": level,
        "seed": seed,
        "interaction_world_equal": True,
        "full_challenge_id": full_public["challenge_id"],
        "simplified_challenge_id": simplified_public["challenge_id"],
        "world_sha256": digest(normalized(full_public)),
        "truth_sha256": digest(normalized(full_truth)),
        "active_values": {
            "rows": scene_rows(full_public),
            "columns": scene_columns(full_public),
            "tile_count": len(full_public["tiles"]),
            "decoy_count": len(scene["decoys"]),
            "rotated_tiles": rotations,
            "non_master_phase_tiles": sum(phase != 0 for phase in phases),
            "distinct_phase_values": len(set(phases)),
            "phase_range": full_public["phase_range"],
            "phase_tick_ms": scene["phase_tick_ms"],
            "target_speed_milli": scene["target"],
            "requirements": requirements,
        },
        "parameters_match": profile_matches,
        "speed_scale_probe_changes_motion": motion_changed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=ENVIRONMENT / "evidence_docs" / "generation_contract.json",
    )
    args = parser.parse_args()
    setup = load_module("split_boxes_generation_setup", SETUP_PATH)
    materializer = load_module("split_boxes_generation_materializer", MATERIALIZER_PATH)
    controls = read_json(ENVIRONMENT / "controls.json")
    base_task = read_json(BASE_TASK)
    historical_fixture = read_json(HISTORICAL_FIXTURE)
    materializer.validate_controls(controls, ENVIRONMENT)
    if historical_fixture["identity_fields_removed_for_comparison"] != [
        "task_id",
        "challenge_id",
        "control_condition",
    ]:
        raise AssertionError("historical fixture removes fields beyond control identity")

    baseline_rows: list[dict[str, Any]] = []
    baseline_task = controlled_task(materializer, controls, base_task, 4, "full")
    for historical in historical_fixture["seeds"]:
        seed = str(historical["seed"])
        expected_public = historical["public_state"]
        expected_truth = historical["ground_truth"]
        original_public, original_truth = setup.generate_task_state(base_task, seed)
        controlled_public, controlled_truth = setup.generate_task_state(baseline_task, seed)
        row = {
            "seed": seed,
            "historical_challenge_id": expected_public["challenge_id"],
            "challenge_id_equal": original_public["challenge_id"] == controlled_public["challenge_id"] == original_truth["challenge_id"] == controlled_truth["challenge_id"] == expected_public["challenge_id"],
            "uncontrolled_full_public_contract_equal": original_public == expected_public,
            "uncontrolled_full_truth_contract_equal": original_truth == expected_truth,
            "uncontrolled_public_matches_historical": normalized(original_public) == normalized(expected_public),
            "uncontrolled_truth_matches_historical": normalized(original_truth) == normalized(expected_truth),
            "controlled_public_matches_historical": normalized(controlled_public) == normalized(expected_public),
            "controlled_truth_matches_historical": normalized(controlled_truth) == normalized(expected_truth),
            "public_world_equal": normalized(original_public) == normalized(controlled_public),
            "truth_contract_equal": normalized(original_truth) == normalized(controlled_truth),
            "historical_dimensions_present": expected_public["scene"].get("rows") == expected_public["scene"].get("columns") == 3,
            "uncontrolled_dimensions_present": original_public["scene"].get("rows") == original_public["scene"].get("columns") == 3,
            "controlled_dimensions_present": controlled_public["scene"].get("rows") == controlled_public["scene"].get("columns") == 3,
            "natural_language_equal": original_public["prompt"] == controlled_public["prompt"],
            "public_world_sha256": digest(normalized(controlled_public)),
            "truth_contract_sha256": digest(normalized(controlled_truth)),
            "historical_public_world_sha256": digest(normalized(expected_public)),
            "historical_truth_contract_sha256": digest(normalized(expected_truth)),
        }
        if not all(value for key, value in row.items() if key.endswith("_equal")):
            raise AssertionError(f"controlled L4 changed historical generation for {seed}: {row}")
        if not all(value for key, value in row.items() if key.endswith("_historical") or key.endswith("_present")):
            raise AssertionError(f"current task does not match the locked historical fixture for {seed}: {row}")
        baseline_rows.append(row)

    profiles = [profile_record(setup, materializer, controls, base_task, level) for level in range(1, 6)]
    with tempfile.TemporaryDirectory(prefix="split-boxes-materialize-") as temporary_name:
        written = materializer.materialize_environment(ENVIRONMENT, Path(temporary_name))
        conditions = sorted(
            (
                int(read_json(task / "task.json")["metadata"]["control_condition"]["difficulty"]),
                str(read_json(task / "task.json")["metadata"]["control_condition"]["interaction"]),
            )
            for task in written
        )
    expected_conditions = sorted((level, interaction) for level in range(1, 6) for interaction in ("simplified", "full"))
    if conditions != expected_conditions:
        raise AssertionError(f"materialized conditions differ: {conditions}")

    sources = (
        ENVIRONMENT / "controls.json",
        BASE_TASK,
        BENCHMARK / "shared_scripts" / "incubator_generators" / "single_scene_split_boxes.py",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "single_scene_split_boxes.py",
    )
    output = {
        "environment": ENVIRONMENT.name,
        "public_environment_name": "Live Shattered-Scene Synchronizer",
        "baseline": {"difficulty": 4, "interaction": "full", "rows": baseline_rows},
        "historical_fixture": {
            "path": str(HISTORICAL_FIXTURE.relative_to(ROOT)),
            "sha256": hashlib.sha256(HISTORICAL_FIXTURE.read_bytes()).hexdigest(),
            "historical_revision": historical_fixture["historical_revision"],
            "historical_generator_sha256": historical_fixture["historical_generator_sha256"],
            "identity_fields_removed_for_comparison": historical_fixture["identity_fields_removed_for_comparison"],
        },
        "materialized_task_count": len(conditions),
        "materialized_conditions": conditions,
        "profiles": profiles,
        "source_hashes": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
