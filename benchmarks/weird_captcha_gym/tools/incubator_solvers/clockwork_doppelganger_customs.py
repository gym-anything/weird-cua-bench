from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "clockwork_doppelganger_customs"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, mechanic: str, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{label}.png"), full_page=True)


def _canvas_point(page, point: dict) -> tuple[float, float]:
    box = page.locator("#clockwork-canvas").bounding_box()
    if not box:
        raise AssertionError("clockwork canvas has no interactive geometry")
    return (
        box["x"] + float(point["x"]) / 860.0 * box["width"],
        box["y"] + float(point["y"]) / 420.0 * box["height"],
    )


def _move_path(page, points: list[dict], duration_ms: int) -> None:
    segments = max(1, len(points) - 1)
    per_segment = duration_ms // segments
    for first, second in zip(points, points[1:]):
        start = _canvas_point(page, first)
        end = _canvas_point(page, second)
        page.mouse.move(*start)
        steps = 7
        for step in range(1, steps + 1):
            amount = step / steps
            page.mouse.move(start[0] + (end[0] - start[0]) * amount, start[1] + (end[1] - start[1]) * amount)
            page.wait_for_timeout(max(45, per_segment // steps))


def _record_role(page, truth: dict, slot: int, out_dir: Path, mechanic: str) -> None:
    del out_dir, mechanic
    role = truth["roles"][slot]
    guide = role["guide"]
    required = role["required_actions"]
    interaction = (truth.get("control_condition") or {}).get("interaction", "legacy")
    start = guide[0]
    page.mouse.move(*_canvas_point(page, start))
    page.locator(f'[data-record="{slot}"]').click()
    page.mouse.move(*_canvas_point(page, start))
    page.wait_for_timeout(300)
    for index, (action, target) in enumerate(zip(required, guide)):
        if index:
            _move_path(page, [guide[index - 1], target], 430)
            page.wait_for_timeout(50)
        if interaction == "full":
            page.mouse.click(*_canvas_point(page, target))
        else:
            page.keyboard.press({"grab": "g", "stamp": "t", "release": "r"}[action])
        page.wait_for_timeout(60)
    expect(page.locator(f'[data-loop-card="{slot}"]')).to_have_attribute("data-ready", "true", timeout=4_500)
    card = page.locator(f'[data-loop-card="{slot}"]')
    for action in required:
        if not card.get_attribute(f"data-{action}-ms"):
            raise AssertionError(f"accepted loop {slot} is missing its recorded {action} action")


def _action_time(page, slot: int, action: str) -> int:
    value = page.locator(f'[data-loop-card="{slot}"]').get_attribute(f"data-{action}-ms")
    if value is None or value == "":
        raise AssertionError(f"loop {slot} has no recorded {action} time")
    return int(value)


def _set_phase(page, slot: int, target: int, step: int) -> None:
    slider = page.locator(f"#ghost-phase-{slot}")
    slider.focus()
    page.keyboard.press("Home")
    for _ in range(target // step):
        page.keyboard.press("ArrowRight")
    expect(slider).to_have_value(str(target))


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    before = str(truth["challenge_id"])
    expect(page.locator(".clockwork-customs")).to_have_attribute("data-active", "true")
    # Screenshot latency is confined to this intentionally rejected take.  No
    # screenshot perturbs any recording used by the passing master cycle.
    start = truth["stations"]["pickup"]
    page.mouse.move(*_canvas_point(page, start))
    page.locator('[data-record="0"]').click()
    page.mouse.move(*_canvas_point(page, start))
    page.wait_for_timeout(260)
    if (truth.get("control_condition") or {}).get("interaction") == "full":
        page.mouse.click(*_canvas_point(page, start))
    else:
        page.keyboard.press("g")
    _shot(page, out_dir, mechanic, "active-rejected-take-negative-run")
    expect(page.locator(".clockwork-foot .readout")).to_contain_text("TAKE 1 REJECTED", timeout=4_500)
    page.locator("#clockwork-submit").click()
    expect(page.locator(".clockwork-customs[data-fresh-failure='true']")).to_be_visible(timeout=7_000)
    expect(page.locator(".clockwork-foot .readout")).to_have_text("FAIL", timeout=7_000)
    deadline = time.time() + 7
    while time.time() < deadline:
        if str(_read(state_dir / "ground_truth.json")["challenge_id"]) != before:
            break
        time.sleep(.05)
    else:
        raise AssertionError("failed customs filing did not issue a fresh challenge")
    _shot(page, out_dir, mechanic, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    expect(page.locator(".clockwork-customs")).to_have_attribute("data-active", "true", timeout=6_000)
    truth = _read(state_dir / "ground_truth.json")
    controls = truth["controls"]
    _shot(page, out_dir, mechanic, "initial-fresh-desk")

    for slot in range(len(truth["roles"])):
        _record_role(page, truth, slot, out_dir, mechanic)
    _shot(page, out_dir, mechanic, "recorded-ghosts")

    step = int(controls["phase_step_ms"])
    catch_time = int(truth["conveyor"]["catch_time_ms"])
    gap = int(truth["solution"]["handoff_gap_ms"])
    phases: list[int] = []
    for slot in range(len(truth["roles"])):
        grab = _action_time(page, slot, "grab")
        target = catch_time if slot == 0 else phases[slot - 1] + _action_time(page, slot - 1, "release") + gap
        phases.append(round((target - grab) / step) * step)
    for slot, phase in enumerate(phases):
        if phase < 0 or phase >= int(controls["loop_duration_ms"]):
            raise AssertionError(f"computed ghost phase is outside master loop: {phase}")
        _set_phase(page, slot, phase, step)
    _shot(page, out_dir, mechanic, "timeline-phased")

    page.locator("#clockwork-run").click()
    page.wait_for_timeout(1_450)
    _shot(page, out_dir, mechanic, "concurrent-ghost-playback")
    expect(page.locator(".clockwork-customs")).to_have_attribute("data-success", "true", timeout=int(controls["loop_duration_ms"]) + 2_500)
    _shot(page, out_dir, mechanic, "synchronized-delivery")
    page.locator("#clockwork-submit").click()
    expect(page.locator(".clockwork-foot .readout")).to_have_text("PASS", timeout=10_000)
