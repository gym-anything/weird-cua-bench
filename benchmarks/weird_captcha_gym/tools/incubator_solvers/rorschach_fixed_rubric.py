from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "rorschach_fixed_rubric"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, mechanic: str, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{label}.png"), full_page=True)


def _wait_for_new_challenge(state_dir: Path, previous: str) -> str:
    deadline = time.time() + 8
    while time.time() < deadline:
        current = str(_read_json(state_dir / "ground_truth.json").get("challenge_id") or "")
        if current and current != previous:
            return current
        time.sleep(0.05)
    raise AssertionError("inkblot material set did not regenerate after failure")


def _fold(page) -> None:
    track = page.locator(".ink-fold-track").bounding_box()
    if not track:
        raise AssertionError("fold-axis track is not visible")
    y = track["y"] + track["height"] / 2
    page.mouse.move(track["x"] + 2, y)
    page.mouse.down()
    page.mouse.move(track["x"] + track["width"] * .94, y, steps=10)
    page.mouse.up()


def _pressure(page, duration_ms: int) -> None:
    button = page.locator(".ink-pressure")
    box = button.bounding_box()
    if not box:
        raise AssertionError("pressure tool is not visible")
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.wait_for_timeout(duration_ms)
    page.mouse.up()


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = str(_read_json(state_dir / "ground_truth.json")["challenge_id"])
    page.locator(".ink-submit").click()
    _wait_for_new_challenge(state_dir, before)
    expect(page.locator(".ink-material-captcha[data-fresh-failure='true']")).to_be_visible(timeout=8_000)
    expect(page.locator(".readout")).to_contain_text("FAIL")
    _screenshot(page, out_dir, mechanic, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read_json(state_dir / "ground_truth.json")

    probe_index = 0
    for blot in truth["blot_rects"]:
        blot_id = blot["id"]
        page.locator(f'.ink-card[data-blot-id="{blot_id}"]').click()
        for tool in truth["required_tools"]:
            if tool == "FOLD":
                _fold(page)
            elif tool == "PRESSURE":
                _pressure(page, int(truth["pressure_min_ms"]) + 110)
            elif tool == "COOL":
                page.locator(".ink-cool").click()
            else:
                raise AssertionError(f"unknown material tool {tool!r}")
            probe_index += 1
            if probe_index in {3, 7}:
                page.wait_for_timeout(310)
                _screenshot(page, out_dir, mechanic, f"active-specimen-response-{probe_index}")
            key = f"{blot_id}|{tool}"
            page.wait_for_function("key => window.inkblotMaterialModel.observations.has(key)", arg=key, timeout=5_000)

    expect(page.locator(".ink-stamp[data-ready='true']")).to_be_visible()
    stamp = page.locator(".ink-stamp").bounding_box()
    target = page.locator(f'.ink-card[data-blot-id="{truth["culprit_id"]}"]').bounding_box()
    if not stamp or not target:
        raise AssertionError("verification stamp or target specimen is not visible")
    page.mouse.move(stamp["x"] + stamp["width"] / 2, stamp["y"] + stamp["height"] / 2)
    page.mouse.down()
    page.mouse.move(target["x"] + target["width"] / 2, target["y"] + target["height"] / 2, steps=10)
    page.mouse.up()
    expect(page.locator(f'.ink-blot[data-blot-id="{truth["culprit_id"]}"].is-stamped')).to_be_visible()
    physical = page.evaluate("""() => ({
      observations: window.inkblotMaterialModel.observations.size,
      ticks: window.inkblotMaterialModel.tickTotal,
      foldSamples: window.inkblotMaterialModel.foldSamples,
      pressureHolds: window.inkblotMaterialModel.pressureHolds,
      thermalPulses: window.inkblotMaterialModel.thermalPulses,
      stampMoves: window.inkblotMaterialModel.stampMoves,
      stamped: window.inkblotMaterialModel.stampedId,
      resets: window.inkblotMaterialModel.resetCount,
    })""")
    expected_observations = int(truth["observations_required"])
    expected_ticks = expected_observations * int(truth["ticks_per_cycle"])
    expected_fold = 5 if "FOLD" in truth["required_tools"] else 0
    expected_pressure = 5 if "PRESSURE" in truth["required_tools"] else 0
    expected_cool = 5 if "COOL" in truth["required_tools"] else 0
    if physical["observations"] != expected_observations or physical["ticks"] != expected_ticks or physical["foldSamples"] < expected_fold * 3 or physical["pressureHolds"] != expected_pressure or physical["thermalPulses"] != expected_cool or physical["stampMoves"] < 3 or physical["stamped"] != truth["culprit_id"] or physical["resets"] != 0:
        raise AssertionError(f"material workflow lacked required physical evidence: {physical}")
    _screenshot(page, out_dir, mechanic, "solved-specimen-matrix")
    page.locator(".ink-submit").click()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=8_000)
