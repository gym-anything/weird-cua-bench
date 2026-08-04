#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import shutil
from pathlib import Path
from typing import Any


BENCHMARK_ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENTS_ROOT = BENCHMARK_ROOT / "environments"
LEVELS = (1, 2, 3, 4, 5)
DIFFICULTY_NAMES = {
    1: "very_easy",
    2: "easy",
    3: "medium",
    4: "hard",
    5: "very_hard",
}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected an object in {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_controls(controls: dict[str, Any], env_root: Path) -> None:
    if controls.get("schema_version") != 1:
        raise ValueError(f"{env_root.name}: unsupported controls schema")
    mechanic_id = str(controls.get("mechanic_id") or "")
    if f"{mechanic_id}_env" != env_root.name:
        raise ValueError(f"{env_root.name}: mechanic_id does not match the environment")
    baseline = controls.get("baseline")
    if not isinstance(baseline, dict) or baseline.get("difficulty") not in LEVELS:
        raise ValueError(f"{env_root.name}: baseline difficulty must be 1 through 5")
    if baseline.get("interaction") not in {"simplified", "full"}:
        raise ValueError(f"{env_root.name}: baseline interaction is invalid")
    interactions = controls.get("interaction")
    if not isinstance(interactions, dict) or set(interactions) != {"simplified", "full"}:
        raise ValueError(f"{env_root.name}: simplified and full interaction definitions are required")
    for name, interaction in interactions.items():
        if not isinstance(interaction, dict) or not isinstance(interaction.get("implemented"), bool):
            raise ValueError(f"{env_root.name}: {name} interaction has no implementation status")
    if interactions[baseline["interaction"]]["implemented"] is not True:
        raise ValueError(f"{env_root.name}: baseline interaction is not implemented")
    profiles = controls.get("difficulty")
    if not isinstance(profiles, dict) or set(profiles) != {str(level) for level in LEVELS}:
        raise ValueError(f"{env_root.name}: exactly five difficulty profiles are required")
    for level in LEVELS:
        profile = profiles[str(level)]
        if not isinstance(profile, dict) or not isinstance(profile.get("parameters"), dict):
            raise ValueError(f"{env_root.name}: difficulty {level} has no parameter object")
        if profile.get("label") != DIFFICULTY_NAMES[level]:
            raise ValueError(f"{env_root.name}: difficulty {level} has the wrong label")
        natural_language = profile.get("natural_language")
        if natural_language is not None and (not isinstance(natural_language, str) or not natural_language.strip()):
            raise ValueError(f"{env_root.name}: difficulty {level} has invalid natural_language")
        natural_language_by_interaction = profile.get("natural_language_by_interaction")
        if natural_language_by_interaction is not None:
            if not isinstance(natural_language_by_interaction, dict) or not set(natural_language_by_interaction) <= {"simplified", "full"}:
                raise ValueError(f"{env_root.name}: difficulty {level} has invalid natural_language_by_interaction")
            if any(not isinstance(value, str) or not value.strip() for value in natural_language_by_interaction.values()):
                raise ValueError(f"{env_root.name}: difficulty {level} has an empty interaction-specific instruction")
        summary = profile.get("summary")
        if summary is not None and (not isinstance(summary, str) or not summary.strip()):
            raise ValueError(f"{env_root.name}: difficulty {level} has invalid summary")


def _base_task(env_root: Path, mechanic_id: str) -> tuple[Path, dict[str, Any]]:
    candidates = sorted((env_root / "tasks").glob(f"{mechanic_id}_seed_0001/task.json"))
    if len(candidates) != 1:
        raise ValueError(f"{env_root.name}: expected one original seed_0001 task")
    return candidates[0].parent, _read_json(candidates[0])


def controlled_task(
    base: dict[str, Any],
    *,
    mechanic_id: str,
    level: int,
    interaction: str,
    profile: dict[str, Any],
    task_dir_name: str,
) -> dict[str, Any]:
    task = copy.deepcopy(base)
    task["id"] = f"{task_dir_name}@0.2"
    task["version"] = "0.2"
    interaction_label = interaction.replace("_", " ").title()
    task["name"] = f"{base['name']} · Difficulty {level} · {interaction_label} Interaction"
    task["difficulty"] = DIFFICULTY_NAMES[level]
    if mechanic_id == "slot_reel_capture" and interaction == "simplified":
        reel_count = int(profile["parameters"]["reel_count"])
        reel_count_text = {
            1: "one",
            2: "two",
            3: "three",
            4: "four",
            5: "five",
            6: "six",
            7: "seven",
        }.get(reel_count, str(reel_count))
        timing = (
            "while its center is between the capture lines"
            if float(profile["parameters"].get("capture_window_ratio", 1.0)) < 1.0
            else "while it is centered"
        )
        task["natural_language"] = (
            f"Click CAPTURE SYMBOL {timing}. "
            f"Capture all {reel_count_text} reels."
        )
    elif (profile.get("natural_language_by_interaction") or {}).get(interaction):
        task["natural_language"] = str(profile["natural_language_by_interaction"][interaction])
    elif profile.get("natural_language"):
        task["natural_language"] = str(profile["natural_language"])
    hooks = dict(task.get("hooks") or {})
    hooks["pre_task"] = f"/workspace/tasks/{task_dir_name}/setup_task.sh"
    hooks["post_task"] = f"/workspace/tasks/{task_dir_name}/export_result.sh"
    task["hooks"] = hooks
    metadata = dict(task.get("metadata") or {})
    metadata["control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": "live",
        "difficulty_parameters": copy.deepcopy(profile["parameters"]),
    }
    metadata["controlled_task_version"] = 1
    metadata["mechanic_id"] = mechanic_id
    task["metadata"] = metadata
    return task


def materialize_environment(env_root: Path, output_root: Path) -> list[Path]:
    controls_path = env_root / "controls.json"
    controls = _read_json(controls_path)
    validate_controls(controls, env_root)
    mechanic_id = str(controls["mechanic_id"])
    base_dir, base_task = _base_task(env_root, mechanic_id)
    destination_tasks = output_root / env_root.name / "tasks"
    written: list[Path] = []
    implemented_interactions = [
        name
        for name in ("simplified", "full")
        if controls["interaction"][name]["implemented"] is True
    ]
    for interaction in implemented_interactions:
        for level in LEVELS:
            task_dir_name = f"{mechanic_id}_d{level}_{interaction}_seed_0001"
            destination = destination_tasks / task_dir_name
            destination.mkdir(parents=True, exist_ok=True)
            for source in sorted(base_dir.iterdir()):
                if source.name == "task.json" or not source.is_file():
                    continue
                target = destination / source.name
                shutil.copy2(source, target)
                if source.suffix == ".sh":
                    text = target.read_text(encoding="utf-8").replace(base_dir.name, task_dir_name)
                    target.write_text(text, encoding="utf-8")
            task = controlled_task(
                base_task,
                mechanic_id=mechanic_id,
                level=level,
                interaction=interaction,
                profile=controls["difficulty"][str(level)],
                task_dir_name=task_dir_name,
            )
            _write_json(destination / "task.json", task)
            written.append(destination)
    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize controlled Weird CUA Bench task variants.")
    parser.add_argument(
        "--environment",
        action="append",
        help="Environment folder name. Repeat for more than one environment.",
    )
    parser.add_argument("--all-controlled", action="store_true")
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if bool(args.environment) == bool(args.all_controlled):
        raise SystemExit("choose either --environment or --all-controlled")
    if args.all_controlled:
        roots = sorted(path.parent for path in ENVIRONMENTS_ROOT.glob("*_env/controls.json"))
    else:
        roots = [ENVIRONMENTS_ROOT / name for name in args.environment]
    written: list[Path] = []
    for env_root in roots:
        if not env_root.is_dir():
            raise SystemExit(f"unknown environment: {env_root.name}")
        written.extend(materialize_environment(env_root, args.output_root.resolve()))
    print(f"materialized {len(written)} controlled tasks under {args.output_root.resolve()}")


if __name__ == "__main__":
    main()
