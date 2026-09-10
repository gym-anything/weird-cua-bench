from __future__ import annotations

import json
import math
import time
from pathlib import Path


MECHANIC_ID = "teach_the_stencil"
MIN_FULL_PATH_LENGTH = 4.0


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _point_lists(public: dict, truth: dict) -> dict[int, list[tuple[int, int]]]:
    width = int(truth["width"])
    by_class: dict[int, list[tuple[int, int]]] = {class_id: [] for class_id in range(len(truth["class_names"]))}
    for index, label in enumerate(truth["target_labels"]):
        by_class[int(label)].append((index % width, index // width))
    return by_class


def _feature_distance(feature: list[float], centroid: list[float]) -> float:
    return sum((float(feature[i]) / 255.0 - float(centroid[i]) / 255.0) ** 2 for i in range(3)) + 0.65 * (float(feature[3]) - float(centroid[3])) ** 2


def _predict(public: dict, samples: list[tuple[int, list[float]]]) -> list[int] | None:
    class_count = len(public["classes"])
    centroids: list[list[float]] = []
    for class_id in range(class_count):
        points = [feature for current, feature in samples if current == class_id]
        if not points:
            return None
        centroids.append([sum(float(point[channel]) for point in points) / len(points) for channel in range(4)])
    return [min(range(class_count), key=lambda class_id: _feature_distance(feature, centroids[class_id])) for feature in public["plate"]["pixels"]]


def _score(prediction: list[int] | None, truth: dict) -> float:
    if prediction is None:
        return 0.0
    target = truth["target_labels"]
    ious = []
    for label in range(len(truth["class_names"])):
        intersection = sum(a == b == label for a, b in zip(prediction, target))
        union = sum(a == label or b == label for a, b in zip(prediction, target))
        ious.append(intersection / union if union else 0.0)
    return sum(ious) / len(ious)


def _screen_point(page, point: tuple[float, float], public: dict) -> tuple[float, float]:
    page.locator("#teach-stencil-canvas").scroll_into_view_if_needed()
    box = page.locator("#teach-stencil-canvas").bounding_box()
    if not box:
        raise AssertionError("Teach the Stencil canvas has no visible geometry")
    width, height = float(public["plate"]["width"]), float(public["plate"]["height"])
    # The visible canvas has a 26,20 / 848,440 plotting frame in its intrinsic
    # 900x480 coordinate system.
    px = (26.0 + (float(point[0]) + 0.5) * 848.0 / width) / 900.0
    py = (20.0 + (float(point[1]) + 0.5) * 440.0 / height) / 480.0
    return box["x"] + px * box["width"], box["y"] + py * box["height"]


def _drag_endpoint(
    public: dict,
    point: tuple[int, int],
    candidates: list[tuple[int, int]] | None = None,
    used: set[tuple[int, int]] | None = None,
) -> tuple[int, int]:
    width, height = int(public["plate"]["width"]), int(public["plate"]["height"])
    occupied = used or set()
    if candidates:
        nearby = sorted(
            (candidate for candidate in candidates if candidate != point and candidate not in occupied),
            key=lambda candidate: (math.dist(point, candidate), candidate),
        )
        for candidate in nearby:
            if math.dist(point, candidate) >= MIN_FULL_PATH_LENGTH:
                return candidate
    for dx, dy in ((4.2, 0.0), (-4.2, 0.0), (0.0, 4.2), (0.0, -4.2)):
        candidate = (round(point[0] + dx, 2), round(point[1] + dy, 2))
        if 0 <= candidate[0] < width and 0 <= candidate[1] < height:
            return int(math.floor(candidate[0])), int(math.floor(candidate[1]))
    raise AssertionError("full interaction has no in-bounds drag endpoint")


def _set_brush_size(page, size: int = 1) -> None:
    control = page.locator("#teach-stencil-size")
    if control.count() == 0:
        raise AssertionError("Teach the Stencil brush-size control is missing")
    control.focus()
    control.press("Home")
    for _ in range(max(0, int(size) - 1)):
        control.press("ArrowRight")


def _mark(
    page,
    public: dict,
    point: tuple[int, int],
    interaction: str,
    endpoint: tuple[int, int] | None = None,
) -> None:
    x, y = _screen_point(page, point, public)
    if interaction == "full":
        endpoint = endpoint or _drag_endpoint(public, point)
        end_x, end_y = _screen_point(page, endpoint, public)
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(end_x, end_y)
        page.mouse.up()
    else:
        page.mouse.click(x, y)


def _choose(page, class_id: int) -> None:
    page.locator(f'[data-stencil-class="{class_id}"]').click()


def _event_samples(
    public: dict,
    class_id: int,
    point: tuple[int, int],
    interaction: str,
    endpoint: tuple[int, int] | None = None,
) -> list[tuple[int, list[float]]]:
    width = int(public["plate"]["width"])
    points = [point]
    if interaction == "full":
        points.append(endpoint or _drag_endpoint(public, point))
    return [(class_id, public["plate"]["pixels"][item[1] * width + item[0]]) for item in points]


def _candidate_correction(
    public: dict,
    samples: list[tuple[int, list[float]]],
    by_class: dict[int, list[tuple[int, int]]],
    used: set[tuple[int, int]],
    current: list[int] | None,
    interaction: str = "simplified",
    consequential: bool = False,
    target: list[int] | None = None,
) -> tuple[int, tuple[int, int], list[int]]:
    # For consequential levels, only consider currently misclassified pixels
    # and require the proposed visible example to make that pixel correct.
    # Truth is used only by this deterministic construction solver; the browser
    # and grader receive ordinary visible coordinates and public features.
    candidate_points: list[tuple[int, tuple[int, int]]] = []
    for class_id in sorted(by_class, key=lambda item: len(by_class[item]), reverse=True):
        points = by_class[class_id]
        if consequential and current is not None:
            width = int(public["plate"]["width"])
            points = [point for point in points if current[point[1] * width + point[0]] != class_id]
        if not points:
            continue
        positions = {round(i * (len(points) - 1) / 23) for i in range(24)}
        candidate_points.extend((class_id, points[position]) for position in sorted(positions))
    best = None
    best_score = -1.0
    for class_id, point in candidate_points:
        if point in used:
            continue
        if consequential and current is not None:
            width = int(public["plate"]["width"])
            if current[point[1] * width + point[0]] == class_id:
                continue
        endpoint = _drag_endpoint(public, point, by_class[class_id], used) if interaction == "full" else None
        prediction = _predict(public, samples + _event_samples(public, class_id, point, interaction, endpoint))
        if prediction is not None and (current is None or prediction != current):
            if consequential:
                width = int(public["plate"]["width"])
                if prediction[point[1] * width + point[0]] != class_id:
                    continue
            if consequential and target is not None:
                ious = []
                for label in by_class:
                    intersection = sum(a == b == label for a, b in zip(prediction, target))
                    union = sum(a == label or b == label for a, b in zip(prediction, target))
                    ious.append(intersection / union if union else 0.0)
                score = sum(ious) / len(ious)
                if score > best_score:
                    best_score = score
                    best = (class_id, point, prediction)
            else:
                return class_id, point, prediction
    if best is not None:
        return best
    # A fallback candidate keeps the solver useful for the preserved lower
    # level, whose original contract requires distinct evidence but not a
    # prediction repair. Consequential levels fail loudly if no visible error
    # can be repaired under the generated plate.
    if consequential:
        raise AssertionError("no consequential correction pixel available")
    for class_id, points in by_class.items():
        for point in points:
            if point not in used:
                endpoint = _drag_endpoint(public, point, points, used) if interaction == "full" else None
                return class_id, point, _predict(public, samples + _event_samples(public, class_id, point, interaction, endpoint)) or []
    raise AssertionError("no unused correction pixel available")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    del out_dir
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator("#teach-stencil-fresh").click()
    page.wait_for_function("() => document.querySelector('.readout')?.textContent === 'FAIL'", timeout=8_000)
    deadline = time.time() + 8
    while time.time() < deadline:
        if str(_read(state_dir / "ground_truth.json")["challenge_id"]) != before:
            return
        time.sleep(0.05)
    raise AssertionError("Teach the Stencil failure did not issue a fresh challenge")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    from playwright.sync_api import expect
    del out_dir
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    public = _read(state_dir / "public_state.json")
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "simplified")
    _set_brush_size(page, 1)
    by_class = _point_lists(public, truth)
    used: set[tuple[int, int]] = set()
    samples: list[tuple[int, list[float]]] = []
    required = int(truth.get("required_samples_per_class") or 1)
    width = int(public["plate"]["width"])

    for class_id in range(len(public["classes"])):
        _choose(page, class_id)
        points = by_class[class_id]
        if not points:
            raise AssertionError(f"class {class_id} has no target pixels")
        mean = [sum(float(public["plate"]["pixels"][point[1] * width + point[0]][channel]) for point in points) / len(points) for channel in range(4)]
        def feature_distance(point: tuple[int, int]) -> float:
            feature = public["plate"]["pixels"][point[1] * width + point[0]]
            return sum((float(feature[channel]) / 255.0 - float(mean[channel]) / 255.0) ** 2 for channel in range(3)) + 0.65 * (float(feature[3]) - float(mean[3])) ** 2
        representative_points = sorted(
            points,
            key=feature_distance,
        )[:required]
        for point in representative_points:
            endpoint = _drag_endpoint(public, point, points, used) if interaction == "full" else None
            _mark(page, public, point, interaction, endpoint)
            used.add(point)
            if endpoint is not None:
                used.add(endpoint)
            samples.extend(_event_samples(public, class_id, point, interaction, endpoint))
    page.locator("#teach-stencil-update").click()
    current = _predict(public, samples)

    for _ in range(20):
        if _score(current, truth) >= float(truth["threshold"]):
            break
        class_id, point, prediction = _candidate_correction(
            public, samples, by_class, used, current, interaction, True, truth.get("target_labels")
        )
        endpoint = _drag_endpoint(public, point, by_class[class_id], used) if interaction == "full" else None
        _choose(page, class_id)
        _mark(page, public, point, interaction, endpoint)
        used.add(point)
        if endpoint is not None:
            used.add(endpoint)
        samples.extend(_event_samples(public, class_id, point, interaction, endpoint))
        page.locator("#teach-stencil-update").click()
        current = prediction
    page.locator("#teach-stencil-certify").click()
    expect(page.locator(".readout")).to_contain_text("PASS", timeout=12_000)
