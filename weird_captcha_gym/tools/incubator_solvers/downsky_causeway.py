from __future__ import annotations

import json
import math
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "downsky_causeway"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=False)


def _model(page) -> dict:
    return page.evaluate(
        """() => {
          const m = window.downskyCausewayModel;
          return {x: m.x, y: m.y, z: m.z, heading: m.heading, pitch: m.pitch,
                  platformId: m.platformId, falling: m.falling, completed: m.completed};
        }"""
    )


def _normalize(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def _target_heading(page, target: tuple[float, float]) -> float:
    state = _model(page)
    return math.atan2(float(target[1]) - float(state["y"]), float(target[0]) - float(state["x"]))


def _look_full(page, delta_pixels: float) -> None:
    canvas = page.locator("#downsky-canvas")
    box = canvas.bounding_box()
    if not box:
        raise AssertionError("Downsky first-person canvas is not visible")
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    delta = max(-240.0, min(240.0, delta_pixels))
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + delta, cy, steps=max(2, round(abs(delta) / 25)))
    page.mouse.up()


def _look_simplified(page, direction: str) -> None:
    page.locator(f'[data-look="{direction}"]').click()


def _turn_to(page, target: tuple[float, float]) -> None:
    sensitivity = float(page.evaluate("() => window.downskyCausewayModel.state.world.rules.look_sensitivity"))
    for _ in range(24):
        state = _model(page)
        difference = _normalize(math.atan2(float(target[1]) - float(state["y"]), float(target[0]) - float(state["x"])) - float(state["heading"]))
        if abs(difference) <= 0.08:
            return
        if str(page.locator(".downsky-causeway").get_attribute("data-interaction")) == "full":
            _look_full(page, difference / sensitivity)
        else:
            _look_simplified(page, "right" if difference > 0 else "left")
        page.wait_for_timeout(18)
    difference = abs(_normalize(_target_heading(page, target) - float(_model(page)["heading"])))
    if difference > 0.24:
        raise AssertionError(f"oracle could not align the causeway view: {difference:.3f} radians")


def _hold_move(page, duration_ms: int) -> None:
    interaction = str(page.locator(".downsky-causeway").get_attribute("data-interaction") or "full")
    if interaction == "full":
        page.keyboard.down("w")
        try:
            page.wait_for_timeout(duration_ms)
        finally:
            page.keyboard.up("w")
        return
    button = page.locator('[data-hold="forward"]')
    box = button.bounding_box()
    if not box:
        raise AssertionError("simplified forward control is not visible")
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    try:
        page.wait_for_timeout(duration_ms)
    finally:
        page.mouse.up()


def _move_to(page, platform: dict) -> None:
    target = (float(platform["center"][0]), float(platform["center"][1]))
    target_id = str(platform["id"])
    for _ in range(90):
        state = _model(page)
        if state["completed"]:
            return
        if state["falling"]:
            raise AssertionError("oracle fell before reaching the intended terrace")
        if str(state["platformId"]) == target_id:
            break
        _turn_to(page, target)
        _hold_move(page, 150)
        page.wait_for_timeout(28)
    else:
        raise AssertionError(f"oracle did not reach terrace {target_id}: {_model(page)}")

    for _ in range(30):
        state = _model(page)
        if state["completed"]:
            return
        if state["falling"]:
            raise AssertionError("oracle fell while centering on the intended terrace")
        remaining = math.hypot(target[0] - float(state["x"]), target[1] - float(state["y"]))
        if remaining <= 0.26:
            return
        _turn_to(page, target)
        _hold_move(page, min(115, max(55, round(remaining / 4.6 * 1000 / 3))))
        page.wait_for_timeout(24)
    raise AssertionError(f"oracle could not center on terrace {target_id}: {_model(page)}")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    expect(page.locator(".downsky-causeway")).to_be_visible(timeout=7_000)
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    _shot(page, out_dir, "failure-before-abandon")
    page.locator("#downsky-abandon").click()
    deadline = time.time() + 8
    while time.time() < deadline:
        current = _read(state_dir / "ground_truth.json")
        if str(current.get("challenge_id")) != before:
            break
        time.sleep(.05)
    else:
        raise AssertionError("abandoning the causeway did not issue a new challenge")
    expect(page.locator(".downsky-causeway")).to_be_visible(timeout=7_000)
    expect(page.locator(".downsky-causeway")).to_have_class(__import__("re").compile(r".*is-failed.*"))
    expect(page.locator(".downsky-verdict b")).to_have_text("FAIL")
    _shot(page, out_dir, "failure-recovery-new-causeway")
    if page.locator(".downsky-causeway").get_attribute("data-interaction") == "full":
        page.locator("#downsky-canvas").click()
    else:
        _look_simplified(page, "right")
    expect(page.locator(".downsky-foot .readout")).to_have_text("REACH THE PAVILION")
    _shot(page, out_dir, "fresh-ready")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    expect(page.locator(".downsky-causeway")).to_be_visible(timeout=7_000)
    truth = _read(state_dir / "ground_truth.json")
    route_ids = [str(item) for item in truth.get("route_platform_ids") or []]
    world = truth.get("world") or {}
    platforms = {str(item["id"]): item for item in world.get("platforms") or []}
    if len(route_ids) < 3 or any(item not in platforms for item in route_ids):
        raise AssertionError("hidden causeway route violates the solver contract")
    _shot(page, out_dir, "initial-first-person-view")
    for index, platform_id in enumerate(route_ids[1:], start=1):
        _move_to(page, platforms[platform_id])
        if index in {1, len(route_ids) // 2, len(route_ids) - 1}:
            _shot(page, out_dir, f"terrace-{index:02d}")
    expect(page.locator(".downsky-foot .readout")).to_have_text("PASS · PAVILION REACHED", timeout=10_000)
    _shot(page, out_dir, "authoritative-pass")
