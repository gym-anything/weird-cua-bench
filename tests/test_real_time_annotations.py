from __future__ import annotations

from dataclasses import replace

from weird_captcha_gym.real_time_annotations import (
    AUDIT_CASES,
    DIFFICULTIES,
    INTERACTIONS,
)


def test_real_time_audit_skeleton_covers_all_750_cases() -> None:
    assert len(AUDIT_CASES) == 75 * 2 * 5 == 750
    assert len({case.key for case in AUDIT_CASES}) == 750
    assert len({case.environment_id for case in AUDIT_CASES}) == 75
    assert len({case.mechanic_id for case in AUDIT_CASES}) == 75

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
