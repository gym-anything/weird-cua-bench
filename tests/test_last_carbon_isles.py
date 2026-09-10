"""Focused contract checks for The Last Carbon Isles."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "weird_captcha_gym" / "environments" / "last_carbon_isles_env"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load(
    "last_carbon_isles_test_generator",
    ROOT / "weird_captcha_gym" / "shared_scripts" / "incubator_generators" / "last_carbon_isles.py",
)
GRADER = _load(
    "last_carbon_isles_test_grader",
    ROOT / "weird_captcha_gym" / "shared_runtime" / "server" / "incubator_graders" / "last_carbon_isles.py",
)


def _controls() -> dict:
    return json.loads((ENV / "controls.json").read_text(encoding="utf-8"))


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    controls = _controls()
    profile = controls["difficulty"][str(level)]
    return {
        "id": f"last_carbon_isles_d{level}_{interaction}_seed_0001_t{real_time}",
        "natural_language": profile["natural_language"],
        "_control_condition": {
            "difficulty": level,
            "interaction": interaction,
            "real_time": real_time,
            "difficulty_parameters": copy.deepcopy(profile["parameters"]),
        },
    }


def _without_control(value: dict) -> dict:
    result = copy.deepcopy(value)
    result.pop("control_condition", None)
    result.pop("task_id", None)
    return result


def _solution_events(public: dict, truth: dict, interaction: str) -> list[dict]:
    cards = {str(card["id"]): card for card in truth["cards"]}
    target_ids = set(truth["target_card_ids"])
    hand = list(truth["initial_hand_ids"])
    events: list[dict] = []
    sequence = 1
    elapsed = 0

    def play(card_id: str) -> None:
        nonlocal sequence, elapsed
        events.append({
            "sequence": sequence,
            "elapsed_ms": elapsed,
            "kind": "play",
            "card_id": card_id,
            "region_id": cards[card_id]["home_region"],
            "card_source": "card_click" if interaction == "simplified" else "card_drag",
            "region_source": "region_click" if interaction == "simplified" else "region_drop",
            "cost": cards[card_id]["cost"],
        })
        sequence += 1
        elapsed += 25
        hand.remove(card_id)

    if truth.get("witness_route"):
        route = truth["witness_route"]
        for track in truth["research_tracks"]:
            card_id = next(c["id"] for c in track["offers"] if c["id"] in route)
            events.append({"sequence": sequence, "elapsed_ms": elapsed, "kind": "research",
                           "source": "research_button", "stage": track["stage"],
                           "card_id": card_id, "cost": track["cost"]})
            sequence += 1
            elapsed += 25
            hand.append(card_id)
        for card_id in route:
            play(card_id)
        events.append({"sequence": sequence, "elapsed_ms": elapsed, "kind": "finish"})
        return events

    for card_id in list(hand):
        if card_id in target_ids:
            play(card_id)
    for track in truth["research_tracks"]:
        card_id = next(
            str(offer["id"])
            for offer in track["offers"]
            if str(offer["id"]) in target_ids
        )
        events.append({
            "sequence": sequence,
            "elapsed_ms": elapsed,
            "kind": "research",
            "source": "research_button",
            "stage": track["stage"],
            "card_id": card_id,
            "cost": track["cost"],
        })
        sequence += 1
        elapsed += 25
        hand.append(card_id)
        play(card_id)
    events.append({"sequence": sequence, "elapsed_ms": elapsed, "kind": "finish"})
    return events


def test_profiles_cover_both_surfaces_and_static_clock() -> None:
    controls = _controls()
    assert controls["baseline"] == {"difficulty": 2, "interaction": "full", "real_time": "live"}
    assert json.loads((ENV / "env.json").read_text(encoding="utf-8"))["runner_options"] == controls["real_time"]
    assert controls["difficulty"]["2"]["parameters"] == GENERATOR.DEFAULT_PARAMETERS
    expected_regions = {1: 3, 2: 5, 3: 5, 4: 6, 5: 6}
    expected_offers = {1: 0, 2: 3, 3: 4, 4: 5, 5: 5}
    for level in range(1, 6):
        full, full_truth = GENERATOR.generate(_task(level, "full"), f"last-carbon-{level}")
        simple, simple_truth = GENERATOR.generate(_task(level, "simplified"), f"last-carbon-{level}")
        paused, paused_truth = GENERATOR.generate(_task(level, "full", "paused"), f"last-carbon-{level}")
        assert len(full["regions"]) == expected_regions[level]
        assert len(full_truth.get("witness_route") or full_truth["target_card_ids"]) == expected_regions[level]
        assert len(full_truth["research_tracks"]) == expected_offers[level]
        assert all(len(track["offers"]) >= 2 for track in full_truth["research_tracks"])
        assert _without_control(full) == _without_control(simple) == _without_control(paused)
        assert _without_control(full_truth) == _without_control(simple_truth) == _without_control(paused_truth)
    for profile in controls["difficulty"].values():
        prompt = profile["natural_language"]
        assert "screenshots and visible controls" in prompt
        assert "Developer Tools" in prompt
        assert "DOM or page-state inspection" in prompt
        assert "unrelated tabs" in prompt
        interaction_prompts = profile["natural_language_by_interaction"]
        simplified_prompt = interaction_prompts["simplified"]
        assert "click" in simplified_prompt.lower()
        assert "screenshots and visible controls" in simplified_prompt
        assert "Developer Tools" in simplified_prompt


def test_independent_grader_accepts_generated_plan_and_rejects_wrong_surface() -> None:
    public, truth = GENERATOR.generate(_task(5, "full"), "last-carbon-grader")
    events = _solution_events(public, truth, "full")
    payload = {
        "mechanic_id": "last_carbon_isles",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "events": events,
    }
    accepted = GRADER.grade(payload, truth, public)
    assert accepted["passed"] is True, accepted
    wrong_surface = copy.deepcopy(payload)
    wrong_surface["events"] = _solution_events(public, truth, "simplified")
    rejected = GRADER.grade(wrong_surface, truth, public)
    assert rejected["passed"] is False

    trailing_event = copy.deepcopy(payload)
    trailing_event["events"].append({
        "sequence": len(trailing_event["events"]) + 1,
        "elapsed_ms": trailing_event["events"][-1]["elapsed_ms"],
        "kind": "unknown",
    })
    assert GRADER.grade(trailing_event, truth, public)["passed"] is False

    missing_cost = copy.deepcopy(payload)
    next(event for event in missing_cost["events"] if event["kind"] == "play").pop("cost")
    assert GRADER.grade(missing_cost, truth, public)["passed"] is False
