#!/usr/bin/env python3
"""Capture paused evaluator-cycle evidence for Rorschach Fixed Rubric.

This uses the same local loopback time-control protocol as
``run_realtime_evaluation.py``: resume for one visible action, issue
``settle_pause``, and wait for the task's registered finite action to settle.
It launches a headless Chromium process with a fresh context and temporary
state/materialized-task directories; it never uses a user browser or profile.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "rorschach_fixed_rubric_env"
APP_DIR = BENCHMARK / "shared_runtime" / "app"
SERVER = BENCHMARK / "shared_runtime" / "server" / "weird_captcha_server.py"
SETUP = BENCHMARK / "shared_scripts" / "setup_task.py"
MATERIALIZER = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
SOLVER_PATH = BENCHMARK / "tools" / "incubator_solvers" / "rorschach_fixed_rubric.py"
MECHANIC = "rorschach_fixed_rubric"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture paused resume/action/settle_pause evidence for Rorschach Fixed Rubric."
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object in {path}")
    return value


def reserve_port() -> int:
    with socket.socket() as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def start_server(task_json: Path, state_dir: Path) -> tuple[subprocess.Popen, int]:
    subprocess.run(
        [
            sys.executable,
            "-B",
            str(SETUP),
            "--task-json",
            str(task_json),
            "--state-dir",
            str(state_dir),
            "--seed",
            "rorschach-paused-evaluator-cycle",
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    port = reserve_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-B",
            str(SERVER),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--app-dir",
            str(APP_DIR),
            "--state-dir",
            str(state_dir),
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 8
    while time.time() < deadline:
        try:
            import urllib.request

            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5).read()
            return process, port
        except Exception:
            time.sleep(0.05)
    process.kill()
    raise RuntimeError("Rorschach loopback server did not start")


def task_for(tasks_root: Path, interaction: str) -> Path:
    matches = []
    for path in tasks_root.glob("*/task.json"):
        condition = (read_json(path).get("metadata") or {}).get("control_condition") or {}
        if int(condition.get("difficulty") or 0) == 4 and condition.get("interaction") == interaction:
            matches.append(path)
    if len(matches) != 1:
        raise AssertionError(f"expected one L4 {interaction} task, got {matches}")
    return matches[0]


def clock(page) -> dict[str, Any]:
    return page.evaluate("() => WeirdCaptchaTime.status()")


def command(page, name: str) -> dict[str, Any]:
    return page.evaluate(
        """async name => {
          const response = await fetch('/time-control', {
            method: 'POST', headers: {'content-type': 'application/json'},
            body: JSON.stringify({command: name}), cache: 'no-store',
          });
          if (!response.ok) throw new Error(`time command ${name} failed: ${response.status}`);
          return await response.json();
        }""",
        name,
    )


def wait_for_clock(page, expression: str, *, timeout: int = 8_000) -> None:
    page.wait_for_function(expression, timeout=timeout)


def run_accepted_probe(
    page,
    truth: dict[str, Any],
    public_state: dict[str, Any],
    solver,
    interaction: str,
    out_dir: Path,
) -> dict[str, Any]:
    blot_id = str(truth["blot_rects"][0]["id"])
    tool = str(truth["required_tools"][0])
    initial = clock(page)
    if initial["state"] != "paused" or initial["pending_action_count"] != 0:
        raise AssertionError(f"{interaction}: task did not begin in paused inference state: {initial}")
    page.screenshot(path=str(out_dir / f"paused-{interaction}-initial.png"))

    command(page, "resume")
    wait_for_clock(page, "() => WeirdCaptchaTime.status().state === 'running'")
    page.locator(f'.ink-card[data-blot-id="{blot_id}"]').click()
    if interaction == "simplified":
        page.locator(f'.ink-proxy-tool[data-tool="{tool}"]').click()
    elif tool == "FOLD":
        solver._fold(page)
    elif tool == "PRESSURE":
        solver._pressure(page, int(truth["pressure_min_ms"]) + 80)
    elif tool == "COOL":
        page.locator(".ink-cool").click()
    else:
        raise AssertionError(f"unsupported material tool {tool!r}")

    key = f"{blot_id}|{tool}"
    page.wait_for_function(
        """() => window.inkblotMaterialModel.active === true
          && WeirdCaptchaTime.status().state === 'running'
          && WeirdCaptchaTime.status().pending_action_count === 1""",
        timeout=3_000,
    )
    active = clock(page)
    page.screenshot(path=str(out_dir / f"paused-{interaction}-accepted-active.png"))

    command(page, "settle_pause")
    page.wait_for_function(
        """key => {
          const model = window.inkblotMaterialModel;
          const time = WeirdCaptchaTime.status();
          return model.active === false
            && model.observations.has(key)
            && time.state === 'paused'
            && time.pending_action_count === 0;
        }""",
        arg=key,
        timeout=10_000,
    )
    settled = clock(page)
    page.screenshot(path=str(out_dir / f"paused-{interaction}-cycle-complete.png"))

    expected_cycle_ms = int(truth["ticks_per_cycle"]) * int(public_state["tick_ms"])
    if settled["task_time_ms"] - active["task_time_ms"] < expected_cycle_ms * 0.8:
        raise AssertionError(
            f"{interaction}: settle_pause returned before the response cycle ran: "
            f"active={active['task_time_ms']} settled={settled['task_time_ms']} expected≈{expected_cycle_ms}"
        )

    page.wait_for_timeout(650)
    frozen = clock(page)
    if abs(float(frozen["task_time_ms"]) - float(settled["task_time_ms"])) > 2:
        raise AssertionError(f"{interaction}: paused inference hold advanced task time: {settled} -> {frozen}")
    page.screenshot(path=str(out_dir / f"paused-{interaction}-post-settle-hold.png"))
    return {
        "interaction": interaction,
        "blot_id": blot_id,
        "tool": tool,
        "response_key": key,
        "initial_clock": initial,
        "active_clock": active,
        "settled_clock": settled,
        "post_settle_hold_clock": frozen,
        "expected_cycle_ms": expected_cycle_ms,
        "observations_after_settle": page.evaluate("() => window.inkblotMaterialModel.observations.size"),
        "ticks_after_settle": page.evaluate("() => window.inkblotMaterialModel.tickTotal"),
    }


def main() -> None:
    args = parse_args()
    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    materializer = load_module("rorschach_realtime_materializer", MATERIALIZER)
    solver = load_module("rorschach_realtime_solver", SOLVER_PATH)
    with tempfile.TemporaryDirectory(prefix="rorschach-paused-evaluator-") as temp_name:
        temp_root = Path(temp_name)
        materializer.materialize_environment(ENVIRONMENT, temp_root / "materialized")
        tasks_root = temp_root / "materialized" / ENVIRONMENT.name / "tasks"
        resolution = read_json(ENVIRONMENT / "env.json")["observation"][0]["resolution"]
        runs: dict[str, Any] = {}
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for interaction in ("simplified", "full"):
                state_dir = temp_root / interaction
                state_dir.mkdir()
                process, port = start_server(task_for(tasks_root, interaction), state_dir)
                context = browser.new_context(
                    viewport={"width": int(resolution[0]), "height": int(resolution[1])},
                    device_scale_factor=1,
                )
                page = context.new_page()
                page_errors: list[str] = []
                console_errors: list[str] = []
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
                try:
                    current_task = state_dir / "current_task.json"
                    current_task_text = current_task.read_text(encoding="utf-8")
                    current_task.unlink()
                    try:
                        page.goto(
                            f"http://127.0.0.1:{port}/?time_mode=paused&start_paused=1&time_control=1",
                            wait_until="domcontentloaded",
                        )
                    finally:
                        current_task.write_text(current_task_text, encoding="utf-8")
                    expect(page.locator(f'[data-interaction="{interaction}"]')).to_be_visible()
                    public_state = read_json(state_dir / "public_state.json")
                    (output / f"public_state_{interaction}.json").write_text(
                        json.dumps(public_state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                    )
                    truth = read_json(state_dir / "ground_truth.json")
                    run = run_accepted_probe(page, truth, public_state, solver, interaction, output)
                    if run["observations_after_settle"] != 1 or run["ticks_after_settle"] != int(truth["ticks_per_cycle"]):
                        raise AssertionError(f"{interaction}: settled response was not fully archived: {run}")
                    if page_errors or console_errors:
                        raise AssertionError(f"{interaction}: browser errors page={page_errors}; console={console_errors}")
                    run["browser_errors"] = {"page": page_errors, "console": console_errors}
                    runs[interaction] = run
                finally:
                    page.close()
                    context.close()
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
            browser.close()
    summary = {
        "mechanic": MECHANIC,
        "difficulty": 4,
        "time_mode": "paused",
        "protocol": "resume one accepted visible action, then the shared settle_pause command",
        "runs": runs,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
