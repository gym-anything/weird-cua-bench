from __future__ import annotations

import argparse
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("index", type=int)
    parser.add_argument("status", choices=("running", "completed", "failed"))
    parser.add_argument("--agent-task")
    parser.add_argument("--label", choices=("yes", "no", "unresolved"))
    parser.add_argument("--delta-ms", type=int)
    parser.add_argument("--window-ms", type=int)
    parser.add_argument("--clause-i", choices=("true", "false"))
    parser.add_argument("--clause-ii", choices=("true", "false"))
    parser.add_argument("--clause-iii", choices=("true", "false"))
    parser.add_argument("--uncertainty", action="append", default=[])
    args = parser.parse_args()

    path = HERE / "ledger.json"
    ledger = json.loads(path.read_text(encoding="utf-8"))
    row = ledger["cases"][args.index - 1]
    if row["index"] != args.index:
        raise ValueError("ledger index mismatch")
    row["status"] = args.status
    if args.agent_task is not None:
        row["agent_task"] = args.agent_task
    if args.label is not None:
        row["label"] = args.label
    if args.delta_ms is not None:
        row["delta_ms"] = args.delta_ms
    if args.window_ms is not None:
        row["window_ms"] = args.window_ms
    for key, value in (("i", args.clause_i), ("ii", args.clause_ii), ("iii", args.clause_iii)):
        if value is not None:
            row["clauses"][key] = value == "true"
    if args.uncertainty:
        row["uncertainties"] = args.uncertainty
    if args.status == "completed" and row.get("comparison_baseline_label") is not None:
        row["first_pass_agreement_with_baseline"] = (
            row["label"] == row["comparison_baseline_label"]
        )
    counts = {key: 0 for key in ("pending", "running", "completed", "failed")}
    for item in ledger["cases"]:
        counts[item["status"]] += 1
    ledger["status_counts"] = counts
    path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
