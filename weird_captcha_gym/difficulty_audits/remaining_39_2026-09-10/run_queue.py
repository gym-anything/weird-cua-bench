"""Execute one sequential slot of fresh reviewers; monitoring stays in chat.

Run only the user-approved number of concurrent slots. This is a work queue, not a detached
monitor: every child is awaited, and each review uses run_reviewer.py's own
fresh process, immutable attempt receipt, and finite outer deadline.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent


def now():
    return datetime.now(timezone.utc).isoformat()


def wait_for_case(root, case):
    """Take over a slot only after its already-running attempt has finished."""
    receipt_path = root / "provenance" / f"{case['case_index']:03d}_{case['environment_id']}.json"
    receipt = json.loads(receipt_path.read_text())
    started = datetime.fromisoformat(receipt["started_at"])
    allowance = receipt["outer_case_deadline_seconds"] + 60
    while True:
        if receipt.get("finished_at") and receipt["status"] in {
            "completed", "failed", "outer_deadline_exceeded"
        }:
            return receipt
        if (datetime.now(timezone.utc) - started).total_seconds() > allowance:
            raise TimeoutError(f"Existing case {case['case_index']} has no terminal receipt")
        time.sleep(1)
        try:
            receipt = json.loads(receipt_path.read_text())
        except json.JSONDecodeError:
            # The original wrapper may be replacing its progress receipt.
            continue


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_indices", type=int, nargs="+")
    parser.add_argument("--audit-dir", type=Path, default=ROOT)
    parser.add_argument("--wait-for-case", type=int, help="Preserve an active review when repartitioning slots")
    args = parser.parse_args()
    root = args.audit_dir.resolve()
    indices = args.case_indices
    assert len(indices) == len(set(indices)), "A slot cannot repeat a case"
    manifest = json.loads((root / "manifest.json").read_text())
    cases = {row["case_index"]: row for row in manifest["cases"]}
    if args.wait_for_case is not None:
        assert args.wait_for_case in cases and args.wait_for_case not in indices
    for index in indices:
        case = cases[index]
        stem = f"{index:03d}_{case['environment_id']}"
        assert not (root / "first_pass" / f"{stem}.json").exists()
        assert not (root / "provenance" / f"{stem}.json").exists()

    queue_path = root / "provenance" / f"queue_{indices[0]:03d}.json"
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "case_indices": indices,
        "started_at": now(),
        "status": "running",
        "current_case_index": None,
        "results": [],
        "execution": "Sequential fresh CLI reviews, one active child per slot; no automatic retries",
    }
    if args.wait_for_case is not None:
        state["status"] = "waiting_for_existing_review"
        state["wait_for_case_index"] = args.wait_for_case
    with queue_path.open("x") as handle:
        json.dump(state, handle, indent=2)
        handle.write("\n")

    def save():
        queue_path.write_text(json.dumps(state, indent=2) + "\n")

    if args.wait_for_case is not None:
        print(f"QUEUE waiting for existing case {args.wait_for_case}", flush=True)
        try:
            receipt = wait_for_case(root, cases[args.wait_for_case])
        except (OSError, ValueError) as error:
            state.update(status="failed_before_start", error=str(error), finished_at=now())
            save()
            raise
        state["handoff_receipt_status"] = receipt["status"]
        state["status"] = "running"
        save()

    for index in indices:
        state["current_case_index"] = index
        save()
        print(f"QUEUE starting case {index}", flush=True)
        result = subprocess.run(
            [sys.executable, str(ROOT / "run_reviewer.py"), str(index), "--audit-dir", str(root)],
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
