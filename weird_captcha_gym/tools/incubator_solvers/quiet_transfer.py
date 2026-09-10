from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "quiet_transfer"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=True)


def _wait_for_new_challenge(state_dir: Path, previous: str) -> str:
    deadline = time.time() + 10
    while time.time() < deadline:
        current = str(_read_json(state_dir / "ground_truth.json").get("challenge_id") or "")
        if current and current != previous:
            return current
        time.sleep(0.05)
    raise AssertionError("quiet transfer did not regenerate after terminal failure")


def _set_simplified_knot(page, index: int, target: float, step: float, *, strict: bool = True) -> None:
    current = float(page.evaluate("index => window.quietTransferModel.curve[index]", index))
    target = round(float(target), 4)
    if abs(current - target) < 0.001:
        return
    direction = 1 if target > current else -1
    selector = f'button[data-knot="{index}"][data-delta="{"" if direction > 0 else "-"}{step:g}"]'
    button = page.locator(selector)
    if button.count() != 1:
        raise AssertionError(f"missing quiet-transfer nudge button {selector}")
    count = 120
    for _ in range(count):
        button.click()
        page.wait_for_timeout(8)
        next_value = float(page.evaluate("index => window.quietTransferModel.curve[index]", index))
        if abs(next_value - target) < 0.001 or abs(next_value - current) < 0.0005:
            break
        current = next_value
    final = float(page.evaluate("index => window.quietTransferModel.curve[index]", index))
    if strict and abs(final - target) > 0.001:
        raise AssertionError(f"nudge surface stopped at {final}, target was {target}")


def _drag_knot(page, index: int, value: float, *, steps: int = 8) -> None:
    state = page.evaluate("() => ({curve: window.quietTransferModel.curve.slice(), count: window.quietTransferModel.curve.length})")
    current = float(state["curve"][index])
    count = int(state["count"])
    svg = page.locator("#qt-curve")
    box = svg.bounding_box()
    if box is None:
        raise AssertionError("quiet-transfer curve has no bounding box")

    def point(curve_value: float) -> tuple[float, float]:
        x = 40 + (index / max(1, count - 1)) * 820
        y = 220 - float(curve_value) * 180
        return box["x"] + x / 900 * box["width"], box["y"] + y / 250 * box["height"]

    start_x, start_y = point(current)
    end_x, end_y = point(value)
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    for step_index in range(1, max(1, steps) + 1):
        fraction = step_index / max(1, steps)
        intermediate = current + (float(value) - current) * fraction
        x, y = point(intermediate)
        page.mouse.move(x, y)
    page.mouse.up()
    final = float(page.evaluate("index => window.quietTransferModel.curve[index]", index))
    if abs(final - float(value)) > 0.004:
        raise AssertionError(f"dragged knot stopped at {final}, target was {value}")


def _edit_curve(page, truth: dict, *, target: list[float], wrong: bool = False) -> None:
    interaction = str((truth.get("control_condition") or {}).get("interaction") or truth.get("interaction_mode") or "full")
    curve = truth["curve"]
    if interaction == "simplified":
        for index in range(1, len(target) - 1):
            _set_simplified_knot(
                page,
                index,
                target[index],
                float(curve["nudge_step"]),
                strict=not wrong,
            )
    else:
        for index in range(1, len(target) - 1):
            _drag_knot(page, index, target[index], steps=10 if wrong else 8)


def _trial_curve(truth: dict) -> list[float]:
    """Make a visible first guess that is guaranteed to be revisable."""
    curve = truth["curve"]
    trial = [float(value) for value in curve["initial"]]
    target = [float(value) for value in truth["target_curve"]]
    step = float(curve["nudge_step"])
    minimum = float(curve["minimum"])
    maximum = float(curve["maximum"])
    index = max(1, (len(trial) - 1) // 2)
    proposed = min(maximum, trial[index] + 2.0 * step)
    if abs(proposed - trial[index]) < 0.001:
        proposed = max(minimum, trial[index] - 2.0 * step)
    trial[index] = round(proposed, 4)
    if all(abs(a - b) <= 0.001 for a, b in zip(trial, target)):
        proposed = min(maximum, trial[index] + 2.0 * step)
        if abs(proposed - trial[index]) < 0.001:
            proposed = max(minimum, trial[index] - 2.0 * step)
        trial[index] = round(proposed, 4)
    return trial


def _run_and_wait(page) -> None:
    paused_mode = bool(
        page.evaluate(
            "() => Boolean(window.WeirdCaptchaTime?.status && WeirdCaptchaTime.status().mode === 'paused')"
        )
    )
    page.locator("#qt-run").click()
    if paused_mode:
        page.evaluate("() => window.WeirdCaptchaTime.resume()")
    ticks = int(page.evaluate("() => window.quietTransferModel.state.curve.playback_ticks"))
    tick_ms = int(page.evaluate("() => window.quietTransferModel.state.curve.tick_ms"))
    page.wait_for_function(
        "() => window.quietTransferModel && !window.quietTransferModel.running && window.quietTransferModel.lastState !== null",
        timeout=max(12_000, ticks * tick_ms + 8_000),
    )
    if paused_mode:
        page.evaluate("() => window.WeirdCaptchaTime.pause()")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read_json(state_dir / "ground_truth.json")
    before = str(truth["challenge_id"])
    count = len(truth["curve"]["initial"])
    wrong = [0.95 if index % 2 else 0.05 for index in range(count)]
    wrong[0] = float(truth["curve"]["initial"][0])
    wrong[-1] = float(truth["curve"]["initial"][-1])
    _edit_curve(page, truth, target=wrong, wrong=True)
    _screenshot(page, out_dir, "failure-curve")
    _run_and_wait(page)
    _screenshot(page, out_dir, "failure-playback")
    revised_wrong = wrong[:]
    for index in range(1, count - 1):
        revised_wrong[index] = 0.78 if revised_wrong[index] >= 0.90 else 0.22
    _edit_curve(page, truth, target=revised_wrong, wrong=True)
    _screenshot(page, out_dir, "failure-revised-curve")
    _run_and_wait(page)
    _screenshot(page, out_dir, "failure-revision-playback")
    page.locator("#qt-certify").click()
    _wait_for_new_challenge(state_dir, before)
    expect(page.locator('.quiet-transfer-shell[data-fresh-failure="true"]')).to_be_visible(timeout=10_000)
    expect(page.locator(".readout")).to_contain_text("FAIL", timeout=10_000)
    _screenshot(page, out_dir, "failure-fresh-task")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read_json(state_dir / "ground_truth.json")
    target = [float(value) for value in truth["target_curve"]]
    trial = _trial_curve(truth)
    _screenshot(page, out_dir, "initial")
    _edit_curve(page, truth, target=trial)
    _screenshot(page, out_dir, "trial-curve")
    _run_and_wait(page)
    _screenshot(page, out_dir, "trial-playback")
    _edit_curve(page, truth, target=target)
    _screenshot(page, out_dir, "revised-curve")
    _run_and_wait(page)
    fidelity = page.evaluate("() => window.quietTransferModel.lastState.fidelity")
    _screenshot(page, out_dir, "playback-complete")
    threshold = float(truth["requirements"]["fidelity_threshold"])
    if float(fidelity) + 1e-7 < threshold:
        raise AssertionError(f"visible target curve did not reach threshold: {fidelity} < {threshold}")
    page.locator("#qt-certify").click()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=10_000)
    expect(page.locator('.quiet-transfer-shell[data-phase="passed"]')).to_be_visible(timeout=10_000)
    _screenshot(page, out_dir, "solved")
