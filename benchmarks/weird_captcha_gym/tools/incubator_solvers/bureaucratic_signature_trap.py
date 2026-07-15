from __future__ import annotations

import math
from pathlib import Path

from benchmarks.weird_captcha_gym.tools.incubator_solvers.reviewed_overhaul_common import (
    drag_delta,
    expect_fail_and_fresh,
    read_json,
    shot,
)

MECHANIC_ID = "bureaucratic_signature_trap"


def _align(page, form: dict) -> None:
    for layer in reversed(form["layers"]):
        dx = float(layer["target"]["x"]) - float(layer["initial"]["x"])
        dy = float(layer["target"]["y"]) - float(layer["initial"]["y"])
        drag_delta(page, page.locator(f'.sheet-tab[data-control-id="{layer["id"]}"]'), dx, dy, maximum_step=24)


def _draw_points(page, form: dict, points: list[list[float]]) -> None:
    canvas = page.locator(".signature-surface")
    box = canvas.bounding_box()
    assert box
    stage = form["stage"]
    screen = [
        (
            box["x"] + float(point[0]) / float(stage["width"]) * box["width"],
            box["y"] + float(point[1]) / float(stage["height"]) * box["height"],
        )
        for point in points
    ]
    page.mouse.move(*screen[0])
    page.mouse.down()
    for point in screen[1:]:
        page.mouse.move(*point, steps=1)
    page.mouse.up()


def _generic_circle(form: dict, radius: float, count: int = 72) -> list[list[float]]:
    aperture = form["aperture"]
    return [
        [
            float(aperture["x"]) + radius * math.cos(index * math.tau / count),
            float(aperture["y"]) + radius * math.sin(index * math.tau / count),
        ]
        for index in range(count + 1)
    ]


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    assert mechanic == MECHANIC_ID
    truth = read_json(state_dir / "ground_truth.json")
    before, form = truth["challenge_id"], truth["form"]
    _align(page, form)
    # This was accepted by v2.  It is now the mechanic-specific forgery test.
    _draw_points(page, form, _generic_circle(form, float(form["aperture"]["radius"]) * .62))
    page.locator(".carbon-submit").click()
    expect_fail_and_fresh(page, state_dir, before)
    shot(page, out_dir, mechanic, "generic-circle-rejected")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    assert mechanic == MECHANIC_ID
    form = read_json(state_dir / "public_state.json")["form"]
    _align(page, form)
    _draw_points(page, form, form["original_trace"])
    shot(page, out_dir, mechanic, "registered-original-traced")
    page.locator(".carbon-submit").click()
