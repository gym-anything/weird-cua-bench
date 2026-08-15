from __future__ import annotations

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
BASELINE = REPO / "weird_captcha_gym" / "real_time_audits" / "all_750.json"


def main() -> None:
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    ledger_path = HERE / "ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    prior = json.loads(BASELINE.read_text(encoding="utf-8"))
    labels: dict[tuple[str, int, str], str] = {}
    for environment in prior["classifications"]:
        for interaction, difficulties in environment["difficulties"].items():
            for difficulty, value in difficulties.items():
                labels[(environment["environment_id"], int(difficulty[1:]), interaction)] = (
                    "yes" if value else "no"
                )
    assert len(labels) == 750
    for case, row in zip(manifest["cases"], ledger["cases"], strict=True):
        key = (case["environment_id"], case["difficulty"], case["interaction_mode"])
        row["comparison_baseline_label"] = labels[key]
        row["first_pass_agreement_with_baseline"] = (
            row["label"] == labels[key] if row["status"] == "completed" else None
        )
    ledger["comparison_baseline"] = {
        "path": str(BASELINE.relative_to(REPO)),
        "sha256": hashlib.sha256(BASELINE.read_bytes()).hexdigest(),
        "role": "pre-existing classification matrix; never shown to Luna reviewers",
    }
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
