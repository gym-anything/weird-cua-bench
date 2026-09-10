"""Execute one sequential slot of fresh reviewers; monitoring stays in chat.

Run at most three slots concurrently. This is a work queue, not a detached
monitor: every child is awaited, and each review uses run_reviewer.py's own
fresh process, immutable attempt receipt, and finite outer deadline.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_indices", type=int, nargs="+")
    args = parser.parse_args()
    indices = args.case_indices
    assert len(indices) == len(set(indices)), "A slot cannot repeat a case"
    manifest = json.loads((ROOT / "manifest.json").read_text())
    cases = {row["case_index"]: row for row in manifest["cases"]}
    for index in indices:
        case = cases[index]
        stem = f"{index:03d}_{case['environment_id']}"
        assert not (ROOT / "first_pass" / f"{stem}.json").exists()
        assert not (ROOT / "provenance" / f"{stem}.json").exists()

    queue_path = ROOT / "provenance" / f"queue_{indices[0]:03d}.json"
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "case_indices": indices,
        "started_at": now(),
        "status": "running",
        "current_case_index": None,
        "results": [],
        "execution": "Sequential fresh CLI reviews, one active child per slot; no automatic retries",
    }
    with queue_path.open("x") as handle:
        json.dump(state, handle, indent=2)
        handle.write("\n")

    def save():
        queue_path.write_text(json.dumps(state, indent=2) + "\n")

    for index in indices:
        state["current_case_index"] = index
        save()
        print(f"QUEUE starting case {index}", flush=True)
        result = subprocess.run(
            [sys.executable, str(ROOT / "run_reviewer.py"), str(index)],
            check=False,
        )
        state["results"].append(
            {"case_index": index, "exit_code": result.returncode, "finished_at": now()}
        )
        save()
        print(f"QUEUE finished case {index}, exit {result.returncode}", flush=True)

    state["current_case_index"] = None
    state["finished_at"] = now()
    failed = any(row["exit_code"] != 0 for row in state["results"])
    state["status"] = "completed_with_failures" if failed else "completed"
    save()
    print(json.dumps(state), flush=True)
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
