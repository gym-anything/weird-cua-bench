from __future__ import annotations

import importlib.util
from pathlib import Path


MECHANIC_ID = "waggle_dispatch"

def _dependency_paths():
    # Source tasks use their checkout. Materialized tasks may live anywhere;
    # their shared runtime comes from the installed benchmark package.
    roots = list(Path(__file__).resolve().parents)
    package = importlib.util.find_spec("weird_captcha_gym")
    if package is not None and package.origin:
        roots.append(Path(package.origin).resolve().parent)
    for root in roots:
        helper = root / "shared_runtime" / "verifier_helpers.py"
        grader = root / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC_ID}.py"
        if helper.is_file() and grader.is_file():
            return helper, grader
    raise ImportError("Waggle Dispatch requires the installed weird-cua-bench package or a source checkout")


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
        helper_path, grader_path = _dependency_paths()
        helpers = _load("weird_captcha_verifier_helpers", helper_path)
        grader = _load(f"{MECHANIC_ID}_independent_grader", grader_path)
        exported, error = helpers.load_exported_result(env_info or {})
    except Exception as exc:
        return {"passed": False, "score": 0, "feedback": f"cannot load verifier dependency: {exc}"}
    if error:
        return {"passed": False, "score": 0, "feedback": error}
    exported = exported or {}
    decision = grader.grade(exported.get("result") or {}, exported.get("ground_truth") or {}, exported.get("public_state") or {})
    passed = decision.get("passed") is True
    return {"passed": passed, "score": 100 if passed else 0, "feedback": f"independent waggle dispatch replay: {decision.get('feedback') or 'no feedback'}"}
