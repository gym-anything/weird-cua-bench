from __future__ import annotations

import json
import heapq
import math
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "one_stroke_atelier"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _box(page) -> dict:
    stage = page.locator(".atelier-stage")
    value = stage.bounding_box()
    if not value:
        raise AssertionError("atelier stage is not visible")
    client = stage.evaluate("element => ({left: element.clientLeft, top: element.clientTop, width: element.clientWidth, height: element.clientHeight})")
    return {"x": value["x"] + client["left"], "y": value["y"] + client["top"], "width": client["width"], "height": client["height"]}


def _screen(box: dict, stage: dict, point: list[float]) -> tuple[float, float]:
    return box["x"] + point[0] / stage["width"] * box["width"], box["y"] + point[1] / stage["height"] * box["height"]


def _gate_key(phase: int, prefix: list[str]) -> str:
    return f"{phase}|{'/'.join(prefix)}"


def _target_map(truth: dict) -> dict[str, str]:
    return {item["field"]: item["value"] for item in truth["target"]}


def _gate(truth: dict, phase: int, prefix: list[str], wrong: bool = False) -> dict:
    field = truth["active_fields"][phase]
    target = _target_map(truth)[field]
    gates = truth["gate_sets"][_gate_key(phase, prefix)]
    return next(item for item in gates if (item["value"] != target if wrong else item["value"] == target))


def _move(page, box: dict, stage: dict, point: list[float]) -> None:
    page.mouse.move(*_screen(box, stage, point), steps=3)


def _advance(page, box: dict, stage: dict, point: list[float], *, proxy: bool) -> None:
    if proxy:
        page.mouse.click(*_screen(box, stage, point))
    else:
        _move(page, box, stage, point)


def _hit_half_length(gate: dict) -> float:
    return float(gate.get("hit_half_length", gate["half_length"] + gate["tolerance"]))


def _segment_hits_bar(first: list[float], second: list[float], gate: dict) -> bool:
    x, y = (float(item) for item in gate["center"])
    along = _hit_half_length(gate)
    half_x, half_y = (9.0, along) if gate["orientation"] == "vertical" else (along, 9.0)
    bounds = ((x - half_x, x + half_x), (y - half_y, y + half_y))
    delta = (second[0] - first[0], second[1] - first[1])
    low, high = 0.0, 1.0
    for axis in range(2):
        if abs(delta[axis]) < 1e-9:
            if not bounds[axis][0] <= first[axis] <= bounds[axis][1]:
                return False
            continue
        enter = (bounds[axis][0] - first[axis]) / delta[axis]
        leave = (bounds[axis][1] - first[axis]) / delta[axis]
        if enter > leave:
            enter, leave = leave, enter
        low, high = max(low, enter), min(high, leave)
        if low > high:
            return False
    return True


def _route_around(start: list[float], goal: list[float], barriers: list[dict], stage: dict) -> list[list[float]]:
    if not any(_segment_hits_bar(start, goal, gate) for gate in barriers):
        return [list(start), list(goal)]
    inset, margin = 14.0, 13.0
    width, height = float(stage["width"]), float(stage["height"])
    candidates: list[list[float]] = [list(start), list(goal), [inset, inset], [width - inset, inset], [inset, height - inset], [width - inset, height - inset]]
    for gate in barriers:
        x, y = (float(item) for item in gate["center"])
        along = _hit_half_length(gate)
        if gate["orientation"] == "vertical":
            candidates.extend([[x - margin, y - along - margin], [x + margin, y - along - margin], [x - margin, y + along + margin], [x + margin, y + along + margin]])
        else:
            candidates.extend([[x - along - margin, y - margin], [x - along - margin, y + margin], [x + along + margin, y - margin], [x + along + margin, y + margin]])
    nodes: list[list[float]] = []
    seen: set[tuple[float, float]] = set()
    for index, point in enumerate(candidates):
        clamped = list(point) if index < 2 else [max(inset, min(width - inset, point[0])), max(inset, min(height - inset, point[1]))]
        token = (round(clamped[0], 3), round(clamped[1], 3))
        if token not in seen and not any(_segment_hits_bar(clamped, clamped, gate) for gate in barriers):
            seen.add(token)
            nodes.append(clamped)
    start_index, goal_index = nodes.index(list(start)), nodes.index(list(goal))
    graph: list[list[tuple[int, float]]] = [[] for _ in nodes]
    for first_index, first in enumerate(nodes):
        for second_index in range(first_index + 1, len(nodes)):
            second = nodes[second_index]
            if any(_segment_hits_bar(first, second, gate) for gate in barriers):
                continue
            weight = math.hypot(second[0] - first[0], second[1] - first[1])
            graph[first_index].append((second_index, weight))
            graph[second_index].append((first_index, weight))
    distances = [math.inf] * len(nodes)
    previous: list[int | None] = [None] * len(nodes)
    distances[start_index] = 0.0
    queue = [(0.0, start_index)]
    while queue:
        total, node = heapq.heappop(queue)
        if total != distances[node]:
            continue
        if node == goal_index:
            break
        for neighbor, weight in graph[node]:
            candidate = total + weight
            if candidate < distances[neighbor]:
                distances[neighbor], previous[neighbor] = candidate, node
                heapq.heappush(queue, (candidate, neighbor))
    if not math.isfinite(distances[goal_index]):
        raise AssertionError("generated atelier barrier layout has no visible route")
    route: list[list[float]] = []
    node: int | None = goal_index
    while node is not None:
        route.append(nodes[node])
        node = previous[node]
    return list(reversed(route))


def _cross_full(
    page,
    box: dict,
    stage: dict,
    current: list[float],
    gate: dict,
    current_gates: list[dict],
    locked_gates: list[dict],
    *,
    proxy: bool,
) -> list[float]:
    x, y = gate["center"]
    if gate["orientation"] == "vertical":
        before = [x - 34, y] if gate["direction"] == "right" else [x + 34, y]
        after = [x + 34, y] if gate["direction"] == "right" else [x - 34, y]
    else:
        before = [x, y - 34] if gate["direction"] == "down" else [x, y + 34]
        after = [x, y + 34] if gate["direction"] == "down" else [x, y - 34]
    for waypoint in _route_around(current, before, [*locked_gates, *current_gates], stage)[1:]:
        _advance(page, box, stage, waypoint, proxy=proxy)
    _advance(page, box, stage, after, proxy=proxy)
    return after


def _perform(page, truth: dict, *, wrong_first: bool = False, screenshot: Path | None = None) -> None:
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    prefix: list[str] = []
    locked_gates: list[dict] = []
    box, stage = _box(page), truth["stage"]
    current = list(truth["start"])
    if interaction == "simplified":
        page.locator(".atelier-proxy-start").click()
    else:
        page.mouse.move(*_screen(box, stage, current))
        page.mouse.down()
    for phase in range(len(truth["active_fields"])):
        gate = _gate(truth, phase, prefix, wrong=wrong_first and phase == 0)
        gates = truth["gate_sets"][_gate_key(phase, prefix)]
        current = _cross_full(page, box, stage, current, gate, gates, locked_gates, proxy=interaction == "simplified")
        prefix.append(gate["value"])
        memory = int(truth.get("locked_gate_memory") or 0)
        if memory:
            locked_gates.append(gate)
            locked_gates = locked_gates[-memory:]
        page.wait_for_timeout(90)
        if screenshot and phase == 1:
            page.screenshot(path=str(screenshot))
    motif = truth["motif"]["points"]
    for waypoint in _route_around(current, motif[0], locked_gates, stage)[1:]:
        _advance(page, box, stage, waypoint, proxy=interaction == "simplified")
        current = list(waypoint)
    for point in motif[1:]:
        _advance(page, box, stage, point, proxy=interaction == "simplified")
        current = list(point)
        page.wait_for_timeout(70)
    if interaction == "simplified":
        page.locator(".atelier-proxy-end").click()
    else:
        page.mouse.up()


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    out_dir.mkdir(parents=True, exist_ok=True)
    _perform(page, truth, screenshot=out_dir / f"{mechanic}-mid-stroke-reconfiguration.png")
    expect(page.locator('.atelier-shell[data-complete="true"]')).to_be_visible()
    page.screenshot(path=str(out_dir / f"{mechanic}-completed-before-certify.png"))
    page.locator(".atelier-submit").click()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=8_000)
    page.screenshot(path=str(out_dir / f"{mechanic}-pass.png"))


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = _read(state_dir / "ground_truth.json")["challenge_id"]
    _perform(page, _read(state_dir / "ground_truth.json"), wrong_first=True)
    page.locator(".atelier-submit").click()
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        current = _read(state_dir / "ground_truth.json")["challenge_id"]
        if current != before:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("failed atelier submission did not generate a fresh challenge")
    expect(page.locator('.atelier-shell[data-fresh-failure="true"]')).to_be_visible()
    expect(page.locator(".readout")).to_contain_text("FAIL")
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-fail-refresh.png"))
