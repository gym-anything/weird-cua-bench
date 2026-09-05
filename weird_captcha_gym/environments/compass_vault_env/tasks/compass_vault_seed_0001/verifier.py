from __future__ import annotations

def verify_task(traj=None, env_info=None, task_info=None):
    try:
        # Materialized tasks live outside the benchmark source tree. Their
        # dependencies belong to the installed benchmark, not their ancestors.
        from weird_captcha_gym.shared_runtime import verifier_helpers as helpers
        from weird_captcha_gym.shared_runtime.server.incubator_graders import compass_vault as grader
    except Exception as exc:
        return {"passed": False, "score": 0, "feedback": f"cannot load verifier dependency: {exc}"}
    exported, error = helpers.load_exported_result(env_info or {})
    if error:
        return {"passed": False, "score": 0, "feedback": error}
    exported = exported or {}
    result = exported.get("result") or {}
    ground_truth = exported.get("ground_truth") or {}
    public_state = exported.get("public_state") or {}
    replay = grader.grade(result, ground_truth, public_state)
    passed = replay.get("passed") is True
    return {
        "passed": passed,
        "score": replay.get("score", 0) if passed else 0,
        "feedback": f"independent construction replay: {replay.get('feedback') or 'no feedback'}",
    }
