#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageChops, ImageStat
from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
BENCH_ROOT = ROOT / "weird_captcha_gym"
ENVIRONMENT = "parallel_grillmaster_env"
MECHANIC = "parallel_grillmaster"
ENV_ROOT = BENCH_ROOT / "environments" / ENVIRONMENT
APP_DIR = BENCH_ROOT / "shared_runtime" / "app"
SERVER = BENCH_ROOT / "shared_runtime" / "server" / "weird_captcha_server.py"
SETUP = BENCH_ROOT / "shared_scripts" / "setup_task.py"
MATERIALIZER = BENCH_ROOT / "tools" / "materialize_controlled_tasks.py"
HELPERS = BENCH_ROOT / "shared_runtime" / "verifier_helpers.py"
OBSERVATION_WINDOW_MS = 800
MODEL_DELAY_MS = 700


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Solve Parallel Grillmaster's controlled task matrix in live and "
            "paused shared-clock modes."
        )
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--difficulty", type=int, choices=range(1, 6))
    parser.add_argument(
        "--interaction",
        choices=("simplified", "full"),
        help="Run one interaction mode instead of both.",
    )
    parser.add_argument(
        "--time-mode",
        choices=("live", "paused"),
        help="Run one time mode instead of both.",
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


def world_fingerprint(public_state: dict[str, Any]) -> str:
    value = copy.deepcopy(public_state)
    for key in ("task_id", "challenge_id", "control_condition"):
        value.pop(key, None)
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def image_difference(left: bytes, right: bytes) -> float:
    first = Image.open(io.BytesIO(left)).convert("RGB")
    second = Image.open(io.BytesIO(right)).convert("RGB")
    return sum(ImageStat.Stat(ImageChops.difference(first, second)).mean) / 3


def reserve_port() -> int:
    with socket.socket() as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def start_server(
    task_json: Path,
    state_dir: Path,
    seed: str,
    mode: str,
) -> tuple[subprocess.Popen, int]:
    subprocess.run(
        [
            "python",
            "-B",
            str(SETUP),
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
    port = reserve_port()
    server_env = os.environ.copy()
    server_env.update(
        {
            "WEIRD_CAPTCHA_TIME_MODE": mode,
            "WEIRD_CAPTCHA_START_PAUSED": "1",
        }
    )
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
        env=server_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 8
    while time.time() < deadline:
        try:
            import urllib.request

            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/health", timeout=0.5
            ).read()
            return process, port
        except Exception:
            time.sleep(0.1)
    process.kill()
    raise RuntimeError("Parallel Grillmaster evidence server did not start")


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
            f"expected one D{difficulty} {interaction} task, found {matches}"
        )
    return matches[0]


def clock_status(page) -> dict[str, Any]:
    return page.evaluate("WeirdCaptchaTime.status()")


def time_command(
    page,
    command: str,
    **values: float,
) -> dict[str, Any]:
    response = page.evaluate(
        """async payload => {
          const response = await fetch("/time-control", {
            method: "POST",
            headers: {"content-type": "application/json"},
            body: JSON.stringify(payload),
            cache: "no-store",
          });
          if (!response.ok) throw new Error(await response.text());
          return response.json();
        }""",
        {"command": command, **values},
    )
    sequence = int(response["sequence"])
    expected = "running" if command == "resume" else "paused"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        status = page.evaluate("WeirdCaptchaTime.status()")
        sequence_matches = int(status["sequence"]) == sequence
        phase_matches = (
            status["phase"] == "completed"
            if command == "run_for"
            else status["state"] == expected
        )
        if sequence_matches and phase_matches:
            break
        time.sleep(0.02)
    else:
        raise AssertionError(
            f"time command {command} sequence {sequence} was not applied"
        )
    return response


def screenshot(page, path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Playwright's drag helper may scroll the dragged element into view. Keep
    # every evidence frame anchored to the complete task from its top edge.
    page.evaluate("window.scrollTo(0, 0)")
    return page.screenshot(path=str(path))


def run_action(
    page,
    mode: str,
    callback: Callable[[], None],
    *,
    settle_ms: int = 45,
) -> float:
    if mode == "paused":
        time_command(page, "resume")
    before = float(clock_status(page)["task_time_ms"])
    callback()
    page.wait_for_timeout(settle_ms)
    after = float(clock_status(page)["task_time_ms"])
    if mode == "paused":
        time_command(page, "pause")
        if clock_status(page)["state"] != "paused":
            raise AssertionError("paused action did not return to a frozen state")
    if after <= before:
        raise AssertionError("task time did not advance during a visible action")
    return after - before


def move_food(
    page,
    food_id: str,
    destination: str,
    interaction: str,
    mode: str,
) -> list[float]:
    food = page.locator(f'.grill-food[data-food-id="{food_id}"]')
    if interaction == "full":
        deltas = [
            run_action(
                page,
                mode,
                lambda: food.drag_to(
                    page.locator(f'.grill-zone[data-drop-zone="{destination}"]')
                ),
            )
        ]
    else:
        deltas = [
            run_action(page, mode, food.click),
        ]
        button = "#grill-start-selected" if destination == "grill" else "#grill-serve-selected"
        expect(page.locator(button)).to_be_enabled()
        deltas.append(run_action(page, mode, page.locator(button).click))
    expect(
        page.locator(
            f'.grill-zone[data-drop-zone="{destination}"] '
            f'.grill-food[data-food-id="{food_id}"]'
        )
    ).to_be_visible()
    return deltas


def advance_paused_observation(page) -> float:
    before = float(clock_status(page)["task_time_ms"])
    time_command(
        page,
        "run_for",
        milliseconds=OBSERVATION_WINDOW_MS,
        start_delay_ms=0,
    )
    after = float(clock_status(page)["task_time_ms"])
    if after - before < OBSERVATION_WINDOW_MS - 50:
        raise AssertionError("paused observation did not advance the configured window")
    return after - before


def elapsed_for_food(page, food_id: str) -> float:
    return float(
        page.evaluate(
            """foodId => {
              const record = grillModel.records[foodId];
              return performance.now() - record.startedAt;
            }""",
            food_id,
        )
    )


def solve(
    page,
    truth: dict[str, Any],
    interaction: str,
    mode: str,
    out_dir: Path,
) -> dict[str, Any]:
    action_deltas: list[float] = []
    observation_cycles = 0
    targets = truth["targets"]
    for food_id in targets:
        action_deltas.extend(
            move_food(page, food_id, "grill", interaction, mode)
        )
    screenshot(page, out_dir / "all-foods-started.png")

    ready_order = sorted(
        targets.items(),
        key=lambda item: (
            float(
                page.evaluate(
                    "foodId => grillModel.records[foodId].startedAt",
                    item[0],
                )
            )
            + float(item[1]["target_ms"])
            + float(item[1]["tolerance_ms"])
        ),
    )
    for food_id, target in ready_order:
        target_ms = float(target["target_ms"])
        tolerance_ms = float(target["tolerance_ms"])
        preselected = interaction == "simplified"
        if preselected:
            action_deltas.append(
                run_action(
                    page,
                    mode,
                    page.locator(
                        f'.grill-food[data-food-id="{food_id}"]'
                    ).click,
                )
            )
            expect(page.locator("#grill-serve-selected")).to_be_enabled()
        if mode == "live":
            remaining = target_ms - elapsed_for_food(page, food_id)
            if remaining > 0:
                page.wait_for_timeout(int(remaining))
        else:
            # One fixed observation may land almost a full 800 ms after the
            # ready interval opens. Leave the rest of the shortest configured
            # window for the visible select/serve action itself.
            ready_threshold = target_ms - tolerance_ms + 10
            while elapsed_for_food(page, food_id) < ready_threshold:
                advance_paused_observation(page)
                observation_cycles += 1
        expect(
            page.locator(
                f'.grill-food[data-food-id="{food_id}"][data-cook-state="ready"]'
            )
        ).to_be_visible()
        if preselected:
            action_deltas.append(
                run_action(
                    page,
                    mode,
                    page.locator("#grill-serve-selected").click,
                )
            )
            expect(
                page.locator(
                    '.grill-zone[data-drop-zone="tray"] '
                    f'.grill-food[data-food-id="{food_id}"]'
                )
            ).to_be_visible()
        else:
            action_deltas.extend(
                move_food(page, food_id, "tray", interaction, mode)
            )

    expect(
        page.locator('.grill-zone[data-drop-zone="tray"] .grill-food')
    ).to_have_count(len(targets))
    screenshot(page, out_dir / "solved-before-submit.png")
    client_result = page.evaluate(
        """() => {
          const durations = {};
          for (const [foodId, record] of Object.entries(grillModel.records)) {
            if (record.place === "tray" && record.duration != null) {
              durations[foodId] = Math.round(record.duration);
            }
          }
          return {
            mechanic_id: grillModel.state.mechanic_id,
            task_id: grillModel.state.task_id,
            challenge_id: grillModel.state.challenge_id,
            durations_ms: durations,
            actions: grillModel.actions,
          };
        }"""
    )
    (out_dir / "client-result-before-submit.json").write_text(
        json.dumps(client_result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if mode == "paused":
        time_command(page, "resume")
    submit_before = float(clock_status(page)["task_time_ms"])
    page.locator("#submit-grill").click()
    expect(page.locator(".readout")).to_have_attribute(
        "data-status", "passed", timeout=8_000
    )
    submit_after = float(clock_status(page)["task_time_ms"])
    if mode == "paused":
        time_command(page, "pause")
    action_deltas.append(submit_after - submit_before)
    screenshot(page, out_dir / "pass.png")
    return {
        "action_task_time_deltas_ms": [round(value, 3) for value in action_deltas],
        "paused_observation_cycles": observation_cycles,
    }


def run_condition(
    browser,
    helpers,
    task_json: Path,
    temp_root: Path,
    out_root: Path,
    difficulty: int,
    interaction: str,
    mode: str,
) -> dict[str, Any]:
    state_dir = temp_root / f"d{difficulty}-{interaction}-{mode}"
    state_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = out_root / f"d{difficulty}-{interaction}-{mode}"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    seed = f"parallel-grillmaster-time-matrix-d{difficulty}"
    process, port = start_server(task_json, state_dir, seed, mode)
    errors: list[str] = []
    page = browser.new_page(
        viewport={"width": 1280, "height": 720},
        device_scale_factor=1,
    )
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        current_task = state_dir / "current_task.json"
        current_task_text = current_task.read_text(encoding="utf-8")
        current_task.unlink()
        try:
            page.goto(
                f"http://127.0.0.1:{port}/"
                f"?time_mode={mode}&start_paused=1&time_control=1",
                wait_until="domcontentloaded",
            )
        finally:
            current_task.write_text(current_task_text, encoding="utf-8")

        page.wait_for_function("WeirdCaptchaTime.status().ready === true")
        expect(page.locator(".grill-captcha")).to_have_attribute(
            "data-interaction", interaction
        )
        initial_state = read_json(state_dir / "public_state.json")
        truth = read_json(state_dir / "ground_truth.json")
        initial_clock = clock_status(page)
        if initial_clock["state"] != "paused":
            raise AssertionError("task did not remain paused through initialization")

        if mode == "live":
            time_command(page, "resume")
        before_image = screenshot(page, evidence_dir / "before-model-delay.png")
        before_delay = clock_status(page)
        page.wait_for_timeout(MODEL_DELAY_MS)
        after_image = screenshot(page, evidence_dir / "after-model-delay.png")
        after_delay = clock_status(page)
        model_delta = (
            float(after_delay["task_time_ms"])
            - float(before_delay["task_time_ms"])
        )
        if mode == "live" and model_delta < MODEL_DELAY_MS - 100:
            raise AssertionError(f"live task advanced only {model_delta:.1f}ms")
        if mode == "paused" and abs(model_delta) > 1:
            raise AssertionError(f"paused task advanced {model_delta:.1f}ms")

        solve_evidence = solve(
            page,
            truth,
            interaction,
            mode,
            evidence_dir,
        )
        result = read_json(state_dir / "result.json")
        truth = read_json(state_dir / "ground_truth.json")
        final_public = read_json(state_dir / "public_state.json")
        server_grade = result.get("server_grade") or {}
        exported = {
            "result": result,
            "ground_truth": truth,
            "public_state": final_public,
        }
        verifier = helpers.verify_external_mechanic(exported, MECHANIC)
        if server_grade.get("passed") is not True:
            raise AssertionError(f"server rejected {difficulty}/{interaction}/{mode}")
        if verifier.get("passed") is not True or verifier.get("score") != 100:
            raise AssertionError(
                f"verifier rejected {difficulty}/{interaction}/{mode}: {verifier}"
            )
        if errors:
            raise AssertionError(
                f"browser errors in {difficulty}/{interaction}/{mode}: {errors}"
            )

        actions = (result.get("trusted_witness") or {}).get("actions") or []
        starts = [
            float(item["task_time_ms"])
            for item in actions
            if item.get("kind") == "start"
        ]
        condition = truth["control_condition"]
        parallel_count = int(
            condition["difficulty_parameters"]["parallel_start_count"]
        )
        start_spread = (
            max(sorted(starts)[:parallel_count])
            - min(sorted(starts)[:parallel_count])
            if parallel_count > 1
            else 0.0
        )
        for name, value in (
            ("result.json", result),
            ("server-grade.json", server_grade),
            ("verifier.json", verifier),
            ("public-state.json", final_public),
            ("exported-result.json", exported),
        ):
            (evidence_dir / name).write_text(
                json.dumps(value, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

        return {
            "passed": True,
            "difficulty": difficulty,
            "interaction": interaction,
            "time_mode": mode,
            "challenge_id": truth["challenge_id"],
            "world_fingerprint": world_fingerprint(initial_state),
            "food_count": len(truth["targets"]),
            "input_sources": sorted(
                {str(item.get("input_source") or "") for item in actions}
            ),
            "model_delay_wall_ms": MODEL_DELAY_MS,
            "model_delay_task_delta_ms": round(model_delta, 3),
            "model_delay_visual_difference": image_difference(
                before_image, after_image
            ),
            "clock_state_after_model_delay": after_delay["state"],
            "start_spread_ms": round(start_spread, 3),
            "server_grade": server_grade,
            "verifier": verifier,
            "page_errors": errors,
            "task_time_at_pass_ms": round(
                float(clock_status(page)["task_time_ms"]), 3
            ),
            **solve_evidence,
        }
    finally:
        page.close()
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    difficulties = (args.difficulty,) if args.difficulty else range(1, 6)
    interactions = (
        (args.interaction,)
        if args.interaction
        else ("simplified", "full")
    )
    time_modes = (
        (args.time_mode,)
        if args.time_mode
        else ("paused", "live")
    )
    helpers = load_module("parallel_grillmaster_time_helpers", HELPERS)
    materializer = load_module(
        "parallel_grillmaster_time_materializer", MATERIALIZER
    )

    with tempfile.TemporaryDirectory(
        prefix="parallel-grillmaster-time-matrix-"
    ) as temporary:
        temp_root = Path(temporary)
        materialized = temp_root / "materialized"
        materializer.materialize_environment(ENV_ROOT, materialized)
        tasks_root = materialized / ENVIRONMENT / "tasks"
        rows: list[dict[str, Any]] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for difficulty in difficulties:
                for interaction in interactions:
                    task_json = controlled_task(
                        tasks_root, difficulty, interaction
                    )
                    for mode in time_modes:
                        rows.append(
                            run_condition(
                                browser,
                                helpers,
                                task_json,
                                temp_root,
                                args.out_dir,
                                difficulty,
                                interaction,
                                mode,
                            )
                        )
            browser.close()

    for difficulty in difficulties:
        level_rows = [
            row for row in rows if row["difficulty"] == difficulty
        ]
        for interaction in interactions:
            pair = [
                row
                for row in level_rows
                if row["interaction"] == interaction
            ]
            if len(time_modes) == 2:
                if len(pair) != 2:
                    raise AssertionError("live/paused condition pair is incomplete")
                if pair[0]["challenge_id"] != pair[1]["challenge_id"]:
                    raise AssertionError("live and paused used different challenges")
                if (
                    pair[0]["world_fingerprint"]
                    != pair[1]["world_fingerprint"]
                ):
                    raise AssertionError("live and paused used different worlds")
        if len(interactions) == 2:
            interaction_worlds = {
                row["world_fingerprint"] for row in level_rows
            }
            if len(interaction_worlds) != 1:
                raise AssertionError(
                    f"D{difficulty} simplified/full worlds differ"
                )

    output = {
        "environment": ENVIRONMENT,
        "mechanic": MECHANIC,
        "settings": {
            "observation_window_ms": OBSERVATION_WINDOW_MS,
            "frames_per_observation": 6,
            "play_time_seconds": 120,
            "model_delay_ms": MODEL_DELAY_MS,
        },
        "condition_count": len(rows),
        "all_passed": all(row["passed"] for row in rows),
        "rows": rows,
    }
    (args.out_dir / "summary.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
