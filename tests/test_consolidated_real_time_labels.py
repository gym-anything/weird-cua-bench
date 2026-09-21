"""Coverage and provenance checks for the consolidated 1,000 real-time labels."""

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDITS = ROOT / "weird_captcha_gym/real_time_audits"


def load_catalog():
    return json.loads((AUDITS / "all_1000.json").read_text())


def identity(row):
    return row["environment_id"], row["difficulty"], row["interaction_mode"]


def test_complete_cartesian_product_and_counts():
    data = load_catalog()
    rows = data["configurations"]
    environments = {row["environment_id"] for row in rows}
    assert len(rows) == len({identity(row) for row in rows}) == 1000
    assert len(environments) == 100
    assert {identity(row) for row in rows} == {
        (env, level, mode)
        for env in environments
        for level in range(1, 6)
        for mode in ("full", "simplified")
    }
    assert Counter(row["label"] for row in rows) == {"yes": 246, "no": 754}
    assert data["counts"]["labels"] == {"yes": 246, "no": 754}
    assert data["counts"]["by_label_source"] == Counter(row["label_source"] for row in rows)
    assert data["counts"]["by_label_source"] == {
        "selected_100": 490, "historical_50_rerun": 452,
        "forced_perspective_rerun": 10, "final_adjudication": 48,
    }
    for summary in data["counts"]["by_difficulty_and_interaction"]:
        subset = [row for row in rows if (row["difficulty"], row["interaction_mode"]) ==
                  (summary["difficulty"], summary["interaction_mode"])]
        assert len(subset) == 100
        assert Counter(row["label"] for row in subset) == {
            "yes": summary["yes"], "no": summary["no"],
        }
    assert Counter(row["label"] for row in rows if row["difficulty"] == 5 and
                   row["interaction_mode"] == "full") == {"yes": 32, "no": 68}


def test_sources_unchanged_and_exact_merge_precedence():
    data = load_catalog()
    sources = {}
    for name, artifact in data["sources"].items():
        raw = (ROOT / artifact["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == artifact["sha256"]
        sources[name] = json.loads(raw)
    assert data["merge_order"] == [
        "selected_100", "historical_50_rerun", "forced_perspective_rerun", "final_adjudication",
    ]
    original = {identity(row): row for row in sources["selected_100"]["selected_100_combined"]}
    expected = {key: row["label"] for key, row in original.items()}
    expected_issues = {key: row.get("issues", []) for key, row in original.items()}
    for game in sources["historical_50_rerun"]["games"]:
        for mode, labels in game["fresh_labels_by_difficulty"].items():
            for level, label in enumerate(labels, 1):
                key = game["environment_id"], level, mode
                expected[key] = label
                index = game["configuration_indices_by_difficulty"][mode][level - 1]
                expected_issues[key] = [
                    issue for entry in game["report_validation"]["issues"]
                    if entry["configuration"] == index for issue in entry["issues"]
                ]
    for row in sources["forced_perspective_rerun"]["configuration_reports"]:
        expected[identity(row)] = row["label"]
    for row in sources["final_adjudication"]["decisions"]:
        key = row["environment_id"], row["difficulty"], row["interaction"]
        assert expected[key] == row["reviewer_label"]
        expected[key] = row["final_label"]
    assert {identity(row): row["label"] for row in data["configurations"]} == expected
    for row in data["configurations"]:
        assert row["public_name"] == original[identity(row)]["public_name"]
        assert row["source_issues"] == expected_issues[identity(row)]
    assert data["preserved_source_flags"] == sources["historical_50_rerun"]["report_flags"]
    assert sum(bool(row["source_issues"]) for row in data["configurations"]) == 10


def test_all_48_final_adjudications_win_over_reviewer_labels():
    data = load_catalog()
    rows = {identity(row): row for row in data["configurations"]}
    final = json.loads((ROOT / data["sources"]["final_adjudication"]["path"]).read_text())
    for decision in final["decisions"]:
        row = rows[decision["environment_id"], decision["difficulty"], decision["interaction"]]
        assert row["label_source"] == "final_adjudication"
        assert row["label"] == decision["final_label"]
        assert row["source_case_index"] == decision["configuration_index"]
        assert row["reviewer_label"] == decision["reviewer_label"]
        assert row["historical_label"] == decision["historical_label"]
        assert row["rationale_id"] == decision["rationale_id"]
