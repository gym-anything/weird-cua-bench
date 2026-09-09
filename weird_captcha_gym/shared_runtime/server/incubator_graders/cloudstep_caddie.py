from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "cloudstep_caddie"
_DIRECTIONS = {
    "north": (0, -1),
    "east": (1, 0),
    "south": (0, 1),
    "west": (-1, 0),
}


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _condition(truth: dict[str, Any], public: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    expected = truth.get("control_condition")
    if expected != public.get("control_condition"):
        raise ValueError("public interaction condition differs from the Cloudstep Caddie contract")
    if expected is None:
        return "simplified", None
    interaction = str(expected.get("interaction") or "")
    if interaction not in {"simplified", "full"}:
        raise ValueError("Cloudstep Caddie interaction condition is invalid")
    return interaction, expected


def _tile_map(course: dict[str, Any]) -> dict[tuple[int, int], dict[str, Any]]:
    tiles = course.get("tiles")
    if not isinstance(tiles, list) or not tiles:
        raise ValueError("course has no tiles")
    result: dict[tuple[int, int], dict[str, Any]] = {}
    for tile in tiles:
        if not isinstance(tile, dict):
            raise ValueError("course tile is not an object")
        try:
            key = (int(tile["x"]), int(tile["y"]))
            int(tile["z"])
            surface = str(tile["surface"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("course tile is malformed") from exc
        if key in result:
            raise ValueError("course has duplicate tile coordinates")
        if surface not in {"fairway", "sand", "water", "ramp", "cup"}:
            raise ValueError("course tile has an unknown surface")
        result[key] = tile
    return result


def _state(position: dict[str, Any], used: list[str], tile_map: dict[tuple[int, int], dict[str, Any]]) -> dict[str, Any]:
    x, y, z = int(position["x"]), int(position["y"]), int(position["z"])
    tile = tile_map.get((x, y))
    if tile is None:
        raise ValueError("ball is outside the visible course")
    return {"x": x, "y": y, "z": z, "surface": str(tile["surface"]), "used_card_ids": list(used)}


def _transition(
    before: dict[str, Any],
    card: dict[str, Any],
    direction: str,
    course: dict[str, Any],
    tile_map: dict[tuple[int, int], dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    vector = _DIRECTIONS.get(direction)
    if vector is None:
        return None, "direction is invalid"
    kind = str(card.get("kind") or "")
    try:
        distance = int(card["distance"])
    except (KeyError, TypeError, ValueError):
        return None, "card distance is invalid"
    if kind not in {"roll", "chip"} or distance < 1 or distance > 3:
        return None, "card rule is invalid"
    x, y, z = int(before["x"]), int(before["y"]), int(before["z"])
    origin_x, origin_y = x, y
    dx, dy = vector
    rules = course.get("rules") or {}
    if kind == "roll":
        if before.get("surface") == "sand" and distance > int(rules.get("sand_roll_limit", 1)):
            return None, "sand stops a long roll; chip or use a shorter roll"
        for offset in range(1, distance + 1):
            tile = tile_map.get((origin_x + dx * offset, origin_y + dy * offset))
            if tile is None or str(tile.get("surface")) == "water":
                return None, "a roll cannot cross water or a missing tile"
            next_z = int(tile["z"])
            height_change = next_z - z
            if abs(height_change) > int(rules.get("roll_max_step_height", 1)):
                return None, "the riser is too high for a roll"
            if height_change > 0 and str(tile.get("surface")) != "ramp":
                return None, "an uphill roll needs a visible ramp"
            if str(tile.get("surface")) == "sand" and offset < distance:
                return None, "the ball settles in sand before the card distance ends"
            x, y, z = int(tile["x"]), int(tile["y"]), next_z
    else:
        tile = tile_map.get((x + dx * distance, y + dy * distance))
        if tile is None or str(tile.get("surface")) == "water":
            return None, "a chip needs a visible landing tile"
        if abs(int(tile["z"]) - z) > int(rules.get("chip_clearance", 1)):
            return None, "the landing height is beyond this chip"
        x, y, z = int(tile["x"]), int(tile["y"]), int(tile["z"])
    return _state({"x": x, "y": y, "z": z}, list(before["used_card_ids"]), tile_map), None


def replay_events(events: list[dict[str, Any]], truth: dict[str, Any], public: dict[str, Any], interaction: str) -> tuple[dict[str, Any], str | None]:
    course = public["course"]
    tile_map = _tile_map(course)
    cards = list(public["cards"])
    card_by_id = {str(card.get("id")): card for card in cards}
    if len(card_by_id) != len(cards) or not cards:
        return {}, "card hand is malformed"
    start = course.get("start") or {}
    current = _state(start, [], tile_map)
    expected_source = {
        "simplified": "card_then_direction_buttons",
        "full": "card_drag_to_compass",
    }[interaction]
    terminal = False
    certificate: dict[str, Any] | None = None
    for sequence, item in enumerate(events, 1):
        if not isinstance(item, dict) or item.get("seq") != sequence:
            return current, f"event {sequence} has invalid sequence numbering"
        if terminal:
            return current, f"event {sequence} occurs after certification"
        kind = str(item.get("type") or "")
        if kind == "stroke":
            if item.get("input_source") != expected_source:
                return current, "stroke uses the wrong interaction input"
            card_id = str(item.get("card_id") or "")
            card = card_by_id.get(card_id)
            if card is None:
                return current, "stroke names an unknown card"
            if card_id in current["used_card_ids"]:
                return current, "a movement card was used twice"
            before = dict(current)
            if item.get("before") != before:
                return current, f"stroke {sequence} starts from a false visible state"
            after, error = _transition(current, card, str(item.get("direction") or ""), course, tile_map)
            if error or after is None:
                return current, f"stroke {sequence} is illegal: {error}"
            after["used_card_ids"] = [*current["used_card_ids"], card_id]
            if item.get("after") != after:
                return current, f"stroke {sequence} reports a false settled position"
            current = after
        elif kind == "certify":
            certificate = item
            terminal = True
        else:
            return current, f"event {sequence} has unknown type {kind!r}"
    if certificate is None:
        return current, "course was never certified"
    cup = course.get("cup") or {}
    expected_used = [str(card.get("id")) for card in cards]
    accepted = (
        current["x"] == int(cup.get("x"))
        and current["y"] == int(cup.get("y"))
        and current["z"] == int(cup.get("z"))
        and set(current["used_card_ids"]) == set(expected_used)
        and len(current["used_card_ids"]) == len(expected_used)
    )
    if certificate.get("input_source") != "certify_button":
        return current, "course certificate uses an invalid input source"
    if certificate.get("ball") != current or certificate.get("used_card_ids") != current["used_card_ids"] or bool(certificate.get("accepted")) != accepted:
        return current, "course certificate disagrees with the independent replay"
    return {**current, "accepted": accepted}, None


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if payload.get("mechanic_id") != MECHANIC_ID or ground_truth.get("mechanic_id") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    task_id = str(ground_truth.get("task_id") or "")
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if not task_id or payload.get("task_id") != task_id or public_state.get("task_id") != task_id:
        return _fail("task identity mismatch")
    if not challenge_id or payload.get("challenge_id") != challenge_id or public_state.get("challenge_id") != challenge_id:
        return _fail("stale or cross-seed challenge")
    try:
        interaction, condition = _condition(ground_truth, public_state)
        if str(payload.get("interaction_mode") or interaction) != interaction:
            return _fail("submitted interaction mode does not match the task")
        for field in ("course", "cards", "palette"):
            if public_state.get(field) != ground_truth.get(field):
                return _fail(f"public/private {field} contract skew")
        events = payload.get("events")
        if not isinstance(events, list) or not 1 <= len(events) <= 80:
            return _fail("card course transcript is missing or outside limits")
        state, error = replay_events(events, ground_truth, public_state, interaction)
    except (KeyError, TypeError, ValueError, IndexError, OverflowError) as exc:
        return _fail(f"invalid Cloudstep Caddie transcript: {exc}")
    if error:
        return _fail(error)
    passed = state.get("accepted") is True and payload.get("completed") is True
    used = len(state.get("used_card_ids") or [])
    total = len(public_state.get("cards") or [])
    return {
        "graded": True,
        "passed": passed,
        "score": 100 if passed else 0,
        "feedback": f"sunken ball; exact hand used {used}/{total}" if passed else f"ball at ({state.get('x')},{state.get('y')},{state.get('z')}); cards {used}/{total}",
    }


__all__ = ["MECHANIC_ID", "grade", "replay_events"]
