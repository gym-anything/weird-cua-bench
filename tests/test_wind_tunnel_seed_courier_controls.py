from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = "wind_tunnel_seed_courier_env"
MECHANIC = "wind_tunnel_seed_courier"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = _load_module("wind_control_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = _load_module(
    "wind_control_materializer", BENCHMARK / "tools" / "materialize_controlled_tasks.py"
)
GRADER = _load_module(
    "wind_control_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py",
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


CONTROLS = _read(BENCHMARK / "environments" / ENVIRONMENT / "controls.json")
BASE_TASK = _read(
    BENCHMARK / "environments" / ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json"
)


def _task(level: int, interaction: str) -> dict:
    return MATERIALIZER.controlled_task(
        BASE_TASK,
        mechanic_id=MECHANIC,
        level=level,
        interaction=interaction,
        profile=CONTROLS["difficulty"][str(level)],
        task_dir_name=f"{MECHANIC}_d{level}_{interaction}_seed_0001",
    )


def _without_control_identity(value: dict) -> dict:
    result = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        result.pop(key, None)
    return result


def _append(events: list[dict], event_type: str, **details: object) -> None:
    events.append({"seq": len(events) + 1, "type": event_type, **details})


def _passing_payload(public: dict, truth: dict, source: str) -> dict:
    """Produce the same event ledger as visible fan controls, then replay it locally."""
    physics = public["physics"]
    plan: dict[int, list[dict]] = {}
    for item in truth["plan"]:
        plan.setdefault(int(item["tick"]), []).append(item)
    events: list[dict] = []
    _append(events, "launch", tick=0, powers=[0 for _ in public["fans"]])

    powers = [0 for _ in public["fans"]]
    actual = [0.0 for _ in public["fans"]]
    heat = [0.0 for _ in public["fans"]]
    pods = [
        {
            **item,
            "x": float(item["x"]),
            "y": float(item["y"]),
            "vx": float(item["vx"]),
            "vy": float(item["vy"]),
            "docked": False,
        }
        for item in public["pods"]
    ]
    passed = {pod["id"]: [] for pod in pods}
    for tick in range(int(physics["ticks"])):
        for item in plan.get(tick, []):
            fan = int(item["fan"])
            power = int(item["power"])
            powers[fan] = power
            _append(events, "fan_control", tick=tick, fan=fan, power=power, input_source=source)
        before_x = {pod["id"]: pod["x"] for pod in pods}
        accelerations = [
            0.006 * math.sin(tick * 0.083 + float(physics["phase"]) + float(pod["gust_phase"]))
            for pod in pods
        ]
        for index, fan in enumerate(public["fans"]):
            heat[index] = max(
                0.0,
                heat[index]
                + (float(physics["heat_rate"]) if powers[index] else -float(physics["cool_rate"])),
            )
            assert heat[index] < float(physics["trip_heat"])
            actual[index] += (powers[index] - actual[index]) * float(physics["spool_rate"])
            for pod_index, pod in enumerate(pods):
                if pod["docked"]:
                    continue
                influence = max(0.0, 1.0 - abs(pod["x"] - float(fan["x"])) / float(fan["radius"]))
                accelerations[pod_index] += (
                    actual[index]
                    * float(physics["fan_accel"])
                    * float(pod["response"])
                    * influence
                )
        current_tick = tick + 1
        for pod_index, pod in enumerate(pods):
            if pod["docked"]:
                continue
            pod["vy"] = (pod["vy"] + accelerations[pod_index]) * float(physics["drag"])
            pod["y"] = max(35.0, min(441.0, pod["y"] + pod["vy"]))
            pod["x"] += pod["vx"]
            next_gate = public["gates"][len(passed[pod["id"]])] if len(passed[pod["id"]]) < len(public["gates"]) else None
            if next_gate and before_x[pod["id"]] < float(next_gate["x"]) <= pod["x"]:
                slot = next(item for item in next_gate["slots"] if item["pod_id"] == pod["id"])
                gate_y = GRADER._gate_y(slot, current_tick)
                assert abs(pod["y"] - gate_y) + float(physics["pod_radius"]) <= float(slot["half_gap"])
                passed[pod["id"]].append(next_gate["id"])
                _append(
                    events,
                    "gate_pass",
                    tick=current_tick,
                    pod_id=pod["id"],
                    gate_id=next_gate["id"],
                    gate_y=round(gate_y, 3),
                    y=round(pod["y"], 3),
                    vy=round(pod["vy"], 3),
                )
            dock = next(item for item in public["docks"] if item["pod_id"] == pod["id"])
            if before_x[pod["id"]] < float(dock["x"]) <= pod["x"]:
                assert len(passed[pod["id"]]) == len(public["gates"])
                assert math.hypot(pod["x"] - float(dock["x"]), pod["y"] - float(dock["y"])) <= float(dock["radius"]) + 4
                pod["docked"] = True
                pod["x"] = float(dock["x"])
                _append(events, "dock", tick=current_tick, pod_id=pod["id"], pod=dict(pod), gates=list(passed[pod["id"]]))
        if all(pod["docked"] for pod in pods):
            _append(events, "terminal", tick=current_tick, passed=True, pods=copy.deepcopy(pods), gates=copy.deepcopy(passed))
            return {
                "mechanic_id": public["mechanic_id"],
                "task_id": public["task_id"],
                "challenge_id": public["challenge_id"],
                "events": events,
                "completed": True,
            }
    raise AssertionError("authored wind plan did not dock every pod")


def test_wind_tunnel_profiles_preserve_l4_and_bind_both_input_surfaces() -> None:
    assert CONTROLS["baseline"] == {"difficulty": 4, "interaction": "simplified", "real_time": "live"}
    assert CONTROLS["real_time"] == {
        "play_time_seconds": 180,
        "observation_window_ms": 600,
        "frames_per_observation": 5,
    }
    assert BASE_TASK["natural_language"] == CONTROLS["difficulty"]["4"]["natural_language"]

    for seed in ("wind-l4-preservation-a", "wind-l4-preservation-b"):
        original_public, original_truth = SETUP.generate_task_state(BASE_TASK, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(_task(4, "simplified"), seed)
        assert _without_control_identity(baseline_public) == _without_control_identity(original_public)
        assert _without_control_identity(baseline_truth) == _without_control_identity(original_truth)

    for level in range(1, 6):
        parameters = CONTROLS["difficulty"][str(level)]["parameters"]
        simplified_public, simplified_truth = SETUP.generate_task_state(
            _task(level, "simplified"), f"wind-profile-{level}"
        )
        full_public, full_truth = SETUP.generate_task_state(
            _task(level, "full"), f"wind-profile-{level}"
        )
        assert _without_control_identity(simplified_public) == _without_control_identity(full_public)
        assert _without_control_identity(simplified_truth) == _without_control_identity(full_truth)
        assert len(simplified_public["pods"]) == parameters["pod_count"]
        assert len(simplified_public["fans"]) == parameters["fan_count"]
        assert len(simplified_public["gates"]) == parameters["gate_count"]
        assert all(len(gate["slots"]) == parameters["pod_count"] for gate in simplified_public["gates"])
        for key in ("tick_ms", "ticks", "fan_accel", "drag", "pod_radius", "spool_rate", "heat_rate", "cool_rate", "trip_heat"):
            assert simplified_public["physics"][key] == parameters[key]
        assert all(slot["half_gap"] == parameters["gate_half_gap"] for gate in simplified_public["gates"] for slot in gate["slots"])

        for source, public, truth in (
            ("fan_button", simplified_public, simplified_truth),
            ("fan_lever_drag", full_public, full_truth),
        ):
            payload = _passing_payload(public, truth, source)
            assert GRADER.grade(payload, truth, public)["passed"] is True
            wrong_surface = copy.deepcopy(payload)
            next(item for item in wrong_surface["events"] if item["type"] == "fan_control")["input_source"] = (
                "fan_lever_drag" if source == "fan_button" else "fan_button"
            )
            rejected = GRADER.grade(wrong_surface, truth, public)
            assert rejected["passed"] is False
            assert rejected["feedback"] == "fan control uses the wrong interaction input"

    renderer = (BENCHMARK / "shared_runtime" / "app" / "mechanics" / "_interaction_vii_viii.js").read_text(encoding="utf-8")
    assert 'state.control_condition?.interaction || "simplified"' in renderer
    assert '"fan_button"' in renderer
    assert '"fan_lever_drag"' in renderer
    assert 'const proxyNote = state.pods.length === 1' in renderer
    assert 'THE ${state.fans.length} LEVER${state.fans.length === 1 ? "" : "S"}' in renderer
