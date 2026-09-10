from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "polarity_run"
ASSET_MANIFEST = "shared_runtime/assets/provenance/polarity_run_v0.json"

DEFAULT_PROFILES: dict[int, dict[str, Any]] = {
    1: {
        "barrier_count": 2,
        "gap_half": 145,
        "target_radius": 50,
        "ticks": 430,
        "polarity_change_budget": 18,
    },
    2: {
        "barrier_count": 3,
        "gap_half": 125,
        "target_radius": 46,
        "ticks": 430,
        "polarity_change_budget": 17,
    },
    3: {
        "barrier_count": 4,
        "gap_half": 105,
        "target_radius": 42,
        "ticks": 430,
        "polarity_change_budget": 16,
    },
    4: {
        "barrier_count": 5,
        "gap_half": 82,
        "target_radius": 38,
        "ticks": 425,
        "polarity_change_budget": 15,
    },
    5: {
        "barrier_count": 6,
        "gap_half": 64,
        "target_radius": 35,
        "ticks": 420,
        "polarity_change_budget": 14,
    },
}

_OPEN_LOOP_SCHEDULE = (
    (0, 1),
    (8, -1),
    (80, 0),
    (88, -1),
    (96, 1),
    (136, -1),
    (224, 1),
    (288, -1),
)
_BARRIER_X = (200.0, 360.0, 520.0, 680.0, 760.0, 815.0)
_FIELD_X = (130.0, 280.0, 430.0, 580.0, 730.0, 850.0)
_FIELD_Y = (150.0, 150.0, 370.0, 370.0, 150.0, 300.0)
_FIELD_Q = (1, -1, 1, -1, 1, -1)


def _seed_int(seed: str) -> int:
    return int(hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode("utf-8")).hexdigest()[:16], 16)


def _effective_condition(task: dict[str, Any]) -> dict[str, Any]:
    raw = dict(task.get("_control_condition") or {})
    if not raw:
        raw = {
            "difficulty": 3,
            "interaction": "full",
            "real_time": "live",
            "difficulty_parameters": copy.deepcopy(DEFAULT_PROFILES[3]),
        }
    difficulty = int(raw.get("difficulty", 3))
    if difficulty not in DEFAULT_PROFILES:
        raise ValueError("polarity difficulty must be 1 through 5")
    interaction = str(raw.get("interaction") or "")
    if interaction not in {"simplified", "full"}:
        raise ValueError("polarity interaction must be simplified or full")
    real_time = str(raw.get("real_time") or "")
    if real_time not in {"live", "paused"}:
        raise ValueError("polarity real_time must be live or paused")
    parameters = copy.deepcopy(DEFAULT_PROFILES[difficulty])
    parameters.update(dict(raw.get("difficulty_parameters") or {}))
    return {
        "difficulty": difficulty,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": parameters,
    }


def _identity(task: dict[str, Any], seed: str, condition: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], random.Random]:
    rng = random.Random(_seed_int(seed))
    task_id = str(task.get("id") or f"{MECHANIC_ID}_seed_0001@0.1")
    condition_tag = f"d{condition['difficulty']}|{condition['interaction']}|{condition['real_time']}"
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|{condition_tag}|{task_id}".encode("utf-8")).hexdigest()[:12]
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "asset_manifest": ASSET_MANIFEST,
        "prompt": task.get("natural_language") or "Guide the charged bead to the exit.",
        "control_condition": copy.deepcopy(condition),
    }
    truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "seed": seed,
        "control_condition": copy.deepcopy(condition),
    }
    return public, truth, rng


def _physics(parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "tick_ms": int(parameters.get("tick_ms", 40)),
        "ticks": int(parameters.get("ticks", 380)),
        "force_strength": float(parameters.get("force_strength", 0.5)),
        "influence_radius": float(parameters.get("influence_radius", 210.0)),
        "softening": float(parameters.get("softening", 80.0)),
        "integration": float(parameters.get("integration", 0.08)),
        "damping": float(parameters.get("damping", 0.992)),
        "max_speed": float(parameters.get("max_speed", 4.2)),
        "bead_radius": float(parameters.get("bead_radius", 10.0)),
        "world_padding": float(parameters.get("world_padding", 20.0)),
    }


def _force_step(body: dict[str, float], polarity: int, charges: list[dict[str, Any]], physics: dict[str, Any]) -> None:
    fx = 0.0
    fy = 0.0
    for charge in charges:
        dx = float(charge["x"]) - body["x"]
        dy = float(charge["y"]) - body["y"]
        distance = math.hypot(dx, dy)
        if distance <= 0.001 or distance >= float(physics["influence_radius"]):
            continue
        # Electric convention: equal signs repel and opposite signs attract.
        coefficient = -float(physics["force_strength"]) * polarity * int(charge["charge"])
        coefficient /= distance + float(physics["softening"])
        fx += coefficient * dx
        fy += coefficient * dy
    body["vx"] = (body["vx"] + fx * float(physics["integration"])) * float(physics["damping"])
    body["vy"] = (body["vy"] + fy * float(physics["integration"])) * float(physics["damping"])
    speed = math.hypot(body["vx"], body["vy"])
    if speed > float(physics["max_speed"]):
        scale = float(physics["max_speed"]) / speed
        body["vx"] *= scale
        body["vy"] *= scale
    body["x"] += body["vx"]
    body["y"] += body["vy"]


def _circle_hits_rect(body: dict[str, float], rect: dict[str, Any], radius: float) -> bool:
    left = float(rect["x"])
    top = float(rect["y"])
    right = left + float(rect["width"])
    bottom = top + float(rect["height"])
    closest_x = max(left, min(body["x"], right))
    closest_y = max(top, min(body["y"], bottom))
    return math.hypot(body["x"] - closest_x, body["y"] - closest_y) < radius


def _replay(
    initial: dict[str, Any],
    charges: list[dict[str, Any]],
    walls: list[dict[str, Any]],
    gates: list[dict[str, Any]],
    target: dict[str, Any],
    physics: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    collect_trace: bool = False,
) -> dict[str, Any]:
    body = {key: float(initial[key]) for key in ("x", "y", "vx", "vy")}
    polarity = 0
    event_index = 0
    gate_index = 0
    trace: list[dict[str, Any]] = []
    crossings: list[dict[str, Any]] = []
    completion_tick: int | None = None
    failure: str | None = None
    previous_x = body["x"]
    for tick in range(int(physics["ticks"])):
        while event_index < len(events) and int(events[event_index]["tick"]) == tick:
            polarity = int(events[event_index]["polarity"])
            event_index += 1
        _force_step(body, polarity, charges, physics)
        if collect_trace and (tick % 2 == 0 or tick < 12):
            trace.append({"tick": tick + 1, **{key: round(body[key], 4) for key in ("x", "y", "vx", "vy")}, "polarity": polarity})
        if not all(math.isfinite(body[key]) for key in ("x", "y", "vx", "vy")):
            failure = "non-finite bead state"
            break
        if body["y"] < float(physics["world_padding"]) or body["y"] > 480.0 - float(physics["world_padding"]):
            failure = "bead left the electric field chamber"
            break
        if any(_circle_hits_rect(body, wall, float(physics["bead_radius"])) for wall in walls):
            failure = "bead struck a maze rail"
            break
        if gate_index < len(gates) and previous_x < float(gates[gate_index]["x"]) <= body["x"]:
            gate = gates[gate_index]
            crossings.append({
                "tick": tick + 1,
                "gate_id": gate["id"],
                "x": round(body["x"], 4),
                "y": round(body["y"], 4),
                "polarity": polarity,
            })
            gate_index += 1
        previous_x = body["x"]
        if body["x"] >= float(target["x"]):
            if math.hypot(body["x"] - float(target["x"]), body["y"] - float(target["y"])) <= float(target["radius"]):
                completion_tick = tick + 1
                break
            failure = "bead passed the exit ring"
            break
    if completion_tick is None and failure is None:
        failure = "time expired"
    return {
        "body": {key: round(body[key], 5) for key in ("x", "y", "vx", "vy")},
        "crossings": crossings,
        "completion_tick": completion_tick,
        "failure": failure,
        "trace": trace,
        "gate_count": gate_index,
    }


def _open_trace(initial: dict[str, Any], charges: list[dict[str, Any]], physics: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _replay(initial, charges, [], [], {"x": 2000.0, "y": 240.0, "radius": 1.0}, physics, events, collect_trace=True)["trace"]


def _sample_y(trace: list[dict[str, Any]], x_value: float, fallback: float) -> float:
    if not trace:
        return fallback
    for sample in trace:
        if float(sample["x"]) >= x_value:
            return float(sample["y"])
    return float(trace[-1]["y"])


def _make_geometry(
    parameters: dict[str, Any],
    initial: dict[str, Any],
    charges: list[dict[str, Any]],
    physics: dict[str, Any],
    solution_events: list[dict[str, Any]],
    exit_target: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    barrier_count = int(parameters.get("barrier_count", 4))
    gap_half = float(parameters.get("gap_half", 105))
    preview = _open_trace(initial, charges, physics, solution_events)
    walls: list[dict[str, Any]] = []
    gates: list[dict[str, Any]] = []
    for index, x_value in enumerate(_BARRIER_X[:barrier_count]):
        center = max(75.0, min(405.0, _sample_y(preview, x_value + 8.0, initial["y"])))
        top_height = max(8.0, center - gap_half - 28.0)
        bottom_y = center + gap_half
        bottom_height = max(8.0, 452.0 - bottom_y)
        top_id = f"rail-{index + 1}-upper"
        bottom_id = f"rail-{index + 1}-lower"
        walls.extend((
            {"id": top_id, "x": x_value, "y": 28.0, "width": 16.0, "height": round(top_height, 3), "gate_id": f"gate-{index + 1}"},
            {"id": bottom_id, "x": x_value, "y": round(bottom_y, 3), "width": 16.0, "height": round(bottom_height, 3), "gate_id": f"gate-{index + 1}"},
        ))
        gates.append({
            "id": f"gate-{index + 1}",
            "x": x_value,
            "gap_center": round(center, 3),
            "gap_half": gap_half,
            "upper_wall_id": top_id,
            "lower_wall_id": bottom_id,
        })
    return walls, gates, preview


def generate(task: dict[str, Any], seed: str):
    condition = _effective_condition(task)
    public, truth, rng = _identity(task, seed, condition)
    parameters = dict(condition["difficulty_parameters"])
    physics = _physics(parameters)
    flip = rng.choice((-1, 1))
    field_shift = rng.choice((-10.0, -5.0, 0.0, 5.0, 10.0))
    start_shift = rng.choice((-12.0, -6.0, 0.0, 6.0, 12.0))
    start_y = 260.0 + start_shift
    charges = [
        {
            "id": f"pole-{index + 1}",
            "x": x,
            "y": round(y + (field_shift if index < 2 or index == 4 else -field_shift if index in {2, 3} else field_shift * 0.3), 3),
            "charge": int(q * flip),
            "radius": 12,
        }
        for index, (x, y, q) in enumerate(zip(_FIELD_X, _FIELD_Y, _FIELD_Q, strict=True))
    ]
    initial = {"x": 70.0, "y": start_y, "vx": 2.6, "vy": 0.0}
    solution_events = [
        {"tick": tick, "polarity": int(polarity * -flip)}
        for tick, polarity in _OPEN_LOOP_SCHEDULE
    ]
    preview = _open_trace(initial, charges, physics, solution_events)
    exit_y = _sample_y(preview, 850.0, 300.0)
    target = {
        "x": 858.0,
        "y": round(exit_y, 3),
        "radius": float(parameters.get("target_radius", 42)),
    }
    walls, gates, preview = _make_geometry(parameters, initial, charges, physics, solution_events, target)
    solved = _replay(initial, charges, walls, gates, target, physics, solution_events)
    if solved["completion_tick"] is None or solved["gate_count"] != len(gates):
        raise RuntimeError(f"polarity authoring route did not clear its generated maze: {solved}")
    palette = rng.choice(("aurora", "ember", "violet-night", "sea-glass"))
    public.update({
        "generator": {
            "name": "seeded_electrostatic_maze_v1",
            "variant_count": 50,
            "variant_count_scope": "physical worlds per fixed difficulty profile (2 signs × 5 field offsets × 5 start offsets)",
            "palette_count": 4,
            "world_palette_variant_count": 200,
            "variation": "field-sign, lane-offset, and start-offset",
        },
        "canvas": {"width": 900, "height": 480},
        "palette": palette,
        "initial_bead": {**initial, "radius": physics["bead_radius"]},
        "charges": charges,
        "walls": walls,
        "gates": gates,
        "target": target,
        "physics": physics,
        "ui": {
            "simplified_input": "polarity_button",
            "full_input": "polarity_dial_drag",
            "polarity_labels": {"-1": "−", "0": "0", "1": "+"},
        },
    })
    truth.update({
        "initial_bead": {**initial, "radius": physics["bead_radius"]},
        "charges": charges,
        "walls": walls,
        "gates": gates,
        "target": target,
        "physics": physics,
        "solution_events": solution_events,
        "solution_trace": solved["trace"],
        "solution_completion_tick": solved["completion_tick"],
        "preview_trace": preview,
        "max_events": int(parameters.get("polarity_change_budget", 16)),
    })
    return public, truth


def replay_solution(truth: dict[str, Any]) -> dict[str, Any]:
    return _replay(
        truth["initial_bead"],
        truth["charges"],
        truth["walls"],
        truth["gates"],
        truth["target"],
        truth["physics"],
        truth["solution_events"],
    )
