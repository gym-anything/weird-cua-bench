#!/usr/bin/env python3
"""Resolve the original task into the target's controlled launch contract.

The checked-in ``collision_chimes_seed_0001`` task is kept as the original
uncontrolled source.  The runner hook passes a temporary copy to the common
task preparer so the browser, generator, grader, and current task record all
see one explicit condition.  Materialized controlled variants already carry a
condition; this resolver preserves their difficulty and interaction and only
aligns the run identity with the runner's selected clock mode.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path


BASELINE_DIFFICULTY = 4
BASELINE_INTERACTION = "full"
BASELINE_PARAMETERS = {
    "grid_size": 9,
    "solution_cells": 5,
    "max_cells": 6,
    "beats": 18,
    "beat_ms": 260,
    "minimum_events": 7,
    "minimum_walls": 3,
    "minimum_beats": 6,
    "minimum_collisions": 2,
}


def resolve(task: dict, time_mode: str) -> dict:
    resolved = copy.deepcopy(task)
    metadata = copy.deepcopy(resolved.get("metadata") or {})
    raw_condition = metadata.get("control_condition")
    if isinstance(raw_condition, dict) and raw_condition:
        condition = copy.deepcopy(raw_condition)
    else:
        condition = {
            "difficulty": BASELINE_DIFFICULTY,
            "interaction": BASELINE_INTERACTION,
            "real_time": time_mode,
            "difficulty_parameters": copy.deepcopy(BASELINE_PARAMETERS),
        }
        metadata["controlled_task_version"] = 1
        metadata["baseline_resolution"] = "runtime_materialized_from_original_seed_task"
    condition["real_time"] = time_mode
    metadata["control_condition"] = condition
    resolved["metadata"] = metadata
    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-json", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--time-mode", required=True, choices=("live", "paused"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    task = json.loads(args.task_json.read_text(encoding="utf-8"))
    resolved = resolve(task, args.time_mode)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(resolved, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "source_task": str(args.task_json),
        "resolved_task": str(args.output),
        "task_id": resolved.get("id"),
        "control_condition": resolved["metadata"]["control_condition"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
