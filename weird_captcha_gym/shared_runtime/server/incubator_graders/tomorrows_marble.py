"""Independent ledger replay for Tomorrow's Marble.

The browser may display the event trace, but this module computes every
machine transition again from the visible world and checks the submitted
timeline against the hidden generated loop anchors.
"""

from __future__ import annotations

import collections
import math
from typing import Any


MECHANIC_ID = "tomorrows_marble"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(float(value))


def _node(value: Any, machine_count: int, piece_count: int, slot_count: int) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    machine = value.get("machine_index")
    piece = value.get("piece_index")
    slot = value.get("slot")
    if any(type(item) is not int for item in (machine, piece, slot)):
        return None
    if not (0 <= machine < machine_count and 0 <= piece < piece_count and 0 <= slot < slot_count):
        return None
    return {"machine_index": machine, "piece_index": piece, "slot": slot}


def _key(node: dict[str, int]) -> tuple[int, int, int]:
    return node["machine_index"], node["piece_index"], node["slot"]


def _sort(nodes: list[dict[str, int]]) -> list[dict[str, int]]:
    return sorted(nodes, key=lambda item: (item["slot"], item["machine_index"], item["piece_index"]))


def _base_transition(node: dict[str, int], machines: list[dict[str, Any]], slot_count: int) -> tuple[dict[str, int], int]:
    machine = machines[node["machine_index"]]
    raw_slot = node["slot"] + int(machine["delay"])
    target = {
        "machine_index": int(machine["next_machine_index"]),
        "piece_index": int(machine["piece_map"][node["piece_index"]]),
        "slot": raw_slot % slot_count,
    }
    return target, raw_slot // slot_count


def _stateful_transition(
    source: dict[str, int],
    program: dict[str, Any],
    memory: list[int],
    public: dict[str, Any],
) -> tuple[dict[str, int], int, bool, list[int], list[int], int]:
    """Replay one phase of the finite handoff drum.

    A matching source leaves memory untouched and uses the compiled route. A
    mismatch increments the phase's memory cell. The resulting shift changes
    machine, piece, and delay for this and subsequent departures, so editing
    one early arrival changes the physical run rather than only one local
    comparison.
    """
    machine_count = len(public.get("machines") or [])
    piece_count = len(public.get("pieces") or [])
    slot_count = int(public["timeline_slots"])
    carry_modulus = int(public["handoff_carry_modulus"])
    base_target, base_wraps = _base_transition(source, public["machines"], slot_count)
    before = list(memory)
    expected = program["expected"]
    matched = _key(source) == _key(expected)
    if not matched:
        memory_slot = int(program["memory_slot"]) % len(memory)
        memory[memory_slot] = (int(memory[memory_slot]) + 1) % carry_modulus
    shift = sum(memory) % carry_modulus
    destination = base_target
    if matched and shift == 0:
        target = {
            "machine_index": int(destination["machine_index"]),
            "piece_index": int(destination["piece_index"]),
            "slot": int(destination["slot"]),
        }
        wraps = base_wraps
    else:
        machine_delay = int(public["machines"][int(source["machine_index"])] ["delay"])
        raw_delay = machine_delay + shift * int(public["handoff_slot_shift"])
        target = {
            "machine_index": (int(destination["machine_index"]) + shift * int(public["handoff_machine_shift"])) % machine_count,
            "piece_index": (int(destination["piece_index"]) + shift * int(public["handoff_piece_shift"])) % piece_count,
            "slot": (int(source["slot"]) + raw_delay) % slot_count,
        }
        wraps = (int(source["slot"]) + raw_delay) // slot_count
    return target, wraps, matched, before, list(memory), shift


def replay(schedule: list[dict[str, int]], public: dict[str, Any]) -> dict[str, Any]:
    machines = public["machines"]
    slot_count = int(public["timeline_slots"])
    source_keys = [_key(item) for item in schedule]
    source_counts = collections.Counter(source_keys)
    departures: list[dict[str, Any]] = []
    program = public.get("handoff_program") or []
    memory_size = int(public.get("handoff_memory") or 0)
    if not program or memory_size < 1:
        return {
            "arrival_count": len(schedule),
            "arrivals": _sort([dict(item) for item in schedule]),
            "departures": [],
            "missing_arrivals": [],
            "orphan_departures": [],
            "anchors_present": False,
            "machine_coverage": len({item["machine_index"] for item in schedule}),
            "closed": False,
            "passed": False,
            "handoff_trace": [],
            "handoff_final_memory": [],
            "handoff_contamination": 0,
            "later_departures_shifted": False,
        }
    memory = [0] * memory_size
    handoff_trace: list[dict[str, Any]] = []
    first_mismatch_step: int | None = None
    later_departures_shifted = False
    for step, item in enumerate(_sort(schedule)):
        phase = program[step % len(program)]
        target, wraps, matched, before, after, shift = _stateful_transition(item, phase, memory, public)
        if not matched and first_mismatch_step is None:
            first_mismatch_step = step
        if first_mismatch_step is not None and step > first_mismatch_step and shift:
            later_departures_shifted = True
        departures.append(
            {
                "source": dict(item),
                "destination": target,
                "wraps": wraps,
                "returns_to_past": wraps > 0,
            }
        )
        handoff_trace.append(
            {
                "step": step,
                "state_label": str(phase.get("state_label") or f"H{int(phase.get('memory_slot', 0)) + 1}"),
                "expected_source": dict(phase["expected"]),
                "observed_source": dict(item),
                "matched": matched,
                "memory_before": before,
                "memory_after": after,
                "shift": shift,
                "destination": dict(target),
            }
        )
    destination_counts = collections.Counter(_key(item["destination"]) for item in departures)
    missing_keys = sorted(source_counts.keys() - destination_counts.keys())
    orphan_keys = sorted(destination_counts.keys() - source_counts.keys())
    anchors = [
        {
            "machine_index": int(anchor["machine_index"]),
            "piece_index": int(anchor["piece_index"]),
            "slot": int(anchor["slot"]),
        }
        for anchor in public.get("anchors") or []
    ]
    schedule_keys = set(source_keys)
    anchors_present = all(_key(anchor) in schedule_keys for anchor in anchors)
    machine_coverage = len({item["machine_index"] for item in schedule})
    passed = (
        len(schedule) == int(public["required_entries"])
        and len(source_counts) == len(schedule)
        and source_counts == destination_counts
        and not missing_keys
        and not orphan_keys
        and anchors_present
        and machine_coverage == len(machines)
        and len(handoff_trace) == len(schedule)
        and all(item["matched"] and int(item["shift"]) == 0 for item in handoff_trace)
    )
    return {
        "arrival_count": len(schedule),
        "arrivals": _sort([dict(item) for item in schedule]),
        "departures": departures,
        "missing_arrivals": [dict(machine_index=a, piece_index=b, slot=c) for a, b, c in missing_keys],
        "orphan_departures": [dict(machine_index=a, piece_index=b, slot=c) for a, b, c in orphan_keys],
        "anchors_present": anchors_present,
        "machine_coverage": machine_coverage,
        "closed": not missing_keys and not orphan_keys and len(source_counts) == len(schedule),
        "passed": passed,
        "handoff_trace": handoff_trace,
        "handoff_final_memory": list(memory),
        "handoff_contamination": sum(memory),
        "later_departures_shifted": later_departures_shifted,
    }


def _same_summary(reported: Any, actual: dict[str, Any]) -> bool:
    if not isinstance(reported, dict):
        return False
    for key in (
        "arrival_count",
        "arrivals",
        "departures",
        "missing_arrivals",
        "orphan_departures",
        "anchors_present",
        "machine_coverage",
        "closed",
        "passed",
        "handoff_trace",
        "handoff_final_memory",
        "handoff_contamination",
        "later_departures_shifted",
    ):
        if reported.get(key) != actual.get(key):
            return False
    return True


def _world_matches(truth: dict[str, Any], public: dict[str, Any]) -> bool:
    fields = (
        "world_hash",
        "timeline_slots",
        "required_entries",
        "machines",
        "pieces",
        "anchors",
        "handoff_program",
        "handoff_memory",
        "handoff_carry_modulus",
        "handoff_slot_shift",
        "handoff_machine_shift",
        "handoff_piece_shift",
    )
    return all(public.get(field) == truth.get(field) for field in fields)


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    if not all(isinstance(value, dict) for value in (payload, truth, public)):
        return _fail("malformed time-machine ledger")
    if any(value.get("mechanic_id") != MECHANIC_ID for value in (payload, truth, public)):
        return _fail("mechanic identity mismatch")
    for field in ("task_id", "challenge_id"):
        if payload.get(field) != truth.get(field) or public.get(field) != truth.get(field):
            return _fail("stale task or challenge identity")
    if not _world_matches(truth, public):
        return _fail("visible contraption does not match the generated world")
    condition = truth.get("control_condition")
    if condition is not None and public.get("control_condition") != condition:
        return _fail("public interaction condition differs from the ledger contract")
    interaction = str((condition or {}).get("interaction") or "full")
    if interaction not in {"simplified", "full"}:
        return _fail("invalid interaction contract")
    expected_source = "timeline_click" if interaction == "simplified" else "timeline_drag"
    machine_count = len(public.get("machines") or [])
    piece_count = len(public.get("pieces") or [])
    slot_count = int(public.get("timeline_slots") or 0)
    if machine_count != 4 or piece_count < 2 or slot_count < 1:
        return _fail("visible machine or timeline contract is malformed")
    events = payload.get("events")
    if not isinstance(events, list) or not events or len(events) > 2000:
        return _fail("ledger transcript is empty or malformed")

    current: dict[str, dict[str, int]] = {}
    successful_runs: list[dict[str, Any]] = []
    sequence = 0
    try:
        for event in events:
            sequence += 1
            if not isinstance(event, dict) or event.get("seq") != sequence:
                return _fail(f"ledger event {sequence} has an invalid sequence number")
            kind = event.get("type")
            if kind == "schedule":
                if event.get("input_source") != expected_source:
                    return _fail("arrival used the wrong interaction input")
                arrival_id = str(event.get("arrival_id") or "")
                if not arrival_id or arrival_id in current:
                    return _fail("arrival identity is missing or duplicated")
                parsed = _node(event.get("node"), machine_count, piece_count, slot_count)
                if parsed is None:
                    return _fail("arrival is outside the visible timeline")
                if any(_key(parsed) == _key(existing) for existing in current.values()):
                    return _fail("the same marble cannot be scheduled twice at one machine and tick")
                current[arrival_id] = parsed
            elif kind == "reschedule":
                if event.get("input_source") != expected_source:
                    return _fail("reschedule used the wrong interaction input")
                arrival_id = str(event.get("arrival_id") or "")
                if arrival_id not in current:
                    return _fail("reschedule names an unknown arrival")
                before = _node(event.get("before"), machine_count, piece_count, slot_count)
                after = _node(event.get("after"), machine_count, piece_count, slot_count)
                if before is None or after is None or before != current[arrival_id]:
                    return _fail("reschedule begins from stale timeline state")
                if any(_key(after) == _key(existing) for key, existing in current.items() if key != arrival_id):
                    return _fail("reschedule would overlap an existing arrival")
                current[arrival_id] = after
            elif kind == "unschedule":
                if event.get("input_source") != expected_source:
                    return _fail("removal used the wrong interaction input")
                arrival_id = str(event.get("arrival_id") or "")
                if arrival_id not in current:
                    return _fail("removal names an unknown arrival")
                current.pop(arrival_id)
            elif kind == "clear":
                if event.get("input_source") != "clear_button":
                    return _fail("ledger clear was not a visible clear action")
                current = {}
            elif kind == "run":
                if event.get("input_source") != "run_button":
                    return _fail("simulation was not started by the visible run control")
                reported_schedule = event.get("schedule")
                if not isinstance(reported_schedule, list):
                    return _fail("simulation omitted its scheduled arrivals")
                submitted_nodes = [_node(item, machine_count, piece_count, slot_count) for item in reported_schedule]
                if any(item is None for item in submitted_nodes):
                    return _fail("simulation contains an invalid scheduled arrival")
                current_nodes = _sort(list(current.values()))
                if collections.Counter(_key(item) for item in submitted_nodes if item is not None) != collections.Counter(_key(item) for item in current_nodes):
                    return _fail("simulation reports a ledger different from the edited timeline")
                actual = replay(current_nodes, public)
                if not _same_summary(event.get("summary"), actual):
                    return _fail("physical event ledger disagrees with independent replay")
                successful_runs.append(actual)
            else:
                return _fail(f"unknown ledger action {kind!r}")
    except (KeyError, TypeError, ValueError, OverflowError):
        return _fail("malformed time-machine event")

    if payload.get("interaction_mode") not in {None, interaction}:
        return _fail("payload interaction mode disagrees with the trial contract")
    if payload.get("completed") is not True or not successful_runs:
        return _fail("run the contraption and submit its visible event ledger")
    final = successful_runs[-1]
    if not final["passed"]:
        return {
            "graded": True,
            "passed": False,
            "score": 0,
            "feedback": f"causal ledger remains open: {len(final['missing_arrivals'])} missing and {len(final['orphan_departures'])} orphan departures",
        }
    expected = {_key(item) for item in truth.get("solution_schedule") or []}
    actual_keys = {_key(item) for item in current.values()}
    if actual_keys != expected or len(actual_keys) != len(expected):
        return _fail("a self-consistent but unassigned loop was submitted")
    return {
        "graded": True,
        "passed": True,
        "score": 100,
        "feedback": f"closed {len(expected)} arrivals across {len(public.get('anchors') or [])} causal loops; every departure returned to an assigned past",
        "replay": final,
    }


__all__ = ["MECHANIC_ID", "replay", "grade"]
