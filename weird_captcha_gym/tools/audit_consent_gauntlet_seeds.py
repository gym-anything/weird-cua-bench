#!/usr/bin/env python3
"""Retain deterministic multi-seed reachability evidence for Consent Gauntlet."""
from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
TEST_CONTRACT = ROOT / "tests/test_consent_gauntlet.py"
DEFAULT_OUTPUT = (
    ROOT
    / "weird_captcha_gym/environments/consent_gauntlet_env/evidence_docs/difficulty_seed_audit.json"
)


def load_contract_module():
    spec = importlib.util.spec_from_file_location("consent_seed_audit_contract", TEST_CONTRACT)
    if spec is None or spec.loader is None:
        raise ImportError(TEST_CONTRACT)
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
        interaction_records = {}
        reference_worlds = {}
        for interaction in ("simplified", "full"):
            passed = 0
            event_counts = []
            entry_positions = set()
            final_positions = set()
            purpose_signatures = set()
            state_signatures = set()
            link_signatures = set()
            worlds = []
            for seed_index in range(args.seeds_per_level):
                seed = f"consent-reachability-{level}-{seed_index}"
                public, truth = contract.GENERATOR.generate(contract._task(level, interaction), seed)
                payload = contract._solution(public, truth, interaction)
                decision = contract.GRADER.grade(payload, truth, public)
                passed += decision.get("passed") is True
                event_counts.append(len(payload["events"]))
                surface = public["surface"]
                entry_positions.add(next(index for index, item in enumerate(surface["entry_options"]) if item["action"] == "manage"))
                final_positions.add(next(index for index, item in enumerate(surface["final_options"]) if item["action"] == "commit"))
                purpose_signatures.add(tuple(item["label"] for item in surface["purposes"]))
                state_signatures.add(tuple(item["initial_state"] for item in surface["purposes"]))
                link_signatures.add(tuple((item["source_id"], item["target_id"]) for item in surface["links"]))
                worlds.append(surface)
            all_passed = all_passed and passed == args.seeds_per_level
            reference_worlds[interaction] = worlds
            interaction_records[interaction] = {
                "passed": passed,
                "attempted": args.seeds_per_level,
                "accepted_event_count": {
                    "minimum": min(event_counts),
                    "maximum": max(event_counts),
                    "mean": round(statistics.fmean(event_counts), 3),
                },
                "distinct_entry_correct_positions": len(entry_positions),
                "distinct_final_correct_positions": len(final_positions),
                "distinct_purpose_decks": len(purpose_signatures),
                "distinct_initial_state_patterns": len(state_signatures),
                "distinct_link_topologies": len(link_signatures),
            }
        same_world = all(
            reference_worlds["simplified"][index] == reference_worlds["full"][index]
            for index in range(args.seeds_per_level)
        )
        all_passed = all_passed and same_world
        levels[str(level)] = {
            "parameters": contract._task(level, "full")["_control_condition"]["difficulty_parameters"],
            "same_world_across_interactions_for_every_seed": same_world,
            "interaction_modes": interaction_records,
        }

    result = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "all_passed": all_passed,
        "seeds_per_level": args.seeds_per_level,
        "total_generated_and_graded": args.seeds_per_level * 5 * 2,
        "generator": "weird_captcha_gym/shared_scripts/incubator_generators/consent_gauntlet.py",
        "grader": "weird_captcha_gym/shared_runtime/server/incubator_graders/consent_gauntlet.py",
        "transcript_builder": "tests/test_consent_gauntlet.py::_solution",
        "levels": levels,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not all_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
