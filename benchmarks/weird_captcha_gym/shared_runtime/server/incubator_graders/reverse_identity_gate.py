from __future__ import annotations

from typing import Any


MECHANIC_ID = "reverse_identity_gate"


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _angle(value: int) -> int:
    return value % 360


def _error(first: int, second: int) -> int:
    return abs((first - second + 180) % 360 - 180)


def _sign(value: int) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    if payload.get("mechanic_id") != MECHANIC_ID or truth.get("mechanic_id") != MECHANIC_ID or public.get("mechanic_id") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    if payload.get("task_id") != truth.get("task_id") or public.get("task_id") != truth.get("task_id"):
        return _fail("task mismatch")
    if payload.get("challenge_id") != truth.get("challenge_id") or public.get("challenge_id") != truth.get("challenge_id"):
        return _fail("stale challenge")
    stages = truth.get("stages")
    physics = truth.get("physics")
    if not isinstance(stages, list) or public.get("stages") != stages or not isinstance(physics, dict) or public.get("physics") != physics:
        return _fail("distributed handshake contract mismatch")
    if len(stages) != 8 or sorted(int(item["station"]) for item in stages) != [0, 0, 1, 1, 2, 2, 3, 3]:
        return _fail("distributed handshake stage structure invalid")
    events = payload.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 20_000:
        return _fail("distributed handshake transcript missing or outside limits")

    deployed: set[int] = set()
    focused: set[int] = set()
    stage_index = 0
    stage_tick = 0
    pulse = int(stages[0]["pulse_start_deg"])
    receiver = int(stages[0]["receiver_initial_deg"])
    direction = 0
    contact = False
    charge = 0
    awaiting_relay = False
    verified = False
    total_ticks = 0

    def current_stage() -> dict[str, Any] | None:
        return stages[stage_index] if stage_index < len(stages) else None

    for sequence, event in enumerate(events, 1):
        if verified:
            return _fail("transcript continues after identity verification")
        if not isinstance(event, dict) or event.get("seq") != sequence:
            return _fail(f"event {sequence} sequence invalid")
        action = event.get("type")
        if awaiting_relay and action != "relay":
            return _fail("charged pulse was not handed off immediately")
        if action == "deploy":
            station = event.get("station")
            if stage_tick or stage_index or station not in range(4) or station in deployed:
                return _fail("limb deployment is duplicate or late")
            deployed.add(station)
            if event.get("deployed_count") != len(deployed):
                return _fail("limb deployment count false")
        elif action == "focus":
            station = event.get("station")
            if station not in deployed:
                return _fail("focus claimed for an undeployed limb")
            focused.add(station)
        elif action == "key":
            stage = current_stage()
            if stage is None or deployed != {0, 1, 2, 3} or event.get("stage") != stage_index or event.get("station") != stage["station"]:
                return _fail("key input sent to the wrong limb or stage")
            before, after = event.get("before"), event.get("after")
            if before != direction or after not in {-1, 0, 1} or before == after:
                return _fail("receiver drive transition invalid")
            direction = after
        elif action == "contact":
            stage = current_stage()
            if stage is None or deployed != {0, 1, 2, 3} or event.get("stage") != stage_index or event.get("station") != stage["station"]:
                return _fail("contact input sent to the wrong limb or stage")
            before, after = event.get("before"), event.get("after")
            if before is not contact or not isinstance(after, bool) or before == after:
                return _fail("contact transition invalid")
            contact = after
        elif action == "tick":
            stage = current_stage()
            if stage is None or deployed != {0, 1, 2, 3} or event.get("stage") != stage_index or event.get("station") != stage["station"]:
                return _fail("fixed tick belongs to the wrong limb or stage")
            if event.get("tick") != stage_tick + 1:
                return _fail("handshake fixed tick is missing or reordered")
            stage_tick += 1
            total_ticks += 1
            if stage_tick > int(physics["maximum_ticks_per_stage"]):
                return _fail("handshake stage exceeded its fixed-step budget")
            pulse = _angle(pulse + int(stage["pulse_speed_deg_per_tick"]))
            receiver = _angle(receiver + direction * int(physics["receiver_control_deg_per_tick"]))
            error = _error(receiver, pulse)
            locked = (
                contact
                and direction == _sign(int(stage["pulse_speed_deg_per_tick"]))
                and error <= int(physics["capture_tolerance_deg"])
            )
            if locked:
                receiver = pulse
                error = 0
                charge += 1
            else:
                charge = max(0, charge - int(physics["charge_decay_per_tick"]))
            state = event.get("state")
            expected = {
                "pulse_deg": pulse,
                "receiver_deg": receiver,
                "error_deg": error,
                "charge": charge,
                "locked": locked,
                "direction": direction,
                "contact": contact,
            }
            if state != expected:
                return _fail(f"event {sequence} handshake state disagrees with replay")
            awaiting_relay = charge >= int(physics["hold_ticks"])
        elif action == "relay":
            stage = current_stage()
            if stage is None or not awaiting_relay or event.get("stage") != stage_index or event.get("station") != stage["station"]:
                return _fail("pulse relay occurred without a charged active station")
            if event.get("tick") != stage_tick or event.get("charge") != charge:
                return _fail("pulse relay reports stale charge")
            expected_next = stages[stage_index + 1]["station"] if stage_index + 1 < len(stages) else None
            if event.get("next_station") != expected_next:
                return _fail("pulse relay names the wrong next limb")
            stage_index += 1
            stage_tick = 0
            direction = 0
            contact = False
            charge = 0
            awaiting_relay = False
            if stage_index < len(stages):
                pulse = int(stages[stage_index]["pulse_start_deg"])
                receiver = int(stages[stage_index]["receiver_initial_deg"])
        elif action == "verify":
            if event.get("completed_stages") != stage_index or event.get("deployed") != sorted(deployed):
                return _fail("master verification reports stale distributed state")
            verified = True
        else:
            return _fail(f"unknown distributed-handshake event {action!r}")

    passed = (
        verified
        and deployed == {0, 1, 2, 3}
        and stage_index == len(stages)
        and payload.get("completed") is True
    )
    feedback = (
        f"distributed replay: limbs {len(deployed)}/4; relays {stage_index}/8; "
        f"ticks {total_ticks}; focused limbs {len(focused)}/4"
    )
    return {"graded": True, "passed": passed, "feedback": feedback}


def cheat(public: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    del public
    return {"stages": truth.get("stages"), "physics": truth.get("physics")}
