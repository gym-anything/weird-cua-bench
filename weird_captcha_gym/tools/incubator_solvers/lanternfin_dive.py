from __future__ import annotations

import json
import math
import time
from pathlib import Path


MECHANIC_ID = "lanternfin_dive"
KEYS = {
    ("tail", -1): "a", ("tail", 1): "d",
    ("yaw", -1): "j", ("yaw", 1): "l",
    ("pitch", -1): "k", ("pitch", 1): "i",
    ("roll", -1): "q", ("roll", 1): "e",
}
CHANNELS = ("tail", "yaw", "pitch", "roll")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _model(page):
    return page.evaluate(
        """() => {
          const m = window.lanternfinDiveModel;
          if (!m) return null;
          return {tick:m.tick, hold:m.hold, fish:{...m.fish}, controls:{...m.controls}, target:{...m.state.target}, physics:{...m.state.physics}, interaction:m.interaction};
        }"""
    )


def _wrap(value: float) -> float:
    return (value + math.pi) % (2 * math.pi) - math.pi


def _desired(snapshot: dict) -> dict[str, int]:
    fish = snapshot["fish"]
    target = snapshot["target"]
    dx = float(target["x"]) - float(fish["x"])
    dy = float(target["y"]) - float(fish["y"])
    dz = float(target["z"]) - float(fish["z"])
    horizontal = math.hypot(dx, dz)
    desired_yaw = math.atan2(dz, dx)
    desired_pitch = math.atan2(dy, max(0.001, horizontal))
    distance = math.sqrt(dx * dx + dy * dy + dz * dz)
    yaw_error = _wrap(desired_yaw - float(fish["yaw"]))
    # The last part of the task is a docking maneuver, not a continued
    # point-at-the-pearl maneuver: once close, level the body before the
    # upright hold is counted.
    pitch_error = (
        -float(fish["pitch"])
        if distance < 0.30 and abs(dy) < 0.08
        else desired_pitch - float(fish["pitch"])
    )
    speed = math.sqrt(sum(float(fish[key]) ** 2 for key in ("vx", "vy", "vz")))
    def sign(value: float, deadband: float) -> int:
        return 1 if value > deadband else -1 if value < -deadband else 0
    # The controller is deliberately a closed-loop policy: it reads the
    # rendered state after each short burst, then chooses the next visible
    # torque detent from the observed attitude and 3D range.
    radius = float(snapshot["physics"]["arrival_radius"])
    speed_limit = float(snapshot["physics"]["speed_limit"])
    if distance > 0.24:
        tail = 1
    elif distance > radius * 0.80 and speed < speed_limit * 1.5:
        tail = 1
    elif distance < 0.48 and speed > speed_limit * 1.25:
        tail = -1
    else:
        tail = 0
    return {
        "yaw": sign(yaw_error, 0.075),
        "pitch": sign(pitch_error, 0.06),
        "roll": sign(-float(fish["roll"]), 0.045),
        "tail": tail,
    }


def _set_simplified(page, active: dict[str, int], desired: dict[str, int]) -> None:
    for channel in CHANNELS:
        value = int(desired[channel])
        if active.get(channel, 0) == value:
            continue
        page.locator(f'button[data-channel="{channel}"][data-value="{value}"]').click()
        active[channel] = value


def _set_full(page, active: dict[str, int], desired: dict[str, int]) -> None:
    for channel in CHANNELS:
        value = int(desired[channel])
        previous = int(active.get(channel, 0))
        if previous == value:
            continue
        if previous:
            page.keyboard.up(KEYS[(channel, previous)])
        if value:
            page.keyboard.down(KEYS[(channel, value)])
        active[channel] = value


def _release_full(page, active: dict[str, int]) -> None:
    for channel, value in list(active.items()):
        if value:
            page.keyboard.up(KEYS[(channel, value)])
        active[channel] = 0


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    del out_dir
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    page.locator("#lf-certify").click()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if (state_dir / "attempts.jsonl").is_file():
            return
        time.sleep(0.05)
    raise AssertionError("Lanternfin deliberate certification did not reach the server")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    del state_dir, out_dir
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    first = _model(page)
    if not first:
        raise AssertionError("Lanternfin model was not rendered")
    interaction = first["interaction"]
    active = {channel: 0 for channel in CHANNELS}
    # A small camera orbit is an ordinary inspection action. It changes only
    # the view, leaving the generated world and the replay contract untouched.
    page.mouse.move(490, 360)
    page.mouse.down()
    page.mouse.move(560, 338, steps=3)
    page.mouse.up()
    settled = False
    for _ in range(int(first["physics"]["max_ticks"]) + 20):
        snapshot = _model(page)
        if not snapshot:
            raise AssertionError("Lanternfin model disappeared during solve")
        desired = _desired(snapshot)
        if interaction == "simplified":
            _set_simplified(page, active, desired)
        else:
            _set_full(page, active, desired)
        page.wait_for_timeout(82)
        current = _model(page)
        if current and current["tick"] >= int(current["physics"]["max_ticks"]):
            break
        if current:
            fish = current["fish"]
            target = current["target"]
            distance = math.sqrt(sum((float(fish[a]) - float(target[a])) ** 2 for a in ("x", "y", "z")))
            speed = math.sqrt(sum(float(fish[a]) ** 2 for a in ("vx", "vy", "vz")))
            if int(current.get("hold", 0)) >= int(current["physics"]["hold_ticks"]):
                # Neutralize the visible controls and require the hold to
                # survive one more physical tick before certifying. This
                # avoids turning a transient overlap into a false oracle
                # pass when a held key is released at the window boundary.
                if interaction == "full":
                    _release_full(page, active)
                else:
                    _set_simplified(page, active, {channel: 0 for channel in CHANNELS})
                page.wait_for_timeout(82)
                stable = _model(page)
                if stable and int(stable.get("hold", 0)) >= int(stable["physics"]["hold_ticks"]):
                    settled = True
                    break
    if interaction == "full":
        _release_full(page, active)
    elif not settled:
        _set_simplified(page, active, {channel: 0 for channel in CHANNELS})
    page.locator("#lf-certify").click()
    page.wait_for_function("() => document.querySelector('#lanternfin-readout')?.textContent === 'PASS'", timeout=20_000)
