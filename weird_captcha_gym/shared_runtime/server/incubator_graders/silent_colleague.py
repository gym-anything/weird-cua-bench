from __future__ import annotations

import copy
from typing import Any


MECHANIC_ID = "silent_colleague"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _ticket(sim: dict[str, Any]) -> dict[str, Any] | None:
    sequence = sim["workshop"]["runtime_ticket_sequence"]
    if sim["ticket_index"] >= len(sequence):
        return None
    ticket_id = sequence[sim["ticket_index"]]
    return next(item for item in sim["workshop"]["tickets"] if item["id"] == ticket_id)


def _label(sim: dict[str, Any], label_id: str) -> dict[str, Any]:
    return next(item for item in sim["workshop"]["labels"] if item["id"] == label_id)


def _target(sim: dict[str, Any]) -> int | None:
    phase = sim["npc_phase"]
    ticket = _ticket(sim)
    if ticket is None:
        return None
    if phase == "signal":
        return int(_label(sim, ticket["label_id"])["station"])
    return {
        "jar": sim["workshop"]["stations"]["jar_rack"],
        "handoff": sim["workshop"]["stations"]["colleague_handoff"],
        "press": sim["workshop"]["stations"]["colleague_press"],
        "hatch": sim["workshop"]["stations"]["hatch"],
    }.get(phase)


def _initial(public: dict[str, Any]) -> dict[str, Any]:
    workshop = copy.deepcopy(public["workshop"])
    return {
        "workshop": workshop, "parameters": copy.deepcopy(public["parameters"]),
        "tick": 0, "player_pos": int(workshop["player_start"]), "npc_pos": int(workshop["colleague_start"]),
        "player_carrying": None, "shelf": None, "ticket_index": 0, "npc_phase": "signal",
        "npc_wait": 0, "prime_until": None, "delivered": [], "spoils": 0, "jams": 0,
        "terminal_failure": False,
    }


def _move_npc(sim: dict[str, Any], target: int, direction: int) -> None:
    size = int(sim["workshop"]["loop_size"])
    candidate = (int(sim["npc_pos"]) + direction) % size
    if candidate == int(sim["player_pos"]):
        sim["jams"] += 1
    else:
        sim["npc_pos"] = candidate


def _npc_step(sim: dict[str, Any]) -> None:
    if sim["terminal_failure"] or _ticket(sim) is None:
        return
    ticket = _ticket(sim)
    phase = sim["npc_phase"]
    if phase == "press_wait":
        if sim["tick"] > int(sim["prime_until"]):
            sim["spoils"] += 1
            sim["npc_phase"] = "signal"
            sim["npc_wait"] = 0
            sim["prime_until"] = None
            if sim["spoils"] >= int(sim["parameters"]["max_spoils"]):
                sim["terminal_failure"] = True
        return
    target = _target(sim)
    if target is None:
        return
    if int(sim["npc_pos"]) != int(target):
        _move_npc(sim, int(target), int(ticket["direction"]))
        if sim["npc_phase"] == "signal" and int(sim["npc_pos"]) == int(target):
            sim["npc_wait"] = 1
        return
    if phase == "signal":
        if sim["npc_wait"] <= 0:
            sim["npc_wait"] = 1
        elif sim["npc_wait"] < int(sim["parameters"]["signal_ticks"]):
            sim["npc_wait"] += 1
        else:
            sim["npc_wait"] = 0
            sim["npc_phase"] = "jar"
            _move_npc(sim, int(_target(sim)), int(ticket["direction"]))
    elif phase == "jar":
        sim["npc_phase"] = "handoff"
    elif phase == "handoff":
        if sim["shelf"] == ticket["fruit_id"]:
            sim["shelf"] = None
            sim["npc_phase"] = "press"
    elif phase == "press":
        sim["npc_phase"] = "press_wait"
        sim["prime_until"] = sim["tick"] + int(sim["parameters"]["press_window_ticks"]) - 1
    elif phase == "hatch":
        sim["delivered"].append(ticket["id"])
        sim["ticket_index"] += 1
        sim["npc_phase"] = "signal"
        sim["npc_wait"] = 0


def advance_to(sim: dict[str, Any], tick: int) -> None:
    if tick < sim["tick"]:
        raise ValueError("event tick moved backward")
    while sim["tick"] < tick:
        sim["tick"] += 1
        _npc_step(sim)


def _station_fruit(sim: dict[str, Any]) -> str | None:
    for fruit in sim["workshop"]["fruits"]:
        if int(fruit["station"]) == int(sim["player_pos"]):
            return str(fruit["id"])
    return None


def apply_action(sim: dict[str, Any], action: str) -> dict[str, Any]:
    before = int(sim["player_pos"])
    if action in {"ccw", "cw"}:
        direction = -1 if action == "ccw" else 1
        candidate = (before + direction) % int(sim["workshop"]["loop_size"])
        moved = candidate != int(sim["npc_pos"])
        if moved:
            sim["player_pos"] = candidate
        else:
            sim["jams"] += 1
        return {"kind": "move", "action": action, "from": before, "to": int(sim["player_pos"]), "moved": moved}
    if action != "use":
        raise ValueError("unknown player action")
    effect = "idle"
    fruit = _station_fruit(sim)
    stations = sim["workshop"]["stations"]
    if fruit is not None:
        sim["player_carrying"] = fruit
        effect = "pick_fruit"
    elif int(sim["player_pos"]) == int(stations["handoff"]):
        if sim["player_carrying"] is not None:
            sim["shelf"] = sim["player_carrying"]
            sim["player_carrying"] = None
            effect = "place_handoff"
        elif sim["shelf"] is not None:
            sim["player_carrying"] = sim["shelf"]
            sim["shelf"] = None
            effect = "retrieve_handoff"
    elif int(sim["player_pos"]) == int(stations["player_press"]) and sim["npc_phase"] == "press_wait" and sim["prime_until"] is not None and sim["tick"] <= int(sim["prime_until"]):
        sim["npc_phase"] = "hatch"
        sim["prime_until"] = None
        effect = "paired_press"
    return {"kind": "use", "action": "use", "position": int(sim["player_pos"]), "effect": effect, "carrying": sim["player_carrying"], "shelf": sim["shelf"]}


def snapshot(sim: dict[str, Any]) -> dict[str, Any]:
    return {
        "tick": int(sim["tick"]), "player_pos": int(sim["player_pos"]), "npc_pos": int(sim["npc_pos"]),
        "player_carrying": sim["player_carrying"], "shelf": sim["shelf"], "ticket_index": int(sim["ticket_index"]),
        "npc_phase": sim["npc_phase"], "npc_wait": int(sim["npc_wait"]), "prime_until": sim["prime_until"],
        "delivered": list(sim["delivered"]), "spoils": int(sim["spoils"]), "jams": int(sim["jams"]),
        "terminal_failure": bool(sim["terminal_failure"]),
    }


def _contract(truth: dict[str, Any], public: dict[str, Any]) -> tuple[dict[str, Any], str]:
    if truth.get("workshop") != public.get("workshop") or truth.get("parameters") != public.get("parameters"):
        raise ValueError("public workshop differs from grading truth")
    condition = truth.get("control_condition")
    if condition != public.get("control_condition"):
        raise ValueError("control condition mismatch")
    if condition is not None and condition.get("difficulty_parameters") != truth.get("parameters"):
        raise ValueError("difficulty parameters are not bound")
    interaction = str((condition or {}).get("interaction") or "full")
    if interaction not in {"simplified", "full"}:
        raise ValueError("invalid interaction mode")
    workshop = truth.get("workshop")
    if not isinstance(workshop, dict) or len(workshop.get("runtime_ticket_sequence") or []) != int(truth["parameters"]["ticket_count"]):
        raise ValueError("ticket sequence is incomplete")
    ticket_ids = {item.get("id") for item in workshop.get("tickets") or []}
    if set(workshop["runtime_ticket_sequence"]) != ticket_ids:
        raise ValueError("ticket inventory does not match colleague schedule")
    return workshop, interaction


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    for item in (payload, truth, public):
        if str(item.get("mechanic_id") or "") != MECHANIC_ID:
            return _fail("mechanic mismatch")
    for key in ("task_id", "challenge_id"):
        expected = str(truth.get(key) or "")
        if not expected or str(public.get(key) or "") != expected or str(payload.get(key) or "") != expected:
            return _fail(f"stale or mismatched {key}")
    try:
        _workshop, interaction = _contract(truth, public)
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"invalid colleague contract: {exc}")
    if payload.get("interaction_mode") != interaction:
        return _fail("submitted interaction mode differs from task condition")
    events = payload.get("events")
    final_tick = payload.get("final_tick")
    if not isinstance(events, list) or not events:
        return _fail("player action transcript is empty")
    if isinstance(final_tick, bool) or not isinstance(final_tick, int) or final_tick < 0 or final_tick > 20000:
        return _fail("final tick is invalid")
    sources = {"full": {"move": "keyboard_move", "use": "keyboard_action"}, "simplified": {"move": "proxy_step", "use": "proxy_action"}}
    sim = _initial(public)
    try:
        for sequence, event in enumerate(events, 1):
            if not isinstance(event, dict) or event.get("sequence") != sequence:
                raise ValueError(f"event {sequence} has invalid sequence")
            tick = event.get("tick")
            if isinstance(tick, bool) or not isinstance(tick, int) or tick > final_tick:
                raise ValueError(f"event {sequence} has invalid tick")
            advance_to(sim, tick)
            expected = apply_action(sim, str(event.get("action") or ""))
            if event.get("input_source") != sources[interaction][expected["kind"]]:
                raise ValueError(f"event {sequence} uses the wrong input surface")
            claim = {key: value for key, value in event.items() if key not in {"sequence", "tick", "input_source"}}
            if claim != expected:
                raise ValueError(f"event {sequence} action claim disagrees with replay")
        advance_to(sim, final_tick)
    except (KeyError, StopIteration, TypeError, ValueError) as exc:
        return _fail(f"colleague replay rejected: {exc}")
    expected_final = snapshot(sim)
    if payload.get("final_state") != expected_final:
        return _fail("submitted final workshop state disagrees with replay")
    all_ids = list(public["workshop"]["runtime_ticket_sequence"])
    passed = expected_final["delivered"] == all_ids and not expected_final["terminal_failure"] and payload.get("completed") is True
    return {
        "graded": True,
        "passed": passed,
        "feedback": f"colleague replay delivered {len(expected_final['delivered'])}/{len(all_ids)} tickets; {expected_final['spoils']} spoiled; {expected_final['jams']} occupied-loop blocks",
    }
