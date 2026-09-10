from __future__ import annotations

import importlib.util
from pathlib import Path


MECHANIC_ID = "polycube_parcel"


def _benchmark_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "shared_runtime" / "verifier_helpers.py").is_file():
            return parent
    spec = importlib.util.find_spec("weird_captcha_gym")
    for location in (spec.submodule_search_locations if spec else ()) or ():
        root = Path(location)
        if (root / "shared_runtime" / "verifier_helpers.py").is_file():
            return root
    raise ImportError("installed Weird CUA benchmark runtime is unavailable")


ROOT = _benchmark_root()


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_task(traj=None, env_info=None, task_info=None):
    del traj, task_info
    try:
        helpers = _load("polycube_parcel_verifier_helpers", ROOT / "shared_runtime" / "verifier_helpers.py")
        grader = _load("polycube_parcel_independent_grader", ROOT / "shared_runtime" / "server" / "incubator_graders" / "polycube_parcel.py")
        exported, error = helpers.load_exported_result(env_info or {})
    except Exception as exc:
        return {"passed": False, "score": 0, "feedback": f"cannot load verifier dependency: {exc}"}
    if error:
        return {"passed": False, "score": 0, "feedback": error}
    exported = exported or {}
    decision = grader.grade(exported.get("result") or {}, exported.get("ground_truth") or {}, exported.get("public_state") or {})
    passed = decision.get("passed") is True
    return {"passed": passed, "score": 100 if passed else 0, "feedback": f"independent polycube occupancy replay: {decision.get('feedback') or 'no feedback'}"}
