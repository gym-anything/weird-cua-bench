from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "tomographic_baggage_surgery"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, mechanic: str, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True); page.screenshot(path=str(out_dir / f"{mechanic}-{name}.png"), full_page=True)


def _wait_new(state_dir: Path, before: str) -> None:
    deadline = time.time() + 8
    while time.time() < deadline:
        if str(_read(state_dir / "ground_truth.json").get("challenge_id")) != before: return
        time.sleep(.05)
    raise AssertionError("tomography challenge did not regenerate")


def _set_offset(page, target: float) -> None:
    target = max(-3.0, min(3.0, round(target / .25) * .25))
    for _ in range(30):
        current = page.evaluate("() => window.tomographicBaggageSurgeryModel.offset")
        if abs(current - target) < .01: return
        page.locator(".tomo-offset[data-delta='.25']" if target > current else ".tomo-offset[data-delta='-.25']").click()
    raise AssertionError("slice offset failed to settle")


def _interaction(truth: dict) -> str:
    return str((truth.get("control_condition") or {}).get("interaction") or "simplified")


def _direct_sweep_x(page, offset: float) -> None:
    canvas = page.locator(".tomo-slice")
    box = canvas.bounding_box()
    if not box:
        raise AssertionError("missing direct tomography canvas")
    center_x, center_y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    target_x = box["x"] + (max(-3.0, min(3.0, offset)) + 3.0) / 6.0 * box["width"]
    page.mouse.move(center_x, center_y)
    page.mouse.down()
    page.mouse.move(target_x, center_y, steps=8)
    page.mouse.up()
    page.wait_for_timeout(35)


def _direct_sweep_y(page, offset: float) -> None:
    canvas = page.locator(".tomo-slice")
    box = canvas.bounding_box()
    if not box:
        raise AssertionError("missing direct tomography canvas")
    # The Y plane has its own visible rail: x=28..492 and y=218..234 in the
    # 520x245 source canvas.  Use that rail rather than the X/Z surface.
    rail_left, rail_width, rail_y = 28, 464, 226
    start_x = box["x"] + (rail_left + rail_width / 24) / 520 * box["width"]
    target_x = box["x"] + (rail_left + (max(-3.0, min(3.0, offset)) + 3.0) / 6.0 * rail_width) / 520 * box["width"]
    target_y = box["y"] + rail_y / 245 * box["height"]
    page.mouse.move(start_x, target_y)
    page.mouse.down()
    page.mouse.move(target_x, target_y, steps=8)
    page.mouse.up()
    page.wait_for_timeout(35)


def _direct_rotate_case(page) -> None:
    canvas = page.locator(".tomo-slice")
    box = canvas.bounding_box()
    if not box:
        raise AssertionError("missing direct tomography canvas")
    handle_x = box["x"] + 470 / 520 * box["width"]
    handle_y = box["y"] + 35 / 245 * box["height"]
    page.mouse.move(handle_x, handle_y)
    page.mouse.down()
    page.mouse.move(handle_x - 12, handle_y + 26, steps=6)
    page.mouse.up()
    page.wait_for_timeout(35)


def _target_x_at_rotation(target: list[float], rotation: int) -> float:
    x, _, z = target
    return (x, z, -x, -z)[rotation % 4]


def _scan_and_lock(page, truth: dict, out_dir: Path | None = None) -> None:
    target = truth["solver"]["target"]
    interaction = _interaction(truth)
    if interaction == "full":
        # A rejected report intentionally paints a brief full-scene FAIL stamp.
        # Direct canvas drags must begin after that visible recovery surface has
        # cleared rather than being delivered to the stamp.
        page.locator(".tomo-fresh").wait_for(state="hidden", timeout=4_000)
    required_rotations = max(
        int(truth["requirements"]["min_rotations"]),
        int(truth["requirements"]["min_target_observations"]),
    )
    # Exercise the shared Y plane on the interaction-specific surface.  This
    # observation is additional evidence; the profile's required hot proof
    # remains the original X/rotation sequence below.
    if interaction == "simplified":
        page.locator(".tomo-axis-buttons button[data-axis='y']").click()
        _set_offset(page, target[1])
    else:
        _direct_sweep_y(page, target[1])
    if out_dir is not None:
        _shot(page, out_dir, MECHANIC_ID, "y-depth-slice")
    if interaction == "simplified":
        page.locator(".tomo-axis-buttons button[data-axis='x']").click(); _set_offset(page, _target_x_at_rotation(target, 0))
    else:
        _direct_sweep_x(page, _target_x_at_rotation(target, 0))
    if out_dir is not None: _shot(page, out_dir, MECHANIC_ID, "hot-slice-orientation-zero")
    if interaction == "simplified":
        _set_offset(page, -2.5)
    else:
        _direct_sweep_x(page, -2.5)
    for rotation in range(1, required_rotations):
        if interaction == "simplified":
            page.locator(".tomo-rotate").click()
            page.locator(".tomo-axis-buttons button[data-axis='x']").click()
            _set_offset(page, _target_x_at_rotation(target, rotation))
        else:
            _direct_rotate_case(page)
            _direct_sweep_x(page, _target_x_at_rotation(target, rotation))
        if rotation == 1 and out_dir is not None:
            _shot(page, out_dir, MECHANIC_ID, "hot-slice-rotated-case")
        if rotation < required_rotations - 1:
            if interaction == "simplified":
                _set_offset(page, 2.5)
            else:
                _direct_sweep_x(page, 2.5)
    if int(truth["requirements"]["min_observations"]) >= 6:
        if interaction == "simplified":
            _set_offset(page, -2.5)
        else:
            _direct_sweep_x(page, -2.5)
    if out_dir is not None: _shot(page, out_dir, MECHANIC_ID, "hot-slice-rotated-case")
    hits = page.evaluate("() => window.tomographicBaggageSurgeryModel.targetHits")
    if hits < int(truth["requirements"]["min_target_observations"]): raise AssertionError(f"distinct target slice signatures missing: {hits}")
    page.locator(".tomo-lock").click(); expect(page.locator(".tomo-slicer[data-locked='true']")).to_be_visible()


def _screen(box: dict, view: dict, coordinate: list[float]) -> tuple[float, float]:
    axis = {"x": 0, "y": 1, "z": 2}
    local = [view["center"][i] + view["scale"] * view["signs"][i] * coordinate[axis[name]] for i, name in enumerate(view["axes"])]
    return box["x"] + local[0] / view["width"] * box["width"], box["y"] + local[1] / view["height"] * box["height"]


def _drag_view(page, truth: dict, view_id: str, coordinate: list[float], steps: int = 28) -> None:
    canvas = page.locator(f".tomo-probe[data-view='{view_id}']"); box = canvas.bounding_box()
    if not box: raise AssertionError(f"missing {view_id} probe view")
    current = page.evaluate("() => [...window.tomographicBaggageSurgeryModel.probe]"); view = truth["views"][view_id]
    page.mouse.move(*_screen(box, view, current)); page.mouse.down(); page.mouse.move(*_screen(box, view, coordinate), steps=steps); page.mouse.up(); page.wait_for_timeout(50)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID: raise AssertionError(mechanic)
    # First prove server failure issues a fresh sealed volume.
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"]); page.locator(".tomo-submit").click(); _wait_new(state_dir, before)
    expect(page.locator(".tomo-captcha[data-fresh-failure='true']")).to_be_visible(timeout=8_000); _shot(page, out_dir, mechanic, "fail-fresh-volume")
    # Exercise the recoverable local collision, then submit its permanently damaged report to obtain another genuinely fresh challenge.
    truth = _read(state_dir / "ground_truth.json"); _scan_and_lock(page, truth)
    collision = truth["solver"]["collision"]; safe = truth["solver"]["safe_y"]
    _drag_view(page, truth, "top", [collision[0], safe, collision[2]])
    _drag_view(page, truth, "front", [collision[0], collision[1], collision[2]])
    expect(page.locator(".tomo-local-fail[data-visible='true']")).to_be_visible(); _shot(page, out_dir, mechanic, "innocent-collision")
    page.locator(".tomo-reset").click()
    if page.evaluate("() => window.tomographicBaggageSurgeryModel.damages") < 1: raise AssertionError("innocent contact was not retained on report")
    _shot(page, out_dir, mechanic, "probe-recovered-damage-retained")
    before = str(truth["challenge_id"]); page.locator(".tomo-submit").click(); _wait_new(state_dir, before)
    expect(page.locator(".tomo-captcha[data-fresh-failure='true']")).to_be_visible(timeout=8_000)


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID: raise AssertionError(mechanic)
    truth = _read(state_dir / "ground_truth.json"); _scan_and_lock(page, truth, out_dir)
    target = truth["solver"]["target"]; safe = truth["solver"]["safe_y"]
    _drag_view(page, truth, "top", [target[0], safe, target[2]]); _shot(page, out_dir, mechanic, "cross-view-registration-top")
    _drag_view(page, truth, "front", target); _shot(page, out_dir, mechanic, "probe-on-target")
    if int(truth["requirements"].get("min_moving_views", 0)) >= 3:
        # A third registration must include a visible non-zero side-view move,
        # then return to the target before capture.
        _drag_view(page, truth, "side", [target[0], safe, target[2]])
        _drag_view(page, truth, "side", target)
    elif int(truth["requirements"].get("min_views", 2)) >= 3:
        _drag_view(page, truth, "side", target)
    page.locator(".tomo-capture").click(); expect(page.locator(".tomo-probe-state")).to_have_text("TARGET HELD"); _shot(page, out_dir, mechanic, "geometric-target-capture")
    _drag_view(page, truth, "front", [target[0], safe, target[2]], steps=36)
    expect(page.locator(".tomo-complete[data-visible='true']")).to_be_visible(); _shot(page, out_dir, mechanic, "clean-target-extraction")
    state = page.evaluate("() => ({done:window.tomographicBaggageSurgeryModel.completed,damages:window.tomographicBaggageSurgeryModel.damages,hits:window.tomographicBaggageSurgeryModel.targetHits})")
    if not state["done"] or state["damages"] != 0 or state["hits"] < 2: raise AssertionError(state)
    page.locator(".tomo-submit").click(); expect(page.locator(".readout")).to_have_text("PASS", timeout=8_000)
