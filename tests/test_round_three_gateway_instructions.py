"""New task instructions must not contradict the programmatic agent gateway."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment
from weird_captcha_gym.tools.run_realtime_evaluation import _task_description

BENCH = Path(__file__).resolve().parents[1] / "weird_captcha_gym"
MECHANICS = (
    "after_hours_at_the_reliquary",
    "anthill_front",
    "apothecary_dead_reckoning",
    "ballast_lantern",
    "bandaged_rose_window",
    "chain_of_appetite",
    "charter_of_the_nine_cantons",
    "circle_limit_twist",
    "comparator_engine",
    "compass_vault",
    "confectioners_ink",
    "coordinates_by_another_name",
    "crackglaze_crossing",
    "einstein_loop",
    "flip_gate_cascade",
    "fluke_census",
    "four_pane_pilgrimage",
    "leaning_tower_of_panels",
    "letter_rapids",
    "load_bearing_idol",
    "museum_of_lost_gestures",
    "one_stroke_atelier",
    "passphrase_under_siege",
    "punchcutters_bench",
    "reflow_vitrine",
    "residual_telescope",
    "silent_colleague",
    "sorting_belt_logic_bench",
    "statute_yard",
    "threshold_grapevine",
    "two_lamp_dyeworks",
    "two_season_strand",
    "unmarked_landfall",
    "unwatched_wing",
    "waggle_dispatch",
)


@pytest.mark.parametrize("mechanic", MECHANICS)
def test_gateway_task_instructions_preserve_screenshot_boundary(tmp_path, mechanic):
    env = BENCH / "environments" / f"{mechanic}_env"
    tasks = [env / "tasks" / f"{mechanic}_seed_0001"]
    tasks.extend(materialize_environment(env, tmp_path))
    assert len(tasks) == 11
    for path in tasks:
        task = json.loads((path / "task.json").read_text())
        prompt = _task_description(
            SimpleNamespace(task_spec=SimpleNamespace(**task)),
            SimpleNamespace(), gateway_programs_allowed=True,
        )
        assert "Do not use code" not in prompt
        assert "do not use code" not in prompt
        assert "You may write programs inside the isolated agent sandbox" in prompt
        assert "DOM" in prompt and "screenshots" in prompt
        # Task text may restrict access to the task's terminal, never programming
        # in the separate agent sandbox.
        assert "terminal, shell, Python" not in prompt
