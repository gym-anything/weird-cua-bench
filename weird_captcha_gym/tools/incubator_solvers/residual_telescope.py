from __future__ import annotations

import json
import math
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "residual_telescope"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _canvas_box(page) -> dict:
    value = page.locator(".residual-model-canvas").bounding_box()
    if not value:
        raise AssertionError("residual telescope model plate is not visible")
    return value


def _screen(box: dict, image: dict, point: list[float]) -> tuple[float, float]:
    # Computer-use pointer coordinates are integer screen pixels. Normalizing
    # both click and drag paths here avoids mode-specific subpixel rounding.
    return round(box["x"] + point[0] / image["width"] * box["width"]), round(box["y"] + point[1] / image["height"] * box["height"])


def _shape_points(truth: dict, component: str) -> list[list[float]]:
    geometry = truth["target_geometry"]
    if component in {"disc", "core"}:
        shape = geometry[component]
        return [shape["center"], [shape["center"][0] + math.cos(shape["angle"]) * shape["radius"], shape["center"][1] + math.sin(shape["angle"]) * shape["radius"]]]
    if component == "bar":
        shape = geometry[component]
        dx, dy = math.cos(shape["angle"]) * shape["length"] / 2, math.sin(shape["angle"]) * shape["length"] / 2
        return [[shape["center"][0] - dx, shape["center"][1] - dy], [shape["center"][0] + dx, shape["center"][1] + dy]]
    index = int(component.split("_")[1]) - 1
    return geometry["arms"][index]


def _draw_component(page, truth: dict, component: str, points: list[list[float]] | None = None) -> None:
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    box, image = _canvas_box(page), truth["image"]
    points = points or _shape_points(truth, component)
    if interaction == "simplified":
        for point in points:
            page.mouse.click(*_screen(box, image, point))
            page.wait_for_timeout(18)
    else:
        page.mouse.move(*_screen(box, image, points[0]))
        page.mouse.down()
        for point in points[1:]:
            # One delivered sample per generated arm vertex preserves the same
            # polyline used by Simplified; the canvas connects sparse samples.
            page.mouse.move(*_screen(box, image, point), steps=1 if component.startswith("arm_") else 4)
            page.wait_for_timeout(15)
        page.mouse.up()
    page.wait_for_timeout(45)


def _draw_shapes(page, truth: dict) -> None:
    for component in truth["component_sequence"]:
        _draw_component(page, truth, component)
    expect(page.locator('.residual-optics[data-locked="false"]')).to_be_visible()


def _tune(page, truth: dict, *, wrong_first: bool = False) -> None:
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    for index, spec in enumerate(truth["parameter_specs"]):
        parameter_id = spec["id"]
        target = int(truth["target_values"][parameter_id])
        if wrong_first and index == 0:
            target = target + 1 if target < 10 else target - 1
        if interaction == "simplified":
            delta = target - int(spec["initial"])
            selector = f'.residual-nudge[data-parameter="{parameter_id}"][data-delta="{1 if delta > 0 else -1}"]'
            for _ in range(abs(delta)):
                page.locator(selector).click()
                page.wait_for_timeout(14)
        else:
            track = page.locator(f'.residual-slider-track[data-parameter="{parameter_id}"]')
            box = track.bounding_box()
            if not box:
                raise AssertionError(f"slider {parameter_id} is not visible")
            start_x = box["x"] + (int(spec["initial"]) - spec["minimum"]) / (spec["maximum"] - spec["minimum"]) * box["width"]
            target_x = box["x"] + (target - spec["minimum"]) / (spec["maximum"] - spec["minimum"]) * box["width"]
            y = box["y"] + box["height"] / 2
            page.mouse.move(start_x, y)
            page.mouse.down()
            page.mouse.move(target_x, y, steps=5)
            page.mouse.up()
            page.wait_for_timeout(28)


def _perform(page, truth: dict, *, wrong_first: bool = False, screenshot: Path | None = None) -> None:
    _draw_shapes(page, truth)
    if screenshot:
        page.screenshot(path=str(screenshot))
    _tune(page, truth, wrong_first=wrong_first)


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-initial.png"))
    _perform(page, truth, screenshot=out_dir / f"{mechanic}-components-fitted.png")
    expect(page.locator('.residual-shell[data-complete="true"]')).to_be_visible()
    page.screenshot(path=str(out_dir / f"{mechanic}-completed-before-certify.png"))
    page.locator(".residual-submit").click()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=8_000)
    page.screenshot(path=str(out_dir / f"{mechanic}-pass.png"))


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = _read(state_dir / "ground_truth.json")["challenge_id"]
    _perform(page, _read(state_dir / "ground_truth.json"), wrong_first=True)
    page.locator(".residual-submit").click()
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if _read(state_dir / "ground_truth.json")["challenge_id"] != before:
            break
        time.sleep(.05)
    else:
        raise AssertionError("failed telescope submission did not generate a fresh challenge")
    expect(page.locator('.residual-shell[data-fresh-failure="true"]')).to_be_visible()
    expect(page.locator(".readout")).to_contain_text("FAIL")
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-fail-refresh.png"))
