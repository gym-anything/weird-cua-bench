from __future__ import annotations

from typing import Any


MECHANIC_ID = "elemental_wayfarer"
DIRECTIONS = {
    "UP": (0, -1),
    "DOWN": (0, 1),
    "LEFT": (-1, 0),
    "RIGHT": (1, 0),
}
INPUT_SOURCES = {"simplified": "direction_button", "full": "keyboard"}


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _bind(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> str | None:
    for key in ("mechanic_id", "task_id", "challenge_id"):
        expected = str(truth.get(key) or "")
        if not expected or str(payload.get(key) or "") != expected:
            return f"payload {key} mismatch"
        if str(public.get(key) or "") != expected:
            return f"public {key} mismatch"
    if truth.get("control_condition") != public.get("control_condition"):
        return "interaction condition mismatch"
    return None


def _contract(truth: dict[str, Any], public: dict[str, Any]) -> tuple[dict[tuple[int, int], dict[str, Any]], tuple[int, int], tuple[int, int], str]:
    hidden_tiles = truth.get("tiles")
    chamber = public.get("chamber") or {}
    public_tiles = chamber.get("tiles")
    if not isinstance(hidden_tiles, list) or not hidden_tiles or public_tiles != hidden_tiles:
        raise ValueError("visible chamber tiles differ from the generated chamber")
    width = int(chamber.get("width", 0))
    height = int(chamber.get("height", 0))
    if width < 5 or height < 5 or len(hidden_tiles) != width * height:
        raise ValueError("chamber dimensions are malformed")
    by_position: dict[tuple[int, int], dict[str, Any]] = {}
    for tile in hidden_tiles:
        if not isinstance(tile, dict):
            raise ValueError("tile is malformed")
        position = (int(tile.get("x", -1)), int(tile.get("y", -1)))
        if not (0 <= position[0] < width and 0 <= position[1] < height) or position in by_position:
            raise ValueError("tile positions are malformed")
        by_position[position] = tile
    start_obj = truth.get("start")
    exit_obj = truth.get("exit")
    if not isinstance(start_obj, dict) or not isinstance(exit_obj, dict):
        raise ValueError("start or exit is malformed")
    start = (int(start_obj["x"]), int(start_obj["y"]))
    exit_position = (int(exit_obj["x"]), int(exit_obj["y"]))
    if (chamber.get("start") or {}) != {"x": start[0], "y": start[1]}:
        raise ValueError("visible start differs from hidden contract")
    if (chamber.get("exit") or {}).get("requires") != exit_obj.get("requires"):
        raise ValueError("visible exit requirement differs from hidden contract")
    if by_position.get(start, {}).get("kind") != "floor" or exit_position not in by_position:
        raise ValueError("start or exit is not on a valid tile")
    condition = truth.get("control_condition") or {}
    interaction = str(condition.get("interaction") or "full")
    if interaction not in INPUT_SOURCES:
        raise ValueError("interaction mode is malformed")
    return by_position, start, exit_position, INPUT_SOURCES[interaction]


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if not all(isinstance(value, dict) for value in (payload, ground_truth, public_state)):
        return _fail("invalid result documents")
    binding_error = _bind(payload, ground_truth, public_state)
    if binding_error:
        return _fail(binding_error)
    try:
        tiles, start, exit_position, expected_source = _contract(ground_truth, public_state)
    except (TypeError, ValueError, KeyError) as exc:
        return _fail(f"invalid Elemental Wayfarer contract: {exc}")

    events = payload.get("actions")
    if not isinstance(events, list) or len(events) > 1200:
        return _fail("movement transcript is missing or too long")
    position = start
    form = "clay"
    collected: list[str] = []
    terminal = False
    outcomes: list[str] = []
    for index, event in enumerate(events, start=1):
        if terminal:
            return _fail("transcript continues after arrival")
        if not isinstance(event, dict) or event.get("sequence") != index:
            return _fail(f"movement {index} has an invalid sequence")
        if event.get("input_source") != expected_source:
            return _fail(f"movement {index} uses the wrong interaction input")
        action = str(event.get("action") or "")
        if action not in DIRECTIONS:
            return _fail(f"movement {index} has an invalid direction")
        if event.get("from") != [position[0], position[1]]:
            return _fail(f"movement {index} starts from the wrong visible position")
        dx, dy = DIRECTIONS[action]
        candidate = (position[0] + dx, position[1] + dy)
        tile = tiles.get(candidate)
        outcome = "blocked_wall"
        next_form = form
        next_position = position
        collected_token: str | None = None
        if tile is not None and tile.get("kind") != "wall":
            if tile.get("kind") == "gate" and tile.get("element") != form:
                outcome = "blocked_gate"
            else:
                next_position = candidate
                outcome = "step"
                if tile.get("kind") in {"token", "decoy"} and str(tile.get("id")) not in collected:
                    collected_token = str(tile["id"])
                    collected.append(collected_token)
                    next_form = str(tile.get("element"))
                    outcome = f"collect_{next_form}"
                if candidate == exit_position:
                    terminal = next_form == str(ground_truth["exit"].get("requires"))
                    if terminal:
                        outcome = "arrive"
        expected = {
            "outcome": outcome,
            "to": [next_position[0], next_position[1]],
            "form_after": next_form,
            "collected_token": collected_token,
        }
        for field, value in expected.items():
            if event.get(field) != value:
                return _fail(f"movement {index} has inconsistent {field}: expected {value!r}")
        position, form = next_position, next_form
        outcomes.append(outcome)

    completed = payload.get("completed") is True
    arrived = position == exit_position and form == str(ground_truth["exit"].get("requires"))
    passed = completed and arrived and terminal
    return {
        "graded": True,
        "passed": passed,
        "feedback": (
            f"wayfarer replay: {len(events)} moves; form {form.upper()}; "
            f"tokens {len(collected)}; exit {'reached' if arrived else 'not reached'}; "
            f"{'PASS' if passed else 'FAIL'}"
        ),
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    return {
        "actions": ground_truth.get("solution_actions") or [],
        "instruction": "Follow the visible corridor and collect each matching elemental token before its seal.",
    }
