from __future__ import annotations

import math
from pathlib import Path


MECHANIC_ID = "velvet_valet"


def _read_json(path: Path) -> dict:
    import json
    return json.loads(path.read_text(encoding="utf-8"))


def _angle_error(current: float, target: float) -> float:
    return (target - current + math.pi) % (2 * math.pi) - math.pi


def _pose(page) -> dict[str, float]:
    car = page.locator(".vv-car")
    return {
        "x": float(car.get_attribute("data-x")),
        "y": float(car.get_attribute("data-y")),
        "heading": float(car.get_attribute("data-heading")),
        "speed": float(car.get_attribute("data-speed")),
        "tick": int(page.locator(".vv-tick b").inner_text()),
    }


def _wait_ticks(page, target: int) -> None:
    page.wait_for_function(
        "target => Number(document.querySelector('.vv-tick b').textContent) >= target",
        arg=int(target),
        timeout=15_000,
    )


def _full_down(page, key: str) -> None:
    page.keyboard.down(key)


def _full_up(page, key: str) -> None:
    page.keyboard.up(key)


def _button(page, command: str) -> None:
    page.locator(f'[data-vv-command="{command}"]').click()


def _set_steer(page, interaction: str, direction: int) -> None:
    if interaction == "simplified":
        _button(page, {1: "steer_right", -1: "steer_left", 0: "steer_center"}[direction])
    else:
        if direction > 0:
            _full_down(page, "ArrowRight")
        elif direction < 0:
            _full_down(page, "ArrowLeft")
        else:
            _full_up(page, "ArrowLeft"); _full_up(page, "ArrowRight")


def _release_steer(page, interaction: str) -> None:
    if interaction == "simplified":
        _button(page, "steer_center")
    else:
        _full_up(page, "ArrowLeft"); _full_up(page, "ArrowRight")


def _set_drive(page, interaction: str, reverse: bool = False) -> None:
    if interaction == "simplified":
        _button(page, "reverse" if reverse else "forward")
    else:
        _full_down(page, "ArrowDown" if reverse else "ArrowUp")


def _coast(page, interaction: str) -> None:
    if interaction == "simplified":
        _button(page, "coast")
    else:
        _full_up(page, "ArrowUp"); _full_up(page, "ArrowDown")


def _brake(page, interaction: str, ticks: int = 4) -> None:
    if interaction == "simplified":
        _button(page, "brake_on")
        page.wait_for_timeout(80 * ticks)
        return
    _full_up(page, "ArrowUp"); _full_up(page, "ArrowDown")
    _full_down(page, "Space")
    page.wait_for_timeout(80 * ticks)
    _full_up(page, "Space")


def _drive_to(page, interaction: str, target: dict[str, float], *, reverse: bool = False, final_heading: float | None = None) -> None:
    # Short feedback-controlled holds make this solver an ordinary-input
    # demonstration rather than a direct state setter. The route is only
    # available to the scripted fixture; a screenshot agent sees the same
    # courtyard, car, bay, and telemetry but not this hidden waypoint list.
    for _ in range(520):
        pose = _pose(page)
        dx, dy = float(target["x"]) - pose["x"], float(target["y"]) - pose["y"]
        distance = math.hypot(dx, dy)
        if distance < (24.0 if reverse else 8.0):
            break
        desired = float(final_heading) if reverse and final_heading is not None else math.atan2(dy, dx)
        error = _angle_error(pose["heading"], desired)
        direction = 1 if error > 0.08 else -1 if error < -0.08 else 0
        _set_steer(page, interaction, direction)
        _set_drive(page, interaction, reverse=reverse)
        # Update the visible control at roughly one physics tick.  Longer
        # holds overshoot the small-radius turn and make the feedback route
        # oscillate around the next waypoint.
        _wait_ticks(page, pose["tick"] + 1)
        if page.locator(".vv.is-failed").count():
            raise AssertionError("vehicle collided while following the visible courtyard route")
    _release_steer(page, interaction)
    _coast(page, interaction)
    _brake(page, interaction, ticks=4)


def _align(page, interaction: str, heading: float) -> None:
    if interaction == "simplified":
        # A proxy-button car has no held-key state.  Pair a short forward arc
        # with an opposite-steer reverse arc so their translations largely
        # cancel while their yaw changes add.
        for _ in range(180):
            pose = _pose(page)
            error = _angle_error(pose["heading"], heading)
            if abs(error) < 0.02:
                break
            turn = 1 if error > 0 else -1
            _set_steer(page, interaction, turn)
            _set_drive(page, interaction, reverse=False)
            _wait_ticks(page, pose["tick"] + 1)
            _brake(page, interaction, ticks=3)
            pose = _pose(page)
            _set_steer(page, interaction, -turn)
            _set_drive(page, interaction, reverse=True)
            _wait_ticks(page, pose["tick"] + 1)
            _brake(page, interaction, ticks=3)
        _release_steer(page, interaction)
        _coast(page, interaction)
        _brake(page, interaction, ticks=5)
        return
    for _ in range(180):
        pose = _pose(page)
        error = _angle_error(pose["heading"], heading)
        if abs(error) < 0.02:
            break
        direction = 1 if error > 0 else -1
        _set_steer(page, interaction, direction)
        _set_drive(page, interaction, reverse=False)
        _wait_ticks(page, pose["tick"] + 1)
        # Alternate a one-tick brake pulse with the forward pulse so the car
        # can change heading in the staging area without driving away from
        # the reverse-entry line.
        if interaction == "simplified":
            _button(page, "brake_on")
        else:
            _full_down(page, "Space")
        pose = _pose(page)
        _wait_ticks(page, pose["tick"] + 1)
        if interaction == "simplified":
            _button(page, "forward")
        else:
            _full_up(page, "Space")
    _release_steer(page, interaction)
    _coast(page, interaction)
    _brake(page, interaction, ticks=5)


def _brake_pulse(page, interaction: str) -> None:
    if interaction == "simplified":
        _button(page, "brake_on")
    else:
        _full_up(page, "ArrowUp"); _full_up(page, "ArrowDown")
        _full_down(page, "Space")


def _reverse_into_bay(page, interaction: str, target: dict[str, float], position_tolerance: float, speed_tolerance: float) -> None:
    # The last metres need a different controller from the open-courtyard
    # route: creep, brake, and creep again so the small final speed tolerance
    # does not make the car skip over the bay center.  Use the signed
    # projection onto the current heading as well as distance: if a very
    # tight bay is crossed, the controller can make a short forward recovery
    # instead of continuing to reverse away from the target.
    _set_steer(page, interaction, 0)
    for _ in range(420):
        pose = _pose(page)
        dx, dy = float(target["x"]) - pose["x"], float(target["y"]) - pose["y"]
        distance = math.hypot(dx, dy)
        if distance <= position_tolerance and abs(pose["speed"]) <= speed_tolerance:
            return
        along = dx * math.cos(pose["heading"]) + dy * math.sin(pose["heading"])
        desired_direction = 1 if along >= 0 else -1
        # Keep speed high in the open approach, then use a proportional slow
        # zone.  This avoids the d5 simplified case's late, one-tick brake
        # that otherwise carries the car past the bay.
        target_speed = 1.6 if distance > 60.0 else max(speed_tolerance, distance * 0.014)
        same_direction = pose["speed"] * desired_direction >= 0
        brake = abs(pose["speed"]) > target_speed or (not same_direction and abs(pose["speed"]) > speed_tolerance)
        if brake:
            _brake_pulse(page, interaction)
        else:
            _set_drive(page, interaction, reverse=desired_direction < 0)
        _wait_ticks(page, pose["tick"] + 1)
        if interaction == "full" and brake:
            _full_up(page, "Space")
    raise AssertionError(f"reverse entry did not settle: {_pose(page)}")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    assert mechanic == MECHANIC_ID
    truth = _read_json(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    page.locator(".vv-start").click()
    if page.locator(".vv-start").count():
        raise AssertionError("engine did not start")
    # Reverse straight into the left kerb.  This is a disposable negative
    # attempt and is deterministic for every generated start pose.
    _set_drive(page, interaction, reverse=True)
    _set_steer(page, interaction, 0)
    page.wait_for_function("() => document.querySelector('.vv')?.classList.contains('is-failed')", timeout=15_000)
    page.screenshot(path=str(out_dir / f"{mechanic}-failure-terminal.png"))
    page.locator(".vv-start").wait_for(timeout=8_000)
    page.screenshot(path=str(out_dir / f"{mechanic}-failure-recovery.png"))


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    assert mechanic == MECHANIC_ID
    public = _read_json(state_dir / "public_state.json")
    truth = _read_json(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    route = list(truth.get("route_waypoints") or [])
    target = public["world"]["target"]
    page.locator(".vv-start").wait_for(timeout=8_000)
    page.locator(".vv-start").click()
    for waypoint in route[:-1]:
        _drive_to(page, interaction, waypoint)
    _align(page, interaction, float(target["heading"]))
    physics = public["world"]["physics"]
    _reverse_into_bay(page, interaction, route[-1], float(physics["position_tolerance"]), float(physics["speed_tolerance"]))
    _brake(page, interaction, ticks=8)
    page.screenshot(path=str(out_dir / f"{mechanic}-pre-submit.png"))
    page.locator(".vv-submit").click()
    page.wait_for_timeout(1300)
    page.screenshot(path=str(out_dir / f"{mechanic}-solved.png"))
