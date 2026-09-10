"""Reference browser solver for wiring evidence.

It reads the generated task truth only to choose a deterministic test route;
all mutations are ordinary visible clicks and pointer drags on the task page.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path


MECHANIC_ID = "cell_gatekeeper"


def _truth(state_dir: Path) -> dict:
    return json.loads((state_dir / "ground_truth.json").read_text(encoding="utf-8"))


def _advance(page, milliseconds: int) -> None:
    # Observation scheduling belongs to the shared runner/harness, never to
    # the policy. In a paused run the harness advances its fixed frame window.
    page.wait_for_timeout(milliseconds)


def _visible_box(page, selector: str) -> dict:
    for _ in range(12):
        box = page.locator(selector).bounding_box()
        if not box:
            raise AssertionError(f"missing input surface {selector}")
        height = page.viewport_size["height"]
        center = box["y"] + box["height"] / 2
        if 16 <= center <= height - 16:
            return box
        # Scroll the task document with the same wheel input a model has.
        page.mouse.move(20, height / 2)
        page.mouse.wheel(0, max(-600, min(600, center - height / 2)))
        page.wait_for_timeout(40)
    raise AssertionError(f"cannot scroll input into the viewport: {selector}")


def _drag(page, source_selector: str, target_selector: str) -> None:
    source = _visible_box(page, source_selector)
    page.mouse.move(source["x"] + source["width"] / 2, source["y"] + source["height"] / 2)
    page.mouse.down()
    target = _visible_box(page, target_selector)
    page.mouse.move(target["x"] + target["width"] / 2, target["y"] + target["height"] / 2, steps=8)
    page.mouse.up()


def _sim(page) -> dict:
    return page.evaluate("window.cellGatekeeperModel.sim")


def _goal_ok(page, state: dict) -> bool:
    sim = _sim(page)
    for sid, target in state["goal"].items():
        for side in ("outside", "inside"):
            if not target[side][0] <= sim["counts"][sid][side] <= target[side][1]:
                return False
    installed = set(sim["installed_history"])
    for pid in state["required_proteins"]:
        if pid not in installed:
            return False
        if pid.endswith("_pump") and sim["crossings"]["active"].get(pid, 0) < state["parameters"]["pump_cycles"]:
            return False
        if pid.endswith("_leak") and sim["crossings"]["passive"].get(pid, 0) < 1:
            return False
    catalog = {item["id"]: item for item in state["protein_catalog"]}
    leak_removed = not any(catalog.get(pid, {}).get("kind") == "leak" and pid in state["required_proteins"] for pid in sim["slots"] if pid)
    return leak_removed and int(sim.get("stable_ticks", 0)) >= int(state["parameters"].get("observation_ticks", 0))


def _slot_for(page, protein_id: str) -> int:
    sim = _sim(page)
    return sim["slots"].index(protein_id)


def _place(page, protein_id: str, mode: str) -> None:
    if mode == "full":
        slot = next(index for index, item in enumerate(_sim(page)["slots"]) if item is None)
        _drag(page, f'.protein-card[data-protein="{protein_id}"]', f'.membrane-slot[data-slot="{slot}"]')
    else:
        slot = next(index for index, item in enumerate(_sim(page)["slots"]) if item is None)
        selector = page.locator(f'[data-place-slot="{protein_id}"]')
        selector.click()
        # Native type-ahead also works in isolated Chromium on macOS, where
        # popup arrow/Home keys may leave the selected option unchanged.
        page.keyboard.type(f"SLOT {slot + 1}")
        page.keyboard.press("Enter")
        assert selector.input_value() == str(slot), "native selector did not choose the first empty slot"
        page.locator(f'[data-place="{protein_id}"]').click()
    page.wait_for_timeout(60)
    assert protein_id in _sim(page)["slots"], (protein_id, _sim(page))


def _remove(page, protein_id: str, mode: str) -> None:
    slot = _slot_for(page, protein_id)
    if mode == "full":
        _drag(page, f'.membrane-slot[data-slot="{slot}"]', ".eject-zone")
    else:
        page.locator(f'[data-eject-slot="{slot}"]').click()
    page.wait_for_timeout(60)
    assert _sim(page)["slots"][slot] is None, _sim(page)


def _supply(page, state: dict, mode: str, units: int) -> None:
    batch = int(state["parameters"]["atp_batch"])
    bursts = math.ceil(units / batch)
    if mode == "full":
        for _ in range(bursts):
            _drag(page, "[data-atp-token]", ".cg-atp")
    else:
        for _ in range(bursts):
            page.locator("[data-supply]").click()


def _calibrate(page, state: dict, mode: str) -> None:
    for sid, targets in state["goal"].items():
        for side in ("outside", "inside"):
            for _ in range(int(state["surface"]["capacity"])):
                count = _sim(page)["counts"][sid][side]
                low, high = targets[side]
                if low <= count <= high:
                    break
                delta = 1 if count < low else -1
                if mode == "full":
                    _drag(page, f'[data-solute="{sid}"][data-delta="{delta}"]', f'.compartment-drop[data-side="{side}"]')
                else:
                    page.locator(f'[data-adjust="{sid}"][data-side="{side}"][data-delta="{delta}"]').click()


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = _truth(state_dir)["challenge_id"]
    page.screenshot(path=str(out_dir / "cell_gatekeeper-initial.png"))
    page.locator("[data-lock]").click()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        current = _truth(state_dir)
        if current["challenge_id"] != before:
            page.screenshot(path=str(out_dir / "cell_gatekeeper-failure-retry.png"))
            return
        time.sleep(0.02)
    raise AssertionError("failed lock did not generate a fresh membrane challenge")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    state = _truth(state_dir)
    mode = (state.get("control_condition") or {}).get("interaction", "full")
    page.screenshot(path=str(out_dir / "cell_gatekeeper-initial.png"))
    required = list(state["required_proteins"])
    leaks = [pid for pid in required if pid.endswith("_leak")]
    pumps = [pid for pid in required if pid.endswith("_pump")]

    for leak in leaks:
        _place(page, leak, mode)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and _sim(page)["crossings"]["passive"].get(leak, 0) < 1:
            _advance(page, 20)
        assert _sim(page)["crossings"]["passive"].get(leak, 0) >= 1, _sim(page)
        page.screenshot(path=str(out_dir / "cell_gatekeeper-passive-crossing.png"))
        _remove(page, leak, mode)

    for pump in pumps:
        _place(page, pump, mode)
    need = len(pumps) * int(state["parameters"]["pump_cycles"])
    _supply(page, state, mode, need)
    page.screenshot(path=str(out_dir / "cell_gatekeeper-active-transport.png"))

    deadline = time.monotonic() + 50
    while time.monotonic() < deadline:
        sim = _sim(page)
        if all(sim["crossings"]["active"].get(pid, 0) >= state["parameters"]["pump_cycles"] for pid in pumps) and sim["atp"] < len(pumps):
            break
        _advance(page, 50)
    _calibrate(page, state, mode)
    while time.monotonic() < deadline and not _goal_ok(page, state):
        _advance(page, max(100, int(state["parameters"]["pump_period"]) * 45))
    assert _goal_ok(page, state), _sim(page)
    page.screenshot(path=str(out_dir / "cell_gatekeeper-ready-to-lock.png"))
    page.locator("[data-lock]").click()
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if page.locator(".readout").get_attribute("data-status") == "passed":
            page.screenshot(path=str(out_dir / "cell_gatekeeper-pass.png"))
            return
        time.sleep(0.03)
    raise AssertionError(f"membrane lock did not pass: {_sim(page)}")
