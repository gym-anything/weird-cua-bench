from __future__ import annotations

import hashlib
import json
import math
from typing import Any


MECHANIC_ID = "parallel_grillmaster"
PUBLIC_KEY_FIELD = "trusted_interaction_public_key"
ALGORITHM = "rsa-sha256-pkcs1-v1_5"
INPUT_SOURCES = {
    "simplified": "grill_proxy_controls",
    "full": "food_drag",
}
EVENT_SURFACES = {
    "simplified": "selection_plus_proxy_button",
    "full": "pointer_drag",
}
WITNESSED_ROUTES = {
    "simplified": "simplified_proxy",
    "full": "full_drop",
}
ACCEPTS_BROWSER_RUNTIME_CONTEXT = True
_SHA256_DIGEST_INFO_PREFIX = bytes.fromhex(
    "3031300d060960864801650304020105000420"
)


def _identity_error(
    payload: dict[str, Any],
    ground_truth: dict[str, Any],
    public_state: dict[str, Any],
) -> str | None:
    mechanic_ids = {
        str(payload.get("mechanic_id") or ""),
        str(ground_truth.get("mechanic_id") or ""),
        str(public_state.get("mechanic_id") or ""),
    }
    if mechanic_ids != {MECHANIC_ID}:
        return "mechanic identity mismatch"
    challenge_ids = {
        str(payload.get("challenge_id") or ""),
        str(ground_truth.get("challenge_id") or ""),
        str(public_state.get("challenge_id") or ""),
    }
    if len(challenge_ids) != 1 or "" in challenge_ids:
        return "challenge identity mismatch"
    task_ids = {
        str(payload.get("task_id") or ""),
        str(ground_truth.get("task_id") or ""),
        str(public_state.get("task_id") or ""),
    }
    if len(task_ids) != 1 or "" in task_ids:
        return "task identity mismatch"
    return None


def _encoded_message(value: dict[str, Any], size: int) -> bytes:
    digest_info = _SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).digest()
    padding = b"\xff" * (size - len(digest_info) - 3)
    if len(padding) < 8:
        raise ValueError("witness key is too short")
    return b"\x00\x01" + padding + b"\x00" + digest_info


def _verify_server_witness(
    witness: Any,
    ground_truth: dict[str, Any],
) -> str | None:
    if not isinstance(witness, dict):
        return "server-witnessed grill actions are missing"
    expected_key = ground_truth.get(PUBLIC_KEY_FIELD)
    if not isinstance(expected_key, dict):
        return "server witness key is not bound to the hidden challenge"
    if witness.get("public_key") != expected_key:
        return "server witness public key differs from the hidden challenge"
    if (
        str(witness.get("mechanic_id") or "") != MECHANIC_ID
        or str(witness.get("task_id") or "")
        != str(ground_truth.get("task_id") or "")
        or str(witness.get("challenge_id") or "")
        != str(ground_truth.get("challenge_id") or "")
        or str(witness.get("clock_source") or "")
        != "server_active_task_clock_v1"
    ):
        return "server witness identity or clock source is invalid"
    signature_hex = str(witness.get("signature_hex") or "")
    signed = dict(witness)
    signed.pop("signature_hex", None)
    try:
        modulus = int(str(expected_key["n_hex"]), 16)
        exponent = int(expected_key["e"])
        signature = int(signature_hex, 16)
        size = (modulus.bit_length() + 7) // 8
        expected = _encoded_message(signed, size)
        actual = pow(signature, exponent, modulus).to_bytes(size, "big")
    except (KeyError, TypeError, ValueError, OverflowError):
        return "server witness signature is malformed"
    if actual != expected:
        return "server witness signature is invalid"
    return None


def _witness_for_grade(
    payload: dict[str, Any],
    ground_truth: dict[str, Any],
    runtime_context: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None, str]:
    if (
        isinstance(runtime_context, dict)
        and runtime_context.get("surface")
        == "static_browser_nonauthoritative"
    ):
        witness = runtime_context.get("witness")
        if not isinstance(witness, dict):
            return None, "static browser interaction witness is missing", ""
        if (
            str(witness.get("mechanic_id") or "") != MECHANIC_ID
            or str(witness.get("task_id") or "")
            != str(ground_truth.get("task_id") or "")
            or str(witness.get("challenge_id") or "")
            != str(ground_truth.get("challenge_id") or "")
            or str(witness.get("clock_source") or "")
            != "static_browser_task_clock_v1"
        ):
            return None, "static browser interaction witness is invalid", ""
        return witness, None, "static-browser nonauthoritative"

    witness = payload.get("trusted_witness")
    error = _verify_server_witness(witness, ground_truth)
    return (
        witness if isinstance(witness, dict) else None,
        error,
        "server-attested",
    )


def _replay_actions(
    raw: Any,
    food_ids: set[str],
    expected_source: str,
    expected_surface: str,
    expected_route: str,
) -> tuple[
    dict[str, float] | None,
    dict[str, float] | None,
    str | None,
]:
    if not isinstance(raw, list) or len(raw) != 2 * len(food_ids):
        return (
            None,
            None,
            "witness must contain one start and one serve for every food",
        )
    starts: dict[str, float] = {}
    durations: dict[str, float] = {}
    previous_time = -1.0
    previous_wall_ns = -1
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            return None, None, "witness contains a malformed action"
        try:
            sequence = int(item.get("sequence"))
            timestamp = float(item.get("task_time_ms"))
        except (TypeError, ValueError):
            return None, None, "witness contains invalid sequence or time values"
        food_id = str(item.get("food_id") or "")
        kind = str(item.get("kind") or "")
        source = str(item.get("input_source") or "")
        surface = str(item.get("event_surface") or "")
        witnessed_route = str(item.get("witnessed_route") or "")
        if sequence != index or food_id not in food_ids or kind not in {
            "start",
            "serve",
        }:
            return None, None, "witness is not a valid monotonic grill sequence"
        if not math.isfinite(timestamp) or timestamp < previous_time:
            return None, None, "witness task time is invalid or non-monotonic"
        if (
            source != expected_source
            or surface != expected_surface
            or witnessed_route != expected_route
        ):
            return None, None, "witness uses the wrong interaction event surface"
        wall_value = item.get("server_received_wall_ns")
        if wall_value is not None:
            try:
                wall_ns = int(wall_value)
            except (TypeError, ValueError):
                return None, None, "witness server receipt time is invalid"
            if wall_ns <= previous_wall_ns:
                return None, None, "witness server receipt order is invalid"
            previous_wall_ns = wall_ns
        previous_time = timestamp
        if kind == "start":
            if food_id in starts or food_id in durations:
                return None, None, "food was started more than once"
            starts[food_id] = timestamp
        else:
            if food_id not in starts or food_id in durations:
                return (
                    None,
                    None,
                    "food was served before starting or more than once",
                )
            durations[food_id] = timestamp - starts[food_id]
    if set(starts) != food_ids or set(durations) != food_ids:
        return None, None, "witness does not cover every food"
    return starts, durations, None


def grade(
    payload: dict[str, Any],
    ground_truth: dict[str, Any],
    public_state: dict[str, Any],
    runtime_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error = _identity_error(payload, ground_truth, public_state)
    if error:
        return {"graded": True, "passed": False, "feedback": error}
    targets = ground_truth.get("targets") or {}
    if not isinstance(targets, dict) or not targets:
        return {
            "graded": True,
            "passed": False,
            "feedback": "hidden grill contract is missing",
        }
    food_ids = {str(food_id) for food_id in targets}
    public_food_ids = {
        str(food.get("id") or "")
        for food in public_state.get("foods") or []
        if isinstance(food, dict)
    }
    if public_food_ids != food_ids:
        return {
            "graded": True,
            "passed": False,
            "feedback": "public foods differ from the grill contract",
        }

    truth_condition = ground_truth.get("control_condition")
    if public_state.get("control_condition") != truth_condition:
        return {
            "graded": True,
            "passed": False,
            "feedback": "public interaction condition differs from grill contract",
        }
    interaction = str(
        (truth_condition or {}).get("interaction")
        or "full"
    )
    expected_source = INPUT_SOURCES.get(interaction)
    expected_surface = EVENT_SURFACES.get(interaction)
    expected_route = WITNESSED_ROUTES.get(interaction)
    if (
        expected_source is None
        or expected_surface is None
        or expected_route is None
    ):
        return {
            "graded": True,
            "passed": False,
            "feedback": "grill interaction condition is invalid",
        }

    witness, witness_error, evidence_label = _witness_for_grade(
        payload,
        ground_truth,
        runtime_context,
    )
    if witness_error or witness is None:
        return {
            "graded": True,
            "passed": False,
            "feedback": witness_error or "interaction witness is missing",
        }
    if str(witness.get("interaction") or "") != interaction:
        return {
            "graded": True,
            "passed": False,
            "feedback": "witness interaction differs from the challenge",
        }
    starts, durations, replay_error = _replay_actions(
        witness.get("actions"),
        food_ids,
        expected_source,
        expected_surface,
        expected_route,
    )
    if replay_error or starts is None or durations is None:
        return {
            "graded": True,
            "passed": False,
            "feedback": replay_error or "invalid witnessed action stream",
        }

    correct = 0
    for food_id, target in targets.items():
        try:
            elapsed = float(durations[str(food_id)])
            target_ms = float(target.get("target_ms"))
            tolerance_ms = float(target.get("tolerance_ms"))
        except (TypeError, ValueError, KeyError):
            continue
        if abs(elapsed - target_ms) <= tolerance_ms:
            correct += 1

    parallel_ok = True
    parallel_feedback = "sequential starts allowed"
    if truth_condition is not None:
        parameters = dict(
            truth_condition.get("difficulty_parameters") or {}
        )
        parallel_count = int(
            parameters.get("parallel_start_count", 1)
        )
        parallel_window = parameters.get("parallel_start_window_ms")
        if parallel_count > 1:
            if parallel_window is None:
                parallel_ok = False
                parallel_feedback = "concurrent start contract is missing"
            else:
                earliest = sorted(starts.values())[:parallel_count]
                spread = earliest[-1] - earliest[0]
                parallel_ok = spread <= float(parallel_window)
                parallel_feedback = (
                    f"first {parallel_count} start spread {spread:.0f}ms/"
                    f"{float(parallel_window):.0f}ms"
                )

    passed = correct == len(food_ids) and parallel_ok
    return {
        "graded": True,
        "passed": passed,
        "feedback": (
            f"{evidence_label}; foods {correct}/{len(food_ids)}; "
            f"{parallel_feedback}"
        ),
    }


def cheat(
    public_state: dict[str, Any],
    ground_truth: dict[str, Any],
) -> dict[str, Any]:
    if (
        str(public_state.get("mechanic_id") or "") != MECHANIC_ID
        or str(ground_truth.get("mechanic_id") or "") != MECHANIC_ID
        or str(public_state.get("challenge_id") or "")
        != str(ground_truth.get("challenge_id") or "")
    ):
        return {"error": "challenge identity mismatch"}
    return {"targets": ground_truth.get("targets") or {}}
