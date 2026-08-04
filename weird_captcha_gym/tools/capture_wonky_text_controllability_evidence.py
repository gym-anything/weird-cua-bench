#!/usr/bin/env python3
"""Capture isolated browser evidence for Wonky Text controllability.

The script deliberately uses a headless Playwright browser with a fresh
non-persistent context and local loopback servers only.  It solves through the
visible controls; private generated state is used only by this test harness to
produce a reproducible UI trajectory.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.sync_api import expect, sync_playwright

from weird_captcha_gym.tools.incubator_solvers.reviewed_overhaul_common import drag_delta


BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "wonky_text_hostile_rendering_env"
BASE_TASK = ENVIRONMENT / "tasks" / "wonky_text_hostile_rendering_seed_0001" / "task.json"
APP_DIR = BENCHMARK / "shared_runtime" / "app"
SETUP = BENCHMARK / "shared_scripts" / "setup_task.py"
SERVER = BENCHMARK / "shared_runtime" / "server" / "weird_captcha_server.py"
EXPORT = BENCHMARK / "shared_scripts" / "export_result.sh"
MATERIALIZER = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
GRADER = BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "wonky_text_hostile_rendering.py"
VERIFIER = ENVIRONMENT / "tasks" / "wonky_text_hostile_rendering_seed_0001" / "verifier.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture Wonky Text controllability evidence.")
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def reserve_port() -> int:
    with socket.socket() as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def start_server(task_json: Path, state_dir: Path, seed: str) -> tuple[subprocess.Popen[bytes], int]:
    state_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["python", "-B", str(SETUP), "--task-json", str(task_json), "--state-dir", str(state_dir), "--seed", seed],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    port = reserve_port()
    process = subprocess.Popen(
        ["python", "-B", str(SERVER), "--host", "127.0.0.1", "--port", str(port), "--app-dir", str(APP_DIR), "--state-dir", str(state_dir)],
        cwd=ROOT,
        env={**os.environ, "WEIRD_CAPTCHA_CHALLENGE_SEED": seed},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5).read()
            return process, port
        except Exception:
            time.sleep(0.1)
    process.kill()
    raise RuntimeError("Wonky Text evidence server did not start")


def stop_server(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()


def short_delta(target: float, initial: float) -> float:
    return (target - initial + 180.0) % 360.0 - 180.0


def world_fingerprint(public: dict[str, Any], truth: dict[str, Any]) -> str:
    values = {"public": copy.deepcopy(public), "truth": copy.deepcopy(truth)}
    for value in values.values():
        for key in ("task_id", "challenge_id", "control_condition"):
            value.pop(key, None)
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _full_replay_payload(public: dict[str, Any], truth: dict[str, Any], zero_releases: int) -> dict[str, Any]:
    """Build a visible full-wheel transcript, including harmless pointer releases."""

    events: list[dict[str, Any]] = []

    def record(kind: str, **details: Any) -> None:
        events.append({"sequence": len(events) + 1, "kind": kind, **details})

    first_plate = truth["press"]["plates"][0]
    for _ in range(zero_releases):
        record("wheel_drag", plate_id=first_plate["id"], delta=0.0, input_source="wheel_drag")
    for plate in truth["press"]["plates"]:
        record(
            "wheel_drag",
            plate_id=plate["id"],
            delta=short_delta(float(plate["target"]), float(plate["initial"])),
            input_source="wheel_drag",
        )
        record("lock", plate_id=plate["id"], locked=True)
    record("press")
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": events,
    }


def baseline_preservation_record(baseline_task: Path, grader: ModuleType) -> dict[str, Any]:
    setup = load_module("wonky_evidence_setup", SETUP)
    seed = "wonky-baseline-preservation"
    original_public, original_truth = setup.generate_task_state(read_json(BASE_TASK), seed)
    baseline_public, baseline_truth = setup.generate_task_state(read_json(baseline_task), seed)

    def normalized(value: dict[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(value)
        result.pop("task_id", None)
        result.pop("control_condition", None)
        return result

    public_equal = normalized(original_public) == normalized(baseline_public)
    truth_equal = normalized(original_truth) == normalized(baseline_truth)
    if not (public_equal and truth_equal):
        raise AssertionError("controlled L3 full does not preserve the original seeded registration world")
    event_limit: dict[str, Any] = {}
    for total_events, zero_releases, expected_passed in ((100, 93, True), (101, 94, False)):
        original_result = grader.grade(
            _full_replay_payload(original_public, original_truth, zero_releases), original_truth, original_public
        )
        baseline_result = grader.grade(
            _full_replay_payload(baseline_public, baseline_truth, zero_releases), baseline_truth, baseline_public
        )
        if len(_full_replay_payload(original_public, original_truth, zero_releases)["events"]) != total_events:
            raise AssertionError("registration boundary replay has the wrong event count")
        if original_result.get("passed") is not expected_passed or baseline_result.get("passed") is not expected_passed:
            raise AssertionError("controlled L3 does not preserve the historical replay event boundary")
        event_limit[str(total_events)] = {
            "event_count": total_events,
            "uncontrolled": original_result,
            "controlled_l3_full": baseline_result,
        }
    unlock_rejection: dict[str, Any] = {}
    for label, public, truth in (
        ("uncontrolled", original_public, original_truth),
        ("controlled_l3_full", baseline_public, baseline_truth),
    ):
        payload = _full_replay_payload(public, truth, 0)
        payload["events"].insert(2, {"kind": "lock", "plate_id": truth["press"]["plates"][0]["id"], "locked": False})
        for sequence, event in enumerate(payload["events"], start=1):
            event["sequence"] = sequence
        result = grader.grade(payload, truth, public)
        if result.get("passed") is not False or result.get("feedback") != "plate lock is invalid":
            raise AssertionError("controlled L3 does not preserve the historical unlock rejection")
        unlock_rejection[label] = result
    return {
        "fixed_seed": seed,
        "historical_user_text": "Register the plate.",
        "corrected_user_text": "Register all three color plates, lock them, then press.",
        "repair_scope": "Text only: the historical generator and grader already required three aligned locks followed by one press.",
        "challenge_id_matches": original_public["challenge_id"] == baseline_public["challenge_id"],
        "press_contract_matches": original_public["press"] == baseline_public["press"],
        "normalized_public_matches": public_equal,
        "normalized_truth_matches": truth_equal,
        "normalized_public_sha256": hashlib.sha256(json.dumps(normalized(original_public), sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "normalized_truth_sha256": hashlib.sha256(json.dumps(normalized(original_truth), sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "event_limit_boundary": event_limit,
        "unlock_event_rejection": unlock_rejection,
    }


def task_for(tasks_root: Path, difficulty: int, interaction: str) -> Path:
    matches = []
    for candidate in tasks_root.glob("*/task.json"):
        condition = (read_json(candidate).get("metadata") or {}).get("control_condition") or {}
        if int(condition.get("difficulty") or 0) == difficulty and condition.get("interaction") == interaction:
            matches.append(candidate)
    if len(matches) != 1:
        raise AssertionError(f"expected one d{difficulty} {interaction} task, found {matches}")
    return matches[0]


def wait_for_fresh_state(state_dir: Path, previous: str) -> tuple[dict[str, Any], dict[str, Any]]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        public, truth = read_json(state_dir / "public_state.json"), read_json(state_dir / "ground_truth.json")
        if truth.get("challenge_id") and truth.get("challenge_id") != previous:
            return public, truth
        time.sleep(0.05)
    raise AssertionError("rejected registration did not create a fresh challenge")


def visible_frame(page, path: Path) -> dict[str, str]:
    """Capture the static registration canvas and its rendered pixels."""

    image = page.screenshot(path=str(path), full_page=True)
    canvas = page.locator(".registration-canvas").evaluate("node => node.toDataURL()")
    return {
        "screenshot": f"screenshots/{path.name}",
        "screenshot_sha256": hashlib.sha256(image).hexdigest(),
        "canvas_sha256": hashlib.sha256(str(canvas).encode()).hexdigest(),
    }


def record_observation(page, time_mode: str, screenshots: Path, label: str) -> dict[str, Any]:
    page.evaluate("mode => WeirdCaptchaTime.setMode(mode)", time_mode)
    before = page.evaluate("WeirdCaptchaTime.status()")
    before_frame = visible_frame(page, screenshots / f"{label}-observation.png")
    page.wait_for_timeout(260)
    after = page.evaluate("WeirdCaptchaTime.status()")
    after_frame = visible_frame(page, screenshots / f"{label}-after-hold.png")
    delta = float(after["task_time_ms"]) - float(before["task_time_ms"])
    if time_mode == "live" and delta < 180:
        raise AssertionError(f"live task clock did not advance during a simulated model delay: {delta}")
    if time_mode == "paused" and abs(delta) > 1:
        raise AssertionError(f"paused task clock advanced during a simulated model delay: {delta}")
    canvas_unchanged = before_frame["canvas_sha256"] == after_frame["canvas_sha256"]
    if not canvas_unchanged:
        raise AssertionError(f"static registration canvas changed during {time_mode} hold: {before_frame} -> {after_frame}")
    return {
        "mode": time_mode,
        "state": str(after["state"]),
        "frames_per_observation": 1,
        "observation_window_ms": 0,
        "before_task_time_ms": float(before["task_time_ms"]),
        "after_task_time_ms": float(after["task_time_ms"]),
        "task_time_delta_ms": round(delta, 3),
        "static_hold": {
            "canvas_unchanged": canvas_unchanged,
            "before": before_frame,
            "after": after_frame,
        },
    }


def solve_visible_ui(page, truth: dict[str, Any], interaction: str, time_mode: str) -> None:
    page.evaluate("WeirdCaptchaTime.resume()")
    press = truth["press"]
    if interaction == "full":
        for plate in press["plates"]:
            degrees = short_delta(float(plate["target"]), float(plate["initial"]))
            wheel = page.locator(f'.registration-wheel[data-plate-id="{plate["id"]}"]')
            drag_delta(page, wheel, degrees / float(press["degrees_per_pixel"]), 0, maximum_step=20)
            page.locator(f'.plate-lock[data-plate-id="{plate["id"]}"]').click()
    else:
        parameters = truth["control_condition"]["difficulty_parameters"]
        step = float(parameters["proxy_step_degrees"])
        coarse_step = float(parameters.get("proxy_coarse_step_degrees") or 0.0)
        for plate in press["plates"]:
            remaining = short_delta(float(plate["target"]), float(plate["initial"]))
            for visible_step in sorted({step, coarse_step} - {0.0}, reverse=True):
                while abs(remaining) >= visible_step - 1e-8:
                    signed_step = visible_step if remaining > 0 else -visible_step
                    delta_text = str(int(signed_step)) if signed_step.is_integer() else str(signed_step)
                    page.locator(f'.plate-step[data-plate-id="{plate["id"]}"][data-delta="{delta_text}"]').click()
                    remaining -= signed_step
            if abs(remaining) >= 1e-8:
                raise AssertionError(f"proxy steps do not reach plate target: {remaining}")
            page.locator(f'.plate-lock[data-plate-id="{plate["id"]}"]').click()
    page.locator(".registration-press").click()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=15_000)
    if time_mode == "paused":
        page.evaluate("WeirdCaptchaTime.pause()")


def export_and_verify(state_dir: Path, destination: Path, verifier: ModuleType, grader: ModuleType) -> dict[str, Any]:
    result = subprocess.run(
        ["bash", str(EXPORT)],
        cwd=ROOT,
        env={**os.environ, "WEIRD_CAPTCHA_STATE_DIR": str(state_dir)},
        check=True,
        capture_output=True,
        text=True,
    )
    shutil.copy2("/tmp/task_result.json", destination)
    exported = read_json(destination)
    direct = grader.grade(exported["result"], exported["ground_truth"], exported["public_state"])

    def copy_from_env(source: str, copied: str) -> None:
        if source != "/tmp/task_result.json":
            raise ValueError(f"unexpected verifier source {source}")
        shutil.copy2(destination, copied)

    verified = verifier.verify_task(env_info={"copy_from_env": copy_from_env})
    server_grade = exported["result"].get("server_grade") or {}
    if not all(item.get("passed") is True for item in (server_grade, direct, verified)):
        raise AssertionError(f"registration acceptance disagrees: server={server_grade}, direct={direct}, verifier={verified}")
    return {
        "export_command_stdout": result.stdout.strip(),
        "server_grade": server_grade,
        "direct_grade": direct,
        "task_verifier": verified,
    }


def run_condition(
    browser,
    *,
    task_json: Path,
    difficulty: int,
    interaction: str,
    time_mode: str,
    out_dir: Path,
    grader: ModuleType,
    verifier: ModuleType,
) -> dict[str, Any]:
    label = f"d{difficulty}-{interaction}-{time_mode}"
    with tempfile.TemporaryDirectory(prefix=f"wonky-{label}-") as temporary:
        state_dir = Path(temporary) / "state"
        # Difficulty changes the generated registration problem.  Interaction
        # and real-time mode must not, so all four runs at one level share this
        # exact seed.
        server, port = start_server(task_json, state_dir, f"wonky-evidence-d{difficulty}")
        context = browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        try:
            page.goto(f"http://127.0.0.1:{port}/?time_mode={time_mode}&start_paused=1", wait_until="networkidle")
            page.wait_for_selector(".registration-captcha")
            public, truth = read_json(state_dir / "public_state.json"), read_json(state_dir / "ground_truth.json")
            if public["control_condition"]["difficulty"] != difficulty or public["control_condition"]["interaction"] != interaction:
                raise AssertionError(f"wrong rendered condition for {label}: {public['control_condition']}")
            initial_world = world_fingerprint(public, truth)
            observation = record_observation(page, time_mode, out_dir / "screenshots", label)

            failure: dict[str, Any] | None = None
            if (difficulty, interaction, time_mode) == (3, "full", "live"):
                original_challenge = str(truth["challenge_id"])
                for plate in truth["press"]["plates"]:
                    page.locator(f'.plate-lock[data-plate-id="{plate["id"]}"]').click()
                page.locator(".registration-press").click()
                expect(page.locator(".readout")).to_have_text("FAIL", timeout=15_000)
                page.screenshot(path=str(out_dir / "screenshots" / "d3-full-live-failure.png"), full_page=True)
                attempts = (state_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
                failure = json.loads(attempts[-1])
                write_json(out_dir / "artifacts" / "d3-full-live-failure-attempt.json", failure)
                public, truth = wait_for_fresh_state(state_dir, original_challenge)
                page.wait_for_timeout(1_050)
                page.screenshot(path=str(out_dir / "screenshots" / "d3-full-live-recovered.png"), full_page=True)

            solve_visible_ui(page, truth, interaction, time_mode)
            page.screenshot(path=str(out_dir / "screenshots" / f"{label}-pass.png"), full_page=True)
            artifact = out_dir / "exports" / f"{label}.json"
            acceptance = export_and_verify(state_dir, artifact, verifier, grader)
            if errors:
                raise AssertionError(f"browser errors in {label}: {errors}")
            screenshots = [
                observation["static_hold"]["before"]["screenshot"],
                observation["static_hold"]["after"]["screenshot"],
                f"screenshots/{label}-pass.png",
            ]
            if failure is not None:
                screenshots.extend([
                    "screenshots/d3-full-live-failure.png",
                    "screenshots/d3-full-live-recovered.png",
                ])
            return {
                "condition": {"difficulty": difficulty, "interaction": interaction, "time_mode": time_mode},
                "challenge_id": truth["challenge_id"],
                "world_fingerprint": initial_world,
                "solved_world_fingerprint": world_fingerprint(public, truth),
                "observation": observation,
                "failure": failure,
                "acceptance": acceptance,
                "screenshots": screenshots,
                "export": f"exports/{label}.json",
            }
        finally:
            page.close()
            context.close()
            stop_server(server)


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    if out_dir.exists():
        raise SystemExit(f"refusing to overwrite existing evidence directory: {out_dir}")
    for relative in ("screenshots", "exports", "artifacts"):
        (out_dir / relative).mkdir(parents=True, exist_ok=True)

    grader = load_module("wonky_evidence_grader", GRADER)
    verifier = load_module("wonky_evidence_verifier", VERIFIER)
    with tempfile.TemporaryDirectory(prefix="wonky-materialized-") as temporary:
        temporary_root = Path(temporary)
        first, second = temporary_root / "first", temporary_root / "second"
        commands = []
        for destination in (first, second):
            command = ["python", str(MATERIALIZER), "--environment", ENVIRONMENT.name, "--output-root", str(destination)]
            completed = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
            commands.append({"command": command, "stdout": completed.stdout.strip(), "stderr": completed.stderr.strip()})
        first_tasks = sorted(first.glob(f"{ENVIRONMENT.name}/tasks/*/task.json"))
        second_tasks = sorted(second.glob(f"{ENVIRONMENT.name}/tasks/*/task.json"))
        if len(first_tasks) != 10 or [path.relative_to(first).as_posix() for path in first_tasks] != [path.relative_to(second).as_posix() for path in second_tasks]:
            raise AssertionError("controlled materialization did not produce ten deterministic task paths")
        if [path.read_bytes() for path in first_tasks] != [path.read_bytes() for path in second_tasks]:
            raise AssertionError("controlled task materialization is not deterministic")
        write_json(out_dir / "artifacts" / "materialization.json", {"commands": commands, "tasks": [path.relative_to(first).as_posix() for path in first_tasks]})
        write_json(
            out_dir / "artifacts" / "baseline-contract-repair.json",
            baseline_preservation_record(task_for(first / ENVIRONMENT.name / "tasks", 3, "full"), grader),
        )

        results: list[dict[str, Any]] = []
        # Playwright launch(headless=True) plus a new_context per run is an
        # isolated temporary browser profile; no persistent browser is opened.
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for difficulty in range(1, 6):
                    for interaction in ("simplified", "full"):
                        controlled = task_for(first / ENVIRONMENT.name / "tasks", difficulty, interaction)
                        for time_mode in ("live", "paused"):
                            results.append(run_condition(
                                browser,
                                task_json=controlled,
                                difficulty=difficulty,
                                interaction=interaction,
                                time_mode=time_mode,
                                out_dir=out_dir,
                                grader=grader,
                                verifier=verifier,
                            ))
            finally:
                browser.close()

    write_json(out_dir / "artifacts" / "raw-run-results.json", results)
    by_pair: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for result in results:
        condition = result["condition"]
        by_pair.setdefault((condition["difficulty"], condition["interaction"]), []).append(result)
    for key, pair in by_pair.items():
        if len(pair) != 2 or pair[0]["world_fingerprint"] != pair[1]["world_fingerprint"]:
            raise AssertionError(f"live and paused runs changed world state for {key}")
    for difficulty in range(1, 6):
        simplified = by_pair[(difficulty, "simplified")][0]
        full = by_pair[(difficulty, "full")][0]
        if simplified["world_fingerprint"] != full["world_fingerprint"]:
            raise AssertionError(f"interaction pair changed generated world at difficulty {difficulty}")

    visible_index = {
        "reference_and_adjacent_difficulties": {
            "baseline": {
                "difficulty": 3,
                "interaction": "full",
                "time_mode": "live",
                "screenshots": [
                    "screenshots/d3-full-live-observation.png",
                    "screenshots/d3-full-live-after-hold.png",
                    "screenshots/d3-full-live-pass.png",
                ],
                "baseline_contract": "artifacts/baseline-contract-repair.json",
            },
            "adjacent_comparison": [
                {"difficulty": level, "screenshot": f"screenshots/d{level}-full-live-observation.png"}
                for level in (2, 3, 4)
            ],
        },
        "same_initial_world_by_difficulty": [
            {
                "difficulty": difficulty,
                "initial_world_fingerprint": by_pair[(difficulty, "full")][0]["world_fingerprint"],
                "conditions": [
                    f"d{difficulty}-{interaction}-{time_mode}"
                    for interaction in ("simplified", "full")
                    for time_mode in ("live", "paused")
                ],
            }
            for difficulty in range(1, 6)
        ],
        "static_live_and_paused_observations": [
            {
                "condition": result["condition"],
                "state": result["observation"]["state"],
                "task_time_delta_ms": result["observation"]["task_time_delta_ms"],
                "static_hold": result["observation"]["static_hold"],
            }
            for result in results
        ],
        "failure_and_recovery": {
            "condition": {"difficulty": 3, "interaction": "full", "time_mode": "live"},
            "failure_screenshot": "screenshots/d3-full-live-failure.png",
            "recovery_screenshot": "screenshots/d3-full-live-recovered.png",
            "failure_attempt": "artifacts/d3-full-live-failure-attempt.json",
            "recovered_export": "exports/d3-full-live.json",
        },
        "grading_export_and_verification": [
            {
                "condition": result["condition"],
                "export": result["export"],
                "server_grade_passed": result["acceptance"]["server_grade"].get("passed") is True,
                "direct_grade_passed": result["acceptance"]["direct_grade"].get("passed") is True,
                "task_verifier_passed": result["acceptance"]["task_verifier"].get("passed") is True,
            }
            for result in results
        ],
    }
    write_json(out_dir / "artifacts" / "visible-evidence-index.json", visible_index)

    summary = {
        "ok": True,
        "isolation": "Playwright chromium.launch(headless=True) with a fresh browser.new_context per local-loopback run.",
        "scope": {"difficulty_interaction_conditions": 10, "live_paused_runs": 20},
        "visible_evidence_index": "artifacts/visible-evidence-index.json",
        "results": results,
        "notes": [
            "The static task uses the shared setting observation_window_ms=0 and frames_per_observation=1.",
            "Screenshots and scripted UI trajectories are automated evidence, not human calibration or computer-use-agent evaluation.",
        ],
    }
    write_json(out_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
