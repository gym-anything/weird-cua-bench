from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "lampwrights_program"
DIRS = ((1, 0), (0, 1), (-1, 0), (0, -1))
COMMANDS = {"F", "L", "R", "J", "G", "A", "B"}


PROFILES: dict[int, dict[str, Any]] = {
    1: {
        "main_slots": 4,
        "sub_slots": 4,
        "program": {"main": ["A"], "A": ["G", "F", "J", "G"], "B": []},
        "decorations": 3,
        "height_variation": 0,
    },
    2: {
        "main_slots": 5,
        "sub_slots": 5,
        "program": {"main": ["A", "R", "B"], "A": ["G", "F", "J", "F", "G"], "B": ["F", "R", "F", "G"]},
        "decorations": 5,
        "height_variation": 1,
    },
    3: {
        "main_slots": 6,
        "sub_slots": 6,
        "program": {"main": ["A", "R", "B", "L", "A"], "A": ["G", "F", "F", "J", "F", "G"], "B": ["F", "R", "F", "J", "F", "G"]},
        "decorations": 7,
        "height_variation": 1,
    },
    4: {
        "main_slots": 8,
        "sub_slots": 6,
        "program": {"main": ["A", "R", "B", "L", "A", "R", "B"], "A": ["G", "F", "F", "J", "F", "G"], "B": ["F", "R", "F", "J", "F", "G"]},
        "decorations": 10,
        "height_variation": 2,
    },
    5: {
        "main_slots": 10,
        "sub_slots": 7,
        "program": {"main": ["A", "R", "B", "L", "A", "R", "B", "L", "A"], "A": ["G", "F", "F", "J", "F", "G"], "B": ["F", "R", "F", "J", "F", "G"]},
        "decorations": 15,
        "height_variation": 2,
    },
}


def _seed(seed: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{MECHANIC_ID}|v1".encode()).digest()[:8], "big")


def _profile(task: dict[str, Any]) -> tuple[int, dict[str, Any], dict[str, Any] | None]:
    condition = copy.deepcopy(task.get("_control_condition") or (task.get("metadata") or {}).get("control_condition"))
    level = int((condition or {}).get("difficulty", 4))
    profile = copy.deepcopy(PROFILES.get(level, PROFILES[4]))
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    for key in ("main_slots", "sub_slots", "decorations", "height_variation"):
        if key in parameters:
            profile[key] = int(parameters[key])
    if isinstance(parameters.get("program"), dict):
        profile["program"] = copy.deepcopy(parameters["program"])
    return level, profile, condition


def _key(point: tuple[int, int]) -> str:
    return f"{point[0]},{point[1]}"


def _run_program(program: dict[str, list[str]]) -> tuple[dict[str, int], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    terrain: dict[str, int] = {_key((0, 0)): 0}
    state = {"x": 0, "y": 0, "heading": 0, "height": 0}
    targets: list[dict[str, Any]] = []
    target_keys: set[str] = set()
    route: list[dict[str, Any]] = []
    sequence = 0
    jump_number = 0
    stack: list[tuple[str, int, int]] = [("main", 0, 0)]
    while stack:
        routine, index, depth = stack.pop()
        commands = program.get(routine, [])
        while index < len(commands):
            command = str(commands[index])
            index += 1
            sequence += 1
            if command in {"A", "B"}:
                if depth >= 4:
                    raise ValueError("procedure nesting is too deep")
                stack.append((routine, index, depth))
                stack.append((command, 0, depth + 1))
                break
            if command not in COMMANDS - {"A", "B"}:
                raise ValueError(f"invalid command {command}")
            before = dict(state)
            if command == "L":
                state["heading"] = (state["heading"] + 3) % 4
            elif command == "R":
                state["heading"] = (state["heading"] + 1) % 4
            elif command in {"F", "J"}:
                dx, dy = DIRS[state["heading"]]
                next_point = (state["x"] + dx, state["y"] + dy)
                next_key = _key(next_point)
                if command == "F":
                    next_height = state["height"]
                else:
                    jump_number += 1
                    direction = 1 if jump_number % 2 else -1
                    next_height = max(0, state["height"] + direction)
                    if next_height == state["height"]:
                        next_height = state["height"] + 1
                prior = terrain.get(next_key)
                if prior is not None and prior != next_height:
                    raise ValueError("program revisits a block at a conflicting height")
                terrain[next_key] = next_height
                state.update({"x": next_point[0], "y": next_point[1], "height": next_height})
            elif command == "G":
                target_key = _key((state["x"], state["y"]))
                if target_key not in target_keys:
                    target_keys.add(target_key)
                    targets.append({
                        "id": f"lamp-{len(targets) + 1}",
                        "x": state["x"],
                        "y": state["y"],
                        "z": state["height"],
                    })
            route.append({"sequence": sequence, "command": command, "before": before, "after": dict(state)})
        else:
            continue
    return terrain, targets, route, dict(state)


def _build_world(program: dict[str, list[str]], rng: random.Random, decorations: int, height_variation: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    terrain, targets, route, final_state = _run_program(program)
    used = set(terrain)
    points = [tuple(map(int, key.split(","))) for key in used]
    min_x = min(x for x, _ in points)
    min_y = min(y for _, y in points)
    shift_x, shift_y = 3 - min_x, 3 - min_y
    shifted_terrain: dict[str, int] = {}
    for key, height in terrain.items():
        x, y = (int(part) for part in key.split(","))
        shifted_terrain[_key((x + shift_x, y + shift_y))] = height
    for target in targets:
        target["x"] += shift_x
        target["y"] += shift_y
    for step in route:
        for pose_name in ("before", "after"):
            pose = step[pose_name]
            pose["x"] += shift_x
            pose["y"] += shift_y
    final_state["x"] += shift_x
    final_state["y"] += shift_y
    max_x = max(x for x, _ in (tuple(map(int, key.split(","))) for key in shifted_terrain))
    max_y = max(y for _, y in (tuple(map(int, key.split(","))) for key in shifted_terrain))
    candidates = [(x, y) for x in range(1, max_x + 4) for y in range(1, max_y + 4) if _key((x, y)) not in shifted_terrain]
    rng.shuffle(candidates)
    for x, y in candidates[:decorations]:
        shifted_terrain[_key((x, y))] = rng.randrange(0, max(1, int(height_variation) + 1))
    blocks = []
    for index, (key, height) in enumerate(sorted(shifted_terrain.items(), key=lambda item: (sum(map(int, item[0].split(","))), item[0]))):
        x, y = (int(part) for part in key.split(","))
        blocks.append({"id": f"block-{index + 1}", "x": x, "y": y, "height": int(height)})
    start_state = {"x": shift_x, "y": shift_y, "heading": 0, "height": 0}
    return blocks, targets, route, {"x": final_state["x"], "y": final_state["y"], "heading": final_state["heading"], "height": final_state["height"]}, start_state


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    level, profile, condition = _profile(task)
    rng = random.Random(_seed(seed))
    program = {key: [str(token) for token in value] for key, value in profile["program"].items()}
    blocks, targets, route, final_state, start = _build_world(program, rng, int(profile["decorations"]), int(profile["height_variation"]))
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|d{level}|{task.get('id')}".encode()).hexdigest()[:12]
    bounds = {
        "width": max(int(block["x"]) for block in blocks) + 2,
        "depth": max(int(block["y"]) for block in blocks) + 2,
    }
    limits = {"main": int(profile["main_slots"]), "A": int(profile["sub_slots"]), "B": int(profile["sub_slots"])}
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Program the lampwright to light every marked roof tile.",
        "submit_label": "CERTIFY ROUTE",
        "asset_manifest": "shared_runtime/assets/provenance/lampwrights_program_v0.json",
        "generator": {"name": "lampwrights_rooftop_v1", "variant_count": 2**32},
        "rules": {
            "commands": {"F": "forward", "L": "turn left", "R": "turn right", "J": "jump one height", "G": "light tile", "A": "call amber routine", "B": "call blue routine"},
            "jump": "J crosses exactly one visible height step; F may only cross a level neighbour.",
            "procedures": "Main may call A or B; routines may contain movement and light commands.",
        },
        "world": {"blocks": blocks, "targets": targets, "bounds": bounds, "start": start},
        "program_limits": limits,
        "control_condition": copy.deepcopy(condition) if condition else {"difficulty": level, "interaction": "full", "real_time": "live", "difficulty_parameters": copy.deepcopy(profile)},
    }
    truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "seed": seed,
        "challenge_id": challenge_id,
        "control_condition": copy.deepcopy(public["control_condition"]),
        "program_limits": limits,
        "program_solution": program,
        "terrain": {f"{int(block['x'])},{int(block['y'])}": int(block["height"]) for block in blocks},
        "targets": copy.deepcopy(targets),
        "route": copy.deepcopy(route),
        "start": start,
        "final_state": final_state,
    }
    return public, truth
