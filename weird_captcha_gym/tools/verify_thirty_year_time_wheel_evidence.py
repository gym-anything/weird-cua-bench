#!/usr/bin/env python3
"""Audit saved Time Wheel browser evidence with the task verifier wrapper.

The interaction smoke deliberately calls the independent grader directly so it
can fail close to the browser run.  This companion takes the exported results
from all live/paused difficulty and interaction cells and passes them through
the task's real ``verify_task`` entry point.  It also changes only the recorded
input surface on each otherwise valid transcript to demonstrate that a result
from the other interface cannot be accepted.

This is an offline artifact check: it starts no browser and does not contact a
server or use any user profile.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENT = "thirty_year_time_wheel_env"
ENV_ROOT = ROOT / "weird_captcha_gym" / "environments" / ENVIRONMENT
DEFAULT_EVIDENCE = ENV_ROOT / "evidence_docs"
TASK_VERIFIER = ENV_ROOT / "tasks" / "thirty_year_time_wheel_seed_0001" / "verifier.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run saved Time Wheel exports through the task verifier wrapper."
    )
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Defaults to task-verifier-audit.json in --evidence-dir.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_verifier() -> Any:
    spec = importlib.util.spec_from_file_location("time_wheel_task_verifier_audit", TASK_VERIFIER)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load task verifier {TASK_VERIFIER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_task_verifier(verifier: Any, exported: dict[str, Any], scratch: Path) -> dict[str, Any]:
    """Exercise the verifier's supported export-copy boundary without a runner."""

    scratch.mkdir(parents=True, exist_ok=True)
    source = scratch / "exported-result.json"
    source.write_text(json.dumps(exported, sort_keys=True), encoding="utf-8")

    def copy_from_env(requested: str, destination: str) -> None:
        if requested != "/tmp/task_result.json":
            raise ValueError(f"unexpected verifier export request: {requested}")
        shutil.copyfile(source, destination)

    response = verifier.verify_task(env_info={"copy_from_env": copy_from_env})
    if not isinstance(response, dict):
        raise AssertionError(f"task verifier returned a non-object response: {response!r}")
    return response


def world_fingerprint(public_state: dict[str, Any]) -> str:
    """Compare generated worlds while excluding task and control identities."""

    normalized = copy.deepcopy(public_state)
    for key in ("task_id", "challenge_id", "control_condition"):
        normalized.pop(key, None)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def opposite_source(interaction: str) -> str:
    if interaction == "full":
        return "proxy_step"
    if interaction == "simplified":
        return "wheel_drag"
    raise ValueError(f"unknown interaction {interaction!r}")


def altered_surface_transcript(exported: dict[str, Any], interaction: str) -> dict[str, Any]:
    altered = copy.deepcopy(exported)
    result = altered.get("result")
    if not isinstance(result, dict):
        raise ValueError("export has no result object")
    changed = 0
    for event in result.get("events") or []:
        if isinstance(event, dict) and event.get("input_source") in {"wheel_drag", "proxy_step"}:
            event["input_source"] = opposite_source(interaction)
            changed += 1
    if changed == 0:
        raise ValueError("valid transcript contained no interaction-surface event")
    return altered


def audit(args: argparse.Namespace) -> dict[str, Any]:
    evidence_dir = args.evidence_dir.resolve()
    verifier = load_verifier()
    cells: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for time_mode in ("live", "paused"):
        matrix = evidence_dir / f"{time_mode}_matrix"
        if not matrix.is_dir():
            raise FileNotFoundError(f"missing matrix evidence: {matrix}")
        for difficulty in range(1, 6):
            pair: dict[str, str] = {}
            for interaction in ("simplified", "full"):
                relative = Path(f"{time_mode}_matrix") / f"d{difficulty}-{interaction}"
                condition_dir = evidence_dir / relative
                exported_path = condition_dir / "exported-result.json"
                initial_path = condition_dir / "initial_public_state.json"
                exported = load_json(exported_path)
                initial = load_json(initial_path)
                fingerprint = world_fingerprint(initial)
                pair[interaction] = fingerprint

                passed = run_task_verifier(
                    verifier, exported, evidence_dir / ".task-verifier-scratch" / time_mode / f"d{difficulty}-{interaction}"
                )
                if passed.get("passed") is not True or passed.get("score") != 100:
                    raise AssertionError(f"task verifier rejected valid {relative}: {passed}")

                wrong_surface = run_task_verifier(
                    verifier,
                    altered_surface_transcript(exported, interaction),
                    evidence_dir / ".task-verifier-scratch" / time_mode / f"d{difficulty}-{interaction}-wrong-surface",
                )
                if wrong_surface.get("passed") is not False or "wrong interaction surface" not in str(wrong_surface.get("feedback")):
                    raise AssertionError(
                        f"task verifier did not reject wrong-surface {relative}: {wrong_surface}"
                    )
                cells.append(
                    {
                        "condition": str(relative),
                        "initial_world_fingerprint_without_identity": fingerprint,
                        "task_verifier": passed,
                        "wrong_surface_transcript": wrong_surface,
                    }
                )
            if len(set(pair.values())) != 1:
                raise AssertionError(
                    f"difficulty {difficulty} {time_mode} interaction modes did not share one initial world: {pair}"
                )
            pairs.append(
                {
                    "time_mode": time_mode,
                    "difficulty": difficulty,
                    "shared_initial_world_fingerprint_without_identity": pair["full"],
                }
            )

    # The saved browser matrices already include a visible failed lock and the
    # server's failed grade.  Feed the equivalent empty transcript through the
    # actual wrapper as a second, exported-result failure check.
    source_export = load_json(evidence_dir / "live_matrix" / "d3-full" / "exported-result.json")
    empty_export = copy.deepcopy(source_export)
    empty_export["result"]["events"] = []
    empty_result = run_task_verifier(
        verifier, empty_export, evidence_dir / ".task-verifier-scratch" / "empty-transcript"
    )
    if empty_result.get("passed") is not False or "transcript is missing" not in str(empty_result.get("feedback")):
        raise AssertionError(f"task verifier accepted an empty transcript: {empty_result}")
    failures.append(
        {
            "source": "live_matrix/d3-full/exported-result.json",
            "mutation": "events replaced with an empty transcript",
            "task_verifier": empty_result,
        }
    )

    shutil.rmtree(evidence_dir / ".task-verifier-scratch", ignore_errors=True)
    return {
        "environment": ENVIRONMENT,
        "purpose": "Task-verifier replay of every saved browser export and cross-surface rejection audit.",
        "matrices": ["live_matrix", "paused_matrix"],
        "valid_exports_checked": len(cells),
        "valid_exports_all_passed": True,
        "cross_surface_transcripts_checked": len(cells),
        "cross_surface_transcripts_all_rejected": True,
        "same_world_interaction_pairs_checked": len(pairs),
        "same_world_interaction_pairs_all_matched": True,
        "cells": cells,
        "interaction_pairs": pairs,
        "intentional_export_failure": failures[0],
    }


def main() -> int:
    args = parse_args()
    result = audit(args)
    output = args.output or args.evidence_dir / "task-verifier-audit.json"
    write_json(output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
