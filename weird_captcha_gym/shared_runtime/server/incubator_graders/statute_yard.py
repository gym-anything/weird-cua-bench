from __future__ import annotations

from typing import Any


MECHANIC_ID = "statute_yard"
PROFILE_NAMES = {
    1: "yard_l1",
    2: "yard_l2",
    3: "yard_original_l4",
    4: "yard_l4",
    5: "yard_l5",
}
DIRECTIONS = {
    "UP": (0, -1),
    "RIGHT": (1, 0),
    "DOWN": (0, 1),
    "LEFT": (-1, 0),
}
SUBJECTS = {"STATUE", "LANTERN", "GATE", "CISTERN"}
PROPERTIES = {"YOU", "EXIT", "DEADLY", "STOP"}


def _fail(feedback: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": feedback}


def _point(item: Any) -> tuple[int, int] | None:
    if not isinstance(item, dict):
        return None
    x, y = item.get("x"), item.get("y")
    if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, int) or not isinstance(y, int):
        return None
    return x, y


def _validate_yard(yard: Any) -> str | None:
    if not isinstance(yard, dict):
        return "yard is missing"
    width, height = yard.get("width"), yard.get("height")
    if isinstance(width, bool) or isinstance(height, bool) or not isinstance(width, int) or not isinstance(height, int):
        return "yard dimensions are malformed"
    if not 7 <= width <= 14 or not 7 <= height <= 14:
        return "yard dimensions are outside limits"
    walls_raw = yard.get("walls")
    entities = yard.get("entities")
    words = yard.get("words")
    if not isinstance(walls_raw, list) or not isinstance(entities, list) or not isinstance(words, list):
        return "yard collections are malformed"
    walls: set[tuple[int, int]] = set()
    for value in walls_raw:
        if not isinstance(value, list) or len(value) != 2 or not all(isinstance(v, int) and not isinstance(v, bool) for v in value):
            return "wall coordinate is malformed"
        walls.add((value[0], value[1]))
    if len(walls) != len(walls_raw):
        return "wall coordinates are duplicated"
    expected_border = {
        (x, y)
        for y in range(height)
        for x in range(width)
        if x in {0, width - 1} or y in {0, height - 1}
    }
    if not expected_border <= walls:
        return "yard border is open"
    entity_ids: set[str] = set()
    for entity in entities:
        identifier = str(entity.get("id") or "") if isinstance(entity, dict) else ""
        kind = str(entity.get("kind") or "") if isinstance(entity, dict) else ""
        position = _point(entity)
        if not identifier or identifier in entity_ids or kind not in SUBJECTS or position is None:
            return "yard entity is malformed"
        if position in walls:
            return "yard entity begins in a wall"
        entity_ids.add(identifier)
    word_ids: set[str] = set()
    word_positions: set[tuple[int, int]] = set()
    for word in words:
        identifier = str(word.get("id") or "") if isinstance(word, dict) else ""
        text = str(word.get("text") or "") if isinstance(word, dict) else ""
        position = _point(word)
        if (
            not identifier
            or identifier in word_ids
            or text not in SUBJECTS | PROPERTIES | {"IS"}
            or position is None
            or position in walls
            or position in word_positions
        ):
            return "yard word-stone is malformed"
        word_ids.add(identifier)
        word_positions.add(position)
    if not 6 <= len(words) <= 18 or not 2 <= len(entities) <= 12:
        return "yard object count is outside limits"
    return None


def _active_rules(words: list[dict[str, Any]], positions: list[tuple[int, int]]) -> tuple[str, ...]:
    at = {position: words[index]["text"] for index, position in enumerate(positions)}
    rules: set[str] = set()
    for index, word in enumerate(words):
        if word["text"] != "IS":
            continue
        x, y = positions[index]
        for before, after in (((x - 1, y), (x + 1, y)), ((x, y - 1), (x, y + 1))):
            subject, prop = at.get(before), at.get(after)
            if subject in SUBJECTS and prop in PROPERTIES:
                rules.add(f"{subject} IS {prop}")
    return tuple(sorted(rules))


def _controlled(rules: tuple[str, ...]) -> set[str]:
    return {rule.removesuffix(" IS YOU") for rule in rules if rule.endswith(" IS YOU")}


def _properties(rules: tuple[str, ...], prop: str) -> set[str]:
    suffix = f" IS {prop}"
    return {rule.removesuffix(suffix) for rule in rules if rule.endswith(suffix)}


def _snapshot(
    yard: dict[str, Any],
    entity_positions: list[tuple[int, int]],
    word_positions: list[tuple[int, int]],
    broken: set[str],
) -> dict[str, Any]:
    rules = _active_rules(yard["words"], word_positions)
    return {
        "entities": [
            {"id": entity["id"], "x": position[0], "y": position[1]}
            for entity, position in zip(yard["entities"], entity_positions)
        ],
        "words": [
            {"id": word["id"], "x": position[0], "y": position[1]}
            for word, position in zip(yard["words"], word_positions)
        ],
        "active_rules": list(rules),
        "controlled_kinds": sorted(_controlled(rules)),
        "broken_opening_rules": sorted(broken),
    }


def _won(yard: dict[str, Any], entity_positions: list[tuple[int, int]], rules: tuple[str, ...]) -> bool:
    controlled = _controlled(rules)
    exits = _properties(rules, "EXIT")
    controlled_positions = {
        position
        for entity, position in zip(yard["entities"], entity_positions)
        if entity["kind"] in controlled
    }
    return bool(controlled_positions) and any(
        entity["kind"] in exits and position in controlled_positions
        for entity, position in zip(yard["entities"], entity_positions)
    )


def _deadly(yard: dict[str, Any], entity_positions: list[tuple[int, int]], rules: tuple[str, ...]) -> bool:
    controlled = _controlled(rules)
    hazards = _properties(rules, "DEADLY")
    controlled_positions = {
        position
        for entity, position in zip(yard["entities"], entity_positions)
        if entity["kind"] in controlled
    }
    return any(
        entity["kind"] in hazards and position in controlled_positions
        for entity, position in zip(yard["entities"], entity_positions)
    )


def _move(
    yard: dict[str, Any],
    entity_positions: list[tuple[int, int]],
    word_positions: list[tuple[int, int]],
    direction: str,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]], tuple[str, ...], str]:
    dx, dy = DIRECTIONS[direction]
    walls = {tuple(point) for point in yard["walls"]}
    rules_before = _active_rules(yard["words"], word_positions)
    controlled = _controlled(rules_before)
    stopped = _properties(rules_before, "STOP")
    next_entities = list(entity_positions)
    next_words = list(word_positions)
    pushed = False
    moved = False
    controlled_indices = [
        index for index, entity in enumerate(yard["entities"]) if entity["kind"] in controlled
    ]
    for entity_index in controlled_indices:
        x, y = next_entities[entity_index]
        target = (x + dx, y + dy)
        if target in walls:
            continue
        word_index = next((index for index, position in enumerate(next_words) if position == target), None)
        if word_index is not None:
            chain: list[int] = []
            cursor = target
            while True:
                found = next((index for index, position in enumerate(next_words) if position == cursor), None)
                if found is None:
                    break
                chain.append(found)
                cursor = (cursor[0] + dx, cursor[1] + dy)
            if cursor in walls or any(
                position == cursor and yard["entities"][index]["kind"] in stopped
                for index, position in enumerate(next_entities)
            ):
                continue
            for index in reversed(chain):
                wx, wy = next_words[index]
                next_words[index] = (wx + dx, wy + dy)
            pushed = True
        if any(
            position == target and yard["entities"][index]["kind"] in stopped
            for index, position in enumerate(next_entities)
        ):
            continue
        next_entities[entity_index] = target
        moved = True
    rules_after = _active_rules(yard["words"], next_words)
    if _deadly(yard, next_entities, rules_after):
        outcome = "deadly_contact"
    elif _won(yard, next_entities, rules_after):
        outcome = "exit_reached"
    elif pushed:
        outcome = "law_shift"
    elif moved:
        outcome = "move"
    elif not controlled_indices:
        outcome = "no_subject_bound"
    else:
        outcome = "blocked"
    return next_entities, next_words, rules_after, outcome


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if str(payload.get("mechanic_id") or "") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    if str(ground_truth.get("mechanic_id") or "") != MECHANIC_ID or str(public_state.get("mechanic_id") or "") != MECHANIC_ID:
        return _fail("statute-yard contract mechanic mismatch")
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if not challenge_id or str(payload.get("challenge_id") or "") != challenge_id:
        return _fail("stale challenge")
    if str(public_state.get("challenge_id") or "") != challenge_id:
        return _fail("public challenge mismatch")
    task_id = str(ground_truth.get("task_id") or "")
    if not task_id or str(payload.get("task_id") or "") != task_id or str(public_state.get("task_id") or "") != task_id:
        return _fail("task identity mismatch")
    yard = ground_truth.get("yard")
    if yard != public_state.get("yard"):
        return _fail("public and hidden yard geometry disagree")
    yard_error = _validate_yard(yard)
    if yard_error:
        return _fail(f"invalid yard contract: {yard_error}")
    truth_condition = ground_truth.get("control_condition")
    if truth_condition != public_state.get("control_condition"):
        return _fail("public interaction condition differs from yard contract")
    interaction = str((truth_condition or {}).get("interaction") or "full")
    expected_source = {"simplified": "direction_buttons", "full": "keyboard"}.get(interaction)
    if expected_source is None:
        return _fail("invalid statute-yard interaction condition")
    parameters = dict((truth_condition or {}).get("difficulty_parameters") or {})
    level = int((truth_condition or {}).get("difficulty") or ground_truth.get("profile") or 3)
    if level not in PROFILE_NAMES or (parameters and parameters.get("profile") != PROFILE_NAMES[level]):
        return _fail("difficulty profile differs from yard contract")

    actions = payload.get("actions")
    if not isinstance(actions, list) or not 1 <= len(actions) <= 500:
        return _fail("movement transcript is missing or outside limits")
    opening_rules = set(ground_truth.get("opening_rules") or [])
    if not opening_rules or opening_rules != set(public_state.get("opening_rules") or []):
        return _fail("opening rule ledger is malformed")
    initial_entities = [_point(entity) for entity in yard["entities"]]
    initial_words = [_point(word) for word in yard["words"]]
    if any(point is None for point in initial_entities + initial_words):
        return _fail("initial yard coordinates are malformed")
    entity_positions = [point for point in initial_entities if point is not None]
    word_positions = [point for point in initial_words if point is not None]
    broken: set[str] = set()
    resets = 0
    terminal = False
    won = False
    deadly = False

    for index, event in enumerate(actions, start=1):
        if not isinstance(event, dict) or event.get("seq") != index:
            return _fail(f"action {index} has an invalid sequence")
        if terminal:
            return _fail("transcript continues after a terminal yard state")
        action_type = str(event.get("type") or "")
        if action_type == "reset":
            if event.get("input_source") != expected_source:
                return _fail(f"action {index} uses the wrong interaction input")
            entity_positions = list(initial_entities)  # type: ignore[arg-type]
            word_positions = list(initial_words)  # type: ignore[arg-type]
            broken = set()
            resets += 1
            expected_outcome = "reset"
        elif action_type == "move":
            if event.get("input_source") != expected_source:
                return _fail(f"action {index} uses the wrong interaction input")
            direction = str(event.get("direction") or "").upper()
            if direction not in DIRECTIONS:
                return _fail(f"action {index} has an invalid direction")
            entity_positions, word_positions, rules, expected_outcome = _move(
                yard, entity_positions, word_positions, direction
            )
            broken |= opening_rules - set(rules)
            deadly = expected_outcome == "deadly_contact"
            won = expected_outcome == "exit_reached"
            terminal = deadly or won
        else:
            return _fail(f"action {index} has an invalid type")
        if event.get("outcome") != expected_outcome:
            return _fail(
                f"action {index} outcome differs from replay: expected {expected_outcome!r}, got {event.get('outcome')!r}"
            )

    final_snapshot = _snapshot(yard, entity_positions, word_positions, broken)
    if payload.get("final_state") != final_snapshot:
        return _fail("submitted final yard does not match independent replay")
    if payload.get("reset_count") != resets:
        return _fail("submitted reset count does not match replay")
    required_breaks = int(ground_truth.get("required_opening_law_breaks") or 1)
    completed = payload.get("completed") is True
    passed = completed and won and not deadly and len(broken) >= required_breaks
    return {
        "graded": True,
        "passed": passed,
        "score": 100 if passed else 0,
        "feedback": (
            f"active laws {len(final_snapshot['active_rules'])}; opening laws broken {len(broken)}/{required_breaks}; "
            f"moves {sum(1 for action in actions if action.get('type') == 'move')}; resets {resets}; "
            f"exit predicate {'true' if won else 'false'}"
        ),
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    return {
        "route": list(ground_truth.get("solution") or []),
        "minimum_solution_steps": ground_truth.get("minimum_solution_steps"),
        "instruction": "Issue each direction in order, then seal the verdict.",
        "answers": [],
    }
