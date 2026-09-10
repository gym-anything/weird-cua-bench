"""Check all 49 immutable reports, including coverage and launch provenance.

This is a mechanical audit. It neither validates semantic claims nor assigns levels.
Only matching review session files are read; only model/effort metadata is exported.
"""

from collections import Counter
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent
FOLDERS = ("pilot_10_2026-09-09", "remaining_39_2026-09-10")
ANCHORS = {
    "Isometric Voxel Extraction Mine": 1,
    "Cursor-Controlled Constellation Hunt": 2,
    "Gyroscopic Tilt Board": 3,
    "Blind Dice Courier": 4,
    "Exact-Change Candy Cascade": 5,
}
REQUIRED = (
    "schema_version case_index environment_id public_name current_baseline "
    "source_coverage anchor_comparisons visible_baseline_solution baseline_judgment "
    "profiles adjacent_pairs baseline_preservation interaction_equivalence findings "
    "verdict concise_summary limitations runtime_checks_performed"
).split()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def adjacent_key(row):
    for first, second in (("from_level", "to_level"), ("from_difficulty", "to_difficulty"), ("from", "to")):
        if first in row and second in row:
            values = [row[first], row[second]]
            return tuple(v.get("difficulty") if isinstance(v, dict) else v for v in values)
    if isinstance(row.get("pair"), str):
        match = re.fullmatch(r"L?([1-5])\s*(?:->|→)\s*L?([1-5])", row["pair"])
        if match:
            return tuple(map(int, match.groups()))
    return None


def references(report, source):
    issues, checked, paths = [], 0, set()
    for obj in objects(report):
        path = obj.get("path")
        if not isinstance(path, str):
            continue
        paths.add(path)
        candidate = source / path
        if not candidate.is_file():
            issues.append({"kind": "missing_file", "path": path})
            continue
        ranges = []
        if "start_line" in obj or "end_line" in obj:
            ranges.append((obj.get("start_line"), obj.get("end_line")))
        elif isinstance(obj.get("lines"), str):
            for piece in obj["lines"].split(","):
                match = re.fullmatch(r"\s*(\d+)(?:\s*[-–]\s*(\d+))?\s*", piece)
                if match:
                    ranges.append((int(match[1]), int(match[2] or match[1])))
                else:
                    issues.append({"kind": "unparsed_range", "path": path, "range": piece})
        count = len(candidate.read_text().splitlines())
        for start, end in ranges:
            checked += 1
            if not isinstance(start, int) or not isinstance(end, int) or not 1 <= start <= end <= count:
                issues.append({"kind": "out_of_bounds", "path": path, "range": [start, end], "file_lines": count})
    for anchor in report["anchor_comparisons"]:
        for value in anchor.get("files_read", []):
            path = value if isinstance(value, str) else value.get("path")
            if isinstance(path, str):
                paths.add(path)
                if not (source / path).is_file():
                    issues.append({"kind": "missing_anchor_file", "anchor": anchor["public_name"], "path": path})
    unique = {json.dumps(issue, sort_keys=True): issue for issue in issues}
    return {"unique_paths_checked": len(paths), "ranges_checked": checked, "issues": list(unique.values())}


def provenance(folder, stem, report_path, sessions):
    receipts = []
    for path in sorted((folder / "provenance").glob(stem + "*.json")):
        receipt = json.loads(path.read_text())
        receipts.append((path, receipt))
    good = [(p, r) for p, r in receipts if r.get("status") == "completed"]
    result = {
        "attempts": [{"receipt": str(p.relative_to(ROOT)), "status": r.get("status"), "exit_code": r.get("exit_code")} for p, r in receipts],
        "completed_receipt_count": len(good),
    }
    if len(good) != 1:
        return result
    path, receipt = good[0]
    result["report_hash_matches_completed_receipt"] = sha256(report_path) == receipt.get("first_pass_sha256")
    result["prompt_hash_matches_receipt"] = sha256(folder / "prompt.md") == receipt.get("prompt_sha256")
    result["requested_model"] = receipt.get("model_requested")
    result["requested_effort"] = receipt.get("reasoning_effort_requested")
    if receipt.get("launch_accepted"):
        result["method"] = "native launcher acceptance; no independent CLI metadata"
        result["native_launch_accepted"] = True
        return result
    result["method"] = "fresh CLI; model and effort from matching turn_context metadata"
    event_path = folder / "outputs" / path.stem / "events.jsonl"
    with event_path.open() as stream:
        first_event = json.loads(next(stream))
    if first_event.get("type") != "thread.started":
        result["error"] = "First event does not identify a thread"
        return result
    thread_id = first_event["thread_id"]
    result["thread_id"] = thread_id
    matches = [p for p in sessions if p.name.endswith(thread_id + ".jsonl")]
    result["matching_session_files"] = len(matches)
    metadata = set()
    if len(matches) == 1:
        with matches[0].open() as stream:
            for line in stream:
                item = json.loads(line)
                if item.get("type") == "turn_context":
                    payload = item.get("payload", {})
                    metadata.add((payload.get("model"), payload.get("effort", payload.get("reasoning_effort"))))
    result["observed_turn_context"] = [{"model": m, "effort": e} for m, e in sorted(metadata)]
    result["all_observed_model_effort_match"] = metadata == {("gpt-5.6-luna", "max")}
    return result


def main():
    sessions = list((Path.home() / ".codex/sessions/2026/09").glob("*/rollout-*.jsonl"))
    rows = []
    for folder_name in FOLDERS:
        folder = ROOT / folder_name
        manifest = json.loads((folder / "manifest.json").read_text())
        source = Path(manifest["source_root"])
        for case in manifest["cases"]:
            stem = "{case_index:03d}_{environment_id}".format(**case)
            path = folder / "first_pass" / (stem + ".json")
            report = json.loads(path.read_text())
            controls = json.loads((source / "weird_captcha_gym/environments" / case["environment_id"] / "controls.json").read_text())
            issues = []
            for key in REQUIRED:
                if key not in report:
                    issues.append({"kind": "missing_top_level_field", "field": key, "present_in_nested_verdict": isinstance(report.get("verdict"), dict) and key in report["verdict"]})
            if report.get("schema_version") != 1:
                issues.append({"kind": "schema_version"})
            for key in ("case_index", "environment_id", "public_name"):
                if report.get(key) != case[key]:
                    issues.append({"kind": "identity", "field": key})
            if any(report["current_baseline"].get(k) != controls["baseline"][k] for k in ("difficulty", "interaction")):
                issues.append({"kind": "current_baseline"})
            if Counter((p.get("difficulty"), p.get("interaction")) for p in report["profiles"]) != Counter((d, m) for d in range(1, 6) for m in ("full", "simplified")):
                issues.append({"kind": "profile_coverage"})
            pairs = [adjacent_key(p) for p in report["adjacent_pairs"]]
            if Counter(pairs) != Counter((d, d + 1) for d in range(1, 5)):
                issues.append({"kind": "adjacent_coverage", "normalized_pairs": pairs})
            if Counter(p.get("difficulty", p.get("level")) for p in report["interaction_equivalence"]) != Counter(range(1, 6)):
                issues.append({"kind": "interaction_coverage"})
            for anchor in report["anchor_comparisons"]:
                if ANCHORS.get(anchor.get("public_name")) != anchor.get("approved_level"):
                    issues.append({"kind": "unrecognized_or_wrong_anchor", "public_name": anchor.get("public_name"), "level": anchor.get("approved_level")})
            if len({a["public_name"] for a in report["anchor_comparisons"]}) < 3:
                issues.append({"kind": "too_few_distinct_anchors"})
            raw_verdict = report.get("verdict")
            verdict = raw_verdict if isinstance(raw_verdict, str) else (raw_verdict.get("decision") or raw_verdict.get("verdict"))
            if verdict not in ("keep", "relabel", "revise_profiles", "insufficient_evidence"):
                issues.append({"kind": "unrecognized_verdict", "value": verdict})
            if not isinstance(raw_verdict, str):
                issues.append({"kind": "nested_verdict_format"})
            rows.append({
                "case_index": case["case_index"], "environment_id": case["environment_id"], "public_name": case["public_name"],
                "report": str(path.relative_to(ROOT)), "sha256": sha256(path), "raw_verdict_normalized_for_index_only": verdict,
                "schema_and_coverage_issues": issues, "references": references(report, source),
                "provenance": provenance(folder, stem, path, sessions),
            })
    rows.sort(key=lambda row: row["case_index"])
    result = {
        "schema_version": 1, "scope": "Mechanical integrity/coverage/provenance only, not semantic validation or calibrated difficulty.",
        "original_reports_modified": False, "reports": len(rows), "configurations": len(rows) * 10,
        "raw_verdict_counts": dict(Counter(r["raw_verdict_normalized_for_index_only"] for r in rows)), "rows": rows,
    }
    (ROOT / "all_49_report_checks.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
    print(json.dumps({
        "cli_metadata_match": sum(r["provenance"].get("all_observed_model_effort_match", False) for r in rows),
        "native_accepted": sum(r["provenance"].get("native_launch_accepted", False) for r in rows),
        "report_hashes_match": sum(r["provenance"].get("report_hash_matches_completed_receipt", False) for r in rows),
        "prompt_hashes_match": sum(r["provenance"].get("prompt_hash_matches_receipt", False) for r in rows),
    }))
    for row in rows:
        if row["schema_and_coverage_issues"] or row["references"]["issues"]:
            print(json.dumps({"case_index": row["case_index"], "schema": row["schema_and_coverage_issues"], "references": row["references"]["issues"]}))


if __name__ == "__main__":
    main()
