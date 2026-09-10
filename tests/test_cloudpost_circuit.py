from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import pytest

from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment


ROOT = Path(__file__).resolve().parents[1]
TASK_ROOT = ROOT / "weird_captcha_gym" / "environments" / "cloudpost_circuit_env" / "tasks"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load(
    ROOT / "weird_captcha_gym" / "shared_scripts" / "incubator_generators" / "cloudpost_circuit.py",
    "cloudpost_test_generator",
)
GRADER = _load(
    ROOT / "weird_captcha_gym" / "shared_runtime" / "server" / "incubator_graders" / "cloudpost_circuit.py",
    "cloudpost_test_grader",
)


@pytest.fixture
def controlled_tasks(tmp_path):
    generated = materialize_environment(TASK_ROOT.parent, tmp_path)
    return generated[0].parent


def _task(name: str, task_root: Path = TASK_ROOT) -> dict:
    return json.loads((task_root / name / "task.json").read_text(encoding="utf-8"))


def _step(plane: dict[str, float], control: tuple[float, float], physics: dict) -> None:
    yaw, pitch = control
    plane["yaw"] += max(-physics["turn_step"], min(physics["turn_step"], yaw * physics["max_yaw"] - plane["yaw"]))
    plane["pitch"] += max(-physics["turn_step"], min(physics["turn_step"], pitch * physics["max_pitch"] - plane["pitch"]))
    cp = math.cos(plane["pitch"])
    plane["x"] += math.sin(plane["yaw"]) * cp * physics["flight_speed"]
    plane["y"] += math.sin(plane["pitch"]) * physics["flight_speed"]
    plane["z"] += math.cos(plane["yaw"]) * cp * physics["flight_speed"]


def _route_payload(public: dict, truth: dict, source: str) -> dict:
    physics = public["physics"]
    plane = {key: float(public["initial_plane"][key]) for key in ("x", "y", "z", "yaw", "pitch")}
    events = []
    contacts = []
    control = (0.0, 0.0)
    target_index = 0
    collected: set[str] = set()
    for tick in range(1, 3001):
        target = public["targets"][target_index]
        dx = target["x"] - plane["x"]
        dy = target["y"] - plane["y"]
        dz = target["z"] - plane["z"]
        distance = max(1e-6, math.sqrt(dx * dx + dy * dy + dz * dz))
        control = (
            max(-1.0, min(1.0, math.atan2(dx, dz) / physics["max_yaw"])),
            max(-1.0, min(1.0, math.asin(max(-1.0, min(1.0, dy / distance))) / physics["max_pitch"])),
        )
        events.append({"seq": len(events) + 1, "type": "steer", "tick": tick - 1, "yaw": control[0], "pitch": control[1], "input_source": source})
        _step(plane, control, physics)
        newly_collected = []
        for candidate in public["targets"]:
            if candidate["id"] in collected:
                continue
            distance = math.dist((plane["x"], plane["y"], plane["z"]), (candidate["x"], candidate["y"], candidate["z"]))
            if distance <= physics["contact_radius"]:
                collected.add(candidate["id"])
                newly_collected.append((candidate, distance))
        for candidate, distance in newly_collected:
            contact = {
                "seq": len(events) + 1,
                "type": "contact",
                "tick": tick,
                "target_id": candidate["id"],
                "distance": round(distance, 4),
                "plane": {key: round(value, 4) for key, value in plane.items()},
            }
            events.append(contact)
            contacts.append(contact)
            target_index = len(collected)
        if len(collected) == len(public["targets"]):
            break
    assert len(collected) == len(public["targets"]), "generated route must be reachable for the replay fixture"
    terminal = {
        "seq": len(events) + 1,
        "type": "terminal",
        "tick": events[-1]["tick"],
        "completed": True,
        "collected": [item["target_id"] for item in contacts],
        "plane": {key: round(value, 4) for key, value in plane.items()},
    }
    events.append(terminal)
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction": "full" if source == "pointer_steer" else "simplified",
        "events": events,
        "contacts": contacts,
        "completed": True,
    }


def test_cloudpost_has_ten_controlled_task_variants_and_five_profiles(controlled_tasks):
    task_files = sorted(controlled_tasks.glob("cloudpost_circuit_d*/task.json"))
    assert len(task_files) == 10
    counts = {}
    for path in task_files:
        task = json.loads(path.read_text(encoding="utf-8"))
        condition = task["metadata"]["control_condition"]
        assert condition["difficulty"] in {1, 2, 3, 4, 5}
        assert condition["interaction"] in {"full", "simplified"}
        assert condition["real_time"] in {"live", "paused"}
        public, truth = GENERATOR.generate(task, "cloudpost-test-seed")
        counts.setdefault(condition["difficulty"], set()).add(len(public["targets"]))
        assert public["challenge_id"] == truth["challenge_id"]
        assert public["asset_manifest"].endswith("cloudpost_circuit_v0.json")
        assert "max_ticks" not in public["physics"]
        assert "max_ticks" not in condition["difficulty_parameters"]
    assert {level: next(iter(values)) for level, values in counts.items()} == {1: 2, 2: 3, 3: 4, 4: 5, 5: 7}


def test_baseline_is_d4_full_and_same_world_is_preserved(controlled_tasks):
    baseline = _task("cloudpost_circuit_seed_0001")
    controlled = _task("cloudpost_circuit_d4_full_seed_0001", controlled_tasks)
    baseline_public, baseline_truth = GENERATOR.generate(baseline, "same-world")
    controlled_public, controlled_truth = GENERATOR.generate(controlled, "same-world")
    assert baseline_public["targets"] == controlled_public["targets"]
    assert baseline_public["physics"] == controlled_public["physics"]
    assert baseline_truth["control_condition"] is None
    assert controlled_truth["control_condition"]["difficulty"] == 4
    assert controlled_truth["control_condition"]["interaction"] == "full"


def test_independent_replay_accepts_full_and_simplified_input_sources(controlled_tasks):
    for task_name, source in (
        ("cloudpost_circuit_d4_full_seed_0001", "pointer_steer"),
        ("cloudpost_circuit_d4_simplified_seed_0001", "trim_button"),
    ):
        task = _task(task_name, controlled_tasks)
        public, truth = GENERATOR.generate(task, "replay-seed")
        payload = _route_payload(public, truth, source)
        result = GRADER.grade(payload, truth, public)
        assert result["passed"], result
        wrong = dict(payload)
        wrong["events"] = [
            {**event, "input_source": "trim_button" if source == "pointer_steer" else "pointer_steer"}
            if event["type"] == "steer" else event
            for event in payload["events"]
        ]
        rejected = GRADER.grade(wrong, truth, public)
        assert rejected["passed"] is False


def test_solver_stops_on_visible_contact_despite_prediction_drift(monkeypatch, tmp_path):
    from types import SimpleNamespace

    solver = _load(
        ROOT / "weird_captcha_gym/tools/incubator_solvers/cloudpost_circuit.py",
        "cloudpost_stopping_test",
    )
    state, _ = GENERATOR.generate(_task("cloudpost_circuit_seed_0001"), "stopping-test")
    state["targets"] = [state["targets"][0]]
    monkeypatch.setattr(solver, "_read_public", lambda _: state)
    monkeypatch.setattr(solver, "_visible_tick", lambda _: 0)
    monkeypatch.setattr(solver, "_visible_count", lambda _: 1)
    monkeypatch.setattr(solver, "_full_step", lambda *args: 0)
    # No predicted movement: the estimate stays far outside the contact radius.
    page = SimpleNamespace(
        locator=lambda _: SimpleNamespace(
            bounding_box=lambda: {"x": 0, "y": 0, "width": 1920, "height": 1080},
            inner_text=lambda: "PASS",
        ),
        wait_for_timeout=lambda _: None,
    )
    solver.solve(page, tmp_path, tmp_path, "cloudpost_circuit")
