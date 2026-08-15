from __future__ import annotations

import json
import random
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = REPO_ROOT / "weird_captcha_gym"
AUDIT_ROOT = BENCHMARK_ROOT / "temporal_audits"


def test_temporal_pilot_sample_is_reproducible() -> None:
    pilot = json.loads((AUDIT_ROOT / "pilot_25.json").read_text(encoding="utf-8"))
    population: list[tuple[str, str, str, int]] = []
    controls = sorted(
        (BENCHMARK_ROOT / "environments").glob("*_env/controls.json"),
        key=lambda path: path.parent.name,
    )
    for path in controls:
        contract = json.loads(path.read_text(encoding="utf-8"))
        for interaction in ("simplified", "full"):
            for difficulty in range(1, 6):
                population.append((
                    path.parent.name,
                    contract["mechanic_id"],
                    interaction,
                    difficulty,
                ))
    expected = random.Random(pilot["seed"]).sample(population, pilot["sample_size"])
    actual = [
        (
            case["environment_id"],
            case["mechanic_id"],
            case["interaction"],
            case["difficulty"],
        )
        for case in pilot["cases"]
    ]
    assert len(population) == pilot["population_size"] == 750
    assert actual == expected


def test_temporal_pilot_results_match_the_frozen_sample() -> None:
    pilot = json.loads((AUDIT_ROOT / "pilot_25.json").read_text(encoding="utf-8"))
    results = json.loads((AUDIT_ROOT / "pilot_25_results.json").read_text(encoding="utf-8"))
    labels = results["classifications"]
    assert [item["index"] for item in labels] == [item["index"] for item in pilot["cases"]]
    assert sum(item["temporal"] for item in labels) == results["counts"]["temporal"] == 15
    assert sum(not item["temporal"] for item in labels) == results["counts"]["not_temporal"] == 10
    assert [
        item["index"] for item in labels
        if item["temporal"] != item["legacy_temporal"]
    ] == results["legacy_comparison"]["disagreement_case_indexes"] == [12, 14, 18]
    assert [
        item["index"] for item in labels
        if item["temporal"] != item["subagent_temporal"]
    ] == results["reviewer_agreement"]["disagreement_case_indexes"] == [16]
