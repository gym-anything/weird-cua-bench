#!/usr/bin/env python3
"""Capture baseline and real-time evidence for Live Shattered-Scene Synchronizer.

The capture is deliberately local-only: each task is served from a temporary
state directory and each browser page is opened in a fresh, headless Playwright
context.  It records the historical L4/full world beside its controlled pair,
then records the six-frame configured observation in live and paused modes.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path
from typing import Any

from playwright.sync_api import expect, sync_playwright

from smoke_controlled_interaction_ui import (
    BENCH_ROOT,
    controlled_task,
    observation_viewport,
    read_json,
    start_server,
)


ROOT = Path(__file__).resolve().parents[2]
ENV_ROOT = BENCH_ROOT / "environments" / "single_scene_split_boxes_env"
MECHANIC = "single_scene_split_boxes"
MATERIALIZER_PATH = BENCH_ROOT / "tools" / "materialize_controlled_tasks.py"
HISTORICAL_FIXTURE = ENV_ROOT / "historical_l4_baseline_fixture.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def without_identity(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        result.pop(key, None)
    return result


def fingerprint(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(without_identity(value), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def stop(process) -> None:
    process.terminate()
    try:
        process.wait(timeout=3)
    except Exception:
        process.kill()


def open_task(browser, *, task: Path, interaction: str, state_dir: Path, mode: str):
    process, port = start_server(task, MECHANIC, interaction, state_dir)
    context = browser.new_context(viewport=observation_viewport(ENV_ROOT), device_scale_factor=1)
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    # Keep the setup-generated seed on the first browser state request. The
    # server otherwise treats the current-task descriptor as a new launch.
    current_task = state_dir / "current_task.json"
    current_task_text = current_task.read_text(encoding="utf-8")
    current_task.unlink()
    try:
        page.goto(
            f"http://127.0.0.1:{port}/?time_mode={mode}&start_paused=1",
            wait_until="networkidle",
        )
    finally:
        current_task.write_text(current_task_text, encoding="utf-8")
    expect(page.locator('.mosaic-captcha[data-interaction]')).to_be_visible()
    return process, context, page, errors


def capture_baseline(
    browser,
    *,
    original_task: Path,
    controlled_l4: Path,
    historical_fixture: dict[str, Any],
    work_root: Path,
    out_dir: Path,
) -> dict[str, Any]:
    historical_by_seed = {str(record["seed"]): record for record in historical_fixture["seeds"]}
    entries: dict[str, dict[str, Any]] = {}
    for label, task, controlled in (
        ("original-uncontrolled-l4-full", original_task, False),
        ("controlled-d4-full", controlled_l4, True),
    ):
        state_dir = work_root / label
        state_dir.mkdir()
        process, context, page, errors = open_task(
            browser,
            task=task,
            interaction="full",
            state_dir=state_dir,
            mode="live",
        )
        try:
            page.evaluate("() => WeirdCaptchaTime.resume()")
            page.wait_for_timeout(120)
            page.screenshot(path=str(out_dir / f"{label}.png"))
            public = read_json(state_dir / "public_state.json")
            truth = read_json(state_dir / "ground_truth.json")
            launch = read_json(state_dir / "current_task.json")
            browser_seed = str(launch.get("seed") or "")
            historical = historical_by_seed.get(browser_seed)
            if historical is None:
                raise AssertionError(f"no locked historical record for browser seed {browser_seed!r}")
            if errors:
                raise AssertionError(f"{label} browser errors: {errors}")
            entries[label] = {
                "screenshot": f"{label}.png",
                "challenge_id": public["challenge_id"],
                "public_world_fingerprint_without_identity": fingerprint(public),
                "truth_world_fingerprint_without_identity": fingerprint(truth),
                "historical_public_world_fingerprint_without_identity": fingerprint(historical["public_state"]),
                "historical_truth_world_fingerprint_without_identity": fingerprint(historical["ground_truth"]),
                "historical_fixture_seed": browser_seed,
                "public_matches_historical_fixture": without_identity(public) == without_identity(historical["public_state"]),
                "truth_matches_historical_fixture": without_identity(truth) == without_identity(historical["ground_truth"]),
                "dimensions_present": public["scene"].get("rows") == public["scene"].get("columns") == 3,
                "control_condition": public.get("control_condition"),
                "visible_grid": page.locator(".mosaic-grid").evaluate("node => getComputedStyle(node).gridTemplateColumns"),
            }
        finally:
            page.close()
            context.close()
            stop(process)
    original = entries["original-uncontrolled-l4-full"]
    controlled = entries["controlled-d4-full"]
    if original["public_world_fingerprint_without_identity"] != controlled["public_world_fingerprint_without_identity"]:
        raise AssertionError("controlled L4 did not preserve the original generated public world")
    if original["truth_world_fingerprint_without_identity"] != controlled["truth_world_fingerprint_without_identity"]:
        raise AssertionError("controlled L4 did not preserve the original generated truth")
    if not all(
        entry["public_matches_historical_fixture"]
        and entry["truth_matches_historical_fixture"]
        and entry["dimensions_present"]
        for entry in entries.values()
    ):
        raise AssertionError("browser baseline state no longer matches the locked historical fixture")
    entries["historical_fixture"] = {
        "path": str(HISTORICAL_FIXTURE.relative_to(ROOT)),
        "sha256": hashlib.sha256(HISTORICAL_FIXTURE.read_bytes()).hexdigest(),
        "historical_revision": historical_fixture["historical_revision"],
        "identity_fields_removed_for_comparison": historical_fixture["identity_fields_removed_for_comparison"],
    }
    return entries


def capture_observation_mode(browser, *, task: Path, mode: str, work_root: Path, out_dir: Path) -> dict[str, Any]:
    state_dir = work_root / f"realtime-{mode}"
    state_dir.mkdir()
    process, context, page, errors = open_task(
        browser,
        task=task,
        interaction="full",
        state_dir=state_dir,
        mode=mode,
    )
    try:
        state = read_json(state_dir / "public_state.json")
        window_ms = int(state["control_condition"]["difficulty_parameters"].get("observation_window_ms", 640))
        frame_count = 6
        # Start the observation window. Both modes advance during collection.
        page.evaluate("() => WeirdCaptchaTime.resume()")
        frames: list[dict[str, Any]] = []
        prior_target = 0.0
        for number in range(1, frame_count + 1):
            target = window_ms * (number - 1) / (frame_count - 1)
            if target > prior_target:
                page.wait_for_timeout(target - prior_target)
            path = out_dir / f"{mode}-observation-frame-{number:03d}.png"
            image = page.screenshot(path=str(path))
            frames.append(
                {
                    "frame": number,
                    "target_elapsed_ms": target,
                    "task_time_ms": page.evaluate("() => WeirdCaptchaTime.status().task_time_ms"),
                    "image": path.name,
                    "sha256": hashlib.sha256(image).hexdigest(),
                }
            )
            prior_target = target
        if mode == "paused":
            page.evaluate("() => WeirdCaptchaTime.pause()")
        after_window = page.evaluate("() => WeirdCaptchaTime.status()")
        before_delay = page.evaluate("() => WeirdCaptchaTime.status()")
        before_path = out_dir / f"{mode}-before-model-delay.png"
        before_image = page.screenshot(path=str(before_path))
        page.wait_for_timeout(700)
        after_delay = page.evaluate("() => WeirdCaptchaTime.status()")
        after_path = out_dir / f"{mode}-after-model-delay.png"
        after_image = page.screenshot(path=str(after_path))
        delay_delta = float(after_delay["task_time_ms"]) - float(before_delay["task_time_ms"])
        if mode == "live" and delay_delta < 620:
            raise AssertionError(f"live task time did not advance through model delay: {delay_delta}")
        if mode == "paused" and abs(delay_delta) > 2:
            raise AssertionError(f"paused task time advanced through model delay: {delay_delta}")
        if mode == "paused":
            action_before = page.evaluate("() => WeirdCaptchaTime.status()")
            page.evaluate("() => WeirdCaptchaTime.resume()")
        else:
            action_before = page.evaluate("() => WeirdCaptchaTime.status()")
        page.locator(".mosaic-tile").nth(1).click()
        page.wait_for_timeout(80)
        if mode == "paused":
            page.evaluate("() => WeirdCaptchaTime.pause()")
        action_after = page.evaluate("() => WeirdCaptchaTime.status()")
        action_path = out_dir / f"{mode}-resumed-pointer-action.png"
        page.screenshot(path=str(action_path))
        if action_after["task_time_ms"] <= action_before["task_time_ms"]:
            raise AssertionError(f"{mode} task did not advance while its visible action was applied")
        if errors:
            raise AssertionError(f"{mode} browser errors: {errors}")
        return {
            "challenge_id": state["challenge_id"],
            "public_world_fingerprint_without_identity": fingerprint(state),
            "window_ms": window_ms,
            "frame_count": frame_count,
            "frames": frames,
            "after_observation_window": after_window,
            "before_model_delay": before_delay,
            "after_model_delay": after_delay,
            "model_delay_task_time_delta_ms": delay_delta,
            "before_model_delay_image": before_path.name,
            "after_model_delay_image": after_path.name,
            "model_delay_images_equal": before_image == after_image,
            "action_before": action_before,
            "action_after": action_after,
            "action_task_time_delta_ms": float(action_after["task_time_ms"]) - float(action_before["task_time_ms"]),
            "resumed_pointer_action_image": action_path.name,
        }
    finally:
        page.close()
        context.close()
        stop(process)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ENV_ROOT / "evidence_docs")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    materializer = load_module("split_boxes_evidence_materializer", MATERIALIZER_PATH)
    historical_fixture = read_json(HISTORICAL_FIXTURE)
    original_task = ENV_ROOT / "tasks" / "single_scene_split_boxes_seed_0001" / "task.json"
    with tempfile.TemporaryDirectory(prefix="split-boxes-evidence-") as temporary_name:
        temporary = Path(temporary_name)
        materializer.materialize_environment(ENV_ROOT, temporary / "materialized")
        tasks = temporary / "materialized" / ENV_ROOT.name / "tasks"
        controlled_l4 = controlled_task(tasks, 4, "full")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            baseline = capture_baseline(
                browser,
                original_task=original_task,
                controlled_l4=controlled_l4,
                historical_fixture=historical_fixture,
                work_root=temporary,
                out_dir=args.out_dir / "baseline",
            )
            realtime = {
                mode: capture_observation_mode(
                    browser,
                    task=controlled_l4,
                    mode=mode,
                    work_root=temporary,
                    out_dir=args.out_dir / "realtime_observations",
                )
                for mode in ("live", "paused")
            }
            browser.close()
    if realtime["live"]["public_world_fingerprint_without_identity"] != realtime["paused"]["public_world_fingerprint_without_identity"]:
        raise AssertionError("live and paused captures did not use one generated world")
    write_json(args.out_dir / "baseline" / "baseline-preservation.json", baseline)
    write_json(args.out_dir / "realtime_observations" / "summary.json", {"baseline_task": controlled_l4.parent.name, "modes": realtime})
    print(json.dumps({"baseline": baseline, "realtime": realtime}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
