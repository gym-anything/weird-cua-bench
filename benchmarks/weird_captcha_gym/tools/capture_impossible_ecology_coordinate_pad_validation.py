#!/usr/bin/env python3
"""Validate the current Impossible Ecology coordinate-pad browser matrices."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "impossible_ecology_env"

EXPECTED_RULES = {
    1: "A matching sanctuary locks an organism permanently. Stabilize both organisms.",
    2: "A matching sanctuary locks an organism permanently. Stabilize all three organisms.",
    3: "A matching sanctuary locks an organism permanently. Stabilize all four organisms.",
    4: "A matching sanctuary locks an organism permanently. Stabilize all five.",
    5: "A matching sanctuary locks an organism permanently. Stabilize all six organisms.",
}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GRADER = load_module(
    "impossible_ecology_coordinate_pad_validation_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "impossible_ecology.py",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=ENVIRONMENT / "evidence_docs" / "coordinate_pad_validation.json",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def without_identity(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        result.pop(key, None)
    return result


def expected_source(interaction: str) -> str:
    return {"full": "arena_pointer", "simplified": "coordinate_pad"}[interaction]


def main() -> None:
    args = parse_args()
    evidence = ENVIRONMENT / "evidence_docs"
    matrices: dict[str, Any] = {}
    for mode in ("live", "paused"):
        mode_rows: dict[str, Any] = {}
        for difficulty in range(1, 6):
            directory = evidence / f"browser_{mode}_coordinate_pad_fhd_d{difficulty}"
            summary = read_json(directory / "summary.json")
            if summary.get("time_mode") != mode or summary.get("difficulty") != difficulty:
                raise AssertionError(f"matrix summary has the wrong condition: {directory}")
            rows: dict[str, Any] = {}
            paired_initial_states: dict[str, dict[str, Any]] = {}
            for interaction in ("full", "simplified"):
                row = summary["interactions"][interaction]
                if row.get("input_sources") != [expected_source(interaction)]:
                    raise AssertionError(f"{directory} {interaction} reports the wrong source")
                if row.get("passed") is not True or row.get("server_grade", {}).get("score") != 100 or row.get("verifier", {}).get("score") != 100:
                    raise AssertionError(f"{directory} {interaction} does not contain a passing replay")
                initial = read_json(directory / interaction / "initial_public_state.json")
                if initial["rules"][-1] != EXPECTED_RULES[difficulty]:
                    raise AssertionError(f"{directory} {interaction} has a stale completion rule")
                exported = read_json(directory / interaction / "exported-result.json")
                replay = GRADER.grade(exported["result"], exported["ground_truth"], exported["public_state"])
                if replay.get("passed") is not True or replay.get("score") != 100:
                    raise AssertionError(f"{directory} {interaction} current replay failed: {replay}")
                wrong = copy.deepcopy(exported["result"])
                first_pointer = next(event for event in wrong["events"] if event["kind"] == "pointer_down")
                first_pointer["input_source"] = expected_source("simplified" if interaction == "full" else "full")
                rejected = GRADER.grade(wrong, exported["ground_truth"], exported["public_state"])
                if "wrong interaction input" not in str(rejected.get("feedback") or ""):
                    raise AssertionError(f"{directory} {interaction} cross-surface replay was accepted: {rejected}")
                paired_initial_states[interaction] = initial
                rows[interaction] = {
                    "input_source": expected_source(interaction),
                    "current_authoritative_replay": "passed score 100",
                    "cross_surface_first_pointer_rejection": rejected["feedback"],
                }
            if without_identity(paired_initial_states["full"]) != without_identity(paired_initial_states["simplified"]):
                raise AssertionError(f"{directory} full/simplified initial public worlds differ")
            mode_rows[str(difficulty)] = {
                "full_simplified_initial_public_worlds_equal_except_control_identity": True,
                "rules_match_generated_goal_count": True,
                "interactions": rows,
            }
        matrices[mode] = mode_rows

    current_env = read_json(ENVIRONMENT / "env.json")
    head_env = json.loads(
        subprocess.check_output(
            ["git", "show", "HEAD:benchmarks/weird_captcha_gym/environments/impossible_ecology_env/env.json"],
            cwd=ROOT,
            text=True,
        )
    )
    current_resolution = current_env["observation"][0]["resolution"]
    head_resolution = head_env["observation"][0]["resolution"]
    if current_resolution != [1920, 1080] or head_resolution != [1280, 720]:
        raise AssertionError(f"unexpected Impossible Ecology observation configuration: {current_resolution} / {head_resolution}")

    artifact = {
        "schema_version": 1,
        "purpose": "Current browser/replay validation after replacing the target-tracking simplified proxy with a direct coordinate pad.",
        "browser_evidence_viewport": [1920, 1080],
        "observation_surface": {
            "current_resolution": current_resolution,
            "committed_pre_control_resolution": head_resolution,
            "fixed_seed": "interaction-pair-impossible_ecology",
            "fixed_seed_l4_current_viewport_evidence": "browser_live_coordinate_pad_fhd_d4/full/initial.png",
            "preserved_task_canvas_coordinates": [1000, 430],
            "generated_l4_world_preservation_report": "baseline_preservation_check.json",
            "current_fhd_browser_evidence_matches_declared_surface": True,
        },
        "full_completion_rules": {str(level): rule for level, rule in EXPECTED_RULES.items()},
        "matrices": matrices,
        "source_hashes_sha256": {
            "env.json": hash_file(ENVIRONMENT / "env.json"),
            "controls.json": hash_file(ENVIRONMENT / "controls.json"),
            "browser_mechanic": hash_file(BENCHMARK / "shared_runtime" / "app" / "mechanics" / "impossible_ecology.js"),
            "authoritative_grader": hash_file(BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "impossible_ecology.py"),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(args.out), "matrices": list(matrices)}, sort_keys=True))


if __name__ == "__main__":
    main()
