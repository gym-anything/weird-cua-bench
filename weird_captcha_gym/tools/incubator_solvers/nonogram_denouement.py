from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MECHANIC_ID = "nonogram_denouement"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _bundle(state_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    public = _load_json(state_dir / "public_state.json")
    truth = _load_json(state_dir / "ground_truth.json")
    return public, truth


def _cell_center(page, row: int, col: int) -> tuple[float, float]:
    box = page.locator(f'[data-cell="{row}:{col}"]').bounding_box()
    if box is None:
        raise AssertionError(f"missing visible cell {row}:{col}")
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def _full_stroke(page, row: int, start_col: int, end_col: int, value: int) -> None:
    start = _cell_center(page, row, start_col)
    end = _cell_center(page, row, end_col)
    button = "left" if value == 1 else "right"
    page.mouse.move(*start)
    page.mouse.down(button=button)
    page.mouse.move(*end, steps=max(2, abs(end_col - start_col) * 2 + 1))
    page.mouse.up(button=button)


def _paint_full(page, solution: list[list[int]]) -> None:
    for row_index, row in enumerate(solution):
        start = 0
        while start < len(row):
            value = 1 if row[start] else -1
            end = start
            while end + 1 < len(row) and (1 if row[end + 1] else -1) == value:
                end += 1
            _full_stroke(page, row_index, start, end, value)
            start = end + 1


def _paint_simplified(page, solution: list[list[int]]) -> None:
    for row_index, row in enumerate(solution):
        for col_index, cell in enumerate(row):
            page.locator(f'[data-cell="{row_index}:{col_index}"]').click()
            mode = "ink" if cell else "clear"
            page.locator(f'[data-proxy-mark="{mode}"]').click()


def _paint(page, solution: list[list[int]], interaction: str) -> None:
    if interaction == "full":
        _paint_full(page, solution)
    elif interaction == "simplified":
        _paint_simplified(page, solution)
    else:
        raise AssertionError(f"unexpected interaction {interaction!r}")
    develop = page.locator("[data-develop]")
    if not develop.is_enabled():
        raise AssertionError("clue-correct plate did not enable development")
    develop.click()
    page.locator(".nd-theatre-panel.is-developed").wait_for(state="visible")


def _answer(page, direction: str, interaction: str) -> None:
    if interaction == "simplified":
        page.locator(f'[data-answer-proxy="{direction}"]').click()
        return
    slug = page.locator(f'[data-direction-slug="{direction}"]')
    well = page.locator("[data-answer-well]")
    slug_box = slug.bounding_box()
    well_box = well.bounding_box()
    if slug_box is None or well_box is None:
        raise AssertionError("answer slug or answer well is not visible")
    start = (slug_box["x"] + slug_box["width"] / 2, slug_box["y"] + slug_box["height"] / 2)
    end = (well_box["x"] + well_box["width"] / 2, well_box["y"] + well_box["height"] / 2)
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move(*end, steps=7)
    page.mouse.up()


def _solve_current(page, state_dir: Path, *, wrong_answer: bool, certify: bool) -> None:
    public, truth = _bundle(state_dir)
    interaction = (public.get("control_condition") or {}).get("interaction") or "full"
    _paint(page, truth["solution"], interaction)
    direction = truth["correct_direction"]
    if wrong_answer:
        direction = next(option for option in public["puzzle"]["answer_options"] if option != direction)
    _answer(page, direction, interaction)
    if certify:
        page.locator("[data-certify]").click()


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    del out_dir
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    _solve_current(page, state_dir, wrong_answer=True, certify=True)
    page.locator(".nd-verdict.is-fail").wait_for(state="visible")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str, *, certify: bool = True) -> None:
    del out_dir
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    _solve_current(page, state_dir, wrong_answer=False, certify=certify)
    if certify:
        page.locator(".nd-verdict.is-pass").wait_for(state="visible")
