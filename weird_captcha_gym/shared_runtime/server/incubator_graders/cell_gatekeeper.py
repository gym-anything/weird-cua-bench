"""Independent replay grader for Cell Gatekeeper."""

from __future__ import annotations

import copy
import math
from typing import Any


MECHANIC_ID = "cell_gatekeeper"


def _failure(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _catalog(public: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["id"]): item for item in public.get("protein_catalog") or []}


def _move(counts: dict[str, dict[str, int]], species: str, source: str, target: str, capacity: int) -> bool:
    if counts[species][source] <= 0 or counts[species][target] >= capacity:
        return False
    counts[species][source] -= 1
    counts[species][target] += 1
    return True


def _advance(state: dict[str, Any], world: dict[str, Any], ticks: int) -> None:
    parameters = world["parameters"]
    capacity = int(world["surface"]["capacity"])
    catalog = _catalog(world)
    for _ in range(ticks):
        state["tick"] += 1
        for slot, protein_id in enumerate(state["slots"]):
            if not protein_id:
                continue
            protein = catalog.get(str(protein_id))
            if not protein or protein.get("kind") == "decoy":
                continue
            species = str(protein["species"])
            if protein["kind"] == "leak":
                period = max(1, int(parameters["passive_period"]))
                if (state["tick"] + slot) % period:
                    continue
                counts = state["counts"][species]
                source = "outside" if counts["outside"] >= counts["inside"] else "inside"
                target = "inside" if source == "outside" else "outside"
                if _move(state["counts"], species, source, target, capacity):
                    key = str(protein_id)
                    state["crossings"]["passive"][key] = state["crossings"]["passive"].get(key, 0) + 1
        period = max(1, int(parameters["pump_period"]))
        if state["tick"] % period == 0:
            pumps = [
                (slot, str(protein_id), catalog[str(protein_id)])
                for slot, protein_id in enumerate(state["slots"])
                if protein_id and catalog.get(str(protein_id), {}).get("kind") == "pump"
            ]
            # ATP is a shared reservoir.  A pump tick fires as a visible
            # cohort only when the reservoir can service every installed pump;
            # this prevents a lower slot from silently consuming a packet that
            # a later pump was waiting for between two observations.
            if pumps and state["atp"] >= len(pumps):
                for _slot, protein_id, protein in pumps:
                    species = str(protein["species"])
                    direction = str(protein["direction"])
                    source = "inside" if direction == "inside_to_outside" else "outside"
                    target = "outside" if source == "inside" else "inside"
                    if _move(state["counts"], species, source, target, capacity):
                        state["atp"] -= 1
                        state["crossings"]["active"][protein_id] = state["crossings"]["active"].get(protein_id, 0) + 1
        if state["tick"] >= int(parameters["max_ticks"]):
            state["status"] = "timeout"
            break
        if _base_goal_ok(state, world):
            state["stable_ticks"] = int(state.get("stable_ticks", 0)) + 1
        else:
            state["stable_ticks"] = 0


def _apply_event(state: dict[str, Any], event: dict[str, Any], world: dict[str, Any], mode: str) -> str | None:
    catalog = _catalog(world)
    parameters = world["parameters"]
    event_type = event.get("type")
    expected_sources = {
        "install": "protein_drag" if mode == "full" else "protein_button",
        "remove": "protein_drag" if mode == "full" else "protein_button",
        "solute": "solute_drag" if mode == "full" else "solute_button",
        "atp": "atp_drag" if mode == "full" else "atp_button",
    }
    if event_type in expected_sources and event.get("input_source") != expected_sources[event_type]:
        return f"{event_type} used the wrong interaction surface"
    if event_type == "install":
        slot = event.get("slot")
        protein_id = str(event.get("protein_id") or "")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot not in range(len(state["slots"])):
            return "invalid membrane slot"
        if state["slots"][slot] is not None:
            return "occupied membrane slot"
        if protein_id not in catalog:
            return "unknown transporter"
        state["slots"][slot] = protein_id
        state["installed_history"].append(protein_id)
        state["stable_ticks"] = 0
        return None
    if event_type == "remove":
        slot = event.get("slot")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot not in range(len(state["slots"])):
            return "invalid eject slot"
        if state["slots"][slot] is None:
            return "empty eject slot"
        state["removed_history"].append(state["slots"][slot])
        state["slots"][slot] = None
        state["stable_ticks"] = 0
        return None
    if event_type == "solute":
        species = str(event.get("species") or "")
        side = str(event.get("side") or "")
        delta = event.get("delta")
        valid_species = {str(item["id"]) for item in world.get("species") or []}
        if species not in valid_species or side not in {"outside", "inside"} or isinstance(delta, bool) or delta not in {-1, 1}:
            return "invalid solute adjustment"
        value = int(state["counts"][species][side]) + int(delta)
        if not 0 <= value <= int(world["surface"]["capacity"]):
            return "solute adjustment leaves the visible chamber bounds"
        state["counts"][species][side] = value
        state["stable_ticks"] = 0
        return None
    if event_type == "atp":
        amount = event.get("amount")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount != int(parameters["atp_batch"]):
            return "ATP supply must use the configured burst size"
        state["atp"] += amount
        state["stable_ticks"] = 0
        return None
    if event_type == "certify":
        return None
    return f"unknown membrane event {event_type!r}"


def _base_goal_ok(state: dict[str, Any], world: dict[str, Any]) -> bool:
    for species_id, target in world["goal"].items():
        counts = state["counts"].get(species_id) or {}
        for side in ("outside", "inside"):
            low, high = target[side]
            if not int(low) <= int(counts.get(side, -1)) <= int(high):
                return False
    catalog = _catalog(world)
    required = [str(item) for item in world.get("required_proteins") or []]
    installed = {str(item) for item in state.get("installed_history") or []}
    if not all(item in installed for item in required):
        return False
    parameters = world["parameters"]
    for item in required:
        protein = catalog[item]
        if protein["kind"] == "pump":
            if int(state["crossings"]["active"].get(item, 0)) < int(parameters["pump_cycles"]):
                return False
        elif int(state["crossings"]["passive"].get(item, 0)) < 1:
            return False
    # A leak is an observation/probing tool.  It must be removed before the
    # final lock, otherwise the same transporter that was observed can undo the
    # gradient the pump just built.
    for slot in state["slots"]:
        if slot and catalog.get(str(slot), {}).get("kind") == "leak" and slot in required:
            return False
    return True


def _in_goal(state: dict[str, Any], world: dict[str, Any]) -> bool:
    required_observations = int(world["parameters"].get("observation_ticks", 0))
    return _base_goal_ok(state, world) and int(state.get("stable_ticks", 0)) >= required_observations


def _essential_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "tick": int(state["tick"]),
        "counts": copy.deepcopy(state["counts"]),
        "slots": list(state["slots"]),
        "atp": int(state["atp"]),
        "crossings": copy.deepcopy(state["crossings"]),
        "installed_history": list(state["installed_history"]),
        "removed_history": list(state["removed_history"]),
        "stable_ticks": int(state.get("stable_ticks", 0)),
        "status": state["status"],
    }


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    if not all(isinstance(item, dict) for item in (payload, truth, public)):
        return _failure("invalid result envelope")
    for key in ("mechanic_id", "task_id", "challenge_id"):
        if payload.get(key) != truth.get(key) or public.get(key) != truth.get(key):
            return _failure("stale task or challenge identity")
    if truth.get("mechanic_id") != MECHANIC_ID:
        return _failure("mechanic mismatch")
    if truth.get("control_condition") != public.get("control_condition"):
        return _failure("control condition differs from the generated world")
    mode = str((truth.get("control_condition") or {}).get("interaction") or "full")
    if mode not in {"simplified", "full"} or payload.get("interaction_mode") != mode:
        return _failure("wrong interaction mode")

    for key in ("parameters", "surface", "species", "protein_catalog", "slot_count", "counts", "goal", "recipe", "required_proteins", "initial_state"):
        if public.get(key) != truth.get(key):
            return _failure(f"public {key} does not match the replay contract")
    try:
        state = copy.deepcopy(public["initial_state"])
        events = payload.get("events")
        terminal_tick = payload.get("terminal_tick")
        if not isinstance(events, list) or len(events) > 3000:
            return _failure("membrane event transcript is malformed")
        if isinstance(terminal_tick, bool) or not isinstance(terminal_tick, int):
            return _failure("terminal tick is malformed")
        max_ticks = int(public["parameters"]["max_ticks"])
        if not 0 <= terminal_tick <= max_ticks:
            return _failure("terminal tick is outside the configured task window")
        last_tick = 0
        certified = None
        for sequence, event in enumerate(events, start=1):
            if not isinstance(event, dict) or event.get("seq") != sequence:
                return _failure("event sequence is malformed")
            tick = event.get("tick")
            if isinstance(tick, bool) or not isinstance(tick, int) or tick < last_tick or tick > terminal_tick:
                return _failure("event time is not monotonic")
            _advance(state, public, tick - state["tick"])
            if state["status"] != "active" and event.get("type") != "certify":
                return _failure("event arrived after the membrane timed out")
            if event.get("type") == "certify":
                if sequence != len(events):
                    return _failure("certify must be the final event")
                certified = event
                last_tick = tick
                break
            error = _apply_event(state, event, public, mode)
            if error:
                return _failure(error)
            last_tick = tick
        if certified is None:
            return _failure("missing final membrane lock")
        if terminal_tick < state["tick"]:
            return _failure("terminal tick moves backward")
        _advance(state, public, terminal_tick - state["tick"])
        accepted = _in_goal(state, public)
        if bool(certified.get("accepted")) != accepted:
            return _failure("visible lock verdict disagrees with replay")
        reported = payload.get("final_state")
        if not isinstance(reported, dict):
            return _failure("missing final membrane state")
        if _essential_state(reported) != _essential_state(state):
            return _failure("final membrane state differs from replay")
        passed = accepted and payload.get("completed") is True
        return {
            "graded": True,
            "passed": passed,
            "score": 100 if passed else 0,
            "feedback": (
                "all target bands held with ATP replay and observed leak removal"
                if passed
                else "target bands or transporter obligations were not satisfied"
            ),
        }
    except (KeyError, TypeError, ValueError, IndexError, OverflowError, AttributeError) as exc:
        return _failure(f"malformed membrane replay: {exc}")
