from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "rising_causeway"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=True)


def _model(page) -> dict:
    return page.evaluate(
        """() => {
          const m = window.risingCausewayModel;
          return {x: m.x, y: m.y, z: m.z, inFlight: m.inFlight, landed: m.landed,
                  redStage: m.redStage, stairEnd: m.stairEnd, primed: m.primed,
                  completed: m.completed, failed: m.failed};
        }"""
    )


def _point(page, world_point: list[float]) -> tuple[float, float]:
    result = page.evaluate("point => window.risingCausewayModel.projectPoint(point)", world_point)
    if not result:
        raise AssertionError(f"world point is not visible: {world_point}")
    box = page.locator("#rising-causeway-canvas").bounding_box()
    if not box:
        raise AssertionError("Rising Causeway canvas is not visible")
    canvas_size = page.locator("#rising-causeway-canvas").evaluate("c => ({width: c.width, height: c.height})")
    return (
        box["x"] + float(result["x"]) * float(box["width"]) / float(canvas_size["width"]),
        box["y"] + float(result["y"]) * float(box["height"]) / float(canvas_size["height"]),
    )


def _click_world(page, world_point: list[float]) -> None:
    x, y = _point(page, world_point)
    page.mouse.click(x, y)
    page.wait_for_timeout(60)


def _hold_forward(page, duration_ms: int) -> None:
    interaction = str(page.locator(".rising-causeway").get_attribute("data-interaction") or "full")
    if interaction == "full":
        page.keyboard.down("w")
        try:
            page.wait_for_timeout(duration_ms)
        finally:
            page.keyboard.up("w")
        return
    button = page.locator('[data-rising-hold="forward"]')
    box = button.bounding_box()
    if not box:
        raise AssertionError("simplified forward proxy is not visible")
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    try:
        page.wait_for_timeout(duration_ms)
    finally:
        page.mouse.up()


def _hold_back(page, duration_ms: int) -> None:
    interaction = str(page.locator(".rising-causeway").get_attribute("data-interaction") or "full")
    if interaction == "full":
        page.keyboard.down("s")
        try:
            page.wait_for_timeout(duration_ms)
        finally:
            page.keyboard.up("s")
        return
    button = page.locator('[data-rising-hold="back"]')
    box = button.bounding_box()
    if not box:
        raise AssertionError("simplified reverse proxy is not visible")
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    try:
        page.wait_for_timeout(duration_ms)
    finally:
        page.mouse.up()


def _hold_strafe(page, direction: str, duration_ms: int) -> None:
    if direction not in {"left", "right"}:
        raise AssertionError(f"unexpected strafe direction {direction!r}")
    interaction = str(page.locator(".rising-causeway").get_attribute("data-interaction") or "full")
    control = "strafe_left" if direction == "left" else "strafe_right"
    if interaction == "full":
        page.keyboard.down("a" if direction == "left" else "d")
        try:
            page.wait_for_timeout(duration_ms)
        finally:
            page.keyboard.up("a" if direction == "left" else "d")
        return
    button = page.locator(f'[data-rising-hold="{control}"]')
    box = button.bounding_box()
    if not box:
        raise AssertionError(f"simplified {control} proxy is not visible")
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    try:
        page.wait_for_timeout(duration_ms)
    finally:
        page.mouse.up()


def _configure(page, truth: dict) -> None:
    world = truth["world"]
    chamber = world["chamber"]
    interaction = str(page.locator(".rising-causeway").get_attribute("data-interaction") or "full")
    red_target = int(truth["required_red_stage"])
    stair_end = str(truth["required_stair_end"])
    launcher_id = str(truth["required_launcher_id"])
    launcher = next(item for item in chamber["launchers"] if str(item["id"]) == launcher_id)
    if interaction == "simplified":
        for _ in range(red_target):
            page.locator('[data-rising-action="red"]').click()
        page.locator(f'[data-rising-action="stair-{stair_end}"]').click()
        page.locator(f'[data-rising-action="launcher:{launcher_id}"]').click()
        return
    for _ in range(red_target):
        _click_world(page, chamber["actuators"][0]["position"])
    yellow = chamber["actuators"][1]["position"]
    offset = -0.76 if stair_end == "left" else 0.76
    _click_world(page, [yellow[0], yellow[1] + offset, yellow[2] + (0.16 if stair_end == "right" else 0)])
    if _model(page)["stairEnd"] != stair_end:
        # Perspective hit regions can overlap at the edge of a projected
        # triple. Re-observe the visible state and click the other endpoint
        # once when the requested endpoint was not the one activated.
        other = "right" if stair_end == "left" else "left"
        other_offset = -0.76 if other == "left" else 0.76
        _click_world(page, [yellow[0], yellow[1] + other_offset, yellow[2] + (0.16 if other == "right" else 0)])
        if _model(page)["stairEnd"] != stair_end:
            raise AssertionError(f"visible stair endpoint did not activate {stair_end}: {_model(page)}")
    _click_world(page, launcher["position"])
    if _model(page)["primed"] != launcher_id:
        # A nearer wall block can occlude a farther one. Walk along the now
        # configured support to inspect the gallery from a closer viewpoint.
        viewing_x = float(chamber["rules"]["stair_end"]) - 0.5
        for _ in range(100):
            if _model(page)["x"] >= viewing_x:
                break
            _hold_forward(page, 40)
        # From the raised stair the floor/wall pads sit below the original
        # camera view. Look down through the same native drag used in play.
        box = page.locator("#rising-causeway-canvas").bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x, y + 60)
        page.mouse.up()
        _click_world(page, launcher["position"])
        page.mouse.move(x, y + 60)
        page.mouse.down()
        page.mouse.move(x, y)
        page.mouse.up()
        if _model(page)["primed"] != launcher_id:
            raise AssertionError(f"visible launcher did not activate {launcher_id}: {_model(page)}")


def _move_to_launcher_contact(page, launcher: dict) -> None:
    target_y = float(launcher["contact"][1])
    # At the default heading, right strafe increases y and left strafe
    # decreases it. Use short ordinary-input pulses and re-observe after each
    # pulse so the contact point is not overshot on narrow galleries.
    for _ in range(40):
        current = _model(page)
        delta_y = target_y - float(current["y"])
        if abs(delta_y) < 0.10:
            return
        _hold_strafe(page, "right" if delta_y > 0 else "left", 24)
    raise AssertionError(f"oracle could not reach launcher contact y={target_y}: {_model(page)}")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    expect(page.locator(".rising-causeway")).to_be_visible(timeout=7_000)
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    _shot(page, out_dir, "failure-before-abandon")
    page.locator("#rising-abandon").click()
    deadline = time.time() + 8
    while time.time() < deadline:
        current = _read(state_dir / "ground_truth.json")
        if str(current.get("challenge_id")) != before:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("abandoning Rising Causeway did not issue a new challenge")
    expect(page.locator(".rising-causeway")).to_be_visible(timeout=7_000)
    _shot(page, out_dir, "failure-recovery-new-chamber")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    expect(page.locator(".rising-causeway")).to_be_visible(timeout=7_000)
    truth = _read(state_dir / "ground_truth.json")
    _shot(page, out_dir, "initial-chamber-view")
    _configure(page, truth)
    _shot(page, out_dir, "configured-actuators")
    launcher = next(item for item in truth["world"]["chamber"]["launchers"] if str(item["id"]) == str(truth["required_launcher_id"]))
    _move_to_launcher_contact(page, launcher)
    for _ in range(140):
        current = _model(page)
        if current["inFlight"] or current["landed"]:
            break
        if current["failed"]:
            raise AssertionError(f"oracle failed before launcher contact: {current}")
        _hold_forward(page, 40)
    deadline = time.time() + 8
    while time.time() < deadline:
        current = _model(page)
        if current["landed"]:
            break
        if current["failed"]:
            raise AssertionError(f"oracle failed before landing: {current}")
        page.wait_for_timeout(90)
    else:
        raise AssertionError(f"oracle did not observe launcher landing: {_model(page)}")
    _shot(page, out_dir, "contact-launch-landed")
    chamber = truth["world"]["chamber"]
    interaction = str(page.locator(".rising-causeway").get_attribute("data-interaction") or "full")
    terminal = chamber["terminal"].get("visual_position", chamber["terminal"]["position"])
    state = _model(page)
    terminal_contact = chamber["terminal"]["position"]
    stop_distance = max(0.45, float(chamber["terminal"]["radius"]) * 0.72)
    visual_terminal = terminal
    for _ in range(96):
        current = _model(page)
        dx = float(terminal_contact[0]) - float(current["x"])
        dy = float(terminal_contact[1]) - float(current["y"])
        dz = float(terminal_contact[2]) - float(current["z"])
        distance = (dx * dx + dy * dy + dz * dz) ** 0.5
        visible = bool(page.evaluate("p => Boolean(window.risingCausewayModel.projectPoint(p))", visual_terminal))
        if distance <= stop_distance and visible:
            break
        if abs(dx) >= abs(dy):
            if dx < 0:
                _hold_back(page, 60)
            else:
                _hold_forward(page, 60)
        elif dy < 0:
            _hold_strafe(page, "left", 60)
        else:
            _hold_strafe(page, "right", 60)
    if interaction == "simplified":
        page.locator('[data-rising-action="terminal"]').click()
    else:
        # Aim at the beacon's current visible projection.  This is still the
        # ordinary viewport click surface; it avoids depending on a fixed
        # canvas coordinate while the live landing frame is settling.
        try:
            _click_world(page, terminal if isinstance(terminal, list) else terminal)
        except AssertionError:
            box = page.locator("#rising-causeway-canvas").bounding_box()
            if not box:
                raise AssertionError("Rising Causeway canvas is not visible at terminal")
            page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.wait_for_timeout(60)
        page.wait_for_timeout(60)
    expect(page.locator(".rising-foot .readout")).to_have_text("PASS · TERMINAL ACTIVATED", timeout=10_000)
    _shot(page, out_dir, "authoritative-pass")
