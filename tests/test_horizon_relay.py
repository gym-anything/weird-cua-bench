from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import pytest

from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment


ROOT = Path(__file__).resolve().parents[1]
MECHANIC_JS = ROOT / "weird_captcha_gym/shared_runtime/app/mechanics/horizon_relay.js"
ENV = ROOT / "weird_captcha_gym/environments/horizon_relay_env"


@pytest.fixture
def tasks(tmp_path):
    generated = materialize_environment(ENV, tmp_path)
    return generated[0].parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("horizon_relay_generator_test", ROOT / "weird_captcha_gym/shared_scripts/incubator_generators/horizon_relay.py")
GRADER = _load("horizon_relay_grader_test", ROOT / "weird_captcha_gym/shared_runtime/server/incubator_graders/horizon_relay.py")


def _task(tasks: Path, level: int, interaction: str) -> dict:
    path = tasks / f"horizon_relay_d{level}_{interaction}_seed_0001/task.json"
    task = json.loads(path.read_text())
    task["_control_condition"] = task["metadata"]["control_condition"]
    return task


def test_all_ten_controlled_variants_share_world_geometry(tasks) -> None:
    for level in range(1, 6):
        simplified_public, simplified_truth = GENERATOR.generate(_task(tasks, level, "simplified"), "held-out-seed")
        full_public, full_truth = GENERATOR.generate(_task(tasks, level, "full"), "held-out-seed")
        assert simplified_public["stations"] == full_public["stations"]
        assert simplified_public["spacecraft"] == full_public["spacecraft"]
        assert simplified_public["rotation"] == full_public["rotation"]
        assert simplified_truth["spacecraft"] == full_truth["spacecraft"]
        assert simplified_public["control_condition"]["interaction"] == "simplified"
        assert full_public["control_condition"]["interaction"] == "full"


def test_profiles_change_the_active_problem(tasks) -> None:
    worlds = [GENERATOR.generate(_task(tasks, level, "full"), "profile-seed")[0] for level in range(1, 6)]
    assert [len(world["spacecraft"]) for world in worlds] == [1, 2, 3, 4, 5]
    assert [world["rotation"]["speed_deg_per_tick"] for world in worlds] == sorted(world["rotation"]["speed_deg_per_tick"] for world in worlds)
    assert [world["aim_tolerance_deg"] for world in worlds] == sorted((world["aim_tolerance_deg"] for world in worlds), reverse=True)
    assert any(abs(item["position"][1]) > 1 for item in worlds[2]["spacecraft"])


def test_independent_replay_accepts_a_closed_loop_full_solution(tasks) -> None:
    task = _task(tasks, 3, "full")
    public, truth = GENERATOR.generate(task, "replay-seed")
    radius = float(truth["planet_radius"])
    speed = float(truth["rotation_speed_deg_per_tick"])
    events = []
    sequence = 0
    current_tick = 0
    completed = []
    for craft in truth["spacecraft"]:
        station = next(
            station
            for station in truth["stations"]
            if GRADER._visible(station, craft, current_tick, speed, radius)
        )
        station_point = GRADER._station_at(station, current_tick, speed, radius)
        craft_point = tuple(float(value) for value in craft["position"])
        vector = tuple(craft_point[index] - station_point[index] for index in range(3))
        norm = math.sqrt(sum(value * value for value in vector))
        aim = [value / norm for value in vector]
        sequence += 1
        events.append({"seq": sequence, "type": "aim", "tick": current_tick, "station_id": station["id"], "craft_id": craft["id"], "input_source": "dish_drag", "aim_vector": aim, "started": True})
        for offset in range(1, int(craft["required_ticks"]) + 1):
            current_tick += 1
            sequence += 1
            events.append({"seq": sequence, "type": "sample", "tick": current_tick, "station_id": station["id"], "craft_id": craft["id"], "delivered_after": offset})
        sequence += 1
        events.append({"seq": sequence, "type": "transfer_complete", "tick": current_tick, "craft_id": craft["id"], "delivered": int(craft["required_ticks"])})
        completed.append(craft["id"])
    sequence += 1
    events.append({"seq": sequence, "type": "submit", "tick": current_tick, "input_source": "certify_button"})
    payload = {"mechanic_id": "horizon_relay", "task_id": truth["task_id"], "challenge_id": truth["challenge_id"], "interaction_mode": "full", "events": events, "completed": True}
    decision = GRADER.grade(payload, truth, public)
    assert decision["passed"], decision


def test_wrong_surface_and_stale_challenge_are_rejected(tasks) -> None:
    task = _task(tasks, 1, "full")
    public, truth = GENERATOR.generate(task, "reject-seed")
    base = {"mechanic_id": "horizon_relay", "task_id": truth["task_id"], "challenge_id": truth["challenge_id"], "interaction_mode": "simplified", "events": [], "completed": False}
    assert GRADER.grade(base, truth, public)["passed"] is False
    stale = dict(base, challenge_id="stale")
    assert "stale" in GRADER.grade(stale, truth, public)["feedback"]


def test_full_station_list_is_informational_but_simplified_list_is_actionable() -> None:
    source = MECHANIC_JS.read_text()
    assert 'if (interaction === "full") return `<div class="hr-station-info' in source
    assert 'data-station-info="${esc(station.id)}"' in source
    assert 'data-station-button="${esc(station.id)}"' in source
    assert 'event("select_station", {station_id: stationId, input_source: "station_button"})' in source


def test_overdelivery_and_duplicate_completion_are_rejected(tasks) -> None:
    task = _task(tasks, 1, "full")
    public, truth = GENERATOR.generate(task, "overdelivery-seed")
    required = int(truth["spacecraft"][0]["required_ticks"])
    craft = truth["spacecraft"][0]
    radius = float(truth["planet_radius"])
    speed = float(truth["rotation_speed_deg_per_tick"])
    station = next(
        station
        for station in truth["stations"]
        if all(
            GRADER._visible(station, craft, tick, speed, radius)
            for tick in range(required + 2)
        )
    )
    station_point = GRADER._station_at(station, 0, speed, radius)
    craft_point = tuple(float(value) for value in craft["position"])
    vector = tuple(craft_point[index] - station_point[index] for index in range(3))
    norm = math.sqrt(sum(value * value for value in vector))
    aim = [value / norm for value in vector]
    events = [{"seq": 1, "type": "aim", "tick": 0, "station_id": station["id"], "craft_id": craft["id"], "input_source": "dish_drag", "aim_vector": aim, "started": True}]
    for tick in range(1, required + 2):
        events.append({"seq": len(events) + 1, "type": "sample", "tick": tick, "station_id": station["id"], "craft_id": craft["id"], "delivered_after": tick})
    events.extend([
        {"seq": len(events) + 1, "type": "transfer_complete", "tick": required + 1, "craft_id": craft["id"], "delivered": required + 1},
        {"seq": len(events) + 1, "type": "submit", "tick": required + 1, "input_source": "certify_button"},
    ])
    payload = {"mechanic_id": "horizon_relay", "task_id": truth["task_id"], "challenge_id": truth["challenge_id"], "interaction_mode": "full", "events": events, "completed": True}
    decision = GRADER.grade(payload, truth, public)
    assert decision["passed"] is False
    assert "exceeds" in decision["feedback"]

    exact_events = [dict(event) for event in events[:required + 1]]
    exact_events.extend([
        {"type": "transfer_complete", "tick": required, "craft_id": craft["id"], "delivered": required},
        {"type": "transfer_complete", "tick": required, "craft_id": craft["id"], "delivered": required},
        {"type": "submit", "tick": required, "input_source": "certify_button"},
    ])
    for seq, event in enumerate(exact_events, start=1):
        event["seq"] = seq
    duplicate = dict(payload, events=exact_events)
    duplicate_decision = GRADER.grade(duplicate, truth, public)
    assert duplicate_decision["passed"] is False
    assert "complete" in duplicate_decision["feedback"]
