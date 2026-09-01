#!/usr/bin/env python3
"""Capture Turtle Forger's 5x2x2 matrix in isolated headless Chromium.

Every condition gets a fresh temporary persistent profile and a loopback-only
puzzle server. The script never attaches to an existing browser profile or any
foreground application.
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
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "turtle_forger_env"
EVIDENCE = ENVIRONMENT / "evidence_docs"
MECHANIC = "turtle_forger"
BASE_TASK = ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json"
CONTROLS = ENVIRONMENT / "controls.json"
SETUP = BENCHMARK / "shared_scripts" / "setup_task.py"
EXPORT = BENCHMARK / "shared_scripts" / "export_result.sh"
SERVER = BENCHMARK / "shared_runtime" / "server" / "weird_captcha_server.py"
APP = BENCHMARK / "shared_runtime" / "app"
GRADER = BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py"
SOLVER = BENCHMARK / "tools" / "incubator_solvers" / f"{MECHANIC}.py"
VERIFIER = BASE_TASK.parent / "verifier.py"
VIEWPORT = {"width": 1280, "height": 720}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reserve_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def condition_task(temporary: Path, level: int, interaction: str, mode: str) -> Path:
    controls = read_json(CONTROLS)
    task = read_json(BASE_TASK)
    task["metadata"]["control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": mode,
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
    }
    suffix = "_tpaused" if mode == "paused" else ""
    task["id"] = f"{MECHANIC}_d{level}_{interaction}_seed_0001{suffix}@0.1"
    path = temporary / "tasks" / f"d{level}-{interaction}-{mode}.json"
    write_json(path, task)
    return path


def start_server(task: Path, state_dir: Path, seed: str) -> tuple[subprocess.Popen[bytes], int]:
    subprocess.run(
        ["python", "-B", str(SETUP), "--task-json", str(task), "--state-dir", str(state_dir), "--seed", seed],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    port = reserve_port()
    process = subprocess.Popen(
        ["python", "-B", str(SERVER), "--host", "127.0.0.1", "--port", str(port), "--app-dir", str(APP), "--state-dir", str(state_dir)],
        cwd=ROOT,
        env={**os.environ, "WEIRD_CAPTCHA_CHALLENGE_SEED": seed, "WEIRD_CAPTCHA_CHEAT_PASSWORD": "turtle-evidence-only"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            urlopen(f"http://127.0.0.1:{port}/health", timeout=.5).read()
            return process, port
        except Exception:  # noqa: BLE001
            time.sleep(.1)
    process.kill()
    raise TimeoutError(f"loopback server did not start on {port}")


def stop_server(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()


def world_fingerprint(state: dict) -> str:
    content = {
        "canvas": state["canvas"],
        "start": state["start"],
        "command_palette": state["command_palette"],
        "runtime_target_segments": state["runtime_target_segments"],
        "parameters": state["parameters"],
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def exported(state_dir: Path, output: Path, label: str) -> tuple[dict, dict]:
    completed = subprocess.run(
        ["bash", str(EXPORT)],
        cwd=ROOT,
        env={**os.environ, "WEIRD_CAPTCHA_STATE_DIR": str(state_dir)},
        check=True,
        text=True,
        capture_output=True,
    )
    task_result = Path("/tmp/task_result.json")
    if not task_result.is_file():
        raise AssertionError("shared export did not create /tmp/task_result.json")
    payload = read_json(task_result)
    path = output / "exports" / f"{label}.json"
    write_json(path, payload)
    return payload, {
        "command": ["bash", "weird_captcha_gym/shared_scripts/export_result.sh"],
        "environment": {"WEIRD_CAPTCHA_STATE_DIR": "<isolated-condition-state-dir>"},
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "artifact": str(path.relative_to(output)),
        "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def verify_export(export_path: Path, label: str) -> dict:
    verifier = load_module(VERIFIER, f"turtle_verifier_{label.replace('-', '_')}")

    def copy_from_env(source: str, destination: str) -> None:
        if source != "/tmp/task_result.json":
            raise AssertionError(f"unexpected verifier source {source}")
        shutil.copyfile(export_path, destination)

    return verifier.verify_task(env_info={"copy_from_env": copy_from_env})


def surface_contract(page, phase: str) -> dict:
    active_reference = page.locator("#tfg-reference-active line").count()
    support_lines = page.locator(".tfg-reference .tfg-grid line").count()
    text = page.locator(".turtle-forger").inner_text().upper()
    forbidden = [term for term in ("CANONICAL_PROGRAM", "TARGET_SEGMENTS", "GROUND_TRUTH") if term in text]
    verdict_node = page.locator(".tfg-verdict")
    verdict = verdict_node.inner_text().strip() if verdict_node.count() else ""
    result = {
        "phase": phase,
        "active_reference_strokes": active_reference,
        "visible_registration_support_lines": support_lines,
        "forbidden_visible_strings": forbidden,
        "verdict": verdict,
        "passed": active_reference <= 1 and not forbidden,
    }
    if phase == "initial":
        result["passed"] = result["passed"] and active_reference == 0 and verdict == ""
    elif phase == "failure-fresh":
        result["passed"] = result["passed"] and "FAIL" in verdict
    elif phase == "pass":
        result["passed"] = result["passed"] and "PASS" in verdict
    if not result["passed"]:
        raise AssertionError(f"visible surface contract failed: {result}")
    return result


def capture_complete_scan(
    page,
    output: Path,
    *,
    level: int,
    interaction: str,
    mode: str,
    preserve_frames: bool,
) -> dict:
    """Run the successful challenge's complete visible scan.

    These are direct isolated-page captures, not evaluator/model inputs.  For
    one full/live condition at every difficulty we preserve one near-complete
    frame for every transient stroke so the visual ladder is inspectable.
    Every other condition still runs the whole scan before solving.
    """
    folder = output / "direct_scan_sequences" / f"d{level}-{interaction}-{mode}"
    if preserve_frames:
        folder.mkdir(parents=True, exist_ok=True)
    page.evaluate("() => WeirdCaptchaTime.resume()")
    before = page.evaluate("() => WeirdCaptchaTime.status()")
    page.locator("#tfg-scan").click()
    # The segment count is intentionally taken from the rendered public
    # surface rather than ground truth.  During a scan it is exposed in the
    # visible counter as the denominator.
    page.wait_for_function("document.querySelector('#tfg-scan-counter')?.textContent.includes('/')")
    counter = page.locator("#tfg-scan-counter").inner_text().strip()
    total = int(counter.rsplit("/", 1)[1].strip())
    # Difficulty timing is public control metadata used only to sample close
    # to the end of each visible stroke; it does not reveal target geometry.
    controls = read_json(CONTROLS)
    stroke_ms = int(controls["difficulty"][str(level)]["parameters"]["stroke_ms"])
    gap_ms = int(controls["difficulty"][str(level)]["parameters"]["gap_ms"])
    records = []
    seen: list[int] = []
    for index in range(total):
        wanted = index + 1
        page.wait_for_function(
            "([wanted]) => document.querySelector('#tfg-scan-counter')?.textContent.startsWith(`STROKE ${String(wanted).padStart(2, '0')} /`)",
            arg=[wanted],
            timeout=max(5_000, (stroke_ms + gap_ms) * 3),
        )
        page.wait_for_timeout(round(stroke_ms * .72))
        scan_counter = page.locator("#tfg-scan-counter").inner_text().strip()
        if not scan_counter.startswith(f"STROKE {wanted:02d} /"):
            raise AssertionError(f"scan sampling skipped stroke {wanted}: {scan_counter}")
        visible_strokes = page.locator("#tfg-reference-active line").count()
        if visible_strokes != 1:
            raise AssertionError(f"stroke {wanted} exposed {visible_strokes} visible lines")
        row = {
            "stroke_index": wanted,
            "scan_counter": scan_counter,
            "visible_strokes": visible_strokes,
            "task_time_ms": round(float(page.evaluate("() => WeirdCaptchaTime.status().task_time_ms")), 3),
        }
        if preserve_frames:
            path = folder / f"stroke-{wanted:03d}.png"
            page.screenshot(path=str(path))
            row.update({
                "path": str(path.relative_to(output)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
        records.append(row)
        seen.append(wanted)
    expect(page.locator("#tfg-scan-counter")).to_have_text(
        "SCAN COMPLETE · REPLAY AVAILABLE",
        timeout=max(5_000, (stroke_ms + gap_ms) * 2),
    )
    after = page.evaluate("() => WeirdCaptchaTime.status()")
    if mode == "paused":
        page.evaluate("() => WeirdCaptchaTime.pause()")
    if seen != list(range(1, total + 1)):
        raise AssertionError(f"incomplete direct scan sequence: {seen}")
    return {
        "provenance": "direct isolated headless Playwright page capture; not evaluator-delivered and not a model observation",
        "successful_challenge": True,
        "complete_scan": True,
        "preserved_visual_frames": preserve_frames,
        "expected_strokes": total,
        "observed_strokes": seen,
        "configured_stroke_ms": stroke_ms,
        "configured_gap_ms": gap_ms,
        "task_time_delta_ms": round(float(after["task_time_ms"]) - float(before["task_time_ms"]), 3),
        "frames": records,
    }


def capture_live_auto_replay_recovery(page, output: Path, scan: dict) -> dict:
    """Show that a delayed live observer can reach late strokes on a later cycle."""
    folder = output / "live_auto_replay_recovery"
    folder.mkdir(parents=True, exist_ok=True)
    button = page.locator("#tfg-auto-replay")
    before = page.evaluate("() => WeirdCaptchaTime.status()")
    button.click()
    expect(button).to_have_attribute("aria-pressed", "true")
    total = int(scan["expected_strokes"])
    stroke_ms = int(scan["configured_stroke_ms"])
    gap_ms = int(scan["configured_gap_ms"])
    cycle_ms = total * (stroke_ms + gap_ms)
    page.wait_for_function(
        "document.querySelector('#tfg-scan-counter')?.textContent.startsWith('CYCLE 02 · STROKE 01 /')",
        timeout=cycle_ms + 5_000,
    )
    page.wait_for_timeout(round(stroke_ms * .55))
    early = folder / "cycle-02-stroke-01.png"
    page.screenshot(path=str(early))
    early_counter = page.locator("#tfg-scan-counter").inner_text().strip()
    page.wait_for_function(
        "([total]) => document.querySelector('#tfg-scan-counter')?.textContent.startsWith(`CYCLE 02 · STROKE ${String(total).padStart(2, '0')} /`)",
        arg=[total],
        timeout=cycle_ms + 5_000,
    )
    page.wait_for_timeout(round(stroke_ms * .55))
    late = folder / f"cycle-02-stroke-{total:02d}.png"
    page.screenshot(path=str(late))
    late_counter = page.locator("#tfg-scan-counter").inner_text().strip()
    button.click()
    expect(button).to_have_attribute("aria-pressed", "false")
    expect(page.locator("#tfg-scan-counter")).to_have_text(
        "SCAN COMPLETE · REPLAY AVAILABLE",
        timeout=cycle_ms + 5_000,
    )
    after = page.evaluate("() => WeirdCaptchaTime.status()")
    delta = float(after["task_time_ms"]) - float(before["task_time_ms"])
    if delta <= cycle_ms:
        raise AssertionError(
            f"auto replay did not remain available beyond one full scan: {delta} <= {cycle_ms}"
        )
    if not early_counter.startswith("CYCLE 02 · STROKE 01 /"):
        raise AssertionError(f"missing second-cycle restart: {early_counter}")
    if not late_counter.startswith(f"CYCLE 02 · STROKE {total:02d} /"):
        raise AssertionError(f"late second-cycle stroke unavailable: {late_counter}")
    return {
        "provenance": "direct isolated headless Playwright page capture; not evaluator-delivered",
        "visible_control": "AUTO REPLAY ON/OFF",
        "configured_cycle_ms": cycle_ms,
        "task_time_delta_ms": round(delta, 3),
        "cycle_2_early_counter": early_counter,
        "cycle_2_late_counter": late_counter,
        "frames": [
            {"path": str(early.relative_to(output)), "sha256": hashlib.sha256(early.read_bytes()).hexdigest()},
            {"path": str(late.relative_to(output)), "sha256": hashlib.sha256(late.read_bytes()).hexdigest()},
        ],
        "claim": "The unchanged ordered scan restarted visibly and exposed its final stroke after a delay longer than one complete first cycle.",
    }


def delay_contract(page, mode: str) -> dict:
    if mode == "live":
        page.evaluate("() => WeirdCaptchaTime.resume()")
    else:
        page.evaluate("() => WeirdCaptchaTime.pause()")
    before = page.evaluate("() => WeirdCaptchaTime.status()")
    first_box = page.locator(".tfg-command").first.bounding_box()
    page.wait_for_timeout(360)
    after = page.evaluate("() => WeirdCaptchaTime.status()")
    delayed_box = page.locator(".tfg-command").first.bounding_box()
    if first_box is None or delayed_box is None:
        raise AssertionError("command drawer is not visible")
    delta = float(after["task_time_ms"]) - float(before["task_time_ms"])
    stable = max(abs(float(first_box[key]) - float(delayed_box[key])) for key in ("x", "y", "width", "height"))
    if mode == "live" and delta < 250:
        raise AssertionError(f"live clock did not advance during action delay: {delta}")
    if mode == "paused" and abs(delta) > 2:
        raise AssertionError(f"paused clock advanced during action delay: {delta}")
    if stable > .5:
        raise AssertionError(f"punch-card action target expired or moved: {stable}px")
    return {
        "task_time_delta_ms": round(delta, 3),
        "command_target_max_geometry_delta_px": round(stable, 3),
        "correct_action_expired": False,
    }


def invalid_attempt(page, state_dir: Path, interaction: str, solver) -> dict:
    initial = read_json(state_dir / "public_state.json")
    first_key = str(initial["command_palette"][0]["key"])
    solver._append_visible_card(page, first_key, interaction)
    page.locator("#tfg-proof").click()
    page.locator("#tfg-certify").click()
    expect(page.locator(".tfg-verdict.is-fail")).to_be_visible(timeout=8_000)
    refreshed = read_json(state_dir / "public_state.json")
    if refreshed["challenge_id"] == initial["challenge_id"]:
        raise AssertionError("invalid proof did not rotate to a fresh master")
    attempts = (state_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    archived = json.loads(attempts[-1])
    return {
        "initial_challenge_id": initial["challenge_id"],
        "fresh_challenge_id": refreshed["challenge_id"],
        "rotated": True,
        "server_grade": archived.get("server_grade"),
    }


def capture_condition(playwright, temporary: Path, output: Path, level: int, interaction: str, mode: str) -> dict:
    label = f"d{level}-{interaction}-{mode}"
    state_dir = temporary / "states" / label
    state_dir.mkdir(parents=True)
    task = condition_task(temporary, level, interaction, mode)
    seed = f"turtle-visible-d{level}"
    process, port = start_server(task, state_dir, seed)
    profile = temporary / "fresh-profiles" / label
    screenshots = output / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    context = playwright.chromium.launch_persistent_context(
        str(profile), headless=True, viewport=VIEWPORT, device_scale_factor=1,
    )
    page = context.pages[0]
    errors: list[str] = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    solver = load_module(SOLVER, f"turtle_solver_{label.replace('-', '_')}")
    try:
        page.goto(f"http://127.0.0.1:{port}/?time_mode={mode}&start_paused=1", wait_until="networkidle")
        expect(page.locator(".turtle-forger")).to_be_visible(timeout=8_000)
        classes = (page.locator(".turtle-forger").get_attribute("class") or "").split()
        if f"mode-{interaction}" not in classes:
            raise AssertionError(f"rendered interaction class mismatch: {classes}")
        initial_state = read_json(state_dir / "public_state.json")
        checks = [surface_contract(page, "initial")]
        if mode == "live":
            page.screenshot(path=str(screenshots / f"{label}-initial.png"))
        delay = delay_contract(page, mode)
        failure = invalid_attempt(page, state_dir, interaction, solver)
        checks.append(surface_contract(page, "failure-fresh"))
        successful_state = read_json(state_dir / "public_state.json")
        if level == 3 and interaction == "full" and mode == "live":
            page.screenshot(path=str(screenshots / "baseline-full-failure-fresh.png"))
        scan = capture_complete_scan(
            page,
            output,
            level=level,
            interaction=interaction,
            mode=mode,
            preserve_frames=interaction == "full" and mode == "live",
        )
        replay_recovery = (
            capture_live_auto_replay_recovery(page, output, scan)
            if level == 3 and interaction == "full" and mode == "live"
            else None
        )
        solver.solve(page, state_dir, output, MECHANIC, certify=False)
        score = page.locator("#tfg-score").inner_text().strip()
        if score != "100.00%":
            raise AssertionError(f"canonical visible proof scored {score}")
        meter_geometry = page.locator(".tfg-meter").evaluate(
            "node => ({container_width: node.getBoundingClientRect().width, "
            "fill_width: node.firstElementChild.getBoundingClientRect().width, "
            "display: getComputedStyle(node).display, "
            "transform: getComputedStyle(node.firstElementChild).transform})"
        )
        if mode == "live" and level in {3, 5}:
            page.screenshot(path=str(screenshots / f"d{level}-{interaction}-solved-before-certify.png"))
        page.locator("#tfg-certify").click()
        expect(page.locator(".tfg-verdict.is-pass")).to_be_visible(timeout=8_000)
        checks.append(surface_contract(page, "pass"))
        if mode == "live" and level in {3, 5}:
            page.screenshot(path=str(screenshots / f"d{level}-{interaction}-pass.png"))
        if mode == "paused":
            page.evaluate("() => WeirdCaptchaTime.pause()")
        export, export_command = exported(state_dir, output, label)
        export_path = output / export_command["artifact"]
        direct = load_module(GRADER, f"turtle_grader_{label.replace('-', '_')}").grade(
            export["result"], export["ground_truth"], export["public_state"],
        )
        verified = verify_export(export_path, label)
        server_grade = export["result"].get("server_grade") or {}
        if int(export["result"].get("scan_count") or 0) < 1:
            raise AssertionError("successful exported challenge bypassed SCAN MASTER")
        if not all(item.get("passed") is True for item in (server_grade, direct, verified)):
            raise AssertionError(f"grade mismatch server={server_grade} direct={direct} verifier={verified}")
        if errors:
            raise AssertionError(f"browser errors: {errors}")
        final_state = read_json(state_dir / "public_state.json")
        return {
            "label": label,
            "level": level,
            "interaction": interaction,
            "time_mode": mode,
            "headless": True,
            "fresh_profile": str(profile.relative_to(temporary)),
            "loopback_origin": f"http://127.0.0.1:{port}",
            "world_fingerprint": world_fingerprint(initial_state),
            "successful_world_fingerprint": world_fingerprint(successful_state),
            "final_world_fingerprint": world_fingerprint(final_state),
            "successful_challenge_scan": scan,
            "live_auto_replay_recovery": replay_recovery,
            "artificial_action_delay": delay,
            "failure_retry": failure,
            "visible_surface_checks": checks,
            "visible_program_score": score,
            "proof_meter_geometry": meter_geometry,
            "server_grade": server_grade,
            "direct_grade": direct,
            "verifier": verified,
            "export": export_command,
            "browser_errors": errors,
        }
    finally:
        context.close()
        stop_server(process)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="turtle-forger-isolated-") as temporary_text:
        temporary = Path(temporary_text)
        matrix = []
        with sync_playwright() as playwright:
            for level in range(1, 6):
                for interaction in ("simplified", "full"):
                    for mode in ("live", "paused"):
                        print(f"capturing d{level}-{interaction}-{mode}", flush=True)
                        matrix.append(capture_condition(playwright, temporary, output, level, interaction, mode))
        grouped: dict[tuple[int, str], list[dict]] = {}
        for item in matrix:
            grouped.setdefault((item["level"], item["interaction"]), []).append(item)
        for key, pair in grouped.items():
            if len(pair) != 2 or pair[0]["world_fingerprint"] != pair[1]["world_fingerprint"]:
                raise AssertionError(f"live/paused world mismatch for {key}: {pair}")
            if pair[0]["successful_world_fingerprint"] != pair[1]["successful_world_fingerprint"]:
                raise AssertionError(f"live/paused successful world mismatch for {key}: {pair}")
        for level in range(1, 6):
            worlds = {item["world_fingerprint"] for item in matrix if item["level"] == level}
            if len(worlds) != 1:
                raise AssertionError(f"interaction or schedule changed the d{level} world: {worlds}")
            successful_worlds = {
                item["successful_world_fingerprint"]
                for item in matrix
                if item["level"] == level
            }
            if len(successful_worlds) != 1:
                raise AssertionError(
                    f"interaction or schedule changed the successful d{level} world: {successful_worlds}"
                )
        summary = {
            "environment": "Turtle Forger",
            "mechanic_id": MECHANIC,
            "browser_isolation": {
                "headless": True,
                "fresh_temporary_persistent_profile_per_condition": True,
                "loopback_only": True,
                "existing_profile_or_window_attached": False,
            },
            "matrix_size": len(matrix),
            "all_twenty_wiring_paths_passed": len(matrix) == 20,
            "all_twenty_successful_exports_used_scan": all(
                item["successful_challenge_scan"]["complete_scan"] for item in matrix
            ),
            "matrix_evidence_boundary": (
                "The successful challenges visibly ran a complete scan, but a private-truth "
                "solver assembled the tapes. This matrix proves wiring and reachability, not "
                "screenshot-only playability or empirical difficulty."
            ),
            "live_paused_same_world": True,
            "interaction_modes_same_world": True,
            "conditions": matrix,
        }
        write_json(output / "browser_matrix.json", summary)
        print(json.dumps({"matrix_size": len(matrix), "all_twenty_wiring_paths_passed": True, "output": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
