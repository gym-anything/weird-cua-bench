from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "tiny_fps_customs_env"
MECHANIC = "tiny_fps_customs"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = _load_module("tiny_fps_controls_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = _load_module(
    "tiny_fps_controls_materializer",
    BENCHMARK / "tools" / "materialize_controlled_tasks.py",
)
GRADER = _load_module(
    "tiny_fps_controls_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py",
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _task(level: int, interaction: str) -> dict:
    controls = _read(ENVIRONMENT / "controls.json")
    base = _read(ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json")
    return MATERIALIZER.controlled_task(
        base,
        mechanic_id=MECHANIC,
        level=level,
        interaction=interaction,
        profile=controls["difficulty"][str(level)],
        task_dir_name=f"{MECHANIC}_d{level}_{interaction}_seed_0001",
    )


def _without_control_identity(value: dict) -> dict:
    value = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        value.pop(key, None)
    return value


def _round_pose(value: float) -> float:
    return round(value, 6)


def _controlled_solution_payload(public: dict, truth: dict, interaction: str) -> dict:
    """Replay the issued route with the same primitive actions as the UI."""
    actions: list[dict] = []
    pose = {
        "x": float(truth["initial_pose"]["x"]),
        "y": float(truth["initial_pose"]["y"]),
        "angle_mdeg": int(truth["initial_pose"]["angle_mdeg"]),
    }
    alive = {str(creature["id"]): creature for creature in truth["creatures"]}
    ammo = int(truth["ammo"])
    hit_ledger: list[dict] = []
    move_count = turn_count = shot_count = 0

    def record(action: dict) -> None:
        action["seq"] = len(actions) + 1
        action["t_ms"] = len(actions)
        action["input_surface"] = interaction
        actions.append(action)

    def turn_to(target_angle: int) -> None:
        nonlocal turn_count
        target_angle %= 360_000
        delta = ((target_angle - pose["angle_mdeg"] + 180_000) % 360_000) - 180_000
        assert delta % 15_000 == 0
        direction = 15_000 if delta > 0 else -15_000
        for _ in range(abs(delta) // 15_000):
            before = pose["angle_mdeg"]
            pose["angle_mdeg"] = (before + direction) % 360_000
            record({
                "type": "turn",
                "delta_mdeg": direction,
                "before_mdeg": before,
                "after_mdeg": pose["angle_mdeg"],
            })
            turn_count += 1

    def step_forward() -> None:
        nonlocal move_count
        before = dict(pose)
        angle = math.radians(pose["angle_mdeg"] / 1_000)
        pose["x"] = _round_pose(pose["x"] + math.cos(angle) * float(truth["move_step"]))
        pose["y"] = _round_pose(pose["y"] + math.sin(angle) * float(truth["move_step"]))
        record({
            "type": "move",
            "forward": 1,
            "strafe": 0,
            "from": before,
            "to": dict(pose),
            "blocked_x": False,
            "blocked_y": False,
        })
        move_count += 1

    for segment in truth["solver_plan"]:
        route = segment["route_cells"]
        for origin, destination in zip(route, route[1:]):
            dx = int(destination["x"]) - int(origin["x"])
            dy = int(destination["y"]) - int(origin["y"])
            desired_angle = {(1, 0): 0, (0, 1): 90_000, (-1, 0): 180_000, (0, -1): 270_000}[(dx, dy)]
            turn_to(desired_angle)
            for _ in range(4):
                step_forward()
        turn_to(int(segment["aim_mdeg"]))
        origin = dict(pose)
        ammo_before = ammo
        ammo -= 1
        outcome, hit_id, distance = GRADER._shot_result(
            truth["map"], alive, set(alive), pose["x"], pose["y"], pose["angle_mdeg"], float(truth["creature_radius"])
        )
        assert outcome == "creature" and hit_id == segment["target_id"]
        alive.pop(hit_id)
        shot_count += 1
        hit_ledger.append({"shot": shot_count, "creature_id": hit_id})
        record({
            "type": "shot",
            "origin": origin,
            "ammo_before": ammo_before,
            "ammo_after": ammo,
            "outcome": outcome,
            "hit_id": hit_id,
            "distance": round(distance, 6),
        })

    return {
        "mechanic_id": MECHANIC,
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "control_condition": public["control_condition"],
        "interaction_mode": interaction,
        "actions": actions,
        "completed": True,
        "final_pose": pose,
        "ammo_remaining": ammo,
        "eliminated_ids": [item["creature_id"] for item in hit_ledger],
        "protected_survivors": len(truth["protected_ids"]),
        "hit_ledger": hit_ledger,
        "interaction_counts": {
            "moves": move_count,
            "turns": turn_count,
            "shots": shot_count,
            "collisions": 0,
            "resets": 0,
        },
    }


def test_tiny_fps_profiles_preserve_l4_and_interaction_keeps_the_world() -> None:
    controls = _read(ENVIRONMENT / "controls.json")
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert [controls["difficulty"][str(level)]["parameters"]["wanted_count"] for level in range(1, 6)] == [2, 3, 3, 4, 5]
    assert [controls["difficulty"][str(level)]["parameters"]["decoy_trait_differences"] for level in range(1, 6)] == [3, 2, 1, 1, 1]

    base = _read(ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json")
    original_public, original_truth = SETUP.generate_task_state(base, "tiny-fps-l4-reference")
    l4_public, l4_truth = SETUP.generate_task_state(_task(4, "full"), "tiny-fps-l4-reference")
    assert _without_control_identity(l4_public) == _without_control_identity(original_public)
    assert _without_control_identity(l4_truth) == _without_control_identity(original_truth)

    simplified_public, simplified_truth = SETUP.generate_task_state(_task(4, "simplified"), "tiny-fps-pair")
    full_public, full_truth = SETUP.generate_task_state(_task(4, "full"), "tiny-fps-pair")
    assert _without_control_identity(simplified_public) == _without_control_identity(full_public)
    assert _without_control_identity(simplified_truth) == _without_control_identity(full_truth)


def test_tiny_fps_grader_rejects_the_other_input_surface() -> None:
    public, truth = SETUP.generate_task_state(_task(4, "simplified"), "tiny-fps-input-surface")
    initial = truth["initial_pose"]
    payload = {
        "mechanic_id": MECHANIC,
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "control_condition": public["control_condition"],
        "interaction_mode": "simplified",
        "actions": [{
            "seq": 1,
            "t_ms": 0,
            "type": "reset",
            "input_surface": "full",
            "pose": initial,
            "ammo": public["ammo"],
        }],
    }
    outcome = GRADER.grade(payload, truth, public)
    assert outcome["passed"] is False
    assert outcome["feedback"] == "customs action uses the wrong interaction input"


def test_tiny_fps_grader_accepts_all_ten_controlled_profiles() -> None:
    for level in range(1, 6):
        for interaction in ("simplified", "full"):
            public, truth = SETUP.generate_task_state(
                _task(level, interaction), f"tiny-fps-all-profiles-{level}-{interaction}"
            )
            payload = _controlled_solution_payload(public, truth, interaction)
            outcome = GRADER.grade(payload, truth, public)
            assert outcome["passed"] is True, outcome
