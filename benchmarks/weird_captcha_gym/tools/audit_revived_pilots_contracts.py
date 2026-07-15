#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import math
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
BENCH_ROOT = ROOT / "benchmarks" / "weird_captcha_gym"


def load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def task(mechanic: str) -> dict[str, Any]:
    path = BENCH_ROOT / "environments" / f"{mechanic}_env" / "tasks" / f"{mechanic}_seed_0001" / "task.json"
    return json.loads(path.read_text(encoding="utf-8"))


def event(events: list[dict[str, Any]], kind: str, **details: Any) -> None:
    events.append({"seq": len(events) + 1, "type": kind, **details})


def solve_scroll(public: dict[str, Any], truth: dict[str, Any], grader: ModuleType) -> dict[str, Any]:
    scene = truth["scene"]
    physics = truth["physics"]
    offsets = list(scene["initial_offsets"])
    events: list[dict[str, Any]] = []
    for shaft, target in enumerate(truth["solution_offsets"]):
        while offsets[shaft] != target:
            before = offsets[shaft]
            delta = int(scene["offset_step"]) if target > before else -int(scene["offset_step"])
            offsets[shaft] = before + delta
            event(events, "scroll", shaft=shaft, delta=delta, before=before, after=offsets[shaft])

    body = {**scene["target"], "captured": False}
    cursor = {"active": False, "x": 0, "y": 0}
    tick = 0

    def drive(goal_x: float, goal_y: float, tolerance: float, maximum: int) -> None:
        nonlocal body, cursor, tick
        for _ in range(maximum):
            if body["captured"]:
                return
            ex = goal_x - body["x"]
            ey = goal_y - body["y"]
            if math.hypot(ex, ey) <= tolerance and abs(body["vx"]) <= 2 and abs(body["vy"]) <= 2:
                return
            desired_vx = max(-5.0, min(5.0, ex * 0.12))
            desired_vy = max(-5.0, min(5.0, ey * 0.12))
            ax = desired_vx - body["vx"] * 0.92
            ay = desired_vy - body["vy"] * 0.92
            if abs(ax) < 0.45 and abs(ay) < 0.45:
                cursor = {
                    "active": True,
                    "x": 1000 if body["x"] < 500 else 0,
                    "y": 520 if body["y"] < 260 else 0,
                }
            else:
                sx = 0 if abs(ax) < 0.45 else (1 if ax > 0 else -1)
                sy = 0 if abs(ay) < 0.45 else (1 if ay > 0 else -1)
                distance = 58 if sx and sy else 70
                cursor = {
                    "active": True,
                    "x": max(0, min(1000, body["x"] - sx * distance)),
                    "y": max(0, min(520, body["y"] - sy * distance)),
                }
            event(events, "cursor", **cursor)
            body, _crossings = grader._step(body, cursor, offsets, scene, physics)
            tick += 1
            event(events, "tick", tick=tick, body=dict(body))
        raise AssertionError(f"scroll controller missed {goal_x},{goal_y}: {body}")

    for index, boundary in enumerate(scene["boundaries"]):
        route_y = truth["route_screen_y"][index]
        drive(int(boundary["x"]) - 48, route_y, 7, 650)
        drive(int(boundary["x"]) + 49, route_y, 8, 650)
    drive(scene["clamp"]["x"], scene["clamp"]["y"], 6, 900)
    if not body["captured"]:
        raise AssertionError("scroll body did not enter clamp")
    event(events, "check", checked=True, body=dict(body))
    event(events, "verify", tick=tick, offsets=list(offsets), body=dict(body), checked=True)
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": events,
        "completed": True,
    }


def solve_tabs(public: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for station in range(4):
        event(events, "deploy", station=station, deployed_count=station + 1)
    physics = truth["physics"]
    for index, stage in enumerate(truth["stages"]):
        station = int(stage["station"])
        direction = 1 if int(stage["pulse_speed_deg_per_tick"]) > 0 else -1
        pulse = int(stage["pulse_start_deg"])
        receiver = int(stage["receiver_initial_deg"])
        charge = 0
        event(events, "focus", station=station)
        event(events, "key", stage=index, station=station, before=0, after=direction)
        event(events, "contact", stage=index, station=station, before=False, after=True)
        for tick in range(1, int(physics["maximum_ticks_per_stage"]) + 1):
            pulse = (pulse + int(stage["pulse_speed_deg_per_tick"])) % 360
            receiver = (receiver + direction * int(physics["receiver_control_deg_per_tick"])) % 360
            phase_error = abs((receiver - pulse + 180) % 360 - 180)
            locked = direction == (1 if int(stage["pulse_speed_deg_per_tick"]) > 0 else -1) and phase_error <= int(physics["capture_tolerance_deg"])
            if locked:
                receiver = pulse
                phase_error = 0
                charge += 1
            else:
                charge = max(0, charge - int(physics["charge_decay_per_tick"]))
            event(events, "tick", stage=index, station=station, tick=tick, state={
                "pulse_deg": pulse,
                "receiver_deg": receiver,
                "error_deg": phase_error,
                "charge": charge,
                "locked": locked,
                "direction": direction,
                "contact": True,
            })
            if charge >= int(physics["hold_ticks"]):
                event(events, "relay", stage=index, station=station, tick=tick, charge=charge,
                      next_station=truth["stages"][index + 1]["station"] if index + 1 < len(truth["stages"]) else None)
                break
        else:
            raise AssertionError(f"tab stage {index} never phase-locked")
    event(events, "verify", completed_stages=8, deployed=[0, 1, 2, 3])
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": events,
        "completed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-seed deterministic and adversarial audit for the rebuilt pilots.")
    parser.add_argument("--seeds", type=int, default=64)
    parser.add_argument("--output", type=Path, default=BENCH_ROOT / "evidence" / "incubator_batch_revived_v1" / "contract-audit.json")
    args = parser.parse_args()
    mechanics = ("moving_checkbox_evasive_button", "reverse_identity_gate")
    output: dict[str, Any] = {"ok": True, "seed_count": args.seeds, "mechanics": {}}
    for mechanic in mechanics:
        generator = load(BENCH_ROOT / "shared_scripts" / "incubator_generators" / f"{mechanic}.py", f"{mechanic}_audit_generator")
        grader = load(BENCH_ROOT / "shared_runtime" / "server" / "incubator_graders" / f"{mechanic}.py", f"{mechanic}_audit_grader")
        max_events = 0
        max_ticks = 0
        for index in range(args.seeds):
            seed = f"revived-contract-audit-{index:04d}"
            public, truth = generator.generate(task(mechanic), seed)
            repeated_public, repeated_truth = generator.generate(task(mechanic), seed)
            if public != repeated_public or truth != repeated_truth:
                raise AssertionError(f"{mechanic} seed {index} is nondeterministic")
            payload = solve_scroll(public, truth, grader) if mechanic.startswith("moving") else solve_tabs(public, truth)
            decision = grader.grade(payload, truth, public)
            if decision.get("passed") is not True:
                raise AssertionError(f"{mechanic} seed {index} clean solve rejected: {decision}")
            stale = copy.deepcopy(payload)
            stale["challenge_id"] = "stale-challenge"
            if grader.grade(stale, truth, public).get("passed") is True:
                raise AssertionError(f"{mechanic} seed {index} accepted stale challenge")
            forged = copy.deepcopy(payload)
            tick_event = next(item for item in forged["events"] if item["type"] == "tick")
            if mechanic.startswith("moving"):
                tick_event["body"]["x"] += 1
            else:
                tick_event["state"]["charge"] += 1
            if grader.grade(forged, truth, public).get("passed") is True:
                raise AssertionError(f"{mechanic} seed {index} accepted forged replay state")
            max_events = max(max_events, len(payload["events"]))
            max_ticks = max(max_ticks, sum(item["type"] == "tick" for item in payload["events"]))
        output["mechanics"][mechanic] = {
            "ok": True,
            "deterministic_seeds": args.seeds,
            "clean_passes": args.seeds,
            "stale_rejections": args.seeds,
            "forged_state_rejections": args.seeds,
            "maximum_events": max_events,
            "maximum_ticks": max_ticks,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
