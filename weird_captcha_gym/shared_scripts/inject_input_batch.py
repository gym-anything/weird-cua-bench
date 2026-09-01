#!/usr/bin/env python3
"""Deliver one ordered batch of standard Gym-Anything desktop actions.

The Weird CUA evaluator pauses or advances task time around a complete model
gesture, not around each wire-level mouse operation.  AVF normally opens a
new SSH command for every move/down/up, which can make transport latency
longer than the visible gesture window.  This guest helper validates the
ordinary action dictionaries and gives them to one xdotool process so their
requested within-gesture cadence is preserved.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import time
from typing import Any

try:
    from .input_control import arm, cancel, complete
except ImportError:
    import sys

    sys.path.insert(0, os.path.dirname(__file__))
    from input_control import arm, cancel, complete


MAX_ACTIONS = 64
MAX_WAIT_SECONDS = 30.0
MAX_COORDINATE = 100_000


def _number(value: Any, *, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _point(value: Any, *, label: str) -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{label} must be a two-coordinate point")
    x = round(_number(value[0], label=f"{label}.x"))
    y = round(_number(value[1], label=f"{label}.y"))
    if abs(x) > MAX_COORDINATE or abs(y) > MAX_COORDINATE:
        raise ValueError(f"{label} exceeds the coordinate limit")
    return x, y


def _append_click(command: list[str], point: Any, button: int, *, repeat: int = 1) -> int:
    x, y = _point(point, label="mouse click")
    command.extend(["mousemove", str(x), str(y), "click"])
    if repeat > 1:
        command.extend(["--repeat", str(repeat), "--delay", "80"])
    command.append(str(button))
    return repeat


def _append_drag(command: list[str], value: Any, button: int) -> int:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("mouse drag must contain start and end points")
    start_x, start_y = _point(value[0], label="mouse drag start")
    end_x, end_y = _point(value[1], label="mouse drag end")
    command.extend(
        [
            "mousemove",
            str(start_x),
            str(start_y),
            "mousedown",
            str(button),
            "mousemove",
            "--sync",
            str(end_x),
            str(end_y),
            "mouseup",
            str(button),
        ]
    )
    return 4


def build_xdotool_command(actions: Any) -> tuple[list[str], int]:
    if not isinstance(actions, list) or not actions:
        raise ValueError("input batch actions must be a non-empty list")
    if len(actions) > MAX_ACTIONS:
        raise ValueError(f"input batch may contain at most {MAX_ACTIONS} actions")

    command = ["xdotool"]
    operation_count = 0
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            raise ValueError(f"action {index} must be an object")
        kind = action.get("action") or action.get("type")
        if kind == "wait":
            seconds = _number(
                action.get("time", action.get("seconds", 1.0)),
                label=f"action {index} wait",
            )
            if not 0 <= seconds <= MAX_WAIT_SECONDS:
                raise ValueError(
                    f"action {index} wait must be between 0 and {MAX_WAIT_SECONDS:g} seconds"
                )
            command.extend(["sleep", repr(seconds)])
            operation_count += 1
            continue

        mouse = action.get("mouse")
        keyboard = action.get("keyboard")
        if bool(mouse) == bool(keyboard):
            raise ValueError(
                f"action {index} must contain exactly one non-empty mouse or keyboard payload"
            )
        if mouse:
            if not isinstance(mouse, dict):
                raise ValueError(f"action {index} mouse payload must be an object")
            recognized = False
            for key, button, repeat in (
                ("left_click", 1, 1),
                ("right_click", 3, 1),
                ("middle_click", 2, 1),
                ("double_click", 1, 2),
                ("triple_click", 1, 3),
            ):
                if key in mouse:
                    operation_count += _append_click(
                        command, mouse[key], button, repeat=repeat
                    )
                    recognized = True
            for key, button in (
                ("left_click_drag", 1),
                ("right_click_drag", 3),
            ):
                if key in mouse:
                    operation_count += _append_drag(command, mouse[key], button)
                    recognized = True
            if "move" in mouse:
                x, y = _point(mouse["move"], label="mouse move")
                command.extend(["mousemove", str(x), str(y)])
                operation_count += 1
                recognized = True
            buttons = mouse.get("buttons") or {}
            if buttons:
                if not isinstance(buttons, dict):
                    raise ValueError(f"action {index} mouse buttons must be an object")
                for key, verb, button in (
                    ("left_down", "mousedown", 1),
                    ("left_up", "mouseup", 1),
                    ("right_down", "mousedown", 3),
                    ("right_up", "mouseup", 3),
                ):
                    if buttons.get(key):
                        command.extend([verb, str(button)])
                        operation_count += 1
                        recognized = True
            if "scroll" in mouse:
                amount = round(_number(mouse["scroll"], label="mouse scroll"))
                if amount:
                    button = 5 if amount > 0 else 4
                    command.extend(["click", "--repeat", str(abs(amount)), str(button)])
                    operation_count += abs(amount)
                recognized = True
            if not recognized:
                raise ValueError(f"action {index} contains no supported mouse operation")
            continue

        if not isinstance(keyboard, dict):
            raise ValueError(f"action {index} keyboard payload must be an object")
        recognized = False
        if "text" in keyboard:
            # xdotool treats the final text argument as one token, even when it
            # contains spaces.  This is safe because subprocess never invokes a shell.
            command.extend(["type", "--delay", "1", "--", str(keyboard["text"])])
            operation_count += 1
            recognized = True
        if "key" in keyboard:
            command.extend(["key", str(keyboard["key"])])
            operation_count += 1
            recognized = True
        if "keys" in keyboard:
            keys = keyboard["keys"]
            combo = "+".join(map(str, keys)) if isinstance(keys, (list, tuple)) else str(keys)
            if combo.strip():
                command.extend(["key", combo])
                operation_count += 1
            recognized = True
        for key, verb in (("keys_down", "keydown"), ("keys_up", "keyup")):
            if key not in keyboard:
                continue
            keys = keyboard[key]
            values = [keys] if isinstance(keys, str) else list(keys)
            for value in values:
                command.extend([verb, str(value)])
                operation_count += 1
            recognized = True
        if not recognized:
            raise ValueError(f"action {index} contains no supported keyboard operation")

    return command, operation_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actions-json", required=True)
    parser.add_argument("--input-category", choices=("mouse", "keyboard", "mixed"))
    parser.add_argument(
        "--receipt-required",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    actions = json.loads(args.actions_json)
    command, operation_count = build_xdotool_command(actions)
    environment = dict(os.environ)
    environment.setdefault("DISPLAY", ":1")
    started = time.perf_counter()
    armed = None
    completed_status = None
    if args.input_category:
        armed = arm(args.input_category, required=args.receipt_required)
    try:
        completed = subprocess.run(
            command,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=MAX_WAIT_SECONDS + 10,
        )
        if armed is not None:
            completed_status = complete(int(armed["arm_sequence"]))
    except Exception:
        if armed is not None:
            try:
                cancel(int(armed["arm_sequence"]))
            except Exception:
                pass
        raise
    result = {
        "ok": completed.returncode == 0,
        "action_count": len(actions),
        "operation_count": operation_count,
        "wall_ms": round((time.perf_counter() - started) * 1000, 3),
        "returncode": completed.returncode,
    }
    if completed_status is not None:
        result["input_status"] = completed_status
    if completed.stderr:
        result["stderr"] = completed.stderr[-500:]
    print(json.dumps(result, sort_keys=True))
    if completed.returncode:
        raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
