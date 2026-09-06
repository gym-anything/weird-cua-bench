from __future__ import annotations

import json
import math
import time
from pathlib import Path


MECHANIC_ID = "leaning_tower_of_panels"
WIDTH = 880.0
HEIGHT = 540.0


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _states(state_dir: Path) -> tuple[dict, dict]:
    return _read(state_dir / "public_state.json"), _read(state_dir / "ground_truth.json")


def _interaction(public: dict) -> str:
    return str((public.get("control_condition") or {}).get("interaction") or "simplified")


def _mod(value: int, size: int) -> int:
    return value % size


def _wrap_angle(value: float) -> float:
    return (value + math.pi) % (math.pi * 2) - math.pi


def _neighbors(blank: int, rows: int, sectors: int) -> list[int]:
    row, sector = divmod(blank, sectors)
    result = [row * sectors + (sector - 1) % sectors, row * sectors + (sector + 1) % sectors]
    if row:
        result.append((row - 1) * sectors + sector)
    if row + 1 < rows:
        result.append((row + 1) * sectors + sector)
    return list(dict.fromkeys(result))


def _canvas_box(page) -> dict:
    box = page.locator("#ltp-stage").bounding_box()
    if box is None:
        raise AssertionError("leaning-tower canvas is not visible")
    return box


def _screen(box: dict, point: tuple[float, float]) -> tuple[float, float]:
    return (
        box["x"] + point[0] / WIDTH * box["width"],
        box["y"] + point[1] / HEIGHT * box["height"],
    )


def _cell_center(public: dict, grid: list, index: int, view: int) -> tuple[float, float]:
    rows = int(public["floor_count"])
    sectors = int(public["sector_count"])
    row, sector = divmod(index, sectors)
    angle = _wrap_angle((sector - view) * math.pi * 2 / sectors)
    half_panel = math.tau / sectors * 0.47
    aligned = sum(
        item is not None and item == f"panel-{cell // sectors + 1}-{cell % sectors + 1}"
        for cell, item in enumerate(grid)
    )
    lean = 28 * (1 - aligned / (rows * sectors - 1))
    lean_top = -lean * (1 - row / max(1, rows))
    lean_bottom = -lean * (1 - (row + 1) / max(1, rows))
    x1 = 440 + math.sin(angle - half_panel) * 252 + lean_top
    x2 = 440 + math.sin(angle + half_panel) * 252 + lean_top
    row_height = 414 / rows
    lift = (1 - math.cos(angle)) * 7
    y1 = 68 + row * row_height + lift
    y2 = 68 + (row + 1) * row_height + lift
    bottom_shift = lean_bottom - lean_top
    return ((x1 + x2 + x2 + bottom_shift + x1 + bottom_shift) / 4, (y1 + y1 + y2 + y2) / 4)


def _turn_once(page, interaction: str, delta: int) -> None:
    if interaction == "simplified":
        page.locator("#ltp-turn-right" if delta == 1 else "#ltp-turn-left").click()
    else:
        box = _canvas_box(page)
        start = (170.0, 286.0) if delta == 1 else (70.0, 286.0)
        end = (70.0, 286.0) if delta == 1 else (170.0, 286.0)
        page.mouse.move(*_screen(box, start))
        page.mouse.down()
        page.mouse.move(*_screen(box, end), steps=10)
        page.mouse.up()
    page.wait_for_timeout(35)


def _turn_to(page, interaction: str, current: int, target: int, sectors: int) -> int:
    while current != target:
        clockwise = (target - current) % sectors
        counter = (current - target) % sectors
        delta = 1 if clockwise <= counter else -1
        _turn_once(page, interaction, delta)
        current = (current + delta) % sectors
    return current


def _slide(page, public: dict, grid: list, tile_id: str, view: int) -> None:
    interaction = _interaction(public)
    source = grid.index(tile_id)
    blank = grid.index(None)
    if source not in _neighbors(blank, int(public["floor_count"]), int(public["sector_count"])):
        raise AssertionError(f"private solution requests illegal slide {tile_id}")
    box = _canvas_box(page)
    source_point = _screen(box, _cell_center(public, grid, source, view))
    if interaction == "simplified":
        page.mouse.click(*source_point)
    else:
        target_point = _screen(box, _cell_center(public, grid, blank, view))
        page.mouse.move(*source_point)
        page.mouse.down()
        page.mouse.move(*target_point, steps=12)
        page.mouse.up()
    grid[blank], grid[source] = grid[source], None
    page.wait_for_timeout(35)


def _drive_solution(page, public: dict, truth: dict, out_dir: Path) -> None:
    interaction = _interaction(public)
    sectors = int(public["sector_count"])
    grid = list(public["start_grid"])
    view = 0
    solution = list(truth["optimal_solution"])
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / "leaning-tower-initial.png"))
    for move_number, tile_id in enumerate(solution, start=1):
        source = grid.index(tile_id)
        target_view = source % sectors
        view = _turn_to(page, interaction, view, target_view, sectors)
        if move_number == 1:
            page.screenshot(path=str(out_dir / "leaning-tower-rotated-view.png"))
        _slide(page, public, grid, tile_id, view)
        if move_number == max(1, len(solution) // 2):
            page.screenshot(path=str(out_dir / "leaning-tower-mid-solve.png"))
    if grid != truth["goal_grid"]:
        raise AssertionError("visible-input solution did not reach the target grid")
    page.screenshot(path=str(out_dir / "leaning-tower-solved-before-certify.png"))


def _wait_new_challenge(state_dir: Path, old: str) -> None:
    deadline = time.time() + 12
    while time.time() < deadline:
        try:
            current = str(_read(state_dir / "public_state.json").get("challenge_id") or "")
        except (FileNotFoundError, json.JSONDecodeError):
            current = old
        if current and current != old:
            return
        time.sleep(0.04)
    raise AssertionError("failed tower certification did not issue a fresh challenge")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    public, _truth = _states(state_dir)
    old = public["challenge_id"]
    page.locator("#ltp-certify").click()
    page.locator(".ltp-verdict.is-fail").wait_for(state="visible")
    page.screenshot(path=str(out_dir / "leaning-tower-failed.png"))
    _wait_new_challenge(state_dir, old)
    page.locator("#ltp-fresh-retry").click()
    page.wait_for_function("old => window.leaningTowerModel?.state?.challenge_id !== old", arg=old)
    page.screenshot(path=str(out_dir / "leaning-tower-fresh-retry.png"))


def exercise_local_recovery(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    public, _truth = _states(state_dir)
    grid = list(public["start_grid"])
    blank = grid.index(None)
    source = _neighbors(blank, int(public["floor_count"]), int(public["sector_count"]))[0]
    tile_id = grid[source]
    view = _turn_to(page, _interaction(public), 0, source % int(public["sector_count"]), int(public["sector_count"]))
    _slide(page, public, grid, tile_id, view)
    page.screenshot(path=str(out_dir / "leaning-tower-reversible-wrong-slide.png"))
    page.locator("#ltp-reset").click()
    page.screenshot(path=str(out_dir / "leaning-tower-reset-same-challenge.png"))


def solve(page, state_dir: Path, out_dir: Path, mechanic: str, *, certify: bool = True) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    public, truth = _states(state_dir)
    _drive_solution(page, public, truth, out_dir)
    if certify:
        page.locator("#ltp-certify").click()
        page.locator(".ltp-verdict.is-pass").wait_for(state="visible")
        page.screenshot(path=str(out_dir / "leaning-tower-pass.png"))
