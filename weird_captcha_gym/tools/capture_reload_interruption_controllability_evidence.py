#!/usr/bin/env python3
"""Capture isolated browser evidence for Reload Interruption controls.

This validation helper reads generated state only to choose its scripted route.
Every attempted solve uses the visible task page's selected controls.  Browser
processes are headless, ephemeral Playwright instances; servers bind only to
127.0.0.1 and state lives in a temporary directory.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BENCHMARK = ROOT / "weird_captcha_gym"
ENV_ROOT = BENCHMARK / "environments" / "reload_interruption_env"
APP_DIR = BENCHMARK / "shared_runtime" / "app"
SERVER = BENCHMARK / "shared_runtime" / "server" / "weird_captcha_server.py"
SETUP = BENCHMARK / "shared_scripts" / "setup_task.py"
EXPORT = BENCHMARK / "shared_scripts" / "export_result.sh"
MATERIALIZER = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
HELPERS = BENCHMARK / "shared_runtime" / "verifier_helpers.py"
SOLVER = BENCHMARK / "tools" / "incubator_solvers" / "reload_interruption.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture Reload Interruption paused-mode control evidence.")
    parser.add_argument("--out-dir", type=Path, default=ENV_ROOT / "evidence_docs" / "browser_paused_v4")
    parser.add_argument("--difficulty", type=int, choices=range(1, 6))
    parser.add_argument("--interaction", choices=("simplified", "full"))
    parser.add_argument("--skip-repeats", action="store_true")
    parser.add_argument(
        "--original-baseline",
        action="store_true",
        help="Capture the uncontrolled original task as the L4/full baseline.",
    )
    return parser.parse_args()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def start_server(task_path: Path, state_dir: Path, port: int, seed: str) -> subprocess.Popen:
    subprocess.run(
        ["python", "-B", str(SETUP), "--task-json", str(task_path), "--state-dir", str(state_dir), "--seed", seed],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    environment = dict(os.environ)
    # A visible rejection must issue a fresh task.  Pin that server-side retry
    # source only for repeatable evidence; the ordinary runtime still uses its
    # normal challenge source.
    environment["WEIRD_CAPTCHA_CHALLENGE_SEED"] = f"reload-evidence-{seed}"
    process = subprocess.Popen(
        ["python", "-B", str(SERVER), "--host", "127.0.0.1", "--port", str(port), "--app-dir", str(APP_DIR), "--state-dir", str(state_dir)],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            import urllib.request

            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=.5).read()
            return process
        except Exception:
            time.sleep(.05)
    process.kill()
    raise TimeoutError(f"server did not start for {task_path}")


def stop_server(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()


def controlled_task(tasks_root: Path, difficulty: int, interaction: str) -> Path:
    matches = []
    for path in tasks_root.glob("*/task.json"):
        condition = (read_json(path).get("metadata") or {}).get("control_condition") or {}
        if condition.get("difficulty") == difficulty and condition.get("interaction") == interaction:
            matches.append(path)
    if len(matches) != 1:
        raise AssertionError(f"expected one controlled task for d{difficulty} {interaction}: {matches}")
    return matches[0]


def pause_after_preview(page) -> None:
    page.evaluate("WeirdCaptchaTime.resume()")
    expect(page.locator(".reload-v2.is-ready")).to_be_visible(timeout=15_000)
    page.evaluate("WeirdCaptchaTime.pause()")
    page.wait_for_timeout(80)
    if page.evaluate("WeirdCaptchaTime.status().state") != "paused":
        raise AssertionError("preview did not return to the paused inference state")


def paused_action(page, name: str, action, *, settle_ms: int = 100) -> dict[str, Any]:
    before = page.evaluate("WeirdCaptchaTime.status()")
    if before["state"] != "paused":
        raise AssertionError(f"{name} began outside paused inference: {before}")
    page.evaluate("WeirdCaptchaTime.resume()")
    # Give the shared virtual requestAnimationFrame loop one normal render
    # turn before moving a visible, animated target.  This is task time (not
    # an inference delay) and avoids asking a pointer action to use the stale
    # paused paint on the exact resume boundary.
    page.wait_for_timeout(34)
    action()
    page.wait_for_timeout(settle_ms)
    after_action = page.evaluate("WeirdCaptchaTime.status()")
    if after_action["state"] != "running" or float(after_action["task_time_ms"]) <= float(before["task_time_ms"]):
        raise AssertionError(f"{name} did not execute on the running task clock")
    page.evaluate("WeirdCaptchaTime.pause()")
    after_pause = page.evaluate("WeirdCaptchaTime.status()")
    page.wait_for_timeout(240)
    after_inference = page.evaluate("WeirdCaptchaTime.status()")
    if abs(float(after_inference["task_time_ms"]) - float(after_pause["task_time_ms"])) > 1:
        raise AssertionError(f"{name} advanced while paused for model inference")
    return {
        "action": name,
        "before": before,
        "after_action": after_action,
        "after_pause": after_pause,
        "after_inference_delay": after_inference,
    }


def clear_visible_overload(page, solver, interaction: str, spec: dict[str, Any]) -> None:
    # This is the same visible surface driven by the solver.  It runs while
    # paused_action has resumed the shared task clock.
    solver._clear_overload(page, interaction, spec)


def export_and_verify(state_dir: Path, output: Path, label: str, helpers) -> dict[str, Any]:
    environment = dict(os.environ)
    environment["WEIRD_CAPTCHA_STATE_DIR"] = str(state_dir)
    completed = subprocess.run(
        ["bash", str(EXPORT)], cwd=ROOT, env=environment, capture_output=True, text=True, check=True
    )
    exported_path = Path("/tmp/task_result.json")
    exported = read_json(exported_path)
    expected = read_json(state_dir / "ground_truth.json")["challenge_id"]
    if exported.get("ground_truth", {}).get("challenge_id") != expected:
        raise AssertionError("shared result export was replaced before it could be captured")
    destination = output / "result_artifacts" / f"{label}-export.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exported_path, destination)
    verified = helpers.verify_reload_interruption(exported)
    verifier = load_module(f"reload_task_verifier_{label.replace('-', '_')}", ENV_ROOT / "tasks" / "reload_interruption_seed_0001" / "verifier.py")

    def copy_from_env(source: str, target: str) -> None:
        if source != "/tmp/task_result.json":
            raise ValueError(f"unexpected verifier source {source}")
        shutil.copy2(exported_path, target)

    task_verified = verifier.verify_task(env_info={"copy_from_env": copy_from_env})
    server_grade = (exported.get("result") or {}).get("server_grade") or {}
    if not (server_grade.get("passed") is True and verified.get("passed") is True and task_verified.get("passed") is True):
        raise AssertionError(f"export verification failed for {label}: {server_grade}; {verified}; {task_verified}")
    wrong_surface = copy.deepcopy(exported)
    expected_interaction = str((wrong_surface["ground_truth"].get("control_condition") or {}).get("interaction"))
    wrong_surface["result"]["interaction_mode"] = "full" if expected_interaction == "simplified" else "simplified"
    rejected = helpers.verify_reload_interruption(wrong_surface)
    if rejected.get("passed"):
        raise AssertionError("wrong interaction mode passed exported verification")
    return {
        "export": str(destination.relative_to(output)),
        "export_stdout": completed.stdout.strip(),
        "server_grade": server_grade,
        "verifier": verified,
        "task_verifier": task_verified,
        "wrong_surface_verifier": rejected,
    }


def save_failure(state_dir: Path, output: Path, label: str) -> dict[str, Any]:
    attempts = state_dir / "attempts.jsonl"
    entries = [json.loads(line) for line in attempts.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(entries) != 1 or entries[0].get("server_grade", {}).get("passed") is not False:
        raise AssertionError(f"unexpected visible failure archive for {label}: {entries}")
    destination = output / "failure_artifacts" / f"{label}-rejected-attempt.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(entries[0], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"artifact": str(destination.relative_to(output)), "server_grade": entries[0]["server_grade"]}


def run_variant(
    browser,
    task_path: Path,
    difficulty: int,
    interaction: str,
    output: Path,
    scratch: Path,
    helpers,
    solver,
    *,
    label: str,
    original_baseline: bool = False,
) -> dict[str, Any]:
    state_dir = scratch / label
    state_dir.mkdir()
    port = free_port()
    process = start_server(task_path, state_dir, port, f"reload-controls-d{difficulty}")
    page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page_errors: list[str] = []
    console_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    try:
        # /state intentionally creates a fresh task when current_task.json is
        # present.  Keep the prepared, paired seed visible for this initial
        # browser observation, matching the shared controlled-interaction
        # smoke.  Restore it immediately so a visibly failed attempt still
        # exercises the normal fresh-challenge path.
        current_task_path = state_dir / "current_task.json"
        current_task_text = current_task_path.read_text(encoding="utf-8")
        current_task_path.unlink()
        try:
            page.goto(f"http://127.0.0.1:{port}/?time_mode=paused&start_paused=1", wait_until="networkidle")
        finally:
            current_task_path.write_text(current_task_text, encoding="utf-8")
        page.evaluate("""() => {
          window.__reloadEvidencePointerEvents = [];
          for (const name of ["pointerdown", "pointerup", "pointercancel", "mousedown", "mouseup"]) {
            window.addEventListener(name, event => window.__reloadEvidencePointerEvents.push({name, target: event.target?.className || event.target?.tagName || "", time: performance.now()}), true);
          }
        }""")
        expect(page.locator(".reload-v2")).to_be_visible()
        pause_after_preview(page)
        expect(page.locator(".reload-v2")).to_have_attribute("data-interaction", interaction)
        initial = read_json(state_dir / "public_state.json")
        initial_state_path = output / "initial_states" / f"{label}.json"
        initial_state_path.parent.mkdir(parents=True, exist_ok=True)
        initial_state_path.write_text(json.dumps(initial, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        page.screenshot(path=str(output / f"{label}-initial.png"))
        before_delay = page.evaluate("WeirdCaptchaTime.status()")
        page.wait_for_timeout(240)
        after_delay = page.evaluate("WeirdCaptchaTime.status()")
        page.screenshot(path=str(output / f"{label}-model-observation-paused.png"))
        if abs(float(after_delay["task_time_ms"]) - float(before_delay["task_time_ms"])) > 1:
            raise AssertionError(f"paused model delay advanced task time for {label}")

        wrong = next(direction for direction in solver.VECTORS if direction != initial["sequence"][0])
        before_failure = page.evaluate("WeirdCaptchaTime.status()")
        page.evaluate("WeirdCaptchaTime.resume()")
        solver._gesture(page, wrong, interaction)
        expect(page.locator(".readout")).to_have_text("FAIL", timeout=3_000)
        page.screenshot(path=str(output / f"{label}-failure.png"))
        page.wait_for_timeout(920)
        page.evaluate("WeirdCaptchaTime.pause()")
        after_failure = page.evaluate("WeirdCaptchaTime.status()")
        if float(after_failure["task_time_ms"]) <= float(before_failure["task_time_ms"]):
            raise AssertionError(f"visible failed action did not advance task time for {label}")
        failure = save_failure(state_dir, output, label)
        recovered = read_json(state_dir / "public_state.json")
        if recovered["challenge_id"] == initial["challenge_id"]:
            raise AssertionError(f"failure did not issue a fresh challenge for {label}")
        pause_after_preview(page)

        action_cycles: list[dict[str, Any]] = []
        for index, direction in enumerate(recovered["sequence"], start=1):
            starts_interruption = any(int(spec["after_step"]) == index for spec in recovered["interruptions"])
            action_cycles.append(paused_action(
                page,
                f"gesture-{index}-{direction}",
                lambda direction=direction: solver._gesture(page, direction, interaction),
                settle_ms=1_000 if index == len(recovered["sequence"]) else (800 if starts_interruption else 90),
            ))
            if not starts_interruption:
                continue
            expect(page.locator(".reload-overload")).to_be_visible(timeout=2_000)
            page.screenshot(path=str(output / f"{label}-active-overload-{index}.png"))
            spec = next(item for item in recovered["interruptions"] if int(item["after_step"]) == index)
            action_cycles.append(paused_action(
                page,
                f"overload-{index}",
                lambda spec=spec: clear_visible_overload(page, solver, interaction, spec),
                settle_ms=100,
            ))
        expect(page.locator(".readout")).to_have_attribute("data-status", "passed", timeout=3_000)
        page.screenshot(path=str(output / f"{label}-pass.png"))
        if page_errors or console_errors:
            raise AssertionError(f"browser errors for {label}: page={page_errors}, console={console_errors}")
        export = export_and_verify(state_dir, output, label, helpers)
        return {
            "condition": {
                "difficulty": difficulty,
                "interaction": interaction,
                "real_time": "paused",
                "label": label,
                "original_baseline": original_baseline,
            },
            "initial_challenge_id": initial["challenge_id"],
            "retry_challenge_id": recovered["challenge_id"],
            "world_pair_fingerprint": json.dumps({key: value for key, value in initial.items() if key not in {"task_id", "challenge_id", "control_condition"}}, sort_keys=True),
            "model_delay": {"before": before_delay, "after_240ms": after_delay},
            "failure": failure,
            "paused_action_cycles": action_cycles,
            "export": export,
            "browser_errors": {"page": page_errors, "console": console_errors},
        }
    except Exception as error:
        # Preserve the visible frame and server transcript for a rejected
        # timing route.  The caller still receives the failure; this is
        # evidence for diagnosis, not a retry that can turn it into a pass.
        diagnostics = output / "diagnostics"
        diagnostics.mkdir(parents=True, exist_ok=True)
        try:
            page.screenshot(path=str(diagnostics / f"{label}-error.png"))
        except Exception:  # pragma: no cover - page may already be gone.
            pass
        attempts = state_dir / "attempts.jsonl"
        if attempts.is_file():
            shutil.copy2(attempts, diagnostics / f"{label}-attempts.jsonl")
        try:
            pointer_events = page.evaluate("window.__reloadEvidencePointerEvents || []")
            (diagnostics / f"{label}-pointer-events.json").write_text(
                json.dumps(pointer_events, indent=2) + "\n", encoding="utf-8"
            )
        except Exception:  # pragma: no cover - page may already be gone.
            pass
        (diagnostics / f"{label}-error.txt").write_text(str(error) + "\n", encoding="utf-8")
        raise
    finally:
        page.close()
        stop_server(process)


def main() -> None:
    args = parse_args()
    if args.original_baseline and (args.difficulty is not None or args.interaction is not None):
        raise SystemExit("--original-baseline cannot be combined with --difficulty or --interaction")
    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    materializer = load_module("reload_evidence_materializer", MATERIALIZER)
    helpers = load_module("reload_evidence_helpers", HELPERS)
    solver = load_module("reload_evidence_solver", SOLVER)
    setup = load_module("reload_evidence_setup", SETUP)
    controls = read_json(ENV_ROOT / "controls.json")
    with tempfile.TemporaryDirectory(prefix="reload-controls-evidence-") as temporary:
        scratch = Path(temporary)
        variants: list[dict[str, Any]] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            if args.original_baseline:
                variants.append(run_variant(
                    browser,
                    ENV_ROOT / "tasks" / "reload_interruption_seed_0001" / "task.json",
                    4,
                    "full",
                    output,
                    scratch,
                    helpers,
                    solver,
                    label="original-uncontrolled-l4-full",
                    original_baseline=True,
                ))
            else:
                materialized = scratch / "materialized"
                materializer.materialize_environment(ENV_ROOT, materialized)
                tasks_root = materialized / ENV_ROOT.name / "tasks"
                difficulties = (args.difficulty,) if args.difficulty else range(1, 6)
                interactions = (args.interaction,) if args.interaction else ("simplified", "full")
                for difficulty in difficulties:
                    for interaction in interactions:
                        variants.append(run_variant(
                            browser,
                            controlled_task(tasks_root, difficulty, interaction),
                            difficulty,
                            interaction,
                            output,
                            scratch,
                            helpers,
                            solver,
                            label=f"d{difficulty}-{interaction}",
                        ))
            # Repeat the most timing-sensitive visible path after its first
            # successful run; a passing single run does not establish a race fix.
            if not args.original_baseline and not args.skip_repeats and args.difficulty in (None, 5) and args.interaction in (None, "full"):
                for number in (1, 2):
                    variants.append(run_variant(
                        browser,
                        controlled_task(tasks_root, 5, "full"),
                        5,
                        "full",
                        output,
                        scratch,
                        helpers,
                        solver,
                        label=f"d5-full-repeat-{number}",
                    ))
            browser.close()
    pair_worlds = {}
    for difficulty in range(1, 6):
        pair = [item for item in variants if item["condition"]["difficulty"] == difficulty and "repeat" not in item["condition"].get("label", "")]
        originals = [item for item in pair if item["condition"]["interaction"] in {"simplified", "full"}]
        if len(originals) >= 2:
            pair_worlds[str(difficulty)] = originals[0]["world_pair_fingerprint"] == originals[1]["world_pair_fingerprint"]
    baseline_preservation = None
    if args.original_baseline:
        original_task = read_json(ENV_ROOT / "tasks" / "reload_interruption_seed_0001" / "task.json")
        controlled_task_document = materializer.controlled_task(
            original_task,
            mechanic_id="reload_interruption",
            level=4,
            interaction="full",
            profile=controls["difficulty"]["4"],
            task_dir_name="reload_interruption_d4_full_seed_0001",
        )
        original_public, original_truth = setup.generate_task_state(original_task, "reload-controls-d4")
        controlled_public, controlled_truth = setup.generate_task_state(controlled_task_document, "reload-controls-d4")
        for state in (controlled_public, controlled_truth):
            for key in ("task_id", "control_condition"):
                state.pop(key, None)
        for state in (original_public, original_truth):
            state.pop("task_id", None)
        if controlled_public != original_public or controlled_truth != original_truth:
            raise AssertionError("controlled L4/full does not preserve the original fixed-seed world")
        baseline_preservation = {
            "seed": "reload-controls-d4",
            "public_state_equal_after_control_identity": True,
            "ground_truth_equal_after_control_identity": True,
        }
    summary = {
        "environment": "reload_interruption_env",
        "mechanic": "reload_interruption",
        "isolation": {
            "browser": "Playwright Chromium headless with an ephemeral browser process",
            "servers": "temporary state directories on 127.0.0.1 only",
            "viewport": [1280, 720],
        },
        "real_time": controls["real_time"],
        "baseline_preservation": baseline_preservation,
        "interaction_pair_worlds_preserved": pair_worlds,
        "variants": variants,
        "notes": [
            "The scripted route reads generated state only to choose actions, then uses the normal visible pointer controls.",
            "Each paused action resumes the shared task clock for the complete action and freezes it for a 240 ms model-inference interval afterward.",
            "The two L5/full repetitions exercise the full tracker and the virtual final-submit timer after a prior paused-path failure was corrected.",
        ],
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "variants": len(variants), "output": str(output)}, indent=2))


if __name__ == "__main__":
    main()
