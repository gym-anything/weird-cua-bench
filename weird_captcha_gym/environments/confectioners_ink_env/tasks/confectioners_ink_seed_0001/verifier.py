from __future__ import annotations

MECHANIC_ID = "confectioners_ink"


def verify_task(traj=None, env_info=None, task_info=None):
    del traj, task_info
    try:
        # Verifiers are copied to arbitrary controlled-task output directories.
        # Resolve code through the installed benchmark, not the copied file's
        # ancestry or paths supplied by the task/result being graded.
        from weird_captcha_gym.shared_runtime import verifier_helpers as helpers
        from weird_captcha_gym.shared_runtime.server.incubator_graders import confectioners_ink as grader
        exported, error = helpers.load_exported_result(env_info or {})
    except Exception as exc:
        return {"passed": False, "score": 0, "feedback": f"cannot load verifier dependency: {exc}"}
    if error:
        return {"passed": False, "score": 0, "feedback": error}
    exported = exported or {}
    decision = grader.grade(exported.get("result") or {}, exported.get("ground_truth") or {}, exported.get("public_state") or {})
    passed = decision.get("passed") is True
    return {"passed": passed, "score": 100 if passed else 0, "feedback": f"independent confectioner's ink replay: {decision.get('feedback') or 'no feedback'}"}
