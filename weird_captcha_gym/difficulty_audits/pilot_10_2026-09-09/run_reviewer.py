"""Launch a fresh Luna/max source reviewer, without modifying puzzle sources."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time


ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_index", type=int)
    parser.add_argument("--attempt", type=int, default=1, choices=(1, 2, 3))
    args = parser.parse_args()
    manifest = json.loads((ROOT / "manifest.json").read_text())
    case = next(row for row in manifest["cases"] if row["case_index"] == args.case_index)
    stem = f"{case['case_index']:03d}_{case['environment_id']}"
    output = ROOT / "first_pass" / f"{stem}.json"
    attempt_stem = stem if args.attempt == 1 else f"{stem}.attempt{args.attempt}"
    private = ROOT / "outputs" / attempt_stem
    receipt_path = ROOT / "provenance" / f"{attempt_stem}.json"
    assert not output.exists() and not receipt_path.exists(), "Never overwrite a review or attempt"
    output.parent.mkdir(parents=True, exist_ok=True)
    private.mkdir(parents=True, exist_ok=False)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    source = Path(manifest["source_root"])
    wrapper = (
        f"Perform one independent difficulty audit using the frozen prompt {ROOT / 'prompt.md'}. "
        "Read that prompt fully and follow it. "
        f"Substitutions: SOURCE_ROOT={source}; CASE_INDEX={case['case_index']}; "
        f"ENVIRONMENT_ID={case['environment_id']}; PUBLIC_NAME={case['public_name']}; OUTPUT_PATH={output}. "
        "Read the complete assigned source and actual approved anchor implementations. "
        "Write only your JSON report with apply_patch. No source edits, browser, previous audits or other reviews. "
        "Do not spawn agents. The user has explicitly authorized writing these audit reports in this folder; "
        "do not stop because concurrent reviewers have produced other audit files. "
        "Parent performs runtime checks separately. This is not a benchmark evaluation."
    )
    command = [
        "/opt/homebrew/bin/codex", "exec", "--ignore-user-config",
        "--model", "gpt-5.6-luna", "-c", 'model_reasoning_effort="max"',
        "-c", 'approval_policy="never"', "-c", "agents.enabled=false",
        "-c", "features.multi_agent=false", "-c", "features.apps=false",
        "-c", 'web_search="disabled"',
        "--sandbox", "workspace-write", "--skip-git-repo-check",
        "--cd", str(private), "--add-dir", str(output.parent),
        "--json", "--color", "never", "--output-last-message", str(private / "last.md"), "-",
    ]
    receipt = {
        "case_index": case["case_index"], "environment_id": case["environment_id"],
        "public_name": case["public_name"], "model_requested": "gpt-5.6-luna",
        "reasoning_effort_requested": "max", "launch_method": "fresh Codex CLI process; no resume or fork",
        "prompt_sha256": hashlib.sha256((ROOT / "prompt.md").read_bytes()).hexdigest(),
        "source_revision": manifest["source_revision"],
        "started_at": datetime.now(timezone.utc).isoformat(), "process_attempt": args.attempt,
        "outer_case_deadline_seconds": 2700,
        "transport_policy": {
            "implementation": "Codex built-in provider transport; no custom provider or outer transport retry layer",
            "provider_request_limits": "Not asserted: installed CLI rejects overrides of built-in provider fields.",
            "outer_retries": 0,
            "scope": "Source-review process, not an empirical benchmark evaluation protocol.",
        },
        "status": "running",
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    started = time.monotonic()
    with (private / "events.jsonl").open("x") as stdout, (private / "stderr.log").open("x") as stderr:
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, text=True)
        receipt["pid"] = proc.pid
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        print(f"STARTED {stem} PID {proc.pid}", flush=True)
        try:
            proc.communicate(wrapper, timeout=2700)
            receipt["status"] = "completed" if proc.returncode == 0 and output.exists() else "failed"
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
            receipt["status"] = "outer_deadline_exceeded"
        receipt["exit_code"] = proc.returncode
    receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
    receipt["elapsed_seconds"] = round(time.monotonic() - started, 2)
    if output.exists():
        receipt["first_pass_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt), flush=True)
    raise SystemExit(0 if receipt["status"] == "completed" else 1)


if __name__ == "__main__":
    main()
