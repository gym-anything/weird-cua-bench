from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


MECHANIC_ID = "bandaged_rose_window"
DISC_IDS = ("north", "southwest", "southeast")
DISC_SLOTS = ((3, 7, 6, 0, 5, 4), (3, 10, 9, 1, 8, 7), (3, 4, 12, 2, 11, 10))
BENCHMARK_ROOT = Path(__file__).resolve().parents[4]
HELPER_PATH = BENCHMARK_ROOT / "shared_runtime" / "verifier_helpers.py"


def _load_helpers():
    spec = importlib.util.spec_from_file_location("bandaged_rose_verifier_helpers", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {HELPER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _legal(state: tuple[int, ...], disc: int) -> bool:
    slots = DISC_SLOTS[disc]
    return state.index(3) in slots and all(point == disc or state.index(point) not in slots for point in range(3))


def _turn(state: tuple[int, ...], disc: int, direction: int) -> tuple[int, ...]:
    slots = DISC_SLOTS[disc]
    values = [state[index] for index in slots]
    values = values[-1:] + values[:-1] if direction == 1 else values[1:] + values[:1]
    result = list(state)
    for slot, value in zip(slots, values):
        result[slot] = value
    return tuple(result)


def _verify_export(exported: dict[str, Any]) -> tuple[bool, str]:
    payload = exported.get("result") or {}
    truth = exported.get("ground_truth") or {}
    public = exported.get("public_state") or {}
    challenge = str(truth.get("challenge_id") or "")
    if payload.get("mechanic_id") != MECHANIC_ID or truth.get("mechanic_id") != MECHANIC_ID:
        return False, "mechanic mismatch"
    if not challenge or payload.get("challenge_id") != challenge or public.get("challenge_id") != challenge:
        return False, "stale challenge"
    if payload.get("task_id") != truth.get("task_id") or public.get("task_id") != truth.get("task_id"):
        return False, "task mismatch"
    rose = truth.get("rose") or {}
    if public.get("rose") != rose or public.get("control_condition") != truth.get("control_condition"):
        return False, "public contract mismatch"
    expected_source = {"simplified": "proxy_buttons", "full": "rim_drag"}.get(str((truth.get("control_condition") or {}).get("interaction") or "full"))
    if expected_source is None:
        return False, "invalid interaction condition"
    try:
        state = tuple(int(value) for value in rose["initial_state"])
        solved = tuple(int(value) for value in rose["solved_state"])
    except (KeyError, TypeError, ValueError):
        return False, "invalid rose contract"
    events = payload.get("events")
    if not isinstance(events, list) or len(events) > 200:
        return False, "invalid transcript"
    successful = refused = 0
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence or event.get("input_source") != expected_source:
            return False, f"event {sequence} header mismatch"
        try:
            disc = DISC_IDS.index(str(event.get("disc_id")))
            direction = int(event.get("direction"))
            before = tuple(int(value) for value in event.get("before_state", []))
            after = tuple(int(value) for value in event.get("after_state", []))
        except (TypeError, ValueError):
            return False, f"event {sequence} malformed"
        if direction not in (-1, 1) or before != state:
            return False, f"event {sequence} before-state mismatch"
        allowed = _legal(state, disc)
        expected = _turn(state, disc, direction) if allowed else state
        successful += int(allowed)
        refused += int(not allowed)
        if event.get("outcome") != ("turned" if allowed else "refused") or after != expected or event.get("turns_after") != successful:
            return False, f"event {sequence} physics mismatch"
        state = expected
    complete = state == solved
    claims_match = (
        payload.get("final_state") == list(state)
        and payload.get("successful_turns") == successful
        and payload.get("refused_turns") == refused
        and payload.get("completed") is complete
    )
    if not claims_match:
        return False, "final claims mismatch"
    return complete, f"independent rose replay {'restored' if complete else 'incomplete'} after {successful} successful turns"


def verify_task(traj=None, env_info=None, task_info=None):
    del traj, task_info
    try:
        exported, error = _load_helpers().load_exported_result(env_info or {})
    except Exception as exc:
        return {"passed": False, "score": 0, "feedback": f"cannot load verifier dependency: {exc}"}
    if error:
        return {"passed": False, "score": 0, "feedback": error}
    passed, feedback = _verify_export(exported or {})
    return {"passed": passed, "score": 100 if passed else 0, "feedback": feedback}
