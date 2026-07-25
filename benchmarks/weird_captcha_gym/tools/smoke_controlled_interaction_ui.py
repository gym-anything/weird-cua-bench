#!/usr/bin/env python3
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

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
BENCH_ROOT = ROOT / "benchmarks" / "weird_captcha_gym"
APP_DIR = BENCH_ROOT / "shared_runtime" / "app"
SERVER = BENCH_ROOT / "shared_runtime" / "server" / "weird_captcha_server.py"
SETUP = BENCH_ROOT / "shared_scripts" / "setup_task.py"
MATERIALIZER = BENCH_ROOT / "tools" / "materialize_controlled_tasks.py"
HELPERS = BENCH_ROOT / "shared_runtime" / "verifier_helpers.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test both interaction modes at an environment's baseline difficulty.")
    parser.add_argument("--environment", required=True, help="Environment folder name such as input_lag_forklift_env")
    parser.add_argument("--out-dir", type=Path)
    return parser.parse_args()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def reserve_port() -> int:
    with socket.socket() as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def start_server(task_json: Path, mechanic: str, interaction: str, state_dir: Path) -> tuple[subprocess.Popen, int]:
    subprocess.run(
        ["python", "-B", str(SETUP), "--task-json", str(task_json), "--state-dir", str(state_dir), "--seed", f"interaction-pair-{mechanic}"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    port = reserve_port()
    process = subprocess.Popen(
        ["python", "-B", str(SERVER), "--host", "127.0.0.1", "--port", str(port), "--app-dir", str(APP_DIR), "--state-dir", str(state_dir)],
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
            time.sleep(0.1)
    process.kill()
    raise RuntimeError(f"server did not start for {mechanic} {interaction}")


def controlled_task(tasks_root: Path, difficulty: int, interaction: str) -> Path:
    matches = []
    for path in tasks_root.glob("*/task.json"):
        condition = (read_json(path).get("metadata") or {}).get("control_condition") or {}
        if int(condition.get("difficulty") or 0) == difficulty and condition.get("interaction") == interaction:
            matches.append(path)
    if len(matches) != 1:
        raise AssertionError(f"expected one level {difficulty} {interaction} task, found {matches}")
    return matches[0]


def main() -> None:
    args = parse_args()
    env_root = BENCH_ROOT / "environments" / args.environment
    controls = read_json(env_root / "controls.json")
    mechanic = str(controls["mechanic_id"])
    difficulty = int(controls["baseline"]["difficulty"])
    solver = load_module(f"interaction_solver_{mechanic}", BENCH_ROOT / "tools" / "incubator_solvers" / f"{mechanic}.py")
    helpers = load_module("controlled_interaction_verifier_helpers", HELPERS)
    materializer = load_module("controlled_interaction_materializer", MATERIALIZER)
    temp_root = Path(tempfile.mkdtemp(prefix=f"controlled-interaction-{mechanic}-"))
    tasks_root = temp_root / "materialized"
    materializer.materialize_environment(env_root, tasks_root)
    tasks_root = tasks_root / args.environment / "tasks"
    out_dir = args.out_dir or temp_root / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, dict] = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for interaction in ("simplified", "full"):
            task_json = controlled_task(tasks_root, difficulty, interaction)
            state_dir = temp_root / interaction
            state_dir.mkdir(parents=True, exist_ok=True)
            process, port = start_server(task_json, mechanic, interaction, state_dir)
            errors: list[str] = []
            page = browser.new_page(viewport={"width": 1280, "height": 820}, device_scale_factor=1)
            page.on("pageerror", lambda error: errors.append(str(error)))
            try:
                page.goto(f"http://127.0.0.1:{port}")
                page.wait_for_load_state("networkidle")
                expect(page.locator("[data-interaction]")).to_have_attribute("data-interaction", interaction)
                solver.fail_once(page, state_dir, out_dir, mechanic)
                solver.solve(page, state_dir, out_dir, mechanic)
                expect(page.locator(".readout")).to_have_attribute("data-status", "passed", timeout=8000)
                exported = {
                    "result": read_json(state_dir / "result.json"),
                    "ground_truth": read_json(state_dir / "ground_truth.json"),
                    "public_state": read_json(state_dir / "public_state.json"),
                }
                server_grade = exported["result"].get("server_grade") or {}
                grader_path = BENCH_ROOT / "shared_runtime" / "server" / "incubator_graders" / f"{mechanic}.py"
                direct_grade = (
                    helpers.verify_external_mechanic(exported, mechanic)
                    if grader_path.is_file()
                    else getattr(helpers, f"verify_{mechanic}")(exported)
                )
                if server_grade.get("passed") is not True:
                    raise AssertionError(f"server rejected {interaction}: {server_grade}")
                if direct_grade.get("passed") is not True or direct_grade.get("score") != 100:
                    raise AssertionError(f"verifier rejected {interaction}: {direct_grade}")
                if errors:
                    raise AssertionError(f"browser errors in {interaction}: {errors}")
                result = exported["result"]
                events = result.get("events") or result.get("issued_commands") or result.get("orders") or []
                sources = sorted({event.get("input_source") for event in events if event.get("input_source")})
                summary[interaction] = {
                    "passed": True,
                    "server_grade": server_grade,
                    "verifier": direct_grade,
                    "input_sources": sources,
                }
            finally:
                page.close()
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
        browser.close()
    print(json.dumps({"environment": args.environment, "mechanic": mechanic, "difficulty": difficulty, "interactions": summary}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
