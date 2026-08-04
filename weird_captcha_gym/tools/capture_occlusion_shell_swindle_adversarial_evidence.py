#!/usr/bin/env python3
"""Record direct-replay rejection of stale and wrong-surface shell transcripts."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "occlusion_shell_swindle_env"
GRADER_PATH = BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "occlusion_shell_swindle.py"
VERIFIER_HELPERS_PATH = BENCHMARK / "shared_runtime" / "verifier_helpers.py"


def load_grader():
    spec = importlib.util.spec_from_file_location("occlusion_shell_adversarial_grader", GRADER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load shell grader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_verifier_helpers():
    spec = importlib.util.spec_from_file_location("occlusion_shell_verifier_helpers", VERIFIER_HELPERS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load verifier helpers")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def grade_both(grader, verifier_helpers, exported: dict) -> dict:
    return {
        "server_grader": grader.grade(
            exported["result"],
            exported["ground_truth"],
            exported["public_state"],
        ),
        "exported_verifier": verifier_helpers.verify_external_mechanic(
            exported,
            "occlusion_shell_swindle",
        ),
    }


def assert_rejected(label: str, verdicts: dict) -> None:
    if any(verdict.get("passed") is True for verdict in verdicts.values()):
        raise AssertionError(f"{label} was accepted: {verdicts}")
    if not all("wrong interaction input" in str(verdict.get("feedback")) for verdict in verdicts.values()):
        raise AssertionError(f"{label} returned an unexpected rejection: {verdicts}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--simplified-exported-result",
        type=Path,
        default=ENVIRONMENT / "evidence_docs" / "live_matrix_final_fixed" / "d4-simplified" / "exported-result.json",
    )
    parser.add_argument(
        "--full-exported-result",
        type=Path,
        default=ENVIRONMENT / "evidence_docs" / "live_matrix_final_fixed" / "d4-full" / "exported-result.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ENVIRONMENT / "evidence_docs" / "adversarial_transcript_rejection.json",
    )
    args = parser.parse_args()
    grader = load_grader()
    verifier_helpers = load_verifier_helpers()
    simplified = read_json(args.simplified_exported_result)
    full = read_json(args.full_exported_result)

    accepted = {
        "simplified": grade_both(grader, verifier_helpers, simplified),
        "full": grade_both(grader, verifier_helpers, full),
    }
    if any(verdict.get("passed") is not True for mode in accepted.values() for verdict in mode.values()):
        raise AssertionError(f"browser-exported controlled transcripts did not pass direct replay: {accepted}")

    def forged_variant(exported: dict, event_kind: str, source: str) -> dict:
        forged = copy.deepcopy(exported)
        event = next(item for item in forged["result"]["events"] if item["kind"] == event_kind)
        event["input_source"] = source
        return forged

    wrong_surface = {
        "simplified_sample_as_full": grade_both(
            grader,
            verifier_helpers,
            forged_variant(simplified, "inspection_sample", "direct_cursor"),
        ),
        "simplified_selection_as_full": grade_both(
            grader,
            verifier_helpers,
            forged_variant(simplified, "round_select", "direct_shell"),
        ),
        "full_sample_as_simplified": grade_both(
            grader,
            verifier_helpers,
            forged_variant(full, "inspection_sample", "peephole_relay_choice"),
        ),
        "full_selection_as_simplified": grade_both(
            grader,
            verifier_helpers,
            forged_variant(full, "round_select", "carrier_controls"),
        ),
    }
    for label, verdicts in wrong_surface.items():
        assert_rejected(label, verdicts)

    wrong_relay = copy.deepcopy(simplified)
    first_round = wrong_relay["ground_truth"]["rounds"][0]
    decoy = (first_round.get("decoy_ports") or [None])[0]
    if not isinstance(decoy, dict):
        raise AssertionError("the D4 simplified replay needs a visible decoy relay")
    relay_event = next(
        item
        for item in wrong_relay["result"]["events"]
        if item["kind"] == "inspection_relay_arm"
        and item.get("round") == 0
        and item.get("occluder_id") == first_round["inspection"]["occluder_id"]
    )
    relay_event["occluder_id"] = decoy["occluder_id"]
    relay_event["point"] = decoy["port"]
    wrong_relay_choice = grade_both(grader, verifier_helpers, wrong_relay)
    if any(verdict.get("passed") is True for verdict in wrong_relay_choice.values()) or not all(
        "selected genuine relay" in str(verdict.get("feedback")) for verdict in wrong_relay_choice.values()
    ):
        raise AssertionError(f"decoy relay choice was accepted: {wrong_relay_choice}")

    stale = copy.deepcopy(simplified)
    stale["result"] = copy.deepcopy(stale["result"])
    stale["challenge_id"] = "stale-shell-challenge"
    stale["result"]["challenge_id"] = "stale-shell-challenge"
    stale_grade = grade_both(grader, verifier_helpers, stale)
    if any(verdict.get("passed") is True for verdict in stale_grade.values()) or not all(
        "stale shell challenge" in str(verdict.get("feedback")) for verdict in stale_grade.values()
    ):
        raise AssertionError(f"stale shell transcript was not rejected: {stale_grade}")

    output = {
        "exported_results": {
            "simplified": str(args.simplified_exported_result.relative_to(ROOT)),
            "full": str(args.full_exported_result.relative_to(ROOT)),
        },
        "accepted_browser_exports": accepted,
        "wrong_interaction_sources": wrong_surface,
        "wrong_visible_relay_choice": wrong_relay_choice,
        "stale_challenge": stale_grade,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
