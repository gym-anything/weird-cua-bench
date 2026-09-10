"""Reject real opposite-mode transcripts after rebinding envelope identity only.

This privileged grader diagnostic is not an executable UI attack or a model run.
Event types, input-source markers, geometry, values and timestamps are untouched.
"""

import copy
import importlib.util
import json
from pathlib import Path
import sys


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def main():
    output = ROOT / "surface_binding_checks.json"
    assert not output.exists(), "Preserve original diagnostics"
    manifest = read(ROOT / "manifest.json")
    source = Path(manifest["source_root"])
    rows = []
    for case in manifest["cases"]:
        mechanic = case["environment_id"].removesuffix("_env")
        path = source / "weird_captcha_gym/shared_runtime/server/incubator_graders" / f"{mechanic}.py"
        spec = importlib.util.spec_from_file_location(f"binding_{mechanic}", path)
        grader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(grader)
        for level in range(1, 6):
            for mode in ("simplified", "full"):
                stem = f"{case['case_index']:03d}_{mechanic}_d{level}_{mode}_seed1_solve"
                exported_path = ROOT / "outputs/browser" / stem / "exported.json"
                row = {"case_index": case["case_index"], "public_name": case["public_name"],
                       "difficulty": level, "source_mode": mode}
                if not exported_path.exists():
                    candidates = sorted((ROOT / "outputs/browser").glob(stem + "_*diagnostic/exported.json"))
                    for candidate in candidates:
                        evidence_path = ROOT / "browser_checks" / (candidate.parent.name + ".json")
                        evidence = read(evidence_path) if evidence_path.exists() else {}
                        if evidence.get("status") == "wiring_pass":
                            exported_path = candidate
                            row["separate_diagnostic_export"] = True
                            row["diagnostic_scope"] = evidence.get("solver_adjustment")
                            break
                if not exported_path.exists():
                    row["status"] = "missing_successful_export"
                    evidence_path = ROOT / "browser_checks" / (stem + ".json")
                    if evidence_path.exists():
                        evidence = read(evidence_path)
                        row["original_check_status"] = evidence.get("status")
                        row["original_error"] = evidence.get("error")
                    rows.append(row)
                    continue
                exported = read(exported_path)
                other_mode = "full" if mode == "simplified" else "simplified"
                generated = ROOT / "outputs/generation" / mechanic / f"d{level}_{other_mode}_seed1"
                truth, public = read(generated / "ground_truth.json"), read(generated / "public_state.json")
                payload = copy.deepcopy(exported["result"])
                changed = []
                for key in ("challenge_id", "task_id", "control_condition"):
                    if key in payload:
                        payload[key] = copy.deepcopy(truth.get(key, public.get(key)))
                        changed.append(key)
                for key in ("interaction", "interaction_mode"):
                    if key in payload:
                        payload[key] = other_mode
                        changed.append(key)
                assert payload.get("events") == exported["result"].get("events")
                row.update({"target_mode": other_mode, "envelope_fields_rebound": changed,
                            "events_unchanged": True, "export_path": str(exported_path.relative_to(ROOT)),
                            "own_mode_grade": grader.grade(exported["result"], exported["ground_truth"], exported["public_state"]),
                            "opposite_mode_grade": grader.grade(payload, truth, public)})
                if row["own_mode_grade"].get("passed") is not True:
                    row["status"] = "invalid_own_mode_export"
                else:
                    row["status"] = "rejected" if row["opposite_mode_grade"].get("passed") is False else "accepted_or_ungraded"
                rows.append(row)
    output.write_text(json.dumps({"scope": __doc__, "checks": rows}, indent=2) + "\n")
    from collections import Counter
    print(dict(Counter(row["status"] for row in rows)))


if __name__ == "__main__":
    main()
