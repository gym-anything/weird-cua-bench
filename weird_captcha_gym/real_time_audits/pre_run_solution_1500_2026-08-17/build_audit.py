from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
REAL_TIME_AUDIT = ROOT / "weird_captcha_gym" / "real_time_audits" / "all_750.json"
OUTPUT_DIR = Path(__file__).resolve().parent

DIFFICULTIES = tuple(f"D{index}" for index in range(1, 6))
INTERACTIONS = ("simplified", "full")
OBSERVATION_MODES = ("live", "paused")
PRE_RUN_THRESHOLD = 0.50

# One test only: after preparation, can the solution start the autonomous
# outcome phase and then send no more outcome-affecting actions until it ends?
PASSING = {
    "clockwork_doppelganger_customs": {
        "difficulties": DIFFICULTIES,
        "interactions": INTERACTIONS,
        "evidence": (
            "The solution records and phases every operator loop before CLOCKWORK RUN; "
            "the master cycle then completes without another task action."
        ),
        "sources": [
            "weird_captcha_gym/tools/incubator_solvers/clockwork_doppelganger_customs.py",
            "weird_captcha_gym/shared_runtime/app/mechanics/clockwork_doppelganger_customs.js",
        ],
    },
    "cursor_lens_reveal": {
        "difficulties": ("D1", "D2"),
        "interactions": ("simplified",),
        "evidence": (
            "There is one echo. The solution scans and positions the coordinate lens, "
            "then CAPTURE ECHO performs the required tracking automatically without "
            "another task action."
        ),
        "sources": [
            "weird_captcha_gym/tools/incubator_solvers/cursor_lens_reveal.py",
            "weird_captcha_gym/shared_runtime/app/mechanics/cursor_lens_reveal.js",
            "weird_captcha_gym/environments/cursor_lens_reveal_env/controls.json",
        ],
    },
    "domino_autopsy": {
        "difficulties": DIFFICULTIES,
        "interactions": INTERACTIONS,
        "evidence": (
            "The solution places and levels every loose domino before DOMINO RUN; "
            "the chain and bell simulation then finish without another task action."
        ),
        "sources": [
            "weird_captcha_gym/tools/incubator_solvers/domino_autopsy.py",
            "weird_captcha_gym/shared_runtime/app/app.js",
        ],
    },
    "flat_pack_compliance": {
        "difficulties": DIFFICULTIES,
        "interactions": INTERACTIONS,
        "evidence": (
            "The solution positions, rotates, and joins every part before LOAD; "
            "the complete load sequence then finishes without another task action."
        ),
        "sources": [
            "weird_captcha_gym/tools/incubator_solvers/flat_pack_compliance.py",
            "weird_captcha_gym/shared_runtime/app/mechanics/flat_pack_compliance.js",
        ],
    },
    "relation_prompt_grounding": {
        "difficulties": DIFFICULTIES,
        "interactions": INTERACTIONS,
        "evidence": (
            "The solution places every object and sets every depth before SETTLE; "
            "the force-settle sequence then finishes without another task action."
        ),
        "sources": [
            "weird_captcha_gym/tools/incubator_solvers/relation_prompt_grounding.py",
            "weird_captcha_gym/shared_runtime/app/mechanics/relation_prompt_grounding.js",
        ],
    },
    "specular_lighthouse_relay": {
        "difficulties": ("D1",),
        "interactions": INTERACTIONS,
        "evidence": (
            "D1 has one round and one receiver whose entire motion stays inside the "
            "beam tolerance. One mirror setting before CHARGE completes the round "
            "without another task action."
        ),
        "sources": [
            "weird_captcha_gym/tools/incubator_solvers/_interaction_vii_viii_common.py",
            "weird_captcha_gym/shared_runtime/app/mechanics/_interaction_vii_viii.js",
            "weird_captcha_gym/environments/specular_lighthouse_relay_env/controls.json",
        ],
    },
    "wind_tunnel_seed_courier": {
        "difficulties": ("D1", "D2"),
        "interactions": INTERACTIONS,
        "evidence": (
            "D1-D2 have one pod and admit a constant fan assignment made before "
            "LAUNCH; the complete flight then succeeds without another task action."
        ),
        "sources": [
            "weird_captcha_gym/tools/incubator_solvers/_interaction_vii_viii_common.py",
            "weird_captcha_gym/shared_runtime/app/mechanics/_interaction_vii_viii.js",
            "weird_captcha_gym/environments/wind_tunnel_seed_courier_env/controls.json",
            "weird_captcha_gym/real_time_audits/all_750.md",
        ],
    },
}

# Seed-test rates are used where the answer varies by generated Wind-Tunnel
# instance. The other entries above are source-structural: the same action
# ordering works for every generated instance of the listed profile.
WIND_SEED_RATES = {
    "D1": {"successes": 1000, "trials": 1000},
    "D2": {"successes": 983, "trials": 1000},
    "D3": {"successes": 18, "trials": 100},
    "D4": {"successes": 0, "trials": 100},
    "D5": {"successes": 0, "trials": 100},
}

RECLASSIFIED_FROM_REAL_TIME = {
    ("relation_prompt_grounding", difficulty, interaction)
    for difficulty in DIFFICULTIES
    for interaction in INTERACTIONS
}


def pre_run_rate(mechanic_id: str, difficulty: str, interaction: str) -> tuple[float, str]:
    if mechanic_id == "wind_tunnel_seed_courier":
        measured = WIND_SEED_RATES[difficulty]
        return measured["successes"] / measured["trials"], (
            f"seed test: {measured['successes']}/{measured['trials']}"
        )
    rule = PASSING.get(mechanic_id)
    if (
        rule
        and difficulty in rule["difficulties"]
        and interaction in rule["interactions"]
    ):
        return 1.0, "source-structural: every generated instance"
    return 0.0, "source-structural: no pre-run path in the solution"


def qualifies(mechanic_id: str, difficulty: str, interaction: str) -> bool:
    rate, _basis = pre_run_rate(mechanic_id, difficulty, interaction)
    return rate >= PRE_RUN_THRESHOLD


def build() -> tuple[dict, str]:
    real_time = json.loads(REAL_TIME_AUDIT.read_text(encoding="utf-8"))
    rows = []
    row_index = 0
    for environment in real_time["classifications"]:
        mechanic_id = str(environment["mechanic_id"])
        solver = f"weird_captcha_gym/tools/incubator_solvers/{mechanic_id}.py"
        for difficulty in DIFFICULTIES:
            for interaction in INTERACTIONS:
                for observation_mode in OBSERVATION_MODES:
                    row_index += 1
                    rate, rate_basis = pre_run_rate(
                        mechanic_id, difficulty, interaction
                    )
                    passed = qualifies(mechanic_id, difficulty, interaction)
                    rule = PASSING.get(mechanic_id) if passed else None
                    reclassified = (
                        mechanic_id,
                        difficulty,
                        interaction,
                    ) in RECLASSIFIED_FROM_REAL_TIME
                    rows.append(
                        {
                            "index": row_index,
                            "environment_index": int(environment["index"]),
                            "environment_id": environment["environment_id"],
                            "mechanic_id": mechanic_id,
                            "public_name": environment["public_name"],
                            "difficulty": difficulty,
                            "interaction": interaction,
                            "observation_mode": observation_mode,
                            "pre_run_rate": rate,
                            "pre_run_rate_basis": rate_basis,
                            "pre_run_threshold": PRE_RUN_THRESHOLD,
                            "pre_run_solution": passed,
                            "current_real_time_label": bool(
                                environment["difficulties"][interaction][difficulty]
                            ),
                            "reclassified_from_real_time": reclassified,
                            "evidence": rule["evidence"] if rule else (
                                "The solution does not have a preparation-then-autonomous-run "
                                "path that finishes without later outcome-affecting actions."
                            ),
                            "sources": rule["sources"] if rule else [solver],
                        }
                    )

    passing = [row for row in rows if row["pre_run_solution"]]
    overlap = [row for row in passing if row["current_real_time_label"]]
    reclassified = [row for row in rows if row["reclassified_from_real_time"]]
    payload = {
        "schema_version": 1,
        "date": "2026-08-17",
        "criterion": (
            "A configuration is pre-run when at least 50% of its generated instances "
            "admit a successful solution that, after preparation, starts the autonomous "
            "outcome phase and sends no more outcome-affecting actions until that phase ends."
        ),
        "pre_run_threshold": PRE_RUN_THRESHOLD,
        "environment_count": len(real_time["classifications"]),
        "difficulty_count": len(DIFFICULTIES),
        "interaction_count": len(INTERACTIONS),
        "observation_mode_count": len(OBSERVATION_MODES),
        "configuration_count": len(rows),
        "counts": {
            "pre_run_solution": len(passing),
            "not_pre_run_solution": len(rows) - len(passing),
            "pre_run_and_currently_real_time": len(overlap),
            "reclassified_from_real_time": len(reclassified),
        },
        "rows": rows,
    }

    passing_groups = []
    for environment in real_time["classifications"]:
        mechanic_id = str(environment["mechanic_id"])
        rule = PASSING.get(mechanic_id)
        if not rule:
            continue
        configurations = (
            len(rule["difficulties"])
            * len(rule["interactions"])
            * len(OBSERVATION_MODES)
        )
        passing_groups.append(
            (
                environment["public_name"],
                ", ".join(rule["difficulties"]),
                ", ".join(value.title() for value in rule["interactions"]),
                configurations,
                rule["evidence"],
            )
        )

    lines = [
        "# Pre-run solution audit: 1,500 configurations",
        "",
        "Date: 2026-08-17",
        "",
        "## Test",
        "",
        payload["criterion"],
        "",
        "Final submission or certification after the run is treated as administrative.",
        "",
        "## Result",
        "",
        f"- Pre-run solution: **{len(passing)} / {len(rows)}**",
        f"- No pre-run solution: **{len(rows) - len(passing)} / {len(rows)}**",
        f"- Pre-run solution while currently labelled real-time: **{len(overlap)}**",
        f"- Reclassified from real-time by this audit: **{len(reclassified)}**",
        "",
        "The live and paused rows have the same result because the test concerns the "
        "solution's action ordering, not the observation schedule.",
        "",
        "## Configurations with a pre-run solution",
        "",
        "| Environment | Difficulties | Interaction | Pre-run rate | Live + paused rows | Evidence |",
        "|---|---|---|---:|---:|---|",
    ]
    for name, difficulties, interactions, count, evidence in passing_groups:
        mechanic_id = next(
            item["mechanic_id"]
            for item in real_time["classifications"]
            if item["public_name"] == name
        )
        if mechanic_id == "wind_tunnel_seed_courier":
            rate_text = "D1 100%; D2 98.3%"
        else:
            rate_text = "100%"
        lines.append(
            f"| {name} | {difficulties} | {interactions} | {rate_text} | {count} | {evidence} |"
        )

    lines.extend(
        [
            "",
            "## Reclassified real-time rows",
            "",
        ]
    )
    reclassified_groups = {}
    for row in reclassified:
        key = (row["public_name"], row["interaction"])
        reclassified_groups.setdefault(key, set()).add(row["difficulty"])
    if reclassified_groups:
        lines.extend(
            [
                "| Environment | Interaction | Difficulties | Live + paused rows |",
                "|---|---|---|---:|",
            ]
        )
        for (name, interaction), difficulties in sorted(reclassified_groups.items()):
            ordered = [value for value in DIFFICULTIES if value in difficulties]
            lines.append(
                f"| {name} | {interaction.title()} | {', '.join(ordered)} | {len(ordered) * 2} |"
            )
    else:
        lines.append("None.")

    lines.extend(
        [
            "",
            "## Reproduction",
            "",
            "```bash",
            "python weird_captcha_gym/real_time_audits/pre_run_solution_1500_2026-08-17/build_audit.py",
            "```",
            "",
            "The generated `results.json` contains all 1,500 rows.",
            "",
        ]
    )
    return payload, "\n".join(lines)


def main() -> None:
    payload, report = build()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (OUTPUT_DIR / "report.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
