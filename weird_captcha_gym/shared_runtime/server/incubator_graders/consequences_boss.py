from __future__ import annotations

from typing import Any


MECHANIC_ID = "consequences_boss"
DEFAULT_SOCKETS = ("left", "right")


def _fail(feedback: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": feedback}


def _binding_error(
    payload: dict[str, Any],
    ground_truth: dict[str, Any],
    public_state: dict[str, Any],
) -> str | None:
    if str(payload.get("mechanic_id") or "") != MECHANIC_ID:
        return "payload mechanic mismatch"
    if str(ground_truth.get("mechanic_id") or "") != MECHANIC_ID:
        return "ground-truth mechanic mismatch"
    if str(public_state.get("mechanic_id") or "") != MECHANIC_ID:
        return "public-state mechanic mismatch"
    challenge_id = str(ground_truth.get("challenge_id") or "")
    if not challenge_id or str(payload.get("challenge_id") or "") != challenge_id:
        return "stale challenge"
    if str(public_state.get("challenge_id") or "") != challenge_id:
        return "public-state challenge mismatch"
    task_id = str(ground_truth.get("task_id") or "")
    if not task_id or str(payload.get("task_id") or "") != task_id:
        return "payload task mismatch"
    if str(public_state.get("task_id") or "") != task_id:
        return "public-state task mismatch"
    return None


def grade(
    payload: dict[str, Any],
    ground_truth: dict[str, Any],
    public_state: dict[str, Any],
) -> dict[str, Any]:
    if error := _binding_error(payload, ground_truth, public_state):
        return _fail(error)

    condition = ground_truth.get("control_condition")
    if condition != public_state.get("control_condition"):
        return _fail("public control condition differs from covenant contract")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    socket_options = tuple(str(item) for item in parameters.get("socket_options", DEFAULT_SOCKETS))
    seal_positions = int(parameters.get("seal_positions", 4))
    minimum_distinct_states = int(parameters.get("minimum_distinct_states", 1))
    expected_sources = {
        "simplified": ("socket_button", "seal_button"),
        "full": ("relic_drag", "seal_drag"),
    }.get(str((condition or {}).get("interaction") or ""))
    if condition is not None and expected_sources is None:
        return _fail("covenant interaction condition is invalid")

    scene_ids = [str(item) for item in ground_truth.get("scene_ids") or []]
    boss_order = [str(item) for item in ground_truth.get("boss_order") or []]
    public_scene_ids = [str(item.get("id") or "") for item in public_state.get("scenes") or []]
    public_boss_order = [str(item) for item in public_state.get("boss_order") or []]
    scene_initial_seals = {
        str(item.get("id") or ""): item.get("initial_seal")
        for item in public_state.get("scenes") or []
    }
    if (
        not scene_ids
        or len(scene_ids) != len(set(scene_ids))
        or public_scene_ids != scene_ids
        or sorted(boss_order) != sorted(scene_ids)
        or public_boss_order != boss_order
    ):
        return _fail("covenant scene contract is invalid")
    if not socket_options or any(option not in DEFAULT_SOCKETS for option in socket_options):
        return _fail("covenant socket contract is invalid")
    if seal_positions not in {1, 2, 4}:
        return _fail("covenant seal contract is invalid")
    if not 1 <= minimum_distinct_states <= min(len(scene_ids), len(socket_options) * seal_positions):
        return _fail("covenant distinct-state contract is invalid")

    events = payload.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 8 * len(scene_ids) + 8:
        return _fail("covenant transcript is missing or outside limits")

    commitments: dict[str, tuple[str, int]] = {}
    reconstructions: list[str] = []
    storm_seen = False
    judgment_seen = False
    storm_started_ms: int | None = None
    last_elapsed_ms = -1
    active_scene_id = scene_ids[0]
    draft_socket: str | None = None
    draft_seal = scene_initial_seals[active_scene_id]
    draft_place_source: str | None = None
    draft_seal_source = "initial_state"
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            return _fail(f"event {sequence} sequence mismatch")
        elapsed_ms = event.get("elapsed_ms")
        if (
            isinstance(elapsed_ms, bool)
            or not isinstance(elapsed_ms, int)
            or elapsed_ms < last_elapsed_ms
        ):
            return _fail(f"event {sequence} task clock is invalid")
        last_elapsed_ms = elapsed_ms
        kind = str(event.get("kind") or "")
        expected_phase = "reconstruct" if judgment_seen else "commit"
        if kind in {"place", "seal"}:
            if storm_seen and not judgment_seen:
                return _fail(f"{kind} event occurred before the storm elapsed")
            if str(event.get("phase") or "") != expected_phase:
                return _fail(f"{kind} event occurred in the wrong phase")
            if str(event.get("scene_id") or "") != active_scene_id:
                return _fail(f"{kind} event targets the wrong covenant scene")
            if expected_sources is not None:
                expected_source = expected_sources[0] if kind == "place" else expected_sources[1]
                if str(event.get("input_source") or "") != expected_source:
                    return _fail(f"{kind} event uses the wrong interaction input")
            if kind == "place":
                socket = str(event.get("socket") or "")
                if socket not in socket_options:
                    return _fail("placement selected an invalid socket")
                draft_socket = socket
                draft_place_source = str(event.get("input_source") or "")
            else:
                seal = event.get("seal")
                if isinstance(seal, bool) or not isinstance(seal, int) or not 0 <= seal < seal_positions:
                    return _fail("seal event selected an invalid orientation")
                draft_seal = seal
                draft_seal_source = str(event.get("input_source") or "")
            continue
        if kind == "commit":
            scene_id = str(event.get("scene_id") or "")
            if (
                storm_seen
                or len(commitments) >= len(scene_ids)
                or scene_id != scene_ids[len(commitments)]
                or event.get("order_index") != len(commitments)
            ):
                return _fail("commitment order is invalid")
            socket, seal = str(event.get("socket") or ""), event.get("seal")
            if (
                socket not in socket_options
                or isinstance(seal, bool)
                or not isinstance(seal, int)
                or not 0 <= seal < seal_positions
                or scene_id in commitments
                or (socket, seal) != (draft_socket, draft_seal)
            ):
                return _fail("commitment state is invalid")
            if expected_sources is not None:
                if event.get("place_input_source") != draft_place_source:
                    return _fail("commitment placement uses the wrong interaction input")
                if event.get("seal_input_source") != draft_seal_source:
                    return _fail("commitment seal uses the wrong interaction input")
            commitments[scene_id] = (socket, seal)
            if len(commitments) < len(scene_ids):
                active_scene_id = scene_ids[len(commitments)]
                draft_socket = None
                draft_seal = scene_initial_seals[active_scene_id]
                draft_place_source = None
                draft_seal_source = "initial_state"
            continue
        if kind == "storm":
            distinct = len(set(commitments.values()))
            if (
                storm_seen
                or len(commitments) != len(scene_ids)
                or distinct < minimum_distinct_states
            ):
                return _fail(
                    f"ledger transition is invalid; distinct states {distinct}/{minimum_distinct_states}"
                )
            storm_seen = True
            storm_started_ms = elapsed_ms
            continue
        if kind == "judgment":
            required_storm_ms = int(ground_truth.get("storm_ms") or 0)
            if (
                not storm_seen
                or judgment_seen
                or storm_started_ms is None
                or elapsed_ms - storm_started_ms < required_storm_ms
            ):
                observed_ms = (
                    0 if storm_started_ms is None else elapsed_ms - storm_started_ms
                )
                return _fail(
                    f"storm elapsed {observed_ms}/{required_storm_ms} ms before judgment"
                )
            judgment_seen = True
            active_scene_id = boss_order[0]
            draft_socket = None
            draft_seal = scene_initial_seals[active_scene_id]
            draft_place_source = None
            draft_seal_source = "initial_state"
            continue
        if kind == "reconstruct":
            if not judgment_seen or len(reconstructions) >= len(boss_order):
                return _fail("reconstruction began outside judgment")
            scene_id = str(event.get("scene_id") or "")
            if (
                scene_id != boss_order[len(reconstructions)]
                or event.get("order_index") != len(reconstructions)
            ):
                return _fail("judgment order was not followed")
            answer = (str(event.get("socket") or ""), event.get("seal"))
            if answer != commitments.get(scene_id) or answer != (draft_socket, draft_seal):
                return _fail("a covenant was reconstructed incorrectly")
            if expected_sources is not None:
                if event.get("place_input_source") != draft_place_source:
                    return _fail("reconstruction placement uses the wrong interaction input")
                if event.get("seal_input_source") != draft_seal_source:
                    return _fail("reconstruction seal uses the wrong interaction input")
            reconstructions.append(scene_id)
            if len(reconstructions) < len(boss_order):
                active_scene_id = boss_order[len(reconstructions)]
                draft_socket = None
                draft_seal = scene_initial_seals[active_scene_id]
                draft_place_source = None
                draft_seal_source = "initial_state"
            continue
        return _fail(f"unknown covenant event {kind}")

    distinct = len(set(commitments.values()))
    passed = (
        judgment_seen
        and len(commitments) == len(scene_ids)
        and distinct >= minimum_distinct_states
        and reconstructions == boss_order
    )
    return {
        "graded": True,
        "passed": passed,
        "feedback": (
            f"covenants reconstructed {len(reconstructions)}/{len(scene_ids)} after occlusion; "
            f"distinct states {distinct}/{minimum_distinct_states}"
        ),
    }
