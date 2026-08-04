#!/usr/bin/env python3
"""Capture the two Craftcha interaction surfaces on one generated world."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "craftcha_alchemy_bench_env"
MATERIALIZER = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
SETUP = BENCHMARK / "shared_scripts" / "setup_task.py"
SERVER = BENCHMARK / "shared_runtime" / "server" / "weird_captcha_server.py"
APP = BENCHMARK / "shared_runtime" / "app"


def reserve_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def stop(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()


def normalized_world(public_state: dict) -> dict:
    world = dict(public_state)
    # The interaction selector is the only control condition intentionally
    # omitted, along with the materialized task identifier: the generated
    # world must not depend on its input surface.
    condition = dict(world.pop("control_condition"))
    condition.pop("interaction")
    world["control_condition_without_interaction"] = condition
    world.pop("task_id", None)
    return world


def start_server(task: Path, state_dir: Path) -> tuple[subprocess.Popen[bytes], int]:
    subprocess.run(
        [
            "python", "-B", str(SETUP), "--task-json", str(task), "--state-dir", str(state_dir),
            "--seed", "craftcha-same-world-evidence",
        ],
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
            "WEIRD_CAPTCHA_TIME_MODE": "paused",
            "WEIRD_CAPTCHA_START_PAUSED": "1",
            "WEIRD_CAPTCHA_CHALLENGE_SEED": "craftcha-same-world-evidence",
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5).read()
            return process, port
        except Exception:  # noqa: BLE001 - the health endpoint is intentionally retried.
            time.sleep(0.1)
    process.kill()
    raise TimeoutError("Craftcha interaction-comparison server did not start")


def capture(browser, task: Path, temporary: Path, interaction: str, out_dir: Path) -> dict:
    state_dir = temporary / interaction
    process, port = start_server(task, state_dir)
    page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(f"http://127.0.0.1:{port}/?time_mode=paused&start_paused=1", wait_until="networkidle")
        root = page.locator(f'.alchemy-bench[data-interaction="{interaction}"]')
        root.wait_for()
        page.screenshot(path=str(out_dir / f"{interaction}-same-world-initial.png"))
        public_state = json.loads((state_dir / "public_state.json").read_text(encoding="utf-8"))
        (out_dir / f"{interaction}-public-state.json").write_text(
            json.dumps(public_state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        # The action surfaces are only exposed once the visible recipe shutter
        # closes.  Advance the shared clock, then freeze it before interacting.
        page.evaluate("() => WeirdCaptchaTime.resume()")
        page.wait_for_selector('.alchemy-bench[data-recipe="sealed"]', timeout=9_000)
        page.evaluate("() => WeirdCaptchaTime.pause()")
        page.screenshot(path=str(out_dir / f"{interaction}-recipe-sealed.png"))

        first_step = public_state["recipe"]["branches"][0]["steps"][0]
        station_id = str(first_step["station_id"])
        item = page.locator('.alchemy-item[data-slot="0"]')
        station = page.locator(f'[data-alchemy-station="{station_id}"]')
        if interaction == "simplified":
            item.click()
            if root.get_attribute("data-proxy-selected") != "true":
                raise AssertionError("simplified click did not visibly select the material")
            page.screenshot(path=str(out_dir / "simplified-material-selected.png"))
            station.click(position={"x": 80, "y": 70})
            action_evidence = {
                "operation": "click inventory material, then click machine",
                "station": station_id,
                "source_slot_filled_after": page.locator('[data-alchemy-slot="0"]').get_attribute("data-filled"),
                "station_loaded_after": station.get_attribute("data-loaded"),
            }
            page.screenshot(path=str(out_dir / "simplified-material-placed.png"))
        else:
            item_box = item.bounding_box()
            station_box = station.bounding_box()
            if item_box is None or station_box is None:
                raise AssertionError("full drag surface did not expose source and machine bounds")
            start = (item_box["x"] + item_box["width"] / 2, item_box["y"] + item_box["height"] / 2)
            end = (station_box["x"] + station_box["width"] / 2, station_box["y"] + station_box["height"] / 2)
            # Physical drag duration is measured from the shared task clock,
            # so resume for the deliberate gesture and freeze again after it.
            page.evaluate("() => WeirdCaptchaTime.resume()")
            page.mouse.move(*start)
            page.mouse.down()
            page.wait_for_timeout(40)
            for ratio in (.16, .32, .5):
                page.mouse.move(start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio)
                page.wait_for_timeout(20)
            page.screenshot(path=str(out_dir / "full-physical-drag-in-progress.png"))
            for ratio in (.67, .84, 1):
                page.mouse.move(start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio)
                page.wait_for_timeout(20)
            page.wait_for_timeout(40)
            page.mouse.up()
            page.evaluate("() => WeirdCaptchaTime.pause()")
            action_evidence = {
                "operation": "direct physical pointer drag from inventory material to machine",
                "station": station_id,
                "source_slot_filled_after": page.locator('[data-alchemy-slot="0"]').get_attribute("data-filled"),
                "station_loaded_after": station.get_attribute("data-loaded"),
            }
            page.screenshot(path=str(out_dir / "full-material-placed.png"))
        if action_evidence["source_slot_filled_after"] != "false" or action_evidence["station_loaded_after"] != "true":
            raise AssertionError(f"{interaction} transfer was not visibly accepted: {action_evidence}")
        if errors:
            raise AssertionError(f"{interaction} browser errors: {errors}")
        return {
            "challenge_id": root.get_attribute("data-challenge-id"),
            "interaction": root.get_attribute("data-interaction"),
            "recipe_code": page.locator(".alchemy-recipe-shutter .recipe-card header b").inner_text(),
            "world": normalized_world(public_state),
            "visible_action": action_evidence,
        }
    finally:
        page.close()
        stop(process)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ENVIRONMENT / "evidence_docs" / "interaction_comparison")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="craftcha-interaction-") as temporary_name, sync_playwright() as playwright:
        temporary = Path(temporary_name)
        subprocess.run(
            ["python", str(MATERIALIZER), "--environment", ENVIRONMENT.name, "--output-root", str(temporary / "materialized")],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        tasks = temporary / "materialized" / ENVIRONMENT.name / "tasks"
        browser = playwright.chromium.launch(headless=True)
        try:
            records = {
                interaction: capture(
                    browser,
                    tasks / f"craftcha_alchemy_bench_d4_{interaction}_seed_0001" / "task.json",
                    temporary,
                    interaction,
                    args.out_dir,
                )
                for interaction in ("simplified", "full")
            }
        finally:
            browser.close()
    if records["simplified"]["world"] != records["full"]["world"]:
        raise AssertionError("simplified and full surfaces changed the generated world")
    summary = {
        "environment": ENVIRONMENT.name,
        "difficulty": 4,
        "same_generated_world": True,
        "challenge_id": records["full"]["challenge_id"],
        "recipe_code": records["full"]["recipe_code"],
        "interactions": {
            interaction: {
                "rendered_interaction": record["interaction"],
                "challenge_id": record["challenge_id"],
                "recipe_code": record["recipe_code"],
                "visible_action": record["visible_action"],
            }
            for interaction, record in records.items()
        },
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
