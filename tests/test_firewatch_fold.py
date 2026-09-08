from __future__ import annotations

import copy
import importlib.util
import json
from collections import deque
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "firewatch_fold_env"
MECHANIC = "firewatch_fold"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load(
    "firewatch_fold_generator_test",
    BENCHMARK / "shared_scripts" / "incubator_generators" / f"{MECHANIC}.py",
)
GRADER = _load(
    "firewatch_fold_grader_test",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py",
)
BASE_TASK = json.loads(
    (ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json").read_text(encoding="utf-8")
)
CONTROLS = json.loads((ENVIRONMENT / "controls.json").read_text(encoding="utf-8"))


def _generated(level: int | None = None, interaction: str = "full", seed: str = "test"):
    task = copy.deepcopy(BASE_TASK)
    if level is not None:
        task["_control_condition"] = {
            "difficulty": level,
            "interaction": interaction,
            "real_time": "live",
            "difficulty_parameters": copy.deepcopy(CONTROLS["difficulty"][str(level)]["parameters"]),
        }
    return GENERATOR.generate(task, seed)


def _target(position: tuple[int, int, int], direction: str, width: int) -> tuple[int, int, int]:
    face, floor, x = position
    if direction == "RIGHT" and x == width - 1:
        return 1 - face, floor, 0
    if direction == "LEFT" and x == 0:
        return 1 - face, floor, width - 1
    dx, dy = GRADER.DIRECTIONS[direction]
    return face, floor + dy, x + dx


def _snapshot(
    position: tuple[int, int, int],
    facing: str,
    cleared: set[str],
    stock: int,
    inspection_face: int,
) -> dict:
    return {
        "player": list(position),
        "facing": facing,
        "cleared_fires": sorted(cleared),
        "extinguishers_left": stock,
        "inspection_face": inspection_face,
    }


def _solution_payload(
    public: dict,
    truth: dict,
    solution_actions: list[dict] | None = None,
) -> dict:
    tower = truth["initial_tower"]
    width = int(tower["floor_width"])
    floor_count = int(tower["floor_count"])
    walls: set[tuple[int, int, int]] = set()
    ladders: set[tuple[int, int, int]] = set()
    fire_positions: dict[str, set[tuple[int, int, int]]] = {}
    for face_index, face in enumerate(tower["faces"]):
        for floor_index, floor in enumerate(face["floors"]):
            walls.update((face_index, floor_index, int(x)) for x in floor.get("walls", []))
            ladders.update((face_index, floor_index, int(x)) for x in floor.get("ladders", []))
            for fire in floor.get("fires", []):
                cells = fire.get("cells") or [fire["x"]]
                fire_positions.setdefault(str(fire["id"]), set()).update(
                    (face_index, floor_index, int(x)) for x in cells
                )
    fire_by_point = {
        point: fire_id
        for fire_id, points in fire_positions.items()
        for point in points
    }
    condition = truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or truth.get("interaction") or "full")
    sources = {
        "MOVE": "keyboard" if interaction == "full" else "control_buttons",
        "EXTINGUISH": "keyboard" if interaction == "full" else "extinguish_button",
        "INSPECT": "eye_button",
    }

    position = tuple(int(value) for value in tower["start"])
    resident = tuple(int(value) for value in tower["resident"])
    facing = "RIGHT"
    inspection_face = position[0]
    stock = int(truth["extinguisher_count"])
    cleared: set[str] = set()
    events = []

    for solution_action in solution_actions if solution_actions is not None else truth["solution_actions"]:
        action = str(solution_action["action"])
        before = _snapshot(position, facing, cleared, stock, inspection_face)
        if action == "INSPECT":
            expected_face = 1 - position[0]
            inspection_face = expected_face
            outcome = "inspected"
        elif action == "MOVE":
            direction = str(solution_action["direction"])
            facing = direction
            target = _target(position, direction, width)
            if target in walls:
                outcome = "blocked_wall"
            elif target in fire_by_point and fire_by_point[target] not in cleared:
                outcome = "blocked_fire"
            elif direction in {"UP", "DOWN"}:
                ladder_position = position if direction == "UP" else target
                if ladder_position not in ladders or not (0 <= target[1] < floor_count):
                    outcome = "blocked_ladder"
                else:
                    position = target
                    outcome = "climbed"
            else:
                position = target
                outcome = "seam_crossed" if target[0] != before["player"][0] else "walked"
        elif action == "EXTINGUISH":
            direction = str(solution_action["direction"])
            assert direction == facing
            target = _target(position, facing, width)
            fire_id = fire_by_point.get(target)
            if fire_id is None or fire_id in cleared:
                outcome = "no_fire"
            elif stock <= 0:
                outcome = "stock_empty"
            else:
                cleared.add(fire_id)
                stock -= 1
                outcome = "extinguished"
        else:
            raise AssertionError(f"unknown solution action {solution_action!r}")

        after = _snapshot(position, facing, cleared, stock, inspection_face)
        event = {
            "sequence": len(events) + 1,
            "action": action,
            "input_source": sources[action],
            "before": before,
            "after": after,
            "outcome": outcome,
        }
        if action in {"MOVE", "EXTINGUISH"}:
            event["direction"] = str(solution_action["direction"])
        if action == "INSPECT":
            event["face"] = inspection_face
        events.append(event)

    final_state = _snapshot(position, facing, cleared, stock, inspection_face)
    return {
        "mechanic_id": truth["mechanic_id"],
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "actions": events,
        "final_state": final_state,
        "extinguishers_used": int(truth["extinguisher_count"]) - stock,
        "completed": position == resident,
        "certify_input_source": "certify_button",
    }


def _affordable_route_actions(public: dict, truth: dict) -> list[dict]:
    tower = public["tower"]
    width = int(tower["floor_width"])
    floors = int(tower["floor_count"])
    walls: set[tuple[int, int, int]] = set()
    ladders: set[tuple[int, int, int]] = set()
    fire_by_point: dict[tuple[int, int, int], str] = {}
    for face_index, face in enumerate(tower["faces"]):
        for floor_index, floor in enumerate(face["floors"]):
            walls.update((face_index, floor_index, int(x)) for x in floor.get("walls", []))
            ladders.update((face_index, floor_index, int(x)) for x in floor.get("ladders", []))
            for fire in floor.get("fires", []):
                for x in fire.get("cells") or [fire["x"]]:
                    fire_by_point[(face_index, floor_index, int(x))] = str(fire["id"])
    alternate_fire_id = str(truth["resource_options"]["alternate_route_fire_id"])
    blocked_fires = {
        point for point, fire_id in fire_by_point.items() if fire_id != alternate_fire_id
    }
    start = tuple(int(value) for value in tower["start"])
    resident = tuple(int(value) for value in tower["resident"])
    pending = deque([start])
    previous: dict[tuple[int, int, int], tuple[tuple[int, int, int], str] | None] = {start: None}
    for_position = ("UP", "RIGHT", "DOWN", "LEFT")
    while pending:
        position = pending.popleft()
        if position == resident:
            break
        for direction in for_position:
            target = _target(position, direction, width)
            if not 0 <= target[1] < floors or target in previous or target in walls or target in blocked_fires:
                continue
            if direction in {"UP", "DOWN"}:
                ladder_position = position if direction == "UP" else target
                if ladder_position not in ladders:
                    continue
            previous[target] = (position, direction)
            pending.append(target)
    assert resident in previous
    path: list[tuple[int, int, int]] = [resident]
    cursor = resident
    while previous[cursor] is not None:
        cursor, direction = previous[cursor]
        path.append(cursor)
    path.reverse()
    directions: list[str] = []
    for before, after in zip(path, path[1:]):
        for direction in ("UP", "RIGHT", "DOWN", "LEFT"):
            if _target(before, direction, width) == after:
                directions.append(direction)
                break
        else:
            raise AssertionError(f"could not recover direction for {before!r} -> {after!r}")
    actions: list[dict] = []
    for direction, target in zip(directions, path[1:]):
        actions.append({"action": "MOVE", "direction": direction})
        if fire_by_point.get(target) == alternate_fire_id:
            actions.append({"action": "EXTINGUISH", "direction": direction, "fire_id": alternate_fire_id})
            actions.append({"action": "MOVE", "direction": direction})
    return actions


@pytest.mark.parametrize("level", range(1, 6))
@pytest.mark.parametrize("interaction", ["full", "simplified"])
def test_controlled_worlds_are_deterministic_and_interaction_equivalent(level: int, interaction: str) -> None:
    public, truth = _generated(level, interaction, f"matrix-{level}")
    other_public, other_truth = _generated(
        level,
        "simplified" if interaction == "full" else "full",
        f"matrix-{level}",
    )
    assert public["tower"] == other_public["tower"]
    assert public["extinguisher_count"] == other_public["extinguisher_count"]
    assert truth["initial_tower"] == other_truth["initial_tower"]
    assert truth["solution_actions"] == other_truth["solution_actions"]
    assert public == _generated(level, interaction, f"matrix-{level}")[0]
    assert truth["control_condition"]["interaction"] == interaction
    assert public["asset_manifest"] == "shared_runtime/assets/provenance/firewatch_fold_v0.json"


@pytest.mark.parametrize("level", range(1, 6))
@pytest.mark.parametrize("interaction", ["full", "simplified"])
def test_solution_replay_and_surface_binding(level: int, interaction: str) -> None:
    public, truth = _generated(level, interaction, f"replay-{level}-{interaction}")
    payload = _solution_payload(public, truth)
    decision = GRADER.grade(payload, truth, public)
    assert decision["passed"], decision

    wrong_source = copy.deepcopy(payload)
    wrong_source["actions"][0]["input_source"] = (
        "control_buttons" if interaction == "full" else "keyboard"
    )
    assert GRADER.grade(wrong_source, truth, public)["passed"] is False

    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "stale-challenge"
    assert GRADER.grade(stale, truth, public)["passed"] is False

    altered_world = copy.deepcopy(public)
    altered_world["tower"]["palette"] = int(altered_world["tower"]["palette"]) + 1
    assert GRADER.grade(payload, truth, altered_world)["passed"] is False


def test_baseline_matches_l4_full_and_invalid_transcripts_fail() -> None:
    baseline_public, baseline_truth = _generated(None, "full", "baseline")
    controlled_public, controlled_truth = _generated(4, "full", "baseline")
    assert baseline_public["tower"] == controlled_public["tower"]
    assert baseline_truth["initial_tower"] == controlled_truth["initial_tower"]
    assert baseline_public["extinguisher_count"] == 4

    payload = _solution_payload(baseline_public, baseline_truth)
    missing_extinguish = copy.deepcopy(payload)
    missing_extinguish["actions"] = [
        event for event in missing_extinguish["actions"] if event["action"] != "EXTINGUISH"
    ]
    assert GRADER.grade(missing_extinguish, baseline_truth, baseline_public)["passed"] is False
    assert GRADER.grade({}, baseline_truth, baseline_public)["passed"] is False


@pytest.mark.parametrize("level", range(1, 6))
def test_each_level_has_nominal_route_budget_and_affordable_alternative(level: int) -> None:
    public, truth = _generated(level, "full", f"route-fire-invariant-{level}")
    route_objects = [
        fire
        for face in public["tower"]["faces"]
        for floor in face["floors"]
        for fire in floor.get("fires", [])
        if fire.get("kind") == "route"
    ]
    route_ids = [str(fire["id"]) for fire in route_objects]
    options = truth["resource_options"]
    assert len(route_ids) == options["route_fire_object_count"]
    assert int(truth["extinguisher_count"]) == level
    assert set(route_ids) == set(truth["route_fire_ids"])
    assert all("cells" not in fire and isinstance(fire.get("x"), int) for fire in route_objects)
    assert set(options) == {
        "alternate_route_available",
        "alternate_route_fire_clears",
        "alternate_route_move_count",
        "minimum_route_fire_clears",
        "alternate_route_fire_id",
        "canonical_route_fire_clears",
        "canonical_route_fire_ids",
        "route_fire_object_count",
        "canonical_route_move_count",
    }
    assert options["alternate_route_available"] is True
    assert options["alternate_route_fire_clears"] == 1
    assert options["minimum_route_fire_clears"] == 1
    assert options["canonical_route_fire_clears"] == level
    assert options["alternate_route_move_count"] > 0
    canonical_extinguishes = [
        str(action["fire_id"])
        for action in truth["solution_actions"]
        if action["action"] == "EXTINGUISH"
    ]
    assert canonical_extinguishes == options["canonical_route_fire_ids"]
    assert len(canonical_extinguishes) == level
    alternate_actions = _affordable_route_actions(public, truth)
    alternate_payload = _solution_payload(public, truth, alternate_actions)
    alternate_decision = GRADER.grade(alternate_payload, truth, public)
    assert alternate_decision["passed"] is True, alternate_decision
    assert alternate_payload["extinguishers_used"] == 1


def test_l1_does_not_require_face_inspection() -> None:
    public, truth = _generated(1, "full", "inspection-contract-1")
    payload = _solution_payload(public, truth)
    assert all(action["action"] != "INSPECT" for action in truth["solution_actions"])
    assert GRADER.grade(payload, truth, public)["passed"] is True


def test_exported_verifier_replays_independently(tmp_path: Path) -> None:
    public, truth = _generated(5, "simplified", "verifier")
    payload = _solution_payload(public, truth)
    verifier = _load(
        "firewatch_fold_verifier_test",
        ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "verifier.py",
    )
    exported = {"public_state": public, "ground_truth": truth, "result": payload}

    def copy_from_env(source: str, destination: str) -> None:
        assert source == "/tmp/task_result.json"
        Path(destination).write_text(json.dumps(exported), encoding="utf-8")

    result = verifier.verify_task(env_info={"copy_from_env": copy_from_env})
    assert result["passed"] is True, result


def test_controls_materialize_all_ten_tasks(tmp_path: Path) -> None:
    from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment

    written = materialize_environment(ENVIRONMENT, tmp_path / "environments")
    assert len(written) == 10
    assert {path.name for path in written} == {
        f"{MECHANIC}_d{level}_{interaction}_seed_0001"
        for level in range(1, 6)
        for interaction in ("full", "simplified")
    }


def test_registry_and_static_contracts() -> None:
    env = json.loads((ENVIRONMENT / "env.json").read_text(encoding="utf-8"))
    assert "time_mode" not in env["runner_options"]
    real_time = json.loads((BENCHMARK / "real_time.json").read_text(encoding="utf-8"))
    assert real_time["environments"][MECHANIC] == {
        "play_time_seconds": 180,
        "observation_window_ms": 0,
        "frames_per_observation": 1,
    }
    for hook in (
        ENVIRONMENT / "scripts" / "install_puzzle_runtime.sh",
        ENVIRONMENT / "scripts" / "setup_puzzle_runtime.sh",
    ):
        assert hook.is_file() and hook.stat().st_mode & 0o111
    manifest = json.loads((BENCHMARK / "benchmark_manifest.json").read_text(encoding="utf-8"))
    assert MECHANIC + "_env" in manifest["environments"]
    assert manifest["environment_count"] == len(manifest["environments"])
    assert (BENCHMARK / "shared_runtime" / "assets" / "provenance" / "firewatch_fold_v0.json").is_file()


@pytest.mark.parametrize("interaction", ["full", "simplified"])
def test_empty_extinguish_attempts_do_not_invalidate_rescue(interaction: str) -> None:
    public, truth = _generated(4, interaction, "recover-empty-extinguish")
    route = []
    for action in truth["solution_actions"]:
        route.append(action)
        if action["action"] == "EXTINGUISH":
            # The second attempt targets the same, now-cleared cell.
            route.append(copy.deepcopy(action))
    payload = _solution_payload(public, truth, route)
    assert sum(event["outcome"] == "no_fire" for event in payload["actions"]) == 4
    assert payload["extinguishers_used"] == 4
    assert GRADER.grade(payload, truth, public)["passed"] is True
    verifier = _load("firewatch_recovery_verifier", ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "verifier.py")
    packet = {"public_state": public, "ground_truth": truth, "result": payload}
    def copy_from_env(source: str, destination: str) -> None:
        Path(destination).write_text(json.dumps(packet), encoding="utf-8")
    assert verifier.verify_task(env_info={"copy_from_env": copy_from_env})["passed"] is True
    forged = copy.deepcopy(payload)
    forged["extinguishers_used"] += 1
    assert GRADER.grade(forged, truth, public)["passed"] is False


@pytest.mark.parametrize("value", [None, [], {}, "invalid"])
@pytest.mark.parametrize("action,field", [("MOVE", "direction"), ("INSPECT", "face")])
def test_malformed_action_fields_are_rejected(value, action: str, field: str) -> None:
    public, truth = _generated(4, "full", "malformed-fields")
    payload = _solution_payload(public, truth)
    event = next(item for item in payload["actions"] if item["action"] == action)
    event[field] = value
    assert GRADER.grade(payload, truth, public)["passed"] is False


@pytest.mark.parametrize("interaction", ["full", "simplified"])
def test_empty_stock_attempt_does_not_invalidate_reachable_rescue(interaction: str) -> None:
    public, truth = _generated(4, interaction, "stock-empty-0")
    original = _solution_payload(public, truth)
    _, _, _, fires = GRADER._index(public["tower"])
    for index, event in enumerate(original["actions"]):
        state = event["after"]
        if state["extinguishers_left"] != 0:
            continue
        for direction in GRADER.DIRECTIONS:
            target = _target(tuple(state["player"]), direction, public["tower"]["floor_width"])
            if any(target in cells and fire_id not in state["cleared_fires"] for fire_id, cells in fires.items()):
                route = copy.deepcopy(truth["solution_actions"])
                route[index + 1:index + 1] = [
                    {"action": "MOVE", "direction": direction},
                    {"action": "EXTINGUISH", "direction": direction},
                ]
                payload = _solution_payload(public, truth, route)
                assert payload["actions"][index + 1]["outcome"] == "blocked_fire"
                assert payload["actions"][index + 2]["outcome"] == "stock_empty"
                assert GRADER.grade(payload, truth, public)["passed"] is True
                return
    pytest.fail("fixture needs an adjacent uncleared fire after the stock is exhausted")
