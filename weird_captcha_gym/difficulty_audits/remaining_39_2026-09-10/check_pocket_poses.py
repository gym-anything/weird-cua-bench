"""Check generated initial/target Pocket Locksmith poses, without browser edits."""

import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent


def main():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    source = Path(manifest["source_root"])
    path = source / "weird_captcha_gym/shared_runtime/server/incubator_graders/pocket_locksmith.py"
    spec = importlib.util.spec_from_file_location("pocket_pose_grader", path)
    grader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grader)
    rows = []
    for folder in sorted((ROOT / "outputs/generation/pocket_locksmith").glob("d*_*_seed*")):
        public = json.loads((folder / "public_state.json").read_text())
        truth = json.loads((folder / "ground_truth.json").read_text())
        initial = grader._world_check(public, truth, truth["initial_torsions"])
        target = grader._world_check(public, truth, truth["target_torsions"])
        rows.append({"configuration": folder.name, "initial": initial, "target": target})
    result = {"source_revision": manifest["source_revision"], "scope": __doc__, "rows": rows}
    (ROOT / "pocket_pose_checks.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"configurations": len(rows), "initially_passing": sum(r["initial"]["passed"] for r in rows),
                      "targets_passing": sum(r["target"]["passed"] for r in rows)}))


if __name__ == "__main__":
    main()
