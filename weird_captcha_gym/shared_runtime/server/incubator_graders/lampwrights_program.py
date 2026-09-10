from __future__ import annotations

from typing import Any


MECHANIC_ID = "lampwrights_program"
TOKENS = {"F", "L", "R", "J", "G", "A", "B"}


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _key(x: int, y: int) -> str:
    return f"{x},{y}"


def _replay(program: dict[str, list[str]], truth: dict[str, Any], *, capture_events: bool = False) -> tuple[bool, str, list[dict[str, Any]]]:
    terrain = {str(key): int(value) for key, value in dict(truth.get("terrain") or {}).items()}
    start = dict(truth.get("start") or {"x": 3, "y": 3, "heading": 0, "height": 0})
    pose = {key: int(start.get(key, 0)) for key in ("x", "y", "heading", "height")}
    dirs = ((1, 0), (0, 1), (-1, 0), (0, -1))
    target_keys = {_key(int(item["x"]), int(item["y"])) for item in truth.get("targets") or []}
    lit: set[str] = set()
    events: list[dict[str, Any]] = []
    stack: list[tuple[str, int, int]] = [("main", 0, 0)]
    max_steps = max(32, sum(len(value) for value in program.values()) * 12)
    while stack and len(events) <= max_steps:
        routine, index, depth = stack.pop()
        commands = program.get(routine, [])
        while index < len(commands):
            command = str(commands[index])
            index += 1
            if command in {"A", "B"}:
                if depth >= 4:
                    return False, "procedure nesting exceeded replay bound", events
                stack.append((routine, index, depth))
                stack.append((command, 0, depth + 1))
                break
            before = dict(pose)
            if command == "L":
                pose["heading"] = (pose["heading"] + 3) % 4
            elif command == "R":
                pose["heading"] = (pose["heading"] + 1) % 4
            elif command in {"F", "J"}:
                dx, dy = dirs[pose["heading"]]
                next_x, next_y = pose["x"] + dx, pose["y"] + dy
                next_key = _key(next_x, next_y)
                if next_key not in terrain:
                    return False, f"{command} leaves the rooftop at {next_key}", events
                next_height = terrain[next_key]
                delta = next_height - pose["height"]
                if command == "F" and delta != 0:
                    return False, "forward crossed an elevation step", events
                if command == "J" and abs(delta) != 1:
                    return False, "jump did not cross exactly one elevation step", events
                pose.update({"x": next_x, "y": next_y, "height": next_height})
            elif command == "G":
                current = _key(pose["x"], pose["y"])
                if current not in target_keys:
                    return False, "light was used on an unmarked tile", events
                lit.add(current)
            else:
                return False, f"unknown instruction {command!r}", events
            if capture_events:
                events.append({"routine": routine, "command": command, "before": before, "after": dict(pose), "lit": sorted(lit)})
        else:
            continue
    if stack:
        return False, "program exceeded the execution bound", events
    if lit != target_keys:
        return False, f"only {len(lit)}/{len(target_keys)} marked tiles were lit", events
    return True, "all marked tiles lit", events


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    if payload.get("mechanic_id") != MECHANIC_ID or truth.get("mechanic_id") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    challenge_id = str(truth.get("challenge_id") or "")
    if not challenge_id or payload.get("challenge_id") != challenge_id or public.get("challenge_id") != challenge_id:
        return _fail("stale challenge")
    condition = truth.get("control_condition")
    if public.get("control_condition") != condition:
        return _fail("public control condition differs from the program contract")
    interaction = str((condition or {}).get("interaction") or "")
    if interaction not in {"simplified", "full"}:
        return _fail("invalid interaction condition")
    expected_source = "palette_click" if interaction == "simplified" else "drag_drop"
    editor_events = payload.get("editor_events")
    if not isinstance(editor_events, list) or len(editor_events) > 400:
        return _fail("editor transcript is malformed")
    for event in editor_events:
        if not isinstance(event, dict) or event.get("input_source") != expected_source:
            return _fail("program edit used the wrong interaction surface")
    program = payload.get("program")
    limits = dict(truth.get("program_limits") or {})
    if not isinstance(program, dict) or set(program) != {"main", "A", "B"}:
        return _fail("program panels are incomplete")
    for panel in ("main", "A", "B"):
        slots = program.get(panel)
        if not isinstance(slots, list) or len(slots) > int(limits.get(panel, 0)):
            return _fail(f"{panel} exceeds its visible slot limit")
        if any(str(token) not in TOKENS for token in slots):
            return _fail(f"{panel} contains an unknown instruction")
    if payload.get("completed") is not True:
        return _fail("program was not marked complete")
    ok, message, replay = _replay({panel: [str(token) for token in program[panel]] for panel in program}, truth, capture_events=True)
    if not ok:
        return _fail(message)
    transcript = payload.get("execution_events")
    if not isinstance(transcript, list) or not transcript:
        return _fail("missing execution transcript")
    complete_events = [event for event in transcript if isinstance(event, dict) and event.get("type") == "run_complete"]
    if not complete_events:
        return _fail("execution did not reach a completed run")
    reported_steps = sum(1 for event in transcript if isinstance(event, dict) and event.get("type") == "step" and event.get("run_id") == complete_events[-1].get("run_id"))
    if reported_steps != len(replay):
        return _fail("visible execution transcript does not match the independent replay")
    return {"graded": True, "passed": True, "feedback": f"{len(truth.get('targets') or [])} roof lamps lit by an independently replayed program"}


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    return {"program": ground_truth.get("program_solution"), "targets": ground_truth.get("targets") or []}
