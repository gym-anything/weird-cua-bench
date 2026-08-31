#!/usr/bin/env python3
"""Retain deterministic multi-seed Cockpit reachability evidence.

This is an in-memory contract audit. It loads the same generator, grader, and
transcript builder exercised by the focused pytest file, and never starts or
attaches to a browser.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEST_CONTRACT = ROOT / "tests" / "test_cockpit_preflight_checklist.py"
DEFAULT_OUTPUT = (
    ROOT
    / "weird_captcha_gym"
    / "environments"
    / "cockpit_preflight_checklist_env"
    / "evidence_docs"
    / "difficulty_seed_audit.json"
)


def load_contract_module():
    spec = importlib.util.spec_from_file_location("cockpit_seed_audit_contract", TEST_CONTRACT)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {TEST_CONTRACT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds-per-level", type=int, default=100)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.seeds_per_level < 1:
        raise SystemExit("--seeds-per-level must be positive")

    contract = load_contract_module()
    levels = {}
    all_passed = True
    for level in range(1, 6):
        mode_records = {}
        panels = []
        for interaction in ("simplified", "full"):
            event_counts = []
            passed = 0
            for seed_index in range(args.seeds_per_level):
                seed = f"reachability-{level}-{seed_index}"
                public, truth = contract.GENERATOR.generate(contract._task(level, interaction), seed)
                payload = contract._solution(public, interaction)
                decision = contract.GRADER.grade(payload, truth, public)
                if decision.get("passed") is True:
                    passed += 1
                event_counts.append(len(payload["events"]))
                if interaction == "full":
                    panels.append(public["panel"])
            all_passed = all_passed and passed == args.seeds_per_level
            mode_records[interaction] = {
                "passed": passed,
                "attempted": args.seeds_per_level,
                "accepted_event_count": {
                    "minimum": min(event_counts),
                    "maximum": max(event_counts),
                    "mean": round(statistics.fmean(event_counts), 3),
                },
            }
        controls = contract._task(level, "full")["_control_condition"]["difficulty_parameters"]
        levels[str(level)] = {
            "parameters": controls,
            "generated_coupling_counts": sorted({len(panel["couplings"]) for panel in panels}),
            "generated_nested_parent_counts": sorted({sum(branch.get("parent_id") is not None for branch in panel["branches"]) for panel in panels}),
            "interaction_modes": mode_records,
        }

    result = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "all_passed": all_passed,
        "seeds_per_level": args.seeds_per_level,
        "total_generated_and_graded": args.seeds_per_level * 5 * 2,
        "generator": "weird_captcha_gym/shared_scripts/incubator_generators/cockpit_preflight_checklist.py",
        "grader": "weird_captcha_gym/shared_runtime/server/incubator_graders/cockpit_preflight_checklist.py",
        "transcript_builder": "tests/test_cockpit_preflight_checklist.py::_solution",
        "levels": levels,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not all_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
