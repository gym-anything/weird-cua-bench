from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "modifier_stack_image_grid"
INTERACTION_SOURCES = {
    "simplified": "proxy_controls",
    "full": "direct_canvas",
}


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} is not finite")
    return float(value)


def _point(value: Any, width: int, height: int, label: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} is malformed")
    p = _number(value[0], f"{label} x"), _number(value[1], f"{label} y")
    if not 0 <= p[0] <= width or not 0 <= p[1] <= height:
        raise ValueError(f"{label} leaves the restoration bed")
    return p


def _inside(point: tuple[float, float], rect: dict[str, Any]) -> bool:
    return float(rect["x"]) <= point[0] <= float(rect["x"]) + float(rect["width"]) and float(rect["y"]) <= point[1] <= float(rect["y"]) + float(rect["height"])


def _public_artifacts(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    import copy

    public = copy.deepcopy(artifacts)
    for artifact in public:
        for token in artifact["stack"]:
            token.pop("inverse", None)
    return public


def _control_contract(
    ground_truth: dict[str, Any],
    public_state: dict[str, Any],
    artifacts: list[dict[str, Any]],
    rail: dict[str, Any],
    slots: list[dict[str, Any]],
    requirements: dict[str, Any],
) -> tuple[str, str | None]:
    """Validate the selected profile and recover its bound input surface."""

    truth_condition = ground_truth.get("control_condition")
    public_condition = public_state.get("control_condition")
    if truth_condition is None and public_condition is None:
        return "full", None
    if not isinstance(truth_condition, dict) or public_condition != truth_condition:
        return "", "public restoration control condition differs from the hidden contract"
    interaction = str(truth_condition.get("interaction") or "")
    parameters = truth_condition.get("difficulty_parameters")
    if interaction not in INTERACTION_SOURCES or not isinstance(parameters, dict):
        return "", "restoration interaction condition is invalid"
    try:
        artifact_count = int(parameters["artifact_count"])
        modifier_count = int(parameters["modifier_count"])
        playback_ms = int(parameters["playback_ms"])
        playback_minimum_ms = int(parameters["playback_minimum_ms"])
        replay_limit = int(parameters["replay_limit"])
        gate_x = [int(value) for value in parameters["rail_gate_x"]]
        required_values = {
            key: int(parameters[key])
            for key in (
                "minimum_rail_samples",
                "minimum_rail_ms",
                "maximum_rail_step",
            )
        }
        required_values["playback_minimum_ms"] = playback_minimum_ms
        if not isinstance(parameters["show_inverse_template"], bool) or not isinstance(parameters["show_arrangement_oracle"], bool):
            return "", "restoration presentation controls are malformed"
    except (KeyError, TypeError, ValueError):
        return "", "restoration difficulty profile is malformed"
    if (
        artifact_count != len(artifacts)
        or modifier_count != len(slots)
        or any(len(artifact.get("stack") or []) != modifier_count for artifact in artifacts)
        or any(int(artifact.get("playback_ms") or -1) != playback_ms for artifact in artifacts)
        or any(int(artifact.get("replay_limit") or -1) != replay_limit for artifact in artifacts)
        or rail.get("gate_x") != gate_x
        or any(requirements.get(key) != value for key, value in required_values.items())
    ):
        return "", "restoration difficulty condition differs from the generated contract"
    return interaction, None


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    challenge = str(ground_truth.get("challenge_id") or "")
    task_id = str(ground_truth.get("task_id") or "")
    if any(str(item.get("mechanic_id") or "") != MECHANIC_ID for item in (payload, ground_truth, public_state)):
        return _fail("mechanic mismatch")
    if not challenge or str(payload.get("challenge_id") or "") != challenge or str(public_state.get("challenge_id") or "") != challenge:
        return _fail("stale restoration challenge")
    if not task_id or str(payload.get("task_id") or "") != task_id or str(public_state.get("task_id") or "") != task_id:
        return _fail("task identity mismatch")
    try:
        stage = dict(ground_truth["stage"])
        width, height = int(stage["width"]), int(stage["height"])
        artifacts = [dict(item) for item in ground_truth["artifacts"]]
        rail = dict(ground_truth["rail"])
        slots = [dict(item) for item in ground_truth["slots"]]
        requirements = dict(ground_truth["requirements"])
        if not 1 <= len(artifacts) <= 3 or not 2 <= len(slots) <= 4:
            raise ValueError("the restoration profile has an unsupported artifact or slot count")
        if any(len(item.get("stack") or []) != len(slots) for item in artifacts):
            raise ValueError("artifact stacks do not match the visible inverse slots")
        for key in ("stage", "rail", "slots", "requirements"):
            if public_state.get(key) != ground_truth.get(key):
                raise ValueError(f"public {key} differs from replay contract")
        if public_state.get("artifacts") != _public_artifacts(artifacts):
            raise ValueError("public artifacts expose or alter the private inverse contract")
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(f"invalid restoration contract: {exc}")

    interaction, contract_error = _control_contract(
        ground_truth,
        public_state,
        artifacts,
        rail,
        slots,
        requirements,
    )
    if contract_error:
        return _fail(contract_error)
    if ground_truth.get("control_condition") is not None and payload.get("interaction_mode") != interaction:
        return _fail("restoration transcript belongs to the other interaction mode")
    expected_source = INTERACTION_SOURCES[interaction]

    events = payload.get("events")
    if not isinstance(events, list) or not (1 <= len(events) <= 2400):
        return _fail("restoration transcript is missing or outside limits")
    current = 0
    phase = "playback"
    completed: list[str] = []
    placements: dict[int, str] = {}
    inverted: set[str] = set()
    drag: dict[str, Any] | None = None
    rail_hold: dict[str, Any] | None = None
    replay_used = {str(item["id"]): 0 for item in artifacts}
    replay_count = reset_count = rail_samples_total = seal_count = 0
    last_time = -1.0

    def artifact() -> dict[str, Any]:
        return artifacts[current]

    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return _fail(f"event {sequence} has invalid sequence")
        kind = str(event.get("kind") or "")
        try:
            if kind != "playback_complete" and event.get("input_source") != expected_source:
                return _fail(f"event {sequence} uses the wrong interaction input")
            event_time = _number(event.get("t_ms"), "event time")
            if event_time < last_time or event_time > float(requirements["maximum_event_time_ms"]):
                return _fail(f"event {sequence} has impossible time")
            last_time = event_time
            if kind == "playback_complete":
                if phase != "playback" or current >= len(artifacts) or str(event.get("artifact_id") or "") != str(artifact()["id"]):
                    return _fail(f"event {sequence} closes the wrong transformation film")
                duration = _number(event.get("duration_ms"), "playback duration")
                if duration < float(requirements["playback_minimum_ms"]):
                    return _fail(f"event {sequence} compresses the transformation film")
                phase = "work"
            elif kind == "replay":
                art = artifact()
                if phase != "work" or drag is not None or rail_hold is not None or replay_used[str(art["id"])] >= int(art["replay_limit"]):
                    return _fail(f"event {sequence} exceeds the film replay budget")
                replay_used[str(art["id"])] += 1
                replay_count += 1
                placements.clear()
                inverted.clear()
                phase = "playback"
            elif kind == "chip_down":
                if interaction != "full":
                    return _fail(f"event {sequence} uses direct modifier dragging in simplified mode")
                art = artifact()
                token_id = str(event.get("token_id") or "")
                token_ids = {str(item["id"]) for item in art["stack"]}
                rack = next((dict(item) for item in art["rack_rects"] if str(item["token_id"]) == token_id), None)
                if phase != "work" or drag is not None or rail_hold is not None or token_id not in token_ids or token_id in placements.values() or rack is None:
                    return _fail(f"event {sequence} begins an invalid modifier drag")
                start = _point(event.get("point"), width, height, "modifier pickup")
                if not _inside(start, rack):
                    return _fail(f"event {sequence} misses the modifier token")
                drag = {"token_id": token_id, "last_elapsed": 0}
            elif kind == "chip_move":
                if interaction != "full":
                    return _fail(f"event {sequence} uses direct modifier dragging in simplified mode")
                if drag is None or str(event.get("token_id") or "") != drag["token_id"]:
                    return _fail(f"event {sequence} moves no matching modifier")
                _point(event.get("point"), width, height, "modifier drag")
                elapsed = int(_number(event.get("elapsed_ms"), "modifier elapsed"))
                if elapsed < drag["last_elapsed"] or elapsed > 10_000:
                    return _fail(f"event {sequence} reverses modifier drag time")
                drag["last_elapsed"] = elapsed
            elif kind == "chip_up":
                if interaction != "full":
                    return _fail(f"event {sequence} uses direct modifier dragging in simplified mode")
                if drag is None or str(event.get("token_id") or "") != drag["token_id"]:
                    return _fail(f"event {sequence} releases no matching modifier")
                point = _point(event.get("point"), width, height, "modifier release")
                duration = int(_number(event.get("duration_ms"), "modifier duration"))
                if not 0 <= duration <= 10_000:
                    return _fail(f"event {sequence} has impossible modifier duration")
                detected = next((int(slot["index"]) for slot in slots if _inside(point, slot)), None)
                if event.get("slot_index") != detected:
                    return _fail(f"event {sequence} claims a false restoration slot")
                cancelled = event.get("cancelled") is True
                accepted = not cancelled and detected is not None and detected not in placements
                if bool(event.get("accepted")) != accepted:
                    return _fail(f"event {sequence} lies about modifier placement")
                if accepted:
                    placements[int(detected)] = drag["token_id"]
                drag = None
            elif kind == "proxy_place":
                if interaction != "simplified":
                    return _fail(f"event {sequence} uses a proxy module action in full mode")
                art = artifact()
                token_id = str(event.get("token_id") or "")
                token_ids = {str(item["id"]) for item in art["stack"]}
                raw_slot = event.get("slot_index")
                if isinstance(raw_slot, bool):
                    return _fail(f"event {sequence} has an invalid proxy slot")
                try:
                    slot_index = int(raw_slot)
                except (TypeError, ValueError):
                    return _fail(f"event {sequence} has an invalid proxy slot")
                if (
                    phase != "work"
                    or drag is not None
                    or rail_hold is not None
                    or token_id not in token_ids
                    or token_id in placements.values()
                    or slot_index not in {int(slot["index"]) for slot in slots}
                    or slot_index in placements
                ):
                    return _fail(f"event {sequence} makes an invalid proxy module placement")
                placements[slot_index] = token_id
            elif kind == "invert":
                token_id = str(event.get("token_id") or "")
                token_ids = {str(item["id"]) for item in artifact()["stack"]}
                before, after = bool(event.get("before")), bool(event.get("after"))
                expected_before = token_id in inverted
                if phase != "work" or drag is not None or rail_hold is not None or token_id not in token_ids or before != expected_before or after != (not before):
                    return _fail(f"event {sequence} reports an invalid inverse switch")
                if after: inverted.add(token_id)
                else: inverted.discard(token_id)
            elif kind == "reset_work":
                if phase != "work" or drag is not None or rail_hold is not None:
                    return _fail(f"event {sequence} resets outside a stable workbench")
                placements.clear()
                inverted.clear()
                reset_count += 1
            elif kind == "rail_start":
                art = artifact()
                expected_order = [str(item["id"]) for item in reversed(art["stack"])]
                arranged = [placements.get(index) for index in range(len(slots))]
                start = _point(event.get("point"), width, height, "rail start")
                if phase != "work" or drag is not None or rail_hold is not None or arranged != expected_order or inverted != set(expected_order) or math.hypot(start[0] - rail["start"][0], start[1] - rail["start"][1]) > 28:
                    return _fail(f"event {sequence} starts the press without a valid inverse stack")
                rail_hold = {"samples": 0, "last": start, "last_elapsed": 0, "gates": 0}
            elif kind == "rail_sample":
                if rail_hold is None:
                    return _fail(f"event {sequence} has no continuous press hold")
                point = _point(event.get("point"), width, height, "rail sample")
                elapsed = int(_number(event.get("elapsed_ms"), "rail elapsed"))
                if elapsed < rail_hold["last_elapsed"] or point[0] + 2 < rail_hold["last"][0] or math.hypot(point[0] - rail_hold["last"][0], point[1] - rail_hold["last"][1]) > float(requirements["maximum_rail_step"]) or abs(point[1] - float(rail["start"][1])) > float(rail["half_height"]):
                    return _fail(f"event {sequence} breaks the continuous restoration rail")
                rail_hold["last"], rail_hold["last_elapsed"] = point, elapsed
                rail_hold["samples"] += 1
                while rail_hold["gates"] < len(rail["gate_x"]) and point[0] >= float(rail["gate_x"][rail_hold["gates"]]):
                    rail_hold["gates"] += 1
                rail_samples_total += 1
            elif kind == "rail_end":
                if rail_hold is None:
                    return _fail(f"event {sequence} ends no continuous press hold")
                point = _point(event.get("point"), width, height, "rail end")
                duration = int(_number(event.get("duration_ms"), "rail duration"))
                accepted = rail_hold["samples"] >= int(requirements["minimum_rail_samples"]) and duration >= int(requirements["minimum_rail_ms"]) and rail_hold["gates"] == len(rail["gate_x"]) and math.hypot(point[0] - rail["end"][0], point[1] - rail["end"][1]) <= 30
                if bool(event.get("accepted")) != accepted:
                    return _fail(f"event {sequence} lies about restoration completion")
                if not accepted:
                    return _fail(f"event {sequence} submits an incomplete restoration rail")
                completed.append(str(artifact()["id"]))
                current += 1
                placements.clear(); inverted.clear(); rail_hold = None
                phase = "terminal" if current == len(artifacts) else "playback"
            elif kind == "rail_cancel":
                if interaction != "full" or rail_hold is None:
                    return _fail(f"event {sequence} cancels no direct press hold")
                _point(event.get("point"), width, height, "cancelled rail point")
                rail_hold = None
            elif kind == "seal":
                if drag is not None or rail_hold is not None:
                    return _fail(f"event {sequence} seals during a pointer hold")
                seal_count += 1
            else:
                return _fail(f"event {sequence} has unknown kind {kind!r}")
        except (KeyError, TypeError, ValueError) as exc:
            return _fail(f"event {sequence}: {exc}")

    expected = {
        "completed_ids": completed,
        "replay_count": replay_count,
        "reset_count": reset_count,
        "rail_samples": rail_samples_total,
        "seal_count": seal_count,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            return _fail(f"submitted {key} does not match restoration replay")
    passed = payload.get("completed") is True and phase == "terminal" and completed == [str(item["id"]) for item in artifacts] and seal_count >= 1
    return {"graded": True, "passed": passed, "score": 100 if passed else 0, "feedback": f"restoration replay: artifacts {len(completed)}/{len(artifacts)}; film replays {replay_count}; resets {reset_count}; rail samples {rail_samples_total}; inverse press terminal={phase == 'terminal'}"}


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    del public_state
    return {"solutions": [{"artifact_id": art["id"], "order": [item["id"] for item in reversed(art["stack"])]} for art in ground_truth.get("artifacts") or []], "answers": []}
