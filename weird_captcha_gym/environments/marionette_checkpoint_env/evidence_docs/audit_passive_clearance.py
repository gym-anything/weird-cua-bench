#!/usr/bin/env python3
"""Audit that L1/L2 geometry cannot clear from the centered string rack."""
from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path
from typing import Any


ENVIRONMENT = Path(__file__).resolve().parents[1]
BENCHMARK = ENVIRONMENT.parents[1]
REPOSITORY = BENCHMARK.parents[2]
MECHANIC = "marionette_checkpoint"
SAMPLE_COUNT = 200


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = load_module("marionette_passive_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = load_module("marionette_passive_materializer", BENCHMARK / "tools" / "materialize_controlled_tasks.py")
GRADER = load_module("marionette_passive_grader", BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "marionette_checkpoint.py")


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


CONTROLS = read(ENVIRONMENT / "controls.json")
BASE_TASK = read(ENVIRONMENT / "tasks" / "marionette_checkpoint_seed_0001" / "task.json")


def controlled_task(level: int, interaction: str) -> dict[str, Any]:
    return MATERIALIZER.controlled_task(
        BASE_TASK,
        mechanic_id=MECHANIC,
        level=level,
        interaction=interaction,
        profile=CONTROLS["difficulty"][str(level)],
        task_dir_name=f"{MECHANIC}_d{level}_{interaction}_seed_0001",
    )


def generated(level: int, interaction: str, seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    return SETUP.generate_task_state(controlled_task(level, interaction), seed)


def _active(public: dict[str, Any]) -> list[int]:
    return [int(value) for value in public.get("active_string_indices", (0, 1, 2, 3))]


def passive_payload(public: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Replay the browser for its whole time allowance without touching a string."""
    events: list[dict[str, Any]] = []
    lengths = [float(value) for value in public["initial_lengths"]]
    poses = public["poses"]
    active = _active(public)
    remaining_ticks = math.floor(
        int(CONTROLS["real_time"]["play_time_seconds"]) * 1000 / int(public["tick_ms"])
    )
    pose_index = tick = progress = accepted_samples = 0
    while remaining_ticks and pose_index < len(poses):
        pose = poses[pose_index]
        tick += 1
        inside = GRADER._inside(lengths, pose, tick, float(public["ring_radius"]), active)
        accepted_samples += int(inside)
        progress = progress + 1 if inside else max(0, progress - int(pose["miss_decay_ticks"]))
        events.append({
            "seq": len(events) + 1,
            "type": "track_sample",
            "pose_id": pose["id"],
            "tick": tick,
            "inside": inside,
            "progress_after": progress,
            "lengths": list(lengths),
        })
        remaining_ticks -= 1
        if progress >= int(pose["tracking_ticks"]):
            events.append({
                "seq": len(events) + 1,
                "type": "act_clear",
                "pose_id": pose["id"],
                "tick": tick,
                "progress": progress,
                "lengths": list(lengths),
            })
            pose_index += 1
            tick = progress = 0
    return {
        "mechanic_id": MECHANIC,
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": events,
        "completed": pose_index == len(poses),
    }, accepted_samples


def solved_payload(public: dict[str, Any], interaction: str) -> dict[str, Any]:
    """Use the actual changing ring geometry to build a valid visible-control trace."""
    source = {"simplified": "string_slider", "full": "string_drag"}[interaction]
    events: list[dict[str, Any]] = []
    lengths = [float(value) for value in public["initial_lengths"]]
    active = _active(public)
    for pose in public["poses"]:
        tick = progress = 0
        while progress < int(pose["tracking_ticks"]):
            target_lengths = GRADER._target_lengths(pose, tick + 1)
            for index in active:
                after = float(round(target_lengths[index]))
                if after == lengths[index]:
                    continue
                before = lengths[index]
                lengths[index] = after
                events.append({
                    "seq": len(events) + 1,
                    "type": "string",
                    "pose_id": pose["id"],
                    "tick": tick,
                    "string": index,
                    "before": before,
                    "after": after,
                    "lengths": list(lengths),
                    "input_source": source,
                })
            tick += 1
            inside = GRADER._inside(lengths, pose, tick, float(public["ring_radius"]), active)
            progress = progress + 1 if inside else max(0, progress - int(pose["miss_decay_ticks"]))
            events.append({
                "seq": len(events) + 1,
                "type": "track_sample",
                "pose_id": pose["id"],
                "tick": tick,
                "inside": inside,
                "progress_after": progress,
                "lengths": list(lengths),
            })
        events.append({
            "seq": len(events) + 1,
            "type": "act_clear",
            "pose_id": pose["id"],
            "tick": tick,
            "progress": progress,
            "lengths": list(lengths),
        })
    return {
        "mechanic_id": MECHANIC,
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": events,
        "completed": True,
    }


def audit(sample_count: int = SAMPLE_COUNT) -> dict[str, Any]:
    records: dict[str, dict[str, Any]] = {}
    for level in (1, 2):
        for interaction in ("simplified", "full"):
            passive_completions = passive_accepted_samples = solved = 0
            for sample in range(sample_count):
                public, truth = generated(level, interaction, f"marionette-passive-d{level}-{sample:03d}")
                passive, accepted = passive_payload(public)
                passive_completions += int(GRADER.grade(passive, truth, public)["passed"])
                passive_accepted_samples += accepted
                solved += int(GRADER.grade(solved_payload(public, interaction), truth, public)["passed"])
            records[f"d{level}_{interaction}"] = {
                "difficulty": level,
                "interaction": interaction,
                "seeds": sample_count,
                "passive_completions": passive_completions,
                "passive_accepted_samples": passive_accepted_samples,
                "geometry_requires_string_adjustment": passive_accepted_samples == 0,
                "geometry_solvable": solved == sample_count,
                "solved": solved,
            }
    return {
        "environment": ENVIRONMENT.name,
        "mechanic": MECHANIC,
        "sample_count": sample_count,
        "method": "Replay each visible 50-length rack for the full 180-second allowance with no string event, then replay per-tick ring-following string events through the independent grader.",
        "records": records,
    }


def main() -> None:
    result = audit()
    assert all(item["passive_completions"] == 0 for item in result["records"].values())
    assert all(item["passive_accepted_samples"] == 0 for item in result["records"].values())
    assert all(item["geometry_solvable"] for item in result["records"].values())
    path = Path(__file__).with_name("passive-clearance-audit.json")
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
