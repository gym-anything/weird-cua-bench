from __future__ import annotations

import json
import math
from pathlib import Path


MECHANIC_ID = "cloudpost_circuit"


def _step(plane: dict[str, float], control: list[float], physics: dict) -> None:
    desired_yaw = max(-1.0, min(1.0, control[0])) * float(physics["max_yaw"])
    desired_pitch = max(-1.0, min(1.0, control[1])) * float(physics["max_pitch"])
    step = float(physics["turn_step"])
    plane["yaw"] += max(-step, min(step, desired_yaw - plane["yaw"]))
    plane["pitch"] += max(-step, min(step, desired_pitch - plane["pitch"]))
    cp = math.cos(plane["pitch"])
    plane["x"] += math.sin(plane["yaw"]) * cp * float(physics["flight_speed"])
    plane["y"] += math.sin(plane["pitch"]) * float(physics["flight_speed"])
    plane["z"] += math.cos(plane["yaw"]) * cp * float(physics["flight_speed"])


def _control_for(plane: dict[str, float], target: dict, physics: dict) -> list[float]:
    dx = float(target["x"]) - plane["x"]
    dy = float(target["y"]) - plane["y"]
    dz = float(target["z"]) - plane["z"]
    distance = max(1e-6, math.sqrt(dx * dx + dy * dy + dz * dz))
    return [
        max(-1.0, min(1.0, math.atan2(dx, dz) / float(physics["max_yaw"]))),
        max(-1.0, min(1.0, math.asin(max(-1.0, min(1.0, dy / distance))) / float(physics["max_pitch"]))),
    ]


def _read_public(state_dir: Path) -> dict:
    return json.loads((state_dir / "public_state.json").read_text(encoding="utf-8"))


def _visible_tick(page) -> int:
    text = page.locator(".cloudpost-tick").inner_text()
    return int(text.split()[1])


def _visible_count(page) -> int:
    text = page.locator(".cloudpost-count").inner_text()
    return int(text.split("/", 1)[0].strip())


def _full_step(page, box, control: list[float], prior_tick: int, force_pointer_event: bool = False) -> int:
    if force_pointer_event:
        # Move through the visible neutral point so a large correction always
        # produces a real pointermove even when Playwright's previous mouse
        # position is already numerically close to the requested vector.
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    x = box["x"] + (control[0] + 1.0) * 0.5 * box["width"]
    y = box["y"] + (0.5 - control[1] * 0.5) * box["height"]
    page.mouse.move(x, y)
    page.wait_for_timeout(25)
    return _visible_tick(page)


def _simplified_set(page, control: list[float], desired: list[float]) -> None:
    while control[0] - desired[0] > 0.055:
        page.get_by_role("button", name="◀ TURN").click()
        control[0] -= 0.12
    while desired[0] - control[0] > 0.055:
        page.get_by_role("button", name="TURN ▶").click()
        control[0] += 0.12
    while control[1] - desired[1] > 0.055:
        page.get_by_role("button", name="▼ DIVE").click()
        control[1] -= 0.10
    while desired[1] - control[1] > 0.055:
        page.get_by_role("button", name="▲ CLIMB").click()
        control[1] += 0.10


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    state = _read_public(state_dir)
    physics = state["physics"]
    plane = {key: float(state["initial_plane"][key]) for key in ("x", "y", "z", "yaw", "pitch")}
    control = [0.0, 0.0]
    canvas = page.locator(".cloudpost-canvas")
    box = canvas.bounding_box()
    if box is None:
        raise AssertionError("Cloudpost canvas is not visible")
    simplified = state.get("control_condition", {}).get("interaction") == "simplified"
    actual_tick = _visible_tick(page)
    # The live browser advances while the page is loading.  Account for those
    # neutral ticks before issuing the first ordinary pointer/button input.
    for _ in range(actual_tick):
        _step(plane, [0.0, 0.0], physics)
    full_control = [0.0, 0.0]
    for target_index, target in enumerate(state["targets"], 1):
        for _ in range(3000):
            desired = _control_for(plane, target, physics)
            if simplified:
                _simplified_set(page, control, desired)
                page.wait_for_timeout(25)
                next_tick = _visible_tick(page)
                commanded = control
            else:
                # Pointer movement is a persistent command.  The browser
                # deliberately ignores sub-0.004 jitter, so replay the last
                # command until the next visible correction crosses that
                # same threshold.
                command_changed = max(abs(desired[0] - full_control[0]), abs(desired[1] - full_control[1])) >= 0.004
                if command_changed:
                    full_control = desired
                next_tick = _full_step(page, box, full_control, actual_tick, command_changed)
                commanded = full_control
            for _tick in range(max(0, next_tick - actual_tick)):
                _step(plane, commanded, physics)
            actual_tick = next_tick
            # The displayed contact count is authoritative. The local flight
            # estimate can drift while browser input and physics run in parallel.
            if _visible_count(page) >= target_index:
                break
        else:
            raise AssertionError(f"solver could not reach {target['id']}")
    page.wait_for_timeout(900)
    if "PASS" not in page.locator("body").inner_text():
        raise AssertionError("Cloudpost solver did not obtain a visible PASS")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    state = _read_public(state_dir)
    box = page.locator(".cloudpost-canvas").bounding_box()
    if box is None:
        raise AssertionError("Cloudpost canvas is not visible")
    # Keep a steady neutral vector until the plane leaves the visible flight
    # corridor. This is a disposable negative attempt; it is never mixed into
    # the pass film.
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    physics = state["physics"]
    wait_ms = int((float(physics["world_x"]) / max(0.1, float(physics["flight_speed"])) + 80) * int(physics["tick_ms"])) + 1000
    page.wait_for_timeout(wait_ms)
