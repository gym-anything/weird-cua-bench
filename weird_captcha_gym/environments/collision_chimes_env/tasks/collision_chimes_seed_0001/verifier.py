from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


MECHANIC_ID = "collision_chimes"
BENCHMARK_ROOT = Path(__file__).resolve().parents[4]
GRADER_PATH = BENCHMARK_ROOT / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC_ID}.py"
HELPER_PATH = BENCHMARK_ROOT / "shared_runtime" / "verifier_helpers.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _verify_export(exported: dict[str, Any]) -> tuple[bool, str]:
    payload = exported.get("result") or {}
    truth = exported.get("ground_truth") or {}
    public = exported.get("public_state") or {}
    if payload.get("mechanic_id") != MECHANIC_ID or truth.get("mechanic_id") != MECHANIC_ID:
        return False, "mechanic mismatch"
    challenge_id = str(truth.get("challenge_id") or "")
    if not challenge_id or payload.get("challenge_id") != challenge_id or public.get("challenge_id") != challenge_id:
        return False, "stale challenge"
    if payload.get("task_id") != truth.get("task_id") or public.get("task_id") != truth.get("task_id"):
        return False, "task mismatch"
    try:
        grader = _load(GRADER_PATH, "collision_chimes_task_grader")
        result = grader.grade(payload, truth, public)
    except Exception as exc:
        return False, f"independent grader could not replay collision chimes: {exc}"
    passed = isinstance(result, dict) and result.get("graded") is True and result.get("passed") is True
    return passed, str((result or {}).get("feedback") or "collision-chimes replay rejected")


def verify_task(traj=None, env_info=None, task_info=None):
    del traj, task_info
    try:
        helpers = _load(HELPER_PATH, "collision_chimes_verifier_helpers")
        exported, error = helpers.load_exported_result(env_info or {})
    except Exception as exc:
        return {"passed": False, "score": 0, "feedback": f"cannot load verifier dependency: {exc}"}
    if error:
        return {"passed": False, "score": 0, "feedback": error}
    passed, feedback = _verify_export(exported or {})
    return {"passed": passed, "score": 100 if passed else 0, "feedback": feedback}

