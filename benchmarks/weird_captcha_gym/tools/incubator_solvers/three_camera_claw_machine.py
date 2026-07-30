from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "three_camera_claw_machine"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, mechanic: str, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True); page.screenshot(path=str(out_dir / f"{mechanic}-{name}.png"), full_page=True)


def _wait_new(state_dir: Path, before: str) -> None:
    deadline = time.time() + 8
    while time.time() < deadline:
        if str(_read(state_dir / "ground_truth.json").get("challenge_id")) != before: return
        time.sleep(.05)
    raise AssertionError("claw challenge did not regenerate")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID: raise AssertionError(mechanic)
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"]); page.locator(".claw-submit").click(); _wait_new(state_dir, before)
    expect(page.locator(".claw-captcha[data-fresh-failure='true']")).to_be_visible(timeout=8_000); expect(page.locator(".readout")).to_contain_text("FAIL"); _shot(page, out_dir, mechanic, "fail-fresh-cage")
    # Disposable collision/recovery attempt. Its transcript is rejected and a
    # genuinely fresh cage is issued before the authoritative clean solve.
    for _ in range(18): _button(page, "x", 1)
    expect(page.locator(".claw-impact[data-visible='true']")).to_be_visible(); _shot(page, out_dir, mechanic, "cage-collision")
    _button(page, "brake"); _button(page, "x", -1); _shot(page, out_dir, mechanic, "inertial-correction")
    _reset(page); expect(page.locator(".claw-tick")).to_have_text("0")
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"]); page.locator(".claw-submit").click(); _wait_new(state_dir, before)
    expect(page.locator(".claw-captcha[data-fresh-failure='true']")).to_be_visible(timeout=8_000)


def _interaction(page) -> str:
    return str(page.locator(".claw-captcha").get_attribute("data-interaction") or "simplified")


def _button(page, axis: str, direction: int = 0):
    if _interaction(page) == "full":
        keys = {
            ("x", -1): "a", ("x", 1): "d", ("y", -1): "s", ("y", 1): "w",
            ("z", -1): "q", ("z", 1): "e", ("coast", 0): "c", ("brake", 0): "Space",
        }
        page.keyboard.press(keys[(axis, direction)])
        return
    selector = f".claw-control[data-axis='{axis}']" + (f"[data-direction='{direction}']" if axis in {"x", "y", "z"} else "")
    page.locator(selector).click()


def _grip(page) -> None:
    if _interaction(page) == "full": page.keyboard.press("f")
    else: page.locator(".claw-grip").click()


def _reset(page) -> None:
    if _interaction(page) == "full": page.keyboard.press("r")
    else: page.locator(".claw-reset").click()


def _move_axis(page, axis: str, target: float) -> None:
    index = {"x": 0, "y": 1, "z": 2}[axis]
    for _ in range(180):
        state = page.evaluate("() => ({p:[...window.threeCameraClawMachineModel.position],v:[...window.threeCameraClawMachineModel.velocity]})")
        error, velocity = target - state["p"][index], state["v"][index]
        if abs(error) < .20 and abs(velocity) < .06: return
        if (abs(error) < .20 and abs(velocity) >= .06) or (velocity * error < 0 and abs(velocity) > .025) or (abs(error) < .75 and abs(velocity) > .12): _button(page, "brake")
        else: _button(page, axis, 1 if error > 0 else -1)
    final = page.evaluate("() => ({position:[...window.threeCameraClawMachineModel.position],velocity:[...window.threeCameraClawMachineModel.velocity],tick:window.threeCameraClawMachineModel.tick,collisions:window.threeCameraClawMachineModel.collisions,captured:window.threeCameraClawMachineModel.captured,readout:document.querySelector('.readout')?.textContent})")
    raise AssertionError(f"{axis} axis failed to settle at {target}: {final}")


def _move(page, target: list[float]) -> None:
    for axis, value in zip(("x", "z", "y"), (target[0], target[2], target[1])): _move_axis(page, axis, value)


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID: raise AssertionError(mechanic)
    truth = _read(state_dir / "ground_truth.json")
    target, chute, safe = truth["solver"]["target"], truth["solver"]["chute"], truth["solver"]["safe_y"]
    _button(page, "x", 1 if target[0] > 0 else -1); _button(page, "coast"); _shot(page, out_dir, mechanic, "three-staggered-active-feeds")
    _move(page, [target[0], safe, target[2]]); _move_axis(page, "y", target[1] + .5)
    _grip(page); expect(page.locator(".claw-load-state")).to_have_text("LOAD"); _shot(page, out_dir, mechanic, "marked-artifact-grab")
    _move_axis(page, "y", safe); _shot(page, out_dir, mechanic, "artifact-above-obstacle-cage")
    _move_axis(page, "x", chute[0]); _move_axis(page, "z", chute[2]); _shot(page, out_dir, mechanic, "obstacle-threading")
    _move_axis(page, "y", chute[1] + .15); _move_axis(page, "x", chute[0]); _move_axis(page, "z", chute[2])
    _grip(page); expect(page.locator(".claw-complete[data-visible='true']")).to_be_visible(); _shot(page, out_dir, mechanic, "chute-delivery")
    clean = page.evaluate("() => ({collisions:window.threeCameraClawMachineModel.collisions,resets:window.threeCameraClawMachineModel.resets,contacts:window.threeCameraClawMachineModel.events.filter(e=>e.kind==='physics_tick'&&e.contact).map(e=>({tick:e.tick,contact:e.contact,position:e.position,resolution:e.resolution}))})")
    if clean["collisions"] != 0 or clean["resets"] != 0: raise AssertionError(f"authoritative claw solve was not clean: {clean}")
    page.locator(".claw-submit").click(); expect(page.locator(".readout")).to_have_text("PASS", timeout=8_000)
