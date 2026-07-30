#!/usr/bin/env python3
"""Capture target-specific temporal evidence for Reload Interruption.

Each page is a new context in a newly launched headless Playwright browser.
The server state directory is temporary and the server binds to 127.0.0.1.
The capture deliberately records the visible, once-only lever preview before
any solve, then the configured six-frame observation schedule in live and
paused modes.  It never connects to or controls a user browser or desktop.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENV_ROOT = BENCHMARK / "environments" / "reload_interruption_env"
MATERIALIZER = BENCHMARK / "tools" / "materialize_controlled_tasks.py"
CAPTURE_HELPER = BENCHMARK / "tools" / "capture_reload_interruption_controllability_evidence.py"
VIEWPORT = {"width": 1280, "height": 720}
VECTORS = {"up": (0, -1), "right": (1, 0), "down": (0, 1), "left": (-1, 0)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ENV_ROOT / "evidence_docs" / "temporal_visual_v1",
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


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalized_world(state: dict[str, Any]) -> dict[str, Any]:
    result = dict(state)
    for key in ("task_id", "challenge_id", "control_condition"):
        result.pop(key, None)
    return result


def world_fingerprint(state: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(normalized_world(state), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def time_request(port: int, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=body,
        headers={"content-type": "application/json"} if body is not None else {},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise RuntimeError(f"time controller returned a non-object at {path}")
    return value


def wait_for_time_status(port: int, predicate, *, timeout: float = 5) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            last = time_request(port, "/time-control/status")
            if predicate(last):
                return last
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            pass
        time.sleep(.02)
    raise TimeoutError(f"time controller did not reach the expected state: {last}")


def command_clock(port: int, command: str) -> dict[str, Any]:
    accepted = time_request(port, "/time-control", {"command": command})
    sequence = int(accepted["sequence"])
    expected_state = "running" if command == "resume" else "paused"
    return wait_for_time_status(
        port,
        lambda item: int(item.get("sequence") or -1) == sequence and item.get("state") == expected_state,
    )


def visible_preview_state(page) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const root = document.querySelector('.reload-v2');
          const lever = document.querySelector('.reload-v2-lever');
          const chamber = document.querySelector('.reload-chamber');
          return {
            previewing: root?.classList.contains('is-previewing') || false,
            ready: root?.classList.contains('is-ready') || false,
            lever_preview: lever?.dataset.preview || '',
            lever_x: lever?.style.getPropertyValue('--lever-x') || '',
            lever_y: lever?.style.getPropertyValue('--lever-y') || '',
            chamber_turn: chamber?.style.getPropertyValue('--preview-turn') || '',
          };
        }"""
    )


def screenshot_record(page, path: Path, *, frame: int, target_elapsed_ms: float | None = None) -> dict[str, Any]:
    before_capture = page.evaluate("() => WeirdCaptchaTime.status()")
    image = page.screenshot(path=str(path))
    after_capture = page.evaluate("() => WeirdCaptchaTime.status()")
    return {
        "frame": frame,
        "target_elapsed_ms": target_elapsed_ms,
        "capture_started_task_time_ms": before_capture["task_time_ms"],
        "capture_completed_task_time_ms": after_capture["task_time_ms"],
        "task_time_ms": after_capture["task_time_ms"],
        "time_status": after_capture,
        "image": path.name,
        "sha256": hashlib.sha256(image).hexdigest(),
        "visible_preview_state": visible_preview_state(page),
    }


def open_task(browser, helper, *, task: Path, state_dir: Path, seed: str, mode: str):
    port = helper.free_port()
    process = helper.start_server(task, state_dir, port, seed)
    context = browser.new_context(viewport=VIEWPORT, device_scale_factor=1)
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    current_task = state_dir / "current_task.json"
    current_task_text = current_task.read_text(encoding="utf-8")
    current_task.unlink()
    try:
        page.goto(
            f"http://127.0.0.1:{port}/?time_mode={mode}&start_paused=1&time_control=1",
            # time_control=1 continuously polls the loopback controller, so
            # networkidle is intentionally unreachable. The visible mechanic
            # root and the controller-ready status below are the readiness
            # conditions for this isolated dynamic page.
            wait_until="domcontentloaded",
        )
    finally:
        current_task.write_text(current_task_text, encoding="utf-8")
    expect(page.locator(".reload-v2")).to_be_visible()
    if page.evaluate("() => WeirdCaptchaTime.status().state") != "paused":
        raise AssertionError("temporal capture must begin from the paused observation boundary")
    wait_for_time_status(port, lambda item: item.get("ready") is True and item.get("state") == "paused")
    return process, context, page, errors, port


def close_task(helper, process, context, page) -> None:
    page.close()
    context.close()
    helper.stop_server(process)


def capture_preview(browser, helper, *, task: Path, difficulty: int, work_root: Path, out_dir: Path) -> dict[str, Any]:
    state_dir = work_root / f"preview-d{difficulty}"
    state_dir.mkdir()
    process, context, page, errors, port = open_task(
        browser,
        helper,
        task=task,
        state_dir=state_dir,
        seed=f"reload-temporal-preview-d{difficulty}",
        mode="paused",
    )
    try:
        state = read_json(state_dir / "public_state.json")
        sequence = list(state["sequence"])
        preview_step_ms = int(state["preview_step_ms"])
        write_json(out_dir / f"d{difficulty}-full-public_state.json", state)
        command_clock(port, "resume")
        expect(page.locator(".reload-v2.is-previewing")).to_be_visible(timeout=2_000)
        frames = []
        for index, direction in enumerate(sequence):
            turn = f"{index * 51}deg"
            page.wait_for_function(
                """turn => {
                  const lever = document.querySelector('.reload-v2-lever');
                  const chamber = document.querySelector('.reload-chamber');
                  return lever?.dataset.preview === 'true'
                    && chamber?.style.getPropertyValue('--preview-turn') === turn;
                }""",
                arg=turn,
                timeout=2_000,
            )
            path = out_dir / f"d{difficulty}-full-preview-frame-{index + 1:02d}.png"
            record = screenshot_record(page, path, frame=index + 1)
            expected = {
                "lever_x": f"{VECTORS[direction][0] * 46}px",
                "lever_y": f"{VECTORS[direction][1] * 46}px",
                "chamber_turn": turn,
            }
            if not record["visible_preview_state"]["previewing"] or any(
                record["visible_preview_state"][key] != value for key, value in expected.items()
            ):
                raise AssertionError(f"d{difficulty} preview frame {index + 1} was not visibly {direction}: {record}")
            record["sequence_index"] = index + 1
            record["generated_direction"] = direction
            frames.append(record)
        expect(page.locator(".reload-v2.is-ready")).to_be_visible(timeout=4_000)
        if len({frame["sha256"] for frame in frames}) != len(frames):
            raise AssertionError(f"d{difficulty} preview frames were not visually distinct")
        if errors:
            raise AssertionError(f"d{difficulty} preview browser errors: {errors}")
        return {
            "difficulty": difficulty,
            "interaction": "full",
            "challenge_id": state["challenge_id"],
            "world_fingerprint_without_identity": world_fingerprint(state),
            "preview_step_ms": preview_step_ms,
            "sequence_length": len(sequence),
            "frames": frames,
            "completed_ready_state": page.evaluate("() => WeirdCaptchaTime.status()"),
        }
    finally:
        close_task(helper, process, context, page)


def capture_observation(browser, helper, *, task: Path, mode: str, work_root: Path, out_dir: Path) -> dict[str, Any]:
    state_dir = work_root / f"observation-{mode}"
    state_dir.mkdir()
    process, context, page, errors, port = open_task(
        browser,
        helper,
        task=task,
        state_dir=state_dir,
        seed="reload-temporal-observation-l4",
        mode=mode,
    )
    try:
        state = read_json(state_dir / "public_state.json")
        real_time = read_json(ENV_ROOT / "controls.json")["real_time"]
        window_ms = int(real_time["observation_window_ms"])
        frame_count = int(real_time["frames_per_observation"])
        if frame_count != 6:
            raise AssertionError(f"expected six configured frames, got {frame_count}")
        write_json(out_dir / f"{mode}-public_state.json", state)

        # The preview begins after 700 task milliseconds.  Starting this exact
        # configured observation window at 650 ms makes the delivered frames
        # visibly span the once-only preview instead of a static ready screen.
        command_clock(port, "resume")
        page.wait_for_function("target => WeirdCaptchaTime.status().task_time_ms >= target", arg=650, timeout=3_000)
        window_start = page.evaluate("() => WeirdCaptchaTime.status()")
        frames = []
        for number in range(1, frame_count + 1):
            target = window_ms * (number - 1) / (frame_count - 1)
            page.wait_for_function(
                "target => WeirdCaptchaTime.status().task_time_ms >= target",
                arg=float(window_start["task_time_ms"]) + target,
                timeout=3_000,
            )
            frames.append(
                screenshot_record(
                    page,
                    out_dir / f"{mode}-observation-frame-{number:03d}.png",
                    frame=number,
                    target_elapsed_ms=target,
                )
            )
        after_window = page.evaluate("() => WeirdCaptchaTime.status()")
        if mode == "paused":
            command_clock(port, "pause")
        before_delay = page.evaluate("() => WeirdCaptchaTime.status()")
        before_image = page.screenshot(path=str(out_dir / f"{mode}-before-model-delay.png"))
        before_visible = visible_preview_state(page)
        page.wait_for_timeout(240)
        after_delay = page.evaluate("() => WeirdCaptchaTime.status()")
        after_image = page.screenshot(path=str(out_dir / f"{mode}-after-model-delay.png"))
        after_visible = visible_preview_state(page)
        delta = float(after_delay["task_time_ms"]) - float(before_delay["task_time_ms"])
        if mode == "live":
            if delta < 180 or before_image == after_image:
                raise AssertionError(f"live inference did not visibly advance: delta={delta}")
        else:
            if abs(delta) > 2 or before_image != after_image or before_visible != after_visible:
                raise AssertionError(f"paused inference changed the task: delta={delta}")
        if len({frame["sha256"] for frame in frames}) < 3:
            raise AssertionError(f"{mode} observation did not visibly span the preview")
        target_tolerance_ms = 45
        if any(
            abs(float(frame["capture_started_task_time_ms"]) - float(window_start["task_time_ms"]) - float(frame["target_elapsed_ms"])) > target_tolerance_ms
            for frame in frames
        ):
            raise AssertionError(f"{mode} observation frames missed their virtual-clock targets: {frames}")
        if errors:
            raise AssertionError(f"{mode} observation browser errors: {errors}")
        return {
            "difficulty": 4,
            "interaction": "full",
            "time_mode": mode,
            "challenge_id": state["challenge_id"],
            "world_fingerprint_without_identity": world_fingerprint(state),
            "observation_window_ms": window_ms,
            "frames_per_observation": frame_count,
            "observation_start_task_time_ms": window_start["task_time_ms"],
            "frame_target_tolerance_ms": target_tolerance_ms,
            "frames": frames,
            "after_observation_window": after_window,
            "before_model_delay": before_delay,
            "after_model_delay": after_delay,
            "model_delay_task_time_delta_ms": delta,
            "before_model_delay_image": f"{mode}-before-model-delay.png",
            "after_model_delay_image": f"{mode}-after-model-delay.png",
            "model_delay_images_equal": before_image == after_image,
            "before_model_delay_visible_state": before_visible,
            "after_model_delay_visible_state": after_visible,
        }
    finally:
        close_task(helper, process, context, page)


def main() -> None:
    args = parse_args()
    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    materializer = load_module("reload_temporal_materializer", MATERIALIZER)
    helper = load_module("reload_temporal_capture_helper", CAPTURE_HELPER)
    with tempfile.TemporaryDirectory(prefix="reload-temporal-evidence-") as temporary_name:
        work_root = Path(temporary_name)
        materializer.materialize_environment(ENV_ROOT, work_root / "materialized")
        tasks_root = work_root / "materialized" / ENV_ROOT.name / "tasks"
        l4_full = helper.controlled_task(tasks_root, 4, "full")
        l5_full = helper.controlled_task(tasks_root, 5, "full")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            previews = {
                "l4_full": capture_preview(browser, helper, task=l4_full, difficulty=4, work_root=work_root, out_dir=output / "previews"),
                "l5_full": capture_preview(browser, helper, task=l5_full, difficulty=5, work_root=work_root, out_dir=output / "previews"),
            }
            observations = {
                mode: capture_observation(browser, helper, task=l4_full, mode=mode, work_root=work_root, out_dir=output / "observations")
                for mode in ("live", "paused")
            }
            browser.close()
    if observations["live"]["world_fingerprint_without_identity"] != observations["paused"]["world_fingerprint_without_identity"]:
        raise AssertionError("live and paused observations did not use the same generated world")
    summary = {
        "environment": "reload_interruption_env",
        "capture_provenance": {
            "browser": "new headless Playwright Chromium process; a fresh browser context per capture",
            "server": "temporary state directories on 127.0.0.1 only",
            "observation_schedule": "six target screenshots scheduled against WeirdCaptchaTime.task_time_ms over the configured 800 ms observation window",
            "clock_control": "loopback /time-control resume and pause commands with time_control=1",
            "inference_delay_ms": 240,
        },
        "previews": previews,
        "observations": observations,
        "assertions": {
            "l4_preview_has_seven_visible_chronological_frames": len(previews["l4_full"]["frames"]) == 7,
            "l5_preview_has_nine_visible_chronological_frames": len(previews["l5_full"]["frames"]) == 9,
            "live_and_paused_observations_share_world": True,
            "each_mode_has_six_observation_frames": all(len(value["frames"]) == 6 for value in observations.values()),
            "each_observation_frame_reached_its_virtual_clock_target": all(
                all(
                    abs(float(frame["capture_started_task_time_ms"]) - float(observation["observation_start_task_time_ms"]) - float(frame["target_elapsed_ms"])) <= float(observation["frame_target_tolerance_ms"])
                    for frame in observation["frames"]
                )
                for observation in observations.values()
            ),
            "live_model_delay_advances_visible_task": observations["live"]["model_delay_images_equal"] is False and observations["live"]["model_delay_task_time_delta_ms"] >= 180,
            "paused_model_delay_freezes_visible_task": observations["paused"]["model_delay_images_equal"] is True and abs(observations["paused"]["model_delay_task_time_delta_ms"]) <= 2,
        },
    }
    write_json(output / "summary.json", summary)
    print(json.dumps({"ok": True, "output": str(output), "assertions": summary["assertions"]}, indent=2))


if __name__ == "__main__":
    main()
