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


def _paused(page) -> bool:
    return page.evaluate("new URLSearchParams(location.search).get('time_mode') === 'paused'")


def _advance(page, milliseconds: int) -> None:
    if _paused(page):
        page.evaluate("ms => WeirdCaptchaTime.runFor(ms)", milliseconds)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if page.evaluate("WeirdCaptchaTime.status().phase") == "completed":
                return
            time.sleep(0.01)
        raise AssertionError("paused observation window did not complete")
    page.wait_for_timeout(milliseconds)


def _drag(page, source_selector: str, target_selector: str) -> None:
    source = page.locator(source_selector).bounding_box()
    target = page.locator(target_selector).bounding_box()
    if not source or not target:
        raise AssertionError(f"missing drag surface {source_selector} -> {target_selector}")
    page.mouse.move(source["x"] + source["width"] / 2, source["y"] + source["height"] / 2)
    page.mouse.down()
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
        page.locator(f'[data-place-slot="{protein_id}"]').select_option(str(slot))
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
            # In live mode this probe is intentionally sampled more finely
            # than one full transport period so the scripted evidence removes
            # the visible leak after the first crossing. Paused mode retains
            # the evaluator's fixed observation window.
            _advance(
                page,
                100 if _paused(page) else 20,
            )
        assert _sim(page)["crossings"]["passive"].get(leak, 0) >= 1, _sim(page)
        page.screenshot(path=str(out_dir / "cell_gatekeeper-passive-crossing.png"))
        _remove(page, leak, mode)

    for pump in pumps:
        _place(page, pump, mode)
    need = len(pumps) * int(state["parameters"]["pump_cycles"])
    _supply(page, state, mode, need)
    page.screenshot(path=str(out_dir / "cell_gatekeeper-active-transport.png"))

    deadline = time.monotonic() + 50
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
