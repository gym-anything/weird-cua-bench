"""Contract tests for the source-reviewed capability configuration matrix."""

from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy

import pytest

from weird_captcha_gym.dashboard.capability_annotations import (
    ANNOTATIONS,
    CAPABILITY_AUDIT_PATH,
    build_capability_annotations,
    build_capability_profiles,
    capability_names,
    get_capability_labels,
    load_capability_audit,
)


LEGACY_SNAPSHOT_PATH = CAPABILITY_AUDIT_PATH.parents[0].parent / "temporal_audits" / "legacy_environment_annotations_2026-08-13.json"


def _audit() -> dict:
    assert CAPABILITY_AUDIT_PATH.exists(), "the packaged capability audit is required"
    return load_capability_audit()


def test_legacy_annotations_remain_unchanged_when_building() -> None:
    original = deepcopy(ANNOTATIONS)
    built = build_capability_annotations()
    assert ANNOTATIONS == original
    assert built is not ANNOTATIONS
    assert built.keys() >= ANNOTATIONS.keys()


def test_frozen_legacy_temporal_snapshot_still_matches_built_annotations() -> None:
    snapshot = json.loads(LEGACY_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    built = build_capability_annotations()
    assert snapshot["annotation_count"] == 75
    for item in snapshot["annotations"]:
        annotation = built[item["mechanic_id"]]
        assert annotation["public_name"] == item["public_name"]
        assert annotation["temporal"] == item["temporal"]


def test_audit_has_eighty_entries_and_ten_profiles_per_entry() -> None:
    audit = _audit()
    profiles = build_capability_profiles()
    assert len(audit["environments"]) == 80
    assert set(profiles) == set(audit["environments"])
    for mechanic_id, entry in audit["environments"].items():
        profile = profiles[mechanic_id]
        assert set(profile["configurations"]) == {"full", "simplified"}
        assert all(set(profile["configurations"][mode]) == {"1", "2", "3", "4", "5"}
                   for mode in ("full", "simplified"))
        for mode in ("full", "simplified"):
            for level in range(1, 6):
                labels = profile["configurations"][mode][str(level)]
                assert set(labels) == {"visual", "temporal", "reasoning_planning", "exploration_interface"}
        assert profile["baseline"] == entry["baseline"]


def test_audit_baseline_label_counts_are_frozen() -> None:
    audit = _audit()
    entries = audit["environments"].values()
    assert Counter(entry["labels"]["visual"] for entry in entries) == {"2D": 76, "3D": 4}
    entries = audit["environments"].values()
    assert Counter(entry["labels"]["temporal"] for entry in entries) == {True: 37, False: 43}
    entries = audit["environments"].values()
    assert Counter(entry["labels"]["reasoning_planning"] for entry in entries) == {True: 75, False: 5}
    entries = audit["environments"].values()
    assert Counter(entry["labels"]["exploration_interface"] for entry in entries) == {True: 28, False: 52}


def test_nine_focused_adjudications_are_present() -> None:
    audit = _audit()["environments"]
    expected = {
        "ballast_lantern": {"visual": "2D", "temporal": True, "reasoning_planning": True, "exploration_interface": False},
        "charter_of_the_nine_cantons": {"visual": "2D", "temporal": True, "reasoning_planning": True, "exploration_interface": True},
        "collision_chimes": {"visual": "2D", "temporal": True, "reasoning_planning": True, "exploration_interface": False},
        "flip_gate_cascade": {"visual": "2D", "temporal": False, "reasoning_planning": True, "exploration_interface": True},
        "fluke_census": {"visual": "2D", "temporal": True, "reasoning_planning": True, "exploration_interface": True},
        "pocket_locksmith": {"visual": "3D", "temporal": False, "reasoning_planning": True, "exploration_interface": True},
        "restless_piston": {"visual": "2D", "temporal": True, "reasoning_planning": True, "exploration_interface": False},
        "two_season_strand": {"visual": "2D", "temporal": True, "reasoning_planning": True, "exploration_interface": True},
        "unwatched_wing": {"visual": "3D", "temporal": True, "reasoning_planning": True, "exploration_interface": True},
    }
    assert {name: audit[name]["labels"] for name in expected} == expected


def test_configuration_exceptions_override_only_their_declared_profiles() -> None:
    audit = _audit()
    profile_count = 0
    for mechanic_id, entry in audit["environments"].items():
        for exception in entry["configuration_exceptions"]:
            profile_count += len(exception["difficulties"]) * len(exception["interaction_modes"])
            for difficulty in exception["difficulties"]:
                for interaction in exception["interaction_modes"]:
                    labels = get_capability_labels(mechanic_id, difficulty, interaction)
                    assert labels is not None
                    assert labels[exception["capability"]] == exception["label"]
    assert profile_count > 0


def test_audited_baseline_lookup_and_capability_name_order() -> None:
    audit = _audit()
    for mechanic_id, entry in audit["environments"].items():
        baseline = entry["baseline"]
        labels = get_capability_labels(mechanic_id, baseline["difficulty"], baseline["interaction"])
        assert labels is not None
        assert labels == entry["labels"]
        assert capability_names(labels)[0] == f"visual understanding: {labels['visual']}"
        assert capability_names(labels) == [
            f"visual understanding: {labels['visual']}",
            *(["temporal understanding and memory"] if labels["temporal"] else []),
            *(["reasoning and planning"] if labels["reasoning_planning"] else []),
            *(["exploration and interface understanding"] if labels["exploration_interface"] else []),
        ]
    assert get_capability_labels("does_not_exist", 3, "full") is None
    assert get_capability_labels(next(iter(audit["environments"])), 0, "full") is None
    assert get_capability_labels(next(iter(audit["environments"])), 3, "unknown") is None


def test_malformed_present_audit_is_rejected(tmp_path) -> None:
    path = tmp_path / "audit.json"
    path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_capability_audit(path)


def test_capability_names_rejects_incomplete_labels() -> None:
    with pytest.raises(ValueError):
        capability_names({"visual": "2D"})
