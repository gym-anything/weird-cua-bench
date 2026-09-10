from __future__ import annotations

import importlib.util
from pathlib import Path


MECHANIC_ID = "last_seats_in_the_lagoon"
BENCHMARK_ROOT = Path(__file__).resolve().parents[4]
HELPER_PATH = BENCHMARK_ROOT / "shared_runtime" / "verifier_helpers.py"
GRADER_PATH = BENCHMARK_ROOT / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC_ID}.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_task(traj=None, env_info=None, task_info=None):
    del traj
    try:
        helpers = _load("last_seats_verifier_helpers", HELPER_PATH)
        grader = _load("last_seats_in_the_lagoon_independent_grader", GRADER_PATH)
        exported, error = helpers.load_exported_result(env_info or {})
    except Exception as exc:
        return {"passed": False, "score": 0, "feedback": f"cannot load verifier dependency: {exc}"}
    if error:
        return {"passed": False, "score": 0, "feedback": error}
    exported = exported or {}
    task_id = (task_info or {}).get("id") if isinstance(task_info, dict) else None
    current_task = exported.get("current_task") or {}
    if not isinstance(current_task, dict):
        return {"passed": False, "score": 0, "feedback": "malformed current task"}
    # The shared exporter does not include task_id in current_task. Bind the
    # requested task to the identities actually carried in the export.
    if task_id and any(
        not isinstance(exported.get(key), dict)
        or exported[key].get("task_id") != task_id
        for key in ("result", "ground_truth", "public_state")
    ):
        return {"passed": False, "score": 0, "feedback": "export belongs to a different task"}
    decision = grader.grade(
        exported.get("result") or {},
        exported.get("ground_truth") or {},
        exported.get("public_state") or {},
    )
    passed = decision.get("passed") is True
    return {
        "passed": passed,
        "score": 100 if passed else 0,
        "feedback": f"independent lifeboat replay: {decision.get('feedback') or 'grade failed'}",
    }

