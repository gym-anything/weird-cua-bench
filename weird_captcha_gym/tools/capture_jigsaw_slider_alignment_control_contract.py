#!/usr/bin/env python3
"""Record reproducible control-contract evidence for Jigsaw Slider Alignment."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCH / "environments" / "jigsaw_slider_alignment_env"
MECHANIC = "jigsaw_slider_alignment"
BASE_TASK = ENVIRONMENT / "tasks" / "jigsaw_slider_alignment_seed_0001" / "task.json"
MATERIALIZER_PATH = BENCH / "tools" / "materialize_controlled_tasks.py"
SETUP_PATH = BENCH / "shared_scripts" / "setup_task.py"
GRADER_PATH = BENCH / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py"
HELPERS_PATH = BENCH / "shared_runtime" / "verifier_helpers.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected an object in {path}")
    return value


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def normalized(public: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    public = copy.deepcopy(public)
    truth = copy.deepcopy(truth)
    for item in (public, truth):
        for key in ("task_id", "challenge_id", "control_condition"):
            item.pop(key, None)
    return {"public_state": public, "ground_truth": truth}


def task_for(tasks: Path, difficulty: int, interaction: str) -> dict[str, Any]:
    matches = []
    for path in tasks.glob("*/task.json"):
        task = read_json(path)
        condition = (task.get("metadata") or {}).get("control_condition") or {}
        if condition.get("difficulty") == difficulty and condition.get("interaction") == interaction:
            matches.append(task)
    if len(matches) != 1:
        raise AssertionError(f"expected one d{difficulty}/{interaction} task, found {len(matches)}")
    return matches[0]


def transcript_header(public: dict[str, Any]) -> dict[str, Any]:
    scene = public["scene"]
    return {
        "mechanic_id": MECHANIC,
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "completed": False,
        "final_rail_milli": scene["rail"]["initial_milli"],
        "final_depth_milli": scene["depth"]["initial_milli"],
        "final_rotation_deg": scene["piece"]["initial_rotation_deg"],
    }


def event(public: dict[str, Any], sequence: int, kind: str, source: str, **details: Any) -> dict[str, Any]:
    scene = public["scene"]
    return {
        "sequence": sequence,
        "type": kind,
        "input_source": source,
        "rail_milli": scene["rail"]["initial_milli"],
        "depth_milli": scene["depth"]["initial_milli"],
        "rotation_deg": scene["piece"]["initial_rotation_deg"],
        **details,
    }


def grade_and_verify(grader, helpers, payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    decision = grader.grade(payload, truth, public)
    verification = helpers.verify_external_mechanic(
        {"result": payload, "ground_truth": truth, "public_state": public}, MECHANIC
    )
    if decision.get("passed") is not False or verification.get("passed") is not False:
        raise AssertionError(f"negative transcript unexpectedly passed: {decision} / {verification}")
    return {"grader": decision, "verifier": verification}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ENVIRONMENT / "evidence_docs")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    materializer = load_module("jigsaw_control_materializer", MATERIALIZER_PATH)
    setup = load_module("jigsaw_control_setup", SETUP_PATH)
    grader = load_module("jigsaw_control_grader", GRADER_PATH)
    helpers = load_module("jigsaw_control_helpers", HELPERS_PATH)
    controls = read_json(ENVIRONMENT / "controls.json")
    original = read_json(BASE_TASK)
    environment = read_json(ENVIRONMENT / "env.json")
    screens = [item for item in environment.get("observation") or [] if item.get("type") == "rgb_screen"]
    if len(screens) != 1 or screens[0].get("resolution") != [1280, 720]:
        raise AssertionError("the L4/full baseline must retain the original 1280x720 observation surface")

    with tempfile.TemporaryDirectory(prefix="jigsaw-control-contract-") as temporary_name:
        temporary = Path(temporary_name)
        first = temporary / "first"
        second = temporary / "second"
        written_first = materializer.materialize_environment(ENVIRONMENT, first)
        written_second = materializer.materialize_environment(ENVIRONMENT, second)
        if len(written_first) != 10 or len(written_second) != 10:
            raise AssertionError("controlled materialization did not produce ten tasks")
        tasks = first / ENVIRONMENT.name / "tasks"
        first_manifest = {
            str(path.relative_to(first)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(first.rglob("*")) if path.is_file()
        }
        second_manifest = {
            str(path.relative_to(second)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(second.rglob("*")) if path.is_file()
        }
        if first_manifest != second_manifest:
            raise AssertionError("controlled materialization is not deterministic")

        baseline_records = []
        baseline_task = task_for(tasks, 4, "full")
        for seed in ("jigsaw-baseline-a", "jigsaw-baseline-b", "jigsaw-baseline-c"):
            original_public, original_truth = setup.generate_task_state(original, seed)
            controlled_public, controlled_truth = setup.generate_task_state(baseline_task, seed)
            original_world = normalized(original_public, original_truth)
            controlled_world = normalized(controlled_public, controlled_truth)
            if original_world != controlled_world:
                raise AssertionError(f"L4/full changed the original generated world for {seed}")
            baseline_records.append({
                "seed": seed,
                "world_fingerprint": digest(original_world),
                "public_matches_original": True,
                "truth_matches_original": True,
            })

        interaction_pairs = []
        profile_records = []
        for difficulty in range(1, 6):
            full_task = task_for(tasks, difficulty, "full")
            simplified_task = task_for(tasks, difficulty, "simplified")
            profile_seed_records = []
            for seed_suffix in ("a", "b", "c"):
                seed = f"jigsaw-paired-d{difficulty}-{seed_suffix}"
                full_public, full_truth = setup.generate_task_state(full_task, seed)
                simple_public, simple_truth = setup.generate_task_state(simplified_task, seed)
                full_world = normalized(full_public, full_truth)
                simple_world = normalized(simple_public, simple_truth)
                if full_world != simple_world:
                    raise AssertionError(f"d{difficulty} interaction pair changed its world for {seed}")
                profile_seed_records.append({
                    "seed": seed,
                    "world_fingerprint": digest(full_world),
                    "full_task_id": full_public["task_id"],
                    "simplified_task_id": simple_public["task_id"],
                    "challenge_id": full_public["challenge_id"],
                    "worlds_match": True,
                })
            interaction_pairs.append({"difficulty": difficulty, "records": profile_seed_records})
            parameters = controls["difficulty"][str(difficulty)]["parameters"]
            visible, hidden = setup.generate_task_state(full_task, f"jigsaw-profile-d{difficulty}")
            profile_records.append({
                "difficulty": difficulty,
                "parameters": parameters,
                "initial_rail_milli": visible["scene"]["rail"]["initial_milli"],
                "target_rail_milli": hidden["target_rail_milli"],
                "initial_depth_milli": visible["scene"]["depth"]["initial_milli"],
                "target_depth_milli": hidden["target_depth_milli"],
                "initial_rotation_deg": visible["scene"]["piece"]["initial_rotation_deg"],
                "tolerances": visible["tolerances"],
                "inertia": visible["inertia"],
            })

        simplified_public, simplified_truth = setup.generate_task_state(task_for(tasks, 4, "simplified"), "jigsaw-negative")
        full_public, full_truth = setup.generate_task_state(task_for(tasks, 4, "full"), "jigsaw-negative")
        direct_under_proxy = transcript_header(simplified_public)
        direct_under_proxy["events"] = [
            event(simplified_public, 1, "rail_start", "direct_rail_drag"),
            event(simplified_public, 2, "rail_end", "direct_rail_drag", velocity_milli_s=0),
            event(simplified_public, 3, "scan_end", "optical_lock_button", duration_ms=1, sample_count=0),
        ]
        proxy_under_full = transcript_header(full_public)
        proxy_under_full["events"] = [
            event(full_public, 1, "rail_nudge", "rail_nudge_button", delta_milli=5000),
            event(full_public, 2, "scan_start", "optical_lock_button"),
            event(full_public, 3, "scan_end", "optical_lock_button", duration_ms=1, sample_count=0),
        ]
        malformed_proxy = transcript_header(simplified_public)
        malformed_proxy["events"] = [
            event(simplified_public, 1, "rail_nudge", "rail_nudge_button", delta_milli=123),
            event(simplified_public, 2, "scan_start", "optical_lock_button"),
            event(simplified_public, 3, "scan_end", "optical_lock_button", duration_ms=1, sample_count=0),
        ]
        stale = copy.deepcopy(direct_under_proxy)
        stale["challenge_id"] = "stale-challenge"
        negative_results = {
            "direct_full_event_under_simplified": grade_and_verify(grader, helpers, direct_under_proxy, simplified_truth, simplified_public),
            "simplified_proxy_event_under_full": grade_and_verify(grader, helpers, proxy_under_full, full_truth, full_public),
            "malformed_simplified_proxy": grade_and_verify(grader, helpers, malformed_proxy, simplified_truth, simplified_public),
            "stale_challenge": grade_and_verify(grader, helpers, stale, simplified_truth, simplified_public),
        }

    output = {
        "environment": ENVIRONMENT.name,
        "mechanic": MECHANIC,
        "baseline": {
            "difficulty": 4,
            "interaction": "full",
            "original_task": str(BASE_TASK.relative_to(ROOT)),
            "observation_resolution": [1280, 720],
            "observation_surface_matches_original": True,
            "records": baseline_records,
        },
        "deterministic_materialization": {
            "task_count": 10,
            "first_manifest_sha256": digest(first_manifest),
            "second_manifest_sha256": digest(second_manifest),
            "manifests_match": True,
        },
        "interaction_pairs": interaction_pairs,
        "profiles": profile_records,
        "negative_transcripts": negative_results,
    }
    path = args.out_dir / "control-contract-audit.json"
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
