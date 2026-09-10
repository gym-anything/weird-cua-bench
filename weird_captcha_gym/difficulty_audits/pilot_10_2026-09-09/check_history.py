"""Identify whether a committed pre-controls generator exists for each case."""

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, text=True, capture_output=True, check=True).stdout.strip()


def main():
    output = ROOT / "historical_source_checks.json"
    assert not output.exists()
    manifest = json.loads((ROOT / "manifest.json").read_text())
    revision = manifest["source_revision"]
    rows = []
    for case in manifest["cases"]:
        mechanic = case["environment_id"].removesuffix("_env")
        controls = f"weird_captcha_gym/environments/{case['environment_id']}/controls.json"
        generator = f"weird_captcha_gym/shared_scripts/incubator_generators/{mechanic}.py"
        additions = git("log", "--diff-filter=A", "--format=%H", revision, "--", controls).splitlines()
        generator_additions = git("log", "--diff-filter=A", "--format=%H", revision, "--", generator).splitlines()
        controls_added = additions[-1] if additions else None
        parent = git("rev-parse", controls_added + "^") if controls_added else None
        exists = bool(git("ls-tree", parent, "--", generator)) if parent else False
        rows.append({"case_index": case["case_index"], "public_name": case["public_name"],
                     "controls_path": controls, "generator_path": generator,
                     "controls_first_committed": controls_added,
                     "generator_first_committed": generator_additions[-1] if generator_additions else None,
                     "pre_controls_parent": parent, "generator_exists_in_pre_controls_parent": exists,
                     "scope": "Committed Git history only; does not reconstruct uncommitted creator-stage versions.",
                     "preservation_verdict": "requires_historical_comparison" if exists else "no_separate_committed_pre_controls_generator"})
    output.write_text(json.dumps({"source_revision": revision, "checks": rows}, indent=2) + "\n")
    for row in rows:
        print(row["public_name"], row["preservation_verdict"])


if __name__ == "__main__":
    main()
