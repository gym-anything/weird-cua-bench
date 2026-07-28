#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
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
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "slot_reel_capture_env"
APP_DIR = BENCHMARK / "shared_runtime" / "app"
SETUP_PATH = BENCHMARK / "shared_scripts" / "setup_task.py"
SERVER = BENCHMARK / "shared_runtime" / "server" / "weird_captcha_server.py"
MATERIALIZER_PATH = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
EXPORT = BENCHMARK / "shared_scripts" / "export_result.sh"
VERIFIER_PATH = BENCHMARK / "shared_runtime" / "verifier_helpers.py"
LEGACY_GRADER_PATH = (
    BENCHMARK / "shared_runtime" / "server" / "legacy_browser_grader.py"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Capture Slot-Reel Character Capture generation, live/paused, "
            "grading, export, and verifier evidence."
        )
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


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluation_viewport() -> dict[str, int]:
    observations = read_json(ENVIRONMENT / "env.json")["observation"]
    resolution = observations[0]["resolution"]
    return {"width": int(resolution[0]), "height": int(resolution[1])}


EVALUATION_VIEWPORT = evaluation_viewport()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def world_fingerprint(public_state: dict, ground_truth: dict) -> str:
    public = copy.deepcopy(public_state)
    truth = copy.deepcopy(ground_truth)
    for value in (public, truth):
        value.pop("task_id", None)
        value.pop("challenge_id", None)
        value.pop("control_condition", None)
        value.pop("slot_reel_interaction_public_key", None)
    public.pop("prompt", None)
    payload = json.dumps(
        {"public_state": public, "ground_truth": truth},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(payload)


def normalized_baseline_state(public_state: dict, ground_truth: dict) -> dict:
    public = copy.deepcopy(public_state)
    truth = copy.deepcopy(ground_truth)
    for value in (public, truth):
        value.pop("task_id", None)
        value.pop("control_condition", None)
    return {"public_state": public, "ground_truth": truth}


def tree_manifest(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): sha256_bytes(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def controlled_task(tasks_root: Path, difficulty: int, interaction: str) -> Path:
    matches = []
    for path in tasks_root.glob("*/task.json"):
        condition = (read_json(path).get("metadata") or {}).get(
            "control_condition"
        ) or {}
        if (
            int(condition.get("difficulty") or 0) == difficulty
            and condition.get("interaction") == interaction
        ):
            matches.append(path)
    if len(matches) != 1:
        raise AssertionError(
            f"expected one d{difficulty} {interaction} task, found {matches}"
        )
    return matches[0]


def reserve_port() -> int:
    with socket.socket() as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def start_server(
    task_json: Path,
    state_dir: Path,
    seed: str,
    *,
    retain_current_task: bool,
) -> tuple[subprocess.Popen, int]:
    state_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "python",
            "-B",
            str(SETUP_PATH),
            "--task-json",
            str(task_json),
            "--state-dir",
            str(state_dir),
            "--seed",
            seed,
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    if not retain_current_task:
        (state_dir / "current_task.json").unlink()
    port = reserve_port()
    process = subprocess.Popen(
        [
            "python",
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
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/health",
                timeout=0.5,
            ).read()
            return process, port
        except Exception:
            time.sleep(0.1)
    process.kill()
    raise RuntimeError("Slot-Reel evidence server did not start")


def stop_server(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()


def export_and_verify(
    state_dir: Path,
    artifact_path: Path,
    verifier,
) -> tuple[str, dict]:
    environment = os.environ.copy()
    environment["WEIRD_CAPTCHA_STATE_DIR"] = str(state_dir)
    command = subprocess.run(
        ["bash", str(EXPORT)],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    shutil.copy2("/tmp/task_result.json", artifact_path)
    verification = verifier.verify_slot_reel_capture(read_json(artifact_path))
    if verification.get("passed") is not True or verification.get("score") != 100:
        raise AssertionError(f"export verifier rejected result: {verification}")
    return command.stdout.strip(), verification


def wait_for_target(page, reel_id: str, target: str) -> None:
    page.wait_for_function(
        """({reelId, target}) => {
          const reel = document.querySelector(
            `.slot-reel[data-reel-id="${CSS.escape(reelId)}"]`
          );
          if (!reel) return false;
          const data = slotModel.state.reels.find((item) => item.id === reelId);
          if (!data) return false;
          const symbol = reel.querySelector(".slot-symbol")?.textContent || "";
          const elapsed = performance.now() - slotModel.startedAt;
          const actualIndex = (
            Math.floor(elapsed / data.interval_ms) + Number(data.phase || 0)
          ) % data.tokens.length;
          const position = (elapsed % data.interval_ms) / data.interval_ms;
          const remaining = data.interval_ms - (elapsed % data.interval_ms);
          const ratio = Number(slotModel.state.capture_window_ratio || 1);
          const safelyTimed = ratio < 1
            ? Math.abs(position - 0.5) < ratio * 0.12
            : remaining > Math.max(160, data.interval_ms * 0.70);
          return reel.dataset.active === "true"
            && reel.dataset.captureReady !== "false"
            && Number(reel.dataset.tokenIndex) === actualIndex
            && safelyTimed
            && symbol === target
            && data.tokens[actualIndex] === target;
        }""",
        arg={"reelId": reel_id, "target": target},
        timeout=15_000,
        polling=8,
    )


def apply_capture(
    page,
    interaction: str,
    time_mode: str,
    target: str,
    frozen_count: int,
) -> dict:
    timing: dict[str, float] = {}
    if time_mode == "paused":
        before = page.evaluate("WeirdCaptchaTime.status()")
        page.evaluate("WeirdCaptchaTime.resume()")
        page.wait_for_timeout(16)
    if interaction == "simplified":
        page.locator("#capture-slot").click(force=True)
    else:
        page.keyboard.press(target)
    if time_mode == "paused":
        page.wait_for_timeout(16)
        page.evaluate("WeirdCaptchaTime.pause()")
        after = page.evaluate("WeirdCaptchaTime.status()")
        timing = {
            "before_task_time_ms": float(before["task_time_ms"]),
            "after_task_time_ms": float(after["task_time_ms"]),
            "task_time_delta_ms": round(
                float(after["task_time_ms"]) - float(before["task_time_ms"]),
                3,
            ),
        }
    try:
        expect(page.locator('.slot-reel[data-frozen="true"]')).to_have_count(
            frozen_count,
            timeout=2000,
        )
    except AssertionError as error:
        diagnostic = page.evaluate(
            """() => ({
              actions: slotModel.actions,
              frozen: slotModel.frozen,
              wrongKeys: slotModel.wrongKeys,
              clock: WeirdCaptchaTime.status(),
              elapsedMs: performance.now() - slotModel.startedAt,
              readout: document.querySelector(".readout")?.textContent || "",
            })"""
        )
        raise AssertionError(
            f"slot capture did not freeze reel {frozen_count}: "
            f"{json.dumps(diagnostic, sort_keys=True)}"
        ) from error
    return timing


def solve_condition(
    page,
    truth: dict,
    interaction: str,
    time_mode: str,
    evidence_dir: Path,
) -> dict:
    first_action_timing: dict[str, float] = {}
    for index, (reel_id, target) in enumerate(
        zip(truth["reel_ids"], truth["sequence"]),
        start=1,
    ):
        if time_mode == "paused":
            page.evaluate("WeirdCaptchaTime.resume()")
        wait_for_target(page, str(reel_id), str(target))
        if time_mode == "paused":
            page.evaluate("WeirdCaptchaTime.pause()")
            page.wait_for_timeout(80)
        timing = apply_capture(
            page,
            interaction,
            time_mode,
            str(target),
            index,
        )
        if index == 1:
            first_action_timing = timing
    if page.evaluate("slotModel.captured") != truth["sequence"]:
        raise AssertionError("visible solve did not capture the generated sequence")
    if int(page.evaluate("slotModel.wrongKeys")) != 0:
        raise AssertionError("passing solve contains a strike")
    page.screenshot(path=str(evidence_dir / "solved-pre-submit.png"))
    if time_mode == "paused":
        page.evaluate("WeirdCaptchaTime.resume()")
    page.locator("#submit-slot").click()
    expect(page.locator(".readout")).to_have_attribute(
        "data-status",
        "passed",
        timeout=8000,
    )
    if time_mode == "paused":
        page.evaluate("WeirdCaptchaTime.pause()")
    return first_action_timing


def run_matrix_condition(
    browser,
    task_json: Path,
    difficulty: int,
    interaction: str,
    time_mode: str,
    temporary: Path,
    matrix_root: Path,
    verifier,
) -> dict:
    name = f"d{difficulty}-{interaction}-{time_mode}"
    state_dir = temporary / "matrix-state" / name
    evidence_dir = matrix_root / name
    evidence_dir.mkdir(parents=True, exist_ok=True)
    process, port = start_server(
        task_json,
        state_dir,
        f"slot-reel-complete-matrix-d{difficulty}-shared-seed",
        retain_current_task=False,
    )
    errors: list[str] = []
    page = browser.new_page(
        viewport=EVALUATION_VIEWPORT,
        device_scale_factor=1,
    )
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(
            (
                f"http://127.0.0.1:{port}/?time_mode={time_mode}"
                f"&start_paused={'1' if time_mode == 'paused' else '0'}"
            ),
            wait_until="networkidle",
        )
        page.wait_for_function("WeirdCaptchaTime.status().ready === true")
        expect(page.locator(".slot-captcha")).to_have_attribute(
            "data-interaction",
            interaction,
        )
        if time_mode == "paused":
            page.evaluate("WeirdCaptchaTime.pause()")
            page.wait_for_function(
                "WeirdCaptchaTime.status().state === 'paused'"
            )
        else:
            page.evaluate("WeirdCaptchaTime.resume()")
            page.wait_for_function(
                "WeirdCaptchaTime.status().state === 'running'"
            )

        public = read_json(state_dir / "public_state.json")
        truth = read_json(state_dir / "ground_truth.json")
        page.screenshot(path=str(evidence_dir / "initial.png"))
        capture_window_ratio = float(
            public.get("capture_window_ratio", 1.0)
        )
        cue_geometry = page.locator(".slot-window").first.evaluate(
            """(node) => {
              const before = getComputedStyle(node, "::before");
              const after = getComputedStyle(node, "::after");
              return {
                windowed: node.dataset.windowed === "true",
                client_height_px: node.clientHeight,
                upper_line_top_px: Number.parseFloat(before.top),
                lower_line_top_px: Number.parseFloat(after.top),
              };
            }"""
        )
        if capture_window_ratio < 1:
            expected_half_span = capture_window_ratio * 46
            actual_half_span = (
                float(cue_geometry["lower_line_top_px"])
                - float(cue_geometry["upper_line_top_px"])
            ) / 2
            cue_geometry.update(
                {
                    "graded_capture_window_ratio": (
                        capture_window_ratio
                    ),
                    "expected_half_span_px": expected_half_span,
                    "actual_half_span_px": actual_half_span,
                    "matches_graded_window": (
                        abs(actual_half_span - expected_half_span) < 0.2
                    ),
                }
            )
            if cue_geometry["matches_graded_window"] is not True:
                raise AssertionError(
                    f"{name} cue does not match graded window: "
                    f"{cue_geometry}"
                )

        inference_before = page.evaluate("WeirdCaptchaTime.status()")
        page.wait_for_timeout(250)
        inference_after = page.evaluate("WeirdCaptchaTime.status()")
        inference_delta = round(
            float(inference_after["task_time_ms"])
            - float(inference_before["task_time_ms"]),
            3,
        )
        if time_mode == "paused" and inference_delta > 2:
            raise AssertionError(
                f"{name} advanced during paused inference: {inference_delta}"
            )
        if time_mode == "live" and inference_delta < 180:
            raise AssertionError(
                f"{name} did not advance during live inference: {inference_delta}"
            )

        action_timing = solve_condition(
            page,
            truth,
            interaction,
            time_mode,
            evidence_dir,
        )
        if (
            time_mode == "paused"
            and action_timing.get("task_time_delta_ms", 0) <= 10
        ):
            raise AssertionError(
                f"{name} action did not run under the resumed clock: "
                f"{action_timing}"
            )
        page.screenshot(path=str(evidence_dir / "pass.png"))
        result = read_json(state_dir / "result.json")
        server_grade = result.get("server_grade") or {}
        if server_grade.get("passed") is not True:
            raise AssertionError(f"server rejected {name}: {server_grade}")

        artifact_path = evidence_dir / "task_result.json"
        export_stdout, verification = export_and_verify(
            state_dir,
            artifact_path,
            verifier,
        )
        if errors:
            raise AssertionError(f"browser errors in {name}: {errors}")
        sources = sorted(
            {
                str(action.get("input_source"))
                for action in result.get("actions") or []
                if action.get("input_source")
            }
        )
        action_times = [
            action.get("elapsed_ms")
            for action in result.get("actions") or []
        ]
        if (
            not action_times
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                for value in action_times
            )
        ):
            raise AssertionError(f"{name} omitted action timing evidence")
        return {
            "difficulty": difficulty,
            "interaction": interaction,
            "time_mode": time_mode,
            "passed": True,
            "challenge_id": truth["challenge_id"],
            "world_fingerprint": world_fingerprint(public, truth),
            "inference_delay": {
                "wall_delay_ms": 250,
                "task_time_delta_ms": inference_delta,
            },
            "first_action_timing": action_timing,
            "capture_cue_geometry": cue_geometry,
            "input_sources": sources,
            "action_elapsed_ms": action_times,
            "viewport": [
                EVALUATION_VIEWPORT["width"],
                EVALUATION_VIEWPORT["height"],
            ],
            "server_grade": server_grade,
            "export": {
                "artifact": str(artifact_path.relative_to(matrix_root)),
                "command_stdout": export_stdout,
            },
            "verification": verification,
            "browser_errors": errors,
            "screenshots": {
                "initial": str(
                    (evidence_dir / "initial.png").relative_to(matrix_root)
                ),
                "solved_pre_submit": str(
                    (evidence_dir / "solved-pre-submit.png").relative_to(
                        matrix_root
                    )
                ),
                "pass": str(
                    (evidence_dir / "pass.png").relative_to(matrix_root)
                ),
            },
        }
    finally:
        page.close()
        stop_server(process)


def capture_generation_evidence(
    output: Path,
    temporary: Path,
    materializer,
    setup,
) -> tuple[Path, dict]:
    first = temporary / "materialized-first"
    second = temporary / "materialized-second"
    materializer.materialize_environment(ENVIRONMENT, first)
    materializer.materialize_environment(ENVIRONMENT, second)
    first_root = first / ENVIRONMENT.name / "tasks"
    second_root = second / ENVIRONMENT.name / "tasks"
    first_manifest = tree_manifest(first / ENVIRONMENT.name)
    second_manifest = tree_manifest(second / ENVIRONMENT.name)
    if first_manifest != second_manifest:
        raise AssertionError("controlled materialization is not deterministic")

    controls = read_json(ENVIRONMENT / "controls.json")
    original_task = read_json(
        ENVIRONMENT
        / "tasks"
        / "slot_reel_capture_seed_0001"
        / "task.json"
    )
    baseline_task = read_json(controlled_task(first_root, 4, "full"))
    baseline_checks = []
    for seed in (
        "slot-baseline-preservation-a",
        "slot-baseline-preservation-b",
        "slot-baseline-preservation-c",
    ):
        original_public, original_truth = setup.generate_task_state(
            original_task,
            seed,
        )
        controlled_public, controlled_truth = setup.generate_task_state(
            baseline_task,
            seed,
        )
        original_token_counts = [
            len(reel["tokens"]) for reel in original_public["reels"]
        ]
        controlled_token_counts = [
            len(reel["tokens"]) for reel in controlled_public["reels"]
        ]
        if original_token_counts != [7] * 5:
            raise AssertionError(
                f"original Slot Reel configuration is not five seven-token reels: "
                f"{original_token_counts}"
            )
        preserved = normalized_baseline_state(
            original_public,
            original_truth,
        ) == normalized_baseline_state(
            controlled_public,
            controlled_truth,
        )
        if not preserved:
            raise AssertionError(f"L4 full changed the original world for {seed}")
        baseline_checks.append(
            {
                "seed": seed,
                "preserved_exactly_after_task_and_control_identity": True,
                "same_challenge_id": (
                    original_truth["challenge_id"]
                    == controlled_truth["challenge_id"]
                ),
                "challenge_id": original_truth["challenge_id"],
                "original_token_counts": original_token_counts,
                "controlled_token_counts": controlled_token_counts,
                "world_fingerprint": world_fingerprint(
                    original_public,
                    original_truth,
                ),
            }
        )

    interaction_pairs = {}
    profile_records = {}
    for difficulty in range(1, 6):
        generated = {}
        for interaction in ("simplified", "full"):
            task = read_json(controlled_task(first_root, difficulty, interaction))
            public, truth = setup.generate_task_state(
                task,
                f"slot-generation-matrix-d{difficulty}",
            )
            condition = truth.get("control_condition") or {}
            expected_parameters = controls["difficulty"][str(difficulty)][
                "parameters"
            ]
            if condition.get("difficulty_parameters") != expected_parameters:
                raise AssertionError(
                    f"d{difficulty} parameters differ from controls.json"
                )
            if public.get("control_condition") != condition:
                raise AssertionError(
                    f"d{difficulty} {interaction} public/truth condition mismatch"
                )
            generated[interaction] = {
                "challenge_id": truth["challenge_id"],
                "world_fingerprint": world_fingerprint(public, truth),
                "condition": condition,
                "reel_count": len(public["reels"]),
                "token_counts": [len(reel["tokens"]) for reel in public["reels"]],
                "interval_ms": [reel["interval_ms"] for reel in public["reels"]],
                "max_strikes": truth["max_strikes"],
                "capture_window_ratio": truth.get(
                    "capture_window_ratio",
                    1.0,
                ),
            }
        same_world = (
            generated["simplified"]["world_fingerprint"]
            == generated["full"]["world_fingerprint"]
        )
        same_challenge = (
            generated["simplified"]["challenge_id"]
            == generated["full"]["challenge_id"]
        )
        if not same_world or not same_challenge:
            raise AssertionError(
                f"d{difficulty} interaction pair changed the generated world"
            )
        interaction_pairs[str(difficulty)] = {
            "same_world": same_world,
            "same_challenge_id": same_challenge,
            "world_fingerprint": generated["full"]["world_fingerprint"],
            "challenge_id": generated["full"]["challenge_id"],
        }
        profile_records[str(difficulty)] = generated

    evidence = {
        "environment": ENVIRONMENT.name,
        "task_condition_count": len(list(first_root.glob("*/task.json"))),
        "deterministic_materialization": {
            "same_file_manifest": True,
            "file_count": len(first_manifest),
            "manifest_sha256": sha256_bytes(
                json.dumps(first_manifest, sort_keys=True).encode("utf-8")
            ),
        },
        "baseline": {
            "difficulty": 4,
            "interaction": "full",
            "original_task_difficulty": original_task["difficulty"],
            "seeds": baseline_checks,
        },
        "interaction_pairs": interaction_pairs,
        "profiles": profile_records,
        "controls_sha256": sha256_bytes(
            (ENVIRONMENT / "controls.json").read_bytes()
        ),
    }
    write_json(output / "generation_matrix.json", evidence)
    return first_root, evidence


def passing_actions(public: dict, truth: dict, interaction: str) -> list[dict]:
    source = {
        "simplified": "capture_button",
        "full": "physical_keyboard",
    }[interaction]
    reels_by_id = {
        str(reel["id"]): reel for reel in public["reels"]
    }
    minimum_elapsed = 0.0
    actions = []
    for sequence, (reel_id, token) in enumerate(
        zip(truth["reel_ids"], truth["sequence"]),
        start=1,
    ):
        reel = reels_by_id[str(reel_id)]
        token_index = reel["tokens"].index(token)
        cycle = (
            token_index - int(reel["phase"])
        ) % len(reel["tokens"])
        elapsed_ms = (cycle + 0.5) * int(reel["interval_ms"])
        while elapsed_ms < minimum_elapsed:
            cycle += len(reel["tokens"])
            elapsed_ms = (cycle + 0.5) * int(reel["interval_ms"])
        minimum_elapsed = elapsed_ms
        actions.append({
            "sequence": sequence,
            "reel_id": reel_id,
            "elapsed_ms": elapsed_ms,
            "observed_token": token,
            "entered_key": token if interaction == "full" else None,
            "accepted": True,
            "input_source": source,
        })
    return actions


def decoy_elapsed_ms(public: dict, truth: dict) -> float:
    first_reel_id = str(truth["reel_ids"][0])
    reel = next(
        reel
        for reel in public["reels"]
        if str(reel["id"]) == first_reel_id
    )
    target = truth["sequence"][0]
    decoy_index = next(
        index
        for index, token in enumerate(reel["tokens"])
        if token != target
    )
    cycle = (
        decoy_index - int(reel["phase"])
    ) % len(reel["tokens"])
    return (cycle + 0.5) * int(reel["interval_ms"])


def passing_payload(public: dict, truth: dict, interaction: str) -> dict:
    actions = passing_actions(public, truth, interaction)
    return {
        "mechanic_id": "slot_reel_capture",
        "challenge_id": truth["challenge_id"],
        "captured_sequence": truth["sequence"],
        "frozen_reel_ids": truth["reel_ids"],
        "wrong_keys": 0,
        "actions": actions,
    }


def post_result(port: int, payload: dict) -> dict:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/result",
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    return json.loads(urllib.request.urlopen(request, timeout=8).read())


def server_negative_case(
    task_json: Path,
    temporary: Path,
    case: str,
) -> dict:
    state_dir = temporary / "negative-state" / case
    process, port = start_server(
        task_json,
        state_dir,
        f"slot-negative-{case}",
        retain_current_task=True,
    )
    try:
        public = read_json(state_dir / "public_state.json")
        truth = read_json(state_dir / "ground_truth.json")
        before_challenge = truth["challenge_id"]
        payload = passing_payload(public, truth, "full")
        if case == "stale_challenge":
            payload["challenge_id"] = "stale-slot-challenge"
        elif case == "wrong_interaction_source":
            for action in payload["actions"]:
                action["input_source"] = "capture_button"
                action["entered_key"] = None
        elif case == "invalid_action_sequence":
            payload["actions"][0]["sequence"] = 9
        elif case == "mismatched_typed_symbol":
            token = payload["actions"][0]["entered_key"]
            payload["actions"][0]["entered_key"] = (
                "A" if token != "A" else "B"
            )
        elif case == "missing_timing_evidence":
            payload["actions"][0].pop("elapsed_ms")
        elif case == "fabricated_timing_claim":
            payload["actions"][0]["elapsed_ms"] = decoy_elapsed_ms(
                public,
                truth,
            )
        else:
            raise AssertionError(f"unknown negative case {case}")
        response = post_result(port, payload)
        attempts = [
            json.loads(line)
            for line in (state_dir / "attempts.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        archived = attempts[-1]
        after_challenge = read_json(state_dir / "public_state.json")[
            "challenge_id"
        ]
        if response.get("passed") is not False:
            raise AssertionError(f"server accepted {case}: {response}")
        if (archived.get("server_grade") or {}).get("passed") is not False:
            raise AssertionError(f"server did not archive rejection for {case}")
        if after_challenge == before_challenge:
            raise AssertionError(f"server did not regenerate after {case}")
        return {
            "case": case,
            "rejected": True,
            "server_response": response,
            "server_grade": archived["server_grade"],
            "before_challenge_id": before_challenge,
            "after_challenge_id": after_challenge,
            "fresh_challenge_after_failure": True,
        }
    finally:
        stop_server(process)


def capture_negative_evidence(
    output: Path,
    temporary: Path,
    tasks_root: Path,
    verifier,
    legacy_grader,
) -> dict:
    full_task = controlled_task(tasks_root, 4, "full")
    server_cases = [
        server_negative_case(full_task, temporary, case)
        for case in (
            "stale_challenge",
            "wrong_interaction_source",
            "invalid_action_sequence",
            "mismatched_typed_symbol",
            "missing_timing_evidence",
            "fabricated_timing_claim",
        )
    ]

    passing_export = read_json(
        output
        / "realtime_matrix"
        / "d4-full-live"
        / "task_result.json"
    )
    public = passing_export["public_state"]
    truth = passing_export["ground_truth"]
    result = passing_export["result"]
    mutations = {}
    for case in (
        "stale_challenge",
        "wrong_interaction_source",
        "invalid_action_sequence",
        "mismatched_typed_symbol",
        "missing_timing_evidence",
        "fabricated_timing_claim",
        "public_condition_mismatch",
    ):
        exported = {
            "public_state": copy.deepcopy(public),
            "ground_truth": copy.deepcopy(truth),
            "result": copy.deepcopy(result),
        }
        if case == "stale_challenge":
            exported["result"]["challenge_id"] = "stale-slot-challenge"
        elif case == "wrong_interaction_source":
            for action in exported["result"]["trusted_witness"]["actions"]:
                action["input_source"] = "capture_button"
                action["entered_key"] = None
        elif case == "invalid_action_sequence":
            exported["result"]["trusted_witness"]["actions"][0][
                "sequence"
            ] = 9
        elif case == "mismatched_typed_symbol":
            token = exported["result"]["trusted_witness"]["actions"][0][
                "entered_key"
            ]
            exported["result"]["trusted_witness"]["actions"][0][
                "entered_key"
            ] = (
                "A" if token != "A" else "B"
            )
        elif case == "missing_timing_evidence":
            exported["result"].pop("trusted_witness")
        elif case == "fabricated_timing_claim":
            exported["result"]["trusted_witness"]["actions"][0][
                "elapsed_ms"
            ] = (
                decoy_elapsed_ms(
                    exported["public_state"],
                    exported["ground_truth"],
                )
            )
        elif case == "public_condition_mismatch":
            exported["public_state"]["control_condition"]["interaction"] = (
                "simplified"
            )
        verification = verifier.verify_slot_reel_capture(exported)
        direct_grade = legacy_grader.grade(
            exported["result"],
            exported["ground_truth"],
            exported["public_state"],
        )
        if verification.get("passed") is not False:
            raise AssertionError(f"verifier accepted {case}: {verification}")
        if direct_grade.get("passed") is not False:
            raise AssertionError(f"legacy grader accepted {case}: {direct_grade}")
        mutations[case] = {
            "verifier": verification,
            "legacy_browser_grader": direct_grade,
        }

    malformed_state = temporary / "negative-state" / "malformed_json"
    malformed_process, malformed_port = start_server(
        full_task,
        malformed_state,
        "slot-negative-malformed-json",
        retain_current_task=True,
    )
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{malformed_port}/result",
            data=b"{",
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=8)
            raise AssertionError("server accepted malformed JSON")
        except urllib.error.HTTPError as error:
            malformed = {
                "status": error.code,
                "body": json.loads(error.read()),
                "rejected": error.code == 400,
            }
    finally:
        stop_server(malformed_process)
    if malformed["rejected"] is not True:
        raise AssertionError(f"malformed request was not rejected: {malformed}")

    evidence = {
        "environment": ENVIRONMENT.name,
        "live_server_cases": server_cases,
        "independent_replay_cases": mutations,
        "malformed_json": malformed,
    }
    write_json(output / "negative_grading.json", evidence)
    return evidence


def capture_rapid_keyboard_failure(
    output: Path,
    temporary: Path,
    tasks_root: Path,
) -> dict:
    task_json = controlled_task(tasks_root, 4, "full")
    state_dir = temporary / "rapid-keyboard-state"
    process, port = start_server(
        task_json,
        state_dir,
        "slot-rapid-keyboard-failure",
        retain_current_task=True,
    )
    errors: list[str] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(
                viewport=EVALUATION_VIEWPORT,
                device_scale_factor=1,
            )
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(
                f"http://127.0.0.1:{port}/?time_mode=live&start_paused=0",
                wait_until="networkidle",
            )
            before_challenge = str(
                page.locator(".slot-captcha").get_attribute(
                    "data-challenge-id"
                )
            )
            max_strikes = int(
                read_json(state_dir / "ground_truth.json")["max_strikes"]
            )
            for _ in range(max_strikes):
                page.keyboard.press("1")
            page.wait_for_function(
                """before => {
                  const panel = document.querySelector(".slot-captcha");
                  return panel && panel.dataset.challengeId !== before;
                }""",
                arg=before_challenge,
                timeout=8_000,
            )
            after_challenge = str(
                page.locator(".slot-captcha").get_attribute(
                    "data-challenge-id"
                )
            )
            page.screenshot(
                path=str(output / "rapid-keyboard-failure-recovery.png")
            )
            browser.close()
    finally:
        stop_server(process)
    if errors:
        raise AssertionError(
            f"rapid keyboard failure produced browser errors: {errors}"
        )
    attempts = [
        json.loads(line)
        for line in (state_dir / "attempts.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    if not attempts:
        raise AssertionError("rapid keyboard failure was not archived")
    failed = attempts[-1]
    actions = (failed.get("trusted_witness") or {}).get("actions") or []
    if (
        len(actions) != max_strikes
        or any(action.get("entered_key") != "1" for action in actions)
        or any(
            action.get("input_source") != "physical_keyboard"
            for action in actions
        )
    ):
        raise AssertionError(
            f"rapid keyboard events were dropped or changed: {actions}"
        )
    evidence = {
        "ok": True,
        "interaction": "full",
        "keys_dispatched_without_response_waits": max_strikes,
        "server_witness_actions": len(actions),
        "all_keys_preserved_in_order": [
            action["entered_key"] for action in actions
        ] == ["1"] * max_strikes,
        "input_sources": sorted(
            {str(action["input_source"]) for action in actions}
        ),
        "before_challenge_id": before_challenge,
        "after_challenge_id": after_challenge,
        "fresh_challenge_after_failure": (
            before_challenge != after_challenge
        ),
        "screenshot": "rapid-keyboard-failure-recovery.png",
        "browser_errors": errors,
    }
    write_json(output / "rapid_keyboard_failure.json", evidence)
    return evidence


def make_realtime_contact_sheet(
    output: Path,
    matrix_root: Path,
) -> Path:
    selected = [
        ("L1 / FULL / LIVE", matrix_root / "d1-full-live" / "initial.png"),
        (
            "L3 / SIMPLIFIED / PAUSED",
            matrix_root / "d3-simplified-paused" / "initial.png",
        ),
        (
            "L4 ORIGINAL / FULL / LIVE",
            matrix_root / "d4-full-live" / "initial.png",
        ),
        (
            "L4 ORIGINAL / SOLVED",
            matrix_root / "d4-full-live" / "solved-pre-submit.png",
        ),
        (
            "L5 / VISIBLE GRADED WINDOW",
            matrix_root / "d5-full-live" / "initial.png",
        ),
        (
            "RAPID KEY FAILURE / FRESH RETRY",
            output / "rapid-keyboard-failure-recovery.png",
        ),
    ]
    width, height = 640, 360
    label_height = 34
    sheet = Image.new(
        "RGB",
        (width * 3, (height + label_height) * 2),
        "#12080a",
    )
    draw = ImageDraw.Draw(sheet)
    for index, (label, path) in enumerate(selected):
        row, column = divmod(index, 3)
        left = column * width
        top = row * (height + label_height)
        draw.text((left + 12, top + 10), label, fill="#ffe7a2")
        with Image.open(path).convert("RGB") as frame:
            thumb = frame.resize((width, height))
        sheet.paste(thumb, (left, top + label_height))
    destination = matrix_root / "contact_sheet.png"
    sheet.save(destination)
    return destination


def main() -> None:
    args = parse_args()
    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="slot-reel-complete-evidence-"))
    atexit.register(shutil.rmtree, temporary, ignore_errors=True)
    materializer = load_module(
        "slot_complete_materializer",
        MATERIALIZER_PATH,
    )
    setup = load_module("slot_complete_setup", SETUP_PATH)
    verifier = load_module("slot_complete_verifier", VERIFIER_PATH)
    legacy_grader = load_module(
        "slot_complete_legacy_grader",
        LEGACY_GRADER_PATH,
    )
    tasks_root, generation = capture_generation_evidence(
        output,
        temporary,
        materializer,
        setup,
    )

    matrix_root = output / "realtime_matrix"
    if matrix_root.exists():
        shutil.rmtree(matrix_root)
    matrix_root.mkdir(parents=True, exist_ok=True)
    entries = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for difficulty in range(1, 6):
            for interaction in ("simplified", "full"):
                task_json = controlled_task(
                    tasks_root,
                    difficulty,
                    interaction,
                )
                for time_mode in ("paused", "live"):
                    entries.append(
                        run_matrix_condition(
                            browser,
                            task_json,
                            difficulty,
                            interaction,
                            time_mode,
                            temporary,
                            matrix_root,
                            verifier,
                        )
                    )
        browser.close()

    expected_source = {
        "simplified": ["capture_button"],
        "full": ["physical_keyboard"],
    }
    same_world_by_difficulty = {}
    for entry in entries:
        if entry["input_sources"] != expected_source[entry["interaction"]]:
            raise AssertionError(f"wrong input source in matrix: {entry}")
        if entry["time_mode"] == "paused":
            if entry["inference_delay"]["task_time_delta_ms"] > 2:
                raise AssertionError(f"paused matrix entry advanced: {entry}")
            if entry["first_action_timing"]["task_time_delta_ms"] <= 10:
                raise AssertionError(
                    f"paused action did not advance task time: {entry}"
                )
        elif entry["inference_delay"]["task_time_delta_ms"] < 180:
            raise AssertionError(f"live matrix entry did not advance: {entry}")

    for difficulty in range(1, 6):
        level_entries = [
            entry
            for entry in entries
            if entry["difficulty"] == difficulty
        ]
        fingerprints = {
            entry["world_fingerprint"] for entry in level_entries
        }
        challenge_ids = {
            entry["challenge_id"] for entry in level_entries
        }
        same_world_by_difficulty[str(difficulty)] = {
            "same_world_across_interaction_and_time": len(fingerprints) == 1,
            "same_challenge_across_interaction_and_time": (
                len(challenge_ids) == 1
            ),
            "world_fingerprint": next(iter(fingerprints)),
            "challenge_id": next(iter(challenge_ids)),
        }
        if len(fingerprints) != 1 or len(challenge_ids) != 1:
            raise AssertionError(
                f"d{difficulty} changed across interaction or time modes"
            )

    matrix = {
        "ok": True,
        "environment": ENVIRONMENT.name,
        "condition_count": len(entries),
        "viewport": [
            EVALUATION_VIEWPORT["width"],
            EVALUATION_VIEWPORT["height"],
        ],
        "viewport_source": "env.json observation[0].resolution",
        "same_world_by_difficulty": same_world_by_difficulty,
        "entries": entries,
    }
    write_json(matrix_root / "summary.json", matrix)
    negatives = capture_negative_evidence(
        output,
        temporary,
        tasks_root,
        verifier,
        legacy_grader,
    )
    rapid_keyboard = capture_rapid_keyboard_failure(
        output,
        temporary,
        tasks_root,
    )
    make_realtime_contact_sheet(output, matrix_root)
    summary = {
        "ok": True,
        "environment": ENVIRONMENT.name,
        "generated_task_conditions": generation["task_condition_count"],
        "baseline_seed_checks": len(generation["baseline"]["seeds"]),
        "realtime_evaluation_settings": len(entries),
        "realtime_evaluation_viewport": [
            EVALUATION_VIEWPORT["width"],
            EVALUATION_VIEWPORT["height"],
        ],
        "server_and_exported_verifier_passes": len(entries),
        "l5_visible_cues_matching_graded_window": sum(
            1
            for entry in entries
            if entry["difficulty"] == 5
            and entry["capture_cue_geometry"].get(
                "matches_graded_window"
            )
            is True
        ),
        "live_server_negative_cases": len(
            negatives["live_server_cases"]
        ),
        "independent_negative_cases": len(
            negatives["independent_replay_cases"]
        ),
        "malformed_json_rejected": negatives["malformed_json"]["rejected"],
        "rapid_full_keyboard_inputs_preserved": (
            rapid_keyboard["server_witness_actions"]
        ),
    }
    write_json(output / "complete_evidence_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
