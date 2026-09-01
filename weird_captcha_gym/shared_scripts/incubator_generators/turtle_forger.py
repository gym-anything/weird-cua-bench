from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "turtle_forger"
CANVAS = {"width": 420, "height": 300, "stroke_width": 5}
INKS = (
    {"slug": "vermilion", "name": "VERMILION", "hex": "#ef5b45"},
    {"slug": "cyan", "name": "CYAN BLUE", "hex": "#35b8d2"},
    {"slug": "saffron", "name": "SAFFRON", "hex": "#f0b84b"},
    {"slug": "jade", "name": "JADE", "hex": "#51bd83"},
    {"slug": "violet", "name": "VIOLET", "hex": "#9d78d5"},
)


def _condition(task: dict[str, Any]) -> dict[str, Any] | None:
    value = task.get("_control_condition")
    return copy.deepcopy(value) if isinstance(value, dict) else None


def _parameters(task: dict[str, Any]) -> dict[str, Any]:
    condition = _condition(task)
    if condition:
        parameters = condition.get("difficulty_parameters")
        if not isinstance(parameters, dict):
            raise ValueError("control difficulty parameters are malformed")
        return copy.deepcopy(parameters)
    return {
        "pattern_profile": "compound_seal",
        "loop_depth": 1,
        "colour_count": 2,
        "subpath_count": 2,
        "grid_mode": "major",
        "stroke_ms": 520,
        "gap_ms": 145,
        "program_capacity": 16,
        "palette_decoys": 4,
        "max_expanded_steps": 64,
    }


def _validate(parameters: dict[str, Any]) -> None:
    profiles = {
        "single_outline": (0, 1, 1),
        "loop_seal": (1, 1, 1),
        "compound_seal": (1, 2, 2),
        "registered_triptych": (1, 3, 3),
        "nested_rosette": (2, 3, 3),
    }
    profile = str(parameters.get("pattern_profile") or "")
    if profile not in profiles:
        raise ValueError("unsupported turtle pattern profile")
    expected = profiles[profile]
    received = tuple(parameters.get(key) for key in ("loop_depth", "colour_count", "subpath_count"))
    if received != expected:
        raise ValueError("turtle structure parameters disagree with their pattern profile")
    if parameters.get("grid_mode") not in {"full", "major", "registration", "none"}:
        raise ValueError("grid_mode is invalid")
    for key, low, high in (
        ("stroke_ms", 250, 1000),
        ("gap_ms", 80, 250),
        ("program_capacity", 4, 40),
        ("palette_decoys", 0, 12),
        ("max_expanded_steps", 12, 180),
    ):
        value = parameters.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"{key} must be an integer in [{low}, {high}]")


def _command(op: str, value: Any = None, *, ink: dict[str, str] | None = None) -> dict[str, Any]:
    if op == "ink":
        if ink is None:
            raise ValueError("ink command requires an ink")
        return {
            "key": f"ink-{ink['slug']}",
            "op": "ink",
            "value": ink["hex"],
            "label": f"INK / {ink['name']}",
            "family": "ink",
        }
    if op == "forward":
        return {"key": f"forward-{int(value)}", "op": op, "value": int(value), "label": f"ADVANCE {int(value)}", "family": "motion"}
    if op in {"left", "right"}:
        arrow = "↺" if op == "left" else "↻"
        return {"key": f"{op}-{int(value)}", "op": op, "value": int(value), "label": f"TURN {arrow} {int(value)}°", "family": "motion"}
    if op == "repeat":
        return {"key": f"repeat-{int(value)}", "op": op, "value": int(value), "label": f"LOOP ×{int(value)}", "family": "loop"}
    labels = {"end": "CLOSE LOOP", "pen_up": "LIFT PEN", "pen_down": "LOWER PEN"}
    if op not in labels:
        raise ValueError(f"unknown turtle command {op}")
    return {"key": op.replace("_", "-"), "op": op, "label": labels[op], "family": "loop" if op == "end" else "pen"}


def _append_loop(program: list[dict[str, Any]], count: int, length: int, turn: int, direction: str = "right") -> None:
    program.extend((_command("repeat", count), _command("forward", length), _command(direction, turn), _command("end")))


def _relocate(program: list[dict[str, Any]], direction: str, distance: int) -> None:
    opposite = "left" if direction == "right" else "right"
    program.extend((_command("pen_up"), _command(direction, 90), _command("forward", distance), _command(opposite, 90), _command("pen_down")))


def _build_program(profile: str, rng: random.Random, inks: list[dict[str, str]]) -> list[dict[str, Any]]:
    program: list[dict[str, Any]] = [_command("ink", ink=inks[0])]
    if profile == "single_outline":
        sides = rng.choice((3, 4))
        length = rng.choice((72, 84, 90))
        angle = 360 // sides
        for _ in range(sides):
            program.extend((_command("forward", length), _command("right", angle)))
        return program
    if profile == "loop_seal":
        if rng.random() < .5:
            _append_loop(program, 5, rng.choice((70, 78, 84)), 144)
        else:
            sides = rng.choice((5, 6))
            _append_loop(program, sides, rng.choice((66, 72, 78)), 360 // sides)
        return program
    if profile == "compound_seal":
        if rng.random() < .5:
            _append_loop(program, 5, rng.choice((68, 72, 78)), 144)
        else:
            _append_loop(program, 5, rng.choice((64, 70, 76)), 72)
        direction = rng.choice(("left", "right"))
        _relocate(program, direction, rng.choice((100, 110, 120)))
        program.append(_command("ink", ink=inks[1]))
        sides = rng.choice((3, 4))
        _append_loop(program, sides, rng.choice((52, 58, 64)), 360 // sides)
        return program
    if profile == "registered_triptych":
        _append_loop(program, 6, rng.choice((48, 54, 60)), 60)
        direction = rng.choice(("left", "right"))
        _relocate(program, direction, rng.choice((100, 110, 120)))
        program.append(_command("ink", ink=inks[1]))
        _append_loop(program, 5, rng.choice((58, 62, 68)), 144)
        opposite = "left" if direction == "right" else "right"
        _relocate(program, opposite, rng.choice((205, 220, 235)))
        program.extend((_command("ink", ink=inks[2]), _command("forward", rng.choice((68, 76, 84)))))
        return program
    if profile == "nested_rosette":
        program.extend((
            _command("repeat", 3),
            _command("repeat", 4), _command("forward", rng.choice((42, 46, 50))), _command("right", 90), _command("end"),
            _command("right", 120), _command("end"),
        ))
        direction = rng.choice(("left", "right"))
        _relocate(program, direction, rng.choice((105, 115, 125)))
        program.append(_command("ink", ink=inks[1]))
        _append_loop(program, 8, rng.choice((62, 68, 72)), 135)
        opposite = "left" if direction == "right" else "right"
        _relocate(program, opposite, rng.choice((215, 230, 245)))
        program.append(_command("ink", ink=inks[2]))
        _append_loop(program, 3, rng.choice((64, 70, 76)), 120)
        return program
    raise AssertionError(profile)


def _expand(program: list[dict[str, Any]], maximum: int) -> list[dict[str, Any]]:
    def block(index: int, nested: bool) -> tuple[list[dict[str, Any]], int]:
        output: list[dict[str, Any]] = []
        while index < len(program):
            command = program[index]
            op = command["op"]
            if op == "end":
                if not nested:
                    raise ValueError("orphan loop end")
                return output, index + 1
            if op == "repeat":
                body, index = block(index + 1, True)
                for _ in range(int(command["value"])):
                    output.extend(copy.deepcopy(body))
            else:
                output.append(command)
                index += 1
            if len(output) > maximum:
                raise ValueError("program exceeds expanded-step limit")
        if nested:
            raise ValueError("unterminated repeat block")
        return output, index

    expanded, _ = block(0, False)
    return expanded


def _execute(program: list[dict[str, Any]], maximum: int) -> tuple[list[dict[str, Any]], dict[str, float]]:
    expanded = _expand(program, maximum)
    x = 0.0
    y = 0.0
    heading = 0.0
    pen_down = True
    ink = "#202523"
    segments: list[dict[str, Any]] = []
    for command in expanded:
        op = command["op"]
        if op == "ink":
            ink = str(command["value"])
        elif op == "pen_up":
            pen_down = False
        elif op == "pen_down":
            pen_down = True
        elif op == "left":
            heading = (heading - float(command["value"])) % 360
        elif op == "right":
            heading = (heading + float(command["value"])) % 360
        elif op == "forward":
            radians = math.radians(heading)
            after_x = x + math.sin(radians) * float(command["value"])
            after_y = y - math.cos(radians) * float(command["value"])
            if pen_down:
                segments.append({
                    "order": len(segments) + 1,
                    "x1": round(x, 4), "y1": round(y, 4),
                    "x2": round(after_x, 4), "y2": round(after_y, 4),
                    "colour": ink, "width": CANVAS["stroke_width"],
                })
            x, y = after_x, after_y
    return segments, {"x": x, "y": y, "heading": heading}


def _center(program: list[dict[str, Any]], maximum: int) -> tuple[list[dict[str, Any]], dict[str, float]]:
    segments, final = _execute(program, maximum)
    if not segments:
        raise AssertionError("generated turtle program draws no ink")
    xs = [coordinate for segment in segments for coordinate in (segment["x1"], segment["x2"])]
    ys = [coordinate for segment in segments for coordinate in (segment["y1"], segment["y2"])]
    dx = CANVAS["width"] / 2 - (min(xs) + max(xs)) / 2
    dy = CANVAS["height"] / 2 - (min(ys) + max(ys)) / 2
    if max(xs) - min(xs) > CANVAS["width"] - 32 or max(ys) - min(ys) > CANVAS["height"] - 32:
        raise AssertionError("generated turtle seal does not fit its plate")
    for segment in segments:
        for key in ("x1", "x2"):
            segment[key] = round(segment[key] + dx, 4)
        for key in ("y1", "y2"):
            segment[key] = round(segment[key] + dy, 4)
    return segments, {
        "x": round(dx, 4), "y": round(dy, 4), "heading": 0.0,
        "final_x": round(final["x"] + dx, 4), "final_y": round(final["y"] + dy, 4),
        "final_heading": round(final["heading"], 4),
    }


def _all_candidate_commands(inks: list[dict[str, str]]) -> list[dict[str, Any]]:
    candidates = [_command("pen_up"), _command("pen_down"), _command("end")]
    candidates.extend(_command("forward", value) for value in (35, 42, 46, 50, 54, 58, 60, 62, 64, 68, 70, 72, 76, 78, 84, 90, 100, 105, 110, 115, 120, 125, 205, 215, 220, 230, 235, 245))
    candidates.extend(_command(direction, angle) for direction in ("left", "right") for angle in (45, 60, 72, 90, 120, 135, 144))
    candidates.extend(_command("repeat", count) for count in (3, 4, 5, 6, 8))
    candidates.extend(_command("ink", ink=ink) for ink in inks)
    return candidates


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    parameters = _parameters(task)
    _validate(parameters)
    stable = hashlib.sha256(f"{MECHANIC_ID}:{seed}:{parameters}".encode("utf-8")).hexdigest()
    rng = random.Random(int(stable[:16], 16))
    task_id = str(task.get("id") or "turtle_forger")
    challenge_id = f"tfg-{stable[:18]}"
    inks = rng.sample(list(INKS), int(parameters["colour_count"]))
    program = _build_program(str(parameters["pattern_profile"]), rng, inks)
    if len(program) > int(parameters["program_capacity"]):
        raise AssertionError("canonical turtle program exceeds tape capacity")
    target_segments, start = _center(program, int(parameters["max_expanded_steps"]))
    if len({segment["colour"] for segment in target_segments}) != int(parameters["colour_count"]):
        raise AssertionError("target colour count differs from profile")

    unique_commands = {command["key"]: copy.deepcopy(command) for command in program}
    used = set(unique_commands)
    candidates = [command for command in _all_candidate_commands(list(INKS)) if command["key"] not in used]
    rng.shuffle(candidates)
    for command in candidates[: int(parameters["palette_decoys"])]:
        unique_commands[command["key"]] = command
    command_palette = list(unique_commands.values())
    rng.shuffle(command_palette)
    canonical_keys = [command["key"] for command in program]
    condition = _condition(task)
    ink_word = {1: "one-ink", 2: "two-ink", 3: "three-ink"}[int(parameters["colour_count"])]
    prompt = (
        "Inspect the UV reference until you can reconstruct every transient stroke. "
        f"Build a compact {ink_word} punch-card program, proof it, then certify the plate."
    )
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": prompt,
        "seal_id": f"TF-{stable[18:26].upper()}",
        "canvas": copy.deepcopy(CANVAS),
        "start": copy.deepcopy(start),
        "command_palette": command_palette,
        "runtime_target_segments": copy.deepcopy(target_segments),
        "parameters": copy.deepcopy(parameters),
        "pass_threshold": 0.985,
        "asset_manifest": str((task.get("metadata") or {}).get("asset_manifest") or "shared_runtime/assets/provenance/turtle_forger_v0.json"),
        "generator": {"name": "transient_turtle_seal_v1", "variant_count": 4_000_000_000},
        "status": "ready",
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "seed": seed,
        "canvas": copy.deepcopy(CANVAS),
        "start": copy.deepcopy(start),
        "command_palette": copy.deepcopy(command_palette),
        "canonical_program": canonical_keys,
        "target_segments": copy.deepcopy(target_segments),
        "parameters": copy.deepcopy(parameters),
        "pass_threshold": 0.985,
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
