from __future__ import annotations

import importlib.util
from pathlib import Path


BENCHMARK_ROOT = Path(__file__).resolve().parents[4]
HELPER_PATH = BENCHMARK_ROOT / "shared_runtime" / "verifier_helpers.py"
GRADER_PATH = BENCHMARK_ROOT / "shared_runtime" / "server" / "incubator_graders" / "little_planet_mason.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_task(traj=None, env_info=None, task_info=None):
    try:
        helpers = _load_module(HELPER_PATH, "little_planet_mason_verifier_helpers")
        grader = _load_module(GRADER_PATH, "little_planet_mason_independent_grader")
    except Exception as exc:
        return {"passed": False, "score": 0, "feedback": f"cannot load Little Planet Mason grader: {exc}"}
    try:
        exported, error = helpers.load_exported_result(env_info or {})
    except Exception as exc:
        return {"passed": False, "score": 0, "feedback": f"cannot load exported result: {exc}"}
    if error:
        return {"passed": False, "score": 0, "feedback": error}
    replay = grader.grade(
        (exported or {}).get("result") or {},
        (exported or {}).get("ground_truth") or {},
        (exported or {}).get("public_state") or {},
    )
    passed = replay.get("passed") is True
    return {
        "passed": passed,
        "score": 100 if passed else 0,
        "feedback": f"independent Little Planet Mason replay: {replay.get('feedback') or 'no feedback'}",
    }
