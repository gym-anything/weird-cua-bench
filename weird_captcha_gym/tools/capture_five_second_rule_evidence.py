#!/usr/bin/env python3
"""Capture Five-Second Rule's 5x2x2 matrix in isolated headless Chromium.

Every condition uses a fresh temporary persistent Chromium profile and a
loopback-only server. This script never attaches to an existing browser,
profile, desktop, mouse, keyboard, or foreground application.
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

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments/five_second_rule_env"
EVIDENCE = ENVIRONMENT / "evidence_docs"
MECHANIC = "five_second_rule"
BASE_TASK = ENVIRONMENT / "tasks/five_second_rule_seed_0001/task.json"
CONTROLS = ENVIRONMENT / "controls.json"
SETUP = BENCHMARK / "shared_scripts/setup_task.py"
EXPORT = BENCHMARK / "shared_scripts/export_result.sh"
SERVER = BENCHMARK / "shared_runtime/server/weird_captcha_server.py"
APP = BENCHMARK / "shared_runtime/app"
GRADER = BENCHMARK / "shared_runtime/server/incubator_graders/five_second_rule.py"
SOLVER = BENCHMARK / "tools/incubator_solvers/five_second_rule.py"
VERIFIER = BASE_TASK.parent / "verifier.py"
VIEWPORT = {"width": 1290, "height": 740}


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
    task["id"] = f"{MECHANIC}_d{level}_{interaction}_seed_0001{suffix}@0.2"
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
        env={**os.environ, "WEIRD_CAPTCHA_CHALLENGE_SEED": seed, "WEIRD_CAPTCHA_CHEAT_PASSWORD": "five-second-evidence-only"},
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


def export_result(state_dir: Path, output: Path, label: str) -> tuple[dict, dict]:
    completed = subprocess.run(
        ["bash", str(EXPORT)],
        cwd=ROOT,
        env={**os.environ, "WEIRD_CAPTCHA_STATE_DIR": str(state_dir)},
        check=True,
        text=True,
        capture_output=True,
    )
    source = Path("/tmp/task_result.json")
    if not source.is_file():
        raise AssertionError("shared export did not create /tmp/task_result.json")
    payload = read_json(source)
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
    verifier = load_module(VERIFIER, f"five_second_verifier_{label.replace('-', '_')}")

    def copy_from_env(source: str, destination: str) -> None:
        if source != "/tmp/task_result.json":
            raise AssertionError(f"unexpected verifier source {source}")
        shutil.copyfile(export_path, destination)

    return verifier.verify_task(env_info={"copy_from_env": copy_from_env})


def center(locator) -> tuple[float, float]:
    box = locator.bounding_box()
    if box is None:
        raise AssertionError("visible control has no geometry")
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def task_status(page) -> dict:
    return page.evaluate("() => WeirdCaptchaTime.status()")


def advance_task(page, milliseconds: float) -> None:
    duration = max(0.0, float(milliseconds))
    if duration < 1:
        return
    before = float(task_status(page)["task_time_ms"])
    page.evaluate("target => WeirdCaptchaTime.resume(target)", before + duration)
    page.wait_for_timeout(duration + 30)
    page.evaluate("() => WeirdCaptchaTime.pause()")
    after = float(task_status(page)["task_time_ms"])
    if after < before + duration - 3:
        raise AssertionError(f"task clock advanced only {after - before:.3f}ms of requested {duration:.3f}ms")


def wait_round(page, spec: dict) -> None:
    page.wait_for_selector(f'.fsr-stage.family-{spec["family"]}', state="visible", timeout=7_000)


def capture_gate_observation(page, output: Path, mode: str, spec: dict) -> dict:
    target_id = spec["predicate"]["target_id"]
    token = next(item for item in spec["tokens"] if item["id"] == target_id)
    crossing = (float(spec["gate"]["x"]) - float(token["motion"]["x0"])) / float(token["motion"]["vx"]) * 1000
    advance_task(page, max(0, crossing - 600))
    folder = output / "model_observations" / f"baseline-full-{mode}"
    folder.mkdir(parents=True, exist_ok=True)
    records = []
    positions = []
    for index in range(6):
        if index:
            # Advance the task clock exactly between samples, then freeze it
            # while Chromium encodes the screenshot. Screenshot wall time must
            # not silently widen the declared 600 ms model window.
            advance_task(page, 120)
        path = folder / f"frame-{index:03d}.png"
        page.screenshot(path=str(path))
        point = center(page.locator(f'[data-token-id="{target_id}"]'))
        positions.append(point)
        records.append({
            "frame_index": index,
            "offset_ms": index * 120,
            "task_time_ms": round(float(task_status(page)["task_time_ms"]), 3),
            "target_center": [round(point[0], 3), round(point[1], 3)],
            "target_in_gate": "is-in-gate" in (page.locator(f'[data-token-id="{target_id}"]').get_attribute("class") or ""),
            "path": str(path.relative_to(output)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    motion = max(((x - positions[0][0]) ** 2 + (y - positions[0][1]) ** 2) ** .5 for x, y in positions[1:])
    if motion < 40 or not records[-1]["target_in_gate"]:
        raise AssertionError(f"gate observation did not end on a moving valid target: motion={motion}, final={records[-1]}")
    return {
        "observation_window_ms": 600,
        "frames_per_observation": 6,
        "target_id": target_id,
        "maximum_target_motion_px": round(motion, 3),
        "screen": records[-1]["path"],
        "screen_is_final_frame": True,
        "frames": records,
    }


def delay_contract(page, mode: str, target_id: str | None = None) -> dict:
    if mode == "live":
        page.evaluate("() => WeirdCaptchaTime.resume()")
    else:
        page.evaluate("() => WeirdCaptchaTime.pause()")
    before = task_status(page)
    point_before = center(page.locator(f'[data-token-id="{target_id}"]')) if target_id else None
    in_gate_before = None if not target_id else "is-in-gate" in (page.locator(f'[data-token-id="{target_id}"]').get_attribute("class") or "")
    page.wait_for_timeout(420)
    after = task_status(page)
    point_after = center(page.locator(f'[data-token-id="{target_id}"]')) if target_id else None
    in_gate_after = None if not target_id else "is-in-gate" in (page.locator(f'[data-token-id="{target_id}"]').get_attribute("class") or "")
    delta = float(after["task_time_ms"]) - float(before["task_time_ms"])
    motion = 0.0 if not target_id else ((point_after[0] - point_before[0]) ** 2 + (point_after[1] - point_before[1]) ** 2) ** .5
    if mode == "live" and delta < 320:
        raise AssertionError(f"live clock did not advance during model delay: {delta}")
    if mode == "paused" and abs(delta) > 2:
        raise AssertionError(f"paused clock advanced during model delay: {delta}")
    if target_id and mode == "live" and (motion < 35 or not in_gate_before or in_gate_after):
        raise AssertionError(f"live valid tag did not expire: motion={motion}, before={in_gate_before}, after={in_gate_after}")
    if target_id and mode == "paused" and (motion > 1 or not in_gate_before or not in_gate_after):
        raise AssertionError(f"paused valid tag was not frozen: motion={motion}, before={in_gate_before}, after={in_gate_after}")
    return {
        "task_time_delta_ms": round(delta, 3),
        "target_motion_px": round(motion, 3),
        "correct_tag_valid_before_delay": in_gate_before,
        "correct_tag_valid_after_delay": in_gate_after,
        "correct_action_expired": bool(target_id and mode == "live"),
        "correct_action_preserved": bool(target_id and mode == "paused"),
    }


def wrong_id(spec: dict, expected: str) -> str:
    return next(item["id"] for item in spec["tokens"] if item["id"] != expected)


def issue_failure(page, spec: dict, interaction: str) -> None:
    family = spec["family"]
    if family == "gate_tag":
        wrong = wrong_id(spec, spec["predicate"]["target_id"])
        page.locator(f'[data-{"token-id" if interaction == "full" else "proxy-tag"}="{wrong}"]').click(force=True)
    elif family == "relay_pair":
        wrong = wrong_id(spec, spec["predicate"]["first_id"])
        page.locator(f'[data-{"token-id" if interaction == "full" else "proxy-tap"}="{wrong}"]').click(force=True)
    elif family == "sync_hold":
        wrong = wrong_id(spec, spec["predicate"]["target_id"])
        node = page.locator(f'[data-{"token-id" if interaction == "full" else "proxy-hold"}="{wrong}"]')
        page.mouse.move(*center(node)); page.mouse.down(); page.mouse.up()
    elif family == "vector_flick":
        wrong = wrong_id(spec, spec["predicate"]["target_id"])
        if interaction == "simplified":
            page.locator(f'[data-proxy-select="{wrong}"]').click()
            page.locator('[data-proxy-direction="NORTH"]').click()
        else:
            x, y = center(page.locator(f'[data-token-id="{wrong}"]'))
            page.mouse.move(x, y); page.mouse.down(); page.mouse.move(x + 90, y); page.mouse.up()
    else:
        wrong = wrong_id(spec, spec["predicate"]["target_id"])
        bay_id = spec["predicate"]["bay_id"]
        if interaction == "simplified":
            page.locator(f'[data-proxy-select="{wrong}"]').click()
            page.locator(f'[data-proxy-bay="{bay_id}"]').click()
        else:
            page.mouse.move(*center(page.locator(f'[data-token-id="{wrong}"]'))); page.mouse.down()
            page.mouse.move(*center(page.locator(f'[data-bay-id="{bay_id}"]'))); page.mouse.up()


def failure_recovery(page, state_dir: Path, interaction: str, mode: str) -> dict:
    initial = read_json(state_dir / "ground_truth.json")
    before = initial["challenge_id"]
    issue_failure(page, initial["rounds"][0], interaction)
    if mode == "paused":
        advance_task(page, 180)
    deadline = time.monotonic() + 8
    refreshed = None
    while time.monotonic() < deadline:
        refreshed = read_json(state_dir / "ground_truth.json")
        if refreshed["challenge_id"] != before:
            break
        time.sleep(.04)
    if refreshed is None or refreshed["challenge_id"] == before:
        raise AssertionError("failed dispatch did not produce a fresh challenge")
    expect(page.locator(".five-second-rule[data-fresh-failure='true']")).to_be_visible(timeout=8_000)
    expect(page.locator(".fsr-verdict.is-fail")).to_be_visible(timeout=8_000)
    return {"initial_challenge_id": before, "fresh_challenge_id": refreshed["challenge_id"], "rotated": True}


def paused_solve(page, truth: dict, interaction: str) -> None:
    directions = {"NORTH": (0, -1), "EAST": (1, 0), "SOUTH": (0, 1), "WEST": (-1, 0)}
    for index, spec in enumerate(truth["rounds"]):
        wait_round(page, spec)
        started = float(task_status(page)["task_time_ms"])
        family = spec["family"]
        if family == "gate_tag":
            target_id = spec["predicate"]["target_id"]
            token = next(item for item in spec["tokens"] if item["id"] == target_id)
            crossing = (float(spec["gate"]["x"]) - float(token["motion"]["x0"])) / float(token["motion"]["vx"]) * 1000
            advance_task(page, max(0, started + crossing - float(task_status(page)["task_time_ms"])))
            if interaction == "simplified":
                page.locator(f'[data-proxy-tag="{target_id}"]').click()
            else:
                page.mouse.click(*center(page.locator(f'[data-token-id="{target_id}"]')))
        elif family == "sync_hold":
            target_id = spec["predicate"]["target_id"]
            advance_task(page, max(0, started + float(spec["cue"]["start_ms"]) - float(task_status(page)["task_time_ms"])))
            node = page.locator(f'[data-{"token-id" if interaction == "full" else "proxy-hold"}="{target_id}"]')
            page.mouse.move(*center(node)); page.mouse.down()
            advance_task(page, float(spec["cue"]["end_ms"]) - float(spec["cue"]["start_ms"]))
            page.mouse.up()
        elif family == "vector_flick":
            target_id = spec["predicate"]["target_id"]
            advance_task(page, max(0, started + 1720 - float(task_status(page)["task_time_ms"])))
            direction = spec["flick"]["flick_direction"]
            if interaction == "simplified":
                page.locator(f'[data-proxy-select="{target_id}"]').click()
                page.locator(f'[data-proxy-direction="{direction}"]').click()
            else:
                dx, dy = directions[direction]
                distance = float(spec["flick"]["min_travel_px"]) + 24
                x, y = center(page.locator(f'[data-token-id="{target_id}"]'))
                page.mouse.move(x, y); page.mouse.down(); page.mouse.move(x + dx * distance, y + dy * distance); page.mouse.up()
        elif family == "relay_pair":
            attribute = "token-id" if interaction == "full" else "proxy-tap"
            page.locator(f'[data-{attribute}="{spec["predicate"]["first_id"]}"]').click()
            page.locator(f'[data-{attribute}="{spec["predicate"]["second_id"]}"]').click()
        else:
            target_id = spec["predicate"]["target_id"]
            bay_id = spec["predicate"]["bay_id"]
            advance_task(page, max(0, started + 1580 - float(task_status(page)["task_time_ms"])))
            if interaction == "simplified":
                page.locator(f'[data-proxy-select="{target_id}"]').click()
                page.locator(f'[data-proxy-bay="{bay_id}"]').click()
            else:
                page.mouse.move(*center(page.locator(f'[data-token-id="{target_id}"]'))); page.mouse.down()
                page.mouse.move(*center(page.locator(f'[data-bay-id="{bay_id}"]')), steps=3); page.mouse.up()
        advance_task(page, 200)
        if page.locator(".fsr-verdict.is-fail").is_visible():
            raise AssertionError(
                f"paused {interaction} solve failed on {family}: "
                f"{page.locator('.readout').inner_text().strip()}"
            )
        if index < len(truth["rounds"]) - 1:
            expect(page.locator(f'.fsr-stage.family-{truth["rounds"][index + 1]["family"]}')).to_be_visible(timeout=5_000)
    expect(page.locator(".fsr-verdict.is-pass")).to_be_visible(timeout=8_000)


def surface_contract(page, phase: str, interaction: str) -> dict:
    root = page.locator(".five-second-rule")
    order = page.locator(".fsr-order h2")
    result = {
        "phase": phase,
        "two_instruction_lines": order.count() == 2 and all(item.strip() for item in order.all_inner_texts()),
        "visible_timer": page.locator(".fsr-timer strong").is_visible(),
        "current_round_only": page.locator(".fsr-stage").count() == 1,
        "interaction_class": f"mode-{interaction}" in (root.get_attribute("class") or "").split(),
        "viewport": VIEWPORT,
        "document_overflow": page.evaluate("() => ({x: document.documentElement.scrollWidth - innerWidth, y: document.documentElement.scrollHeight - innerHeight})"),
    }
    if not all((result["two_instruction_lines"], result["visible_timer"], result["current_round_only"], result["interaction_class"])):
        raise AssertionError(f"visible surface contract failed: {result}")
    return result


def capture_condition(playwright, temporary: Path, output: Path, level: int, interaction: str, mode: str) -> dict:
    label = f"d{level}-{interaction}-{mode}"
    state_dir = temporary / "states" / label
    state_dir.mkdir(parents=True)
    task = condition_task(temporary, level, interaction, mode)
    # The first browser /state request derives ``<base>:refresh:1``. The d4
    # base is retained as a moving-gate witness for the live/paused delay
    # contract under the generator's canonical parameter hash.
    seed = f"five-second-evidence-d{level}-0"
    process, port = start_server(task, state_dir, seed)
    profile = temporary / "fresh-profiles" / label
    screenshots = output / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    record_video = level == 4 and interaction == "full"
    context_options = {"headless": True, "viewport": VIEWPORT, "device_scale_factor": 1}
    if record_video:
        context_options.update({"record_video_dir": str(temporary / "raw-videos" / label), "record_video_size": VIEWPORT})
    context = playwright.chromium.launch_persistent_context(str(profile), **context_options)
    page = context.pages[0]
    video = page.video if record_video else None
    errors: list[str] = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    solver = load_module(SOLVER, f"five_second_solver_{label.replace('-', '_')}")
    record = None
    try:
        page.goto(f"http://127.0.0.1:{port}/?time_mode={mode}&start_paused=1", wait_until="networkidle")
        expect(page.locator(".five-second-rule")).to_be_visible(timeout=8_000)
        initial_state = read_json(state_dir / "public_state.json")
        initial_truth = read_json(state_dir / "ground_truth.json")
        checks = [surface_contract(page, "initial", interaction)]
        page.screenshot(path=str(screenshots / f"{label}-initial.png"))

        observation = None
        target_id = None
        if level == 4 and interaction == "full":
            if initial_truth["rounds"][0]["family"] != "gate_tag":
                raise AssertionError("baseline evidence seed must expose gate first")
            observation = capture_gate_observation(page, output, mode, initial_truth["rounds"][0])
            target_id = observation["target_id"]
        delay = delay_contract(page, mode, target_id)

        failure = failure_recovery(page, state_dir, interaction, mode)
        checks.append(surface_contract(page, "failure-fresh", interaction))
        page.screenshot(path=str(screenshots / f"{label}-failure-fresh.png"))
        retry_truth = read_json(state_dir / "ground_truth.json")
        if mode == "live":
            solver.solve(page, state_dir, output, MECHANIC)
        else:
            paused_solve(page, retry_truth, interaction)
        checks.append(surface_contract(page, "pass", interaction))
        page.screenshot(path=str(screenshots / f"{label}-pass.png"))

        exported, export_command = export_result(state_dir, output, label)
        export_path = output / export_command["artifact"]
        direct = load_module(GRADER, f"five_second_grader_{label.replace('-', '_')}").grade(
            exported["result"], exported["ground_truth"], exported["public_state"],
        )
        verifier = verify_export(export_path, label)
        server_grade = exported["result"].get("server_grade") or {}
        if not all(item.get("passed") is True for item in (server_grade, direct, verifier)):
            raise AssertionError(f"grade mismatch server={server_grade} direct={direct} verifier={verifier}")
        if errors:
            raise AssertionError(f"browser errors: {errors}")
        record = {
            "label": label,
            "difficulty": level,
            "interaction": interaction,
            "time_mode": mode,
            "headless": True,
            "fresh_profile": str(profile.relative_to(temporary)),
            "loopback_origin": f"http://127.0.0.1:{port}",
            "world_fingerprint": initial_state["world_fingerprint"],
            "initial_round_order": [item["family"] for item in initial_state["rounds"]],
            "difficulty_parameters": initial_state["parameters"],
            "model_observation": observation,
            "artificial_model_delay": delay,
            "failure_retry": failure,
            "visible_surface_checks": checks,
            "server_grade": server_grade,
            "direct_grade": direct,
            "verifier": verifier,
            "export": export_command,
            "browser_errors": errors,
        }
    finally:
        context.close()
        stop_server(process)
    if record is None:
        raise AssertionError(f"condition {label} produced no record")
    if video is not None:
        destination = output / "recordings" / f"baseline-full-{mode}.webm"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(video.path(), destination)
        record["recording"] = {
            "path": str(destination.relative_to(output)),
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "bytes": destination.stat().st_size,
        }
    write_json(output / "matrix" / f"{label}.json", record)
    return record


def negative_contract(output: Path) -> dict:
    exported = read_json(output / "exports/d4-full-live.json")
    payload = exported["result"]
    truth = exported["ground_truth"]
    public = exported["public_state"]
    grader = load_module(GRADER, "five_second_negative_evidence")
    cases = {}

    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "fsr-stale-evidence"
    cases["stale_challenge"] = grader.grade(stale, truth, public)

    wrong_surface = copy.deepcopy(payload)
    wrong_surface["rounds"][0]["events"][0]["input_source"] = "proxy_tag"
    cases["wrong_interaction_surface"] = grader.grade(wrong_surface, truth, public)

    late = copy.deepcopy(payload)
    timed = next(record for record in late["rounds"] if record["family"] in {"gate_tag", "vector_flick", "shutter_drop"})
    timed["events"][0]["t_ms"] = 5001
    cases["expired_action"] = grader.grade(late, truth, public)

    forged = copy.deepcopy(payload)
    forged["world_fingerprint"] = "0" * 64
    cases["forged_world"] = grader.grade(forged, truth, public)

    incomplete = copy.deepcopy(payload)
    incomplete["rounds"] = incomplete["rounds"][:-1]
    cases["incomplete_deck"] = grader.grade(incomplete, truth, public)

    result = {"all_rejected": all(item.get("passed") is False for item in cases.values()), "cases": cases}
    write_json(output / "negative_contract.json", result)
    return result


def capture_with_timeout_retry(playwright, temporary: Path, output: Path, level: int, interaction: str, mode: str) -> dict:
    errors = []
    for attempt in (1, 2):
        try:
            record = capture_condition(
                playwright,
                temporary / f"browser-attempt-{attempt}",
                output,
                level,
                interaction,
                mode,
            )
            record["capture_attempt"] = attempt
            record["prior_timeout_errors"] = errors
            write_json(output / "matrix" / f"d{level}-{interaction}-{mode}.json", record)
            return record
        except PlaywrightTimeoutError as exc:
            errors.append(str(exc).splitlines()[0])
            if attempt == 2:
                raise
    raise AssertionError("unreachable capture retry state")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="five-second-rule-isolated-") as temporary_text:
        temporary = Path(temporary_text)
        matrix = []
        with sync_playwright() as playwright:
            for level in range(1, 6):
                for interaction in ("simplified", "full"):
                    for mode in ("live", "paused"):
                        print(f"capturing d{level}-{interaction}-{mode}", flush=True)
                        matrix.append(capture_with_timeout_retry(playwright, temporary, output, level, interaction, mode))

    grouped: dict[tuple[int, str], list[dict]] = {}
    for item in matrix:
        grouped.setdefault((item["difficulty"], item["interaction"]), []).append(item)
    pairs = {}
    for key, pair in grouped.items():
        same = len(pair) == 2 and pair[0]["world_fingerprint"] == pair[1]["world_fingerprint"]
        pairs[f"d{key[0]}-{key[1]}"] = {"same_world": same, "fingerprints": [item["world_fingerprint"] for item in pair]}
        if not same:
            raise AssertionError(f"live/paused world mismatch for {key}: {pair}")
    for level in range(1, 6):
        worlds = {item["world_fingerprint"] for item in matrix if item["difficulty"] == level}
        if len(worlds) != 1:
            raise AssertionError(f"interaction or schedule changed the d{level} world: {worlds}")
    negative = negative_contract(output)
    summary = {
        "environment": "Five-Second Rule",
        "mechanic_id": MECHANIC,
        "ok": len(matrix) == 20 and all(item["server_grade"]["passed"] and item["direct_grade"]["passed"] and item["verifier"]["passed"] for item in matrix) and negative["all_rejected"],
        "browser_isolation": {"headless": True, "fresh_persistent_profile_per_condition": True, "loopback_only": True, "existing_profile_used": False, "foreground_browser_used": False},
        "conditions_checked": len(matrix),
        "all_twenty_passed": len(matrix) == 20,
        "all_failure_recovery_passed": all(item["failure_retry"]["rotated"] for item in matrix),
        "live_paused_same_world": all(item["same_world"] for item in pairs.values()),
        "same_world_pairs": pairs,
        "negative_contract": negative,
        "records": matrix,
    }
    write_json(output / "validation_summary.json", summary)
    print(json.dumps({"ok": summary["ok"], "conditions_checked": len(matrix), "evidence": str(output)}, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
