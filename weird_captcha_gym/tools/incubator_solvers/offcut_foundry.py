"""Oracle browser driver for Offcut Foundry wiring and evidence capture."""
from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "offcut_foundry"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _click(page, selector: str) -> None:
    locator = page.locator(selector)
    box = locator.bounding_box()
    assert box is not None, selector
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def _center(page, selector: str) -> tuple[float, float]:
    box = page.locator(selector).bounding_box()
    assert box is not None, selector
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def _trace(page, cells: list[str]) -> None:
    assert cells
    first_x, first_y = _center(page, f'[data-cell="{cells[0]}"]')
    page.mouse.move(first_x, first_y)
    page.mouse.down()
    for cell_id in cells[1:]:
        x, y = _center(page, f'[data-cell="{cell_id}"]')
        page.mouse.move(x, y, steps=2)
    page.mouse.up()


def solution_order(truth: dict) -> list[dict]:
    placements = truth["placements"]
    return [
        {"piece_id": piece["id"], "cells": list(placements[piece["id"]])}
        for piece in truth["pieces"]
    ]


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = _read(state_dir / "public_state.json")["challenge_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / "offcut-failure-before-cuts.png"))
    _click(page, "#of-certify")
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        current = _read(state_dir / "public_state.json").get("challenge_id")
        if current and current != before:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("failed Offcut Foundry certification did not generate a fresh challenge")
    expect(page.locator(".offcut-shell")).to_be_visible()
    page.screenshot(path=str(out_dir / "offcut-failure-fresh-stock.png"))


def solve(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID, *, film: bool = False) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    public = _read(state_dir / "public_state.json")
    truth = _read(state_dir / "ground_truth.json")
    interaction = (public.get("control_condition") or {}).get("interaction", public.get("interaction", "full"))
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / "offcut-initial.png"))
    for index, item in enumerate(solution_order(truth), start=1):
        if interaction == "simplified":
            _click(page, f'[data-piece="{item["piece_id"]}"]')
            for cell_id in item["cells"]:
                _click(page, f'[data-cell="{cell_id}"]')
            _click(page, "#of-extract")
        else:
            _trace(page, item["cells"])
        if index == max(1, len(truth["pieces"]) // 2):
            page.screenshot(path=str(out_dir / "offcut-mid-partition.png"))
    page.screenshot(path=str(out_dir / "offcut-ready-to-certify.png"))
    _click(page, "#of-certify")
    expect(page.locator(".readout")).to_have_attribute("data-status", "passed", timeout=8_000)
    expect(page.locator(".readout")).to_contain_text("PASS")
    page.screenshot(path=str(out_dir / "offcut-pass.png"))
