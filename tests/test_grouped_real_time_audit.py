"""Game-grouped continuation preserves the original per-configuration audit."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


AUDIT = Path(__file__).resolve().parents[1] / "weird_captcha_gym/real_time_audits/selected_100_pending_490_2026-09-10"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def audit(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("grouped_real_time_report", AUDIT / "build_report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "audit"
    root.mkdir()
    source = tmp_path / "source"
    source.mkdir()
    (source / "implementation.py").write_text("# Complete implementation\n# No autonomous changes\n")
    (root / "prompt.md").write_text("Original frozen prompt")
    cases = [
        {"case_index": (level - 1) * 2 + position + 1, "environment_id": "example_env", "public_name": "Example", "difficulty": level, "interaction_mode": mode}
        for level in range(1, 6) for position, mode in enumerate(("full", "simplified"))
    ]
    parent = {"source_root": str(source), "source_revision": "revision", "prompt_sha256": digest(root / "prompt.md"), "cases": cases}
    write_json(root / "manifest.json", parent)
    write_json(root / "provenance/old_cancelled.json", {"status": "failed", "exit_code": -15})
    group = root / "grouped_2026-09-11"
    group.mkdir()
    (group / "prompt.md").write_text("One game, ten configurations")
    hashes = {str(p.relative_to(root)): digest(p) for p in (root / "provenance").glob("*.json")}
    game = {"case_index": 7, "environment_id": "example_env", "public_name": "Example", "all_configuration_indices": list(range(1, 11)), "configurations": [{k: case[k] for k in ("case_index", "difficulty", "interaction_mode")} for case in cases], "preserved_configuration_indices": []}
    manifest = {**parent, "prompt_sha256": digest(group / "prompt.md"), "parent_manifest_sha256": digest(root / "manifest.json"), "parent_prompt_sha256": digest(root / "prompt.md"), "preserved_parent_files": {"folders": ["first_pass", "provenance"], "glob": "*.json", "count": len(hashes), "sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()}, "population": {"new_configuration_judgments": 10}, "cases": [game]}
    write_json(group / "manifest.json", manifest)
    monkeypatch.setattr(module, "ROOT", root)
    return module, root, group, parent, manifest


def complete(audit):
    module, root, group, parent, manifest = audit
    reports = []
    for config in manifest["cases"][0]["configurations"]:
        reports.append({**config, "environment_id": "example_env", "public_environment_name": "Example", "label": "no", "clause_i": {"holds": False, "reason": "A fixed policy suffices."}, "clause_ii": {"holds": True, "reason": "Current visible information suffices."}, "clause_iii": {"holds": False, "reason": "No autonomous changes."}, "pre_run": {"threshold": 0.5, "at_least_half": None, "reason": "Mathematical definition already fails."}, "files_read_completely": ["implementation.py"], "source_evidence": [{"path": "implementation.py", "lines": "1-2", "claim": "No autonomous changes."}]})
    report_path = group / "first_pass/007_example_env.json"
    write_json(report_path, {"case_index": 7, "environment_id": "example_env", "public_environment_name": "Example", "configuration_reports": reports})
    receipt = {"status": "completed", "first_pass_sha256": digest(report_path), "manifest_sha256": digest(group / "manifest.json"), "prompt_sha256": digest(group / "prompt.md"), "source_revision": "revision"}
    write_json(group / "provenance/007_example_env.json", receipt)
    return report_path


def test_pending_is_one_game_and_ten_configurations(audit):
    module, root, group, parent, manifest = audit
    rows, counts = module.grouped_reviews(parent)
    assert len(rows) == 10
    assert {row["status"] for row in rows.values()} == {"pending"}
    assert counts == {"population": 1, "status": {"pending": 1}}


def test_one_completed_game_maps_to_ten_judgments_without_copying(audit):
    module, root, group, parent, manifest = audit
    old = (root / "provenance/old_cancelled.json").read_bytes()
    complete(audit)
    rows, counts = module.grouped_reviews(parent)
    assert counts == {"population": 1, "status": {"reviewed": 1}}
    assert all(row["label"] == "no" and row["status"] == "reviewed" and not row["issues"] for row in rows.values())
    assert {row["report_member_case_index"] for row in rows.values()} == set(range(1, 11))
    assert len({row["first_pass_path"] for row in rows.values()}) == 1
    assert not (root / "first_pass").exists()
    assert (root / "provenance/old_cancelled.json").read_bytes() == old


@pytest.mark.parametrize("change", ["missing", "duplicate", "extra", "wrong_game"])
def test_group_identity_and_exact_coverage_are_required(audit, change):
    module, root, group, parent, manifest = audit
    path = complete(audit)
    payload = json.loads(path.read_text())
    if change == "missing":
        payload["configuration_reports"].pop()
    elif change == "duplicate":
        payload["configuration_reports"].append(payload["configuration_reports"][0])
    elif change == "extra":
        payload["configuration_reports"].append({**payload["configuration_reports"][0], "case_index": 99})
    else:
        payload["environment_id"] = "wrong_env"
    write_json(path, payload)
    rows, counts = module.grouped_reviews(parent)
    assert counts["status"] == {"invalid_report": 1}
    assert all(row["status"] == "invalid_report" and row["label"] is None for row in rows.values())
    assert all(any(issue.startswith("invalid_group_report:") for issue in row["issues"]) for row in rows.values())


def test_partial_game_preserves_six_finished_configurations(audit):
    module, root, group, parent, manifest = audit
    game = manifest["cases"][0]
    game["configurations"] = game["configurations"][:4]
    game["preserved_configuration_indices"] = list(range(5, 11))
    manifest["population"]["new_configuration_judgments"] = 4
    write_json(group / "manifest.json", manifest)
    complete(audit)
    rows, counts = module.grouped_reviews(parent)
    assert set(rows) == {1, 2, 3, 4}
    assert counts["status"] == {"reviewed": 1}


@pytest.mark.parametrize("status,alive,expected", [("running", True, "running"), ("running", False, "process_interrupted"), ("failed", False, "process_failed")])
def test_process_status_applies_to_whole_assignment(audit, monkeypatch, status, alive, expected):
    module, root, group, parent, manifest = audit
    write_json(group / "provenance/007_example_env.json", {"status": status, "pid": 123})
    monkeypatch.setattr(module, "process_exists", lambda pid: alive)
    rows, counts = module.grouped_reviews(parent)
    assert counts["status"] == {expected: 1}
    assert {row["status"] for row in rows.values()} == {expected}


def test_old_artifact_mutation_is_rejected(audit):
    module, root, group, parent, manifest = audit
    write_json(root / "provenance/old_cancelled.json", {"changed": True})
    with pytest.raises(AssertionError, match="Preserved first-phase artifacts changed"):
        module.grouped_reviews(parent)


def test_grouped_prompt_mutation_is_rejected(audit):
    module, root, group, parent, manifest = audit
    (group / "prompt.md").write_text("Changed definition")
    with pytest.raises(AssertionError, match="Grouped prompt changed"):
        module.grouped_reviews(parent)


def test_semantic_flags_do_not_rewrite_labels(audit):
    module, root, group, parent, manifest = audit
    path = complete(audit)
    payload = json.loads(path.read_text())
    payload["configuration_reports"][0]["label"] = "yes"
    write_json(path, payload)
    rows, _ = module.grouped_reviews(parent)
    assert rows[1]["label"] == "yes"
    assert "yes_without_three_clauses" in rows[1]["issues"]
    assert all("group_first_pass_sha256_mismatch" in row["issues"] for row in rows.values())


def test_original_mode_has_no_grouped_rows(tmp_path, monkeypatch, audit):
    module = audit[0]
    monkeypatch.setattr(module, "ROOT", tmp_path)
    assert module.grouped_reviews({}) == ({}, {})


def test_grouping_preserves_definition_and_pre_run_threshold_verbatim():
    original = (AUDIT / "prompt.md").read_text()
    grouped = (AUDIT / "grouped_2026-09-11/prompt.md").read_text()
    section = lambda value: value.split("## Frozen mathematical definition\n", 1)[1].split("## Review procedure\n", 1)[0]
    assert section(original) == section(grouped)


def correction_fixture(audit):
    module, root, group, parent, manifest = audit
    path = complete(audit)
    payload = json.loads(path.read_text())
    payload["configuration_reports"][0]["files_read_completely"] = ["typo.py"]
    write_json(path, payload)
    receipt_path = group / "provenance/007_example_env.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["first_pass_sha256"] = digest(path)
    write_json(receipt_path, receipt)
    rows, _ = module.grouped_reviews(parent)
    decision = {
        "case_index": 1, "first_pass_path": str(path.relative_to(root)),
        "first_pass_sha256": digest(path), "original_issues": rows[1]["issues"],
        "reason": "Read the correct source; preserve the original typo.",
        "patches": [{"field": ["files_read_completely", 0], "before": "typo.py", "after": "implementation.py"}],
    }
    decisions = {"source_revision": "revision", "manifest_sha256": digest(root / "manifest.json"), "cases": [decision]}
    write_json(root / "adjudications.json", decisions)
    return rows, decisions, path


def test_explicit_adjudication_preserves_first_pass_and_raw_flags(audit):
    module, root, group, parent, manifest = audit
    rows, _, path = correction_fixture(audit)
    original = path.read_bytes()
    module.apply_adjudications(list(rows.values()), parent, Path(parent["source_root"]))
    row = rows[1]
    assert row["issues"] == []
    assert row["first_pass_issues"] == ["missing_source_path:typo.py"]
    assert row["first_pass_label"] == row["label"] == "no"
    assert row["adjudicated_report"]["files_read_completely"] == ["implementation.py"]
    assert path.read_bytes() == original
    assert all("adjudicated_report" not in rows[index] for index in range(2, 11))


@pytest.mark.parametrize("change", ["hash", "issues", "old_value", "still_invalid", "identity", "duplicate", "process_error", "source_revision", "manifest_hash"])
def test_adjudication_rejects_stale_or_invalid_corrections(audit, change):
    module, root, group, parent, manifest = audit
    rows, decisions, _ = correction_fixture(audit)
    decision = decisions["cases"][0]
    if change == "hash":
        decision["first_pass_sha256"] = "changed"
    elif change == "issues":
        decision["original_issues"] = []
    elif change == "old_value":
        decision["patches"][0]["before"] = "different.py"
    elif change == "still_invalid":
        decision["patches"][0]["after"] = "another_typo.py"
    elif change == "identity":
        decision["patches"][0] = {"field": ["case_index"], "before": 1, "after": 2}
    elif change == "duplicate":
        decisions["cases"].append(decision)
    elif change == "process_error":
        rows[1]["issues"].append("group_first_pass_sha256_mismatch")
        decision["original_issues"] = list(rows[1]["issues"])
    elif change == "source_revision":
        decisions["source_revision"] = "different"
    else:
        decisions["manifest_sha256"] = "different"
    write_json(root / "adjudications.json", decisions)
    with pytest.raises(AssertionError):
        module.apply_adjudications(list(rows.values()), parent, Path(parent["source_root"]))


def test_no_label_cannot_use_a_false_pre_run_override(audit):
    module, root, group, parent, manifest = audit
    path = complete(audit)
    report = json.loads(path.read_text())["configuration_reports"][0]
    for key in ("i", "ii", "iii"):
        report[f"clause_{key}"]["holds"] = True
    report["pre_run"]["at_least_half"] = False
    case = parent["cases"][0]
    assert "no_without_failed_clause_or_pre_run_override" in module.check_report(case, report, Path(parent["source_root"]))
    report.update(label="yes", delta_ms=300, window_ms=800, common_visible_process="Moving intercept vector")
    assert module.check_report(case, report, Path(parent["source_root"])) == []


def test_published_corrections_cover_exactly_fourteen_original_flags():
    result = json.loads((AUDIT / "results.json").read_text())
    decisions = json.loads((AUDIT / "adjudications.json").read_text())
    flagged = {row["case_index"] for row in result["cases"] if row["first_pass_issues"]}
    assert flagged == {12, 27, 38, 71, *range(271, 281)}
    assert {row["case_index"] for row in decisions["cases"]} == flagged
    assert result["counts"]["first_pass_labels"] == {"yes": 111, "no": 379}
    assert result["counts"]["current_labels"] == {"yes": 112, "no": 378}
    assert result["counts"]["selected_100_labels"] == {"yes": 295, "no": 705}
    assert result["counts"]["reports_with_issues"] == 0
    changed = [row["case_index"] for row in result["cases"] if row["label"] != row["first_pass_label"]]
    assert changed == [12]
    for decision in decisions["cases"]:
        assert digest(AUDIT / decision["first_pass_path"]) == decision["first_pass_sha256"]


def test_anthill_l1_defense_cannot_be_precommitted_and_lane_expires():
    """Replay wiring evidence, not a screenshot-policy or gameplay evaluation."""
    from copy import deepcopy
    from weird_captcha_gym.shared_scripts.incubator_generators import anthill_front as generator
    from weird_captcha_gym.shared_runtime.server.incubator_graders import anthill_front as grader

    controls = json.loads((AUDIT.parents[1] / "environments/anthill_front_env/controls.json").read_text())
    task = {"_control_condition": {"difficulty": 1, "interaction": "simplified", "difficulty_parameters": controls["difficulty"]["1"]["parameters"]}}
    _, truth = generator.generate(task, "flag-adjudication-2026-09-11")
    world = truth["world"]
    raid = world["raids"][0]
    state = grader.initial_state(world)
    grader.apply_action(state, world, "GATHER", state["workers"], "seed")
    grader.advance(state, world, 36)
    for _ in range(5):
        grader.apply_action(state, world, "RAISE", [], "brood")
    grader.advance(state, world, 60)
    assert len(state["soldiers"]) == 5
    assert raid["spawn_tick"] < raid["response_open_tick"]
    with pytest.raises(ValueError, match="no uncommitted raid"):
        grader.apply_action(state, world, "MARCH", state["soldiers"], "north")
    abandoned = deepcopy(state)
    grader.advance(abandoned, world, raid["impact_tick"])
    assert abandoned["terminal"] and not abandoned["won"] and abandoned["queen_hp"] == 0
    crossing = next(tick for tick in range(raid["response_open_tick"], raid["response_deadline_tick"] - 3)
                    if grader.intercept_lane(raid, tick) != grader.intercept_lane(raid, tick + 1))
    old_lane = grader.intercept_lane(raid, crossing)
    grader.advance(state, world, crossing + 1)
    wrong, correct = deepcopy(state), deepcopy(state)
    grader.apply_action(wrong, world, "MARCH", wrong["soldiers"], old_lane)
    grader.apply_action(correct, world, "MARCH", correct["soldiers"], grader.intercept_lane(raid, crossing + 1))
    with pytest.raises(ValueError, match="no uncommitted raid"):
        grader.apply_action(wrong, world, "MARCH", wrong["soldiers"], grader.intercept_lane(raid, crossing + 1))
    grader.advance(wrong, world, raid["impact_tick"])
    grader.advance(correct, world, raid["impact_tick"])
    assert wrong["terminal"] and wrong["queen_hp"] == 0
    assert correct["successful_intercepts"] == [raid["wave"]]
    grader.apply_action(correct, world, "MARCH", correct["soldiers"], "enemy")
    grader.advance(correct, world, raid["impact_tick"] + world["assault_travel_ticks"])
    assert correct["terminal"] and correct["won"]
