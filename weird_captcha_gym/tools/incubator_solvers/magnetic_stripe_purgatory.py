from __future__ import annotations

import json
import math
import time
from pathlib import Path


MECHANIC_ID = "magnetic_stripe_purgatory"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, mechanic: str, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{label}.png"), full_page=True)


def _wait_new_challenge(state_dir: Path, previous: str) -> str:
    deadline = time.time() + 8
    while time.time() < deadline:
        current = str(_read(state_dir / "ground_truth.json").get("challenge_id") or "")
        if current and current != previous:
            return current
        time.sleep(0.05)
    raise AssertionError("calibration desk did not regenerate after incomplete audit")


def _stage_box(page) -> dict:
    box = page.locator("#stripe-stage").bounding_box()
    if box is None:
        raise AssertionError("calibration desk has no visible stage")
    return box


def _screen_point(page, point: list[float], box: dict | None = None, stage: dict | None = None) -> tuple[float, float]:
    box = box or _stage_box(page)
    stage = stage or page.evaluate("() => magneticStripePurgatoryModel.state.stage")
    return box["x"] + point[0] / stage["width"] * box["width"], box["y"] + point[1] / stage["height"] * box["height"]


def _center(rect: dict) -> list[float]:
    return [float(rect["x"]) + float(rect["width"]) / 2, float(rect["y"]) + float(rect["height"]) / 2]


def _interaction(page) -> str:
    return str(page.locator(".stripe-purgatory").get_attribute("data-interaction") or "full")


def _insert(page, card: dict, reader: dict, *, total_ms: int = 160) -> None:
    if _interaction(page) == "simplified":
        page.locator(f'.mag-card-select[data-card-id="{card["id"]}"]').click()
        page.locator(f'.stripe-insert-proxy[data-reader-id="{reader["id"]}"]').click()
        return
    start = _center(card["initial_rect"])
    end = _center(reader["slot"])
    box = _stage_box(page)
    stage = page.evaluate("() => magneticStripePurgatoryModel.state.stage")
    page.mouse.move(*_screen_point(page, start, box, stage))
    page.mouse.down()
    steps = 7
    for index in range(1, steps + 1):
        point = [start[0] + (end[0] - start[0]) * index / steps, start[1] + (end[1] - start[1]) * index / steps]
        page.mouse.move(*_screen_point(page, point, box, stage), steps=1)
        page.wait_for_timeout(max(8, total_ms // steps))
    page.mouse.up()


def _blocking_fields(reader: dict) -> list[dict]:
    center_y = float(reader["track"]["y"])
    direction = 1 if reader["track"]["direction"] == "ltr" else -1
    return sorted(
        (
            zone for zone in reader["interference_zones"]
            if float(zone["y"]) <= center_y <= float(zone["y"]) + float(zone["height"])
        ),
        key=lambda zone: direction * float(zone["x"]),
    )


def _clearance_y(reader: dict, zone: dict) -> float:
    track = reader["track"]
    tolerance = float(reader["calibration"]["straightness_px"])
    offset = min(16.0, tolerance - 4.0)
    passes_below = float(zone["y"]) < float(track["y"]) - tolerance / 2
    return float(track["y"]) + (offset if passes_below else -offset)


def _dense_polyline(waypoints: list[list[float]], minimum_samples: int, maximum_gap_px: int) -> list[list[float]]:
    lengths = [math.hypot(second[0] - first[0], second[1] - first[1]) for first, second in zip(waypoints, waypoints[1:])]
    total = sum(lengths)
    samples = max(minimum_samples, math.ceil(total / max(12.0, maximum_gap_px * 0.6)))
    points = [waypoints[0]]
    for index in range(1, samples + 1):
        remaining = total * index / samples
        for segment, length in enumerate(lengths):
            if remaining <= length or segment == len(lengths) - 1:
                first, second = waypoints[segment], waypoints[segment + 1]
                amount = remaining / length if length else 1.0
                points.append([first[0] + (second[0] - first[0]) * amount, first[1] + (second[1] - first[1]) * amount])
                break
            remaining -= length
    return points


def _clearance_points(reader: dict) -> list[list[float]]:
    track = reader["track"]
    direction = 1 if track["direction"] == "ltr" else -1
    start_x = float(track["x_start"] if direction > 0 else track["x_end"])
    end_x = float(track["x_end"] if direction > 0 else track["x_start"])
    center_y = float(track["y"])
    waypoints = [[start_x, center_y]]
    for zone in _blocking_fields(reader):
        approach_x = float(zone["x"]) - 12 if direction > 0 else float(zone["x"]) + float(zone["width"]) + 12
        exit_x = float(zone["x"]) + float(zone["width"]) + 12 if direction > 0 else float(zone["x"]) - 12
        clearance_y = _clearance_y(reader, zone)
        waypoints.extend([[approach_x, clearance_y], [exit_x, clearance_y]])
    waypoints.append([end_x, center_y])
    calibration = reader["calibration"]
    return _dense_polyline(waypoints, int(calibration["minimum_samples"]), int(calibration["maximum_sample_gap_px"]))


def _swipe(page, reader: dict, duration_ms: int, *, curve_px: float = 0.0, center_path: bool = False) -> None:
    reader_id = str(reader["id"])
    if _interaction(page) == "simplified":
        if curve_px or center_path:
            raise AssertionError("the simplified swipe proxy supplies its generated clearance route")
        page.locator(f'.stripe-proxy-duration[data-reader-id="{reader_id}"]').fill(str(duration_ms))
        page.locator(f'.stripe-proxy-execute[data-reader-id="{reader_id}"]').click()
        return
    handle = page.locator(f'.stripe-handle[data-reader-id="{reader_id}"]')
    box = handle.bounding_box()
    if box is None:
        raise AssertionError(f"reader {reader_id} has no swipe handle")
    track = reader["track"]
    x0 = float(track["x_start"] if track["direction"] == "ltr" else track["x_end"])
    x1 = float(track["x_end"] if track["direction"] == "ltr" else track["x_start"])
    center_y = float(track["y"])
    stage_box = _stage_box(page)
    stage = page.evaluate("() => magneticStripePurgatoryModel.state.stage")
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    if center_path or curve_px:
        steps = int(reader["calibration"]["minimum_samples"])
        points = []
        for index in range(1, steps + 1):
            amount = index / steps
            y = center_y + curve_px * (1 - abs(2 * amount - 1))
            points.append([x0 + (x1 - x0) * amount, y])
    else:
        points = _clearance_points(reader)[1:]
    for index, point in enumerate(points, start=1):
        amount = index / len(points)
        desired_elapsed = duration_ms * amount
        actual_elapsed = float(page.evaluate("() => performance.now() - magneticStripePurgatoryModel.swipe.startedAt"))
        if actual_elapsed < desired_elapsed:
            page.wait_for_timeout(round(desired_elapsed - actual_elapsed))
        page.mouse.move(*_screen_point(page, point, stage_box, stage), steps=1)
    page.mouse.up()


def _reader_for_card(truth: dict, card: dict) -> dict:
    return next(reader for reader in truth["readers"] if reader["id"] == card["assigned_reader"])


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    state_dir = Path(state_dir)
    truth = _read(state_dir / "ground_truth.json")
    before = str(truth["challenge_id"])
    card = truth["cards"][0]
    assigned = _reader_for_card(truth, card)
    wrong = next((reader for reader in truth["readers"] if reader["id"] != assigned["id"]), None)

    if wrong is not None:
        _insert(page, card, wrong)
        page.wait_for_function("() => magneticStripePurgatoryModel.invalidInsertions === 1")
        _screenshot(page, out_dir, mechanic, "invalid-insertion-feedback")
    _insert(page, card, assigned)
    page.wait_for_function("readerId => magneticStripePurgatoryModel.readerCards[readerId] !== null", arg=assigned["id"])
    if _interaction(page) == "simplified":
        _swipe(page, assigned, 300)
        page.wait_for_function("readerId => magneticStripePurgatoryModel.readerFeedback[readerId] === 'TOO FAST'", arg=assigned["id"])
        _screenshot(page, out_dir, mechanic, "proxy-too-fast")
    else:
        if _blocking_fields(assigned):
            _swipe(page, assigned, int(assigned["calibration"]["solver_ms"]), center_path=True)
            page.wait_for_function("readerId => magneticStripePurgatoryModel.readerFeedback[readerId] === 'STATIC FIELD'", arg=assigned["id"])
            _screenshot(page, out_dir, mechanic, "static-field-bad-read")
        else:
            _swipe(page, assigned, int(assigned["calibration"]["solver_ms"]), curve_px=56)
            page.wait_for_function("readerId => magneticStripePurgatoryModel.readerFeedback[readerId] === 'BAD READ'", arg=assigned["id"])
            _screenshot(page, out_dir, mechanic, "curved-bad-read")
    page.locator("#stripe-audit").click()
    _wait_new_challenge(state_dir, before)
    page.wait_for_function("() => document.querySelector('.readout')?.textContent.includes('FAIL')", timeout=8_000)
    _screenshot(page, out_dir, mechanic, "fail-fresh-desk")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(Path(state_dir) / "ground_truth.json")
    challenge = page.locator(".stripe-purgatory").get_attribute("data-challenge-id")
    if challenge != truth.get("challenge_id"):
        raise AssertionError(f"UI challenge {challenge!r} differs from hidden challenge {truth.get('challenge_id')!r}")
    page.wait_for_function("() => !document.querySelector('.stripe-verdict-fresh')", timeout=4_000)

    page.locator("#stripe-reset").click()
    page.wait_for_function("() => magneticStripePurgatoryModel.resetCount === 1 && Object.values(magneticStripePurgatoryModel.cardLocations).every(value => value === null)")
    _screenshot(page, out_dir, mechanic, "reset-edge")

    for index, card in enumerate(truth["cards"]):
        reader = _reader_for_card(truth, card)
        _insert(page, card, reader)
        page.wait_for_function("readerId => magneticStripePurgatoryModel.readerCards[readerId] !== null", arg=reader["id"])
        if index == 0:
            _swipe(page, reader, 300 if _interaction(page) == "simplified" else 120)
            page.wait_for_function("readerId => magneticStripePurgatoryModel.readerFeedback[readerId] === 'TOO FAST'", arg=reader["id"])
            _screenshot(page, out_dir, mechanic, "too-fast-calibration")
        _swipe(page, reader, int(reader["calibration"]["solver_ms"]), curve_px=0)
        page.wait_for_function("readerId => magneticStripePurgatoryModel.readerLocked[readerId] === true", arg=reader["id"], timeout=5_000)
        if index == 1:
            _screenshot(page, out_dir, mechanic, "two-readers-locked")

    state = page.evaluate("""() => ({
      locked:Object.values(magneticStripePurgatoryModel.readerLocked).filter(Boolean).length,
      attempts:magneticStripePurgatoryModel.swipeAttempts,
      reset:magneticStripePurgatoryModel.resetCount,
    })""")
    expected_readers = len(truth["readers"])
    if state["locked"] != expected_readers or state["attempts"] != expected_readers + 1 or state["reset"] != 1:
        raise AssertionError(f"unexpected physical calibration state: {state}")
    _screenshot(page, out_dir, mechanic, "all-readers-locked")
    page.locator("#stripe-audit").click()
    page.wait_for_function("() => document.querySelector('.readout')?.textContent === 'PASS'", timeout=8_000)
