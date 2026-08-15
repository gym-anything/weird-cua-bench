from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent


def percent(numerator: int, denominator: int) -> str:
    return f"{100 * numerator / denominator:.2f}%"


def main() -> None:
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    ledger = json.loads((HERE / "ledger.json").read_text(encoding="utf-8"))
    protocol_errors = json.loads(
        (HERE / "protocol_errors.json").read_text(encoding="utf-8")
    )

    manifest_cases = manifest["cases"]
    ledger_cases = ledger["cases"]
    assert len(manifest_cases) == len(ledger_cases) == 750

    rows: list[dict[str, object]] = []
    for expected_index, (case, result) in enumerate(
        zip(manifest_cases, ledger_cases, strict=True), start=1
    ):
        assert case["index"] == result["index"] == expected_index
        assert result["status"] == "completed"
        assert result["label"] in {"yes", "no"}
        assert result["comparison_baseline_label"] in {"yes", "no"}
        rows.append(
            {
                "index": expected_index,
                "public_name": case["public_name"],
                "environment_id": case["environment_id"],
                "difficulty": f"D{case['difficulty']}",
                "interaction_mode": case["interaction_mode"],
                "label": result["label"],
                "delta_ms": result["delta_ms"],
                "window_ms": result["window_ms"],
                "clauses": result["clauses"],
                "uncertainties": result["uncertainties"],
                "comparison_baseline_label": result["comparison_baseline_label"],
                "first_pass_agreement_with_baseline": result[
                    "first_pass_agreement_with_baseline"
                ],
                "agent_task": result["agent_task"],
            }
        )

    disagreements = [
        row for row in rows if not row["first_pass_agreement_with_baseline"]
    ]
    agreement_count = len(rows) - len(disagreements)
    label_counts = Counter(row["label"] for row in rows)
    baseline_counts = Counter(row["comparison_baseline_label"] for row in rows)
    direction_counts = Counter(
        (row["comparison_baseline_label"], row["label"])
        for row in disagreements
    )
    difficulty_counts = Counter(row["difficulty"] for row in disagreements)
    interaction_counts = Counter(row["interaction_mode"] for row in disagreements)
    environment_counts = Counter(row["public_name"] for row in disagreements)

    output = {
        "schema_version": 1,
        "review": manifest["review"],
        "comparison_baseline": ledger["comparison_baseline"],
        "counts": {
            "total": len(rows),
            "luna_yes": label_counts["yes"],
            "luna_no": label_counts["no"],
            "baseline_yes": baseline_counts["yes"],
            "baseline_no": baseline_counts["no"],
            "agreement": agreement_count,
            "disagreement": len(disagreements),
            "agreement_rate": agreement_count / len(rows),
            "baseline_yes_luna_no": direction_counts[("yes", "no")],
            "baseline_no_luna_yes": direction_counts[("no", "yes")],
        },
        "disagreement_counts": {
            "by_difficulty": dict(sorted(difficulty_counts.items())),
            "by_interaction_mode": dict(sorted(interaction_counts.items())),
            "by_environment": dict(
                sorted(environment_counts.items(), key=lambda item: (-item[1], item[0]))
            ),
        },
        "protocol_errors": protocol_errors["errors"],
        "cases": rows,
    }
    (HERE / "results.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# GPT-5.6 Luna real-time classification: all 750 configurations",
        "",
        "## Protocol",
        "",
        f"- Population: {len(rows)} configurations (75 environments x 5 difficulties x 2 interaction modes).",
        "- One fresh GPT-5.6 Luna context per configuration, high reasoning effort.",
        "- Every reviewer received the same frozen prompt and settled mathematical definition.",
        "- No reviewer saw the prior classification matrix or another reviewer's answer.",
        "- No corrective follow-up occurred before a first-pass result was recorded.",
        "- The prior matrix is used only for the independent comparison below; first-pass labels are not changed.",
        "",
        "## Result",
        "",
        f"- Luna: {label_counts['yes']} yes, {label_counts['no']} no.",
        f"- Prior matrix: {baseline_counts['yes']} yes, {baseline_counts['no']} no.",
        f"- First-pass agreement: {agreement_count}/{len(rows)} ({percent(agreement_count, len(rows))}).",
        f"- First-pass disagreement: {len(disagreements)}/{len(rows)} ({percent(len(disagreements), len(rows))}).",
        f"- Direction: {direction_counts[('yes', 'no')]} prior-yes/Luna-no; {direction_counts[('no', 'yes')]} prior-no/Luna-yes.",
        "",
        "No disagreement was corrected, adjudicated, or converted into agreement.",
        "",
        "## Disagreements by difficulty and interaction",
        "",
        "| Group | Count |",
        "|---|---:|",
    ]
    for difficulty in ["D1", "D2", "D3", "D4", "D5"]:
        lines.append(f"| {difficulty} | {difficulty_counts[difficulty]} |")
    for interaction in ["full", "simplified"]:
        lines.append(f"| {interaction} | {interaction_counts[interaction]} |")

    lines.extend(
        [
            "",
            "## Disagreements by environment",
            "",
            "| Environment | Count |",
            "|---|---:|",
        ]
    )
    for environment, count in sorted(
        environment_counts.items(), key=lambda item: (-item[1], item[0])
    ):
        lines.append(f"| {environment} | {count} |")

    lines.extend(
        [
            "",
            "## All 44 first-pass disagreements",
            "",
            "| # | Environment | Difficulty | Interaction | Prior | Luna | Clauses (i/ii/iii) |",
            "|---:|---|---|---|---|---|---|",
        ]
    )
    for row in disagreements:
        clauses = row["clauses"]
        clause_text = "/".join(
            "T" if clauses[key] else "F" for key in ("i", "ii", "iii")
        )
        lines.append(
            f"| {row['index']} | {row['public_name']} | {row['difficulty']} | "
            f"{row['interaction_mode']} | {row['comparison_baseline_label']} | "
            f"{row['label']} | {clause_text} |"
        )

    lines.extend(
        [
            "",
            "## Protocol error",
            "",
            "Cases 171-180 were initially assigned with the wrong environment name. Those ten answers were invalid, excluded, and rerun in fresh Luna contexts with the correct Fake Desktop / Automation Inversion configuration. Only the replacement first-pass answers are counted.",
            "",
            "## Artifacts",
            "",
            "- `manifest.json`: frozen population and prompt/definition hashes.",
            "- `ledger.json`: recorded first-pass labels, clause booleans, timing witnesses, uncertainties, and baseline comparison.",
            "- `results.json`: complete joined 750-row matrix plus summary counts.",
            "- `protocol_errors.json`: excluded invalid assignments and replacement disposition.",
            "",
            "The ledger stores structured first-pass decisions rather than the reviewers' complete prose responses.",
        ]
    )
    (HERE / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
