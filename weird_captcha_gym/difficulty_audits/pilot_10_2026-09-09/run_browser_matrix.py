"""Run each requested headless configuration once and preserve errors separately."""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=int, nargs="+", required=True)
    parser.add_argument("--case-timeout", type=int, default=300)
    args = parser.parse_args()
    manifest = json.loads((ROOT / "manifest.json").read_text())
    cases = [c for c in manifest["cases"] if c["case_index"] in args.cases]
    logs = ROOT / "outputs" / "browser_matrix"
    logs.mkdir(parents=True, exist_ok=True)
    for case in cases:
        controls_path = Path(manifest["source_root"]) / "weird_captcha_gym/environments" / case["environment_id"] / "controls.json"
        baseline = case.get("current_baseline") or json.loads(controls_path.read_text())["baseline"]
        configurations = [(level, mode, 1, False) for level in range(1, 6) for mode in ("simplified", "full")]
        configurations += [(baseline["difficulty"], mode, 17, True) for mode in ("simplified", "full")]
        for level, mode, seed, failure in configurations:
            mechanic = case["environment_id"].removesuffix("_env")
            suffix = "failure" if failure else "solve"
            stem = f"{case['case_index']:03d}_{mechanic}_d{level}_{mode}_seed{seed}_{suffix}"
            existing = ROOT / "browser_checks" / f"{stem}.json"
            if existing.exists():
                print(f"PRESERVED {stem} {json.loads(existing.read_text()).get('status')}", flush=True)
                continue
            cmd = [sys.executable, "-B", str(ROOT / "check_browser.py"), str(case["case_index"]),
                   "--level", str(level), "--interaction", mode, "--seed", str(seed)]
            if failure:
                cmd.append("--failure")
            started = time.monotonic()
            with (logs / f"{stem}.stdout.log").open("x") as stdout, (logs / f"{stem}.stderr.log").open("x") as stderr:
                proc = subprocess.Popen(cmd, stdout=stdout, stderr=stderr, start_new_session=True)
                try:
                    code = proc.wait(timeout=args.case_timeout)
                    status = json.loads(existing.read_text()).get("status") if existing.exists() else "no_check_record"
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait(timeout=5)
                    code, status = proc.returncode, "infrastructure_case_deadline"
                    if not existing.exists():
                        existing.parent.mkdir(exist_ok=True)
                        existing.write_text(json.dumps({"case_index": case["case_index"], "environment_id": case["environment_id"],
                            "public_name": case["public_name"], "difficulty": level, "interaction": mode,
                            "seed": seed, "check": suffix, "status": status, "deadline_seconds": args.case_timeout,
                            "note": "Outer implementation-check deadline; no puzzle difficulty or impossibility judgment inferred."}, indent=2) + "\n")
            print(f"CHECK {stem}: {status}; exit={code}; seconds={time.monotonic()-started:.1f}", flush=True)


if __name__ == "__main__":
    main()
