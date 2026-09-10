"""Validate review coverage and references without modifying original reports."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent


def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def main():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    source = Path(manifest["source_root"])
    rows = []
    for case in manifest["cases"]:
        path = ROOT / "first_pass" / ("{case_index:03d}_{environment_id}.json".format(**case))
        report = json.loads(path.read_text())
        issues = []
        for key in ("case_index", "environment_id", "public_name"):
            if report.get(key) != case[key]:
                issues.append({"kind": "identity", "field": key})
        profiles = report.get("profiles", [])
        combinations = Counter((p.get("difficulty"), p.get("interaction")) for p in profiles)
        expected = Counter((d, mode) for d in range(1, 6) for mode in ("full", "simplified"))
        if combinations != expected:
            issues.append({"kind": "profile_coverage", "count": len(profiles)})
        if len(report.get("adjacent_pairs", [])) != 4:
            issues.append({"kind": "adjacent_pair_coverage"})
        if len(report.get("interaction_equivalence", [])) != 5:
            issues.append({"kind": "interaction_pair_coverage"})
        if len(report.get("anchor_comparisons", [])) < 3:
            issues.append({"kind": "anchor_count"})
        controls = json.loads((source / "weird_captcha_gym/environments" / case["environment_id"] / "controls.json").read_text())
        for key in ("difficulty", "interaction"):
            if report["current_baseline"].get(key) != controls["baseline"][key]:
                issues.append({"kind": "current_baseline", "field": key})
        checked_ranges = 0
        alternative_range_records = 0
        for obj in objects(report):
            relative = obj.get("path")
            if not isinstance(relative, str):
                continue
            file_path = Path(relative) if Path(relative).is_absolute() else source / relative
            if not file_path.is_file():
                issues.append({"kind": "missing_path", "path": relative})
                continue
            ranges = []
            if "start_line" in obj or "end_line" in obj:
                ranges = [(obj.get("start_line"), obj.get("end_line"))]
            elif isinstance(obj.get("lines"), str):
                alternative_range_records += 1
                for fragment in obj["lines"].split(","):
                    match = re.fullmatch(r"\s*(\d+)(?:\s*[-–]\s*(\d+))?\s*", fragment)
                    if match:
                        ranges.append((int(match[1]), int(match[2] or match[1])))
                    else:
                        issues.append({"kind": "unparsed_range", "path": relative, "lines": fragment})
            if ranges:
                line_count = len(file_path.read_text().splitlines())
                for start, end in ranges:
                    checked_ranges += 1
                    if not isinstance(start, int) or not isinstance(end, int) or not 1 <= start <= end <= line_count:
                        issues.append({"kind": "range_out_of_bounds", "path": relative, "start": start, "end": end, "file_lines": line_count})
        verdict = report.get("verdict")
        normalized_verdict = verdict if isinstance(verdict, str) else (verdict.get("decision") or verdict.get("verdict"))
        rows.append({
            "case_index": case["case_index"], "environment_id": case["environment_id"], "public_name": case["public_name"],
            "first_pass_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "profiles": len(profiles), "adjacent_pairs": len(report.get("adjacent_pairs", [])),
            "interaction_pairs": len(report.get("interaction_equivalence", [])), "anchors": len(report.get("anchor_comparisons", [])),
            "verdict_normalized_for_index_only": normalized_verdict,
            "nested_verdict_format": isinstance(verdict, dict), "alternative_range_records": alternative_range_records,
            "checked_ranges": checked_ranges, "issues": issues,
        })
    result = {"schema_version": 1, "scope": "Mechanical coverage and reference checks only; not semantic validation or difficulty calibration.", "original_reports_modified": False, "rows": rows}
    (ROOT / "report_checks.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
