#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
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
    parser = argparse.ArgumentParser(
        description="Smoke-test both interaction modes at an environment's baseline or all five difficulties."
    )
    parser.add_argument("--environment", required=True, help="Environment folder name such as input_lag_forklift_env")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument(
        "--all-difficulties",
        action="store_true",
        help="Exercise all ten difficulty/interaction variants instead of only the baseline pair.",
    )
    parser.add_argument(
        "--difficulty",
        type=int,
        choices=range(1, 6),
        help="Exercise one specified difficulty pair instead of the baseline pair.",
    )
    parser.add_argument(
        "--interaction",
        choices=("simplified", "full"),
        help="Exercise one input surface; by default both surfaces are run.",
    )
    parser.add_argument(
        "--time-mode",
        choices=("live", "paused"),
        default="live",
        help="Run the browser matrix with the shared clock live or paused.",
    )
    parser.add_argument(
        "--model-delay-ms",
        type=int,
        default=0,
        help="Artificial inference delay after the initial observation; validates live/paused clock behavior.",
    )
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


def world_fingerprint(public_state: dict) -> str:
    value = copy.deepcopy(public_state)
    for key in ("task_id", "challenge_id", "control_condition"):
        value.pop(key, None)
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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


def observation_viewport(env_root: Path) -> dict[str, int]:
    specification = read_json(env_root / "env.json")
    screens = [item for item in specification.get("observation", []) if item.get("type") == "rgb_screen"]
    if len(screens) != 1:
        raise AssertionError(f"{env_root.name} must declare exactly one rgb_screen observation")
    resolution = screens[0].get("resolution")
    if not isinstance(resolution, list) or len(resolution) != 2 or not all(isinstance(value, int) and value > 0 for value in resolution):
        raise AssertionError(f"{env_root.name} rgb_screen resolution is malformed")
    return {"width": resolution[0], "height": resolution[1]}


def main() -> None:
    args = parse_args()
    env_root = BENCH_ROOT / "environments" / args.environment
    controls = read_json(env_root / "controls.json")
    viewport = observation_viewport(env_root)
    mechanic = str(controls["mechanic_id"])
    baseline_difficulty = int(controls["baseline"]["difficulty"])
    if args.all_difficulties and args.difficulty is not None:
        raise SystemExit("--all-difficulties and --difficulty are mutually exclusive")
    if args.model_delay_ms < 0:
        raise SystemExit("--model-delay-ms must be nonnegative")
    difficulties = range(1, 6) if args.all_difficulties else (args.difficulty or baseline_difficulty,)
    solver = load_module(f"interaction_solver_{mechanic}", BENCH_ROOT / "tools" / "incubator_solvers" / f"{mechanic}.py")
    helpers = load_module("controlled_interaction_verifier_helpers", HELPERS)
    materializer = load_module("controlled_interaction_materializer", MATERIALIZER)
    temp_root = Path(tempfile.mkdtemp(prefix=f"controlled-interaction-{mechanic}-"))
    tasks_root = temp_root / "materialized"
    materializer.materialize_environment(env_root, tasks_root)
    tasks_root = tasks_root / args.environment / "tasks"
    out_dir = args.out_dir or temp_root / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, dict[str, dict]] = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for difficulty in difficulties:
            level_summary: dict[str, dict] = {}
            for interaction in ((args.interaction,) if args.interaction else ("simplified", "full")):
                task_json = controlled_task(tasks_root, difficulty, interaction)
                state_dir = temp_root / f"d{difficulty}-{interaction}"
                state_dir.mkdir(parents=True, exist_ok=True)
                evidence_dir = (
                    out_dir / f"d{difficulty}-{interaction}"
                    if args.all_difficulties
                    else out_dir / interaction
                )
                evidence_dir.mkdir(parents=True, exist_ok=True)
                process, port = start_server(task_json, mechanic, interaction, state_dir)
                errors: list[str] = []
                page = browser.new_page(viewport=viewport, device_scale_factor=1)
                page.on("pageerror", lambda error: errors.append(str(error)))
                try:
                    current_task_path = state_dir / "current_task.json"
                    current_task_text = current_task_path.read_text(encoding="utf-8")
                    current_task_path.unlink()
                    try:
                        page.goto(
                            f"http://127.0.0.1:{port}/"
                            f"?time_mode={args.time_mode}"
                            f"&start_paused={'1' if args.time_mode == 'paused' else '0'}"
                        )
                        page.wait_for_load_state("networkidle")
                    finally:
                        current_task_path.write_text(current_task_text, encoding="utf-8")
                    expect(page.locator("[data-interaction]")).to_have_attribute("data-interaction", interaction)
                    if mechanic == "popup_exorcist":
                        expect(page.locator(".parasite-head")).to_be_visible()
                        expect(page.locator(".parasite-foot")).to_be_visible()
                        page.wait_for_timeout(150)
                    initial_public_state = read_json(state_dir / "public_state.json")
                    initial_challenge_id = str(initial_public_state.get("challenge_id") or "")
                    if not initial_challenge_id:
                        raise AssertionError("controlled task did not expose an initial challenge identity")
                    clock_initial = page.evaluate("() => WeirdCaptchaTime.status()")
                    page.screenshot(path=str(evidence_dir / "initial.png"))
                    clock_after_model_delay = clock_initial
                    if args.model_delay_ms:
                        page.wait_for_timeout(args.model_delay_ms)
                        clock_after_model_delay = page.evaluate("() => WeirdCaptchaTime.status()")
                        page.screenshot(path=str(evidence_dir / "after-model-delay.png"))
                        delay_delta = float(clock_after_model_delay["task_time_ms"]) - float(clock_initial["task_time_ms"])
                        if args.time_mode == "live" and delay_delta < args.model_delay_ms * 0.7:
                            raise AssertionError(
                                f"live task clock did not advance through the model delay: {delay_delta}ms"
                            )
                        if args.time_mode == "paused" and abs(delay_delta) > 2:
                            raise AssertionError(
                                f"paused task clock advanced through the model delay: {delay_delta}ms"
                            )
                    if args.time_mode == "paused":
                        page.evaluate("() => WeirdCaptchaTime.resume()")
                    solver.fail_once(page, state_dir, evidence_dir, mechanic)
                    failed_attempt_path = state_dir / "attempts.jsonl"
                    if not failed_attempt_path.is_file():
                        raise AssertionError("failed certification was not archived by the server")
                    failed_attempts = [
                        json.loads(line)
                        for line in failed_attempt_path.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    ]
                    if not failed_attempts:
                        raise AssertionError("failed certification archive is empty")
                    failed_attempt = failed_attempts[-1]
                    failed_grade = dict(failed_attempt.get("server_grade") or {})
                    if failed_grade.get("passed") is not False:
                        raise AssertionError(f"intentional failed certification was accepted: {failed_grade}")
                    retry_public_state = read_json(state_dir / "public_state.json")
                    retry_challenge_id = str(retry_public_state.get("challenge_id") or "")
                    if not retry_challenge_id or retry_challenge_id == initial_challenge_id:
                        raise AssertionError("failed certification did not issue a fresh challenge")
                    (evidence_dir / "failed-attempts.jsonl").write_text(
                        "".join(json.dumps(attempt, sort_keys=True) + "\n" for attempt in failed_attempts),
                        encoding="utf-8",
                    )
                    (evidence_dir / "failure-server-grade.json").write_text(
                        json.dumps(failed_grade, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    (evidence_dir / "retry_public_state.json").write_text(
                        json.dumps(retry_public_state, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    if args.time_mode == "paused":
                        page.evaluate("() => WeirdCaptchaTime.pause()")
                    clock_after_failure = page.evaluate("() => WeirdCaptchaTime.status()")
                    if args.time_mode == "paused":
                        page.evaluate("() => WeirdCaptchaTime.resume()")
                    solver.solve(page, state_dir, evidence_dir, mechanic)
                    if args.time_mode == "paused":
                        page.evaluate("() => WeirdCaptchaTime.pause()")
                    clock_after_success = page.evaluate("() => WeirdCaptchaTime.status()")
                    expect(page.locator(".readout")).to_have_attribute("data-status", "passed", timeout=8000)
                    page.screenshot(path=str(evidence_dir / "pass.png"))
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
                        raise AssertionError(f"server rejected difficulty {difficulty} {interaction}: {server_grade}")
                    if direct_grade.get("passed") is not True or direct_grade.get("score") != 100:
                        raise AssertionError(f"verifier rejected difficulty {difficulty} {interaction}: {direct_grade}")
                    if errors:
                        raise AssertionError(f"browser errors in difficulty {difficulty} {interaction}: {errors}")
                    (evidence_dir / "public_state.json").write_text(
                        json.dumps(exported["public_state"], indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    (evidence_dir / "initial_public_state.json").write_text(
                        json.dumps(initial_public_state, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    (evidence_dir / "result.json").write_text(
                        json.dumps(exported["result"], indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    (evidence_dir / "server-grade.json").write_text(
                        json.dumps(server_grade, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    (evidence_dir / "verifier.json").write_text(
                        json.dumps(direct_grade, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    (evidence_dir / "exported-result.json").write_text(
                        json.dumps(exported, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    result = exported["result"]
                    events = (
                        result.get("events")
                        or result.get("actions")
                        or (result.get("trusted_witness") or {}).get("actions")
                        or result.get("issued_commands")
                        or result.get("orders")
                        or []
                    )
                    sources = sorted({
                        event.get("input_source") or event.get("input_surface")
                        for event in events
                        if event.get("input_source") or event.get("input_surface")
                    })
                    placement_sources = result.get("placement_sources") or {}
                    if isinstance(placement_sources, dict):
                        sources = sorted(set(sources) | {source for source in placement_sources.values() if source})
                    level_summary[interaction] = {
                        "passed": True,
                        "server_grade": server_grade,
                        "verifier": direct_grade,
                        "input_sources": sources,
                        "failure_and_retry": {
                            "initial_challenge_id": initial_challenge_id,
                            "failed_server_grade": failed_grade,
                            "retry_challenge_id": retry_challenge_id,
                            "fresh_challenge_issued": True,
                            "retry_passed": True,
                            "retry_world_fingerprint": world_fingerprint(retry_public_state),
                        },
                        "clock": {
                            "initial": clock_initial,
                            "after_model_delay": clock_after_model_delay,
                            "after_failure_attempt": clock_after_failure,
                            "after_success_attempt": clock_after_success,
                        },
                        "initial_browser_run_world_fingerprint": world_fingerprint(initial_public_state),
                        "solved_browser_run_world_fingerprint": world_fingerprint(exported["public_state"]),
                    }
                except Exception:
                    attempts = state_dir / "attempts.jsonl"
                    if attempts.is_file():
                        (evidence_dir / "failed-attempts.jsonl").write_bytes(attempts.read_bytes())
                    raise
                finally:
                    page.close()
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
            summary[str(difficulty)] = level_summary
        browser.close()
    if args.all_difficulties:
        output = {
            "environment": args.environment,
            "mechanic": mechanic,
            "time_mode": args.time_mode,
            "model_delay_ms": args.model_delay_ms,
            "difficulties": summary,
        }
    else:
        selected_difficulty = next(iter(difficulties))
        output = {
            "environment": args.environment,
            "mechanic": mechanic,
            "time_mode": args.time_mode,
            "model_delay_ms": args.model_delay_ms,
            "difficulty": selected_difficulty,
            "interactions": summary[str(selected_difficulty)],
        }
    (out_dir / "summary.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
