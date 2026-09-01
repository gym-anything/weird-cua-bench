#!/usr/bin/env python3
"""Retain deterministic multi-seed reachability evidence for Fence the Fox."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import statistics
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEST_CONTRACT = ROOT / "tests/test_fence_the_fox.py"
DEFAULT_OUTPUT = (
    ROOT / "weird_captcha_gym/environments/fence_the_fox_env/evidence_docs/difficulty_seed_audit.json"
)


def load_contract_module():
    spec = importlib.util.spec_from_file_location("fence_fox_seed_audit_contract", TEST_CONTRACT)
    if spec is None or spec.loader is None:
        raise ImportError(TEST_CONTRACT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fingerprint(world: dict) -> str:
    encoded = json.dumps(world, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds-per-level", type=int, default=12)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.seeds_per_level < 2:
        raise SystemExit("--seeds-per-level must be at least 2")

    contract = load_contract_module()
    all_passed = True
    levels = {}
    all_fingerprints: set[str] = set()
    for level in range(1, 6):
        records = {"simplified": [], "full": []}
        for seed_index in range(args.seeds_per_level):
            seed = f"fence-fox-audit-{level}-{seed_index}"
            for interaction in ("simplified", "full"):
                started = time.perf_counter()
                public, truth = contract.GENERATOR.generate(contract._task(level, interaction), seed)
                elapsed = time.perf_counter() - started
                decision = contract.GRADER.grade(contract._solution(public, truth, interaction), truth, public)
                world_hash = fingerprint(contract._world(public))
                records[interaction].append({
                    "seed": seed,
                    "world_fingerprint": world_hash,
                    "verified_winning_plan_turns": int(truth["solver_plan_turns"]),
                    "global_shortest_certified": bool(truth["shortest_plan_certified"]),
                    "shortest_plan_turns": truth["shortest_plan_turns"],
                    "shortest_plan_proof": truth["shortest_plan_proof"],
                    "generation_seconds": elapsed,
                    "passed": decision.get("passed") is True,
                })

        same_world = all(
            records["simplified"][index]["world_fingerprint"] == records["full"][index]["world_fingerprint"]
            for index in range(args.seeds_per_level)
        )
        simplified = records["simplified"]
        plan_turns = [item["verified_winning_plan_turns"] for item in simplified]
        timings = [item["generation_seconds"] for items in records.values() for item in items]
        fingerprints = {item["world_fingerprint"] for item in simplified}
        all_fingerprints.update(fingerprints)
        level_passed = (
            same_world
            and len(fingerprints) == args.seeds_per_level
            and all(item["passed"] for items in records.values() for item in items)
        )
        all_passed = all_passed and level_passed
        levels[str(level)] = {
            "passed": level_passed,
            "parameters": contract._task(level, "simplified")["_control_condition"]["difficulty_parameters"],
            "same_world_across_interactions_for_every_seed": same_world,
            "distinct_worlds": len(fingerprints),
            "verified_winning_plan_turns": {
                "minimum": min(plan_turns),
                "maximum": max(plan_turns),
                "mean": round(statistics.fmean(plan_turns), 3),
                "observed": plan_turns,
            },
            "global_shortest_certification": {
                "certified_worlds": sum(item["global_shortest_certified"] for item in simplified),
                "all_worlds_certified": all(item["global_shortest_certified"] for item in simplified),
                "proof_kinds": sorted({item["shortest_plan_proof"] for item in simplified}),
                "scope_note": (
                    "Radius-three worlds use exhaustive breadth-first search. "
                    "Radius-four worlds retain bounded-search winning plans and do not claim global minimality."
                ),
            },
            "generation_seconds": {
                "minimum": round(min(timings), 4),
                "maximum": round(max(timings), 4),
                "mean": round(statistics.fmean(timings), 4),
            },
            "simplified_passed": sum(item["passed"] for item in records["simplified"]),
            "full_passed": sum(item["passed"] for item in records["full"]),
        }

    result = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "all_passed": all_passed,
        "seeds_per_level": args.seeds_per_level,
        "distinct_generated_worlds": len(all_fingerprints),
        "total_generated_and_graded": args.seeds_per_level * 5 * 2,
        "generator": "weird_captcha_gym/shared_scripts/incubator_generators/fence_the_fox.py",
        "grader": "weird_captcha_gym/shared_runtime/server/incubator_graders/fence_the_fox.py",
        "transcript_builder": "tests/test_fence_the_fox.py::_solution",
        "levels": levels,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
