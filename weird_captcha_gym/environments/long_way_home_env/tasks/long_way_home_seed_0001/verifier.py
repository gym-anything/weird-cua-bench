from __future__ import annotations

import importlib.util
from pathlib import Path


BENCHMARK_ROOT = Path(__file__).resolve().parents[4]
HELPER_PATH = BENCHMARK_ROOT / "shared_runtime" / "verifier_helpers.py"
GRADER_PATH = BENCHMARK_ROOT / "shared_runtime" / "server" / "incubator_graders" / "long_way_home.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_task(traj=None, env_info=None, task_info=None):
    try:
        helpers = _load_module("weird_captcha_verifier_helpers", HELPER_PATH)
        grader = _load_module("long_way_home_independent_grader", GRADER_PATH)
    except Exception as exc:
        return {"passed": False, "score": 0, "feedback": f"cannot load verifier dependency: {exc}"}
    exported, error = helpers.load_exported_result(env_info or {})
    if error:
        return {"passed": False, "score": 0, "feedback": error}
    exported = exported or {}
    result = exported.get("result") or {}
    ground_truth = exported.get("ground_truth") or {}
    public_state = exported.get("public_state") or {}
    expected_id = task_info.get("id") if isinstance(task_info, dict) else None
    if expected_id and any(state.get("task_id") != expected_id for state in (result, ground_truth, public_state) if isinstance(state, dict)):
        return {"passed": False, "score": 0, "feedback": "export belongs to a different requested task"}
    try:
        replay = grader.grade(result, ground_truth, public_state)
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
        return {"passed": False, "score": 0, "feedback": f"malformed garden export: {exc}"}
    passed = replay.get("passed") is True
    return {
        "passed": passed,
        "score": 100 if passed else 0,
        "feedback": f"independent garden geometry replay: {replay.get('feedback') or 'no feedback'}",
    }
