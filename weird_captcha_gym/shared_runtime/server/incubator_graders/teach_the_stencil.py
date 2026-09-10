from __future__ import annotations

import math
from typing import Any


MECHANIC_ID = "teach_the_stencil"
_MIN_FULL_PATH_LENGTH = 4.0

_BRUSH_OFFSETS: dict[int, tuple[tuple[int, int], ...]] = {
    1: ((0, 0),),
    2: ((0, 0), (1, 0)),
    3: ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)),
    4: ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1)),
    5: (
        (0, 0), (1, 0), (-1, 0), (0, 1), (0, -1),
        (1, 1), (-1, -1), (1, -1), (-1, 1), (2, 0), (-2, 0), (0, 2), (0, -2),
    ),
}


def _fail(message: str) -> dict[str, Any]:
    return {"graded": True, "passed": False, "score": 0, "feedback": message}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _condition(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _interaction_sources(interaction: str) -> tuple[str, str]:
    if interaction == "simplified":
        return "proxy_stamp", "proxy_erase"
    if interaction == "full":
        return "brush_drag", "eraser_drag"
    return "", ""


def _brush_size(value: Any) -> int | None:
    if value is None:
        return 1
    try:
        size = int(float(value))
    except (TypeError, ValueError):
        return None
    return size if size in _BRUSH_OFFSETS else None


def _brush_points(point: tuple[float, float], size: int, width: int, height: int) -> list[tuple[int, int]]:
    base_x, base_y = int(math.floor(point[0])), int(math.floor(point[1]))
    result: list[tuple[int, int]] = []
    for offset_x, offset_y in _BRUSH_OFFSETS[size]:
        x, y = base_x + offset_x, base_y + offset_y
        if not (0 <= x < width and 0 <= y < height):
            continue
        if (x, y) not in result:
            result.append((x, y))
    return result


def _eraser_radius(size: int) -> float:
    return 0.8 + 0.55 * float(size)


def _path_length(points: list[tuple[float, float]]) -> float:
    return sum(math.hypot(right[0] - left[0], right[1] - left[1]) for left, right in zip(points, points[1:]))


def _raw_point_key(point: tuple[float, float]) -> tuple[int, int]:
    return int(math.floor(point[0])), int(math.floor(point[1]))


def _feature_distance(feature: list[float], centroid: list[float]) -> float:
    # Color is normalized so the surface texture channel can affect decisions
    # without overwhelming RGB differences.
    return sum((float(feature[i]) / 255.0 - float(centroid[i]) / 255.0) ** 2 for i in range(3)) + 0.65 * (float(feature[3]) - float(centroid[3])) ** 2


def _predict(features: list[list[float]], samples: list[dict[str, Any]], class_count: int) -> list[int]:
    centroids: dict[int, list[float]] = {}
    for class_id in range(class_count):
        points = [item["feature"] for item in samples if int(item["class_id"]) == class_id]
        if points:
            centroids[class_id] = [sum(float(point[channel]) for point in points) / len(points) for channel in range(4)]
    if len(centroids) != class_count:
        return [-1] * len(features)
    return [min(centroids, key=lambda class_id: _feature_distance(feature, centroids[class_id])) for feature in features]


def _valid_point(item: Any, width: int, height: int) -> tuple[float, float] | None:
    if not isinstance(item, dict):
        return None
    x, y = _number(item.get("x")), _number(item.get("y"))
    if x is None or y is None or not (0 <= x < width and 0 <= y < height):
        return None
    return x, y


def _mean_iou(predicted: list[int], target: list[int], class_count: int) -> tuple[float, list[float]]:
    ious: list[float] = []
    for class_id in range(class_count):
        intersection = sum(1 for left, right in zip(predicted, target, strict=True) if left == right == class_id)
        union = sum(1 for left, right in zip(predicted, target, strict=True) if left == class_id or right == class_id)
        ious.append(intersection / union if union else 0.0)
    return (sum(ious) / len(ious) if ious else 0.0), ious


def grade(payload: dict[str, Any], truth: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("mechanic_id") != MECHANIC_ID:
        return _fail("mechanic mismatch")
    if truth.get("mechanic_id") != MECHANIC_ID or public.get("mechanic_id") != MECHANIC_ID:
        return _fail("task state is not a Teach the Stencil challenge")
    if payload.get("task_id") != truth.get("task_id") or payload.get("challenge_id") != truth.get("challenge_id") or public.get("challenge_id") != truth.get("challenge_id"):
        return _fail("stale task or challenge")
    if payload.get("target_labels") is not None or payload.get("predicted_labels") is not None or payload.get("ground_truth") is not None:
        return _fail("submitted mask data is not an allowed browser action")

    condition = _condition(truth.get("control_condition"))
    if public.get("control_condition") != condition or payload.get("control_condition") != condition:
        return _fail("public interaction condition differs from the stencil contract")
    interaction = str(condition.get("interaction") or "")
    paint_source, erase_source = _interaction_sources(interaction)
    if not paint_source:
        return _fail("invalid stencil interaction condition")

    plate = public.get("plate") or {}
    width, height = int(truth.get("width") or 0), int(truth.get("height") or 0)
    features = plate.get("pixels")
    target = truth.get("target_labels")
    classes = public.get("classes") or []
    class_count = len(classes)
    if width <= 0 or height <= 0 or not isinstance(features, list) or len(features) != width * height or not isinstance(target, list) or len(target) != len(features) or class_count < 2:
        return _fail("malformed stencil state")

    events = payload.get("events")
    if not isinstance(events, list) or not events or len(events) > int(truth.get("sample_budget") or 120) * 8:
        return _fail("training transcript is empty or too long")

    selected: int | None = None
    selected_classes: set[int] = set()
    samples: list[dict[str, Any]] = []
    update_predictions: list[list[int]] = []
    update_changes: list[int] = []
    corrections = 0
    painted_points: set[tuple[int, int]] = set()
    last_action: str | None = None
    update_seen = False
    sample_count = 0

    for expected_sequence, event in enumerate(events, 1):
        if not isinstance(event, dict) or event.get("seq") != expected_sequence:
            return _fail(f"training action {expected_sequence} has an invalid sequence number")
        action = str(event.get("type") or "")
        if action == "select_class":
            try:
                class_id = int(event.get("class_id"))
            except (TypeError, ValueError):
                return _fail("class selection is malformed")
            if class_id not in range(class_count) or event.get("input_source") != "palette_button":
                return _fail("class selection did not use a visible palette button")
            selected = class_id
            selected_classes.add(class_id)
        elif action in {"paint", "erase"}:
            points = event.get("points")
            if not isinstance(points, list) or not points or len(points) > 160:
                return _fail("brush action has no bounded visible point list")
            expected_source = paint_source if action == "paint" else erase_source
            if event.get("input_source") != expected_source:
                return _fail("brush action uses the wrong interaction surface")
            if action == "paint":
                try:
                    class_id = int(event.get("class_id"))
                except (TypeError, ValueError):
                    return _fail("paint action has no class")
                if selected != class_id or class_id not in range(class_count):
                    return _fail("paint action was not bound to the selected visible class")
                selected_classes.add(class_id)
                parsed = [_valid_point(point, width, height) for point in points]
                if any(point is None for point in parsed):
                    return _fail("paint point is outside the visible plate")
                if interaction == "full" and (len(parsed) < 2 or _path_length(parsed) < _MIN_FULL_PATH_LENGTH):
                    return _fail("full brush action must contain a real drag")
                size = _brush_size(event.get("brush_size"))
                if size is None:
                    return _fail("brush size is outside the visible control range")
                event_keys = {_raw_point_key(point) for point in parsed}
                new_event_keys = event_keys.difference(painted_points)
                for x, y in parsed:
                    assert x is not None and y is not None
                    for sample_x, sample_y in _brush_points((x, y), size, width, height):
                        pixel_index = sample_y * width + sample_x
                        feature = features[pixel_index]
                        samples.append({"class_id": class_id, "x": sample_x, "y": sample_y, "feature": feature})
                sample_count += sum(len(_brush_points(point, size, width, height)) for point in parsed)
                if update_seen:
                    if new_event_keys:
                        corrections += 1
                painted_points.update(event_keys)
            else:
                parsed = [_valid_point(point, width, height) for point in points]
                if any(point is None for point in parsed):
                    return _fail("erase point is outside the visible plate")
                if interaction == "full" and (len(parsed) < 2 or _path_length(parsed) < _MIN_FULL_PATH_LENGTH):
                    return _fail("full eraser action must contain a real drag")
                size = _brush_size(event.get("brush_size"))
                if size is None:
                    return _fail("brush size is outside the visible control range")
                radius = _eraser_radius(size)
                for x, y in parsed:
                    assert x is not None and y is not None
                    samples = [item for item in samples if math.hypot(float(item["x"]) - x, float(item["y"]) - y) > radius]
        elif action == "live_update":
            if event.get("input_source") != "live_update_button" or not samples:
                return _fail("Live Update was not triggered from a visible trained model")
            predicted = _predict(features, samples, class_count)
            if predicted[0] < 0:
                return _fail("Live Update requires at least one example for every visible class")
            if update_predictions:
                changed = sum(left != right for left, right in zip(update_predictions[-1], predicted, strict=True))
            else:
                changed = len(predicted)
            update_predictions.append(predicted)
            update_changes.append(changed)
            update_seen = True
        elif action == "certify":
            if event.get("input_source") != "certify_button":
                return _fail("certification did not use the visible button")
            if expected_sequence != len(events):
                return _fail("no actions may follow certification")
        else:
            return _fail(f"unknown stencil action {action!r}")
        last_action = action

    if last_action != "certify" or len(events) < 2 or events[-2].get("type") != "live_update":
        return _fail("the final visible operation must be Live Update immediately before certification")
    if payload.get("completed") is not True:
        return _fail("certification was not completed")
    if sample_count > int(truth.get("sample_budget") or 0):
        return _fail("annotation budget exceeded")
    required = int(truth.get("required_samples_per_class") or 1)
    counts = {class_id: sum(1 for item in samples if int(item["class_id"]) == class_id) for class_id in range(class_count)}
    if selected_classes != set(range(class_count)) or any(counts[class_id] < required for class_id in range(class_count)):
        return _fail("every visible material needs representative labeled examples")
    predicted = update_predictions[-1]
    score, ious = _mean_iou(predicted, [int(item) for item in target], class_count)
    threshold = float(truth.get("threshold") or 1.0)
    passed = score >= threshold
    changed_updates = sum(1 for change in update_changes[1:] if change > 0)
    feedback = f"mean class IoU {score:.3f} (required {threshold:.3f}); updates {len(update_predictions)}; corrections {corrections}; changed updates {changed_updates}; class IoU {[round(value, 3) for value in ious]}"
    return {"graded": True, "passed": passed, "score": round(score * 100, 2), "feedback": feedback}
