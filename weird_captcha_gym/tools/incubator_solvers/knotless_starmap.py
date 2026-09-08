"""Implementation witness for Knotless Starmap.

This helper reads the generated witness only to produce a normal sequence of
mouse gestures. It is not a screenshot-only agent evaluation or a difficulty
measurement: the benchmark task itself exposes only the visible map and
controls to an evaluated computer-use agent.
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "knotless_starmap"


def _screen(box: dict[str, float], point: list[float] | tuple[float, float]) -> tuple[float, float]:
    return (
        box["x"] + float(point[0]) * box["width"] / 860.0,
        box["y"] + float(point[1]) * box["height"] / 500.0,
    )


def _parking_positions(count: int) -> list[list[float]]:
    # Keep the temporary parking lane in the unobstructed right margin.
    # The 32px spacing also
    # remains above every profile's minimum vertex separation.
    candidates = [[810.0, 20.0 + 32.0 * index] for index in range(15)]
    return candidates[:count]


def _move(page, canvas, before: list[float], after: list[float], full: bool) -> None:
    box = canvas.bounding_box()
    if not box:
        raise AssertionError("starmap canvas has no visible bounding box")
    start, finish = _screen(box, before), _screen(box, after)
    if full:
        page.mouse.move(*start)
        page.mouse.down()
        page.mouse.move(*finish, steps=10)
        page.mouse.up()
    else:
        page.mouse.click(*start)
        page.mouse.click(*finish)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    old = json.loads((state_dir / "public_state.json").read_text(encoding="utf-8"))["challenge_id"]
    page.locator(".ks-abandon").click()
    expect(page.locator(".ks-verdict")).to_contain_text("FAIL")
    page.screenshot(path=str(out_dir / f"{mechanic}-failure.png"), full_page=True)
    page.get_by_role("button", name="BEGIN FRESH MAP →", exact=True).click()
    expect(page.locator(".ks-verdict")).to_be_hidden()
    new = json.loads((state_dir / "public_state.json").read_text(encoding="utf-8"))["challenge_id"]
    assert new != old
    page.screenshot(path=str(out_dir / f"{mechanic}-recovery.png"), full_page=True)


def solve(
    page,
    state_dir: Path,
    out_dir: Path,
    mechanic: str = MECHANIC_ID,
    advance=None,
) -> None:
    del advance
    truth = json.loads((state_dir / "ground_truth.json").read_text(encoding="utf-8"))
    vertices = truth["world"]["vertices"]
    full = (truth.get("control_condition") or {}).get("interaction", "full") == "full"
    positions = {str(vertex["id"]): [float(vertex["x"]), float(vertex["y"])] for vertex in vertices}
    parking = _parking_positions(len(vertices))
    canvas = page.locator(".ks-canvas")

    for vertex, destination in zip(vertices, parking):
        vertex_id = str(vertex["id"])
        _move(page, canvas, positions[vertex_id], destination, full)
        positions[vertex_id] = destination
    page.screenshot(path=str(out_dir / f"{mechanic}-parking.png"), full_page=True)

    solution = truth["solution_positions"]
    for vertex in vertices:
        vertex_id = str(vertex["id"])
        destination = [float(solution[vertex_id][0]), float(solution[vertex_id][1])]
        _move(page, canvas, positions[vertex_id], destination, full)
        positions[vertex_id] = destination
    page.screenshot(path=str(out_dir / f"{mechanic}-prepared.png"), full_page=True)
    expect(page.locator(".ks-count")).to_have_text("0")
    page.locator(".ks-submit").click()
    expect(page.locator(".readout")).to_have_attribute("data-status", "passed", timeout=15000)
    page.screenshot(path=str(out_dir / f"{mechanic}-pass.png"), full_page=True)
