"""Wiring-only oracle: drives the ordinary visible Crater Walker controls."""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "crater_walker"
LEGS = ("front_left", "front_right", "rear_left", "rear_right")
ACTUATORS = ("yaw", "lift", "extend")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{name}.png"), full_page=True)


def _set_value(page, leg: str, actuator: str, target: int, mode: str) -> None:
    card = page.locator(f'[data-leg="{leg}"]')
    if mode == "full":
        card.locator(f'input[data-actuator="{actuator}"]').fill(str(target))
        return
    value = int(card.locator(f'[data-value-for="{actuator}"]').inner_text())
    button = card.locator(f'button[data-actuator="{actuator}"][data-nudge="{{delta}}"]')
    while value != target:
        delta = 1 if target > value else -1
        card.locator(f'button[data-actuator="{actuator}"][data-nudge="{delta}"]').click()
        value += delta


def _settle(page) -> None:
    page.locator(".crater-settle").click()
    page.wait_for_timeout(35)


def solve(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    truth = _read(state_dir / "ground_truth.json")
    mode = str((truth.get("control_condition") or {}).get("interaction") or "simplified")
    for index, transfer in enumerate(truth.get("transfer_controls") or [], start=1):
        leg = str(transfer["leg"])
        controls = dict(transfer["controls"])
        _set_value(page, leg, "lift", 3, mode)
        _settle(page)
        _set_value(page, leg, "yaw", int(controls["yaw"]), mode)
        _set_value(page, leg, "extend", int(controls["extend"]), mode)
        _settle(page)
        _set_value(page, leg, "lift", int(controls["lift"]), mode)
        _settle(page)
        target_stage = index + 1
        for _ in range(6):
            if page.locator(".crater-stage").inner_text().startswith(f"{target_stage} /"):
                break
            _settle(page)
        if not page.locator(".crater-stage").inner_text().startswith(f"{target_stage} /"):
            raise AssertionError("walker did not visibly traverse to the next terrace")
        _shot(page, out_dir, f"transfer-{index}")
    page.locator(".crater-certify").click()
    expect(page.locator(".crater-readout")).to_contain_text("PASS", timeout=8000)
    _shot(page, out_dir, "pass")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str = MECHANIC_ID) -> None:
    mode = str((_read(state_dir / "ground_truth.json").get("control_condition") or {}).get("interaction") or "simplified")
    for leg in LEGS[:2]:
        _set_value(page, leg, "lift", 3, mode)
    _settle(page)
    expect(page.locator(".crater-readout")).to_contain_text("FAIL", timeout=4000)
    _shot(page, out_dir, "failure")
    page.locator(".crater-retry").click()
    expect(page.locator(".crater-readout")).to_contain_text("READY", timeout=8000)


__all__ = ["solve", "fail_once"]
