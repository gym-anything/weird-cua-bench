from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from weird_captcha_gym.real_time_annotations import (
    AUDIT_CASES,
    DIFFICULTIES,
    INTERACTIONS,
    build_real_time_audit_skeleton,
)


def test_real_time_audit_skeleton_covers_all_registered_cases() -> None:
    manifest = json.loads((Path(__file__).resolve().parents[1] / "weird_captcha_gym/benchmark_manifest.json").read_text())
    expected_environments = set(manifest["environments"])
    expected_cases = len(expected_environments) * len(INTERACTIONS) * len(DIFFICULTIES)
    assert len(AUDIT_CASES) == expected_cases
    assert len({case.key for case in AUDIT_CASES}) == expected_cases
    assert {case.environment_id for case in AUDIT_CASES} == expected_environments
    assert len({case.mechanic_id for case in AUDIT_CASES}) == len(expected_environments)

    for environment_id in {case.environment_id for case in AUDIT_CASES}:
        environment_cases = [
            case for case in AUDIT_CASES if case.environment_id == environment_id
        ]
        assert {case.interaction for case in environment_cases} == set(INTERACTIONS)
        for interaction in INTERACTIONS:
            assert {
                case.difficulty
                for case in environment_cases
                if case.interaction == interaction
            } == set(DIFFICULTIES)


def test_real_time_audit_skeleton_uses_public_task_names() -> None:
    public_names_by_environment: dict[str, set[str]] = {}
    for case in AUDIT_CASES:
        public_names_by_environment.setdefault(case.environment_id, set()).add(
            case.public_name
        )

    assert all(len(names) == 1 for names in public_names_by_environment.values())
    assert all(next(iter(names)).strip() for names in public_names_by_environment.values())


def test_real_time_audit_skeleton_uses_canonical_name_with_generated_tasks(
    tmp_path: Path,
) -> None:
    environment_dir = tmp_path / "demo_env"
    controls = {
        "mechanic_id": "demo",
        "difficulty": {str(level): {} for level in DIFFICULTIES},
        "interaction": {
            interaction: {"implemented": True} for interaction in INTERACTIONS
        },
    }
    environment_dir.mkdir()
    (environment_dir / "controls.json").write_text(json.dumps(controls), encoding="utf-8")
    canonical = environment_dir / "tasks" / "demo_seed_0001"
    generated = environment_dir / "tasks" / "demo_d1_full_seed_0001"
    canonical.mkdir(parents=True)
    generated.mkdir(parents=True)
    (canonical / "task.json").write_text(
        json.dumps({"name": "Demo"}), encoding="utf-8"
    )
    (generated / "task.json").write_text(
        json.dumps({"name": "Demo · Difficulty 1 · Full Interaction"}),
        encoding="utf-8",
    )

    cases = build_real_time_audit_skeleton(tmp_path)

    assert len(cases) == len(INTERACTIONS) * len(DIFFICULTIES)
    assert {case.public_name for case in cases} == {"Demo"}


def test_real_time_audit_skeleton_starts_unclassified() -> None:
    for case in AUDIT_CASES:
        assert case.clause_i is None
        assert case.clause_ii is None
        assert case.clause_iii is None
        assert case.evidence == ()
        assert case.classified is False
        assert case.real_time is None


def test_real_time_result_is_the_three_clause_conjunction() -> None:
    case = AUDIT_CASES[0]
    assert replace(case, clause_i=True, clause_ii=True, clause_iii=True).real_time is True
    assert replace(case, clause_i=False, clause_ii=True, clause_iii=True).real_time is False
    assert replace(case, clause_i=True, clause_ii=False, clause_iii=True).real_time is False
    assert replace(case, clause_i=True, clause_ii=True, clause_iii=False).real_time is False
    assert replace(case, clause_i=True, clause_ii=None, clause_iii=True).real_time is None
