from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "weird_captcha_gym/shared_scripts/inject_input_batch.py"
)
SPEC = importlib.util.spec_from_file_location("inject_input_batch", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_builds_one_ordered_xdotool_command_for_complete_gesture() -> None:
    actions = [
        {"mouse": {"move": [10.2, 20.8]}},
        {"mouse": {"buttons": {"left_down": True}}},
        {"action": "wait", "time": 0.61},
        {"mouse": {"move": [80, 20]}},
        {"mouse": {"buttons": {"left_up": True}}},
        {"mouse": {"left_click": [30, 40]}},
    ]

    command, operations = MODULE.build_xdotool_command(actions)

    assert command == [
        "xdotool",
        "mousemove", "10", "21",
        "mousedown", "1",
        "sleep", "0.61",
        "mousemove", "80", "20",
        "mouseup", "1",
        "mousemove", "30", "40", "click", "1",
    ]
    assert operations == 6


def test_rejects_shell_payload_and_unbounded_wait() -> None:
    with pytest.raises(ValueError, match="supported mouse"):
        MODULE.build_xdotool_command([{"mouse": {"shell": "touch /tmp/no"}}])
    with pytest.raises(ValueError, match="between 0 and 30"):
        MODULE.build_xdotool_command([{"action": "wait", "time": 31}])
