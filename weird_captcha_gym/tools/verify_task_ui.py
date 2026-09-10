#!/usr/bin/env python3
"""Verify one controlled task through privileged planning and ordinary UI input.

This is an implementation smoke, not a benchmark CLI or a model evaluation.
The existing generator, runtime, input recorder, solver and verifier are reused.
Each invocation preserves one independent attempt in a new output directory.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from weird_captcha_gym.shared_scripts.setup_task import generate_task_state
from weird_captcha_gym.tools.env_step_action_trace import RECORDER_SCRIPT, parse_input_trace
from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment
from weird_captcha_gym.tools.smoke_controlled_interaction_ui import (
    controlled_task, load_module, observation_viewport, read_json, reserve_port,
)
from weird_captcha_gym.tools.verify_randomized_env_step_matrix import (
    _collect_context_events, _reject_programmatic_solver_actions,
)

BENCH = ROOT / "weird_captcha_gym"


def write(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def check_solver_actions(path: Path) -> None:
    _reject_programmatic_solver_actions(path)
    # These high-level setters do not produce the mouse/keyboard procedure
    # expected from a model. Locator.click still dispatches trusted input.
    forbidden = {"select_option", "fill", "check", "uncheck", "set_checked",
                 "dispatch_event", "set_input_files", "goto", "reload",
                 "set_content", "add_script_tag", "add_init_script"}
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in forbidden:
            raise AssertionError(f"{path}:{node.lineno}: oracle uses forbidden action {node.func.attr}")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "WeirdCaptchaTime" in node.value:
            raise AssertionError(f"{path}:{node.lineno}: task clock belongs to the harness, not the oracle")


def check_clock(page, base: str, controls: dict) -> dict:
    """Exercise the existing runner clock/input protocol, not a solving policy.

    This checks frozen renders, input delivery, and exact fixed-window clock
    endpoints. It is not an env.step solve or a frame-sampling calibration.
    """
    from weird_captcha_gym.tools.smoke_realtime_control import (
        post, post_input, wait_status, wait_input_status,
    )

    wait_status(base, lambda item: item.get('ready') is True)
    armed = post_input(base, dict(command='arm',category='mouse',required=True))
    wait_input_status(base, lambda item: item.get('command_sequence')==armed['sequence'] and item.get('phase')=='armed')
    before = page.evaluate('WeirdCaptchaTime.status().task_time_ms')
    page.mouse.move(2,2)
    complete = post_input(base, dict(command='complete',arm_sequence=armed['arm_sequence']))
    receipt = wait_input_status(base, lambda item: item.get('command_sequence')==complete['sequence'] and item.get('phase') in ('completed','missing'))
    assert receipt.get('receipt_confirmed') is True, receipt
    assert page.evaluate('WeirdCaptchaTime.status().task_time_ms')==before
    first = page.screenshot()
    page.wait_for_timeout(180)
    assert page.screenshot()==first, 'task render changed while its clock was paused'
    duration = int(controls['real_time']['observation_window_ms'])
    command = post(base, dict(command='run_for' if duration else 'pause',milliseconds=duration))
    end = wait_status(base, lambda item: item.get('sequence')==command['sequence'] and item.get('state')=='paused' and (not duration or item.get('phase')=='completed'))
    assert abs(end['task_time_ms']-before-duration)<.001, end
    page.wait_for_timeout(180)
    assert abs(page.evaluate('WeirdCaptchaTime.status().task_time_ms')-end['task_time_ms'])<.001
    return dict(paused_render_sha256=hashlib.sha256(first).hexdigest(),input_receipt=receipt,
                observation_window_ms=duration,task_time_before_ms=before,task_time_after_ms=end['task_time_ms'],
                refrozen=True,scope='shared clock/input protocol only; not a paused env.step solve')


def source_hashes(mechanic: str) -> dict[str, str]:
    paths = [
        BENCH / "environments" / f"{mechanic}_env" / "controls.json",
        BENCH / "shared_scripts/incubator_generators" / f"{mechanic}.py",
        BENCH / "shared_runtime/app/mechanics" / f"{mechanic}.js",
        BENCH / "shared_runtime/app/mechanics" / f"{mechanic}.css",
        BENCH / "shared_runtime/server/incubator_graders" / f"{mechanic}.py",
        BENCH / "tools/incubator_solvers" / f"{mechanic}.py",
    ]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def run(args) -> bool:
    from playwright.sync_api import sync_playwright
    from weird_captcha_gym.tools.smoke_incubator_batch_one_ui import exported_payload, run_task_verifier
    from weird_captcha_gym.tools.smoke_realtime_control import wait_status

    env_root = BENCH / "environments" / args.environment
    controls = read_json(env_root / "controls.json")
    mechanic = controls["mechanic_id"]
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    screens = out / "screenshots"
    screens.mkdir()
    state = out / "state"
    state.mkdir()
    task_root = out / "materialized"
    materialize_environment(env_root, task_root)
    task_path = controlled_task(task_root / env_root.name / "tasks", args.difficulty, args.interaction)
    subprocess.run([sys.executable, "-B", str(BENCH / "shared_scripts/setup_task.py"),
                    "--task-json", str(task_path), "--state-dir", str(state), "--seed", args.seed],
                   cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    # The runtime's existing task-token handshake retains the fixed setup seed
    # on initial navigation. No state is altered after task interaction begins.
    task_record = read_json(state / "current_task.json")
    token = "ui-check-" + out.name
    task_record["client_task_token"] = token
    write(state / "current_task.json", task_record)
    initial_public = read_json(state / "public_state.json")
    initial_truth = read_json(state / "ground_truth.json")
    other = "full" if args.interaction == "simplified" else "simplified"
    opposite_task = read_json(task_path)
    opposite_task["metadata"]["control_condition"]["interaction"] = other
    # Generate the opposite surface, rather than relabelling its world. Some
    # mechanics have mode-specific UI fields outside control_condition.
    opposite_public, opposite_truth = generate_task_state(opposite_task, args.seed)
    write(out / "opposite-world.json", {"public_state": opposite_public, "ground_truth": opposite_truth})
    solver_path = BENCH / "tools/incubator_solvers" / f"{mechanic}.py"
    check_solver_actions(solver_path)
    solver = load_module(f"ui_solver_{mechanic}", solver_path)
    grader = load_module(f"ui_grader_{mechanic}", BENCH / "shared_runtime/server/incubator_graders" / f"{mechanic}.py")
    hashes = source_hashes(mechanic)
    record = {"environment": env_root.name, "mechanic": mechanic, "difficulty": args.difficulty,
              "interaction": args.interaction, "seed": args.seed, "check": args.check,
              "solve_entrypoint": args.solve_entrypoint,
              "headless": True, "fresh_browser_profile": True, "viewport": observation_viewport(env_root),
              "source_hashes": hashes, "scope": "Privileged-information ordinary-input live browser smoke, not model evaluation"}
    record['harness_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    started = time.monotonic()
    port = reserve_port()
    errors = []
    with (out / "server.log").open("x") as log:
        server = subprocess.Popen([sys.executable, "-B", str(BENCH / "shared_runtime/server/weird_captcha_server.py"),
            "--host", "127.0.0.1", "--port", str(port), "--app-dir", str(BENCH / "shared_runtime/app"),
            "--state-dir", str(state)], cwd=ROOT, stdout=log, stderr=log,
            env={**os.environ, "WEIRD_CAPTCHA_CHALLENGE_SEED": args.seed})
        try:
            deadline = time.monotonic() + 15
            while True:
                if server.poll() is not None:
                    raise RuntimeError("isolated task server exited")
                try:
                    with urlopen(f"http://127.0.0.1:{port}/health", timeout=.5) as response:
                        response.read()
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("isolated task server did not become healthy")
                    time.sleep(.1)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport=record["viewport"], device_scale_factor=1)
                context.add_init_script(RECORDER_SCRIPT)
                page = context.new_page()
                page.set_default_timeout(15000)
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                try:
                    base = f"http://127.0.0.1:{port}"
                    mode = 'paused' if args.check=='clock' else 'live'
                    # The enabled clock protocol polls continuously, so its
                    # ready acknowledgement replaces network-idle detection.
                    page.goto(f"{base}/?task={token}&time_mode={mode}&start_paused=1&time_control={int(args.check=='clock')}",
                              wait_until='domcontentloaded' if args.check=='clock' else 'networkidle')
                    if args.check=='clock':
                        wait_status(base, lambda item: item.get('ready') is True)
                        page.evaluate('document.fonts.ready')
                    root_selector = page.evaluate("id => window.WeirdCaptchaMechanics?.[id]?.rootSelector", mechanic)
                    assert isinstance(root_selector, str) and root_selector, "mechanic did not register its task root"
                    page.locator(root_selector).wait_for(state="visible")
                    record["root_selector"] = root_selector
                    assert read_json(state / "public_state.json") == initial_public
                    assert read_json(state / "ground_truth.json") == initial_truth
                    page.screenshot(path=str(screens / "initial.png"))
                    # Shared framework bootstrap only. No pause/resume is
                    # permitted inside the live solving policy.
                    if args.check == 'clock':
                        record['clock_check'] = check_clock(page,base,controls)
                        record['scope'] = record['clock_check']['scope']
                    else:
                        page.evaluate("() => WeirdCaptchaTime.resume()")
                    if args.check == "failure":
                        initial_root = page.locator(root_selector).element_handle()
                        with page.expect_response(lambda response: response.request.method == "POST" and urlparse(response.url).path == "/result", timeout=60000) as received:
                            solver.fail_once(page, state, screens, mechanic)
                        response = received.value.json()
                        assert response.get("passed") is False, "negative action was not rejected by the server"
                        attempts = state / "attempts.jsonl"
                        assert attempts.is_file(), "negative helper never submitted to the server"
                        failed = [json.loads(line) for line in attempts.read_text().splitlines() if line.strip()]
                        assert failed and failed[-1].get("server_grade", {}).get("passed") is False
                        fresh = read_json(state / "public_state.json")
                        assert fresh["challenge_id"] != initial_public["challenge_id"], "failure did not generate a fresh challenge"
                        assert response.get("state", {}).get("challenge_id") == fresh["challenge_id"], "fresh world was not returned to the browser"
                        page.wait_for_function("({old, fresh}) => !old.isConnected || old.dataset.challengeId === fresh",
                                               arg={"old": initial_root, "fresh": fresh["challenge_id"]})
                        page.locator(root_selector).wait_for(state="visible")
                        record["failed_server_grade"] = failed[-1]["server_grade"]
                        record["fresh_challenge_after_failure"] = True
                    elif args.check != 'clock':
                        getattr(solver, args.solve_entrypoint)(page, state, screens, mechanic)
                        exported = exported_payload(state)
                        write(out / "exported.json", exported)
                        record["server_grade"] = exported["result"].get("server_grade") or {}
                        record["direct_grade"] = grader.grade(exported["result"], exported["ground_truth"], exported["public_state"])
                        record["exported_verifier"] = run_task_verifier(mechanic, exported, out)
                        assert all(record[key].get("passed") is True for key in ("server_grade", "direct_grade", "exported_verifier")), record
                        assert exported["ground_truth"]["challenge_id"] == initial_truth["challenge_id"], "positive solve changed challenge"
                        rebound = copy.deepcopy(exported["result"])
                        for key in ("task_id", "challenge_id"):
                            rebound[key] = opposite_truth[key]
                        if "control_condition" in rebound:
                            rebound["control_condition"] = copy.deepcopy(opposite_truth["control_condition"])
                        for key in ("interaction", "interaction_mode"):
                            if key in rebound:
                                rebound[key] = other
                        record["opposite_mode_grade"] = grader.grade(rebound, opposite_truth, opposite_public)
                        assert record["opposite_mode_grade"].get("passed") is False, "opposite-mode events passed"
                    record["status"] = "passed"
                finally:
                    page.screenshot(path=str(screens / "final.png"))
                    events = _collect_context_events(context)
                    write(out / "input-events.json", events)
                    write(out / "action-groups.json", parse_input_trace(events))
                    record["input_event_count"] = len(events)
                    record["untrusted_input_events"] = [e for e in events if e["type"] == "input" and not e.get("trusted")]
                    context.close()
                    browser.close()
            assert record["input_event_count"] > 0, "no recorded UI input"
            assert not record["untrusted_input_events"], "programmatic input changed a control"
            assert not errors, errors
        except Exception as error:
            record.update(status="failed", error_type=type(error).__name__, error=str(error))
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
            record["browser_errors"] = errors
            record["source_unchanged_during_run"] = source_hashes(mechanic) == hashes
            if not record["source_unchanged_during_run"]:
                record.update(status="failed", error="source changed during the run")
            record["elapsed_seconds"] = round(time.monotonic() - started, 3)
            write(out / "summary.json", record)
    print(json.dumps(record, indent=2))
    return record["status"] == "passed"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--difficulty", type=int, choices=range(1, 6), required=True)
    parser.add_argument("--interaction", choices=("simplified", "full"), required=True)
    parser.add_argument("--seed", default="1")
    parser.add_argument("--check", choices=("solve", "failure", "clock"), default="solve")
    parser.add_argument("--solve-entrypoint", default="solve", help="ordinary-input function in the existing mechanic solver")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.out_dir.exists():
        parser.error('output directory already exists; preserving the earlier attempt')
    try:
        passed = run(args)
    except Exception as error:
        # Setup/import failures occur before the browser/server try block.
        # Preserve them too, without replacing any earlier attempt's record.
        record = dict(status='failed',phase='setup',environment=args.environment,
                      difficulty=args.difficulty,interaction=args.interaction,seed=args.seed,
                      check=args.check,error_type=type(error).__name__,error=str(error))
        args.out_dir.mkdir(parents=True,exist_ok=True)
        if not (args.out_dir/'summary.json').exists():write(args.out_dir/'summary.json',record)
        print(json.dumps(record,indent=2))
        passed = False
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
