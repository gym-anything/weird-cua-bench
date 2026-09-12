from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load(
    "curio_tray_test_generator",
    ROOT / "weird_captcha_gym/shared_scripts/incubator_generators/curio_tray.py",
)
GRADER = _load(
    "curio_tray_test_grader",
    ROOT / "weird_captcha_gym/shared_runtime/server/incubator_graders/curio_tray.py",
)


def _task(level: int, interaction: str) -> dict:
    base = json.loads(
        (ROOT / "weird_captcha_gym/environments/curio_tray_env/tasks/curio_tray_seed_0001/task.json").read_text()
    )
    controls = json.loads(
        (ROOT / "weird_captcha_gym/environments/curio_tray_env/controls.json").read_text()
    )
    base["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": "live",
        "difficulty_parameters": controls["difficulty"][str(level)]["parameters"],
    }
    return base


def _passing_payload(public: dict, truth: dict) -> dict:
    items = truth["items"]
    remaining = {str(item["id"]): item for item in items}
    tray: list[str] = []
    picks: list[dict] = []
    triples = 0
    interaction = truth["control_condition"]["interaction"]
    source = "proxy_pick" if interaction == "simplified" else "pile_click"
    for sequence, item_id in enumerate(truth["solution_order"], start=1):
        assert item_id in GRADER._accessible(items, set(remaining))
        item = remaining.pop(item_id)
        tray.append(str(item["type"]))
        cleared = None
        outcome = "pick"
        if tray.count(str(item["type"])) == 3:
            tray = [value for value in tray if value != item["type"]]
            cleared = str(item["type"])
            triples += 1
            outcome = "triple_clear"
        picks.append(
            {
                "sequence": sequence,
                "item_id": item_id,
                "input_source": source,
                "outcome": outcome,
                "cleared_type": cleared,
                "tray_after": tray[:],
                "tray_size_after": len(tray),
                "remaining_count": len(remaining),
            }
        )
    return {
        "mechanic_id": "curio_tray",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "picks": picks,
        "tray": tray,
        "remaining_ids": sorted(remaining),
        "pick_count": len(picks),
        "triple_count": triples,
        "completed": True,
    }


def test_all_profiles_generate_and_interaction_is_equivalent() -> None:
    for level in range(1, 6):
        simplified_public, simplified_truth = GENERATOR.generate(_task(level, "simplified"), "curio-test-seed")
        full_public, full_truth = GENERATOR.generate(_task(level, "full"), "curio-test-seed")
        assert simplified_public["cabinet"] == full_public["cabinet"]
        assert simplified_public["challenge_id"] == full_public["challenge_id"]
        assert len(simplified_public["cabinet"]["items"]) == (9, 12, 15, 21, 27)[level - 1]
        for public, truth in ((simplified_public, simplified_truth), (full_public, full_truth)):
            result = GRADER.grade(_passing_payload(public, truth), truth, public)
            assert result["passed"] is True, result


def test_same_profile_varies_by_seed_without_changing_contract() -> None:
    first_public, first_truth = GENERATOR.generate(_task(4, "full"), "curio-seed-a")
    second_public, second_truth = GENERATOR.generate(_task(4, "full"), "curio-seed-b")
    assert first_public["challenge_id"] != second_public["challenge_id"]
    assert first_public["cabinet"] != second_public["cabinet"]
    assert len(first_truth["solution_order"]) == len(first_truth["items"]) == 21
    assert len(second_truth["solution_order"]) == len(second_truth["items"]) == 21


def test_wrong_input_surface_and_stale_challenge_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "curio-rejection-seed")
    payload = _passing_payload(public, truth)
    wrong_surface = copy.deepcopy(payload)
    wrong_surface["picks"][0]["input_source"] = "proxy_pick"
    assert GRADER.grade(wrong_surface, truth, public)["passed"] is False
    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "stale000000"
    assert GRADER.grade(stale, truth, public)["feedback"] == "stale challenge"


def test_empty_incomplete_transcript_is_a_real_failure() -> None:
    public, truth = GENERATOR.generate(_task(4, "simplified"), "curio-empty-seed")
    payload = {
        "mechanic_id": "curio_tray",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "picks": [],
        "tray": [],
        "remaining_ids": sorted(str(item["id"]) for item in truth["items"]),
        "pick_count": 0,
        "triple_count": 0,
        "completed": False,
    }
    assert GRADER.grade(payload, truth, public)["passed"] is False
