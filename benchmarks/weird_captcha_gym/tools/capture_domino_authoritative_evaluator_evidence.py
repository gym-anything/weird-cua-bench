#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

from gym_anything.api import from_config

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from benchmarks.weird_captcha_gym.realtime import RealTimeSettings
from benchmarks.weird_captcha_gym.tools.run_realtime_evaluation import (
    _capture_observation,
    _task_time_ms,
    _time_command,
)

ENV_ROOT = ROOT / "benchmarks" / "weird_captcha_gym" / "environments" / "domino_autopsy_env"
TASK_ID = "domino_autopsy_seed_0001"
SEED = 314159
SETTINGS = RealTimeSettings(
    play_time_seconds=180,
    observation_window_ms=1000,
    frames_per_observation=6,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Capture Domino Autopsy frames through the exact authoritative "
            "run_realtime_evaluation observation function."
        )
    )
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args()


def read_guest_json(env, source: str, destination: Path) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True)
    env.runner.copy_from(source, str(destination))
    return json.loads(destination.read_text(encoding="utf-8"))


def run_mode(mode: str, out_dir: Path) -> dict:
    mode_dir = out_dir / mode
    mode_dir.mkdir(parents=True, exist_ok=True)
    env = from_config(str(ENV_ROOT), task_id=TASK_ID, fast_io=False)
    env.env_spec.security.resolved_env.update({
        "WEIRD_CAPTCHA_TIME_MODE": mode,
        "WEIRD_CAPTCHA_START_PAUSED": "1",
        "WEIRD_CAPTCHA_CHALLENGE_SEED": str(SEED),
        "SEED": str(SEED),
    })
    try:
        env.reset(seed=SEED, use_cache=False, use_savevm=False)
        ready = _time_command(env, "wait-ready")
        if mode == "live":
            ready = _time_command(env, "resume")
        else:
            _time_command(env, "resume")
        activate_exit = env.runner.exec(
            'DISPLAY=:1 wmctrl -a "Weird CAPTCHA Gym"',
            use_pty=False,
        )
        if activate_exit != 0:
            raise RuntimeError(
                f"{mode}: browser window activation exited {activate_exit}"
            )
        env.runner.inject_action({"mouse": {"left_click": [1350, 735]}})
        time.sleep(0.05)
        if mode == "paused":
            _time_command(env, "pause")
        observation = _capture_observation(
            env,
            mode=mode,
            settings=SETTINGS,
            turn=0,
        )
        copied_frames = []
        for index, frame in enumerate(observation["frames"]):
            source = Path(frame["path"])
            destination = mode_dir / f"frame-{index:03d}.png"
            shutil.copy2(source, destination)
            copied_frames.append({
                "path": str(destination.relative_to(out_dir)),
                "offset_ms": frame["offset_ms"],
                "target_offset_ms": frame["target_offset_ms"],
                "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            })
        distinct_frames = len({frame["sha256"] for frame in copied_frames})
        if distinct_frames < 2:
            raise AssertionError(
                f"authoritative {mode} observation did not show changing physics"
            )

        public_state = read_guest_json(
            env,
            "/tmp/weird_captcha_gym/public_state.json",
            mode_dir / "public_state.json",
        )
        current_task = read_guest_json(
            env,
            "/tmp/weird_captcha_gym/current_task.json",
            mode_dir / "current_task.json",
        )
        expected_task_seed = f"{SEED}:refresh:1"
        if current_task.get("seed") != expected_task_seed:
            raise AssertionError(
                f"authoritative {mode} task seed was {current_task.get('seed')!r}, "
                f"expected {expected_task_seed!r}"
            )
        before = _task_time_ms(env)
        time.sleep(0.7)
        after = _task_time_ms(env)
        inference_delta = round(after - before, 3)
        if mode == "paused" and inference_delta > 5:
            raise AssertionError(f"authoritative paused inference advanced: {inference_delta}")
        if mode == "live" and inference_delta < 500:
            raise AssertionError(f"authoritative live inference did not advance: {inference_delta}")
        if observation["screen"]["path"] != observation["frames"][-1]["path"]:
            raise AssertionError("authoritative obs.screen is not the final chronological frame")
        return {
            "mode": mode,
            "episode_dir": str(env.episode_dir),
            "ready": ready,
            "observation": {
                "screen": copied_frames[-1]["path"],
                "frames": copied_frames,
                "time": observation["time"],
            },
            "inference_delay": {
                "wall_delay_ms": 700,
                "task_time_before_ms": before,
                "task_time_after_ms": after,
                "task_time_delta_ms": inference_delta,
            },
            "challenge_id": public_state["challenge_id"],
            "mechanic_id": public_state["mechanic_id"],
            "task_seed": current_task["seed"],
            "screen_is_final_frame": True,
            "visible_action": "runner pointer click on RUN PHYSICS",
            "distinct_frame_hashes": distinct_frames,
            "capture_function": (
                "benchmarks.weird_captcha_gym.tools.run_realtime_evaluation."
                "_capture_observation"
            ),
            "guest_capture_script": (
                "/workspace/shared_scripts/capture_observation_window.py"
            ),
        }
    finally:
        env.close()


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    live = run_mode("live", out_dir)
    paused = run_mode("paused", out_dir)
    if paused["challenge_id"] != live["challenge_id"]:
        raise AssertionError("authoritative live and paused runs generated different worlds")
    summary = {
        "ok": True,
        "same_generated_world": True,
        "settings": {
            "play_time_seconds": SETTINGS.play_time_seconds,
            "observation_window_ms": SETTINGS.observation_window_ms,
            "frames_per_observation": SETTINGS.frames_per_observation,
        },
        "paused": paused,
        "live": live,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
