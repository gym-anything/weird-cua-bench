from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, evidence_dir: Path, mechanic: str, name: str) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(evidence_dir / f"{mechanic}-{name}.png"), full_page=True)


def _canvas_point(box: dict, x: float, y: float) -> tuple[float, float]:
    return (
        float(box["x"]) + x * float(box["width"]) / 720,
        float(box["y"]) + y * float(box["height"]) / 410,
    )


def fail_once(page, _state_dir: Path, evidence_dir: Path, mechanic: str) -> None:
    _shot(page, evidence_dir, mechanic, "initial")
    page.locator("#domino-run").click()
    page.wait_for_function("dominoModel.mode === 'result'", timeout=11_000)
    expect(page.locator(".domino-verdict")).to_contain_text("PHYSICS FAIL")
    _shot(page, evidence_dir, mechanic, "failure")
    page.locator("#domino-reset").click()
    expect(page.locator(".domino-trace")).to_contain_text("PHYSICS READY")
    _shot(page, evidence_dir, mechanic, "recovered")


def _place_domino(page, box: dict, domino_id: str, target: dict, interaction: str) -> None:
    position = page.evaluate(
        "id => ({x: dominoModel.bodiesById[id].position.x, y: dominoModel.bodiesById[id].position.y})",
        domino_id,
    )
    start = _canvas_point(box, float(position["x"]), float(position["y"]))
    end = _canvas_point(box, float(target["x"]), float(target["y"]))
    if interaction == "simplified":
        page.mouse.click(*start)
        page.mouse.click(*end)
    else:
        page.mouse.move(*start)
        page.mouse.down()
        page.mouse.move(*end, steps=10)
        page.mouse.up()

    for _ in range(14):
        axis_angle = float(
            page.evaluate(
                "id => dominoAxisAngle(dominoModel.bodiesById[id].angle * 180 / Math.PI)",
                domino_id,
            )
        )
        if abs(axis_angle) <= 8:
            return
        page.locator("#domino-rotate-right").click()
    raise AssertionError(f"could not level domino {domino_id}")


def solve(page, state_dir: Path, evidence_dir: Path, mechanic: str) -> None:
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    canvas = page.locator(".domino-physics-canvas")
    box = canvas.bounding_box()
    if not box:
        raise AssertionError("domino physics canvas has no visible bounds")

    for index, (domino_id, target) in enumerate(zip(truth["loose_ids"], truth["target_slots"])):
        _place_domino(page, box, str(domino_id), target, interaction)
        if index == 0:
            page.locator("#domino-flip").click()

    page.locator("#domino-run").click()
    page.wait_for_timeout(750)
    _shot(page, evidence_dir, mechanic, "active-simulation")
    try:
        page.wait_for_function("dominoModel.physicsPassed === true", timeout=11_000)
    except Exception as exc:
        debug = page.evaluate(
            """() => ({
                mode: dominoModel.mode,
                bellHit: dominoModel.bellHit,
                bellPeakAngle: dominoModel.bellPeakAngle,
                pairs: Array.from(dominoModel.collisionPairs),
                sources: dominoModel.placementSources,
                bodies: Object.fromEntries(dominoModel.dominoIds.map(id => {
                    const body = dominoModel.bodiesById[id];
                    return [id, {x: body.position.x, y: body.position.y, angle: body.angle}];
                })),
            })"""
        )
        _shot(page, evidence_dir, mechanic, "physics-failure")
        raise AssertionError(f"domino chain did not reach the bell: {debug}") from exc
    page.wait_for_function(
        "minimum => dominoModel.bellPeakAngle >= minimum",
        arg=float(truth["minimum_bell_swing_radians"]),
        timeout=4_000,
    )
    _shot(page, evidence_dir, mechanic, "bell-impact")
    page.wait_for_function("dominoModel.mode === 'result'", timeout=11_000)
    expect(page.locator(".domino-verdict")).to_contain_text("PHYSICS PASS")
    expect(page.locator("#domino-submit")).to_be_enabled()
    page.locator("#domino-submit").click()
    expect(page.locator(".readout")).to_have_attribute("data-status", "passed", timeout=8_000)
    _shot(page, evidence_dir, mechanic, "pass")
