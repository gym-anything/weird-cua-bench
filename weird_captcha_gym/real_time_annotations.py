"""Diagnostic real-time classification matrix.

The settled definition lives in ``docs/controllability/real-time.md``.  This
module builds the complete environment x interaction x difficulty inventory
from the benchmark's own control and task contracts.  Classifications are
deliberately empty until the corresponding implementation has been audited.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


ENVIRONMENTS_ROOT = Path(__file__).resolve().parent / "environments"
INTERACTIONS = ("full", "simplified")
DIFFICULTIES = (1, 2, 3, 4, 5)


@dataclass(frozen=True)
class RealTimeAuditCase:
    """One case in the 75 x 2 x 5 diagnostic matrix."""

    environment_id: str
    mechanic_id: str
    public_name: str
    interaction: str
    difficulty: int
    clause_i: bool | None = None
    clause_ii: bool | None = None
    clause_iii: bool | None = None
    evidence: tuple[str, ...] = ()

    @property
    def key(self) -> tuple[str, str, int]:
        return (self.environment_id, self.interaction, self.difficulty)

    @property
    def classified(self) -> bool:
        return all(
            value is not None
            for value in (self.clause_i, self.clause_ii, self.clause_iii)
        )

    @property
    def real_time(self) -> bool | None:
        """Return the conjunction of the three settled clauses when complete."""

        if not self.classified:
            return None
        return bool(self.clause_i and self.clause_ii and self.clause_iii)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _public_name(environment_dir: Path) -> str:
    task_paths = sorted(environment_dir.glob("tasks/*/task.json"))
    if not task_paths:
        raise ValueError(f"{environment_dir.name} has no task contract")
    names = {
        str(_read_json(task_path).get("name") or "").strip()
        for task_path in task_paths
    }
    names.discard("")
    if len(names) != 1:
        raise ValueError(
            f"{environment_dir.name} must have one exact public name; found {sorted(names)!r}"
        )
    return names.pop()


def build_real_time_audit_skeleton(
    environments_root: Path = ENVIRONMENTS_ROOT,
) -> tuple[RealTimeAuditCase, ...]:
    """Build every unclassified case from canonical repository metadata."""

    cases: list[RealTimeAuditCase] = []
    for controls_path in sorted(environments_root.glob("*_env/controls.json")):
        environment_dir = controls_path.parent
        controls = _read_json(controls_path)
        mechanic_id = str(controls.get("mechanic_id") or "").strip()
        if not mechanic_id:
            raise ValueError(f"{controls_path} has no mechanic_id")

        difficulty_keys = set(controls.get("difficulty", {}))
        expected_difficulties = {str(level) for level in DIFFICULTIES}
        if difficulty_keys != expected_difficulties:
            raise ValueError(
                f"{environment_dir.name} difficulty profiles are {sorted(difficulty_keys)!r}, "
                f"expected {sorted(expected_difficulties)!r}"
            )

        interaction_controls = controls.get("interaction", {})
        missing_interactions = [
            interaction
            for interaction in INTERACTIONS
            if not interaction_controls.get(interaction, {}).get("implemented")
        ]
        if missing_interactions:
            raise ValueError(
                f"{environment_dir.name} lacks implemented interactions: "
                f"{missing_interactions!r}"
            )

        public_name = _public_name(environment_dir)
        for interaction in INTERACTIONS:
            for difficulty in DIFFICULTIES:
                cases.append(
                    RealTimeAuditCase(
                        environment_id=environment_dir.name,
                        mechanic_id=mechanic_id,
                        public_name=public_name,
                        interaction=interaction,
                        difficulty=difficulty,
                    )
                )

    return tuple(cases)


AUDIT_CASES = build_real_time_audit_skeleton()


__all__ = [
    "AUDIT_CASES",
    "DIFFICULTIES",
    "ENVIRONMENTS_ROOT",
    "INTERACTIONS",
    "RealTimeAuditCase",
    "build_real_time_audit_skeleton",
]
