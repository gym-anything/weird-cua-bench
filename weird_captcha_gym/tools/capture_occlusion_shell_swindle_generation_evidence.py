#!/usr/bin/env python3
"""Record deterministic control and world-preservation evidence for Shell Swindle."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "occlusion_shell_swindle_env"
BASE_TASK = ENVIRONMENT / "tasks" / "occlusion_shell_swindle_seed_0001" / "task.json"
MATERIALIZER_PATH = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
SETUP_PATH = BENCHMARK / "shared_scripts" / "setup_task.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalized(value: dict) -> dict:
    result = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        result.pop(key, None)
    return result


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def task_for(materializer, controls: dict, base_task: dict, level: int, interaction: str) -> dict:
    return materializer.controlled_task(
        base_task,
        mechanic_id="occlusion_shell_swindle",
        level=level,
        interaction=interaction,
        profile=controls["difficulty"][str(level)],
        task_dir_name=f"occlusion_shell_swindle_d{level}_{interaction}_seed_0001",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ENVIRONMENT / "evidence_docs" / "generation_contract.json")
    args = parser.parse_args()
    setup = load_module("occlusion_shell_generation_setup", SETUP_PATH)
    materializer = load_module("occlusion_shell_generation_materializer", MATERIALIZER_PATH)
    controls = read_json(ENVIRONMENT / "controls.json")
    base_task = read_json(BASE_TASK)
    materializer.validate_controls(controls, ENVIRONMENT)

    baseline_rows = []
    for seed in ("occlusion-shell-baseline-a", "occlusion-shell-baseline-b", "occlusion-shell-baseline-c"):
        original_public, original_truth = setup.generate_task_state(base_task, seed)
        baseline_public, baseline_truth = setup.generate_task_state(task_for(materializer, controls, base_task, 2, "full"), seed)
        row = {
            "seed": seed,
            "challenge_id_equal": original_public["challenge_id"] == baseline_public["challenge_id"] == original_truth["challenge_id"] == baseline_truth["challenge_id"],
            "public_world_equal": normalized(original_public) == normalized(baseline_public),
            "truth_contract_equal": normalized(original_truth) == normalized(baseline_truth),
            "public_world_sha256": digest(normalized(baseline_public)),
            "truth_contract_sha256": digest(normalized(baseline_truth)),
        }
        if not all(value for key, value in row.items() if key.endswith("_equal")):
            raise AssertionError(f"L2/full changed the original world for {seed}: {row}")
        baseline_rows.append(row)

    profiles = []
    for level in range(1, 6):
        simplified_public, simplified_truth = setup.generate_task_state(task_for(materializer, controls, base_task, level, "simplified"), f"occlusion-shell-profile-{level}")
        full_public, full_truth = setup.generate_task_state(task_for(materializer, controls, base_task, level, "full"), f"occlusion-shell-profile-{level}")
        equivalent = normalized(simplified_public) == normalized(full_public) and normalized(simplified_truth) == normalized(full_truth)
        if not equivalent:
            raise AssertionError(f"difficulty {level} interaction pair changed its generated world")
        parameters = controls["difficulty"][str(level)]["parameters"]
        profile = {
            "difficulty": level,
            "interaction_world_equal": equivalent,
            "round_count": len(full_public["rounds"]),
            "shell_count": len(full_public["rounds"][0]["shell_ids"]),
            "decoy_port_count": len(full_public["rounds"][0].get("decoy_ports") or []),
            "inspection_radius": full_public["rounds"][0]["inspection"]["radius"],
            "parameters_match": (
                len(full_public["rounds"]) == parameters["round_count"]
                and len(full_public["rounds"][0]["shell_ids"]) in parameters["shell_count_values"]
                and len(full_public["rounds"][0].get("decoy_ports") or []) == parameters["decoy_port_count"]
                and full_public["rounds"][0]["inspection"]["radius"] == parameters["inspection_port_radius"]
            ),
        }
        if not profile["parameters_match"]:
            raise AssertionError(f"difficulty {level} does not expose its configured shell profile")
        profiles.append(profile)

    with tempfile.TemporaryDirectory(prefix="occlusion-shell-materialize-") as temporary:
        written = materializer.materialize_environment(ENVIRONMENT, Path(temporary))
        conditions = sorted(
            (
                read_json(path / "task.json")["metadata"]["control_condition"]["difficulty"],
                read_json(path / "task.json")["metadata"]["control_condition"]["interaction"],
            )
            for path in written
        )
    expected_conditions = sorted((level, interaction) for level in range(1, 6) for interaction in ("simplified", "full"))
    if conditions != expected_conditions:
        raise AssertionError(f"materialized conditions differ: {conditions}")
    output = {
        "environment": ENVIRONMENT.name,
        "baseline": {"difficulty": 2, "interaction": "full", "rows": baseline_rows},
        "materialized_task_count": len(conditions),
        "materialized_conditions": conditions,
        "profiles": profiles,
        "source_hashes": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (ENVIRONMENT / "controls.json", BASE_TASK, BENCHMARK / "shared_scripts" / "incubator_generators" / "occlusion_shell_swindle.py")
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
