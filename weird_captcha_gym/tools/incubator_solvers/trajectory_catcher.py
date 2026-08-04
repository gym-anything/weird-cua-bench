from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "trajectory_catcher"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, mechanic: str, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{label}.png"), full_page=True)


def _wait_for_phase(page, phase: str, timeout: int = 8_000) -> None:
    expect(page.locator(".trajectory-catcher")).to_have_attribute("data-phase", phase, timeout=timeout)


def _canvas_position(page, point: dict) -> tuple[float, float]:
    bounds = page.locator("#trajectory-canvas").bounding_box()
    if not bounds:
        raise AssertionError("trajectory canvas has no interactive bounds")
    return (
        bounds["x"] + float(point["x"]) / 900.0 * bounds["width"],
        bounds["y"] + float(point["y"]) / 480.0 * bounds["height"],
    )


def _place_catcher(page, round_data: dict, solution: dict) -> None:
    initial = round_data["initial_catcher"]
    source = _canvas_position(page, initial)
    destination = _canvas_position(page, solution)
    page.mouse.move(*source)
    page.mouse.down()
    page.mouse.move(*destination, steps=10)
    page.mouse.up()

    current_angle = int(initial["angle_deg"]) % 180
    target_angle = int(solution["angle_deg"]) % 180
    aperture = int(initial["aperture"])
    target_aperture = int(solution["aperture"])
    interaction = page.locator(".trajectory-catcher").get_attribute("data-interaction")
    if interaction == "simplified":
        clockwise_steps = ((target_angle - current_angle) % 180) // 15
        counter_steps = ((current_angle - target_angle) % 180) // 15
        if clockwise_steps and clockwise_steps <= counter_steps:
            for _ in range(clockwise_steps):
                page.locator("#trajectory-rotate-right").click()
        elif counter_steps:
            for _ in range(counter_steps):
                page.locator("#trajectory-rotate-left").click()
        button = "#trajectory-size-up" if target_aperture > aperture else "#trajectory-size-down"
        for _ in range(abs(target_aperture - aperture) // 10):
            page.locator(button).click()
    elif interaction == "full":
        bounds = page.locator("#trajectory-canvas").bounding_box()
        if not bounds:
            raise AssertionError("trajectory canvas has no visible bounds")

        def screen_point(local_x: float, local_y: float, angle_deg: float) -> tuple[float, float]:
            import math

            radians = math.radians(angle_deg)
            world_x = float(solution["x"]) + local_x * math.cos(radians) - local_y * math.sin(radians)
            world_y = float(solution["y"]) + local_x * math.sin(radians) + local_y * math.cos(radians)
            return (
                bounds["x"] + world_x / 900.0 * bounds["width"],
                bounds["y"] + world_y / 480.0 * bounds["height"],
            )

        ring_radius = max(float(round_data["capture_depth"]) / 2, aperture / 2) + 18
        delta = ((target_angle - current_angle + 90) % 180) - 90
        if delta:
            page.mouse.move(*screen_point(ring_radius, 0, 0))
            page.mouse.down()
            import math

            page.mouse.move(*screen_point(ring_radius * math.cos(math.radians(delta)), ring_radius * math.sin(math.radians(delta)), 0), steps=12)
            page.mouse.up()
        if target_aperture != aperture:
            page.mouse.move(*screen_point(0, aperture / 2, target_angle))
            page.mouse.down()
            page.mouse.move(*screen_point(0, target_aperture / 2, target_angle), steps=10)
            page.mouse.up()
    else:
        raise AssertionError(f"unexpected trajectory interaction {interaction!r}")

    root = page.locator(".trajectory-catcher")
    expected = page.evaluate(
        """() => ({
            angle: document.querySelector('#trajectory-angle')?.textContent,
            aperture: document.querySelector('#trajectory-aperture')?.textContent,
        })"""
    )
    if expected != {"angle": f"{target_angle}°", "aperture": str(target_aperture)}:
        raise AssertionError(f"catcher controls did not reach hidden solution: {expected}")
    expect(root).to_have_attribute("data-phase", "hidden")
    page.locator("#trajectory-arm").click()
    expect(root).to_have_attribute("data-armed", "true")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator("#trajectory-file").click()
    expect(page.locator(".trajectory-catcher[data-fresh-failure='true']")).to_be_visible(timeout=7_000)
    expect(page.locator(".trajectory-foot .readout")).to_have_text("FAIL", timeout=7_000)
    after = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    if before == after:
        raise AssertionError("failed flight log did not issue a fresh challenge")
    _screenshot(page, out_dir, mechanic, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    rounds = truth["rounds"]
    solutions = truth["solutions"]
    if not rounds or len(rounds) != len(solutions):
        raise AssertionError("trajectory challenge has inconsistent flight rounds")

    # The refreshed challenge begins immediately. Preserve visual evidence of the
    # observable flight before any hidden commitment is made.
    _wait_for_phase(page, "observing")
    page.wait_for_timeout(520)
    _screenshot(page, out_dir, mechanic, "active-observation")

    for index, (round_data, solution) in enumerate(zip(rounds, solutions)):
        attempts = 0
        while True:
            _wait_for_phase(page, "hidden")
            _place_catcher(page, round_data, solution)
            if index == 0 and attempts == 0:
                _screenshot(page, out_dir, mechanic, "hidden-commit")
            page.wait_for_function(
                "document.querySelector('.trajectory-catcher')?.dataset.result !== ''",
                timeout=7_000,
            )
            result = page.locator(".trajectory-catcher").get_attribute("data-result")
            if result == "caught":
                break
            if result == "miss" and attempts < int(round_data["replay_limit"]):
                page.locator("#trajectory-replay").click()
                attempts += 1
                continue
            raise AssertionError(
                f"trajectory round {index + 1} did not catch after visible recovery: {result!r}"
            )
        if index < len(rounds) - 1:
            page.locator("#trajectory-next").click()

    _screenshot(page, out_dir, mechanic, "solved")
    page.locator("#trajectory-file").click()
    expect(page.locator(".trajectory-foot .readout")).to_have_text("PASS", timeout=7_000)
    expect(page.locator(".trajectory-foot .readout")).to_have_attribute("data-status", "passed")
