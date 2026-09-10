"""Compare all files in the original frozen-source manifest with Git and disk."""

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent


def main():
    manifest = json.loads((ROOT / "remaining_39_2026-09-10/manifest.json").read_text())
    source = Path(manifest["source_root"])
    revision = manifest["source_revision"]
    original_manifest_path = ROOT.parent / "capability_audits/round_six_2026-09-09/source_manifest.json"
    original_manifest = json.loads(original_manifest_path.read_text())
    assert original_manifest["revision"] == revision
    expected_files = {row["path"]: row["git_blob_sha"] for row in original_manifest["source_files"]}
    assert len(expected_files) == 2859, "Unexpected change to the original frozen-source selection"
    entries = subprocess.check_output(["git", "ls-tree", "-rz", "--full-tree", revision], cwd=ROOT).split(b"\0")
    rows = []
    for entry in entries:
        if not entry:
            continue
        metadata, encoded_path = entry.split(b"\t", 1)
        mode, kind, expected = metadata.decode().split()
        path = encoded_path.decode()
        if path not in expected_files:
            continue
        assert expected_files[path] == expected, f"Original source manifest disagrees with Git: {path}"
        if kind != "blob":
            rows.append({"path": path, "status": "unsupported_object_kind", "kind": kind})
            continue
        file = source / path
        if not file.is_file():
            rows.append({"path": path, "status": "missing"})
            continue
        data = file.read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        rows.append({"path": path, "expected_blob": expected, "actual_blob": actual, "matches": actual == expected})
    assert len(rows) == len(expected_files), "Not all original frozen-source files were checked"
    mismatches = [row for row in rows if row.get("matches") is not True]
    result = {"source_revision": revision, "source_root": str(source), "scope": __doc__, "tracked_files_checked": len(rows),
        "all_match": not mismatches, "mismatches": mismatches,
        "selection_manifest": str(original_manifest_path.relative_to(ROOT.parent)),
        "selection_note": "The original archive intentionally excludes old evidence/audits/evaluations and non-source assets; this check covers all 2859 files actually selected, not all files in the full Git tree.",
        "comparison_manifest_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()}
    (ROOT / "source_integrity_checks.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "mismatches"} | {"mismatch_count": len(mismatches)}))
    raise SystemExit(bool(mismatches))


if __name__ == "__main__":
    main()
