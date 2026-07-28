#!/usr/bin/env python3
"""Measure active Magnetic Stripe Purgatory field geometry across fixed seeds."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from benchmarks.weird_captcha_gym.shared_scripts.setup_task import generate_task_state


BENCH_ROOT = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCH_ROOT / "environments" / "magnetic_stripe_purgatory_env"
BASE_TASK = ENVIRONMENT / "tasks" / "magnetic_stripe_purgatory_seed_0001" / "task.json"


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def center_path(reader: dict[str, Any]) -> list[tuple[int, int]]:
    track = reader["track"]
    start = int(track["x_start"] if track["direction"] == "ltr" else track["x_end"])
    end = int(track["x_end"] if track["direction"] == "ltr" else track["x_start"])
    count = int(reader["calibration"]["minimum_samples"])
    return [(round(start + (end - start) * index / count), int(track["y"])) for index in range(count + 1)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=500)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ENVIRONMENT / "evidence_docs" / "geometry_verified_v5",
    )
    args = parser.parse_args()
    if args.seeds < 1:
        raise SystemExit("--seeds must be positive")
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    controls = read_json(ENVIRONMENT / "controls.json")
    base = read_json(BASE_TASK)
    materializer = load_module("magnetic_stripe_geometry_materializer", BENCH_ROOT / "tools" / "materialize_controlled_tasks.py")
    grader = load_module("magnetic_stripe_geometry_grader", BENCH_ROOT / "shared_runtime" / "server" / "incubator_graders" / "magnetic_stripe_purgatory.py")
    solver = load_module("magnetic_stripe_geometry_solver", BENCH_ROOT / "tools" / "incubator_solvers" / "magnetic_stripe_purgatory.py")

    def task_for(level: int) -> dict[str, Any]:
        return materializer.controlled_task(
            base,
            mechanic_id="magnetic_stripe_purgatory",
            level=level,
            interaction="full",
            profile=controls["difficulty"][str(level)],
            task_dir_name=f"magnetic_stripe_purgatory_d{level}_full_seed_0001",
        )

    non_routing_profiles: dict[str, Any] = {}
    for level in (1, 2, 3, 4):
        task = task_for(level)
        counts = {
            "fields": 0,
            "fields_overlapping_visible_rail_lane": 0,
            "fields_reachable_within_straightness": 0,
        }
        for seed_index in range(args.seeds):
            _, truth = generate_task_state(task, f"field-geometry-{level}-{seed_index}")
            for reader in truth["readers"]:
                track = reader["track"]
                center_y = int(track["y"])
                lane_half_height = int(track["lane_half_height"])
                straightness = int(reader["calibration"]["straightness_px"])
                fields = reader["interference_zones"]
                counts["fields"] += len(fields)
                counts["fields_overlapping_visible_rail_lane"] += sum(
                    int(zone["y"]) <= center_y + lane_half_height and int(zone["y"]) + int(zone["height"]) >= center_y - lane_half_height
                    for zone in fields
                )
                counts["fields_reachable_within_straightness"] += sum(
                    int(zone["y"]) <= center_y + straightness and int(zone["y"]) + int(zone["height"]) >= center_y - straightness
                    for zone in fields
                )
        if level in (1, 2, 3) and counts["fields"] != 0:
            raise AssertionError(f"L{level} unexpectedly generated static fields")
        if level == 4 and (counts["fields_overlapping_visible_rail_lane"] or counts["fields_reachable_within_straightness"]):
            raise AssertionError("preserved L4 legacy fields became an active routing constraint")
        non_routing_profiles[f"L{level}"] = counts

    profiles: dict[str, Any] = {}
    for level in (5,):
        task = task_for(level)
        counts = {
            "fields": 0,
            "fields_overlapping_visible_rail_lane": 0,
            "fields_reachable_within_straightness": 0,
            "centered_paths_rejected_for_static": 0,
            "clearance_paths_accepted": 0,
            "reader_paths": 0,
        }
        for seed_index in range(args.seeds):
            _, truth = generate_task_state(task, f"field-geometry-{level}-{seed_index}")
            for reader in truth["readers"]:
                track = reader["track"]
                center_y = int(track["y"])
                lane_half_height = int(track["lane_half_height"])
                straightness = int(reader["calibration"]["straightness_px"])
                fields = reader["interference_zones"]
                counts["fields"] += len(fields)
                counts["fields_overlapping_visible_rail_lane"] += sum(
                    int(zone["y"]) <= center_y + lane_half_height and int(zone["y"]) + int(zone["height"]) >= center_y - lane_half_height
                    for zone in fields
                )
                counts["fields_reachable_within_straightness"] += sum(
                    int(zone["y"]) <= center_y + straightness and int(zone["y"]) + int(zone["height"]) >= center_y - straightness
                    for zone in fields
                )
                blocked = grader._evaluate_swipe(reader, center_path(reader), int(reader["calibration"]["solver_ms"]))
                if blocked["feedback"] == "BAD READ" and blocked["zone_hits"] > 0:
                    counts["centered_paths_rejected_for_static"] += 1
                clearance = [tuple(round(value) for value in point) for point in solver._clearance_points(reader)]
                accepted = grader._evaluate_swipe(reader, clearance, int(reader["calibration"]["solver_ms"]))
                if accepted["feedback"] == "ACCEPTED" and accepted["zone_hits"] == 0:
                    counts["clearance_paths_accepted"] += 1
                counts["reader_paths"] += 1
        if counts["fields"] != counts["fields_overlapping_visible_rail_lane"]:
            raise AssertionError(f"L{level} generated a field outside the visible rail lane")
        if counts["fields"] != counts["fields_reachable_within_straightness"]:
            raise AssertionError(f"L{level} generated a field outside the accepted straightness corridor")
        if counts["reader_paths"] != counts["centered_paths_rejected_for_static"]:
            raise AssertionError(f"L{level} centered path did not hit static on every reader")
        if counts["reader_paths"] != counts["clearance_paths_accepted"]:
            raise AssertionError(f"L{level} lacked a feasible accepted clearance route")
        profiles[f"L{level}"] = counts

    report = {
        "environment": ENVIRONMENT.name,
        "seeds_per_profile": args.seeds,
        "method": "L1–L4 are measured to verify no active field-routing condition precedes L5. Every L5 full-mode reader is replayed once through its rail centre and once through the deterministic visible-field clearance route used by the simplified surface.",
        "non_routing_profiles": non_routing_profiles,
        "active_routing_profiles": profiles,
    }
    (out_dir / "geometry-summary.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
