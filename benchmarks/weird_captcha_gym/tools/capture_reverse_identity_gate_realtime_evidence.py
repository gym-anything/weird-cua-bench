#!/usr/bin/env python3
"""Capture visible live and paused phase observations for Four-Tab Robot Handshake.

The browser run is deliberately isolated: Chromium is headless, each mode gets
a new in-memory context, and the task server is bound only to loopback.  The
script never uses a desktop browser profile or an operating-system input API.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page, expect, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
BENCH_ROOT = ROOT / "benchmarks" / "weird_captcha_gym"
ENV_ROOT = BENCH_ROOT / "environments" / "reverse_identity_gate_env"
MATERIALIZER = BENCH_ROOT / "tools" / "materialize_controlled_tasks.py"
SMOKE = BENCH_ROOT / "tools" / "smoke_controlled_interaction_ui.py"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_smoke_module():
    specification = importlib.util.spec_from_file_location("reverse_identity_gate_smoke", SMOKE)
    if specification is None or specification.loader is None:
        raise ImportError(f"cannot import smoke helpers from {SMOKE}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def controlled_l4(tasks_root: Path, interaction: str) -> Path:
    matches: list[Path] = []
    for task_path in tasks_root.glob("*/task.json"):
        condition = (read_json(task_path).get("metadata") or {}).get("control_condition") or {}
        if condition.get("difficulty") == 4 and condition.get("interaction") == interaction:
            matches.append(task_path)
    if len(matches) != 1:
        raise AssertionError(f"expected one materialized L4/{interaction} task, found {matches}")
    return matches[0]


def clock(page: Page) -> dict[str, Any]:
    return page.evaluate("() => WeirdCaptchaTime.status()")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observation_settings() -> dict[str, int]:
    settings = read_json(ENV_ROOT / "controls.json")["real_time"]
    window = int(settings["observation_window_ms"])
    frames = int(settings["frames_per_observation"])
    if window <= 0 or frames < 2:
        raise AssertionError(f"reverse identity gate needs a positive multi-frame observation: {settings}")
    return {
        "play_time_seconds": int(settings["play_time_seconds"]),
        "observation_window_ms": window,
        "frames_per_observation": frames,
    }


def deploy_l4_tabs(context: BrowserContext, master: Page, state: dict[str, Any]) -> dict[int, Page]:
    tabs: dict[int, Page] = {}
    for station in sorted(state["stations"], key=lambda item: int(item["id"])):
        station_id = int(station["id"])
        with context.expect_page(timeout=5_000) as opened:
            master.locator(f'[data-deploy="{station_id}"]').click()
        tab = opened.value
        expect(tab.locator(f'.robot-station[data-station-page="{station_id}"]')).to_be_visible()
        tabs[station_id] = tab
    return tabs


def visible_phase_observation(
    master: Page,
    tab: Page,
    output: Path,
    mode: str,
    settings: dict[str, int],
    interaction: str,
) -> dict[str, Any]:
    """Capture the configured limb-tab observation frames, then test the delay."""
    output.mkdir(parents=True, exist_ok=True)
    start = clock(master)
    if start["state"] != "paused":
        raise AssertionError(f"expected initially paused shared clock, got {start}")
    master.evaluate("() => WeirdCaptchaTime.resume()")
    expect(tab.locator('.robot-station[data-active="true"]')).to_be_visible()

    frames: list[dict[str, Any]] = []
    frame_count = settings["frames_per_observation"]
    frame_gap_ms = settings["observation_window_ms"] / (frame_count - 1)
    observation_start = clock(master)
    for index in range(frame_count):
        target_offset = index * frame_gap_ms
        before_frame = clock(master)
        elapsed = float(before_frame["task_time_ms"]) - float(observation_start["task_time_ms"])
        if target_offset > elapsed:
            master.wait_for_timeout(target_offset - elapsed)
            before_frame = clock(master)
        image = output / f"frame-{index:02d}.png"
        tab.screenshot(path=str(image))
        frames.append({
            "index": index,
            "target_offset_ms": target_offset,
            "task_time_ms": before_frame["task_time_ms"],
            "clock_state": before_frame["state"],
            "png_sha256": digest(image),
        })
    end_observation = clock(master)

    # A paused agent receives the captured observation and then the shared
    # clock freezes while it deliberates.  A live agent keeps running.
    if mode == "paused":
        master.evaluate("() => WeirdCaptchaTime.pause()")
    before_delay = clock(master)
    tab.screenshot(path=str(output / "after-observation.png"))
    master.wait_for_timeout(1_000)
    after_delay = clock(master)
    tab.screenshot(path=str(output / "after-model-delay.png"))
    delay_delta = float(after_delay["task_time_ms"]) - float(before_delay["task_time_ms"])
    if mode == "live" and delay_delta < 700:
        raise AssertionError(f"live clock did not advance through model delay: {delay_delta}ms")
    if mode == "paused" and abs(delay_delta) > 2:
        raise AssertionError(f"paused clock advanced through model delay: {delay_delta}ms")

    # Exercise the selected visible input surface after the observation. In
    # paused mode it must explicitly resume for the action and pause again.
    if mode == "paused":
        master.evaluate("() => WeirdCaptchaTime.resume()")
    action_before = clock(master)
    contact = tab.locator("#station-contact")
    if interaction == "simplified":
        tab.locator('[data-station-drive="1"]').click()
        contact.click()
        master.wait_for_timeout(180)
        contact.click()
        action_sources = ["direction_button", "contact_toggle"]
    else:
        box = contact.bounding_box()
        if box is None:
            raise AssertionError("active limb contact control has no visible box")
        tab.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        tab.keyboard.down("d")
        tab.mouse.down()
        master.wait_for_timeout(180)
        tab.mouse.up()
        tab.keyboard.up("d")
        action_sources = ["keyboard", "pointer_hold"]
    if mode == "paused":
        master.evaluate("() => WeirdCaptchaTime.pause()")
    action_after = clock(master)
    tab.screenshot(path=str(output / "full-input-after-observation.png"))
    action_delta = float(action_after["task_time_ms"]) - float(action_before["task_time_ms"])
    if action_delta < 100:
        raise AssertionError(f"shared task clock did not run for visible {interaction} input: {action_delta}ms")
    if mode == "paused" and action_after["state"] != "paused":
        raise AssertionError(f"paused run did not return to paused after input: {action_after}")

    return {
        "observation_settings": settings,
        "initial_clock": start,
        "frames": frames,
        "after_observation_clock": end_observation,
        "before_model_delay_clock": before_delay,
        "after_model_delay_clock": after_delay,
        "delay_task_time_delta_ms": delay_delta,
        "selected_input_before_clock": action_before,
        "selected_input_after_clock": action_after,
        "selected_input_task_time_delta_ms": action_delta,
        "selected_input_sources": action_sources,
    }


def capture_mode(
    smoke: Any,
    browser: Any,
    task: Path,
    mode: str,
    scratch: Path,
    output: Path,
    settings: dict[str, int],
    interaction: str,
) -> dict[str, Any]:
    state_dir = scratch / mode
    state_dir.mkdir()
    process, port = smoke.start_server(task, "reverse_identity_gate", interaction, state_dir)
    context = browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    master = context.new_page()
    errors: list[str] = []
    master.on("pageerror", lambda error: errors.append(str(error)))
    try:
        # Keep the server's initial task available to the page while avoiding a
        # state-file read/write race with setup.  This is the same loopback-only
        # startup sequence used by the controlled browser smoke.
        current_task = state_dir / "current_task.json"
        task_text = current_task.read_text(encoding="utf-8")
        current_task.unlink()
        try:
            master.goto(
                f"http://127.0.0.1:{port}/?time_mode={mode}&start_paused=1",
                wait_until="networkidle",
            )
        finally:
            current_task.write_text(task_text, encoding="utf-8")
        expect(master.locator(f'.robot-master[data-interaction="{interaction}"]')).to_be_visible()
        state = read_json(state_dir / "public_state.json")
        master.screenshot(path=str(output / "master-before-deployment.png"))
        tabs = deploy_l4_tabs(context, master, state)
        master.screenshot(path=str(output / "master-four-tabs-online.png"))
        active_station = int(state["stages"][0]["station"])
        evidence = visible_phase_observation(master, tabs[active_station], output, mode, settings, interaction)
        if errors:
            raise AssertionError(f"browser page errors in {mode}: {errors}")
        evidence.update({
            "mode": mode,
            "task": task.parent.name,
            "initial_active_station": active_station,
            "station_count": len(state["stations"]),
            "relay_count": len(state["stages"]),
            "browser": "Chromium headless with a new in-memory context",
            "server": "127.0.0.1 loopback only",
        })
        return evidence
    finally:
        context.close()
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ENV_ROOT / "evidence_docs" / "realtime_observations")
    parser.add_argument("--interaction", choices=("simplified", "full"))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    smoke = load_smoke_module()
    settings = observation_settings()
    interaction = args.interaction or str(read_json(ENV_ROOT / "controls.json")["baseline"]["interaction"])

    with tempfile.TemporaryDirectory(prefix="reverse-identity-gate-realtime-") as temporary_name:
        scratch = Path(temporary_name)
        subprocess.run(
            ["python", "-B", str(MATERIALIZER), "--environment", ENV_ROOT.name, "--output-root", str(scratch / "materialized")],
            cwd=ROOT,
            check=True,
        )
        task = controlled_l4(scratch / "materialized" / ENV_ROOT.name / "tasks", interaction)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                evidence = {
                    "environment": ENV_ROOT.name,
                    "mechanic": "reverse_identity_gate",
                    "difficulty": 4,
                    "interaction": interaction,
                    "modes": {
                        mode: capture_mode(
                            smoke,
                            browser,
                            task,
                            mode,
                            scratch,
                            args.out_dir / mode,
                            settings,
                            interaction,
                        )
                        for mode in ("live", "paused")
                    },
                }
            finally:
                browser.close()

    (args.out_dir / "realtime-observations.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
