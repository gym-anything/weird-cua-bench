from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "reverse_identity_gate"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, mechanic: str, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{label}.png"), full_page=True)


def _station_page(context, station: int):
    for candidate in context.pages:
        if candidate.is_closed():
            continue
        try:
            if candidate.locator(f'[data-station-page="{station}"]').count():
                return candidate
        except Exception:
            continue
    raise AssertionError(f"real browser tab for station {station} not found")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator("#robot-verify").click()
    expect(page.locator(".robot-master[data-fresh-failure='true']")).to_be_visible(timeout=7_000)
    expect(page.locator(".robot-master-foot .readout")).to_contain_text("FAIL", timeout=7_000)
    after = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    if before == after:
        raise AssertionError("failed robot ledger did not issue a fresh challenge")
    _screenshot(page, out_dir, mechanic, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    context = page.context
    tabs = {}
    for station in range(4):
        page.bring_to_front()
        with page.expect_popup() as popup:
            page.locator(f'[data-deploy="{station}"]').click()
        child = popup.value
        child.wait_for_load_state("domcontentloaded")
        expect(child.locator(f'[data-station-page="{station}"]')).to_be_visible()
        tabs[station] = child
    page.bring_to_front()
    expect(page.locator("#robot-deployment-count")).to_have_text("4/4")
    _screenshot(page, out_dir, mechanic, "four-tabs-online")

    for index, stage in enumerate(truth["stages"]):
        station = int(stage["station"])
        child = tabs.get(station) or _station_page(context, station)
        child.bring_to_front()
        root = child.locator(f'[data-station-page="{station}"]')
        expect(root).to_have_attribute("data-active", "true", timeout=5_000)
        key = "d" if int(stage["pulse_speed_deg_per_tick"]) > 0 else "a"
        child.keyboard.down(key)
        contact = child.locator("#station-contact")
        bounds = contact.bounding_box()
        if not bounds:
            raise AssertionError(f"station {station} contact has no bounds")
        child.mouse.move(bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
        child.mouse.down()
        expect(root).to_have_attribute("data-active", "false", timeout=16_000)
        child.mouse.up()
        child.keyboard.up(key)
        if index == 0:
            _screenshot(child, out_dir, mechanic, "first-relay-sealed")

    page.bring_to_front()
    expect(page.locator("#robot-relay-count")).to_have_text("8/8", timeout=5_000)
    _screenshot(page, out_dir, mechanic, "eight-relays")
    page.locator("#robot-verify").click()
    expect(page.locator(".robot-master-foot .readout")).to_have_text("PASS", timeout=8_000)
    expect(page.locator(".robot-master-foot .readout")).to_have_attribute("data-status", "passed")
