#!/usr/bin/env python3
"""Capture Marionette Checkpoint's own static UI and bundled Pyodide passes."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

EVIDENCE = Path(__file__).resolve().parent
REPO = EVIDENCE.parents[3]
sys.path.insert(0, str(REPO))
from weird_captcha_gym.dashboard.catalog import build_catalog
from weird_captcha_gym.dashboard.export_static import _export_browser_play

ENVIRONMENT = "marionette_checkpoint_env"
MECHANIC = "marionette_checkpoint"

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format, *_args): pass

def fingerprint(state):
    state = copy.deepcopy(state)
    for key in ("task_id", "challenge_id", "control_condition"): state.pop(key, None)
    return hashlib.sha256(json.dumps(state, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")

def solver():
    path = REPO / f"weird_captcha_gym/tools/incubator_solvers/{MECHANIC}.py"
    spec = importlib.util.spec_from_file_location("marionette_static_solver", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

def navigate(page, url, difficulty, interaction):
    page.goto(f"{url}/play/?environment={ENVIRONMENT}&attempt=0&difficulty={difficulty}&interaction={interaction}", wait_until="domcontentloaded")
    page.wait_for_function("document.body.dataset.mechanic === 'marionette-checkpoint'")
    expect(page.locator(".ivv")).to_have_attribute("data-interaction", interaction)

def instruction_for(state):
    active = state.get("active_string_indices") or [0, 1, 2, 3]
    acts = len(state["poses"])
    if len(active) == 4 and acts == 3:
        return "Continuously track four moving inspection rings with coupled strings. Progress grows only while every limb is inside and leaks on misses."
    rings = "moving inspection ring" if len(active) == 1 else "moving inspection rings"
    strings = "active string" if len(active) == 1 else "active strings"
    act_text = "moving act" if acts == 1 else "moving acts"
    limb_text = "the active limb is" if len(active) == 1 else "every active limb is"
    return f"Continuously track {len(active)} {rings} with {len(active)} {strings} through {acts} {act_text}. Progress grows only while {limb_text} inside and leaks on misses."

def solve(page, truth, output, label):
    with tempfile.TemporaryDirectory(prefix="marionette-static-truth-") as temporary:
        state = Path(temporary); write(state / "ground_truth.json", truth)
        solver().solve(page, state, output, MECHANIC)
    expect(page.locator(".readout")).to_have_attribute("data-status", "passed", timeout=100_000)
    expect(page.locator(".ivv-verdict.is-pass")).to_be_visible(timeout=5_000)
    page.screenshot(path=str(output / f"{label}-pyodide-pass.png"), full_page=True)
    result = page.evaluate("async () => (await (await fetch('/result')).json())")
    if result.get("browser_grade", {}).get("passed") is not True: raise AssertionError(result)
    return result

def main():
    output = EVIDENCE / "static_target_browser"; site = output / "site"; shots = output / "screenshots"
    site.mkdir(parents=True, exist_ok=True); shots.mkdir(parents=True, exist_ok=True)
    environment = next(item for item in build_catalog()["environments"] if item["id"] == ENVIRONMENT)
    manifest = _export_browser_play(site, {"environments": [environment]})
    bundle = json.loads((site / f"play/challenges/{ENVIRONMENT}.json").read_text())
    handler = partial(QuietHandler, directory=str(site)); server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start(); url = f"http://127.0.0.1:{server.server_port}"
    rows, errors, results = [], [], {}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True); page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
            page.on("pageerror", lambda error: errors.append(str(error)))
            for difficulty in range(1, 6):
                profiles = bundle["difficulty_profiles"][str(difficulty)]["interaction_profiles"]
                simplified, full = profiles["simplified"]["challenges"][0]["public_state"], profiles["full"]["challenges"][0]["public_state"]
                if fingerprint(simplified) != fingerprint(full): raise AssertionError(f"L{difficulty} interaction changes the static world")
                for interaction, state in (("simplified", simplified), ("full", full)):
                    navigate(page, url, difficulty, interaction)
                    instruction = page.locator(".ivv-head p").inner_text()
                    if instruction != instruction_for(state): raise AssertionError((difficulty, interaction, instruction))
                    page.screenshot(path=str(shots / f"d{difficulty}-{interaction}-initial-1280x720.png"), full_page=True)
                    rows.append({"difficulty": difficulty, "interaction": interaction, "challenge_id": state["challenge_id"], "world_fingerprint": fingerprint(state), "visible_instruction": instruction})
            navigate(page, url, 4, "simplified")
            first = page.locator(".ivv").get_attribute("data-challenge-id"); page.locator("#marionette-abandon").click()
            expect(page.locator(".ivv-verdict.is-fresh")).to_be_visible(timeout=100_000)
            second = page.locator(".ivv").get_attribute("data-challenge-id")
            if not first or not second or first == second: raise AssertionError("static Marionette failure did not regenerate")
            page.screenshot(path=str(shots / "d4-simplified-failure-regenerated-1280x720.png"), full_page=True)
            truth = bundle["difficulty_profiles"]["4"]["interaction_profiles"]["simplified"]["challenges"][1]["ground_truth"]
            if second != truth["challenge_id"]: raise AssertionError("static retry chose the wrong bundled challenge")
            results["d4_simplified_recovery"] = solve(page, truth, shots, "d4-simplified-recovery")
            navigate(page, url, 4, "full")
            truth = bundle["difficulty_profiles"]["4"]["interaction_profiles"]["full"]["challenges"][0]["ground_truth"]
            results["d4_full"] = solve(page, truth, shots, "d4-full")
            browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)
    if errors: raise AssertionError(errors)
    summary = {"ok": True, "environment": ENVIRONMENT, "mechanic": MECHANIC, "viewport": [1280, 720], "static_export": manifest, "rendered_profiles": rows, "browser_results": results, "failure_and_recovery": {"initial_challenge_id": first, "fresh_challenge_id": second}}
    write(output / "summary.json", summary); print(json.dumps({"ok": True, "profiles": len(rows), "pyodide_passes": len(results)}, indent=2))
if __name__ == "__main__": main()
