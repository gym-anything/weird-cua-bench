#!/usr/bin/env python3
"""Write deterministic controllability evidence for Blind Corridor Oscilloscope.

This is intentionally a generator-level companion to the visible browser
evidence.  It proves that the exact uncontrolled world survives at L4 and
that an interaction pair differs only at its bound input surface.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "trace_shape_without_walls_env"
MECHANIC = "trace_shape_without_walls"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object in {path}")
    return value


def _without_identity(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        result.pop(key, None)
    return result


def _digest(value: dict[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _metrics(public: dict[str, Any]) -> dict[str, Any]:
    drift = dict(public["drift"])
    requirements = dict(public["requirements"])
    return {
        "main_path_points": len(public["main_path"]),
        "branch_count": len(public["branches"]),
        "checkpoint_count": len(public["checkpoint_indices"]),
        "corridor_radius": public["corridor_radius"],
        "sonar_radius": public["sonar_radius"],
        "sonar_fade_ms": public["sonar_fade_ms"],
        "drift_amplitude_x": drift["amplitude_x"],
        "drift_amplitude_y": drift["amplitude_y"],
        "drift_rate_x": drift["rate_x"],
        "drift_rate_y": drift["rate_y"],
        "min_probe_samples": requirements["min_probe_samples"],
        "min_trace_samples": requirements["min_trace_samples"],
        "min_trace_distance": requirements["min_trace_distance"],
        "min_trace_ms": requirements["min_trace_ms"],
        "max_raw_step": requirements["max_raw_step"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit Trace Shape Without Walls baseline and control-pair generation."
    )
    parser.add_argument("--out", type=Path, required=True, help="JSON evidence file to write")
    args = parser.parse_args()

    setup = _load("trace_shape_control_audit_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
    materializer = _load(
        "trace_shape_control_audit_materializer",
        BENCHMARK / "tools" / "materialize_controlled_tasks.py",
    )
    controls = _read(ENVIRONMENT / "controls.json")
    base_task = _read(ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json")

    def controlled(level: int, interaction: str) -> dict[str, Any]:
        return materializer.controlled_task(
            base_task,
            mechanic_id=MECHANIC,
            level=level,
            interaction=interaction,
            profile=controls["difficulty"][str(level)],
            task_dir_name=f"{MECHANIC}_d{level}_{interaction}_seed_0001",
        )

    if controls["baseline"] != {"difficulty": 4, "interaction": "full", "real_time": "live"}:
        raise AssertionError("Trace Shape Without Walls baseline is not L4 full/live")
    if base_task["natural_language"] != controls["difficulty"]["4"]["natural_language"]:
        raise AssertionError("L4 task text does not preserve the original task text")

    baseline_seeds = ("trace-shape-baseline-a", "trace-shape-baseline-b", "trace-shape-baseline-c")
    baseline: list[dict[str, str]] = []
    for seed in baseline_seeds:
        original_public, original_truth = setup.generate_task_state(base_task, seed)
        l4_public, l4_truth = setup.generate_task_state(controlled(4, "full"), seed)
        stripped_original_public = _without_identity(original_public)
        stripped_l4_public = _without_identity(l4_public)
        stripped_original_truth = _without_identity(original_truth)
        stripped_l4_truth = _without_identity(l4_truth)
        if stripped_original_public != stripped_l4_public or stripped_original_truth != stripped_l4_truth:
            raise AssertionError(f"L4 changed the uncontrolled world for {seed}")
        baseline.append({
            "seed": seed,
            "public_world_sha256": _digest(stripped_original_public),
            "ground_truth_world_sha256": _digest(stripped_original_truth),
        })

    pairs: dict[str, dict[str, Any]] = {}
    for level in range(1, 6):
        seed = f"trace-shape-interaction-pair-{level}"
        simplified_public, simplified_truth = setup.generate_task_state(controlled(level, "simplified"), seed)
        full_public, full_truth = setup.generate_task_state(controlled(level, "full"), seed)
        simplified_world = _without_identity(simplified_public)
        full_world = _without_identity(full_public)
        simplified_truth_world = _without_identity(simplified_truth)
        full_truth_world = _without_identity(full_truth)
        if simplified_world != full_world or simplified_truth_world != full_truth_world:
            raise AssertionError(f"interaction pair changed the generated world at L{level}")
        pairs[str(level)] = {
            "seed": seed,
            "same_public_world": True,
            "same_ground_truth_world": True,
            "public_world_sha256": _digest(simplified_world),
            "ground_truth_world_sha256": _digest(simplified_truth_world),
            "world_metrics": _metrics(simplified_public),
        }

    adjacent_seed = "trace-shape-adjacent-level-evidence"
    adjacent: dict[str, dict[str, Any]] = {}
    adjacent_public: dict[int, dict[str, Any]] = {}
    for level in (1, 3, 4, 5):
        public, _truth = setup.generate_task_state(controlled(level, "full"), adjacent_seed)
        adjacent_public[level] = public
        adjacent[str(level)] = _metrics(public)
    if not (
        adjacent_public[1]["corridor_radius"] > adjacent_public[3]["corridor_radius"] > adjacent_public[4]["corridor_radius"] > adjacent_public[5]["corridor_radius"]
        and adjacent_public[1]["sonar_radius"] > adjacent_public[3]["sonar_radius"] > adjacent_public[4]["sonar_radius"] > adjacent_public[5]["sonar_radius"]
        and len(adjacent_public[1]["branches"]) < len(adjacent_public[3]["branches"]) <= len(adjacent_public[4]["branches"]) < len(adjacent_public[5]["branches"])
        and adjacent_public[1]["drift"]["amplitude_x"] < adjacent_public[3]["drift"]["amplitude_x"] < adjacent_public[4]["drift"]["amplitude_x"] < adjacent_public[5]["drift"]["amplitude_x"]
    ):
        raise AssertionError("adjacent control levels are not ordered on their configured axes")

    output = {
        "environment": ENVIRONMENT.name,
        "mechanic": MECHANIC,
        "baseline": {
            "assigned_condition": controls["baseline"],
            "original_task_text_equals_l4": True,
            "fixed_seed_exact_world_match": True,
            "seeds": baseline,
        },
        "interaction_pairs": pairs,
        "adjacent_difficulty_evidence": {
            "seed": adjacent_seed,
            "levels": adjacent,
            "strict_order_checks": {
                "corridor_narrows": True,
                "sonar_range_shrinks": True,
                "false_branches_nondecreasing": True,
                "crosswind_grows": True,
            },
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
