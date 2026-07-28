#!/usr/bin/env python3
"""Record that both Impossible Ecology surfaces replay the same lure trajectory."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "impossible_ecology_env"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = load_module("impossible_ecology_equivalence_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = load_module("impossible_ecology_equivalence_materializer", BENCHMARK / "tools" / "materialize_controlled_tasks.py")
GRADER = load_module(
    "impossible_ecology_equivalence_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "impossible_ecology.py",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=ENVIRONMENT / "evidence_docs" / "interaction_action_effect_check.json",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def without_identity(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        result.pop(key, None)
    return result


def task_for(interaction: str) -> dict[str, Any]:
    controls = read_json(ENVIRONMENT / "controls.json")
    original = read_json(ENVIRONMENT / "tasks" / "impossible_ecology_seed_0001" / "task.json")
    return MATERIALIZER.controlled_task(
        original,
        mechanic_id="impossible_ecology",
        level=4,
        interaction=interaction,
        profile=controls["difficulty"]["4"],
        task_dir_name=f"impossible_ecology_d4_{interaction}_equivalence",
    )


def append(events: list[dict[str, Any]], kind: str, **details: Any) -> None:
    events.append({"sequence": len(events) + 1, "kind": kind, **details})


def canonical_trace(public: dict[str, Any], truth: dict[str, Any], input_source: str) -> tuple[dict[str, Any], list[list[dict[str, Any]]]]:
    arena = truth["arena"]
    organisms = GRADER._initial_organisms(truth)
    targets = GRADER._targets(truth)
    field = str(truth["fields"][0])
    events: list[dict[str, Any]] = []
    physics_snapshots: list[list[dict[str, Any]]] = []
    tick = 0
    active = False
    lure = [142.0, 72.0]

    append(events, "field_select", field=field, tick=tick)
    append(events, "pointer_down", field=field, tick=tick, input_source=input_source, point=lure)
    active = True

    def physics_tick() -> None:
        nonlocal tick
        tick += 1
        GRADER._advance(organisms, targets, truth, active, field if active else None, lure)
        snapshot = GRADER._snapshot(organisms)
        physics_snapshots.append(snapshot)
        append(
            events,
            "physics_tick",
            tick=tick,
            active=active,
            field=field if active else None,
            lure=list(lure),
            organisms=snapshot,
        )

    physics_tick()
    lure = [726.0, 304.0]
    append(events, "pointer_move", field=field, tick=tick, input_source=input_source, point=lure)
    physics_tick()
    physics_tick()
    append(events, "pointer_up", field=field, tick=tick, input_source=input_source, point=lure)
    active = False
    physics_tick()

    payload = {
        "mechanic_id": "impossible_ecology",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "interaction": truth["control_condition"]["interaction"],
        "control_condition": truth["control_condition"],
        "events": events,
        "final_organisms": GRADER._snapshot(organisms),
        "tick": tick,
        "completed": False,
        "field_selections": 1,
        "pointer_drags": 1,
        "calibration_runs": 0,
        "resets": 0,
    }
    return payload, physics_snapshots


def accepted_partial_replay(result: dict[str, Any]) -> bool:
    return result.get("graded") is True and result.get("passed") is False and str(result.get("feedback") or "").startswith("coupled ecology replay:")


def main() -> None:
    args = parse_args()
    samples: dict[str, dict[str, Any]] = {}
    snapshot_sets: dict[str, list[list[dict[str, Any]]]] = {}
    for interaction, input_source in (("full", "arena_pointer"), ("simplified", "coordinate_pad")):
        public, truth = SETUP.generate_task_state(task_for(interaction), "impossible-ecology-action-equivalence")
        payload, snapshots = canonical_trace(public, truth, input_source)
        result = GRADER.grade(payload, truth, public)
        if not accepted_partial_replay(result):
            raise AssertionError(f"{interaction} canonical trajectory was rejected: {result}")
        wrong = copy.deepcopy(payload)
        wrong_source = "coordinate_pad" if input_source == "arena_pointer" else "arena_pointer"
        next(event for event in wrong["events"] if event["kind"] == "pointer_down")["input_source"] = wrong_source
        rejected = GRADER.grade(wrong, truth, public)
        if "wrong interaction input" not in str(rejected.get("feedback") or ""):
            raise AssertionError(f"{interaction} cross-surface trace was not rejected: {rejected}")
        samples[interaction] = {
            "input_source": input_source,
            "trajectory": [[142.0, 72.0], [726.0, 304.0]],
            "authoritative_partial_replay_accepted": True,
            "partial_replay_feedback": result["feedback"],
            "cross_surface_rejection": rejected["feedback"],
            "physics_tick_snapshots": snapshots,
        }
        snapshot_sets[interaction] = snapshots

    full_public, full_truth = SETUP.generate_task_state(task_for("full"), "impossible-ecology-action-equivalence")
    simple_public, simple_truth = SETUP.generate_task_state(task_for("simplified"), "impossible-ecology-action-equivalence")
    if without_identity(full_public) != without_identity(simple_public) or without_identity(full_truth) != without_identity(simple_truth):
        raise AssertionError("paired L4 worlds differ outside their control identities")
    if snapshot_sets["full"] != snapshot_sets["simplified"]:
        raise AssertionError("the identical lure trajectory produced different physics snapshots")

    artifact = {
        "check": "impossible_ecology_interaction_action_effect_equivalence",
        "seed": "impossible-ecology-action-equivalence",
        "difficulty": 4,
        "declared_observation_resolution": read_json(ENVIRONMENT / "env.json")["observation"][0]["resolution"],
        "paired_world_equal_except_control_identity": True,
        "same_lure_trajectory_has_identical_authoritative_physics_snapshots": True,
        "surfaces": samples,
        "source_hashes": {
            "browser_mechanic": source_hash(BENCHMARK / "shared_runtime" / "app" / "mechanics" / "impossible_ecology.js"),
            "grader": source_hash(BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "impossible_ecology.py"),
            "controls": source_hash(ENVIRONMENT / "controls.json"),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(args.out), "surfaces": list(samples)}, sort_keys=True))


if __name__ == "__main__":
    main()
