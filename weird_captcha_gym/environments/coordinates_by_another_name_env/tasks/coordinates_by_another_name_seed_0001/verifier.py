from __future__ import annotations

import importlib.util
from pathlib import Path


def _benchmark_root() -> Path:
    # Controlled task directories can be materialized outside the source tree.
    # Use the installed benchmark there; mounted guest tasks use /workspace.
    candidates = list(Path(__file__).resolve().parents)
    package = importlib.util.find_spec("weird_captcha_gym")
    if package is not None and package.submodule_search_locations:
        candidates.extend(Path(root) for root in package.submodule_search_locations)
    candidates.append(Path("/workspace"))
    for root in candidates:
        if (root / "shared_runtime" / "verifier_helpers.py").is_file():
            return root
    return Path("/workspace")


BENCHMARK_ROOT = _benchmark_root()
HELPER_PATH = BENCHMARK_ROOT / "shared_runtime" / "verifier_helpers.py"
GRADER_PATH = BENCHMARK_ROOT / "shared_runtime" / "server" / "incubator_graders" / "coordinates_by_another_name.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_task(traj=None, env_info=None, task_info=None):
    del traj, task_info
    try:
        helpers = _load_module("weird_captcha_verifier_helpers", HELPER_PATH)
        grader = _load_module("coordinates_independent_grader", GRADER_PATH)
    except Exception as exc:
        return {"passed": False, "score": 0, "feedback": f"cannot load verifier dependency: {exc}"}
    exported, error = helpers.load_exported_result(env_info or {})
    if error:
        return {"passed": False, "score": 0, "feedback": error}
    exported = exported or {}
    try:
        replay = grader.grade(exported.get("result") or {}, exported.get("ground_truth") or {}, exported.get("public_state") or {})
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        return {"passed": False, "score": 0, "feedback": f"invalid exported designation record: {exc}"}
    passed = replay.get("passed") is True
    return {"passed": passed, "score": replay["score"] if passed else 0, "feedback": f"independent designation replay: {replay.get('feedback') or 'no feedback'}"}
