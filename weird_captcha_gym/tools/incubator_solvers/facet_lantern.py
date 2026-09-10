"""Ordinary-input implementation witness for Facet Lantern.

The witness reads the private generated solution to choose a legal sequence, but
performs the same visible drag, button, stud-click, and certify actions exposed
to a screenshot-only agent.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "facet_lantern"


def _edge(first: str, second: str) -> tuple[str, str]:
    return tuple(sorted((str(first), str(second))))


def _visible(vertex: dict, yaw: float, world: dict) -> bool:
    radians = math.radians(yaw)
    depth = float(vertex.get("x", 0)) * math.sin(radians) + float(vertex.get("z", 0)) * math.cos(radians)
    return depth >= -float(world.get("occlusion_band", 0.25)) - 1e-7


def _target_yaw(first: dict, second: dict, world: dict, *, step: float | None = None) -> float:
    candidates = [i * (step or 1.0) for i in range(int(360 / (step or 1.0)))]
    choices = []
    for yaw in candidates:
        if _visible(first, yaw, world) and _visible(second, yaw, world):
            radians = math.radians(yaw)
            def point(vertex):
                return ((float(vertex["x"]) * math.cos(radians) - float(vertex["z"]) * math.sin(radians)) * 150, float(vertex["y"]) * 150)
            # A visible depth flag alone does not make an endpoint clickable:
            # another projected stud can cover it. Choose an exposed view
            # with enough separation for the actual SVG stud hit areas.
            clearance = min(math.dist(point(endpoint), point(other)) for endpoint in (first, second) for other in world["vertices"] if other["id"] != endpoint["id"] and _visible(other, yaw, world))
            choices.append((clearance, yaw))
    if choices:
        return max(choices)[1]
    raise AssertionError(f"no common visible yaw for {first['id']} and {second['id']}")


def _delta(current: float, target: float) -> float:
    return (target - current + 180.0) % 360.0 - 180.0


def _rotate_full(page, stage, current: float, target: float) -> float:
    delta = _delta(current, target)
    if abs(delta) < 0.8:
        # Keep the direct-manipulation witness explicit even when the next
        # required edge is already visible in the initial projection.
        _drag(page, stage, 30)
        _drag(page, stage, -30)
        return current
    while abs(delta) > 150:
        part = 150 if delta > 0 else -150
        _drag(page, stage, part)
        current = (current + part) % 360
        delta = _delta(current, target)
    if abs(delta) > 0.8:
        _drag(page, stage, delta)
        current = (current + delta) % 360
    return current


def _drag(page, stage, degrees: float) -> None:
    box = stage.bounding_box()
    if not box:
        raise AssertionError("facet lantern stage has no visible bounding box")
    start = (box["x"] + 42, box["y"] + 42)
    finish = (start[0] + degrees / 0.55, start[1] + 8)
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move(*finish, steps=12)
    page.mouse.up()


def _rotate_simplified(page, current: float, target: float, step: float) -> float:
    amount = _delta(current, target)
    if abs(amount) < 0.8:
        # Keep the interaction witness explicit even when the first required
        # edge is already exposed in the initial view.
        page.locator(".fl-turn-right").click()
        page.locator(".fl-turn-left").click()
        return current
    direction = ".fl-turn-right" if amount > 0 else ".fl-turn-left"
    count = int(round(abs(amount) / step))
    for _ in range(count):
        page.locator(direction).click()
    return (current + (step if amount > 0 else -step) * count) % 360


def _connect(page, vertex_id: str) -> None:
    locator = page.locator(f'.fl-stud[data-vertex-id="{vertex_id}"]')
    expect(locator).to_be_visible(timeout=3000)
    locator.click()


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    old = json.loads((state_dir / "public_state.json").read_text(encoding="utf-8"))["challenge_id"]
    page.locator(".fl-abandon").click()
    expect(page.locator(".fl-readout")).to_contain_text("FAIL", timeout=15000)
    page.screenshot(path=str(out_dir / f"{mechanic}-failure.png"), full_page=True)
    new = json.loads((state_dir / "public_state.json").read_text(encoding="utf-8"))["challenge_id"]
    assert new != old
    page.screenshot(path=str(out_dir / f"{mechanic}-recovery.png"), full_page=True)


def solve(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID, advance=None) -> None:
    del advance
    truth = json.loads((state_dir / "ground_truth.json").read_text(encoding="utf-8"))
    public = json.loads((state_dir / "public_state.json").read_text(encoding="utf-8"))
    world = truth["world"]
    vertices = {str(vertex["id"]): vertex for vertex in world["vertices"]}
    interaction = (truth.get("control_condition") or {}).get("interaction", "full")
    full = interaction == "full"
    current_yaw = float(world.get("initial_yaw", 0.0))
    step = float(world.get("rotation_step_degrees", 15.0))
    completed = {_edge(edge[0], edge[1]) for edge in world.get("connections") or []}
    stage = page.locator(".fl-stage")

    page.screenshot(path=str(out_dir / f"{mechanic}-initial.png"), full_page=True)
    for raw_edge in truth["required_connections"]:
        edge = _edge(raw_edge[0], raw_edge[1])
        if edge in completed:
            continue
        first, second = vertices[edge[0]], vertices[edge[1]]
        target = _target_yaw(first, second, world, step=step if not full else None)
        current_yaw = _rotate_full(page, stage, current_yaw, target) if full else _rotate_simplified(page, current_yaw, target, step)
        _connect(page, edge[0])
        _connect(page, edge[1])
        completed.add(edge)
        page.screenshot(path=str(out_dir / f"{mechanic}-edge-{len(completed):02d}.png"), full_page=True)
    expect(page.locator(".fl-complete-count")).to_have_text(str(len(truth["targets"])))
    page.locator(".fl-submit").click()
    expect(page.locator(".fl-readout")).to_have_attribute("data-status", "passed", timeout=15000)
    page.screenshot(path=str(out_dir / f"{mechanic}-pass.png"), full_page=True)
