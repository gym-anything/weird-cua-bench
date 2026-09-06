from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MECHANIC_ID = "crackglaze_crossing"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _direction(cells: dict[str, dict[str, Any]], origin: str, destination: str) -> str:
    first, second = cells[origin], cells[destination]
    delta = (int(second["row"]) - int(first["row"]), int(second["column"]) - int(first["column"]))
    return {(-1, 0): "up", (1, 0): "down", (0, -1): "left", (0, 1): "right"}[delta]


def _step(page, state: dict[str, Any], origin: str, destination: str) -> None:
    interaction = str((state.get("control_condition") or {}).get("interaction") or "full")
    if interaction == "full":
        page.locator(f'[data-cell-id="{destination}"]').click()
    else:
        cells = {cell["id"]: cell for cell in state["cells"]}
        page.locator(f'[data-direction="{_direction(cells, origin, destination)}"]').click()


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    state = _read(state_dir / "public_state.json")
    original = state["challenge_id"]
    cells = {cell["id"]: cell for cell in state["cells"]}
    fuses = {cell_id: int(state["fuse_lengths"][cell["glaze"]]) for cell_id, cell in cells.items()}
    position = state["start_id"]
    neighbor = state["neighbors"][position][0]
    lit_at: dict[str, int] = {}
    step = 0
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / "failure-before-bounce.png"))
    for _ in range(max(fuses.values()) * 3):
        destination = neighbor if position != neighbor else state["start_id"]
        next_step = step + 1
        lit_at.setdefault(position, next_step)
        expired = destination in lit_at and next_step - lit_at[destination] >= fuses[destination]
        _step(page, state, position, destination)
        step = next_step
        if expired:
            page.locator(".crack-fresh-failure").wait_for(state="visible")
            current = page.locator(".crackglaze-crossing").get_attribute("data-challenge-id")
            if current == original:
                raise AssertionError("failed floor did not receive a fresh challenge")
            page.screenshot(path=str(out_dir / "failure-fresh-attempt.png"))
            return
        position = destination
    raise AssertionError("bounce route did not reach an expired tile")


def solve(
    page,
    state_dir: Path,
    out_dir: Path,
    mechanic: str,
    *,
    certify: bool = True,
    start_index: int = 0,
    capture_initial: bool = True,
) -> None:
    del certify
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    state = _read(state_dir / "public_state.json")
    truth = _read(state_dir / "ground_truth.json")
    path = list(truth["certified_solution"])
    gallery = {cell["id"] for cell in state["cells"] if cell["under_gallery"]}
    cells = {cell["id"]: cell for cell in state["cells"]}
    divergence = int(truth["search_certificate"]["counterfactual"]["first_route_divergence"])
    out_dir.mkdir(parents=True, exist_ok=True)
    if capture_initial:
        page.screenshot(path=str(out_dir / "initial.png"))
    crack_captured = False
    gallery_captured = False
    calibration_captured = False
    decision_captured = False
    pairs = list(zip(path, path[1:]))
    for index, (origin, destination) in enumerate(pairs[start_index:], start_index + 1):
        if not decision_captured and index == divergence:
            page.screenshot(path=str(out_dir / "decision-point.png"))
            decision_captured = True
        _step(page, state, origin, destination)
        if not crack_captured and index >= 5:
            page.screenshot(path=str(out_dir / "crack-progression.png"))
            crack_captured = True
        if not calibration_captured and cells[destination]["row"] >= 4:
            page.screenshot(path=str(out_dir / "calibration-complete.png"))
            calibration_captured = True
        if not gallery_captured and destination in gallery:
            page.screenshot(path=str(out_dir / "dark-gallery-traversal.png"))
            gallery_captured = True
    page.locator('.readout[data-status="passed"]').wait_for(state="visible")
    page.locator('.crackglaze-crossing[data-terminal="passed"]').wait_for(state="visible")
    page.screenshot(path=str(out_dir / "passed.png"))
