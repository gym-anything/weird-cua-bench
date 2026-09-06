from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "apothecary_dead_reckoning"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{name}.png"), full_page=True)


def _wait_for_new_challenge(state_dir: Path, previous_id: str) -> None:
    deadline = time.time() + 8
    while time.time() < deadline:
        current = _read(state_dir / "ground_truth.json")
        if str(current.get("challenge_id")) != previous_id:
            return
        time.sleep(.05)
    raise AssertionError("apothecary server did not issue a fresh challenge")


def _center(locator) -> tuple[float, float]:
    box = locator.bounding_box()
    if not box:
        raise AssertionError("visible interaction target has no bounding box")
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def _load(page, ingredient_id: str, interaction: str) -> None:
    jar = page.locator(f'.apoth-jar[data-ingredient-id="{ingredient_id}"]')
    if interaction == "simplified":
        jar.click()
        return
    start = _center(jar)
    end = _center(page.locator(".apoth-mortar"))
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move(*end, steps=12)
    page.mouse.up()


def _grind(page, grind_step: int, interaction: str) -> None:
    if interaction == "simplified":
        page.locator(f'button[data-grind-step="{grind_step}"]').click()
        return
    point = _center(page.locator("#apoth-pestle"))
    page.mouse.move(*point)
    page.mouse.down()
    if grind_step:
        page.wait_for_function(
            "step => window.apothecaryDeadReckoningModel.grindStep >= step",
            arg=grind_step,
            timeout=max(3_000, grind_step * 420),
        )
    else:
        page.wait_for_timeout(35)
    page.mouse.up()
    page.wait_for_function("() => !window.apothecaryDeadReckoningModel.grinding")
    actual = page.evaluate("() => window.apothecaryDeadReckoningModel.grindStep")
    if actual != grind_step:
        raise AssertionError(f"full pestle stopped at notch {actual}, expected {grind_step}")


def _commit(page) -> None:
    page.locator("#apoth-stir").click()
    while page.evaluate("() => Boolean(window.apothecaryDeadReckoningModel.activeId)"):
        page.locator("#apoth-stir").click()


def _exercise_recovery(page, truth: dict, interaction: str, out_dir: Path) -> None:
    origin = truth["origin"]
    probe = truth["recovery_probe"]
    _load(page, str(probe["ingredient_id"]), interaction)
    _grind(page, int(probe["grind_step"]), interaction)
    expect(page.locator(".readout")).not_to_contain_text("LOCKED")
    _commit(page)
    displaced = page.evaluate(
        "() => ({position: window.apothecaryDeadReckoningModel.position, routeProgress: window.apothecaryDeadReckoningModel.routeProgress, vortices: [...window.apothecaryDeadReckoningModel.contactedVortices]})"
    )
    if displaced["routeProgress"] != 0:
        raise AssertionError("off-route recovery probe advanced a route ring")
    expected_vortex = probe.get("expected_vortex_id")
    if expected_vortex and expected_vortex not in displaced["vortices"]:
        raise AssertionError(f"recovery probe missed {expected_vortex}: {displaced}")
    _shot(page, out_dir, f"committed-error-{interaction}")
    for _attempt in range(int(truth["parameters"]["water_budget"])):
        current = page.evaluate("() => window.apothecaryDeadReckoningModel.position")
        if max(abs(float(current[index]) - float(origin[index])) for index in (0, 1)) <= .01:
            break
        page.locator("#apoth-water").click()
    returned = page.evaluate("() => window.apothecaryDeadReckoningModel.position")
    if max(abs(float(returned[index]) - float(origin[index])) for index in (0, 1)) > .01:
        raise AssertionError(f"water did not recover the committed error: {returned} != {origin}")
    water_left = int(page.locator("#apoth-water-left").text_content() or "0")
    if water_left and int(truth["parameters"]["bellows_budget"]):
        page.locator("#apoth-bellows").click()
        page.locator("#apoth-water").click()
    returned = page.evaluate("() => window.apothecaryDeadReckoningModel.position")
    if max(abs(float(returned[index]) - float(origin[index])) for index in (0, 1)) > .01:
        raise AssertionError(f"water did not recover the bellows check: {returned} != {origin}")
    _shot(page, out_dir, f"water-recovery-{interaction}")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(mechanic)
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator("#apoth-seal").click()
    _wait_for_new_challenge(state_dir, before)
    expect(page.locator(".apoth-verdict.is-fresh")).to_be_visible(timeout=8_000)
    expect(page.locator(".readout")).to_contain_text("FAIL")
    _shot(page, out_dir, "failure-fresh-map")
    expect(page.locator(".apoth-verdict.is-fresh")).to_be_hidden(timeout=4_000)


def solve(page, state_dir: Path, out_dir: Path, mechanic: str, *, certify: bool = True) -> None:
    del certify
    if mechanic != MECHANIC_ID:
        raise AssertionError(mechanic)
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    _shot(page, out_dir, f"initial-{interaction}")
    _exercise_recovery(page, truth, interaction, out_dir)
    for index, commit in enumerate(truth["solution"]):
        if index == 0:
            decoy = next(
                ingredient["id"]
                for ingredient in truth["ingredients"]
                if ingredient["id"] != commit["ingredient_id"]
            )
            _load(page, str(decoy), interaction)
            _grind(page, min(2, int(truth["parameters"]["grind_notches"]) - 1), interaction)
            expect(page.locator(".readout")).not_to_contain_text("LOCKED")
            expect(page.locator(".readout")).not_to_contain_text("DO NOT MATCH")
            _shot(page, out_dir, f"probe-and-route-ring-{interaction}")
        _load(page, str(commit["ingredient_id"]), interaction)
        _grind(page, int(commit["grind_step"]), interaction)
        expect(page.locator(".readout")).not_to_contain_text("LOCKED")
        expect(page.locator(".readout")).not_to_contain_text("DO NOT MATCH")
        if index == 0:
            _shot(page, out_dir, f"first-route-preview-{interaction}")
        _commit(page)
        if index == max(0, len(truth["solution"]) // 2 - 1):
            _shot(page, out_dir, f"fog-opening-{interaction}")

    rendered = page.evaluate(
        "() => ({position: window.apothecaryDeadReckoningModel.position, active: window.apothecaryDeadReckoningModel.activeId, contacts: [...window.apothecaryDeadReckoningModel.contactedBones], routeProgress: window.apothecaryDeadReckoningModel.routeProgress})"
    )
    target = next(effect for effect in truth["effects"] if effect["id"] == truth["target_effect_id"])
    dx = float(rendered["position"][0]) - float(target["center"][0])
    dy = float(rendered["position"][1]) - float(target["center"][1])
    if rendered["active"] is not None or (dx * dx + dy * dy) ** .5 > .12:
        raise AssertionError(f"solution route missed target geometry: {rendered} versus {target}")
    if len(rendered["contacts"]) > int(truth["parameters"]["max_hazard_contacts"]):
        raise AssertionError(f"solution route contacted forbidden hazards: {rendered['contacts']}")
    if rendered["routeProgress"] != len(truth["route_gates"]):
        raise AssertionError(f"solution did not pass every route ring: {rendered}")
    _shot(page, out_dir, f"target-revealed-{interaction}")
    page.locator("#apoth-seal").click()
    expect(page.locator(".apoth-verdict.is-pass strong")).to_have_text("PASS", timeout=8_000)
    expect(page.locator(".readout")).to_have_text("PASS")
    _shot(page, out_dir, f"pass-{interaction}")
