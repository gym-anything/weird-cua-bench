from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "pocket_animation_studio"
FIELDS = {
    "circle": ("x", "y", "radius"),
    "rect": ("x", "y", "width", "height"),
    "line": ("x1", "y1", "x2", "y2", "width"),
}
ALL_EXPRESSION_TYPES = frozenset({"const", "linear", "reverse", "wave"})


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "feedback": message}


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def _expr_value(expression: dict[str, Any], t: float) -> float | None:
    if not isinstance(expression, dict):
        return None
    kind = str(expression.get("kind") or "const")
    if kind not in {"const", "linear", "reverse", "wave"}:
        return None
    a = _number(expression.get("a"))
    b = _number(expression.get("b", 0.0))
    if a is None or b is None:
        return None
    try:
        frequency = int(expression.get("frequency") or 1)
    except (TypeError, ValueError):
        return None
    if frequency < 1 or frequency > 8:
        return None
    if kind == "linear":
        value = a + b * t
    elif kind == "reverse":
        value = a + b * (1.0 - t)
    elif kind == "wave":
        value = a + b * math.sin(2.0 * math.pi * frequency * t)
    else:
        value = a
    if not math.isfinite(value):
        return None
    return max(0.0, min(100.0, value))


def _render(program: list[dict[str, Any]], t: float) -> list[dict[str, Any]] | None:
    rendered: list[dict[str, Any]] = []
    for shape in program:
        if not isinstance(shape, dict):
            return None
        kind = str(shape.get("kind") or "")
        if kind not in FIELDS:
            return None
        expressions = shape.get("expressions")
        if not isinstance(expressions, dict):
            return None
        item = {
            "id": str(shape.get("id") or ""),
            "kind": kind,
            "color": str(shape.get("color") or ""),
        }
        for field in FIELDS[kind]:
            value = _expr_value(expressions.get(field), t)
            if value is None:
                return None
            item[field] = value
        rendered.append(item)
    return rendered


def _event_counts(events: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        kind = str(event.get("type") or "")
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def _allowed_expression_types(ground_truth: dict[str, Any]) -> frozenset[str]:
    condition = ground_truth.get("control_condition") or {}
    parameters = condition.get("difficulty_parameters") or {}
    declared = parameters.get("allowed_expression_types")
    if not isinstance(declared, list):
        return ALL_EXPRESSION_TYPES
    return frozenset(str(kind) for kind in declared) & ALL_EXPRESSION_TYPES


def _validate_interaction(
    payload: dict[str, Any],
    truth: dict[str, Any],
    program: list[Any],
) -> str | None:
    condition = truth.get("control_condition") or {}
    expected = str(condition.get("interaction") or "full")
    actual = str(payload.get("interaction") or "")
    if actual != expected:
        return f"interaction mismatch: expected {expected}, received {actual or 'none'}"
    events = payload.get("events")
    if not isinstance(events, list):
        return "interaction event transcript missing"

    # Replay editor effects, not quotas or comparisons of historical edits to
    # the final values. Defaults, corrections and removal are legitimate UI use.
    built: list[dict[str, Any]] = []
    running = False
    preview = False
    certified = False
    runs = 0
    allowed = _allowed_expression_types(truth)
    shape_event = "drag_shape" if expected == "full" else "proxy_shape"
    expression_event = "drag_expression" if expected == "full" else "proxy_expression"

    def complete() -> bool:
        return bool(built) and all(
            all(field in shape["expressions"] for field in FIELDS[shape["kind"]])
            for shape in built
        )

    for event in events:
        if not isinstance(event, dict):
            return "interaction transcript contains a malformed event"
        kind = event.get("type")
        if not isinstance(kind, str):
            return "interaction event type is malformed"
        shape = next((item for item in built if item["id"] == event.get("shape_id")), None)
        if kind == shape_event:
            if not isinstance(event.get("kind"), str) or event["kind"] not in FIELDS or len(built) >= len(program):
                return "invalid shape addition"
            if event.get("shape_id") != f"shape-{len(built) + 1}":
                return "shape addition has an invalid identity"
            built.append({"id": event["shape_id"], "kind": event["kind"], "expressions": {}})
        elif kind == "remove_shape":
            if shape is None:
                return "removal references an unknown shape"
            built.remove(shape)
            for index, item in enumerate(built):
                item["id"] = f"shape-{index + 1}"
        elif kind in {expression_event, "numeric_edit"}:
            field = event.get("field")
            if shape is None or not isinstance(field, str) or field not in FIELDS[shape["kind"]]:
                return "interaction references an unknown field"
            expressions = shape["expressions"]
            if kind == expression_event:
                op = event.get("kind")
                if not isinstance(op, str) or op not in allowed:
                    return "expression is not allowed by this profile"
                expression = expressions.setdefault(
                    field, {"kind": op, "a": 50, "b": 0 if op == "const" else 20, "frequency": 1}
                )
                expression["kind"] = op
                if op == "const":
                    expression["b"] = 0
                if op != "wave":
                    expression["frequency"] = 1
            else:
                expression = expressions.get(field)
                part = event.get("part")
                if expression is None or not isinstance(part, str) or part not in {"kind", "a", "b", "frequency"}:
                    return "numeric edit references an unplaced expression or invalid part"
                value = event.get("value")
                if part == "kind":
                    if not isinstance(value, str) or value not in allowed:
                        return "expression is not allowed by this profile"
                    expression["kind"] = value
                    if value == "const":
                        expression["b"] = 0
                    if value != "wave":
                        expression["frequency"] = 1
                else:
                    value = _number(value)
                    if value is None or not -100 <= value <= 100:
                        return "numeric edit is outside the editor range"
                    if part == "frequency" and (not 1 <= value <= 8 or value != int(value)):
                        return "invalid frequency edit"
                    expression[part] = value
        elif kind == "run":
            if event.get("accepted") is True:
                if not complete():
                    return "accepted run has incomplete sockets"
                runs += 1
                running, preview, certified = True, False, False
            elif event.get("accepted") is not False or complete():
                return "invalid rejected run"
            continue
        elif kind == "preview_complete":
            if not running or _number(event.get("duration_ms")) != _number(truth.get("duration_ms")):
                return "preview completion has no current full run"
            running, preview = False, True
            continue
        elif kind == "certify":
            if not preview or not complete():
                return "certification has no completed current preview"
            certified = True
            continue
        else:
            return "unsupported or wrong-surface interaction event"
        # Any edit invalidates the previous preview, including an in-flight run.
        running, preview, certified = False, False, False

    if not runs or not preview or not certified:
        return "interaction requires a run, completed preview and certification"
    count = _number(payload.get("run_count"))
    # CLEAR PROGRAM resets the transcript but not the browser's lifetime counter.
    if count is None or count != int(count) or count < runs:
        return "invalid preview run count"
    if len(built) != len(program):
        return "interaction transcript does not construct the submitted shapes"
    for actual, recorded in zip(program, built):
        if not isinstance(actual, dict) or actual.get("id") != recorded["id"] or actual.get("kind") != recorded["kind"]:
            return "interaction transcript does not construct the submitted shape"
        expressions = actual.get("expressions")
        if not isinstance(expressions, dict):
            return "submitted expressions are malformed"
        for field in FIELDS[recorded["kind"]]:
            expression = expressions.get(field)
            replayed = recorded["expressions"].get(field)
            if not isinstance(expression, dict) or replayed is None or expression.get("kind") != replayed["kind"]:
                return "interaction transcript does not construct the submitted expression"
            for part in ("a", "b", "frequency"):
                value = _number(expression.get(part))
                # Browser events round numeric values to three decimal places.
                if value is None or abs(value - replayed[part]) > 0.000501:
                    return "interaction transcript does not match the final numeric value"
    return None


def grade(payload: dict[str, Any], ground_truth: dict[str, Any], public_state: dict[str, Any]) -> dict[str, Any]:
    if str(payload.get("mechanic_id") or "") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    if str(payload.get("task_id") or "") != str(ground_truth.get("task_id") or ""):
        return _fail("task mismatch")
    if str(payload.get("challenge_id") or "") != str(ground_truth.get("challenge_id") or ""):
        return _fail("stale challenge")
    if payload.get("completed") is not True:
        return _fail("certification was not completed")
    if payload.get("preview_complete") is not True:
        return _fail("the complete preview loop was not run")

    program = payload.get("program")
    target_program = ground_truth.get("target_program")
    if not isinstance(program, list) or not isinstance(target_program, list):
        return _fail("program is missing")
    if len(program) != len(target_program):
        return _fail(f"shape blocks {len(program)}/{len(target_program)}")

    interaction_error = _validate_interaction(payload, ground_truth, program)
    if interaction_error:
        return _fail(interaction_error)

    allowed_expression_types = _allowed_expression_types(ground_truth)

    for index, (actual, expected) in enumerate(zip(program, target_program)):
        if not isinstance(actual, dict) or not isinstance(expected, dict):
            return _fail(f"shape {index + 1} is malformed")
        if str(actual.get("kind") or "") != str(expected.get("kind") or ""):
            return _fail(f"shape {index + 1} has the wrong drawing block")
        if str(actual.get("color") or "") != str(expected.get("color") or ""):
            return _fail(f"shape {index + 1} has the wrong pen color")
        actual_fields = actual.get("expressions")
        expected_fields = expected.get("expressions")
        if not isinstance(actual_fields, dict) or not isinstance(expected_fields, dict):
            return _fail(f"shape {index + 1} is missing expression sockets")
        for field in FIELDS[str(expected.get("kind"))]:
            if field not in actual_fields:
                return _fail(f"shape {index + 1} is missing {field}")
            actual_expression = actual_fields.get(field)
            expected_expression = expected_fields.get(field)
            actual_kind = str(actual_expression.get("kind") or "") if isinstance(actual_expression, dict) else ""
            expected_kind = str(expected_expression.get("kind") or "") if isinstance(expected_expression, dict) else ""
            if actual_kind not in allowed_expression_types:
                return _fail(
                    f"shape {index + 1} field {field} uses {actual_kind or 'no'} expression; "
                    f"allowed: {', '.join(sorted(allowed_expression_types))}"
                )
            if expected_kind not in allowed_expression_types:
                return _fail(
                    f"target shape {index + 1} field {field} uses undeclared {expected_kind or 'no'} expression"
                )

    samples = ground_truth.get("target_frames")
    if not isinstance(samples, list) or not samples:
        return _fail("reference samples are missing")
    max_error = 0.0
    total_error = 0.0
    compared = 0
    for frame in samples:
        if not isinstance(frame, dict):
            return _fail("malformed reference frame")
        t = _number(frame.get("t"))
        expected_objects = frame.get("objects")
        if t is None or not isinstance(expected_objects, list):
            return _fail("malformed reference sample")
        actual_objects = _render(program, t)
        if actual_objects is None or len(actual_objects) != len(expected_objects):
            return _fail("program cannot be replayed across the reference duration")
        for actual, expected in zip(actual_objects, expected_objects):
            if actual["kind"] != expected.get("kind") or actual["color"] != expected.get("color"):
                return _fail("program draw order or appearance differs from the reference")
            fields = FIELDS[actual["kind"]]
            errors = [abs(float(actual[field]) - float(expected.get(field, 0.0))) for field in fields]
            if actual["kind"] == "line":
                # A line has no endpoint direction. Compare both complete
                # endpoint assignments, without mixing coordinates between them.
                reversed_fields = ("x2", "y2", "x1", "y1", "width")
                reversed_errors = [
                    abs(float(actual[field]) - float(expected.get(other, 0.0)))
                    for field, other in zip(fields, reversed_fields)
                ]
                errors = min((errors, reversed_errors), key=lambda values: (max(values), sum(values)))
            for error in errors:
                max_error = max(max_error, error)
                total_error += error
                compared += 1
    tolerance = float(ground_truth.get("tolerance") or 2.6)
    mean_error = total_error / max(1, compared)
    passed = max_error <= tolerance
    counts = _event_counts(payload.get("events") or [])
    feedback = (
        f"frames {len(samples)}; fields {compared}; max error {max_error:.2f}; "
        f"mean error {mean_error:.2f}; run events {counts.get('run', 0)}"
    )
    return {
        "graded": True,
        "passed": passed,
        "feedback": feedback if passed else f"animation mismatch: {feedback}; tolerance {tolerance:.2f}",
        "metrics": {
            "frames": len(samples),
            "fields": compared,
            "max_error": round(max_error, 4),
            "mean_error": round(mean_error, 4),
            "tolerance": tolerance,
        },
    }
