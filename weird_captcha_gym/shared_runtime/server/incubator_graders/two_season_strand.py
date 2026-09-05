from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "two_season_strand"


def _fail(feedback: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": feedback}


def _pairs(sequence: list[int], order: list[int]) -> list[list[int]]:
    stacks: dict[int, list[int]] = {0: [], 1: []}
    result: list[list[int]] = []
    for index in order:
        color = sequence[index]
        if color in (0, 1):
            stacks[color].append(index)
        else:
            opener = 1 if color == 2 else 0
            if stacks[opener]:
                result.append(sorted((stacks[opener].pop(), index)))
    return sorted(result)


def _integer_sequence(value: Any, length: int, label: str) -> list[int]:
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"{label} has the wrong length")
    if any(isinstance(item, bool) or not isinstance(item, int) or item not in range(4) for item in value):
        raise ValueError(f"{label} contains an invalid bead colour")
    return list(value)


def _order(value: Any, length: int, label: str) -> list[int]:
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"{label} order has the wrong length")
    if any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        raise ValueError(f"{label} order contains a non-integer index")
    if sorted(value) != list(range(length)):
        raise ValueError(f"{label} order is not a permutation of the strand")
    return list(value)


def _pair_list(value: Any, length: int, label: str) -> list[list[int]]:
    if not isinstance(value, list):
        raise ValueError(f"{label} pair set is missing")
    pairs: list[list[int]] = []
    seen: set[int] = set()
    for raw in value:
        if not isinstance(raw, list) or len(raw) != 2:
            raise ValueError(f"{label} contains a malformed pair")
        left, right = raw
        if any(isinstance(item, bool) or not isinstance(item, int) for item in raw):
            raise ValueError(f"{label} contains a non-integer pair")
        if not 0 <= left < right < length:
            raise ValueError(f"{label} contains an out-of-range pair")
        if left in seen or right in seen:
            raise ValueError(f"{label} pairs one bead more than once")
        seen.update((left, right))
        pairs.append([left, right])
    if pairs != sorted(pairs):
        raise ValueError(f"{label} pair set is not canonical")
    return pairs


def _binding(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> str | None:
    for label, record in (("payload", payload), ("ground truth", ground_truth), ("public state", public_state)):
        if str(record.get("mechanic_id") or "") != MECHANIC_ID:
            return f"{label} mechanic mismatch"
    challenge_id = str(ground_truth.get("challenge_id") or "")
    task_id = str(ground_truth.get("task_id") or "")
    if not challenge_id or str(payload.get("challenge_id") or "") != challenge_id:
        return "stale challenge"
    if str(public_state.get("challenge_id") or "") != challenge_id:
        return "public challenge mismatch"
    if not task_id or str(payload.get("task_id") or "") != task_id:
        return "payload task mismatch"
    if str(public_state.get("task_id") or "") != task_id:
        return "public task mismatch"
    return None


def _contract(ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    parameters = ground_truth.get("parameters")
    if not isinstance(parameters, dict) or parameters != public_state.get("parameters"):
        raise ValueError("public difficulty parameters differ from the hidden contract")
    length = int(parameters.get("strand_length") or 0)
    budget = int(parameters.get("edit_budget") or 0)
    if length % 8 or not 40 <= length <= 88 or not 2 <= budget <= 40:
        raise ValueError("strand dimensions are outside supported limits")
    initial = _integer_sequence(ground_truth.get("initial_sequence"), length, "initial strand")
    canonical = _integer_sequence(ground_truth.get("canonical_sequence"), length, "canonical strand")
    if public_state.get("initial_sequence") != initial:
        raise ValueError("public initial strand differs from the hidden contract")
    orders_raw = ground_truth.get("season_orders")
    if not isinstance(orders_raw, dict) or orders_raw != public_state.get("season_orders"):
        raise ValueError("season traversal contract mismatch")
    orders = {
        season: _order(orders_raw.get(season), length, season)
        for season in ("spring", "winter")
    }
    targets_raw = ground_truth.get("target_pairs")
    if not isinstance(targets_raw, dict) or targets_raw != public_state.get("target_pairs"):
        raise ValueError("public blueprints differ from the hidden contract")
    targets = {
        season: _pair_list(targets_raw.get(season), length, season)
        for season in ("spring", "winter")
    }
    for season in ("spring", "winter"):
        if _pairs(canonical, orders[season]) != targets[season]:
            raise ValueError(f"{season} blueprint is not generated by the canonical strand")
    return {
        "length": length,
        "budget": budget,
        "initial": initial,
        "orders": orders,
        "targets": targets,
    }


def _indices(value: Any, length: int) -> list[int]:
    if not isinstance(value, list) or not value:
        raise ValueError("edited bead indices are missing")
    if any(isinstance(item, bool) or not isinstance(item, int) or not 0 <= item < length for item in value):
        raise ValueError("edited bead index is invalid")
    if len(set(value)) != len(value):
        raise ValueError("edited bead indices repeat")
    return list(value)


def _pair_progress(sequence: list[int], orders: dict[str, list[int]], targets: dict[str, list[list[int]]]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for season in ("spring", "winter"):
        current = _pairs(sequence, orders[season])
        target_set = {tuple(pair) for pair in targets[season]}
        result[season] = {
            "paired": len(current),
            "matched": len(target_set & {tuple(pair) for pair in current}),
            "target": len(target_set),
        }
    return result


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    binding_error = _binding(payload, ground_truth, public_state)
    if binding_error:
        return _fail(binding_error)
    truth_condition = ground_truth.get("control_condition")
    if truth_condition != public_state.get("control_condition"):
        return _fail("public control condition differs from the hidden contract")
    interaction = str((truth_condition or {}).get("interaction") or "full")
    if interaction not in {"simplified", "full"}:
        return _fail("interaction condition is invalid")
    if str(payload.get("interaction_mode") or "") != interaction:
        return _fail("payload interaction mode mismatch")
    try:
        contract = _contract(ground_truth, public_state)
    except (TypeError, ValueError) as exc:
        return _fail(f"invalid strand contract: {exc}")

    events = payload.get("edits")
    if not isinstance(events, list) or len(events) > 80:
        return _fail("edit transcript is missing or outside limits")
    sequence = contract["initial"][:]
    edit_count = 0
    for sequence_number, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence_number:
            return _fail(f"edit {sequence_number} has an invalid sequence number")
        source = str(event.get("input_source") or "")
        allowed = {"palette_apply"} if interaction == "simplified" else {"strand_drag"}
        if source not in allowed:
            return _fail(f"edit {sequence_number} uses the wrong interaction input")
        color = event.get("color")
        if isinstance(color, bool) or not isinstance(color, int) or color not in range(4):
            return _fail(f"edit {sequence_number} has an invalid colour")
        try:
            indices = _indices(event.get("indices"), contract["length"])
        except ValueError as exc:
            return _fail(f"edit {sequence_number} is malformed: {exc}")
        if source == "palette_apply" and len(indices) != 1:
            return _fail(f"edit {sequence_number} must affect exactly one bead")
        if source == "strand_drag":
            if any(abs(left - right) != 1 for left, right in zip(indices, indices[1:])):
                return _fail(f"edit {sequence_number} is not one contiguous paint stroke")
            gesture = event.get("gesture")
            if not isinstance(gesture, dict):
                return _fail(f"edit {sequence_number} is missing its drag evidence")
            samples = gesture.get("sample_count")
            travel = gesture.get("travel_px")
            if isinstance(samples, bool) or not isinstance(samples, int) or samples < max(3, len(indices)):
                return _fail(f"edit {sequence_number} has too few pointer samples")
            if isinstance(travel, bool) or not isinstance(travel, (int, float)) or not math.isfinite(float(travel)):
                return _fail(f"edit {sequence_number} has invalid pointer travel")
            if float(travel) < max(12.0, 10.0 * (len(indices) - 1)):
                return _fail(f"edit {sequence_number} drag is shorter than its painted run")
            if gesture.get("start_index") != indices[0] or gesture.get("end_index") != indices[-1]:
                return _fail(f"edit {sequence_number} drag endpoints do not match its painted run")
        changed = [index for index in indices if sequence[index] != color]
        if not changed:
            return _fail(f"edit {sequence_number} does not change the strand")
        for index in indices:
            sequence[index] = color
        edit_count += len(changed)
        if edit_count > contract["budget"]:
            return _fail(f"edit budget exceeded at edit {sequence_number}")
        if event.get("changed_count") != len(changed):
            return _fail(f"edit {sequence_number} has an inconsistent changed-bead count")
        expected_progress = _pair_progress(sequence, contract["orders"], contract["targets"])
        if event.get("pair_progress_after") != expected_progress:
            return _fail(f"edit {sequence_number} has inconsistent fold feedback")

    current_pairs = {
        season: _pairs(sequence, contract["orders"][season])
        for season in ("spring", "winter")
    }
    if payload.get("final_sequence") != sequence:
        return _fail("submitted strand does not match replay")
    if payload.get("folds") != current_pairs:
        return _fail("submitted seasonal folds do not match replay")
    if payload.get("edit_count") != edit_count:
        return _fail("submitted edit count does not match replay")
    exact = all(current_pairs[season] == contract["targets"][season] for season in ("spring", "winter"))
    passed = payload.get("completed") is True and exact and 0 < edit_count <= contract["budget"]
    progress = _pair_progress(sequence, contract["orders"], contract["targets"])
    return {
        "graded": True,
        "passed": passed,
        "feedback": (
            f"two-season replay: Spring {progress['spring']['matched']}/{progress['spring']['target']} stems; "
            f"Winter {progress['winter']['matched']}/{progress['winter']['target']} stems; "
            f"edits {edit_count}/{contract['budget']}"
        ),
    }


def cheat(public_state: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_sequence": ground_truth.get("canonical_sequence") or [],
        "mutated_indices": ground_truth.get("mutated_indices") or [],
        "canonical_paint_run": ground_truth.get("canonical_paint_run") or [],
        "instruction": "Restore the canonical bead colours, then seal both seasonal folds.",
        "answers": [],
    }
