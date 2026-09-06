from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
GENERATOR_PATH = BENCH / "shared_scripts" / "incubator_generators" / "anthill_front.py"
GRADER_PATH = BENCH / "shared_runtime" / "server" / "incubator_graders" / "anthill_front.py"
VERIFIER_PATH = BENCH / "environments" / "anthill_front_env" / "tasks" / "anthill_front_seed_0001" / "verifier.py"
CONTROLS_PATH = BENCH / "environments" / "anthill_front_env" / "controls.json"
TASK_PATH = BENCH / "environments" / "anthill_front_env" / "tasks" / "anthill_front_seed_0001" / "task.json"
FRONTEND_PATH = BENCH / "shared_runtime" / "app" / "mechanics" / "anthill_front.js"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = _load("anthill_front_generator_test", GENERATOR_PATH)
grader = _load("anthill_front_grader_test", GRADER_PATH)
verifier = _load("anthill_front_exported_verifier_test", VERIFIER_PATH)
controls = json.loads(CONTROLS_PATH.read_text(encoding="utf-8"))


def _condition(level: int, interaction: str) -> dict:
    return {
        "difficulty": level,
        "difficulty_label": controls["difficulty"][str(level)]["label"],
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
        "interaction": interaction,
        "real_time": "live",
    }


def _generated(level: int, interaction: str, seed: str = "anthill-test"):
    task = {
        "id": f"anthill_front_d{level}_{interaction}_seed_0001@0.1",
        "natural_language": "Keep the amber queen alive and destroy the rival queen.",
        "_control_condition": _condition(level, interaction),
    }
    return generator.generate(task, seed)


def _winning_payload(truth: dict, interaction: str) -> dict:
    world = truth["world"]
    state = grader.initial_state(world)
    source = "direct_map" if interaction == "full" else "command_panel"
    events: list[dict] = []

    def action(name: str, ids: list[str], target: str) -> None:
        event = {"sequence": len(events) + 1, "tick": state["tick"], "action": name, "unit_ids": list(ids), "target": target, "input_source": source}
        grader.apply_action(state, world, name, list(ids), target)
        events.append(event)

    action("GATHER", list(state["workers"]), "seed")
    if world["hidden_opening"]:
        action("SCOUT", [state["workers"][0]], "front")
    if int(world["dig_workers"]) > 0:
        start = 1 if world["hidden_opening"] else 0
        action("DIG", state["workers"][start:start + int(world["dig_workers"])], "brood")

    desired = int(world["enemy_queen"]["hp"]) + sum((int(raid["count"]) + 2) // 3 for raid in world["raids"])
    raised = 0
    while raised < desired:
        if state["brood_ready"] and state["seeds"] >= int(world["soldier_cost"]):
            action("RAISE", [], "brood")
            raised += 1
        else:
            grader.advance(state, world, state["tick"] + 1)
    while len(state["soldiers"]) < desired:
        grader.advance(state, world, state["tick"] + 1)

    overlapping = len(world["raids"]) > 1 and int(world["raids"][1]["response_open_tick"]) <= int(world["raids"][0]["response_deadline_tick"])
    allocated = 0
    for index, raid in enumerate(world["raids"]):
        if index and not overlapping:
            grader.advance(state, world, int(world["raids"][index - 1]["impact_tick"]) + 1)
        grader.advance(state, world, int(raid["response_open_tick"]))
        if overlapping:
            count = int(raid["count"])
            unit_ids = list(state["soldiers"])[allocated:allocated + count]
            allocated += count
        else:
            unit_ids = list(state["soldiers"])
        action("MARCH", unit_ids, grader.intercept_lane(raid, state["tick"]))
    grader.advance(state, world, max(int(raid["impact_tick"]) for raid in world["raids"]) + 1)
    action("MARCH", list(state["soldiers"]), "enemy")
    while not state["terminal"]:
        grader.advance(state, world, state["tick"] + 1)
    return {
        "mechanic_id": "anthill_front",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "events": events,
        "final_tick": state["tick"],
        "final_state": grader.summary(state, world),
    }


def test_all_difficulty_and_interaction_pairs_replay_to_exact_victory():
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = _generated(level, interaction)
            payload = _winning_payload(truth, interaction)
            outcome = grader.grade(payload, truth, public)
            assert outcome["passed"] is True, (level, interaction, outcome)
            assert payload["final_state"]["queen_hp"] > 0
            assert payload["final_state"]["enemy_queen_hp"] == 0
            assert payload["final_state"]["waves_cleared"] == len(truth["world"]["raids"])
            assert payload["final_state"]["rival_outposts_ready"] == len(truth["world"]["raids"])
            worlds.append(public["world"])
        assert worlds[0] == worlds[1]


def test_levels_change_active_decision_contract_and_original_baseline_moved_to_level_three():
    assert controls["baseline"] == {"difficulty": 3, "interaction": "full", "real_time": "live"}
    signatures = []
    for level in range(1, 6):
        public, _truth = _generated(level, "full")
        world = public["world"]
        signatures.append((world["width"], world["dig_workers"], world["hidden_opening"], tuple((raid["lane"], raid["count"], raid["impact_tick"]) for raid in world["raids"]), world["enemy_queen"]["hp"]))
    assert len(set(signatures)) == 5
    assert signatures[0][2] is False
    assert len(signatures[2][3]) == 1
    assert len(signatures[3][3]) == 2
    assert signatures[-1][3][0][0] != signatures[-1][3][1][0]
    level4 = _generated(4, "full")[1]["world"]["raids"]
    level5 = _generated(5, "full")[1]["world"]["raids"]
    assert level4[1]["response_open_tick"] > level4[0]["impact_tick"]
    assert level5[1]["response_open_tick"] <= level5[0]["response_deadline_tick"]


def test_seeded_worlds_have_structural_variation_and_fair_nonoverlapping_geometry():
    for level in range(1, 6):
        signatures = set()
        for seed_index in range(200):
            public, truth = _generated(level, "full", seed=f"anthill-layout-{level}-{seed_index}")
            world = public["world"]
            signatures.add(
                (
                    tuple((worker["x"], worker["y"]) for worker in world["workers"]),
                    tuple(world["lane_y"].items()),
                    tuple(world["seed_pile"].values()),
                    tuple(world["brood"].values()),
                    tuple(world["listening_front"].values()),
                    tuple((raid["outpost"]["x"], raid["outpost"]["y"], raid["motion_phase_offset_ticks"]) for raid in world["raids"]),
                )
            )
            assert public["world"] == truth["world"]
            assert 0 < world["home_queen"]["x"] < world["brood"]["x"] < world["seed_pile"]["x"] < world["listening_front"]["x"] < world["enemy_queen"]["x"] < world["width"]
            assert 0 < world["lane_y"]["north"] < world["home_queen"]["y"] < world["lane_y"]["south"] < world["height"]
            assert len({(worker["x"], worker["y"]) for worker in world["workers"]}) == len(world["workers"])
            assert all(raid["outpost"]["x"] - world["listening_front"]["x"] >= 2.5 for raid in world["raids"])
            assert all(0 <= raid["motion_phase_offset_ticks"] < 36 for raid in world["raids"])
        assert len(signatures) >= 198


def test_every_raid_has_a_replayed_expansion_before_spawn_and_impact():
    for level in range(1, 6):
        public, truth = _generated(level, "full")
        for raid in truth["world"]["raids"]:
            assert 0 <= raid["expand_start_tick"] < raid["expand_complete_tick"] < raid["spawn_tick"]
            assert raid["spawn_tick"] < raid["response_open_tick"] < raid["response_deadline_tick"] < raid["impact_tick"]
            assert raid["outpost"]["y"] not in truth["world"]["lane_y"].values()
        assert public["world"] == truth["world"]


def test_unconditioned_task_is_the_original_configuration_at_level_three():
    task = json.loads(TASK_PATH.read_text(encoding="utf-8"))
    baseline_public, _ = generator.generate(task, "same-world")
    controlled_public, _ = _generated(3, "full", seed="same-world")
    assert baseline_public["difficulty_level"] == 3
    assert baseline_public["world"] == controlled_public["world"]


def test_grader_rejects_wrong_surface_stale_identity_and_state_tampering():
    public, truth = _generated(4, "full")
    payload = _winning_payload(truth, "full")
    wrong_surface = copy.deepcopy(payload)
    wrong_surface["events"][0]["input_source"] = "command_panel"
    assert grader.grade(wrong_surface, truth, public)["passed"] is False
    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "stale"
    assert grader.grade(stale, truth, public)["passed"] is False
    tampered = copy.deepcopy(payload)
    tampered["final_state"]["enemy_queen_hp"] = 1
    assert grader.grade(tampered, truth, public)["passed"] is False

def test_scout_must_remain_assigned_and_excavation_uses_the_exact_crew():
    _public, truth = _generated(3, "full")
    world = truth["world"]
    state = grader.initial_state(world)
    grader.apply_action(state, world, "GATHER", list(state["workers"]), "seed")
    grader.apply_action(state, world, "SCOUT", ["W1"], "front")
    with pytest.raises(ValueError, match="exactly"):
        grader.apply_action(state, world, "DIG", ["W2", "W3", "W4"], "brood")
    grader.apply_action(state, world, "DIG", ["W1", "W2"], "brood")
    grader.advance(state, world, int(world["scout_ticks"]) + 2)
    assert state["opening_revealed"] is False
    assert state["scout_id"] is None
    assert state["brood_ready"] is True

    grader.apply_action(state, world, "SCOUT", ["W1"], "front")
    grader.advance(state, world, state["tick"] + int(world["scout_ticks"]))
    assert state["opening_revealed"] is True
    assert state["scout_id"] is None
    assert state["orders"]["W1"] == "gather"


def test_precommitment_and_preclear_assault_are_rejected_across_fresh_instances():
    for level in range(1, 6):
        for seed_index in range(20):
            _public, truth = _generated(level, "full", seed=f"anthill-precommit-{level}-{seed_index}")
            world = truth["world"]
            state = grader.initial_state(world)
            state["opening_revealed"] = True
            state["soldiers"] = ["S1"]
            state["orders"]["S1"] = "rally"
            state["order_started"]["S1"] = 0
            first = world["raids"][0]
            grader.advance(state, world, int(first["spawn_tick"]) - 1)
            with pytest.raises(ValueError, match="intercept band"):
                grader.apply_action(state, world, "MARCH", ["S1"], first["lane"])
            with pytest.raises(ValueError, match="before every raid"):
                grader.apply_action(state, world, "MARCH", ["S1"], "enemy")


def test_visible_intercept_window_expires_and_one_blind_guess_cannot_be_retried():
    _public, truth = _generated(3, "full", seed="anthill-window")
    world = truth["world"]
    raid = world["raids"][0]

    state = grader.initial_state(world)
    state["opening_revealed"] = True
    state["soldiers"] = ["S1"]
    state["orders"]["S1"] = "rally"
    state["order_started"]["S1"] = 0
    grader.advance(state, world, int(raid["response_open_tick"]))
    correct_lane = grader.intercept_lane(raid, state["tick"])
    wrong_lane = "south" if correct_lane == "north" else "north"
    grader.apply_action(state, world, "MARCH", ["S1"], wrong_lane)
    with pytest.raises(ValueError, match="uncommitted raid"):
        grader.apply_action(state, world, "MARCH", ["S1"], correct_lane)

    late = grader.initial_state(world)
    late["opening_revealed"] = True
    late["soldiers"] = ["S1"]
    late["orders"]["S1"] = "rally"
    late["order_started"]["S1"] = 0
    grader.advance(late, world, int(raid["response_deadline_tick"]) + 1)
    with pytest.raises(ValueError, match="intercept band"):
        grader.apply_action(late, world, "MARCH", ["S1"], raid["lane"])


def test_recent_motion_changes_the_correct_action_while_success_remains_possible():
    _public, truth = _generated(3, "full", seed="anthill-action-delay")
    world = truth["world"]
    raid = world["raids"][0]
    observed_tick = next(
        tick
        for tick in range(int(raid["response_open_tick"]), int(raid["response_deadline_tick"]) - 8)
        if grader.intercept_lane(raid, tick) != grader.intercept_lane(raid, tick + 8)
    )
    delayed_tick = observed_tick + 8
    observed_lane = grader.intercept_lane(raid, observed_tick)
    delayed_lane = grader.intercept_lane(raid, delayed_tick)
    assert observed_lane != delayed_lane
    assert delayed_tick < int(raid["response_deadline_tick"])

    stale = grader.initial_state(world)
    stale["opening_revealed"] = True
    stale["soldiers"] = [f"S{index + 1}" for index in range(int(raid["count"]))]
    stale["orders"].update({unit_id: "rally" for unit_id in stale["soldiers"]})
    stale["order_started"].update({unit_id: 0 for unit_id in stale["soldiers"]})
    grader.advance(stale, world, delayed_tick)
    grader.apply_action(stale, world, "MARCH", list(stale["soldiers"]), observed_lane)
    grader.advance(stale, world, int(raid["impact_tick"]))
    assert stale["successful_intercepts"] == []

    recovered = grader.initial_state(world)
    recovered["opening_revealed"] = True
    recovered["soldiers"] = [f"S{index + 1}" for index in range(int(raid["count"]))]
    recovered["orders"].update({unit_id: "rally" for unit_id in recovered["soldiers"]})
    recovered["order_started"].update({unit_id: 0 for unit_id in recovered["soldiers"]})
    grader.advance(recovered, world, delayed_tick)
    grader.apply_action(recovered, world, "MARCH", list(recovered["soldiers"]), delayed_lane)
    grader.advance(recovered, world, int(raid["impact_tick"]))
    assert recovered["successful_intercepts"] == [int(raid["wave"])]


def test_overlapping_level_five_intercepts_reserve_disjoint_soldiers():
    _public, truth = _generated(5, "full", seed="anthill-overlap")
    world = truth["world"]
    first, second = world["raids"]
    state = grader.initial_state(world)
    state["opening_revealed"] = True
    state["soldiers"] = ["S1", "S2"]
    state["orders"].update({"S1": "rally", "S2": "rally"})
    state["order_started"].update({"S1": 0, "S2": 0})
    grader.advance(state, world, int(first["response_open_tick"]))
    grader.apply_action(state, world, "MARCH", ["S1"], first["lane"])
    grader.advance(state, world, int(second["response_open_tick"]))
    with pytest.raises(ValueError, match="two unresolved"):
        grader.apply_action(state, world, "MARCH", ["S1"], second["lane"])
    grader.apply_action(state, world, "MARCH", ["S2"], second["lane"])


def test_interaction_modes_accept_the_same_semantic_allocations():
    for level in range(1, 6):
        _simple_public, simple_truth = _generated(level, "simplified", seed="anthill-mode-parity")
        _full_public, full_truth = _generated(level, "full", seed="anthill-mode-parity")
        simple = _winning_payload(simple_truth, "simplified")
        full = _winning_payload(full_truth, "full")
        strip_source = lambda event: {key: value for key, value in event.items() if key != "input_source"}
        assert [strip_source(event) for event in simple["events"]] == [strip_source(event) for event in full["events"]]
        assert simple["final_state"] == full["final_state"]


def test_frontend_hides_unscouted_rival_uses_shared_information_and_exact_screen_hit_geometry():
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    assert 'marker(world.listening_front' in source
    assert 'world.hidden_opening && !sim.opening_revealed' in source
    assert 'world.hidden_opening || sim.opening_revealed' in source
    assert 'markerContains(world.listening_front, TARGET_RADIUS_PX.front' in source
    assert 'Math.abs(y - laneScreenY(lane, x, rect)) <= TUNNEL_HALF_WIDTH_PX' in source
    assert 'const TUNNEL_HALF_WIDTH_PX = 8' in source
    assert 'id="anthill-roster"' in source
    assert 'NORTH TUNNEL' not in source  # labels are generated from the shared lane names
    assert '${lane.toUpperCase()} TUNNEL' in source
    assert 'createLinearGradient(trailSx' not in source
    assert 'Click or marquee ants' not in source
    assert "Front doctrine" not in source
    assert "Station one soldier per raider" not in source


def test_difficulty_specific_instructions_match_available_actions_and_defense_rule():
    level_one = controls["difficulty"]["1"]["natural_language"]
    assert "scout" not in level_one.lower()
    assert "excavat" not in level_one.lower()
    for level in range(2, 6):
        text = controls["difficulty"][str(level)]["natural_language"].lower()
        assert "listening front" in text
        assert "excavat" in text
        assert "movement across recent screenshots" in text
        assert "north or south" in text
        assert "reported tunnel" not in text
    base = json.loads(TASK_PATH.read_text(encoding="utf-8"))["natural_language"].lower()
    assert "movement across recent screenshots" in base
    assert "reported tunnel" not in base


def test_exported_verifier_loads_the_artifact_and_replays_it(tmp_path: Path):
    public, truth = _generated(4, "full")
    payload = _winning_payload(truth, "full")
    exported = tmp_path / "task_result.json"
    exported.write_text(json.dumps({"result": payload, "ground_truth": truth, "public_state": public}), encoding="utf-8")

    def copy_from_env(source: str, destination: str) -> None:
        assert source == "/tmp/task_result.json"
        Path(destination).write_bytes(exported.read_bytes())

    outcome = verifier.verify_task(env_info={"copy_from_env": copy_from_env})
    assert outcome["passed"] is True
    assert outcome["score"] == 100
    assert "independent colony replay" in outcome["feedback"]


def test_task_has_exact_source_anchors_and_visible_ui_only_boundary():
    task = json.loads(TASK_PATH.read_text(encoding="utf-8"))
    assert task["name"] == "Anthill Front"
    assert task["metadata"]["source_anchors"] == ["XAGT-329", "XAGT-389", "XAGT-385"]
    text = task["natural_language"]
    for phrase in ("screenshots and visible controls", "Developer Tools", "DOM or page-state inspection", "terminal", "reload/navigation", "unrelated tab"):
        assert phrase in text
    assert "screenshots and visible controls" in task["description"]
    assert "Developer Tools" in task["description"]
