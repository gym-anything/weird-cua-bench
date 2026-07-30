#!/usr/bin/env python3
"""Exercise every Portal Freight control condition in live and paused time modes.

The probe launches only temporary loopback servers and separate persistent
headless Chromium profiles.  It checks the shared clock's model-delay and
resume-for-action behavior using the rendered Portal Freight controls; it does
not use a user's browser, desktop, profile, or foreground input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "portal_freight_oversized_parcel_env"
MECHANIC = "portal_freight_oversized_parcel"
MATERIALIZER = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
SETUP = BENCHMARK / "shared_scripts" / "setup_task.py"
SERVER = BENCHMARK / "shared_runtime" / "server" / "weird_captcha_server.py"
APP = BENCHMARK / "shared_runtime" / "app"
WORLD_KEYS = ("canvas", "room", "walls", "tools", "controls", "parcel", "delivery", "qualification")


def reserve_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def world_fingerprint(state: dict) -> str:
    world = {key: state.get(key) for key in WORLD_KEYS}
    return hashlib.sha256(
        json.dumps(world, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def start_server(task_json: Path, state_dir: Path, seed: str) -> tuple[subprocess.Popen[bytes], int]:
    subprocess.run(
        ["python", "-B", str(SETUP), "--task-json", str(task_json), "--state-dir", str(state_dir), "--seed", seed],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    port = reserve_port()
    process = subprocess.Popen(
        [
            "python", "-B", str(SERVER), "--host", "127.0.0.1", "--port", str(port),
            "--app-dir", str(APP), "--state-dir", str(state_dir),
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "WEIRD_CAPTCHA_CHALLENGE_SEED": seed,
            "WEIRD_CAPTCHA_CHEAT_PASSWORD": "portal-freight-realtime-matrix",
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5).read()
            return process, port
        except Exception:  # noqa: BLE001 - the loop intentionally handles process startup races.
            time.sleep(0.1)
    process.kill()
    raise TimeoutError(f"Portal Freight realtime server did not start on {port}")


def stop_server(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()


def status(page) -> dict:
    return page.evaluate("() => WeirdCaptchaTime.status()")


def canvas_click_on_a_east_frame(page, state: dict) -> None:
    """Place BLUE using the full visible canvas surface, just inside A-east."""
    canvas = page.locator("#freight-canvas")
    box = canvas.bounding_box()
    if box is None:
        raise AssertionError("full Portal Freight canvas has no visible bounds")
    room = state["room"]
    source_lane = float(state["tools"]["A"]["origin"][2])
    local_x = 34.0 + (float(room["width"]) - 0.12) / float(room["width"]) * 375.0
    local_y = 48.0 + source_lane / float(room["depth"]) * 365.0
    page.mouse.click(
        float(box["x"]) + local_x / 900.0 * float(box["width"]),
        float(box["y"]) + local_y / 468.0 * float(box["height"]),
    )


def apply_visible_action(page, interaction: str, state: dict) -> str:
    if interaction == "simplified":
        page.locator('[data-aim="15"]').click()
        return "proxy aim +15°"
    canvas_click_on_a_east_frame(page, state)
    expect(page.locator("#blue-ledger")).to_contain_text("A/east")
    return "direct canvas BLUE placement"


def capture_condition(
    playwright,
    *,
    task_json: Path,
    level: int,
    interaction: str,
    mode: str,
    temporary: Path,
    output: Path,
) -> dict:
    label = f"l{level}-{interaction}-{mode}"
    state_dir = temporary / f"state-{label}"
    profile_dir = temporary / f"fresh-profile-{label}"
    state_dir.mkdir()
    seed = f"portal-freight-realtime-l{level}"
    process, port = start_server(task_json, state_dir, seed)
    context = playwright.chromium.launch_persistent_context(
        str(profile_dir),
        headless=True,
        viewport={"width": 1280, "height": 720},
        device_scale_factor=1,
    )
    page = context.new_page()
    errors: list[str] = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(
            f"http://127.0.0.1:{port}/?time_mode={mode}&start_paused=1",
            wait_until="networkidle",
        )
        root = page.locator('.portal-freight[data-active="true"]')
        expect(root).to_be_visible(timeout=8_000)
        expect(root).to_have_attribute("data-interaction", interaction)
        state = read_json(state_dir / "public_state.json")
        output.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(output / f"{label}-initial.png"), full_page=True)

        initial = status(page)
        if initial["mode"] != mode or initial["state"] != "paused":
            raise AssertionError(f"{label} did not start in the requested paused observation state: {initial}")
        if mode == "live":
            page.evaluate("() => WeirdCaptchaTime.resume()")
        before_delay = status(page)
        page.wait_for_timeout(420)
        after_delay = status(page)
        page.screenshot(path=str(output / f"{label}-after-model-delay.png"), full_page=True)
        delay_delta = float(after_delay["task_time_ms"]) - float(before_delay["task_time_ms"])
        if mode == "live" and delay_delta < 300:
            raise AssertionError(f"{label} live task clock did not advance through model delay: {delay_delta}")
        if mode == "paused" and abs(delay_delta) > 2:
            raise AssertionError(f"{label} paused task clock advanced through model delay: {delay_delta}")

        if mode == "paused":
            page.evaluate("() => WeirdCaptchaTime.resume()")
        action_before = status(page)
        action_description = apply_visible_action(page, interaction, state)
        page.wait_for_timeout(90)
        if mode == "paused":
            page.evaluate("() => WeirdCaptchaTime.pause()")
        action_after = status(page)
        page.screenshot(path=str(output / f"{label}-action.png"), full_page=True)
        action_delta = float(action_after["task_time_ms"]) - float(action_before["task_time_ms"])
        if action_delta < 60:
            raise AssertionError(f"{label} action did not run while task time advanced: {action_delta}")
        if mode == "paused" and action_after["state"] != "paused":
            raise AssertionError(f"{label} did not return to paused after its action: {action_after}")
        if errors:
            raise AssertionError(f"{label} browser errors: {errors}")
        return {
            "level": level,
            "interaction": interaction,
            "mode": mode,
            "seed": seed,
            "world_fingerprint": world_fingerprint(state),
            "initial_clock": initial,
            "delay_before": before_delay,
            "delay_after": after_delay,
            "delay_task_time_delta_ms": delay_delta,
            "action": action_description,
            "action_before": action_before,
            "action_after": action_after,
            "action_task_time_delta_ms": action_delta,
            "screenshots": [
                f"{label}-initial.png",
                f"{label}-after-model-delay.png",
                f"{label}-action.png",
            ],
            "console_errors": errors,
        }
    finally:
        page.close()
        context.close()
        stop_server(process)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ENVIRONMENT / "evidence_docs" / "realtime_matrix",
    )
    args = parser.parse_args()
    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="portal-freight-realtime-matrix-") as temporary_name:
        temporary = Path(temporary_name)
        materialized = temporary / "materialized"
        subprocess.run(
            ["python", str(MATERIALIZER), "--environment", ENVIRONMENT.name, "--output-root", str(materialized)],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        tasks = materialized / ENVIRONMENT.name / "tasks"
        evidence: dict[str, object] = {
            "environment": ENVIRONMENT.name,
            "mechanic": MECHANIC,
            "headless_isolated": True,
            "loopback_only": True,
            "fresh_temporary_profile_per_condition": True,
            "shared_real_time": read_json(ENVIRONMENT / "controls.json")["real_time"],
            "conditions": {},
        }
        with sync_playwright() as playwright:
            for level in range(1, 6):
                for interaction in ("simplified", "full"):
                    task_json = tasks / f"{MECHANIC}_d{level}_{interaction}_seed_0001" / "task.json"
                    for mode in ("live", "paused"):
                        record = capture_condition(
                            playwright,
                            task_json=task_json,
                            level=level,
                            interaction=interaction,
                            mode=mode,
                            temporary=temporary,
                            output=output,
                        )
                        evidence["conditions"][f"l{level}-{interaction}-{mode}"] = record

    conditions = evidence["conditions"]
    for level in range(1, 6):
        records = [
            conditions[f"l{level}-{interaction}-{mode}"]
            for interaction in ("simplified", "full")
            for mode in ("live", "paused")
        ]
        fingerprints = {record["world_fingerprint"] for record in records}
        if len(fingerprints) != 1:
            raise AssertionError(f"L{level} real-time and interaction checks used different generated worlds: {fingerprints}")
    output_summary = output / "summary.json"
    output_summary.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
