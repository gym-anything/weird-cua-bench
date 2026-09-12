from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
TASKS = BENCHMARK / "environments/timber_knot_release_env/tasks"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = load(BENCHMARK / "shared_scripts/setup_task.py", "timber_knot_setup_test")
GRADER = load(BENCHMARK / "shared_runtime/server/incubator_graders/timber_knot_release.py", "timber_knot_grader_test")


def task(level: int, interaction: str) -> dict:
    return json.loads((TASKS / f"timber_knot_release_d{level}_{interaction}_seed_0001/task.json").read_text())


def replay(task_data: dict, seed: str) -> tuple[dict, dict, dict]:
    public, truth = SETUP.generate_task_state(task_data, seed)
    interaction = (truth["control_condition"] or {})["interaction"]
    events = [{"sequence": 1, "kind": "start"}]
    sequence = 2
    for event in truth["solution"]:
        if interaction == "simplified":
            events.append({"sequence": sequence, "kind": "select", "piece": event["piece"], "input_source": "beam_select"})
            sequence += 1
            source = "proxy_step"
        else:
            source = "direct_drag"
        events.append({"sequence": sequence, **{key: event[key] for key in ("piece", "axis", "direction", "from", "to")}, "kind": "move", "input_source": source})
        sequence += 1
    events.append({"sequence": sequence, "kind": "finish", "input_source": "certify_button", "completed": True, "released": truth["solution_order"]})
    result = {
        "mechanic_id": truth["mechanic_id"],
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "control_condition": public.get("control_condition"),
        "interaction_mode": interaction,
        "events": events,
    }
    return public, truth, result


def test_all_profiles_and_interaction_surfaces_grade() -> None:
    for level in range(1, 6):
        for interaction in ("full", "simplified"):
            public, truth, result = replay(task(level, interaction), f"pytest-timber-{level}")
            grade = GRADER.grade(result, truth, public)
            assert grade["passed"] is True, (level, interaction, grade)


def test_interaction_profiles_preserve_same_visible_world() -> None:
    full, _, _ = replay(task(3, "full"), "pytest-shared-world")
    simplified, _, _ = replay(task(3, "simplified"), "pytest-shared-world")
    assert full["pieces"] == simplified["pieces"]


def test_wrong_surface_and_stale_challenge_are_rejected() -> None:
    public, truth, result = replay(task(3, "full"), "pytest-negative")
    wrong_surface = copy.deepcopy(result)
    wrong_surface["interaction_mode"] = "simplified"
    assert GRADER.grade(wrong_surface, truth, public)["passed"] is False
    stale = copy.deepcopy(result)
    stale["challenge_id"] = "stale-challenge"
    assert GRADER.grade(stale, truth, public)["passed"] is False
