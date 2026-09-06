from __future__ import annotations

import json
import math
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "four_pane_pilgrimage"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, mechanic: str, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{name}.png"), full_page=True)


def _wait_new(state_dir: Path, before: str) -> None:
    deadline = time.time() + 8
    while time.time() < deadline:
        if str(_read(state_dir / "ground_truth.json").get("challenge_id")) != before:
            return
        time.sleep(.05)
    raise AssertionError("pilgrimage challenge did not regenerate")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(mechanic)
    truth = _read(state_dir / "ground_truth.json")
    before = str(truth["challenge_id"])
    page.locator(".fpp-submit").click()
    _wait_new(state_dir, before)
    expect(page.locator(".four-pane-pilgrimage[data-fresh-failure='true']")).to_be_visible(timeout=8_000)
    expect(page.locator(".readout")).to_contain_text("FAIL")
    _shot(page, out_dir, mechanic, "failure-fresh-folio")
    expect(page.locator(".fpp-fresh-stamp")).to_be_hidden(timeout=4_000)


def _drag(page, source, target, steps: int = 14) -> None:
    source_box = source.bounding_box()
    target_box = target.bounding_box()
    if not source_box or not target_box:
        raise AssertionError("visible drag endpoints are unavailable")
    start = (source_box["x"] + source_box["width"] / 2, source_box["y"] + source_box["height"] / 2)
    end = (target_box["x"] + target_box["width"] / 2, target_box["y"] + target_box["height"] / 2)
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move(*end, steps=steps)
    page.mouse.up()
    page.wait_for_timeout(90)


def _desired_slots(truth: dict) -> list[str]:
    desired = ["", "", "", ""]
    for route_index, slot in enumerate(truth["route_slots"]):
        desired[int(slot)] = truth["route_panel_ids"][route_index]
    return desired


def _reorder(page, truth: dict, interaction: str) -> None:
    slots = list(truth["initial_slots"])
    desired = _desired_slots(truth)
    for target_slot, wanted in enumerate(desired):
        current_slot = slots.index(wanted)
        if current_slot == target_slot:
            continue
        if interaction == "simplified":
            page.locator(f'[data-select-panel="{wanted}"]').click()
            page.locator(f'[data-move-slot="{target_slot}"]').click()
        else:
            _drag(
                page,
                page.locator(f'.fpp-pane-grip[data-panel-id="{wanted}"]'),
                page.locator(f'.fpp-slot[data-slot="{target_slot}"] .fpp-pane-grip'),
            )
        displaced = slots[target_slot]
        slots[current_slot], slots[target_slot] = displaced, wanted
    rendered = page.evaluate("() => [...window.fourPanePilgrimageModel.slots]")
    if rendered != desired:
        raise AssertionError(f"pane reorder failed: {rendered} != {desired}")


def _proxy_pan(page, panel_id: str, dx: float, dy: float, step: float) -> None:
    page.locator(f'[data-select-panel="{panel_id}"]').click()
    horizontal = "1,0" if dx > 0 else "-1,0"
    vertical = "0,1" if dy > 0 else "0,-1"
    for _ in range(round(abs(dx) / step)):
        page.locator(f'[data-pan="{horizontal}"]').click()
    for _ in range(round(abs(dy) / step)):
        page.locator(f'[data-pan="{vertical}"]').click()


def _proxy_zoom(page, panel_id: str, delta: float, step: float) -> None:
    page.locator(f'[data-select-panel="{panel_id}"]').click()
    direction = 1 if delta > 0 else -1
    for _ in range(round(abs(delta) / step)):
        page.locator(f'[data-zoom="{direction}"]').click()


def _clear_canvas_point(
    page,
    panel_id: str,
    dx_units: float = 0,
    dy_units: float = 0,
) -> tuple[float, float, dict]:
    canvas = page.locator(f'.fpp-canvas[data-panel-id="{panel_id}"]')
    box = canvas.bounding_box()
    if not box:
        raise AssertionError(f"pane {panel_id} is not visible")
    candidates = ((.5, .5), (.28, .28), (.72, .28), (.28, .72), (.72, .72), (.16, .5), (.84, .5))
    for fraction_x, fraction_y in candidates:
        end_x = fraction_x + dx_units / 300.0
        end_y = fraction_y + dy_units / 200.0
        if not .06 <= end_x <= .94 or not .06 <= end_y <= .94:
            continue
        x = box["x"] + box["width"] * fraction_x
        y = box["y"] + box["height"] * fraction_y
        owns_point = page.evaluate(
            """({x, y, panel}) => {
              const node = document.elementFromPoint(x, y);
              return node?.closest?.('.fpp-canvas')?.dataset?.panelId === panel;
            }""",
            {"x": x, "y": y, "panel": panel_id},
        )
        if owns_point:
            return x, y, box
    raise AssertionError(f"pane {panel_id} has no unobstructed direct-manipulation point")


def _direct_pan(page, panel_id: str, dx: float, dy: float) -> None:
    # Keep each physical gesture inside the pane. Sparse pointer delivery is
    # still exercised because every segment is replayed from its visible start.
    remaining_x, remaining_y = dx, dy
    while abs(remaining_x) > .01 or abs(remaining_y) > .01:
        part_x = max(-70.0, min(70.0, remaining_x))
        part_y = max(-55.0, min(55.0, remaining_y))
        start_x, start_y, box = _clear_canvas_point(page, panel_id, part_x, part_y)
        end_x = start_x + part_x / 300.0 * box["width"]
        end_y = start_y + part_y / 200.0 * box["height"]
        page.mouse.move(start_x, start_y)
        page.mouse.down()
        page.mouse.move(end_x, end_y, steps=12)
        page.mouse.up()
        page.wait_for_timeout(55)
        remaining_x -= part_x
        remaining_y -= part_y


def _direct_zoom(page, panel_id: str, delta: float, step: float) -> None:
    direction = -120 if delta > 0 else 120
    for _ in range(round(abs(delta) / step)):
        x, y, _box = _clear_canvas_point(page, panel_id)
        page.mouse.move(x, y)
        page.mouse.wheel(0, direction)
        page.wait_for_timeout(55)


def _align(page, truth: dict, interaction: str) -> None:
    step = float(truth["limits"]["pan_step"])
    zoom_step = float(truth["limits"]["zoom_step"])
    current = json.loads(json.dumps(truth["initial_transforms"]))
    for panel_id in truth["route_panel_ids"]:
        target = truth["solution_transforms"][panel_id]
        transform = current[panel_id]
        zoom_delta = round(float(target["zoom"]) - float(transform["zoom"]), 3)
        if abs(zoom_delta) > .001:
            if interaction == "simplified":
                _proxy_zoom(page, panel_id, zoom_delta, zoom_step)
            else:
                _direct_zoom(page, panel_id, zoom_delta, zoom_step)
            transform["zoom"] = target["zoom"]
        dx = float(target["pan_x"]) - float(transform["pan_x"])
        dy = float(target["pan_y"]) - float(transform["pan_y"])
        if abs(dx) > .01 or abs(dy) > .01:
            if interaction == "simplified":
                _proxy_pan(page, panel_id, dx, dy, step)
            else:
                _direct_pan(page, panel_id, dx, dy)
            transform["pan_x"] = target["pan_x"]
            transform["pan_y"] = target["pan_y"]


def _place_plate(page, plate: dict, target_panel_id: str, interaction: str) -> None:
    plate_id = plate["id"]
    if interaction == "simplified":
        page.locator(f'[data-proxy-peel="{plate_id}"]').click()
        page.locator(f'[data-proxy-stack="{plate_id}"][data-target-panel="{target_panel_id}"]').click()
    else:
        _drag(page, page.locator(f'.fpp-bound-plate[data-plate-id="{plate_id}"]'), page.locator(".fpp-layer-tray"))
        _drag(
            page,
            page.locator(f'.fpp-loose-plate[data-plate-id="{plate_id}"]'),
            page.locator(f'.fpp-aperture-target[data-plate-target="{plate_id}"][data-target-panel="{target_panel_id}"]'),
        )


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(mechanic)
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    _shot(page, out_dir, mechanic, f"initial-{interaction}")
    _reorder(page, truth, interaction)
    _align(page, truth, interaction)
    _shot(page, out_dir, mechanic, f"aligned-{interaction}")

    plates = {plate["id"]: plate for plate in truth["plates"]}
    for stage, join in enumerate(truth["joins"]):
        page.wait_for_function("expected => window.fourPanePilgrimageModel.stage >= expected", arg=stage)
        plate_id = join.get("required_plate_id")
        if plate_id:
            _place_plate(page, plates[plate_id], join["target_panel_id"], interaction)
            page.wait_for_timeout(160)
            _shot(page, out_dir, mechanic, f"crossing-{stage + 1}-{interaction}")
        page.wait_for_function("expected => window.fourPanePilgrimageModel.stage > expected", arg=stage, timeout=4_000)
        page.wait_for_timeout(580)

    page.wait_for_function("() => window.fourPanePilgrimageModel.stage === 3 && !window.fourPanePilgrimageModel.walking", timeout=5_000)
    state = page.evaluate("() => ({stage:window.fourPanePilgrimageModel.stage,events:window.fourPanePilgrimageModel.events,final:window.fourPanePilgrimageModel.transforms,slots:window.fourPanePilgrimageModel.slots})")
    if state["stage"] != 3 or state["slots"] != _desired_slots(truth):
        raise AssertionError(f"visible pilgrimage did not reach the shrine: {state}")
    expected_transforms = truth["solution_transforms"]
    for panel_id, expected in expected_transforms.items():
        actual = state["final"][panel_id]
        if any(not math.isclose(float(actual[key]), float(expected[key]), abs_tol=.03) for key in ("zoom", "pan_x", "pan_y")):
            raise AssertionError(f"pane {panel_id} transform mismatch: {actual} != {expected}")
    _shot(page, out_dir, mechanic, f"solved-before-seal-{interaction}")
    page.locator(".fpp-submit").click()
    expect(page.locator(".fpp-verdict strong")).to_have_text("PASS", timeout=8_000)
    expect(page.locator(".readout")).to_have_text("PASS")
    _shot(page, out_dir, mechanic, f"pass-{interaction}")
