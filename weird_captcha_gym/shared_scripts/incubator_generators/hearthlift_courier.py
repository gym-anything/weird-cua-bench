"""Generate the original Hearthlift Courier voxel transport puzzle.

The source-grounded mechanic is the relationship between box placement,
climbable voxel stacks, and a fire endpoint.  The benchmark construction is a
small deterministic grid world: the browser renders the cells and boxes as
isometric voxels, while the grader replays the same discrete movement,
push/climb, pickup/drop, and camera-input contract independently.
"""

from __future__ import annotations

import copy
import hashlib
import json
import random
from typing import Any


MECHANIC_ID = "hearthlift_courier"
ASSET_MANIFEST = "shared_runtime/assets/provenance/hearthlift_courier_v0.json"
VARIANT_COUNT = 8 * 5 * 4 * 3 * 10_000

DEFAULT_PARAMETERS: dict[str, Any] = {
    "stage_count": 4,
    "decoy_count": 3,
    "turn_count": 3,
    "stack_height": 4,
    "camera_obscurity": 0.72,
    "cargo_detour": 1,
}

DIRECTIONS = {
    "N": (0, -1),
    "E": (1, 0),
    "S": (0, 1),
    "W": (-1, 0),
}


def _rng(seed: str) -> random.Random:
    raw = hashlib.sha256(f"{MECHANIC_ID}|{seed}|voxel-v1".encode("utf-8")).digest()
    return random.Random(int.from_bytes(raw[:8], "big"))


def _key(x: int, y: int) -> str:
    return f"{int(x)},{int(y)}"


def _copy_state(state: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(state)


def _box_at(state: dict[str, Any], x: int, y: int) -> dict[str, Any] | None:
    for box in state["boxes"]:
        if int(box["x"]) == int(x) and int(box["y"]) == int(y):
            return box
    return None


def _cell(world: dict[str, Any], x: int, y: int) -> dict[str, Any] | None:
    return world["cell_map"].get(_key(x, y))


def _snapshot(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "avatar": copy.deepcopy(state["avatar"]),
        "boxes": copy.deepcopy(state["boxes"]),
        "held": state.get("held"),
        "delivered": bool(state.get("delivered")),
    }


def _apply_action(world: dict[str, Any], state: dict[str, Any], action: dict[str, Any]) -> None:
    """Apply an oracle action while constructing the hidden solution transcript."""
    action_type = str(action.get("type") or "")
    if action_type == "camera":
        state["camera_yaw"] = round(float(state.get("camera_yaw", 0.0)) + float(action.get("delta", 0.0)), 4)
        return
    if action_type == "move":
        direction = str(action.get("direction") or "")
        if direction not in DIRECTIONS:
            raise ValueError(f"unknown direction {direction}")
        dx, dy = DIRECTIONS[direction]
        avatar = state["avatar"]
        tx, ty = int(avatar["x"]) + dx, int(avatar["y"]) + dy
        cell = _cell(world, tx, ty)
        if cell is None:
            raise ValueError(f"oracle walked off the voxel garden at {(tx, ty)}")
        box = _box_at(state, tx, ty)
        if box is not None:
            top = int(cell["height"]) + 1
            if int(avatar["z"]) == top:
                avatar.update({"x": tx, "y": ty, "z": top})
                return
            if state.get("held") is not None:
                raise ValueError("oracle tried to move through a box while carrying cargo")
            dest = _cell(world, tx + dx, ty + dy)
            if (
                dest is None
                or _box_at(state, tx + dx, ty + dy) is not None
                or int(cell["height"]) != int(avatar["z"])
                or int(dest["height"]) != int(avatar["z"])
                or str(box.get("kind")) == "cargo"
            ):
                raise ValueError("oracle push is not legal")
            box.update({"x": tx + dx, "y": ty + dy, "base_z": int(dest["height"])})
            avatar.update({"x": tx, "y": ty, "z": int(cell["height"])})
            return
        if abs(int(cell["height"]) - int(avatar["z"])) > 1:
            raise ValueError("oracle attempted an unsupported height change")
        avatar.update({"x": tx, "y": ty, "z": int(cell["height"])})
        return
    if action_type == "climb":
        avatar = state["avatar"]
        direction = str(action.get("direction") or "E")
        if direction not in DIRECTIONS:
            raise ValueError("oracle climb direction is invalid")
        dx, dy = DIRECTIONS[direction]
        tx, ty = int(avatar["x"]) + dx, int(avatar["y"]) + dy
        cell = _cell(world, tx, ty)
        box = _box_at(state, tx, ty)
        if cell is None or box is None or int(cell["height"]) != int(avatar["z"]):
            raise ValueError("oracle climb has no adjacent box at the current level")
        avatar.update({"x": tx, "y": ty, "z": int(cell["height"]) + 1})
        return
    if action_type == "pickup":
        if state.get("held") is not None:
            raise ValueError("oracle picked up while already carrying")
        avatar = state["avatar"]
        cargo = next((box for box in state["boxes"] if box.get("kind") == "cargo"), None)
        if cargo is None or abs(int(cargo["x"]) - int(avatar["x"])) + abs(int(cargo["y"]) - int(avatar["y"])) != 1 or int(cargo["base_z"]) != int(avatar["z"]):
            raise ValueError("oracle cargo pickup is not adjacent")
        state["held"] = str(cargo["id"])
        state["boxes"] = [box for box in state["boxes"] if box is not cargo]
        return
    if action_type == "drop":
        avatar = state["avatar"]
        hearth = world["hearth"]
        if state.get("held") is None or [int(avatar["x"]), int(avatar["y"])] != [int(hearth["x"]), int(hearth["y"])] or int(avatar["z"]) != int(hearth["height"]):
            raise ValueError("oracle cargo drop is not at the hearth")
        state["held"] = None
        state["delivered"] = True
        return
    raise ValueError(f"unknown oracle action {action_type}")


def _event_transcript(world: dict[str, Any], actions: list[dict[str, Any]], interaction: str) -> list[dict[str, Any]]:
    state = {
        "avatar": copy.deepcopy(world["avatar_start"]),
        "boxes": copy.deepcopy(world["boxes"]),
        "held": None,
        "delivered": False,
        "camera_yaw": float(world["camera"]["initial_yaw"]),
    }
    events: list[dict[str, Any]] = []
    for seq, action in enumerate(actions, 1):
        before = _snapshot(state)
        camera_before = round(float(state["camera_yaw"]), 4)
        _apply_action(world, state, action)
        after = _snapshot(state)
        event = {
            "seq": seq,
            "type": action["type"],
            "input_source": (
                "camera_drag" if action["type"] == "camera" and interaction == "full" else
                "camera_button" if action["type"] == "camera" else
                "keyboard_move" if action["type"] == "move" and interaction == "full" else
                "proxy_move" if action["type"] == "move" else
                "keyboard_action" if interaction == "full" else "proxy_action"
            ),
            "before": before,
            "after": after,
        }
        if action["type"] == "camera":
            event.update({"delta": round(float(action.get("delta", 0.0)), 4), "camera_before": camera_before, "camera_after": round(float(state["camera_yaw"]), 4)})
        else:
            if "direction" in action:
                event["direction"] = action["direction"]
        events.append(event)
    events.append({
        "seq": len(events) + 1,
        "type": "certify",
        "input_source": "certify_button",
        "before": _snapshot(state),
        "after": _snapshot(state),
    })
    return events


def _direction(first: tuple[int, int], second: tuple[int, int]) -> str:
    dx = int(second[0]) - int(first[0])
    dy = int(second[1]) - int(first[1])
    for name, vector in DIRECTIONS.items():
        if (dx, dy) == vector:
            return name
    raise ValueError(f"non-adjacent route cells: {first} -> {second}")


def _build_world(seed: str, parameters: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], str]:
    rng = _rng(seed)
    stage_count = int(parameters["stage_count"])
    decoy_count = int(parameters["decoy_count"])
    turn_count = int(parameters["turn_count"])
    stack_height = int(parameters["stack_height"])
    cargo_detour = int(parameters["cargo_detour"])
    if not 2 <= stage_count <= 5 or not 0 <= decoy_count <= 5 or not 0 <= turn_count <= 4:
        raise ValueError("hearthlift profile is outside the supported range")

    cells: dict[str, dict[str, Any]] = {}
    route: list[tuple[int, int]] = []
    stages: list[dict[str, Any]] = []
    boxes: list[dict[str, Any]] = []
    x, y = 1, 2

    def add_cell(cx: int, cy: int, height: int, material: str = "moss") -> None:
        key = _key(cx, cy)
        existing = cells.get(key)
        if existing is not None and int(existing["height"]) != int(height):
            raise ValueError(f"generated overlapping cells disagree at {key}")
        cells[key] = {"x": int(cx), "y": int(cy), "height": int(height), "material": existing.get("material", material) if existing else material}

    def append_route(cx: int, cy: int, height: int) -> None:
        add_cell(cx, cy, height)
        if not route or route[-1] != (cx, cy):
            route.append((cx, cy))

    append_route(x, y, 0)
    for index in range(stage_count):
        height = index
        box_before = (x + 1, y)
        box_after = (x + 2, y)
        high = (x + 3, y)
        connector = (x + 4, y)
        append_route(*box_before, height)
        append_route(*box_after, height)
        append_route(*high, height + 1)
        append_route(*connector, height + 1)
        boxes.append({
            "id": f"lift-box-{index + 1}",
            "kind": "helper",
            "x": box_before[0],
            "y": box_before[1],
            "base_z": height,
            "accent": ["copper", "teal", "plum", "amber"][index % 4],
        })
        stage = {
            "index": index + 1,
            "height_before": height,
            "box_id": f"lift-box-{index + 1}",
            "box_before": list(box_before),
            "box_after": list(box_after),
            "high_cell": list(high),
            "connector": list(connector),
            "transfer_direction": "E",
        }
        if index < stage_count - 1:
            change_lane = index < turn_count
            dy = (1 if rng.random() >= 0.5 else -1) if change_lane else 0
            if y + dy < 1 or y + dy > 3:
                dy *= -1
            if dy:
                turn_cell = (connector[0], connector[1] + dy)
                append_route(*turn_cell, height + 1)
                stage["turn"] = {"direction": "S" if dy > 0 else "N", "cell": list(turn_cell)}
                x, y = turn_cell
            else:
                x, y = connector
                stage["turn"] = None
        else:
            x, y = connector
            stage["turn"] = None
        stages.append(stage)

    hearth = {"x": x, "y": y, "height": stage_count, "label": "EMBER HEARTH"}
    add_cell(x, y, stage_count, "hearthstone")
    start = {"x": 1, "y": 2, "z": 0}
    # The baseline keeps its marked cargo on the north approach.  The
    # lower-profile setting deliberately puts it on the south approach so the
    # same seed presents a different visible pickup decision rather than an
    # inert metadata-only toggle.
    cargo = (1, 1 if cargo_detour else 3)
    add_cell(cargo[0], cargo[1], 0, "fernstone")
    boxes.append({"id": "marked-cargo", "kind": "cargo", "x": cargo[0], "y": cargo[1], "base_z": 0, "accent": "gold", "marked": True})

    # Side shelves and decoy crates make depth and height meaningful without
    # occupying the single guaranteed route.  They are real cells and real
    # pushable boxes, not decorative sprites over empty space.
    used = set(cells)
    for index in range(decoy_count):
        candidate_x = 2 + ((index * 3 + rng.randrange(2)) % max(2, (x - 1)))
        candidate_y = 0 if index % 2 == 0 else 4
        if _key(candidate_x, candidate_y) in used:
            candidate_x = max(1, candidate_x - 1)
        candidate_h = min(stage_count - 1, index % max(1, stack_height))
        add_cell(candidate_x, candidate_y, candidate_h, "side-shelf")
        used.add(_key(candidate_x, candidate_y))
        boxes.append({"id": f"decoy-crate-{index + 1}", "kind": "decoy", "x": candidate_x, "y": candidate_y, "base_z": candidate_h, "accent": "smoke" if index % 2 else "coral"})

    world = {
        "version": "hearthlift-voxel-v1",
        "dimensions": {"width": x + 3, "depth": 5, "height": stage_count + 2},
        "cells": sorted(cells.values(), key=lambda item: (item["height"], item["y"], item["x"])),
        "cell_map": cells,
        "route": [list(point) for point in route],
        "stages": stages,
        "boxes": copy.deepcopy(boxes),
        "avatar_start": start,
        "hearth": hearth,
        "camera": {"initial_yaw": -0.62, "obscurity": float(parameters["camera_obscurity"]), "orbit_step": 0.34},
        "rules": {
            "move": "One cardinal move crosses at most one voxel height. A box at the current level is pushed into an empty same-height cell; a box one voxel above the feet can be climbed with CLIMB.",
            "carry": "The marked cargo is picked up from an adjacent same-height cell and dropped only on the glowing hearth.",
            "camera": "Orbiting changes the projection only. It is required to inspect the depth-staggered shelves and the hearth approach.",
        },
    }
    world_public = copy.deepcopy(world)
    world_public.pop("cell_map", None)
    # The route and stage table are construction-only witnesses.  The browser
    # must make the courier infer the route from the visible cells, boxes, and
    # elevation changes rather than receiving a serialized solution map.
    world_public.pop("route", None)
    world_public.pop("stages", None)
    # Build the canonical sequence once. The browser never receives this
    # sequence; it receives only the visible voxel world.
    actions: list[dict[str, Any]] = [{"type": "camera", "delta": 0.34}]
    current = tuple(route[0])
    for stage in stages:
        # Entering the helper's cell is the push itself.  The next cell is
        # empty and the helper advances one voxel while the courier occupies
        # its former cell.
        actions.append({"type": "move", "direction": "E"})
        actions.append({"type": "climb", "direction": "E"})
        actions.append({"type": "move", "direction": "E"})
        actions.append({"type": "move", "direction": "E"})
        current = tuple(stage["connector"])
        if stage.get("turn"):
            actions.append({"type": "move", "direction": stage["turn"]["direction"]})
            current = tuple(stage["turn"]["cell"])

    # Return through the same visible route to fetch the marked crate. The
    # helper crates are now climbable from their top surfaces.
    for first, second in zip(reversed(route[1:]), reversed(route[:-1])):
        actions.append({"type": "move", "direction": _direction(tuple(first), tuple(second))})
    actions.append({"type": "pickup"})
    current = tuple(route[0])
    for stage in stages:
        before = tuple(stage["box_before"])
        if current != before:
            actions.append({"type": "move", "direction": _direction(current, before)})
        actions.append({"type": "climb", "direction": "E"})
        actions.append({"type": "move", "direction": "E"})
        actions.append({"type": "move", "direction": "E"})
        current = tuple(stage["connector"])
        if stage.get("turn"):
            actions.append({"type": "move", "direction": stage["turn"]["direction"]})
            current = tuple(stage["turn"]["cell"])
    actions.append({"type": "drop"})
    # Internal-only lookup used during construction; no hidden route mapping
    # is allowed into the public state.
    world_for_replay = copy.deepcopy(world)
    world_for_replay["cell_map"] = cells
    interaction = "full"
    return world_public, actions, world_for_replay, interaction


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = copy.deepcopy(task.get("_control_condition"))
    parameters = dict(DEFAULT_PARAMETERS)
    if condition:
        parameters.update(dict(condition.get("difficulty_parameters") or {}))
    world_public, actions, world_internal, _ = _build_world(str(seed), parameters)
    task_id = str(task.get("id") or f"{MECHANIC_ID}_seed_0001@0.1")
    condition_token = json.dumps(condition, sort_keys=True, separators=(",", ":")) if condition else "baseline"
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|{condition_token}|{task_id}".encode("utf-8")).hexdigest()[:14]
    interaction = str((condition or {}).get("interaction") or "full")
    # Replaying the solution with the chosen input surface creates an oracle
    # transcript for independent tests while keeping it out of public state.
    solution_events = _event_transcript(world_internal, actions, interaction)
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Carry the marked crate to the ember hearth.",
        "submit_label": "CERTIFY DELIVERY",
        "asset_manifest": ASSET_MANIFEST,
        "generator": {"name": "hearthlift_voxel_courier_v1", "variant_count": VARIANT_COUNT},
        "difficulty_level": int((condition or {}).get("difficulty", 4)),
        "world": world_public,
        "goal": "The marked cargo must be carried to the glowing hearth; helper crates change the climbable route.",
        "camera": copy.deepcopy(world_public["camera"]),
    }
    truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": str(seed),
        "challenge_id": challenge_id,
        "world": world_internal,
        "initial_state": {"avatar": copy.deepcopy(world_internal["avatar_start"]), "boxes": copy.deepcopy(world_internal["boxes"]), "held": None, "delivered": False},
        "solution_actions": actions,
        "solution_events": solution_events,
        "variant_count": VARIANT_COUNT,
    }
    if condition:
        public["control_condition"] = copy.deepcopy(condition)
        truth["control_condition"] = copy.deepcopy(condition)
    return public, truth


__all__ = ["MECHANIC_ID", "generate"]
