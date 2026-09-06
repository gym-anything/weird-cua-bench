"""The reference policy must solve through both input surfaces and schedules."""
import pytest

from tests.test_round_three_task_clocks import task_browser


@pytest.mark.parametrize("interaction", ["full", "simplified"])
@pytest.mark.parametrize("time_mode", ["live", "paused"])
def test_feedback_solution_at_level_five(tmp_path, interaction, time_mode):
    pytest.importorskip("playwright.sync_api")
    from weird_captcha_gym.tools.incubator_solvers.ballast_lantern import solve
    from weird_captcha_gym.shared_runtime.server.incubator_graders.ballast_lantern import grade
    from weird_captcha_gym.tools.smoke_incubator_batch_one_ui import exported_payload, run_task_verifier

    with task_browser(tmp_path, "ballast_lantern", interaction, difficulty=5, time_mode=time_mode) as (page, state):
        solve(page, state, tmp_path / "captures", "ballast_lantern")
        exported = exported_payload(state)
        assert exported["result"]["server_grade"]["passed"] is True
        assert grade(exported["result"], exported["ground_truth"], exported["public_state"])["passed"] is True
        assert run_task_verifier("ballast_lantern", exported, tmp_path)["passed"] is True
