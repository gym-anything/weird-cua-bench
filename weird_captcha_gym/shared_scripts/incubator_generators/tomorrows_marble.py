"""Seeded visible state for Tomorrow's Marble.

The public state contains the four-machine contraption, the visible routing
rules, and an empty timeline.  A scheduled arrival is a handoff in a finite
state machine: every accepted arrival advances the handoff memory, and a
source that does not match the current handoff phase contaminates later
departures.  The generated solution is a closed ledger whose sources visit
the handoff phases in order.  The browser exposes those phases through the
run trace; the independent grader replays the same state transition.
"""

from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "tomorrows_marble"
PUBLIC_NAME = "Tomorrow's Marble"
SOURCE_ANCHORS = ["XART-111"]
CANVAS = {"width": 560, "height": 430}


_PIECE_LIBRARY = (
    ("amber", "Amber marble", "◆", "#f8bd68"),
    ("cyan", "Cyan marble", "●", "#64d7d4"),
    ("violet", "Violet marble", "✦", "#c19bff"),
    ("coral", "Coral marble", "⬟", "#ff8d83"),
)

_MACHINE_NAMES = (
    ("m0", "The Copper Mouth", "receives a marble and winds the copper spring"),
    ("m1", "The Glass Orchard", "splits the light and sends one echo onward"),
    ("m2", "The Blue Anvil", "stamps the echo and advances the clock"),
    ("m3", "The Brass Recoil", "throws the marble back toward its assigned past"),
)

_PROFILES: dict[int, dict[str, Any]] = {
    1: {
        "timeline_slots": 8,
        "loop_count": 1,
        "piece_count": 2,
        "required_entries": 4,
        "run_duration_ms": 2600,
        "handoff_memory": 1,
        "handoff_carry_modulus": 2,
        "handoff_slot_shift": 1,
        "handoff_machine_shift": 1,
        "handoff_piece_shift": 1,
        "summary": "Follow one four-machine loop while one visible handoff state advances across eight clock ticks.",
        "natural_language": "Schedule the visible origin marbles, run the contraption, and certify the four-arrival ledger after its handoff state returns cleanly.",
    },
    2: {
        # This is the original baseline configuration.  It was previously
        # labelled L3; keep its active numeric parameters intact at L2.
        "timeline_slots": 10,
        "loop_count": 2,
        "piece_count": 3,
        "required_entries": 8,
        "run_duration_ms": 3200,
        "handoff_memory": 2,
        "handoff_carry_modulus": 3,
        "handoff_slot_shift": 1,
        "handoff_machine_shift": 1,
        "handoff_piece_shift": 1,
        "summary": "The original two-loop baseline now crosses a two-state handoff drum on a ten-tick timeline.",
        "natural_language": "Schedule every visible origin marble, run the contraption, and use the handoff trace to certify both causal loops.",
    },
    3: {
        "timeline_slots": 11,
        "loop_count": 2,
        "piece_count": 3,
        "required_entries": 8,
        "run_duration_ms": 3500,
        "handoff_memory": 3,
        "handoff_carry_modulus": 3,
        "handoff_slot_shift": 1,
        "handoff_machine_shift": 1,
        "handoff_piece_shift": 1,
        "summary": "Two loops interleave on an eleven-tick timeline while three handoff-memory cells preserve causal mistakes.",
        "natural_language": "Schedule the visible origin marbles, run the interleaved contraption, and repair any handoff state before certifying both loops.",
    },
    4: {
        "timeline_slots": 13,
        "loop_count": 3,
        "piece_count": 4,
        "required_entries": 12,
        "run_duration_ms": 4000,
        "handoff_memory": 4,
        "handoff_carry_modulus": 4,
        "handoff_slot_shift": 1,
        "handoff_machine_shift": 1,
        "handoff_piece_shift": 1,
        "summary": "Three interleaved loops use four marble identities and four handoff-memory cells on a thirteen-tick timeline.",
        "natural_language": "Schedule the visible origin marbles, watch the four-cell handoff trace through the interleaved run, and certify only a repaired closed ledger.",
    },
    5: {
        "timeline_slots": 16,
        "loop_count": 3,
        "piece_count": 4,
        "required_entries": 12,
        "run_duration_ms": 4600,
        "handoff_memory": 5,
        "handoff_carry_modulus": 5,
        "handoff_slot_shift": 2,
        "handoff_machine_shift": 1,
        "handoff_piece_shift": 1,
        "summary": "Three interleaved loops cross a sixteen-tick clock; five handoff-memory cells make an early wrong arrival alter the later physical run.",
        "natural_language": "Build the twelve-arrival ledger from the visible origins, follow the five-cell handoff trace, and repair the run before certifying it.",
    },
}


def profile_for(difficulty: int) -> dict[str, Any]:
    profile = copy.deepcopy(_PROFILES[int(difficulty)])
    profile["difficulty"] = int(difficulty)
    return profile


def _condition(task: dict[str, Any]) -> dict[str, Any] | None:
    raw = task.get("_control_condition") or (task.get("metadata") or {}).get("control_condition")
    return copy.deepcopy(raw) if raw else None


def _difficulty(condition: dict[str, Any] | None) -> int:
    # The original uncontrolled task was the former L3 numeric profile.  Its
    # exact active configuration now lives at L2, so the baseline generator
    # must select L2 when no controlled condition is supplied.
    return int((condition or {}).get("difficulty") or 2)


def _seed_int(seed: str, salt: str) -> int:
    return int(hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).hexdigest()[:16], 16)


def _permutation(rng: random.Random, count: int) -> list[int]:
    values = list(range(count))
    rng.shuffle(values)
    return values


def _inverse_permutation(values: list[int]) -> list[int]:
    inverse = [0] * len(values)
    for index, value in enumerate(values):
        inverse[value] = index
    return inverse


def _compose(left: list[int], right: list[int]) -> list[int]:
    """Return right(left(x)) for two output-index permutations."""
    return [right[left[index]] for index in range(len(left))]


def _next_node(node: dict[str, Any], machines: list[dict[str, Any]], slot_count: int) -> dict[str, Any]:
    machine = machines[int(node["machine_index"])]
    raw_slot = int(node["slot"]) + int(machine["delay"])
    return {
        "machine_index": int(machine["next_machine_index"]),
        "piece_index": int(machine["piece_map"][int(node["piece_index"])]),
        "slot": raw_slot % int(slot_count),
    }


def _base_transition(
    node: dict[str, Any], machines: list[dict[str, Any]], slot_count: int
) -> tuple[dict[str, Any], int]:
    """Return the visible machine transition and its clock wrap count."""
    machine = machines[int(node["machine_index"])]
    raw_slot = int(node["slot"]) + int(machine["delay"])
    target = _next_node(node, machines, slot_count)
    return target, raw_slot // int(slot_count)


def _node_key(node: dict[str, Any]) -> tuple[int, int, int]:
    return int(node["machine_index"]), int(node["piece_index"]), int(node["slot"])


def _cycle(anchor: dict[str, Any], machines: list[dict[str, Any]], slot_count: int) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    current = copy.deepcopy(anchor)
    for _ in range(4):
        nodes.append(copy.deepcopy(current))
        current = _next_node(current, machines, slot_count)
    if _node_key(current) != _node_key(anchor):
        raise RuntimeError("machine maps did not close a four-step loop")
    return nodes


def _world_hash(
    machines: list[dict[str, Any]],
    pieces: list[dict[str, Any]],
    anchors: list[dict[str, Any]],
    slot_count: int,
    handoff_program: list[dict[str, Any]],
    params: dict[str, Any],
) -> str:
    stable = {
        "machines": machines,
        "pieces": pieces,
        "anchors": anchors,
        "timeline_slots": slot_count,
        "handoff_program": handoff_program,
        "handoff_parameters": {
            key: params[key]
            for key in (
                "handoff_memory",
                "handoff_carry_modulus",
                "handoff_slot_shift",
                "handoff_machine_shift",
                "handoff_piece_shift",
            )
        },
    }
    encoded = repr(stable).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _handoff_program(
    solution_nodes: list[dict[str, Any]],
    machines: list[dict[str, Any]],
    slot_count: int,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compile the intended ledger into the machine's finite handoff drum.

    The expected source is deliberately recorded for each phase.  During a
    correct run every phase matches and the drum stays at zero contamination.
    A wrong or missing source changes one memory cell; subsequent phases use a
    shifted route until the contaminated cell is corrected by a later run.
    """
    memory_size = int(params["handoff_memory"])
    program: list[dict[str, Any]] = []
    for step, source in enumerate(solution_nodes):
        # Compile only the phase expectation. The actual departure remains a
        # replay of the visible machine's next-machine, delay, and piece map.
        _base_transition(source, machines, slot_count)
        program.append(
            {
                "step": step,
                "expected": copy.deepcopy(source),
                "memory_slot": step % memory_size,
                "state_label": f"H{(step % memory_size) + 1}",
            }
        )
    return program


def _make_rules(rng: random.Random, piece_count: int, slot_count: int, difficulty: int) -> tuple[list[dict[str, Any]], list[int]]:
    order = list(range(4))
    rng.shuffle(order)
    delays = [1] * 4
    remaining = slot_count - 4
    for index in range(4):
        if index == 3:
            delays[index] += remaining
        else:
            add = rng.randint(0, min(remaining, max(0, 2 + difficulty)))
            delays[index] += add
            remaining -= add
    rng.shuffle(delays)

    maps_by_order: list[list[int]] = []
    composed = list(range(piece_count))
    for _ in range(3):
        mapping = _permutation(rng, piece_count)
        maps_by_order.append(mapping)
        composed = _compose(composed, mapping)
    maps_by_order.append(_inverse_permutation(composed))

    next_machine = [0] * 4
    delay_by_machine = [0] * 4
    piece_map_by_machine: list[list[int]] = [[] for _ in range(4)]
    for index, machine_index in enumerate(order):
        next_machine[machine_index] = order[(index + 1) % 4]
        delay_by_machine[machine_index] = delays[index]
        piece_map_by_machine[machine_index] = maps_by_order[index]

    machines: list[dict[str, Any]] = []
    positions = ((90, 95), (455, 78), (448, 330), (100, 342))
    for machine_index, (machine_id, name, action) in enumerate(_MACHINE_NAMES):
        machines.append(
            {
                "index": machine_index,
                "id": machine_id,
                "name": name,
                "action": action,
                "next_machine_index": next_machine[machine_index],
                "delay": delay_by_machine[machine_index],
                "piece_map": piece_map_by_machine[machine_index],
                "position": {"x": positions[machine_index][0], "y": positions[machine_index][1]},
                "glyph": ("I", "II", "III", "IV")[machine_index],
            }
        )
    return machines, order


def _make_pieces(piece_count: int) -> list[dict[str, Any]]:
    pieces: list[dict[str, Any]] = []
    for index in range(piece_count):
        piece_id, name, glyph, color = _PIECE_LIBRARY[index]
        pieces.append({"index": index, "id": piece_id, "name": name, "glyph": glyph, "color": color})
    return pieces


def _anchors(loop_count: int, piece_count: int, order: list[int]) -> list[dict[str, Any]]:
    # The anchor marks are visible at the first machine and at tick zero.  A
    # different highlighted piece starts each loop; following the visible
    # machine rules determines every later arrival.
    return [
        {"id": f"origin_{index + 1}", "machine_index": order[0], "piece_index": index, "slot": 0}
        for index in range(loop_count)
        if index < piece_count
    ]


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = _condition(task)
    difficulty = _difficulty(condition)
    params = profile_for(difficulty)
    rng = random.Random(_seed_int(seed, "marble-rules"))
    slot_count = int(params["timeline_slots"])
    piece_count = int(params["piece_count"])
    machines, order = _make_rules(rng, piece_count, slot_count, difficulty)
    pieces = _make_pieces(piece_count)
    anchors = _anchors(int(params["loop_count"]), piece_count, order)
    cycles = [_cycle(anchor, machines, slot_count) for anchor in anchors]
    solution_nodes = [
        {
            "machine_index": int(node["machine_index"]),
            "piece_index": int(node["piece_index"]),
            "slot": int(node["slot"]),
        }
        for cycle in cycles
        for node in cycle
    ]
    solution_nodes.sort(key=lambda node: (int(node["slot"]), int(node["machine_index"]), int(node["piece_index"])))
    handoff_program = _handoff_program(solution_nodes, machines, slot_count, params)
    machine_map = {machine["index"]: machine for machine in machines}
    tubes = []
    for machine in machines:
        target = machine_map[int(machine["next_machine_index"])]
        tubes.append(
            {
                "from_machine_index": machine["index"],
                "to_machine_index": target["index"],
                "curvature": 0.18 if machine["index"] % 2 == 0 else -0.18,
            }
        )
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|d{difficulty}".encode("utf-8")).hexdigest()[:16]
    interaction = str((condition or {}).get("interaction") or "full")
    real_time = str((condition or {}).get("real_time") or "live")
    public_params = copy.deepcopy(params)
    public_params.pop("difficulty", None)
    public_params.pop("summary", None)
    public_params.pop("natural_language", None)
    control = {
        "difficulty": difficulty,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": public_params,
    }
    public: dict[str, Any] = {
        "mechanic_id": MECHANIC_ID,
        "public_name": PUBLIC_NAME,
        "task_id": str(task.get("id") or "tomorrows_marble_seed_0001@0.2"),
        "challenge_id": challenge_id,
        "seed_label": str(seed),
        "canvas": copy.deepcopy(CANVAS),
        "timeline_slots": slot_count,
        "pieces": copy.deepcopy(pieces),
        "machines": copy.deepcopy(machines),
        "tubes": tubes,
        "anchors": copy.deepcopy(anchors),
        "handoff_program": copy.deepcopy(handoff_program),
        "handoff_memory": int(params["handoff_memory"]),
        "handoff_carry_modulus": int(params["handoff_carry_modulus"]),
        "handoff_slot_shift": int(params["handoff_slot_shift"]),
        "handoff_machine_shift": int(params["handoff_machine_shift"]),
        "handoff_piece_shift": int(params["handoff_piece_shift"]),
        "required_entries": int(params["required_entries"]),
        "run_duration_ms": int(params["run_duration_ms"]),
        "control_contract": {
            "simplified": "Select a marble, then click a machine row and a timeline tick; RUN reveals the stamp map for each traversed machine.",
            "full": "Drag a marble or a placed arrival directly onto a machine row and timeline tick; RUN reveals the stamp map for each traversed machine.",
        },
        "interaction_mode": interaction,
        "real_time_mode": real_time,
        "world_hash": _world_hash(machines, pieces, anchors, slot_count, handoff_program, params),
        "caption": "CAUSAL EVENT TRACE",
        "handoff_rule": "The visible origin identities seed a finite handoff drum. A physical run reveals the traversed machine's piece stamp, current phase, and any contaminated memory cell.",
        "prompt": str((condition or {}).get("difficulty_parameters", {}).get("natural_language") or params["natural_language"]),
        "source_anchors": list(SOURCE_ANCHORS),
        "asset_manifest": "shared_runtime/assets/provenance/tomorrows_marble_v0.json",
        "status": "prototype_visual_candidate",
    }
    if condition is not None:
        public["control_condition"] = copy.deepcopy(control)
    truth: dict[str, Any] = {
        "mechanic_id": MECHANIC_ID,
        "public_name": PUBLIC_NAME,
        "task_id": public["task_id"],
        "challenge_id": challenge_id,
        "seed_label": str(seed),
        "solution_schedule": solution_nodes,
        "initial_schedule": [],
        "machines": copy.deepcopy(machines),
        "pieces": copy.deepcopy(pieces),
        "anchors": copy.deepcopy(anchors),
        "handoff_program": copy.deepcopy(handoff_program),
        "handoff_memory": int(params["handoff_memory"]),
        "handoff_carry_modulus": int(params["handoff_carry_modulus"]),
        "handoff_slot_shift": int(params["handoff_slot_shift"]),
        "handoff_machine_shift": int(params["handoff_machine_shift"]),
        "handoff_piece_shift": int(params["handoff_piece_shift"]),
        "timeline_slots": slot_count,
        "required_entries": int(params["required_entries"]),
        "run_duration_ms": int(params["run_duration_ms"]),
        "world_hash": _world_hash(machines, pieces, anchors, slot_count, handoff_program, params),
        "control_condition": copy.deepcopy(control) if condition is not None else None,
        "source_anchors": list(SOURCE_ANCHORS),
    }
    return public, truth


__all__ = ["MECHANIC_ID", "PUBLIC_NAME", "SOURCE_ANCHORS", "profile_for", "generate"]
