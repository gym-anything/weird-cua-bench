from __future__ import annotations

from collections import deque
import copy
import hashlib
import json
import random
from typing import Any, Callable


MECHANIC_ID = "statute_yard"
DIRECTIONS: dict[str, tuple[int, int]] = {
    "UP": (0, -1),
    "RIGHT": (1, 0),
    "DOWN": (0, 1),
    "LEFT": (-1, 0),
}
SUBJECTS = {"STATUE", "LANTERN", "GATE", "CISTERN"}
PROPERTIES = {"YOU", "EXIT", "DEADLY", "STOP"}
PALETTES = ("verdigris", "umber", "moonstone", "moss")

State = tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...], frozenset[str]]
_BREAK_CERTIFICATE_CACHE: dict[str, dict[str, Any]] = {}

PROFILE_NAMES = {
    1: "yard_l1",
    2: "yard_l2",
    3: "yard_original_l4",
    4: "yard_l4",
    5: "yard_l5",
}
SOLUTION_BANDS = {
    1: (5, 8),
    2: (9, 10),
    3: (11, 16),
    4: (17, 20),
    5: (21, 24),
}
REQUIRED_TRACE_FIELDS = {
    1: ("deadly_break_step",),
    2: ("deadly_break_step", "exit_make_step"),
    3: ("deadly_break_step", "transfers"),
    4: ("deadly_break_step", "transfers", "exit_make_step"),
    5: ("deadly_break_step", "transfers", "exit_make_step", "stop_break_step"),
}

# These are decision-bearing placements. They are deliberately independent rather
# than zipped into three authored layouts, and each generated combination is
# accepted only after the exhaustive solver checks the level's operation and
# shortest-route band.
LOW_LEVEL_SPAWNS: dict[int, dict[str, tuple[tuple[int, int], ...]]] = {
    1: {
        "statue": ((1, 3), (2, 3), (1, 4), (2, 4), (3, 4)),
        "gate": ((5, 2), (6, 2), (7, 2), (5, 3), (6, 3), (7, 3), (5, 4), (6, 4), (7, 4)),
    },
    2: {
        "statue": ((1, 3), (2, 3), (1, 4), (2, 4), (3, 4)),
        "gate": ((7, 3), (8, 3), (6, 4), (7, 4), (8, 4), (6, 5), (7, 5), (8, 5)),
    },
    3: {
        "statue": ((1, 5), (2, 5), (3, 5), (1, 6), (2, 6), (3, 6), (1, 7), (2, 7), (3, 7)),
        "lantern": ((9, 5), (10, 5), (11, 5), (9, 6), (10, 6), (11, 6), (9, 7), (10, 7), (11, 7)),
        "gate": ((9, 2), (10, 2), (11, 2), (9, 3), (10, 3), (11, 3), (9, 4), (10, 4), (11, 4)),
    },
}
LOW_LEVEL_BAFFLES: dict[int, tuple[tuple[int, int], ...]] = {
    1: ((5, 5), (6, 5), (7, 5), (5, 4), (6, 4), (7, 4)),
    2: (),
    3: (),
}
LOW_LEVEL_WORD_VARIANTS: dict[int, tuple[dict[str, tuple[int, int]], ...]] = {
    2: (
        {"gate-noun": (6, 3), "gate-is": (7, 2), "exit-property": (8, 2)},
        {"gate-noun": (5, 3), "gate-is": (6, 2), "exit-property": (7, 2)},
        {"gate-noun": (6, 4), "gate-is": (7, 3), "exit-property": (8, 3)},
        {"gate-noun": (5, 4), "gate-is": (6, 3), "exit-property": (7, 3)},
        {"gate-noun": (6, 2), "gate-is": (7, 3), "exit-property": (7, 4)},
        {"gate-noun": (5, 2), "gate-is": (6, 3), "exit-property": (6, 4)},
    ),
}

# These pairs were derived from the semantic scaffold, not from solution paths.
# Every entry is still re-solved at generation time. Combined with four annex
# topologies and two orientations, each higher level has at least 192
# decision-bearing candidates before palette/crack decoration.
HIGH_LEVEL_SPAWNS: dict[int, tuple[tuple[tuple[int, int], tuple[int, int], tuple[int, int]], ...]] = {
    4: (
        ((1, 6), (10, 3), (11, 3)), ((1, 6), (10, 3), (12, 3)),
        ((1, 6), (10, 3), (12, 4)), ((1, 6), (11, 3), (10, 3)),
        ((1, 6), (11, 3), (12, 3)), ((1, 6), (11, 3), (11, 4)),
        ((1, 6), (11, 3), (12, 4)), ((1, 6), (11, 3), (12, 5)),
        ((1, 6), (12, 3), (10, 3)), ((1, 6), (12, 3), (11, 3)),
        ((1, 6), (12, 3), (10, 4)), ((1, 6), (12, 3), (11, 4)),
        ((1, 6), (12, 3), (12, 4)), ((1, 6), (12, 3), (11, 5)),
        ((1, 6), (12, 3), (12, 5)), ((1, 6), (10, 4), (12, 3)),
        ((1, 6), (11, 4), (11, 3)), ((1, 6), (11, 4), (12, 3)),
        ((1, 6), (11, 4), (12, 4)), ((1, 6), (12, 4), (10, 3)),
        ((1, 6), (12, 4), (11, 3)), ((1, 6), (12, 4), (12, 3)),
        ((1, 6), (12, 4), (11, 4)), ((1, 6), (12, 4), (12, 5)),
    ),
    5: (
        ((1, 6), (11, 3), (12, 3)), ((1, 6), (12, 3), (11, 3)),
        ((1, 6), (12, 3), (12, 4)), ((1, 6), (11, 4), (12, 4)),
        ((1, 6), (12, 4), (10, 3)), ((1, 6), (12, 4), (12, 3)),
        ((1, 6), (12, 4), (11, 4)), ((1, 6), (12, 4), (12, 5)),
        ((1, 6), (11, 5), (12, 5)), ((1, 6), (12, 5), (10, 4)),
        ((1, 6), (12, 5), (12, 4)), ((1, 6), (12, 5), (11, 5)),
        ((1, 7), (10, 3), (12, 3)), ((1, 7), (11, 3), (12, 3)),
        ((1, 7), (11, 3), (12, 4)), ((1, 7), (12, 3), (10, 3)),
        ((1, 7), (12, 3), (11, 3)), ((1, 7), (12, 3), (11, 4)),
        ((1, 7), (12, 3), (12, 4)), ((1, 7), (12, 3), (12, 5)),
        ((1, 7), (10, 4), (12, 4)), ((1, 7), (11, 4), (10, 3)),
        ((1, 7), (11, 4), (12, 3)), ((1, 7), (11, 4), (12, 4)),
    ),
}
ANNEX_OPENINGS: tuple[tuple[tuple[int, int], ...], ...] = (
    (),
    tuple((x, 6) for x in range(5, 9)),
    tuple((x, y) for x in range(5, 9) for y in (6, 7)),
    tuple((x, y) for x in (5, 6) for y in (6, 7, 8)),
)


def _word(identifier: str, text: str, x: int, y: int) -> dict[str, Any]:
    return {"id": identifier, "text": text, "x": x, "y": y}


def _entity(identifier: str, kind: str, x: int, y: int) -> dict[str, Any]:
    return {"id": identifier, "kind": kind, "x": x, "y": y}


def _border(width: int, height: int) -> set[tuple[int, int]]:
    return {
        (x, y)
        for y in range(height)
        for x in range(width)
        if x in {0, width - 1} or y in {0, height - 1}
    }


def _cistern_column(x: int, height: int) -> list[dict[str, Any]]:
    return [_entity(f"cistern-{y}", "CISTERN", x, y) for y in range(1, height - 1)]


def _template(level: int, variant: int) -> dict[str, Any]:
    variant %= 3
    if level == 1:
        width, height = 9, 7
        statue_starts = ((2, 4), (1, 4), (2, 3))
        gate_starts = ((6, 3), (6, 4), (7, 3))
        words = [
            _word("cistern-noun", "CISTERN", 1, 2),
            _word("cistern-is", "IS", 2, 2),
            _word("deadly-property", "DEADLY", 3, 2),
            _word("statue-noun", "STATUE", 1, 5),
            _word("statue-is", "IS", 2, 5),
            _word("you-property", "YOU", 3, 5),
            _word("gate-noun", "GATE", 5, 1),
            _word("gate-is", "IS", 6, 1),
            _word("exit-property", "EXIT", 7, 1),
        ]
        entities = [
            _entity("statue", "STATUE", *statue_starts[variant]),
            _entity("gate", "GATE", *gate_starts[variant]),
            *_cistern_column(4, height),
        ]
        walls = _border(width, height)
        title = "Break one law to cross the cistern and reach the exit."
    elif level == 2:
        width, height = 10, 7
        statue_starts = ((2, 4), (1, 4), (2, 3))
        gate_starts = ((7, 4), (8, 4), (7, 5))
        words = [
            _word("cistern-noun", "CISTERN", 1, 2),
            _word("cistern-is", "IS", 2, 2),
            _word("deadly-property", "DEADLY", 3, 2),
            _word("statue-noun", "STATUE", 1, 5),
            _word("statue-is", "IS", 2, 5),
            _word("you-property", "YOU", 3, 5),
            _word("gate-noun", "GATE", 6, 3),
            _word("gate-is", "IS", 7, 2),
            _word("exit-property", "EXIT", 8, 2),
        ]
        entities = [
            _entity("statue", "STATUE", *statue_starts[variant]),
            _entity("gate", "GATE", *gate_starts[variant]),
            *_cistern_column(4, height),
        ]
        walls = _border(width, height)
        title = "Break the deadly law, then enact an exit law."
    elif level == 3:
        # This is the exact original uncontrolled L4 decision scaffold. It was
        # reclassified rather than edited to defend the previous label.
        width, height = 13, 9
        statue_starts = ((2, 6), (1, 6), (2, 7))
        lantern_starts = ((10, 6), (9, 7), (11, 6))
        gate_starts = ((10, 3), (11, 2), (9, 2))
        words = [
            _word("cistern-noun", "CISTERN", 1, 2),
            _word("cistern-is", "IS", 2, 2),
            _word("deadly-property", "DEADLY", 3, 2),
            _word("lantern-noun", "LANTERN", 5, 3),
            _word("statue-noun", "STATUE", 6, 3),
            _word("control-is", "IS", 6, 4),
            _word("you-property", "YOU", 6, 5),
            _word("gate-noun", "GATE", 9, 1),
            _word("gate-is", "IS", 10, 1),
            _word("exit-property", "EXIT", 11, 1),
            _word("stop-decoy", "STOP", 2, 7),
            _word("exit-decoy", "EXIT", 7, 7),
        ]
        entities = [
            _entity("statue", "STATUE", *statue_starts[variant]),
            _entity("lantern", "LANTERN", *lantern_starts[variant]),
            _entity("gate", "GATE", *gate_starts[variant]),
            *_cistern_column(4, height),
        ]
        walls = _border(width, height) | {(8, y) for y in range(1, height - 1)}
        title = "Break the cistern law, cross, then transfer control to the lantern."
    elif level in {4, 5}:
        width, height = 14, 10
        statue_starts = ((1, 6), (1, 7), (2, 7))
        lantern_starts = ((11, 3), (12, 3), (12, 4))
        gate_starts = ((12, 3), (11, 3), (12, 5))
        words = [
            _word("cistern-noun", "CISTERN", 1, 2),
            _word("cistern-is", "IS", 2, 2),
            _word("deadly-property", "DEADLY", 3, 2),
            _word("lantern-noun", "LANTERN", 6, 3),
            _word("statue-noun", "STATUE", 7, 3),
            _word("control-is", "IS", 7, 4),
            _word("you-property", "YOU", 7, 5),
            _word("gate-exit-noun", "GATE", 10, 6),
            _word("gate-exit-is", "IS", 11, 7),
            _word("exit-property", "EXIT", 12, 7),
        ]
        if level == 5:
            words[7:7] = [
                _word("gate-stop-noun", "GATE", 10, 2),
                _word("gate-stop-is", "IS", 11, 2),
                _word("stop-property", "STOP", 12, 2),
            ]
        entities = [
            _entity("statue", "STATUE", *statue_starts[variant]),
            _entity("lantern", "LANTERN", *lantern_starts[variant]),
            _entity("gate", "GATE", *gate_starts[variant]),
            _entity("cistern-crossing", "CISTERN", 4, 3),
        ]
        allowed = {
            (2, y) for y in range(3, 9)
        } | {
            (3, 1), (3, 2), (3, 3), (4, 3), (5, 3), (6, 3), (7, 3), (8, 3),
            (1, 2), (2, 2), (7, 4), (7, 5),
        } | {
            (x, y) for x in range(10, 13) for y in range(1, 9)
        }
        # The branching annex adds real navigation choices around the law work,
        # while the single cistern aperture remains the mandatory crossing.
        allowed |= {
            (x, y) for x in range(1, 4) for y in range(1, 9)
        } | {
            (x, y) for x in range(5, 9) for y in range(1, 6)
        }
        interior = {(x, y) for x in range(1, width - 1) for y in range(1, height - 1)}
        walls = _border(width, height) | (interior - allowed)
        title = (
            "Break, transfer, enact the exit, and repeal the gate's stop law."
            if level == 5
            else "Break, transfer control, and enact the exit law."
        )
    else:
        raise ValueError(f"unsupported difficulty {level}")

    return {
        "width": width,
        "height": height,
        "walls": [list(point) for point in sorted(walls)],
        "entities": entities,
        "words": words,
        "objective": title,
        "profile": level,
        "legacy_source_profile": 4 if level == 3 else None,
    }


def _transpose(template: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(template)
    result["width"], result["height"] = template["height"], template["width"]
    result["walls"] = sorted([[y, x] for x, y in template["walls"]])
    for collection in (result["entities"], result["words"]):
        for item in collection:
            item["x"], item["y"] = item["y"], item["x"]
    result["orientation"] = "transposed"
    return result


def _place_entity(template: dict[str, Any], identifier: str, point: tuple[int, int]) -> None:
    entity = next(item for item in template["entities"] if item["id"] == identifier)
    entity["x"], entity["y"] = point


def _low_level_candidate(level: int, rng: random.Random) -> tuple[dict[str, Any], dict[str, Any]]:
    template = _template(level, 0)
    word_variant: dict[str, list[int]] = {}
    if level in LOW_LEVEL_WORD_VARIANTS:
        for identifier, point in rng.choice(LOW_LEVEL_WORD_VARIANTS[level]).items():
            word = next(item for item in template["words"] if item["id"] == identifier)
            word["x"], word["y"] = point
            word_variant[identifier] = list(point)
    selected: dict[str, tuple[int, int]] = {}
    occupied: set[tuple[int, int]] = {
        tuple(point) for point in word_variant.values()
    }
    for identifier, points in LOW_LEVEL_SPAWNS[level].items():
        available = [point for point in points if point not in occupied]
        point = rng.choice(available)
        _place_entity(template, identifier, point)
        selected[identifier] = point
        occupied.add(point)

    word_cells = {(int(word["x"]), int(word["y"])) for word in template["words"]}
    wall_cells = {tuple(point) for point in template["walls"]}
    baffle_slots = [
        point
        for point in LOW_LEVEL_BAFFLES[level]
        if point not in occupied and point not in word_cells and point not in wall_cells
    ]
    rng.shuffle(baffle_slots)
    baffles = tuple(sorted(baffle_slots[: rng.randrange(min(3, len(baffle_slots)) + 1)]))
    wall_cells.update(baffles)
    template["walls"] = [list(point) for point in sorted(wall_cells)]
    return template, {
        "spawn_positions": {key: list(value) for key, value in sorted(selected.items())},
        "routing_baffles": [list(point) for point in baffles],
        "word_positions": word_variant,
    }


def _high_level_candidate(level: int, rng: random.Random) -> tuple[dict[str, Any], dict[str, Any]]:
    template = _template(level, 0)
    spawn_index = rng.randrange(len(HIGH_LEVEL_SPAWNS[level]))
    statue, lantern, gate = HIGH_LEVEL_SPAWNS[level][spawn_index]
    for identifier, point in (("statue", statue), ("lantern", lantern), ("gate", gate)):
        _place_entity(template, identifier, point)

    topology_index = rng.randrange(len(ANNEX_OPENINGS))
    walls = {tuple(point) for point in template["walls"]}
    walls.difference_update(ANNEX_OPENINGS[topology_index])
    template["walls"] = [list(point) for point in sorted(walls)]
    return template, {
        "spawn_index": spawn_index,
        "spawn_positions": {
            "statue": list(statue),
            "lantern": list(lantern),
            "gate": list(gate),
        },
        "annex_topology": topology_index,
        "annex_openings": [list(point) for point in ANNEX_OPENINGS[topology_index]],
    }


def _decision_signature(template: dict[str, Any]) -> str:
    decision = {
        "width": template["width"],
        "height": template["height"],
        "walls": template["walls"],
        "entities": template["entities"],
        "words": template["words"],
    }
    encoded = json.dumps(decision, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _position_tuple(items: list[dict[str, Any]]) -> tuple[tuple[int, int], ...]:
    return tuple((int(item["x"]), int(item["y"])) for item in items)


def _active_rules_for_positions(
    words: list[dict[str, Any]], positions: tuple[tuple[int, int], ...]
) -> tuple[str, ...]:
    at = {point: words[index]["text"] for index, point in enumerate(positions)}
    rules: set[str] = set()
    for index, word in enumerate(words):
        if word["text"] != "IS":
            continue
        x, y = positions[index]
        for before, after in (((x - 1, y), (x + 1, y)), ((x, y - 1), (x, y + 1))):
            subject = at.get(before)
            prop = at.get(after)
            if subject in SUBJECTS and prop in PROPERTIES:
                rules.add(f"{subject} IS {prop}")
    return tuple(sorted(rules))


def _initial_state(template: dict[str, Any]) -> State:
    entities = _position_tuple(template["entities"])
    words = _position_tuple(template["words"])
    return entities, words, frozenset()


def _state_snapshot(template: dict[str, Any], state: State) -> dict[str, Any]:
    entity_positions, word_positions, broken = state
    rules = _active_rules_for_positions(template["words"], word_positions)
    controlled = sorted(rule.removesuffix(" IS YOU") for rule in rules if rule.endswith(" IS YOU"))
    return {
        "entities": [
            {"id": entity["id"], "x": position[0], "y": position[1]}
            for entity, position in zip(template["entities"], entity_positions)
        ],
        "words": [
            {"id": word["id"], "x": position[0], "y": position[1]}
            for word, position in zip(template["words"], word_positions)
        ],
        "active_rules": list(rules),
        "controlled_kinds": controlled,
        "broken_opening_rules": sorted(broken),
    }


def _state_digest(template: dict[str, Any], state: State) -> str:
    encoded = json.dumps(_state_snapshot(template, state), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _is_win(template: dict[str, Any], state: State) -> bool:
    entity_positions, word_positions, _broken = state
    rules = _active_rules_for_positions(template["words"], word_positions)
    controlled = {rule.removesuffix(" IS YOU") for rule in rules if rule.endswith(" IS YOU")}
    exits = {rule.removesuffix(" IS EXIT") for rule in rules if rule.endswith(" IS EXIT")}
    if not controlled or not exits:
        return False
    controlled_positions = {
        position
        for entity, position in zip(template["entities"], entity_positions)
        if entity["kind"] in controlled
    }
    return any(
        entity["kind"] in exits and position in controlled_positions
        for entity, position in zip(template["entities"], entity_positions)
    )


def _is_deadly(template: dict[str, Any], state: State) -> bool:
    entity_positions, word_positions, _broken = state
    rules = _active_rules_for_positions(template["words"], word_positions)
    controlled = {rule.removesuffix(" IS YOU") for rule in rules if rule.endswith(" IS YOU")}
    deadly = {rule.removesuffix(" IS DEADLY") for rule in rules if rule.endswith(" IS DEADLY")}
    controlled_positions = {
        position
        for entity, position in zip(template["entities"], entity_positions)
        if entity["kind"] in controlled
    }
    return any(
        entity["kind"] in deadly and position in controlled_positions
        for entity, position in zip(template["entities"], entity_positions)
    )


def _advance(template: dict[str, Any], state: State, direction: str) -> tuple[State, dict[str, Any]]:
    if direction not in DIRECTIONS:
        raise ValueError(f"unknown direction {direction!r}")
    dx, dy = DIRECTIONS[direction]
    entity_positions, word_positions, broken_before = state
    entities_next = list(entity_positions)
    words_next = list(word_positions)
    walls = {tuple(point) for point in template["walls"]}
    rules_before = _active_rules_for_positions(template["words"], word_positions)
    controlled_kinds = {rule.removesuffix(" IS YOU") for rule in rules_before if rule.endswith(" IS YOU")}
    stop_kinds = {rule.removesuffix(" IS STOP") for rule in rules_before if rule.endswith(" IS STOP")}
    controlled_indices = [
        index for index, entity in enumerate(template["entities"]) if entity["kind"] in controlled_kinds
    ]
    moved_entities: list[str] = []
    pushed_words: list[str] = []

    for entity_index in controlled_indices:
        x, y = entities_next[entity_index]
        target = (x + dx, y + dy)
        if target in walls:
            continue
        occupying_word = next((i for i, point in enumerate(words_next) if point == target), None)
        if occupying_word is not None:
            chain: list[int] = []
            cursor = target
            while True:
                word_index = next((i for i, point in enumerate(words_next) if point == cursor), None)
                if word_index is None:
                    break
                chain.append(word_index)
                cursor = (cursor[0] + dx, cursor[1] + dy)
            destination_blocked = cursor in walls or any(
                position == cursor and template["entities"][index]["kind"] in stop_kinds
                for index, position in enumerate(entities_next)
            )
            if destination_blocked:
                continue
            for word_index in reversed(chain):
                wx, wy = words_next[word_index]
                words_next[word_index] = (wx + dx, wy + dy)
                pushed_words.append(template["words"][word_index]["id"])
        if any(
            position == target and template["entities"][index]["kind"] in stop_kinds
            for index, position in enumerate(entities_next)
        ):
            continue
        entities_next[entity_index] = target
        moved_entities.append(template["entities"][entity_index]["id"])

    rules_after = _active_rules_for_positions(template["words"], tuple(words_next))
    opening = set(_active_rules_for_positions(template["words"], _position_tuple(template["words"])))
    broken_after = frozenset(set(broken_before) | (opening - set(rules_after)))
    next_state: State = tuple(entities_next), tuple(words_next), broken_after
    deadly = _is_deadly(template, next_state)
    won = not deadly and _is_win(template, next_state)
    if deadly:
        outcome = "deadly_contact"
    elif won:
        outcome = "exit_reached"
    elif pushed_words:
        outcome = "law_shift"
    elif moved_entities:
        outcome = "move"
    elif not controlled_indices:
        outcome = "no_subject_bound"
    else:
        outcome = "blocked"
    return next_state, {
        "outcome": outcome,
        "moved_entities": sorted(set(moved_entities)),
        "pushed_word_ids": sorted(set(pushed_words)),
        "active_rules_before": list(rules_before),
        "active_rules_after": list(rules_after),
        "controlled_before": sorted(controlled_kinds),
        "controlled_after": sorted(
            rule.removesuffix(" IS YOU") for rule in rules_after if rule.endswith(" IS YOU")
        ),
        "won": won,
        "deadly": deadly,
    }


def _solve(
    template: dict[str, Any],
    *,
    state_allowed: Callable[[State], bool] | None = None,
    maximum_states: int = 750_000,
) -> tuple[list[str] | None, State | None, int]:
    initial = _initial_state(template)
    queue: deque[tuple[State, tuple[str, ...]]] = deque([(initial, ())])
    seen = {initial}
    while queue:
        state, path = queue.popleft()
        if _is_win(template, state):
            return list(path), state, len(seen)
        for direction in DIRECTIONS:
            next_state, result = _advance(template, state, direction)
            if result["deadly"] or next_state == state or next_state in seen:
                continue
            if state_allowed is not None and not state_allowed(next_state):
                continue
            seen.add(next_state)
            if len(seen) > maximum_states:
                raise ValueError("statute-yard solver state budget exceeded")
            queue.append((next_state, path + (direction,)))
    return None, None, len(seen)


def _solution_trace(template: dict[str, Any], solution: list[str]) -> dict[str, Any]:
    state = _initial_state(template)
    transfers: list[dict[str, Any]] = []
    deadly_break_step: int | None = None
    exit_make_step: int | None = None
    stop_break_step: int | None = None
    for index, direction in enumerate(solution, start=1):
        state, result = _advance(template, state, direction)
        before = result["controlled_before"]
        after = result["controlled_after"]
        if before != after:
            transfers.append({"step": index, "from": before, "to": after})
        if deadly_break_step is None and "CISTERN IS DEADLY" in result["active_rules_before"] and "CISTERN IS DEADLY" not in result["active_rules_after"]:
            deadly_break_step = index
        if exit_make_step is None and "GATE IS EXIT" not in result["active_rules_before"] and "GATE IS EXIT" in result["active_rules_after"]:
            exit_make_step = index
        if stop_break_step is None and "GATE IS STOP" in result["active_rules_before"] and "GATE IS STOP" not in result["active_rules_after"]:
            stop_break_step = index
    return {
        "transfers": transfers,
        "deadly_break_step": deadly_break_step,
        "exit_make_step": exit_make_step,
        "stop_break_step": stop_break_step,
        "final_state": _state_snapshot(template, state),
        "final_digest": _state_digest(template, state),
    }


def _certify_break_required(template: dict[str, Any], level: int) -> dict[str, Any]:
    opening = set(_active_rules_for_positions(template["words"], _position_tuple(template["words"])))
    geometry = {
        "width": template["width"],
        "height": template["height"],
        "walls": template["walls"],
        "entities": template["entities"],
        "words": template["words"],
    }
    cache_key = hashlib.sha256(
        json.dumps(geometry, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    cached = _BREAK_CERTIFICATE_CACHE.get(cache_key)
    if cached is not None:
        return copy.deepcopy(cached)

    no_break_solution, no_break_final, explored_states = _solve(
        template,
        state_allowed=lambda state: not state[2],
    )
    if no_break_solution is not None or no_break_final is not None:
        raise ValueError("generated statute yard can be won without breaking an opening law")

    if level not in PROFILE_NAMES:
        raise ValueError("unsupported structural certificate")
    if "CISTERN IS DEADLY" not in opening:
        raise ValueError("deadly crossing profile lacks its opening law")
    structural_witness = {
        "law": "CISTERN IS DEADLY",
        "reason": "Walls and the cistern cut separate the opening YOU object from every exit or control-transfer region; crossing while the opening law remains active is terminal.",
    }

    certificate = {
        "method": "exhaustive_bfs_no_opening_rule_break",
        "opening_rules": sorted(opening),
        "state_constraint": "broken_opening_rules remains empty",
        "explored_states": explored_states,
        "result": "no winning state reachable",
        "structural_witness": structural_witness,
    }
    _BREAK_CERTIFICATE_CACHE[cache_key] = copy.deepcopy(certificate)
    return certificate


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = task.get("_control_condition")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    level = int((condition or {}).get("difficulty", 3))
    if not 1 <= level <= 5:
        raise ValueError("statute-yard difficulty must be between 1 and 5")
    expected_profile = str(parameters.get("profile") or PROFILE_NAMES[level])
    if expected_profile != PROFILE_NAMES[level]:
        raise ValueError("statute-yard profile does not match its difficulty")

    expected_minimum, expected_maximum = SOLUTION_BANDS[level]
    minimum_required = int(parameters.get("minimum_solution_steps", expected_minimum))
    maximum_required = int(parameters.get("maximum_solution_steps", expected_maximum))
    if (minimum_required, maximum_required) != (expected_minimum, expected_maximum):
        raise ValueError("statute-yard solution band differs from its difficulty contract")

    digest = hashlib.sha256(f"{seed}|{MECHANIC_ID}|v2|{level}".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    template: dict[str, Any] | None = None
    solution: list[str] | None = None
    final_state: State | None = None
    trace: dict[str, Any] | None = None
    explored_states = 0
    decision_variant: dict[str, Any] = {}
    for attempt in range(64):
        candidate, candidate_variant = (
            _low_level_candidate(level, rng)
            if level <= 3
            else _high_level_candidate(level, rng)
        )
        if rng.randrange(2):
            candidate = _transpose(candidate)
        else:
            candidate["orientation"] = "landscape"
        try:
            candidate_solution, candidate_final, candidate_states = _solve(
                candidate, maximum_states=30_000
            )
        except ValueError:
            continue
        if candidate_solution is None or candidate_final is None:
            continue
        candidate_trace = _solution_trace(candidate, candidate_solution)
        if any(not candidate_trace.get(field) for field in REQUIRED_TRACE_FIELDS[level]):
            continue
        if not minimum_required <= len(candidate_solution) <= maximum_required:
            continue
        template = candidate
        solution = candidate_solution
        final_state = candidate_final
        trace = candidate_trace
        decision_variant = {
            **candidate_variant,
            "orientation": candidate["orientation"],
            "solver_acceptance_attempt": attempt + 1,
        }
        explored_states = candidate_states
        break
    if template is None or solution is None or final_state is None or trace is None:
        raise ValueError("could not construct a statute-yard decision variant inside its profile band")

    template["palette"] = PALETTES[rng.randrange(len(PALETTES))]
    wall_cells = {tuple(point) for point in template["walls"]}
    floor_cells = [
        (x, y)
        for y in range(1, template["height"] - 1)
        for x in range(1, template["width"] - 1)
        if (x, y) not in wall_cells
    ]
    rng.shuffle(floor_cells)
    template["cracks"] = [list(point) for point in floor_cells[: min(18, len(floor_cells))]]

    opening_rules = set(_active_rules_for_positions(template["words"], _position_tuple(template["words"])))
    if not final_state[2]:
        raise ValueError("statute-yard solution does not break an opening law")
    break_requirement = _certify_break_required(template, level)
    task_id = str(task.get("id") or "statute_yard_seed_0001@0.1")
    condition_token = f"|d{level}|{task_id}" if condition else ""
    challenge_id = hashlib.sha256(f"{seed}|statute-yard-v2{condition_token}".encode("utf-8")).hexdigest()[:12]
    initial_snapshot = _state_snapshot(template, _initial_state(template))
    initial_rules = initial_snapshot["active_rules"]
    prompt = task.get("natural_language") or template["objective"]
    if condition:
        prompt = str((condition.get("natural_language") or prompt))

    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": prompt,
        "submit_label": "SEAL VERDICT",
        "asset_manifest": "shared_runtime/assets/provenance/statute_yard_v0.json",
        "generator": {
            "name": "statute_yard_v2",
            "variation_kind": "solver-accepted entity placement and routing topology; palette and cracks excluded",
            "solver": "breadth_first_minimum",
            "minimum_solution_steps": len(solution),
            "solution_band": [minimum_required, maximum_required],
            "required_operation_count": len(REQUIRED_TRACE_FIELDS[level]),
            "explored_states": explored_states,
            "opening_law_break_certificate": break_requirement["method"],
            "no_break_states_exhausted": break_requirement["explored_states"],
        },
        "yard": copy.deepcopy(template),
        "initial_state": initial_snapshot,
        "opening_rules": initial_rules,
        "rules": {
            "syntax": "NOUN + IS + PROPERTY in a straight three-stone line is law.",
            "motion": "Every object named by YOU moves together. Word-stones push.",
            "exit": "A YOU object sharing a tile with an EXIT object wins.",
        },
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "yard": copy.deepcopy(template),
        "opening_rules": initial_rules,
        "initial_state": initial_snapshot,
        "initial_digest": _state_digest(template, _initial_state(template)),
        "minimum_solution_steps": len(solution),
        "solution": solution,
        "solution_trace": trace,
        "solver_explored_states": explored_states,
        "opening_law_break_certificate": break_requirement,
        "required_opening_law_breaks": 1,
        "profile": level,
        "profile_name": expected_profile,
        "decision_variant": decision_variant,
        "decision_layout_signature": _decision_signature(template),
        "route_signature": hashlib.sha256(" ".join(solution).encode("utf-8")).hexdigest(),
        "orientation": template["orientation"],
        "palette": template["palette"],
    }
    if condition:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth


def replay(yard: dict[str, Any], actions: list[str]) -> tuple[State, list[dict[str, Any]]]:
    state = _initial_state(yard)
    results: list[dict[str, Any]] = []
    for direction in actions:
        before_digest = _state_digest(yard, state)
        state, result = _advance(yard, state, direction)
        results.append({**result, "before_digest": before_digest, "after_digest": _state_digest(yard, state)})
    return state, results
