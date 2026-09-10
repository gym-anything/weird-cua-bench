from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
HELPER = ROOT / "shared_runtime" / "verifier_helpers.py"
GRADER = ROOT / "shared_runtime" / "server" / "incubator_graders" / "branch_repair.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_task(traj=None, env_info=None, task_info=None):
    del traj, task_info
    try:
        helpers = _load("branch_repair_verifier_helpers", HELPER)
        grader = _load("branch_repair_verifier_grader", GRADER)
    except Exception as exc:
        return {"passed": False, "score": 0, "feedback": str(exc)}
    exported, error = helpers.load_exported_result(env_info or {})
    if error:
        return {"passed": False, "score": 0, "feedback": error}
    result = (exported or {}).get("result") or {}
    if not result:
        return {"passed": False, "score": 0, "feedback": "No submitted UI result found."}
    grade = grader.grade(result, (exported or {}).get("ground_truth") or {}, (exported or {}).get("public_state") or {})
    passed = grade.get("passed") is True
    return {"passed": passed, "score": 100 if passed else 0, "feedback": str(grade.get("feedback") or "branch repair grade unavailable")}
