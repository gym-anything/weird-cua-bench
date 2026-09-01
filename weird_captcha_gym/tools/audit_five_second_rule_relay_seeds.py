#!/usr/bin/env python3
"""Audit Five-Second Rule relay instructions from visible scene attributes."""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import math
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments/five_second_rule_env"
GENERATOR = BENCHMARK / "shared_scripts/incubator_generators/five_second_rule.py"
DEFAULT_OUTPUT = ENVIRONMENT / "evidence_docs/relay_visible_contract_audit.json"
ACTION_BOX = {"width": 86, "height": 92}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("five_second_rule_relay_audit_generator", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def visible_candidates(round_spec: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Resolve candidates by parsing the two visible instruction lines."""
    tokens = round_spec["tokens"]
    depth = int(round_spec["relay"]["relation_depth"])
    if depth < 2:
        first_label = (
            round_spec["instruction"][0]
            .removeprefix("FIRST TAP THE ")
            .removesuffix(".")
        )
        first_candidates = [
            token for token in tokens
            if f'{token["color"]} {token["shape"]}' == first_label
        ]
    else:
        relation = {
            2: "IMMEDIATELY LEFT OF",
            3: "DOWN-LEFT OF",
            4: "ON THE 45° DIAGONAL DOWN-LEFT OF",
        }[depth]
        anchor_label = (
            round_spec["instruction"][0]
            .removeprefix(f"FIRST TAP THE TOKEN {relation} THE ")
            .removesuffix(".")
        )
        anchors = [
            token for token in tokens
            if f'{token["color"]} {token["shape"]}' == anchor_label
        ]
        if len(anchors) != 1:
            return [], []
        anchor = anchors[0]
        if depth == 2:
            first_candidates = [
                token for token in tokens
                if token["x"] < anchor["x"] and token["y"] == anchor["y"]
            ]
        elif depth == 3:
            first_candidates = [
                token for token in tokens
                if token["x"] < anchor["x"] and token["y"] > anchor["y"]
            ]
        else:
            first_candidates = [
                token for token in tokens
                if token["x"] < anchor["x"]
                and token["y"] > anchor["y"]
                and abs((anchor["x"] - token["x"]) - (token["y"] - anchor["y"])) <= 1
            ]
    if depth == 0:
        second_label = (
            round_spec["instruction"][1]
            .removeprefix("THEN TAP THE ")
            .removesuffix(".")
        )
        second_candidates = [
            token for token in tokens
            if f'{token["color"]} {token["shape"]}' == second_label
        ]
    else:
        mark = (
            round_spec["instruction"][1]
            .removeprefix("THEN TAP THE OTHER TOKEN WITH ITS ")
            .removesuffix(" MARK.")
        )
        first_ids = {token["id"] for token in first_candidates}
        second_candidates = [
            token for token in tokens
            if token["id"] not in first_ids and token["mark"] == mark
        ]
    return (
        [token["id"] for token in first_candidates],
        [token["id"] for token in second_candidates],
    )


def overlap_pairs(round_spec: dict[str, Any]) -> list[list[str]]:
    pairs = []
    for index, left in enumerate(round_spec["tokens"]):
        for right in round_spec["tokens"][index + 1:]:
            if (
                abs(left["x"] - right["x"]) < ACTION_BOX["width"]
                and abs(left["y"] - right["y"]) < ACTION_BOX["height"]
            ):
                pairs.append([left["id"], right["id"]])
    return pairs


def minimum_center_distance(round_spec: dict[str, Any]) -> float:
    distances = []
    for index, left in enumerate(round_spec["tokens"]):
        for right in round_spec["tokens"][index + 1:]:
            distances.append(math.hypot(left["x"] - right["x"], left["y"] - right["y"]))
    return min(distances)


def audit(samples_per_level: int) -> dict[str, Any]:
    if samples_per_level < 1:
        raise ValueError("samples_per_level must be positive")
    generator = load_module(GENERATOR)
    task = read_json(ENVIRONMENT / "tasks/five_second_rule_seed_0001/task.json")
    controls = read_json(ENVIRONMENT / "controls.json")
    levels = {}
    all_ok = True
    for level in range(1, 6):
        first_counts: Counter[int] = Counter()
        second_counts: Counter[int] = Counter()
        overlap_worlds = 0
        mismatched_worlds = 0
        minimum_distance = float("inf")
        examples = []
        for index in range(samples_per_level):
            controlled = copy.deepcopy(task)
            controlled["_control_condition"] = {
                "difficulty": level,
                "interaction": "full",
                "real_time": "live",
                "difficulty_parameters": copy.deepcopy(
                    controls["difficulty"][str(level)]["parameters"]
                ),
            }
            public, _truth = generator.generate(
                controlled, f"relay-visible-audit-l{level}-{index:04d}"
            )
            relay = next(item for item in public["rounds"] if item["family"] == "relay_pair")
            first, second = visible_candidates(relay)
            overlaps = overlap_pairs(relay)
            first_counts[len(first)] += 1
            second_counts[len(second)] += 1
            overlap_worlds += bool(overlaps)
            minimum_distance = min(minimum_distance, minimum_center_distance(relay))
            expected = relay["predicate"]
            mismatch = (
                first != [expected["first_id"]]
                or second != [expected["second_id"]]
                or bool(overlaps)
            )
            mismatched_worlds += mismatch
            if mismatch and len(examples) < 5:
                examples.append({
                    "seed_index": index,
                    "instruction": relay["instruction"],
                    "first_candidates": first,
                    "second_candidates": second,
                    "expected": expected,
                    "overlaps": overlaps,
                })
        level_ok = mismatched_worlds == 0
        all_ok = all_ok and level_ok
        levels[str(level)] = {
            "ok": level_ok,
            "relation_depth": controls["difficulty"][str(level)]["parameters"]["relay_relation_depth"],
            "worlds_checked": samples_per_level,
            "first_visible_candidate_count_histogram": dict(sorted(first_counts.items())),
            "second_visible_candidate_count_histogram": dict(sorted(second_counts.items())),
            "overlap_worlds": overlap_worlds,
            "mismatched_worlds": mismatched_worlds,
            "minimum_center_distance_px": round(minimum_distance, 3),
            "examples": examples,
        }
    return {
        "schema_version": 1,
        "environment": "Five-Second Rule",
        "mechanic_id": "five_second_rule",
        "ok": all_ok,
        "method": (
            "The two instruction strings are parsed to obtain visible color/shape labels, "
            "mark, and relation. Candidate sets are reconstructed from those words and the "
            "visible token attributes and positions. Private predicate IDs are consulted only "
            "afterward to check whether the unique visible candidates match grading."
        ),
        "action_box_px": ACTION_BOX,
        "samples_per_level": samples_per_level,
        "total_worlds_checked": samples_per_level * 5,
        "levels": levels,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples-per-level", type=int, default=1000)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = audit(args.samples_per_level)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": result["ok"],
        "total_worlds_checked": result["total_worlds_checked"],
        "output": str(args.output),
    }, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
