"""Index fresh classifications without changing first-pass or historical records."""

import argparse
from collections import Counter
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def process_exists(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def check_report(case, report, source):
    issues = []
    for field, expected in {
        "case_index": case["case_index"],
        "environment_id": case["environment_id"],
        "public_environment_name": case["public_name"],
        "difficulty": case["difficulty"],
        "interaction_mode": case["interaction_mode"],
    }.items():
        if report.get(field) != expected:
            issues.append(f"identity:{field}")
    label = report.get("label")
    if label not in ("yes", "no", "unresolved"):
        issues.append("invalid_label")
    clauses = [report.get(f"clause_{key}", {}) for key in ("i", "ii", "iii")]
    for key, clause in zip(("i", "ii", "iii"), clauses):
        if not isinstance(clause, dict) or not clause.get("reason"):
            issues.append(f"missing_clause_reason:{key}")
    pre_run = report.get("pre_run", {})
    if not isinstance(pre_run, dict):
        pre_run = {}
    if pre_run.get("threshold") != 0.5 or not pre_run.get("reason"):
        issues.append("missing_pre_run_assessment")
    if pre_run.get("at_least_half") is True and label != "no":
        issues.append("pre_run_label_conflict")
    if label == "yes":
        if not all(isinstance(clause, dict) and clause.get("holds") is True for clause in clauses):
            issues.append("yes_without_three_clauses")
        if pre_run.get("at_least_half") is not False:
            issues.append("yes_without_pre_run_exclusion")
        if not isinstance(report.get("delta_ms"), (int, float)) or report["delta_ms"] <= 0:
            issues.append("missing_positive_delay_witness")
        if not isinstance(report.get("window_ms"), (int, float)) or report["window_ms"] < 0:
            issues.append("missing_window_witness")
        if not report.get("common_visible_process"):
            issues.append("missing_common_visible_process")
    if label == "no" and pre_run.get("at_least_half") is not True and not any(
        isinstance(clause, dict) and clause.get("holds") is False for clause in clauses
    ):
        issues.append("no_without_failed_clause_or_pre_run_override")
    paths = report.get("files_read_completely", [])
    if not isinstance(paths, list) or not paths:
        issues.append("missing_complete_reads")
        paths = []
    evidence = report.get("source_evidence", [])
    if not isinstance(evidence, list) or not evidence:
        issues.append("missing_source_evidence")
        evidence = []
    for relative in paths + [item.get("path") for item in evidence if isinstance(item, dict)]:
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            issues.append(f"invalid_source_path:{relative}")
        elif not (source / relative).is_file():
            issues.append(f"missing_source_path:{relative}")
    for item in evidence:
        if not isinstance(item, dict) or not item.get("claim"):
            issues.append("missing_evidence_claim")
            continue
        relative = item.get("path", "")
        if (
            not isinstance(relative, str)
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or not (source / relative).is_file()
        ):
            continue
        line_count = len((source / relative).read_text().splitlines())
        ranges = re.split(r"[,;]", str(item.get("lines", "")))
        for fragment in ranges:
            match = re.fullmatch(r"\s*(\d+)(?:\s*[-–]\s*(\d+))?\s*", fragment)
            if not match or not 1 <= int(match[1]) <= int(match[2] or match[1]) <= line_count:
                issues.append(f"invalid_line_range:{relative}:{fragment}")
    return sorted(set(issues))


def grouped_reviews(parent_manifest, source=None):
    """Index game-level reports without copying or replacing earlier first passes."""
    root = ROOT / "grouped_2026-09-11"
    if not (root / "manifest.json").exists():
        return {}, {}
    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["parent_manifest_sha256"] == sha256(ROOT / "manifest.json")
    assert manifest["parent_prompt_sha256"] == sha256(ROOT / "prompt.md")
    assert manifest["prompt_sha256"] == sha256(root / "prompt.md"), "Grouped prompt changed"
    assert manifest["source_revision"] == parent_manifest["source_revision"]
    assert manifest["source_root"] == parent_manifest["source_root"]
    preserved = manifest["preserved_parent_files"]
    hashes = {
        str(path.relative_to(ROOT)): sha256(path)
        for folder in preserved["folders"]
        for path in sorted((ROOT / folder).glob(preserved["glob"]))
    }
    assert len(hashes) == preserved["count"]
    assert hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest() == preserved["sha256"], "Preserved first-phase artifacts changed"
    source = Path(source or manifest["source_root"])
    parent_cases = {case["case_index"]: case for case in parent_manifest["cases"]}
    rows, statuses = {}, Counter()
    for game in manifest["cases"]:
        cases = {}
        all_indices = game["all_configuration_indices"]
        assert len(all_indices) == len(set(all_indices)) == 10
        assert all(parent_cases[index]["environment_id"] == game["environment_id"] for index in all_indices)
        for config in game["configurations"]:
            index = config["case_index"]
            assert index in all_indices and index not in rows and index not in cases
            case = parent_cases[index]
            assert case["environment_id"] == game["environment_id"] and case["public_name"] == game["public_name"]
            assert all(case[key] == config[key] for key in ("difficulty", "interaction_mode"))
            cases[index] = case
        assert set(cases).isdisjoint(game["preserved_configuration_indices"])
        assert set(cases) | set(game["preserved_configuration_indices"]) == set(all_indices)
        stem = f"{game['case_index']:03d}_{game['environment_id']}"
        path = root / "first_pass" / f"{stem}.json"
        attempts = sorted((root / "provenance").glob(f"{stem}*.json"))
        receipts = [json.loads(p.read_text()) for p in attempts]
        completed = [receipt for receipt in receipts if receipt["status"] == "completed"]
        status, reports, issues = "pending", {}, []
        if receipts:
            running = [receipt for receipt in receipts if receipt["status"] == "running"]
            status = "running" if any(process_exists(r.get("pid")) for r in running) else "process_interrupted" if running else "process_failed"
        if completed and path.exists():
            try:
                payload = json.loads(path.read_text())
                for field, expected in (("case_index", game["case_index"]), ("environment_id", game["environment_id"]), ("public_environment_name", game["public_name"])):
                    if payload.get(field) != expected:
                        raise ValueError(f"game_identity:{field}")
                members = payload["configuration_reports"]
                if not isinstance(members, list) or any(not isinstance(member, dict) for member in members):
                    raise ValueError("configuration_reports must be an array of objects")
                reports = {member["case_index"]: member for member in members}
                if len(reports) != len(members) or set(reports) != set(cases):
                    raise ValueError("configuration coverage must exactly match the game assignment")
                status = "reviewed"
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                status = "invalid_report"
                issues.append(f"invalid_group_report:{type(exc).__name__}:{exc}")
            receipt = completed[-1]
            for key, expected in (("first_pass_sha256", sha256(path)), ("prompt_sha256", manifest["prompt_sha256"]), ("manifest_sha256", sha256(root / "manifest.json")), ("source_revision", manifest["source_revision"])):
                if receipt.get(key) != expected:
                    issues.append(f"group_{key}_mismatch")
        statuses[status] += 1
        for index, case in cases.items():
            row = dict(case, status=status, label=None, issues=list(issues), review_unit="game", game_case_index=game["case_index"])
            row["attempts"] = [{"path": str(p.relative_to(ROOT)), "status": receipt["status"], "review_unit": "game"} for p, receipt in zip(attempts, receipts)]
            if completed and path.exists():
                row.update(first_pass_path=str(path.relative_to(ROOT)), first_pass_sha256=sha256(path), report_member_case_index=index)
            if status == "reviewed":
                try:
                    row["issues"].extend(check_report(case, reports[index], source))
                    row["label"] = reports[index].get("label")
                except (ValueError, TypeError, AttributeError) as exc:
                    row["status"] = "invalid_report"
                    row["issues"].append(f"invalid_report:{type(exc).__name__}:{exc}")
            rows[index] = row
    assert len(rows) == manifest["population"]["new_configuration_judgments"]
    return rows, {"population": len(manifest["cases"]), "status": dict(statuses)}


def apply_adjudications(rows, manifest, source):
    """Apply explicit, hash-bound corrections without modifying review artifacts."""
    for row in rows:
        row["first_pass_label"] = row["label"]
        row["first_pass_issues"] = list(row["issues"])
    path = ROOT / "adjudications.json"
    if not path.exists():
        return
    decisions = json.loads(path.read_text())
    assert decisions["source_revision"] == manifest["source_revision"]
    assert decisions["manifest_sha256"] == sha256(ROOT / "manifest.json")
    by_index = {row["case_index"]: row for row in rows}
    seen = set()
    for decision in decisions["cases"]:
        index = decision["case_index"]
        assert index not in seen, "Duplicate adjudication"
        seen.add(index)
        row = by_index[index]
        assert row["status"] == "reviewed", "Cannot adjudicate an incomplete review"
        assert decision["first_pass_sha256"] == row["first_pass_sha256"], "Adjudication first-pass hash mismatch"
        assert decision["first_pass_path"] == row["first_pass_path"]
        assert decision["original_issues"] == row["issues"], "Adjudication issues changed"
        assert decision.get("reason") and decision.get("patches")
        report = json.loads((ROOT / row["first_pass_path"]).read_text())
        if "report_member_case_index" in row:
            report = next(member for member in report["configuration_reports"] if member["case_index"] == index)
        # Never let an adjudication erase a process/provenance validation error.
        assert check_report(row, report, source) == row["issues"], "Non-report issues cannot be adjudicated"
        report = copy.deepcopy(report)
        for patch in decision["patches"]:
            fields = patch["field"]
            assert fields and fields[0] in {
                "label", "clause_i", "clause_ii", "clause_iii", "pre_run",
                "files_read_completely", "source_evidence", "uncertainties",
            }, "Unsupported adjudication field"
            target = report
            for field in fields[:-1]:
                target = target[field]
            assert target[fields[-1]] == patch["before"], "Adjudication old value mismatch"
            target[fields[-1]] = copy.deepcopy(patch["after"])
        issues = check_report(row, report, source)
        assert not issues, f"Adjudication {index} still has issues: {issues}"
        row.update(label=report["label"], issues=issues, adjudicated_report=report,
                   adjudication_path="adjudications.json", adjudication_sha256=sha256(path))


def build(source=None):
    manifest = json.loads((ROOT / "manifest.json").read_text())
    assert sha256(ROOT / "prompt.md") == manifest["prompt_sha256"], "Frozen prompt changed"
    source = Path(source or manifest["source_root"])
    skipped = json.loads((ROOT / "skipped_existing.json").read_text())["cases"]
    rows = []
    for case in manifest["cases"]:
        stem = f"{case['case_index']:03d}_{case['environment_id']}"
        path = ROOT / "first_pass" / f"{stem}.json"
        attempts = sorted((ROOT / "provenance").glob(f"{stem}*.json"))
        receipts = [json.loads(p.read_text()) for p in attempts]
        completed = [receipt for receipt in receipts if receipt["status"] == "completed"]
        row = dict(case, status="pending", label=None, issues=[])
        if receipts:
            running = [r for r in receipts if r["status"] == "running"]
            if any(process_exists(r.get("pid")) for r in running):
                row["status"] = "running"
            elif running:
                row["status"] = "process_interrupted"
                row["process_note"] = "Process no longer exists; original running receipt preserved without fabricating a terminal result."
            else:
                row["status"] = "process_failed"
            row["attempts"] = [{"path": str(p.relative_to(ROOT)), "status": r["status"]} for p, r in zip(attempts, receipts)]
        if completed and path.exists():
            row["first_pass_path"] = str(path.relative_to(ROOT))
            row["first_pass_sha256"] = sha256(path)
            try:
                report = json.loads(path.read_text())
                row["issues"] = check_report(case, report, source)
                row["label"] = report.get("label")
                row["status"] = "reviewed"
            except (ValueError, TypeError, AttributeError) as exc:
                row["issues"].append(f"invalid_report:{type(exc).__name__}:{exc}")
                row["status"] = "invalid_report"
            receipt = completed[-1]
            if receipt.get("first_pass_sha256") != row["first_pass_sha256"]:
                row["issues"].append("first_pass_hash_mismatch")
            if receipt.get("prompt_sha256") != manifest["prompt_sha256"]:
                row["issues"].append("prompt_hash_mismatch")
            if receipt.get("source_revision") != manifest["source_revision"]:
                row["issues"].append("source_revision_mismatch")
        rows.append(row)
    grouped, group_counts = grouped_reviews(manifest, source)
    for index, row in enumerate(rows):
        if row["case_index"] not in grouped:
            continue
        assert row["status"] != "reviewed", "Never replace a completed first-phase report"
        replacement = grouped[row["case_index"]]
        replacement["attempts"] = row.get("attempts", []) + replacement["attempts"]
        rows[index] = replacement
    status_counts = dict(Counter(row["status"] for row in rows))
    labels = dict(Counter(row["label"] for row in rows if row["status"] == "reviewed"))
    original_issue_count = sum(bool(row["issues"]) for row in rows)
    apply_adjudications(rows, manifest, source)
    combined = [dict(row, label=row["historical_label"], status="skipped_historical") for row in skipped] + rows
    key = lambda row: (row["environment_id"], row["difficulty"], row["interaction_mode"])
    assert len({key(row) for row in combined}) == len(combined) == 1000
    result = {
        "schema_version": 2,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Source-review first passes, explicit flag adjudications, and untouched historical labels. Initial reviews used one context per configuration; grouped continuation uses one context per game. Raw labels/issues remain separate from current labels/issues. Structural checks do not establish semantic correctness or gameplay performance.",
        "source_revision": manifest["source_revision"],
        "manifest_sha256": sha256(ROOT / "manifest.json"),
        "counts": {"pending_population": len(rows), "skipped_existing": len(skipped), "status": status_counts, "first_pass_labels": labels, "first_pass_reports_with_issues": original_issue_count, "current_labels": dict(Counter(row["label"] for row in rows if row["status"] == "reviewed")), "reports_with_issues": sum(bool(row["issues"]) for row in rows), "adjudicated_reports": sum("adjudicated_report" in row for row in rows), "selected_100_labels": dict(Counter(row["label"] for row in combined))},
        "cases": rows,
        "selected_100_combined": sorted(combined, key=key),
    }
    if group_counts:
        result["counts"]["grouped_game_reviews"] = group_counts
    return result


def verify_source_revision(source):
    """Check cited source bytes against the frozen Git revision on another machine."""
    manifest = json.loads((ROOT / "manifest.json").read_text())
    repository = Path(__file__).resolve().parents[3]
    tree = subprocess.run(["git", "ls-tree", "-r", manifest["source_revision"]],
                          cwd=repository, text=True, capture_output=True, check=True)
    blobs = {line.split("\t", 1)[1]: line.split()[2] for line in tree.stdout.splitlines()}
    references = set()
    for folder in (ROOT / "first_pass", ROOT / "grouped_2026-09-11/first_pass"):
        for path in folder.glob("*.json"):
            payload = json.loads(path.read_text())
            for report in payload.get("configuration_reports", [payload]):
                references.update(report["files_read_completely"])
                references.update(item["path"] for item in report["source_evidence"])
    if (ROOT / "adjudications.json").exists():
        for decision in json.loads((ROOT / "adjudications.json").read_text())["cases"]:
            references.update(decision["source_files_checked"])
    for relative in sorted(references):
        # Invalid original citations remain visible to check_report/adjudication.
        if relative not in blobs:
            continue
        path = source / relative
        content = path.read_bytes()
        actual = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
        assert actual == blobs[relative], f"Frozen source differs: {relative}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, help="Source directory at the frozen revision; cited files are checked against Git blobs")
    args = parser.parse_args()
    if args.source_root is not None:
        verify_source_revision(args.source_root)
    result = build(args.source_root)
    (ROOT / "results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    counts = result["counts"]
    lines = [
        "# Real-time classification: selected 100, pending 490", "",
        f"Updated: {result['updated_at']}", "",
        "510 existing classifications are skipped and preserved. This run covers only the 490 previously unclassified configurations across 49 environments.", "",
        f"- Review status: {counts['status']}",
        f"- First-pass labels: {counts['first_pass_labels']}",
        f"- Original reports with structural/reference issues: {counts['first_pass_reports_with_issues']}",
        f"- Explicitly adjudicated reports: {counts['adjudicated_reports']}",
        f"- Current labels: {counts['current_labels']}",
        f"- Current reports with structural/reference issues: {counts['reports_with_issues']}",
        f"- Combined selected-100 labels: {counts['selected_100_labels']}", "",
        "First-pass counts are not rewritten by structural checks or subsequent adjudication. Any issues below remain visible. Skipped historical labels are not claimed to be revalidated against the current source.", "",
        "Explicit corrections are recorded in `adjudications.json`; current corrected reports are embedded in `results.json`. The original completion record and all first passes remain unchanged.", "",
        "| # | Environment | Difficulty | Interaction | Status | First-pass label | Current label | Original issues | Current issues |",
        "|---:|---|---:|---|---|---|---|---|---|",
    ]
    for row in result["cases"]:
        issues = "; ".join(row["issues"]).replace("|", "\\|")
        original_issues = "; ".join(row["first_pass_issues"]).replace("|", "\\|")
        lines.append(f"| {row['case_index']} | {row['public_name']} | L{row['difficulty']} | {row['interaction_mode']} | {row['status']} | {row['first_pass_label'] or '—'} | {row['label'] or '—'} | {original_issues} | {issues} |")
    (ROOT / "report.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(counts, sort_keys=True))


if __name__ == "__main__":
    main()
