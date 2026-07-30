#!/usr/bin/env python3
"""Record accepted and rejected controlled Split Boxes transcript replays."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "single_scene_split_boxes_env"
MECHANIC = "single_scene_split_boxes"
GRADER_PATH = BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py"
VERIFIER_HELPERS_PATH = BENCHMARK / "shared_runtime" / "verifier_helpers.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verdicts(grader, verifier_helpers, exported: dict[str, Any]) -> dict[str, Any]:
    return {
        "server_grader": grader.grade(exported["result"], exported["ground_truth"], exported["public_state"]),
        "exported_verifier": verifier_helpers.verify_external_mechanic(exported, MECHANIC),
    }


def require_pass(label: str, values: dict[str, Any]) -> None:
    if not all(value.get("passed") is True for value in values.values()):
        raise AssertionError(f"{label} did not replay: {values}")


def require_rejected(label: str, values: dict[str, Any]) -> None:
    if any(value.get("passed") is True for value in values.values()):
        raise AssertionError(f"{label} was accepted: {values}")


def wrong_swap_source(exported: dict[str, Any], source: str) -> dict[str, Any]:
    forged = copy.deepcopy(exported)
    event = next(event for event in forged["result"]["events"] if event.get("type") == "swap")
    event["input_source"] = source
    return forged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--simplified-exported-result",
        type=Path,
        default=ENVIRONMENT / "evidence_docs" / "browser_pairs_live_delay_final" / "d4-simplified" / "exported-result.json",
    )
    parser.add_argument(
        "--full-exported-result",
        type=Path,
        default=ENVIRONMENT / "evidence_docs" / "browser_pairs_live_delay_final" / "d4-full" / "exported-result.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ENVIRONMENT / "evidence_docs" / "adversarial_transcript_rejection.json",
    )
    args = parser.parse_args()
    grader = load_module("split_boxes_adversarial_grader", GRADER_PATH)
    verifier_helpers = load_module("split_boxes_adversarial_verifier", VERIFIER_HELPERS_PATH)
    simplified = read_json(args.simplified_exported_result)
    full = read_json(args.full_exported_result)

    accepted = {"simplified": verdicts(grader, verifier_helpers, simplified), "full": verdicts(grader, verifier_helpers, full)}
    for interaction, result in accepted.items():
        require_pass(f"accepted {interaction} browser export", result)

    wrong_surface = {
        "simplified_swap_as_full_drag": verdicts(grader, verifier_helpers, wrong_swap_source(simplified, "tile_drag")),
        "full_drag_as_simplified_slot_button": verdicts(grader, verifier_helpers, wrong_swap_source(full, "slot_button")),
    }
    for label, result in wrong_surface.items():
        require_rejected(label, result)

    stale = copy.deepcopy(simplified)
    stale["result"]["challenge_id"] = "stale-split-boxes-challenge"
    stale_result = verdicts(grader, verifier_helpers, stale)
    require_rejected("stale challenge", stale_result)

    condition_mismatch = copy.deepcopy(simplified)
    condition_mismatch["public_state"]["control_condition"]["interaction"] = "full"
    condition_result = verdicts(grader, verifier_helpers, condition_mismatch)
    require_rejected("public control condition mismatch", condition_result)

    output = {
        "environment": ENVIRONMENT.name,
        "browser_export_inputs": {
            "simplified": str(args.simplified_exported_result.relative_to(ROOT)),
            "full": str(args.full_exported_result.relative_to(ROOT)),
        },
        "accepted_browser_exports": accepted,
        "wrong_interaction_sources": wrong_surface,
        "stale_challenge": stale_result,
        "public_control_condition_mismatch": condition_result,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
