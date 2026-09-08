"""Ordinary-input browser solver for Ember Mosaic evidence.

The solver reads seeded truth only to choose generated gate coordinates. It
also watches the visible fire front near the public oil pockets and selects
water when that live state requires cooling. All state changes are produced by
visible palette, canvas, and stamp controls.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable


MECHANIC_ID = "ember_mosaic"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _wait(page, expression: str, arg: Any = None, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if page.evaluate(expression, arg):
            return
        time.sleep(0.05)
    raise AssertionError(f"visible Ember Mosaic state did not arrive: {expression}")


def _mode(state: dict[str, Any]) -> str:
    return str((state.get("control_condition") or {}).get("interaction") or "full")


def _choose(page, material: str) -> None:
    page.locator(f'[data-material="{material}"]').click()


def _canvas_point(page, state: dict[str, Any], x: int, y: int) -> tuple[float, float]:
    box = page.locator("#em-canvas").bounding_box()
    if not box:
        raise AssertionError("Ember Mosaic canvas has no visible bounding box")
    width, height = int(state["width"]), int(state["height"])
    return box["x"] + (x + 0.5) * box["width"] / width, box["y"] + (y + 0.5) * box["height"] / height


def _brush(page, state: dict[str, Any], x: int, y: int, material: str) -> None:
    _choose(page, material)
    if _mode(state) == "simplified":
        page.locator("#em-x").fill(str(x))
        page.locator("#em-y").fill(str(y))
        page.locator("#em-stamp").click()
        return
    px, py = _canvas_point(page, state, x, y)
    page.mouse.move(px, py)
    page.mouse.down()
    page.mouse.up()


def _stats(page) -> dict[str, Any]:
    return page.evaluate(
        """() => ({
          tick: window.emberMosaicModel?.tick ?? -1,
          burned: window.emberMosaicModel?.burned?.size ?? 0,
          target: window.emberMosaicModel?.targetCells?.size ?? 0,
          oil: Boolean(window.emberMosaicModel?.oilIgnited),
          warm: (window.emberMosaicModel?.oilHeat || []).some((value) => value > 0),
          hot_fires: (() => {
            const model = window.emberMosaicModel;
            if (!model) return [];
            const oil = new Set((model.state?.oil_pockets || []).flatMap((pocket) => pocket.cells || []));
            const fires = new Set();
            for (const oilCell of oil) {
              const x = oilCell % model.width, y = Math.floor(oilCell / model.width);
              for (const [dx, dy] of [[0, -1], [0, 1], [-1, 0], [1, 0]]) {
                const nx = x + dx, ny = y + dy;
                if (nx >= 0 && nx < model.width && ny >= 0 && ny < model.height) {
                  const neighbour = ny * model.width + nx;
                  if (model.grid[neighbour] === "f") fires.add(neighbour);
                }
              }
            }
            return Array.from(fires);
          })(),
          gates: (window.emberMosaicModel?.state?.gate_cells || []).map((cell) => window.emberMosaicModel.grid[cell]),
        })"""
    )


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = _read(state_dir / "ground_truth.json")["challenge_id"]
    page.locator("#em-submit").click()
    _wait(page, "() => document.querySelector('.ember-mosaic') && document.querySelector('#em-burned')?.textContent === '0/0' || document.querySelector('.ember-mosaic')", timeout=8)
    page.screenshot(path=str(out_dir / "ember_mosaic-failed-refresh.png"), full_page=True)
    after = _read(state_dir / "ground_truth.json")["challenge_id"]
    if before == after:
        raise AssertionError("Ember Mosaic did not regenerate after a failed certification")


def solve(
    page,
    state_dir: Path,
    out_dir: Path,
    mechanic: str = MECHANIC_ID,
    inspection_delay_ms: int = 100,
    after_action: Callable[[str], None] | None = None,
    before_action: Callable[[str], None] | None = None,
) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    state = _read(state_dir / "public_state.json")
    truth = _read(state_dir / "ground_truth.json")
    if _mode(state) not in {"full", "simplified"}:
        raise AssertionError("invalid Ember Mosaic interaction mode")
    if before_action:
        before_action("active-observation")

    # Repaint the visible gate positions whenever the live model shows that a
    # baffle has eroded.  The coordinates come from the seeded fixture only;
    # the browser still receives normal pointer/stamp actions.
    gates = [int(cell) for cell in truth["gate_cells"]]
    for gate in gates:
        x, y = gate % int(state["width"]), gate // int(state["width"])
        _brush(page, state, x, y, "stone")

    # Make both moving materials visible in the lower basin after protecting
    # the oil.  They are part of the same real grid and do not touch targets.
    basin = state["basin"]
    _brush(page, state, int(basin["x"]) + 1, int(basin["y"]), "water")
    _brush(page, state, int(basin["x"]) + 4, int(basin["y"]), "sand")
    page.wait_for_timeout(inspection_delay_ms)
    page.screenshot(path=str(out_dir / "ember_mosaic-active-flow.png"), full_page=True)
    last_repair_tick = -1
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        stats = _stats(page)
        if stats["oil"]:
            raise AssertionError("Ember Mosaic solver reached an oil ignition")
        # The first oil pocket has a public, ungated branch. Cool the currently
        # adjacent visible flame before the oil heat window expires. This is
        # intentionally a closed-loop choice; a fixed gate sweep cannot do it.
        for fire in stats.get("hot_fires", []):
            if before_action:
                before_action(f"cool-{fire}-{stats['tick']}")
            x, y = int(fire) % int(state["width"]), int(fire) // int(state["width"])
            _brush(page, state, x, y, "water")
            if after_action:
                after_action(f"cool-{fire}-{stats['tick']}")
        if stats["burned"] >= stats["target"] and stats["target"] > 0:
            break
        if stats["tick"] >= 0 and stats["tick"] - last_repair_tick >= 3:
            last_repair_tick = int(stats["tick"])
            for gate in gates:
                if before_action:
                    before_action(f"repair-{gate}-{last_repair_tick}")
                x, y = gate % int(state["width"]), gate // int(state["width"])
                _brush(page, state, x, y, "stone")
                if after_action:
                    after_action(f"repair-{gate}-{last_repair_tick}")
        page.wait_for_timeout(inspection_delay_ms)
    else:
        raise AssertionError(f"Ember Mosaic target did not burn in time: {_stats(page)}")

    page.screenshot(path=str(out_dir / "ember_mosaic-solved-before-certify.png"), full_page=True)
    if before_action:
        before_action("certify")
    page.locator("#em-submit").click()
    if after_action:
        after_action("certify")
    _wait(page, "() => document.querySelector('.readout')?.textContent === 'PASS'", timeout=20)
    page.screenshot(path=str(out_dir / "ember_mosaic-pass.png"), full_page=True)
