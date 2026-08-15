from __future__ import annotations

import hashlib
import json
from pathlib import Path

from weird_captcha_gym.real_time_annotations import AUDIT_CASES


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PROMPT = REPO / "weird_captcha_gym" / "real_time_audits" / "luna_pilot_25_2026-08-13" / "prompt.md"
DEFINITION = REPO / "weird_captcha_gym" / "docs" / "controllability" / "real-time.md"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    by_key = {
        (case.environment_id, case.difficulty, case.interaction): case
        for case in AUDIT_CASES
    }
    keys = sorted(by_key)
    assert len(keys) == 750
    cases = []
    for index, key in enumerate(keys, start=1):
        case = by_key[key]
        cases.append(
            {
                "index": index,
                "environment_id": case.environment_id,
                "mechanic_id": case.mechanic_id,
                "public_name": case.public_name,
                "difficulty": case.difficulty,
                "interaction_mode": case.interaction,
            }
        )

    manifest = {
        "schema_version": 1,
        "date": "2026-08-14",
        "purpose": "independent GPT-5.6 Luna real-time classification of all configurations",
        "population": {
            "environment_count": 75,
            "difficulty_count": 5,
            "interaction_mode_count": 2,
            "configuration_count": 750,
        },
        "ordering": "lexicographic environment_id, numeric difficulty, lexicographic interaction_mode",
        "review": {
            "model": "gpt-5.6-luna",
            "reasoning_effort": "high",
            "reviews_per_configuration": 1,
            "fork_turns": "none",
            "corrective_followups_before_scoring": 0,
            "prompt_path": str(PROMPT.relative_to(REPO)),
            "prompt_sha256": sha256(PROMPT),
            "definition_path": str(DEFINITION.relative_to(REPO)),
            "definition_sha256": sha256(DEFINITION),
        },
        "cases": cases,
    }
    ledger = {
        "schema_version": 1,
        "manifest": "manifest.json",
        "status_counts": {"pending": 750, "running": 0, "completed": 0, "failed": 0},
        "cases": [
            {
                "index": case["index"],
                "status": "pending",
                "agent_task": None,
                "label": None,
                "delta_ms": None,
                "window_ms": None,
                "clauses": {"i": None, "ii": None, "iii": None},
                "uncertainties": [],
            }
            for case in cases
        ],
    }
    HERE.mkdir(parents=True, exist_ok=True)
    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (HERE / "ledger.json").write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
