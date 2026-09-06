from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "ballast_lantern"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, mechanic: str, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    was_running = page.evaluate("() => window.WeirdCaptchaTime?.status().state === 'running'")
    if was_running:
        page.evaluate("() => window.WeirdCaptchaTime.pause()")
        page.wait_for_timeout(40)
    page.screenshot(path=str(out_dir / f"{mechanic}-{name}.png"), full_page=True)
    if was_running:
        page.evaluate("() => window.WeirdCaptchaTime.resume()")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator(".ballast-abandon").click()
    expect(page.locator(".ballast-foot .readout")).to_contain_text("FAIL", timeout=7000)
    after = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    if before == after:
        raise AssertionError("Ballast Lantern did not regenerate after deliberate failure")
    _screenshot(page, out_dir, mechanic, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    truth = _read(state_dir / "ground_truth.json")
    schedule = list(truth["reference_schedule"])
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    captured = False
    capture_tick = int(truth["crate"]["spawn_tick"]) + 45
    paused_mode = page.evaluate("() => new URLSearchParams(location.search).get('time_mode') === 'paused'")
    for event in schedule:
        tick = int(event["tick"])
        if paused_mode and page.evaluate("() => window.ballastLanternModel.sim.tick") < tick:
            page.evaluate("() => window.WeirdCaptchaTime.resume()")
        page.wait_for_function(
            "target => window.ballastLanternModel && window.ballastLanternModel.sim.tick >= target",
            arg=tick,
            timeout=70000,
            polling=2,
        )
        if paused_mode:
            page.evaluate("() => window.WeirdCaptchaTime.pause()")
        if interaction == "full":
            if event["engaged"]:
                page.keyboard.down("Space")
            else:
                page.keyboard.up("Space")
        else:
            page.locator(".ballast-haul" if event["engaged"] else ".ballast-coast").click()
        if not captured and tick >= capture_tick:
            _screenshot(page, out_dir, mechanic, "active-dual-target")
            captured = True
    if paused_mode:
        page.evaluate("() => window.WeirdCaptchaTime.resume()")
    expect(page.locator(".ballast-foot .readout")).to_contain_text("PASS", timeout=70000)
    if paused_mode:
        page.evaluate("() => window.WeirdCaptchaTime.pause()")
    if interaction == "full":
        page.keyboard.up("Space")
    _screenshot(page, out_dir, mechanic, "pass")
