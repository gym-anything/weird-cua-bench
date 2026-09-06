from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


MECHANIC_ID = "flip_gate_cascade"
BENCHMARK_ROOT = Path(__file__).resolve().parents[4]
HELPER_PATH = BENCHMARK_ROOT / "shared_runtime" / "verifier_helpers.py"


def _load_helpers():
    spec = importlib.util.spec_from_file_location("flip_gate_verifier_helpers", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {HELPER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row_offsets(top_chutes: int, row_count: int) -> tuple[int, ...]:
    offsets: list[int] = []
    total = 0
    for row in range(row_count):
        offsets.append(total)
        total += top_chutes + row
    return tuple(offsets)


def _transition(
    state: tuple[int, ...],
    chute: int,
    top_chutes: int,
    row_count: int,
    entry_columns: tuple[int, ...],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    offsets = _row_offsets(top_chutes, row_count)
    result = list(state)
    column = entry_columns[chute]
    path: list[int] = []
    for row in range(row_count):
        gate = offsets[row] + column
        path.append(gate)
        points_right = bool(result[gate])
        result[gate] = 0 if points_right else 1
        if points_right:
            column += 1
    return tuple(result), tuple(path)


def _verify_export(exported: dict[str, Any]) -> tuple[bool, str]:
    payload = exported.get("result") or {}
    truth = exported.get("ground_truth") or {}
    public = exported.get("public_state") or {}
    challenge_id = str(truth.get("challenge_id") or "")
    if payload.get("mechanic_id") != MECHANIC_ID or truth.get("mechanic_id") != MECHANIC_ID:
        return False, "mechanic mismatch"
    if not challenge_id or payload.get("challenge_id") != challenge_id or public.get("challenge_id") != challenge_id:
        return False, "stale challenge"
    if payload.get("task_id") != truth.get("task_id") or public.get("task_id") != truth.get("task_id"):
        return False, "task mismatch"
    machine = truth.get("machine")
    if not isinstance(machine, dict) or public.get("machine") != machine:
        return False, "public machine mismatch"
    if public.get("control_condition") != truth.get("control_condition"):
        return False, "control condition mismatch"
    try:
        top_chutes = int(machine["top_chutes"])
        row_count = int(machine["row_count"])
        gate_count = int(machine["gate_count"])
        budget = int(machine["drop_budget"])
        entry_columns = tuple(int(value) for value in machine["entry_columns"])
        state = tuple(int(value) for value in machine["initial_state"])
        target = tuple(int(value) for value in machine["target_state"])
    except (KeyError, TypeError, ValueError):
        return False, "invalid machine contract"
    expected_gate_count = sum(top_chutes + row for row in range(row_count))
    if (
        not 2 <= top_chutes <= 5
        or not 2 <= row_count <= 4
        or gate_count != expected_gate_count
        or len(state) != gate_count
        or len(target) != gate_count
        or any(value not in (0, 1) for value in (*state, *target))
        or not 1 <= budget <= 16
        or sorted(entry_columns) != list(range(top_chutes))
        or any(chute == column for chute, column in enumerate(entry_columns))
    ):
        return False, "machine geometry mismatch"
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "simplified")
    expected_source = {"simplified": "chute_click", "full": "marble_drag"}.get(interaction)
    if expected_source is None:
        return False, "invalid interaction condition"
    events = payload.get("events")
    if not isinstance(events, list) or len(events) > budget:
        return False, "invalid drop transcript"
    reached_at: int | None = None
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence or event.get("input_source") != expected_source:
            return False, f"drop {sequence} header mismatch"
        if reached_at is not None:
            return False, "drop after completion"
        try:
            chute = int(event.get("chute"))
            before = tuple(int(value) for value in event.get("before_state", []))
            after = tuple(int(value) for value in event.get("after_state", []))
            path = tuple(int(value) for value in event.get("path", []))
        except (TypeError, ValueError):
            return False, f"drop {sequence} malformed"
        if chute < 0 or chute >= top_chutes or before != state:
            return False, f"drop {sequence} invalid input"
        expected_after, expected_path = _transition(
            state, chute, top_chutes, row_count, entry_columns
        )
        if (
            after != expected_after
            or path != expected_path
            or event.get("drops_after") != sequence
            or event.get("settled") is not True
        ):
            return False, f"drop {sequence} physics mismatch"
        state = expected_after
        if state == target:
            reached_at = sequence
    completed = reached_at is not None and reached_at <= budget
    claims_match = (
        payload.get("final_state") == list(state)
        and payload.get("drops_used") == len(events)
        and payload.get("completed") is completed
        and payload.get("budget_exhausted") is (len(events) >= budget and not completed)
    )
    if not claims_match:
        return False, "final claims mismatch"
    return completed, (
        f"independent flip-gate replay matched the target after {reached_at} drops"
        if completed
        else f"independent replay remained incomplete after {len(events)} drops"
    )


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
