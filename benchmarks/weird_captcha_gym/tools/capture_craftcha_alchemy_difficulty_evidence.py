#!/usr/bin/env python3
"""Capture original/L4 preservation and adjacent Craftcha difficulty evidence."""
from __future__ import annotations

import argparse
import copy
import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "craftcha_alchemy_bench_env"
MATERIALIZER = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
SETUP = BENCHMARK / "shared_scripts" / "setup_task.py"
SERVER = BENCHMARK / "shared_runtime" / "server" / "weird_captcha_server.py"
APP = BENCHMARK / "shared_runtime" / "app"
ORIGINAL_TASK = ENVIRONMENT / "tasks" / "craftcha_alchemy_bench_seed_0001" / "task.json"


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


def normalized(state: dict) -> dict:
    result = copy.deepcopy(state)
    for key in ("task_id", "challenge_id", "control_condition"):
        result.pop(key, None)
    return result


def start_server(task: Path, state_dir: Path, seed: str) -> tuple[subprocess.Popen[bytes], int]:
    subprocess.run(
        [
            "python", "-B", str(SETUP), "--task-json", str(task), "--state-dir", str(state_dir),
            "--seed", seed,
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
            "WEIRD_CAPTCHA_CHALLENGE_SEED": seed,
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
    raise TimeoutError("Craftcha difficulty evidence server did not start")


def capture(browser, task: Path, state_dir: Path, seed: str, screenshot: Path) -> dict:
    process, port = start_server(task, state_dir, seed)
    page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(f"http://127.0.0.1:{port}/?time_mode=paused&start_paused=1", wait_until="networkidle")
        root = page.locator('.alchemy-bench[data-recipe="open"]')
        root.wait_for()
        image = page.screenshot(path=str(screenshot))
        public = json.loads((state_dir / "public_state.json").read_text(encoding="utf-8"))
        truth = json.loads((state_dir / "ground_truth.json").read_text(encoding="utf-8"))
        if errors:
            raise AssertionError(f"browser errors for {task.parent.name}: {errors}")
        recipe = public["recipe"]
        return {
            "image": image,
            "public": public,
            "truth": truth,
            "challenge_id": root.get_attribute("data-challenge-id"),
            "rendered_interaction": root.get_attribute("data-interaction"),
            "recipe_code": page.locator(".alchemy-recipe-shutter .recipe-card header b").inner_text(),
            "step_count": recipe["step_count"],
            "branch_lengths": [len(branch["steps"]) for branch in recipe["branches"]],
            "active_station_ids": public["active_station_ids"],
            "recipe_window_ms": public["recipe_window_ms"],
            "replay_window_ms": public["replay_window_ms"],
            "memory": {
                "initial": public["memory_charge_initial"],
                "cost": public["memory_replay_cost"],
            },
        }
    finally:
        page.close()
        stop(process)


def evidence_record(capture_result: dict, screenshot: Path) -> dict:
    return {
        "screenshot": screenshot.name,
        "challenge_id": capture_result["challenge_id"],
        "rendered_interaction": capture_result["rendered_interaction"],
        "recipe_code": capture_result["recipe_code"],
        "step_count": capture_result["step_count"],
        "branch_lengths": capture_result["branch_lengths"],
        "active_station_ids": capture_result["active_station_ids"],
        "recipe_window_ms": capture_result["recipe_window_ms"],
        "replay_window_ms": capture_result["replay_window_ms"],
        "memory": capture_result["memory"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ENVIRONMENT / "evidence_docs" / "difficulty_comparison")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="craftcha-difficulty-evidence-") as temporary_name, sync_playwright() as playwright:
        temporary = Path(temporary_name)
        materialized_root = temporary / "materialized"
        subprocess.run(
            ["python", str(MATERIALIZER), "--environment", ENVIRONMENT.name, "--output-root", str(materialized_root)],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        tasks = materialized_root / ENVIRONMENT.name / "tasks"
        browser = playwright.chromium.launch(headless=True)
        try:
            baseline_seed = "craftcha-original-l4-baseline-evidence"
            original_path = args.out_dir / "original-uncontrolled-open.png"
            l4_path = args.out_dir / "baseline-l4-full-open.png"
            original = capture(browser, ORIGINAL_TASK, temporary / "original", baseline_seed, original_path)
            l4 = capture(
                browser,
                tasks / "craftcha_alchemy_bench_d4_full_seed_0001" / "task.json",
                temporary / "l4",
                baseline_seed,
                l4_path,
            )

            adjacent: dict[str, dict] = {}
            adjacent_seed = "craftcha-adjacent-difficulty-evidence"
            for level in (3, 4, 5):
                path = args.out_dir / f"adjacent-l{level}-full-open.png"
                adjacent[str(level)] = capture(
                    browser,
                    tasks / f"craftcha_alchemy_bench_d{level}_full_seed_0001" / "task.json",
                    temporary / f"adjacent-l{level}",
                    adjacent_seed,
                    path,
                )
        finally:
            browser.close()

    public_equal = normalized(original["public"]) == normalized(l4["public"])
    truth_equal = normalized(original["truth"]) == normalized(l4["truth"])
    image_equal = original["image"] == l4["image"]
    if not public_equal or not truth_equal or not image_equal:
        raise AssertionError(
            "uncontrolled original and L4/full did not preserve the same seeded generated world and visible recipe"
        )
    summary = {
        "environment": ENVIRONMENT.name,
        "baseline": {
            "difficulty": 4,
            "interaction": "full",
            "seed": baseline_seed,
            "original": evidence_record(original, original_path),
            "controlled_l4": evidence_record(l4, l4_path),
            "normalized_public_state_equal": public_equal,
            "normalized_ground_truth_equal": truth_equal,
            "visible_recipe_screenshot_byte_equal": image_equal,
        },
        "adjacent_difficulties": {
            "seed": adjacent_seed,
            **{
                str(level): evidence_record(
                    adjacent[str(level)], args.out_dir / f"adjacent-l{level}-full-open.png"
                )
                for level in (3, 4, 5)
            },
        },
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
