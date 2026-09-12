from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "curio_tray"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=True)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator("#curio-submit").click()
    page.wait_for_function("() => document.querySelector('.readout')?.textContent.includes('NEW CABINET')", timeout=5_000)
    after = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    if before == after:
        raise AssertionError("Curio Tray did not regenerate after deliberate failure")
    _shot(page, out_dir, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    order = [str(item) for item in truth["solution_order"]]
    for index, item_id in enumerate(order):
        if interaction == "simplified":
            page.locator(f'.curio-proxy[data-item-id="{item_id}"]').click()
        else:
            page.locator(f'.curio-item[data-item-id="{item_id}"][data-accessible="true"]').click()
        if index == max(1, len(order) // 2):
            _shot(page, out_dir, "active")
        page.wait_for_timeout(35)
    expect(page.locator(".readout")).to_contain_text("APPRAISE", timeout=5_000)
    page.locator("#curio-submit").click()
    expect(page.locator(".readout")).to_contain_text("PASS", timeout=5_000)
    _shot(page, out_dir, "pass")
