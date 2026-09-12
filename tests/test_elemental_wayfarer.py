from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "weird_captcha_gym/shared_scripts/incubator_generators/elemental_wayfarer.py"
GRADER_PATH = ROOT / "weird_captcha_gym/shared_runtime/server/incubator_graders/elemental_wayfarer.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load(GENERATOR_PATH, "elemental_wayfarer_test_generator")
GRADER = _load(GRADER_PATH, "elemental_wayfarer_test_grader")


def _route_events(public: dict, truth: dict, source: str) -> list[dict]:
    directions = {
        (0, -1): "UP",
        (0, 1): "DOWN",
        (-1, 0): "LEFT",
        (1, 0): "RIGHT",
    }
    tiles = {(tile["x"], tile["y"]): tile for tile in truth["tiles"]}
    position = (truth["start"]["x"], truth["start"]["y"])
    form = "clay"
    collected: set[str] = set()
    events: list[dict] = []
    route = [position]
    for action in truth["solution_actions"]:
        dx, dy = next(delta for delta, name in directions.items() if name == action)
        route.append((route[-1][0] + dx, route[-1][1] + dy))
    for sequence, (action, before, after) in enumerate(
        zip(truth["solution_actions"], route, route[1:]), start=1
    ):
        tile = tiles[after]
        next_form = form
        collected_token = None
        outcome = "step"
        if tile.get("kind") in {"token", "decoy"} and tile["id"] not in collected:
            collected.add(tile["id"])
            collected_token = tile["id"]
            next_form = tile["element"]
            outcome = f"collect_{next_form}"
        if after == (truth["exit"]["x"], truth["exit"]["y"]) and next_form == truth["exit"]["requires"]:
            outcome = "arrive"
        events.append(
            {
                "sequence": sequence,
                "action": action,
                "input_source": source,
                "from": [before[0], before[1]],
                "to": [after[0], after[1]],
                "outcome": outcome,
                "form_after": next_form,
                "collected_token": collected_token,
            }
        )
        position, form = after, next_form
    return events


def _task(level: int, interaction: str, seed: str = "test-seed") -> tuple[dict, dict]:
    return GENERATOR.generate(
        {
            "id": f"elemental_wayfarer_d{level}_{interaction}@0.1",
            "metadata": {"control_condition": {"difficulty": level, "interaction": interaction}},
        },
        seed,
    )


def test_all_difficulties_and_input_surfaces_grade_the_same_visible_world() -> None:
    for level in range(1, 6):
        full_public, full_truth = _task(level, "full")
        simplified_public, simplified_truth = _task(level, "simplified")
        assert full_public["chamber"] == simplified_public["chamber"]
        assert full_truth["tiles"] == simplified_truth["tiles"]
        assert full_truth["solution_actions"] == simplified_truth["solution_actions"]

        full_payload = {
            "mechanic_id": full_truth["mechanic_id"],
            "task_id": full_truth["task_id"],
            "challenge_id": full_truth["challenge_id"],
            "actions": _route_events(full_public, full_truth, "keyboard"),
            "completed": True,
        }
        simple_payload = {
            **full_payload,
            "task_id": simplified_truth["task_id"],
            "challenge_id": simplified_truth["challenge_id"],
            "actions": _route_events(simplified_public, simplified_truth, "direction_button"),
        }
        assert GRADER.grade(full_payload, full_truth, full_public)["passed"] is True
        assert GRADER.grade(simple_payload, simplified_truth, simplified_public)["passed"] is True


def test_input_surface_is_bound_by_the_grader() -> None:
    public, truth = _task(4, "full")
    payload = {
        "mechanic_id": truth["mechanic_id"],
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "actions": _route_events(public, truth, "direction_button"),
        "completed": True,
    }
    result = GRADER.grade(payload, truth, public)
    assert result["passed"] is False
    assert "wrong interaction input" in result["feedback"]


def test_final_visible_exit_move_is_arrival() -> None:
    public, truth = _task(5, "simplified")
    events = _route_events(public, truth, "direction_button")
    assert events[-1]["outcome"] == "arrive"
    assert GRADER.grade(
        {
            "mechanic_id": truth["mechanic_id"],
            "task_id": truth["task_id"],
            "challenge_id": truth["challenge_id"],
            "actions": events,
            "completed": True,
        },
        truth,
        public,
    )["passed"] is True
