#!/usr/bin/env python3
"""Capture literal Scroll-Cage observations through the production evaluator.

The evaluator guest is an isolated background environment.  It never attaches
to a user browser, desktop, profile, or foreground application.  The standard
production observation call supplies the live frames and ``obs.screen``
binding.  A second invocation of the same guest capture utility records the
paused model-inference hold at the same wall-clock schedule without advancing
task time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image
from gym_anything.api import from_config


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from weird_captcha_gym.realtime import RealTimeSettings, load_real_time_settings
from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment
from weird_captcha_gym.tools.run_realtime_evaluation import (
    _capture_observation,
    _guest_json,
    _task_time_ms,
    _time_command,
)


BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "moving_checkbox_evasive_button_env"
MECHANIC = "moving_checkbox_evasive_button"
TASK_ID = f"{MECHANIC}_d4_simplified_seed_0001"
SEED = 314159
EXPECTED_RESOLUTION = [1280, 720]
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ENVIRONMENT / "evidence_docs" / "authoritative_evaluator_literal_frames",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def copy_guest_json(env: Any, source: str, destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    env.runner.copy_from(source, str(destination))
    return read_json(destination)


def build_runtime_environment(temporary: Path, out_dir: Path) -> Path:
    materialized = temporary / "materialized"
    materialize_environment(ENVIRONMENT, materialized)
    runtime_benchmark = temporary / "weird_captcha_gym"
    runtime_environment = runtime_benchmark / "environments" / ENVIRONMENT.name
    runtime_environment.mkdir(parents=True)
    shutil.copytree(BENCHMARK / "shared_runtime", runtime_benchmark / "shared_runtime")
    shutil.copytree(materialized / ENVIRONMENT.name / "tasks", runtime_environment / "tasks")
    config = read_json(ENVIRONMENT / "env.json")
    config["recording"]["output_dir"] = str((out_dir / "raw_episodes_1280x720").resolve())
    for mount in config["mounts"]:
        if mount.get("target") == "/workspace/tasks":
            mount["source"] = str((runtime_environment / "tasks").resolve())
    (runtime_environment / "env.json").write_text(
        json.dumps(config, indent=2) + "\n",
        encoding="utf-8",
    )
    return runtime_environment


def publish_frames(
    *,
    frame_sources: list[dict[str, Any]],
    screen_source: str,
    output: Path,
    label: str,
    root: Path,
) -> dict[str, Any]:
    destination_dir = output / label
    destination_dir.mkdir(parents=True, exist_ok=True)
    frames: list[dict[str, Any]] = []
    for index, frame in enumerate(frame_sources):
        source = Path(str(frame["path"])).resolve()
        destination = destination_dir / f"frame-{index:03d}.png"
        shutil.copy2(source, destination)
        with Image.open(destination) as image:
            resolution = list(image.size)
        if resolution != EXPECTED_RESOLUTION:
            raise AssertionError(f"{label}: literal frame resolution {resolution}, expected {EXPECTED_RESOLUTION}")
        frames.append(
            {
                "path": relative(destination, root),
                "source_path": relative(source, root),
                "sha256": sha256(destination),
                "offset_ms": frame["offset_ms"],
                "target_offset_ms": frame["target_offset_ms"],
                "resolution": resolution,
            }
        )
    screen_path = Path(screen_source).resolve()
    if screen_path != Path(str(frame_sources[-1]["path"])).resolve():
        raise AssertionError(f"{label}: production obs.screen path is not the final frame path")
    if sha256(screen_path) != frames[-1]["sha256"]:
        raise AssertionError(f"{label}: production obs.screen hash differs from the final frame")
    return {
        "frames": frames,
        "screen": frames[-1]["path"],
        "screen_source_path": relative(screen_path, root),
        "screen_sha256": frames[-1]["sha256"],
        "screen_is_final_frame": True,
        "distinct_frame_hashes": len({frame["sha256"] for frame in frames}),
    }


def describe_production_observation(
    observation: dict[str, Any],
    *,
    output: Path,
    label: str,
    root: Path,
) -> dict[str, Any]:
    frames = list(observation.get("frames") or [])
    if len(frames) != 5:
        raise AssertionError(f"{label}: expected five production frames, got {len(frames)}")
    screen = observation.get("screen") or {}
    record = publish_frames(
        frame_sources=frames,
        screen_source=str(screen.get("path") or ""),
        output=output,
        label=label,
        root=root,
    )
    manifest = Path(str(observation.get("capture_manifest") or "")).resolve()
    copied_manifest = output / label / "guest-capture-manifest.json"
    shutil.copy2(manifest, copied_manifest)
    record.update(
        {
            "capture_manifest": relative(copied_manifest, root),
            "capture_manifest_source": relative(manifest, root),
            "time": observation["time"],
            "capture_source": "production run_realtime_evaluation._capture_observation",
        }
    )
    return record


def capture_paused_hold(
    env: Any,
    *,
    settings: RealTimeSettings,
    turn: int,
    label: str,
    output: Path,
    root: Path,
) -> dict[str, Any]:
    _time_command(env, "pause")
    before_task_ms = _task_time_ms(env)
    observation = _capture_observation(
        env,
        mode="paused",
        settings=settings,
        turn=turn,
        hold_paused=True,
    )
    after_task_ms = _task_time_ms(env)
    if abs(after_task_ms - before_task_ms) > 5:
        raise AssertionError(f"{label}: paused hold advanced task time {before_task_ms} -> {after_task_ms}")
    result = describe_production_observation(
        observation,
        output=output,
        label=label,
        root=root,
    )
    if result["distinct_frame_hashes"] != 1:
        raise AssertionError(f"{label}: paused frames are not byte-identical")
    result.update(
        {
            "capture_source": (
                "production run_realtime_evaluation._capture_observation "
                "with hold_paused=True"
            ),
            "task_time_before_ms": before_task_ms,
            "task_time_after_ms": after_task_ms,
            "task_time_delta_ms": round(after_task_ms - before_task_ms, 3),
            "configured_schedule_ms": settings.observation_window_ms,
            "configured_frame_count": settings.frames_per_observation,
        }
    )
    return result


def run_mode(mode: str, *, runtime_env: Path, output: Path, settings: RealTimeSettings) -> dict[str, Any]:
    env = from_config(str(runtime_env), task_id=TASK_ID, fast_io=False)
    env.env_spec.security.resolved_env.update(
        {
            "WEIRD_CAPTCHA_TIME_MODE": mode,
            "WEIRD_CAPTCHA_START_PAUSED": "1",
            "WEIRD_CAPTCHA_CHALLENGE_SEED": str(SEED),
            "SEED": str(SEED),
        }
    )
    try:
        env.reset(seed=SEED, use_cache=False, use_savevm=False)
        env.set_episode_limits(max_steps=4, timeout_sec=86400)
        _time_command(env, "wait-ready")
        if mode == "live":
            _time_command(env, "resume")
        public = copy_guest_json(env, "/tmp/weird_captcha_gym/public_state.json", output / mode / "public_state.json")
        current_task = copy_guest_json(env, "/tmp/weird_captcha_gym/current_task.json", output / mode / "current_task.json")
        condition = public.get("control_condition") or {}
        if condition.get("difficulty") != 4 or condition.get("interaction") != "simplified":
            raise AssertionError(f"{mode}: evaluator did not load L4 simplified: {condition}")

        initial = _capture_observation(env, mode=mode, settings=settings, turn=0)
        initial_record = describe_production_observation(
            initial,
            output=output,
            label=f"{mode}/production-initial-observation",
            root=output,
        )
        if mode == "live" and initial_record["distinct_frame_hashes"] < 2:
            raise AssertionError("live production observation did not show Scroll-Cage motion")

        paused_hold_before: dict[str, Any] | None = None
        paused_hold_after: dict[str, Any] | None = None
        if mode == "paused":
            paused_hold_before = capture_paused_hold(
                env,
                settings=settings,
                turn=1000,
                label="paused/hold-before-action",
                output=output,
                root=output,
            )

        if mode == "paused":
            _time_command(env, "resume")
        action_before = _task_time_ms(env)
        # The delivered observation is 1280x720, where the initial physical
        # checkbox is centered near (355, 543).  The evaluator guest accepts
        # native 1920x1080 input, so (532, 815) targets that same visible
        # checkbox.  This intentionally incomplete action makes fixed-step
        # repulsion inspectable without solving the puzzle.
        visible_action = [
            {"mouse": {"move": [532, 815]}},
            {"action": "wait", "time": 0.18},
        ]
        _ignored_obs, _reward, _done, action_info = env.step(
            visible_action,
            wait_between_actions=0.0,
        )
        action_after_execution = _task_time_ms(env)
        clock_after_action = _time_command(env, "settle-pause" if mode == "paused" else "status")
        if action_after_execution <= action_before:
            raise AssertionError(f"{mode}: visible pointer-field action did not advance task time")
        if mode == "paused":
            if clock_after_action.get("state") != "paused":
                raise AssertionError("paused action did not return to the shared paused state")
            paused_hold_after = capture_paused_hold(
                env,
                settings=settings,
                turn=1001,
                label="paused/hold-after-action",
                output=output,
                root=output,
            )
            if paused_hold_before is None or paused_hold_before["screen_sha256"] == paused_hold_after["screen_sha256"]:
                raise AssertionError("paused visible pointer action did not produce a visible physical change")

        post_action = _capture_observation(env, mode=mode, settings=settings, turn=1)
        post_action_record = describe_production_observation(
            post_action,
            output=output,
            label=f"{mode}/production-after-action-observation",
            root=output,
        )
        return {
            "mode": mode,
            "episode_dir": relative(Path(env.episode_dir), output),
            "task_id": TASK_ID,
            "seed": SEED,
            "task_seed": current_task.get("seed"),
            "challenge_id": public.get("challenge_id"),
            "mechanic_id": public.get("mechanic_id"),
            "controlled_condition": condition,
            "initial_production_observation": initial_record,
            "paused_model_inference_hold_before_action": paused_hold_before,
            "visible_action": {
                "purpose": "move the visible pointer-repulsion field onto the physical checkbox",
                "actions": visible_action,
                "action_result": action_info.get("action_result"),
                "task_time_before_ms": action_before,
                "task_time_after_execution_ms": action_after_execution,
                "task_time_delta_ms": round(action_after_execution - action_before, 3),
                "clock_after_action": clock_after_action,
            },
            "paused_model_inference_hold_after_action": paused_hold_after,
            "post_action_production_observation": post_action_record,
        }
    finally:
        env.close()


def main() -> None:
    args = parse_args()
    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    settings = load_real_time_settings(MECHANIC)
    if settings != RealTimeSettings(play_time_seconds=180, observation_window_ms=500, frames_per_observation=5):
        raise AssertionError(f"unexpected Scroll-Cage real-time settings: {settings}")
    with tempfile.TemporaryDirectory(prefix="scroll-cage-authoritative-evaluator-") as temporary_name:
        runtime_env = build_runtime_environment(Path(temporary_name), output)
        live = run_mode("live", runtime_env=runtime_env, output=output, settings=settings)
        paused = run_mode("paused", runtime_env=runtime_env, output=output, settings=settings)
    for key in ("task_id", "seed", "task_seed", "challenge_id", "mechanic_id", "controlled_condition"):
        if live[key] != paused[key]:
            raise AssertionError(f"live and paused authoritative runs disagree on {key}")
    summary = {
        "ok": True,
        "environment": ENVIRONMENT.name,
        "task_id": TASK_ID,
        "same_controlled_task_seed_interaction_and_world": True,
        "capture_function": "weird_captcha_gym.tools.run_realtime_evaluation._capture_observation",
        "paused_hold_capture_function": (
            "weird_captcha_gym.tools.run_realtime_evaluation._capture_observation "
            "with hold_paused=True"
        ),
        "model_observation_resolution": EXPECTED_RESOLUTION,
        "settings": settings.__dict__,
        "live": live,
        "paused": paused,
        "evidence_boundary": (
            "The evaluator guest and its loopback task server run in an isolated background environment. "
            "This is literal task-frame transport and time-control evidence, not a human or model capability result."
        ),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
