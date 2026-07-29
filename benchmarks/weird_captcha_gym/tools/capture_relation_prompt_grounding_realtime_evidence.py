#!/usr/bin/env python3
"""Capture target-specific live and paused evidence for Relation Prompt Grounding.

The capture uses the same local loopback server and shared time-control protocol
as evaluation.  It intentionally keeps the browser headless and uses a fresh
temporary task/state directory on each invocation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path
from typing import Any

from playwright.sync_api import expect, sync_playwright

from smoke_controlled_interaction_ui import BENCH_ROOT, controlled_task, read_json, start_server


ROOT = Path(__file__).resolve().parents[3]
ENVIRONMENT = BENCH_ROOT / "environments" / "relation_prompt_grounding_env"
MECHANIC = "relation_prompt_grounding"
MATERIALIZER_PATH = BENCH_ROOT / "tools" / "materialize_controlled_tasks.py"
SOLVER_PATH = BENCH_ROOT / "tools" / "incubator_solvers" / f"{MECHANIC}.py"
HELPERS_PATH = BENCH_ROOT / "shared_runtime" / "verifier_helpers.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ENVIRONMENT / "evidence_docs" / "realtime_delay",
    )
    return parser.parse_args()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def png_resolution(image: bytes) -> list[int]:
    if image[:8] != b"\x89PNG\r\n\x1a\n" or image[12:16] != b"IHDR":
        raise AssertionError("expected a PNG screenshot")
    return [int.from_bytes(image[16:20], "big"), int.from_bytes(image[20:24], "big")]


def clock(page) -> dict[str, Any]:
    return page.evaluate("() => WeirdCaptchaTime.status()")


def command(page, name: str, **details: Any) -> dict[str, Any]:
    payload = {"command": name, **details}
    return page.evaluate(
        """async payload => {
          const response = await fetch('/time-control', {
            method: 'POST', headers: {'content-type': 'application/json'},
            body: JSON.stringify(payload), cache: 'no-store',
          });
          if (!response.ok) throw new Error(`time command ${payload.command} failed: ${response.status}`);
          return await response.json();
        }""",
        payload,
    )


def wait_for_clock(page, expression: str) -> dict[str, Any]:
    page.wait_for_function(f"() => ({expression})", timeout=10_000)
    return clock(page)


def screenshot(page, path: Path, expected_resolution: list[int]) -> tuple[bytes, str]:
    image = page.screenshot(path=str(path))
    if png_resolution(image) != expected_resolution:
        raise AssertionError(f"unexpected screenshot resolution: {png_resolution(image)}")
    return image, hashlib.sha256(image).hexdigest()


def capture_live(page, out_dir: Path, resolution: list[int]) -> dict[str, Any]:
    command(page, "resume")
    wait_for_clock(page, "WeirdCaptchaTime.status().state === 'running'")
    frames: list[dict[str, Any]] = []
    for index in range(5):
        image, digest = screenshot(page, out_dir / f"live-observation-frame-{index + 1}.png", resolution)
        frames.append({"file": f"live-observation-frame-{index + 1}.png", "sha256": digest, "task_time_ms": clock(page)["task_time_ms"]})
    if len({frame["sha256"] for frame in frames}) < 4:
        raise AssertionError("live five-frame observation did not show carousel motion")
    before = clock(page)
    before_image, before_digest = screenshot(page, out_dir / "live-before-model-delay.png", resolution)
    page.wait_for_timeout(800)
    after = clock(page)
    after_image, after_digest = screenshot(page, out_dir / "live-after-model-delay.png", resolution)
    delta = float(after["task_time_ms"]) - float(before["task_time_ms"])
    if delta < 700:
        raise AssertionError(f"live task clock did not advance through model delay: {delta}ms")
    if before_image == after_image:
        raise AssertionError("live carousel did not visibly advance through model delay")
    return {
        "observation_frames": frames,
        "before_model_delay": before,
        "after_model_delay": after,
        "delay_task_time_delta_ms": delta,
        "before_image": "live-before-model-delay.png",
        "after_image": "live-after-model-delay.png",
        "before_image_sha256": before_digest,
        "after_image_sha256": after_digest,
    }


def capture_paused(page, out_dir: Path, state_dir: Path, resolution: list[int]) -> dict[str, Any]:
    if clock(page)["state"] != "paused":
        command(page, "pause")
        wait_for_clock(page, "WeirdCaptchaTime.status().state === 'paused'")

    observation_before = clock(page)
    command(page, "run_for", milliseconds=600)
    wait_for_clock(page, "WeirdCaptchaTime.status().phase === 'running_window'")
    observation_frames: list[dict[str, Any]] = []
    for index in range(5):
        image, digest = screenshot(page, out_dir / f"paused-observation-frame-{index + 1}.png", resolution)
        observation_frames.append({"file": f"paused-observation-frame-{index + 1}.png", "sha256": digest, "task_time_ms": clock(page)["task_time_ms"]})
    wait_for_clock(page, "WeirdCaptchaTime.status().state === 'paused' && WeirdCaptchaTime.status().phase === 'completed'")
    observation_after = clock(page)
    observation_delta = float(observation_after["task_time_ms"]) - float(observation_before["task_time_ms"])
    if not 500 <= observation_delta <= 760:
        raise AssertionError(f"paused observation window did not run for its configured duration: {observation_delta}ms")
    if len({frame["sha256"] for frame in observation_frames}) < 4:
        raise AssertionError("paused five-frame observation did not show enough carousel motion before it froze")

    before_delay = clock(page)
    before_image, before_digest = screenshot(page, out_dir / "paused-before-model-delay.png", resolution)
    page.wait_for_timeout(800)
    after_delay = clock(page)
    after_image, after_digest = screenshot(page, out_dir / "paused-after-model-delay.png", resolution)
    inference_delta = float(after_delay["task_time_ms"]) - float(before_delay["task_time_ms"])
    if abs(inference_delta) > 2:
        raise AssertionError(f"paused task clock advanced through model delay: {inference_delta}ms")
    if before_image != after_image:
        raise AssertionError("paused task screenshot changed during model inference")

    solver = load_module("relation_prompt_grounding_realtime_solver", SOLVER_PATH)
    truth = read_json(state_dir / "ground_truth.json")
    action_before = clock(page)
    command(page, "resume")
    wait_for_clock(page, "WeirdCaptchaTime.status().state === 'running'")
    ordered_ids = [item["id"] for item in truth["objects"] if item.get("container")]
    ordered_ids.extend(item["id"] for item in truth["objects"] if not item.get("container"))
    for object_id in ordered_ids:
        solver._drag_object(page, object_id, truth["solution_positions"][object_id], truth["stage"])
    for object_id, target in truth["solution_positions"].items():
        if int(target["depth"]) != 50:
            solver._set_depth(page, object_id, int(target["depth"]))
    expect(page.locator(".rel-placed-count[data-ready='true']")).to_contain_text(f"{len(ordered_ids)}/{len(ordered_ids)}")
    page.locator(".rel-settle").click()
    page.wait_for_function("() => window.relationAssemblyModel.settling === true", timeout=3_000)
    _settling_image, settling_digest = screenshot(page, out_dir / "paused-settle-action.png", resolution)
    command(page, "settle_pause")
    wait_for_clock(
        page,
        "window.relationAssemblyModel.settled === true && WeirdCaptchaTime.status().state === 'paused' && WeirdCaptchaTime.status().pending_action_count === 0",
    )
    after_settle = clock(page)
    _settled_image, settled_digest = screenshot(page, out_dir / "paused-settle-complete.png", resolution)
    events = page.evaluate("() => window.relationAssemblyModel.events")
    settle_ticks = [event for event in events if event.get("kind") == "settle_tick"]
    if len(settle_ticks) != int(truth["settle_ticks"]) or events[-1].get("kind") != "settle_complete":
        raise AssertionError("paused settle action did not reach its complete eight-tick state")

    command(page, "resume")
    wait_for_clock(page, "WeirdCaptchaTime.status().state === 'running'")
    page.locator(".rel-submit").click()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=8_000)
    _pass_image, pass_digest = screenshot(page, out_dir / "paused-action-pass.png", resolution)
    command(page, "settle_pause")
    wait_for_clock(page, "WeirdCaptchaTime.status().state === 'paused'")
    exported = {
        "result": read_json(state_dir / "result.json"),
        "ground_truth": read_json(state_dir / "ground_truth.json"),
        "public_state": read_json(state_dir / "public_state.json"),
    }
    helpers = load_module("relation_prompt_grounding_realtime_helpers", HELPERS_PATH)
    verifier = helpers.verify_external_mechanic(exported, MECHANIC)
    server_grade = exported["result"].get("server_grade") or {}
    if server_grade.get("passed") is not True or verifier.get("passed") is not True or verifier.get("score") != 100:
        raise AssertionError(f"paused action result was not accepted: server={server_grade}; verifier={verifier}")
    (out_dir / "paused-action-exported-result.json").write_text(
        json.dumps({**exported, "independent_verifier": verifier}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "observation_before": observation_before,
        "observation_after": observation_after,
        "observation_task_time_delta_ms": observation_delta,
        "observation_frames": observation_frames,
        "before_model_delay": before_delay,
        "after_model_delay": after_delay,
        "delay_task_time_delta_ms": inference_delta,
        "before_image": "paused-before-model-delay.png",
        "after_image": "paused-after-model-delay.png",
        "before_image_sha256": before_digest,
        "after_image_sha256": after_digest,
        "settle_action": {
            "task_time_before_action_ms": action_before["task_time_ms"],
            "task_time_after_settle_ms": after_settle["task_time_ms"],
            "settle_tick_count": len(settle_ticks),
            "settling_image": "paused-settle-action.png",
            "settling_image_sha256": settling_digest,
            "settled_image": "paused-settle-complete.png",
            "settled_image_sha256": settled_digest,
            "pass_image": "paused-action-pass.png",
            "pass_image_sha256": pass_digest,
            "server_grade": server_grade,
            "independent_verifier": verifier,
        },
    }


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    environment = read_json(ENVIRONMENT / "env.json")
    screens = [item for item in environment.get("observation") or [] if item.get("type") == "rgb_screen"]
    if len(screens) != 1:
        raise AssertionError("relation environment must declare one RGB screen")
    resolution = list(screens[0].get("resolution") or [])
    if len(resolution) != 2 or not all(isinstance(value, int) and value > 0 for value in resolution):
        raise AssertionError("relation environment RGB screen is malformed")
    materializer = load_module("relation_prompt_grounding_realtime_materializer", MATERIALIZER_PATH)
    evidence: dict[str, Any] = {
        "environment": ENVIRONMENT.name,
        "mechanic": MECHANIC,
        "difficulty": 4,
        "interaction": "full",
        "observation_window_ms": 600,
        "frames_per_observation": 5,
        "observation_resolution": resolution,
        "modes": {},
    }
    with tempfile.TemporaryDirectory(prefix="relation-prompt-grounding-realtime-") as temporary_name:
        temporary = Path(temporary_name)
        materializer.materialize_environment(ENVIRONMENT, temporary / "materialized")
        task = controlled_task(temporary / "materialized" / ENVIRONMENT.name / "tasks", 4, "full")
        evidence["task"] = task.parent.name
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for mode in ("live", "paused"):
                state_dir = temporary / mode
                state_dir.mkdir()
                process, port = start_server(task, MECHANIC, "full", state_dir)
                page = browser.new_page(viewport={"width": resolution[0], "height": resolution[1]}, device_scale_factor=1)
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                try:
                    page.goto(
                        f"http://127.0.0.1:{port}/?time_mode={mode}&start_paused=1&time_control=1",
                        # `time_control=1` intentionally polls the local
                        # companion, so network idle is never a meaningful
                        # readiness condition for this capture.
                        wait_until="domcontentloaded",
                    )
                    expect(page.locator('.relation-assembly-captcha[data-interaction="full"]')).to_be_visible()
                    wait_for_clock(page, "WeirdCaptchaTime.status().ready === true")
                    if mode == "live":
                        evidence["modes"][mode] = capture_live(page, args.out_dir, resolution)
                    else:
                        evidence["modes"][mode] = capture_paused(page, args.out_dir, state_dir, resolution)
                    if errors:
                        raise AssertionError(f"{mode} browser errors: {errors}")
                finally:
                    page.close()
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except Exception:
                        process.kill()
            browser.close()
    live_delta = float(evidence["modes"]["live"]["delay_task_time_delta_ms"])
    paused_delta = float(evidence["modes"]["paused"]["delay_task_time_delta_ms"])
    if live_delta < 700 or abs(paused_delta) > 2:
        raise AssertionError(f"unexpected inference timing: live={live_delta}; paused={paused_delta}")
    (args.out_dir / "realtime-delay.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
