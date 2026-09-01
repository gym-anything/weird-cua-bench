from __future__ import annotations

import copy
import math
from typing import Any


MECHANIC_ID = "turtle_forger"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _bind(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> str | None:
    if any(str(item.get("mechanic_id") or "") != MECHANIC_ID for item in (payload, truth, public)):
        return "mechanic mismatch"
    for key in ("task_id", "challenge_id"):
        expected = str(truth.get(key) or "")
        if not expected or str(payload.get(key) or "") != expected or str(public.get(key) or "") != expected:
            return f"stale or mismatched {key}"
    return None


def _contract(truth: dict[str, Any], public: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any], str]:
    if truth.get("canvas") != public.get("canvas") or truth.get("start") != public.get("start"):
        raise ValueError("public plate geometry differs from replay truth")
    if truth.get("command_palette") != public.get("command_palette"):
        raise ValueError("public command drawer differs from replay truth")
    if truth.get("target_segments") != public.get("runtime_target_segments"):
        raise ValueError("runtime reference scan differs from target geometry")
    if truth.get("parameters") != public.get("parameters"):
        raise ValueError("public difficulty parameters differ from replay truth")
    condition = truth.get("control_condition")
    if condition != public.get("control_condition"):
        raise ValueError("public control condition differs from replay truth")
    if condition is not None and condition.get("difficulty_parameters") != truth.get("parameters"):
        raise ValueError("condition parameters differ from generated task")
    interaction = str((condition or {}).get("interaction") or "full")
    if interaction not in {"simplified", "full"}:
        raise ValueError("interaction mode is invalid")
    palette = truth.get("command_palette")
    if not isinstance(palette, list) or not 2 <= len(palette) <= 40:
        raise ValueError("command palette has invalid size")
    by_key: dict[str, dict[str, Any]] = {}
    for command in palette:
        key = str(command.get("key") or "") if isinstance(command, dict) else ""
        if not key or key in by_key:
            raise ValueError("command palette keys are invalid")
        by_key[key] = command
    return by_key, copy.deepcopy(truth["parameters"]), interaction


def _expand(program: list[dict[str, Any]], maximum: int) -> list[dict[str, Any]]:
    def block(index: int, nested: bool) -> tuple[list[dict[str, Any]], int]:
        output: list[dict[str, Any]] = []
        while index < len(program):
            command = program[index]
            op = str(command.get("op") or "")
            if op == "end":
                if not nested:
                    raise ValueError("orphan loop end")
                return output, index + 1
            if op == "repeat":
                count = command.get("value")
                if isinstance(count, bool) or not isinstance(count, int) or not 2 <= count <= 12:
                    raise ValueError("repeat count is invalid")
                body, index = block(index + 1, True)
                for _ in range(count):
                    output.extend(copy.deepcopy(body))
            else:
                if op not in {"ink", "forward", "left", "right", "pen_up", "pen_down"}:
                    raise ValueError("program contains an invalid command")
                output.append(command)
                index += 1
            if len(output) > maximum:
                raise ValueError("program exceeds expanded-step limit")
        if nested:
            raise ValueError("unterminated repeat block")
        return output, index

    expanded, _ = block(0, False)
    return expanded


def _execute(program: list[dict[str, Any]], start: dict[str, Any], maximum: int, width: int) -> list[dict[str, Any]]:
    expanded = _expand(program, maximum)
    x = float(start["x"])
    y = float(start["y"])
    heading = float(start.get("heading", 0.0))
    pen_down = True
    ink = "#202523"
    segments: list[dict[str, Any]] = []
    for command in expanded:
        op = str(command["op"])
        if op == "ink":
            ink = str(command.get("value") or "")
            if not ink.startswith("#") or len(ink) != 7:
                raise ValueError("ink command has an invalid colour")
        elif op == "pen_up":
            pen_down = False
        elif op == "pen_down":
            pen_down = True
        elif op in {"left", "right"}:
            value = command.get("value")
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 359:
                raise ValueError("turn command has an invalid angle")
            heading = (heading + value * (1 if op == "right" else -1)) % 360
        elif op == "forward":
            value = command.get("value")
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 300:
                raise ValueError("advance command has an invalid distance")
            radians = math.radians(heading)
            after_x = x + math.sin(radians) * value
            after_y = y - math.cos(radians) * value
            if pen_down:
                segments.append({
                    "order": len(segments) + 1,
                    "x1": round(x, 4), "y1": round(y, 4),
                    "x2": round(after_x, 4), "y2": round(after_y, 4),
                    "colour": ink, "width": width,
                })
            x, y = after_x, after_y
    return segments


def _gesture(event: dict[str, Any]) -> None:
    gesture = event.get("gesture")
    if not isinstance(gesture, dict):
        raise ValueError("direct card placement lacks drag proof")
    travel = gesture.get("travel_px")
    samples = gesture.get("sample_count")
    if isinstance(travel, bool) or not isinstance(travel, (int, float)) or not math.isfinite(float(travel)) or float(travel) < 36:
        raise ValueError("direct card placement has insufficient travel")
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 2:
        raise ValueError("direct card placement has too few movement samples")


def _replay_events(events: Any, palette: dict[str, dict[str, Any]], interaction: str, capacity: int) -> list[str]:
    if not isinstance(events, list) or not 1 <= len(events) <= 300:
        raise ValueError("program edit transcript is missing or outside limits")
    program: list[str] = []
    add_source = "palette_click" if interaction == "simplified" else "card_drag"
    move_source = "move_buttons" if interaction == "simplified" else "tape_drag"
    for sequence, event in enumerate(events, 1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            raise ValueError(f"edit event {sequence} has invalid sequence")
        action = str(event.get("type") or "")
        if action == "add":
            key = str(event.get("command_key") or "")
            at = event.get("at")
            if key not in palette or isinstance(at, bool) or not isinstance(at, int) or not 0 <= at <= len(program):
                raise ValueError(f"edit event {sequence} has invalid card placement")
            if event.get("input_source") != add_source:
                raise ValueError(f"edit event {sequence} uses the wrong interaction input")
            if interaction == "full":
                _gesture(event)
            program.insert(at, key)
            if len(program) > capacity:
                raise ValueError("program tape exceeds capacity")
        elif action == "remove":
            at = event.get("at")
            key = str(event.get("command_key") or "")
            if event.get("input_source") != "tape_remove" or isinstance(at, bool) or not isinstance(at, int) or not 0 <= at < len(program) or program[at] != key:
                raise ValueError(f"edit event {sequence} has an invalid removal")
            program.pop(at)
        elif action == "move":
            before, after = event.get("from"), event.get("to")
            if event.get("input_source") != move_source or any(isinstance(value, bool) or not isinstance(value, int) for value in (before, after)):
                raise ValueError(f"edit event {sequence} has invalid movement")
            if not 0 <= before < len(program) or not 0 <= after < len(program):
                raise ValueError(f"edit event {sequence} moves outside the tape")
            if interaction == "full":
                _gesture(event)
            key = program.pop(before)
            program.insert(after, key)
        else:
            raise ValueError(f"edit event {sequence} has unknown action")
    return program


def _segment_key(segment: dict[str, Any]) -> tuple[Any, ...]:
    return (
        int(segment.get("order")),
        round(float(segment.get("x1")), 4), round(float(segment.get("y1")), 4),
        round(float(segment.get("x2")), 4), round(float(segment.get("y2")), 4),
        str(segment.get("colour") or ""), int(segment.get("width")),
    )


def _raster(segments: list[dict[str, Any]], cell: float = 3.0) -> set[tuple[str, int, int]]:
    occupied: set[tuple[str, int, int]] = set()
    for segment in segments:
        x1, y1 = float(segment["x1"]), float(segment["y1"])
        x2, y2 = float(segment["x2"]), float(segment["y2"])
        length = math.hypot(x2 - x1, y2 - y1)
        steps = max(1, int(math.ceil(length / 1.25)))
        colour = str(segment["colour"])
        for index in range(steps + 1):
            fraction = index / steps
            ix = round((x1 + (x2 - x1) * fraction) / cell)
            iy = round((y1 + (y2 - y1) * fraction) / cell)
            for ox in (-1, 0, 1):
                for oy in (-1, 0, 1):
                    occupied.add((colour, ix + ox, iy + oy))
    return occupied


def _score(output: list[dict[str, Any]], target: list[dict[str, Any]]) -> tuple[float, float, float]:
    actual = _raster(output)
    expected = _raster(target)
    if not actual or not expected:
        return 0.0, 0.0, 0.0
    overlap = len(actual & expected)
    precision = overlap / len(actual)
    coverage = overlap / len(expected)
    union = len(actual | expected)
    return overlap / union if union else 0.0, precision, coverage


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    binding = _bind(payload, truth, public)
    if binding:
        return _fail(binding)
    try:
        palette, parameters, interaction = _contract(truth, public)
        if payload.get("interaction_mode") != interaction:
            raise ValueError("submitted interaction mode differs from task condition")
        program_keys = _replay_events(payload.get("edit_events"), palette, interaction, int(parameters["program_capacity"]))
        if payload.get("final_program") != program_keys:
            raise ValueError("submitted program does not match edit replay")
        run_count = payload.get("run_count")
        if isinstance(run_count, bool) or not isinstance(run_count, int) or not 1 <= run_count <= 100:
            raise ValueError("program was not proofed through the visible runner")
        program = [palette[key] for key in program_keys]
        canvas = truth["canvas"]
        replayed = _execute(program, truth["start"], int(parameters["max_expanded_steps"]), int(canvas["stroke_width"]))
        rendered = payload.get("rendered_segments")
        if not isinstance(rendered, list):
            raise ValueError("rendered proof geometry is missing")
        if [_segment_key(item) for item in rendered] != [_segment_key(item) for item in replayed]:
            raise ValueError("rendered proof geometry differs from program replay")
        target = truth.get("target_segments")
        if not isinstance(target, list) or not target:
            raise ValueError("target geometry is missing")
        score, precision, coverage = _score(replayed, target)
        reported = payload.get("similarity")
        if isinstance(reported, bool) or not isinstance(reported, (int, float)) or not math.isfinite(float(reported)) or abs(float(reported) - score) > .0005:
            raise ValueError("reported visual similarity differs from independent raster replay")
        threshold = float(truth.get("pass_threshold", .985))
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return _fail(f"turtle replay rejected: {exc}")
    passed = payload.get("completed") is True and score >= threshold and precision >= threshold and coverage >= threshold
    return {
        "graded": True,
        "passed": passed,
        "feedback": (
            f"raster similarity {score * 100:.2f}%; precision {precision * 100:.2f}%; "
            f"coverage {coverage * 100:.2f}%; {len(program_keys)} cards; {len(replayed)} ink strokes"
        ),
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {"canonical_program": ground_truth.get("canonical_program") or [], "answers": []}
