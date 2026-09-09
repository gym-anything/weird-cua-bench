"""Contract tests for audited task metadata and controlled variants."""

from __future__ import annotations

import json
from pathlib import Path

from weird_captcha_gym.dashboard.capability_annotations import (
    CAPABILITY_AUDIT_PATH,
    capability_names,
    get_capability_labels,
    load_capability_audit,
)
from weird_captcha_gym.tools.materialize_controlled_tasks import controlled_task


ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENTS = ROOT / "weird_captcha_gym" / "environments"
AUDIT_REFERENCE = "weird_captcha_gym/capability_audits/new_environments_2026-09-08.json"


def _task_path(mechanic_id: str) -> Path:
    return (
        ENVIRONMENTS
        / f"{mechanic_id}_env"
        / "tasks"
        / f"{mechanic_id}_seed_0001"
        / "task.json"
    )


def _load_task(mechanic_id: str) -> dict:
    return json.loads(_task_path(mechanic_id).read_text(encoding="utf-8"))


def _load_controls(mechanic_id: str) -> dict:
    return json.loads(
        (
            ENVIRONMENTS
            / f"{mechanic_id}_env"
            / "controls.json"
        ).read_text(encoding="utf-8")
    )


def test_eighty_canonical_tasks_reference_the_audited_baseline_configuration() -> None:
    audit = load_capability_audit()
    assert CAPABILITY_AUDIT_PATH.exists()
    assert len(audit["environments"]) == 80

    for mechanic_id, entry in audit["environments"].items():
        task = _load_task(mechanic_id)
        metadata = task["metadata"]
        baseline = entry["baseline"]
        labels = get_capability_labels(
            mechanic_id, baseline["difficulty"], baseline["interaction"]
        )
        assert labels is not None
        assert metadata["capabilities"] == capability_names(labels)
        assert metadata["capability_audit"] == AUDIT_REFERENCE
        assert metadata["capability_configuration"] == baseline
        assert "capability_audit" not in task
        assert "capability_configuration" not in task


def test_all_eight_hundred_controlled_variants_resolve_audited_labels() -> None:
    audit = load_capability_audit()["environments"]
    assert len(audit) == 80

    for mechanic_id, entry in audit.items():
        base = _load_task(mechanic_id)
        controls = _load_controls(mechanic_id)
        for interaction in ("simplified", "full"):
            for difficulty in range(1, 6):
                profile = controls["difficulty"][str(difficulty)]
                task = controlled_task(
                    base,
                    mechanic_id=mechanic_id,
                    level=difficulty,
                    interaction=interaction,
                    profile=profile,
                    task_dir_name=f"{mechanic_id}_d{difficulty}_{interaction}_seed_0001",
                )
                metadata = task["metadata"]
                labels = get_capability_labels(mechanic_id, difficulty, interaction)
                assert labels is not None
                assert metadata["capabilities"] == capability_names(labels)
                assert metadata["capability_audit"] == AUDIT_REFERENCE
                assert metadata["capability_configuration"] == {
                    "difficulty": difficulty,
                    "interaction": interaction,
                }
                assert metadata["control_condition"] == {
                    "difficulty": difficulty,
                    "interaction": interaction,
                    "real_time": "live",
                    "difficulty_parameters": profile["parameters"],
                }


def test_controlled_variants_preserve_description_and_use_profile_instruction() -> None:
    audit = load_capability_audit()["environments"]

    for mechanic_id in audit:
        base = _load_task(mechanic_id)
        controls = _load_controls(mechanic_id)
        for interaction in ("simplified", "full"):
            for difficulty in range(1, 6):
                profile = controls["difficulty"][str(difficulty)]
                task = controlled_task(
                    base,
                    mechanic_id=mechanic_id,
                    level=difficulty,
                    interaction=interaction,
                    profile=profile,
                    task_dir_name="metadata-contract",
                )
                assert task["description"] == base["description"]
                expected_instruction = (profile.get("natural_language_by_interaction") or {}).get(
                    interaction
                ) or profile.get("natural_language") or base["natural_language"]
                if mechanic_id == "slot_reel_capture" and interaction == "simplified":
                    # This environment intentionally specializes the generated
                    # instruction from its reel-count and capture-window profile.
                    assert task["natural_language"].startswith("Click CAPTURE SYMBOL")
                else:
                    assert task["natural_language"] == expected_instruction
                assert task["metadata"]["control_condition"]["difficulty_parameters"] == profile[
                    "parameters"
                ]


def test_apothecary_controls_and_canonical_interaction_profiles_match_audit() -> None:
    mechanic_id = "apothecary_dead_reckoning"
    entry = load_capability_audit()["environments"][mechanic_id]
    difficulty = entry["baseline"]["difficulty"]
    controls = _load_controls(mechanic_id)
    task_profiles = _load_task(mechanic_id)["metadata"]["capabilities_by_interaction"]

    for interaction in ("simplified", "full"):
        labels = get_capability_labels(mechanic_id, difficulty, interaction)
        assert labels is not None
        expected = capability_names(labels)
        assert controls["interaction"][interaction]["capabilities"] == expected
        assert task_profiles[interaction] == expected


def test_seventy_five_non_audited_canonical_tasks_have_no_audit_metadata() -> None:
    audit_ids = set(load_capability_audit()["environments"])
    canonical = sorted(ENVIRONMENTS.glob("*_env/tasks/*_seed_0001/task.json"))
    legacy = [
        path
        for path in canonical
        if path.parent.parent.parent.name[:-4] not in audit_ids
    ]
    assert len(canonical) == 155
    assert len(legacy) == 75

    for path in legacy:
        current = json.loads(path.read_text(encoding="utf-8"))
        metadata = current["metadata"]
        assert "capability_audit" not in metadata
        assert "capability_configuration" not in metadata
        mechanic_id = path.parent.parent.parent.name[:-4]
        controls = _load_controls(mechanic_id)
        baseline = controls["baseline"]
        variant = controlled_task(
            current,
            mechanic_id=mechanic_id,
            level=baseline["difficulty"],
            interaction=baseline["interaction"],
            profile=controls["difficulty"][str(baseline["difficulty"])],
            task_dir_name="legacy-metadata-contract",
        )
        assert "capability_audit" not in variant["metadata"]
        assert "capability_configuration" not in variant["metadata"]
        assert variant["metadata"].get("capabilities") == metadata.get("capabilities")
