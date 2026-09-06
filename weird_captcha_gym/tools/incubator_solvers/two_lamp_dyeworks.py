from __future__ import annotations

import json
import math
from pathlib import Path


MECHANIC_ID = "two_lamp_dyeworks"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=True)


def _select_pigment(page, pigment_id: str) -> None:
    page.locator(f'.dye-bottle[data-pigment="{pigment_id}"]').click()


def _set_simplified_dose(page, units: int) -> None:
    for _ in range(max(0, units - 1)):
        page.locator("#dose-plus").click()


def _draw_full_plunger(page, units: int, maximum_units: int) -> None:
    handle = page.locator("#dye-plunger-handle").bounding_box()
    track = page.locator("#dye-plunger-track").bounding_box()
    if handle is None or track is None:
        raise AssertionError("syringe plunger is not visible")
    x = handle["x"] + handle["width"] / 2
    start_y = handle["y"] + handle["height"] / 2
    end_y = track["y"] + track["height"] * units / maximum_units
    page.mouse.move(x, start_y)
    page.mouse.down()
    page.mouse.move(x, end_y, steps=7)
    page.mouse.up()


def _stir_full(page) -> None:
    vat = page.locator(".vat-basin").bounding_box()
    stirrer = page.locator("#dye-stirrer").bounding_box()
    if vat is None or stirrer is None:
        raise AssertionError("vat stirring geometry is not visible")
    center_x = vat["x"] + vat["width"] / 2
    center_y = vat["y"] + vat["height"] / 2
    radius = min(vat["width"], vat["height"]) * 0.34
    page.mouse.move(stirrer["x"] + stirrer["width"] / 2, stirrer["y"] + stirrer["height"] / 2)
    page.mouse.down()
    for step in range(1, 21):
        angle = 2 * math.pi * step / 20
        page.mouse.move(center_x + radius * math.cos(angle), center_y + radius * math.sin(angle))
    page.mouse.up()


def _dip_full(page) -> None:
    strip = page.locator("#test-strip-source").bounding_box()
    opening = page.locator(".vat-rim").bounding_box()
    if strip is None or opening is None:
        raise AssertionError("test strip or vat opening is not visible")
    page.mouse.move(strip["x"] + strip["width"] / 2, strip["y"] + strip["height"] / 2)
    page.mouse.down()
    # Use the left-center of the opening so the release is visibly in liquid
    # and clear of the stirrer laid across the right side of the vat.
    page.mouse.move(opening["x"] + opening["width"] * 0.32, opening["y"] + opening["height"] / 2, steps=8)
    page.mouse.up()


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read_json(state_dir / "ground_truth.json")
    before = str(truth["challenge_id"])
    fresh_vats = int(truth["parameters"]["fresh_vats"])
    for _ in range(fresh_vats):
        page.locator("#dump-vat").click()
    page.wait_for_function(
        "before => window.twoLampDyeworksModel.state.challenge_id !== before && document.querySelector('.readout')?.textContent.includes('FAIL')",
        arg=before,
        timeout=10000,
    )
    after = _read_json(state_dir / "ground_truth.json")["challenge_id"]
    if before == after:
        raise AssertionError("exhausting the vat bank did not create a fresh challenge")
    _screenshot(page, out_dir, "failure-fresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read_json(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    maximum_units = int(truth["parameters"]["maximum_units_per_pigment"])
    plan = list(truth.get("canonical_plan") or [])
    if not plan:
        raise AssertionError("generated dyeworks target has no canonical dosing plan")
    for dose_index, dose in enumerate(plan, start=1):
        units = int(dose["units"])
        _select_pigment(page, str(dose["pigment"]))
        if interaction == "full":
            _draw_full_plunger(page, units, maximum_units)
        else:
            _set_simplified_dose(page, units)
        page.locator("#dye-inject").click()
        page.wait_for_function(
            "count => window.twoLampDyeworksModel.events.filter(event => event.type === 'dose').length === count",
            arg=dose_index,
        )
    _screenshot(page, out_dir, "mixed-unstirred")
    if interaction == "full":
        _stir_full(page)
        page.wait_for_function("() => window.twoLampDyeworksModel.stirred === true")
        _dip_full(page)
    else:
        page.locator("#dye-stir-button").click()
        page.locator("#dye-dip-button").click()
    page.wait_for_function("() => Boolean(window.twoLampDyeworksModel.sampledComposition)")
    page.wait_for_timeout(220)
    _screenshot(page, out_dir, f"{interaction}-daylight-sample")
    if page.locator("#lamp-switch").get_attribute("data-lamp") != "daylight":
        page.locator("#lamp-switch").click()
    page.locator("#lamp-switch").click()
    page.wait_for_function("() => window.twoLampDyeworksModel.lamp === 'sodium' && window.twoLampDyeworksModel.ready === true")
    page.wait_for_timeout(220)
    _screenshot(page, out_dir, f"{interaction}-sodium-match")
    page.locator("#dye-certify").click()
    page.wait_for_function("() => document.querySelector('.readout')?.textContent === 'PASS'", timeout=10000)
    _screenshot(page, out_dir, f"{interaction}-pass")
