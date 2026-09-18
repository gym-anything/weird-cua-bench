"""Exercise a real Sandweave desktop through the benchmark's public API.

Run only on a dedicated CPU allocation with a prepared SANDWEAVE_HOME.
This checks the harness, not model performance or puzzle solvability.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import tempfile
import time
from pathlib import Path

from gym_anything.api import from_config
from gym_anything.runtime.runners.registry import register_runner

from weird_captcha_gym.evaluation.codex_cli import WeirdCodexActionGateway
from weird_captcha_gym.evaluation.temporal_modes import TEMPORAL_MODES
from weird_captcha_gym.runner import WeirdCaptchaRunner


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--modes", nargs="+", choices=TEMPORAL_MODES, default=list(TEMPORAL_MODES))
    parser.add_argument("--use-cache", action="store_true")
    parser.add_argument("--recording", action="store_true")
    parser.add_argument("--stage-mounts", action="store_true", help="Copy runtime inputs to local storage, excluding Python bytecode caches")
    parser.add_argument("--connection-file", type=Path, help="Use already staged mounts from a CPU-node diagnostic")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    # Also allows this diagnostic to run from an uninstalled source checkout.
    register_runner("weird_captcha", WeirdCaptchaRunner, replace=True)
    env_dir = Path("weird_captcha_gym/environments/rotating_keyboard_env")
    staged = tempfile.TemporaryDirectory(prefix="wcb-sandweave-inputs-") if args.stage_mounts else None
    overrides = {}
    if args.connection_file:
        overrides["mounts"] = json.loads(args.connection_file.read_text())["mounts"]
    if staged:
        mounts = json.loads((env_dir / "env.json").read_text())["mounts"]
        for index, mount in enumerate(mounts):
            destination = Path(staged.name) / str(index)
            shutil.copytree(mount["source"], destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
            mount["source"] = str(destination)
        overrides["mounts"] = mounts
    results = []
    for mode in args.modes:
        live = mode != "paused"
        output = root / mode
        output.mkdir(parents=True, exist_ok=True)
        env = from_config(
            env_dir,
            "rotating_keyboard_d3_full_seed_0001",
            overrides={
                **overrides,
                "runner_options": {
                    "inner": "sandweave", "time_mode": "live" if live else "paused",
                    "start_paused": True, "frames_per_observation": 1 if live else 6,
                    "observation_window_ms": 0 if live else 800, "play_time_seconds": 0,
                },
                "recording": {"enable": args.recording, "output_dir": str(output)},
            },
            fast_io=True,
        )
        started = time.monotonic()
        print(f"START {mode}", flush=True)
        gateway = None
        try:
            initial = env.reset(seed=42, use_cache=args.use_cache, cache_level="pre_start")
            reset_seconds = time.monotonic() - started
            assert len(initial["frames"]) == (1 if live else 6), initial
            assert env.runner.inner.acks_input_delivery()
            session = env.get_session_info()
            episode_dir = Path(session.artifacts_dir)
            gateway = WeirdCodexActionGateway(
                env, (1920, 1080), 30, "smoke-only",
                temporal_mode=mode, timing_path=output / "gateway-timing.jsonl",
            )
            first = gateway.step_from_command('{"action":"screenshot"}')
            assert not first.get("error"), first
            before = env.runner.exec_capture("python3 /workspace/shared_scripts/time_control.py status")
            time.sleep(0.4)
            after = env.runner.exec_capture("python3 /workspace/shared_scripts/time_control.py status")
            clock_before, clock_after = json.loads(before.splitlines()[-1]), json.loads(after.splitlines()[-1])
            delta = clock_after["task_time_ms"] - clock_before["task_time_ms"]
            assert delta >= 200 if live else abs(delta) < 50, (mode, clock_before, clock_after)
            commands = [
                {"keyboard": {"keys_down": ["SHIFT"]}},
                {"keyboard": {"keys_up": ["SHIFT"]}},
                {"action": "left_click", "coordinate": [round(1270 / gateway.ratio_x), round(305 / gateway.ratio_y)]},
            ]
            responses = []
            for command in commands:
                response = gateway.step_from_command(json.dumps(command))
                assert not response.get("error"), response
                responses.append({k: v for k, v in response.items() if "b64" not in k})
            if mode == "live_timestamped_execution":
                target = responses[-1]["timing"]["current_time_s"] + 1.0
                response = gateway.step_from_command(json.dumps({
                    "actions": [{"mouse": {"left_click": [round(1270 / gateway.ratio_x), round(305 / gateway.ratio_y)]}}],
                    "execute_at_s": target,
                }))
                assert not response.get("error"), response
                assert response["timing"]["action_executed_at_s"] >= target - 0.01, response["timing"]
                responses.append({k: v for k, v in response.items() if "b64" not in k})
                target = response["timing"]["current_time_s"] + .25
                direct, _, _, _ = env.step([{"action": "scheduled_input", "execute_at_s": target,
                    "actions": [{"mouse": {"move": [100, 500]}}]}], settle_after_actions=False)
                assert direct["input_receipt"]["action_executed_at_s"] >= target
            env.runner.capture_screenshot(output / "final-desktop.png")
            results.append({
                "mode": mode, "reset_seconds": reset_seconds, "idle_task_time_delta_ms": delta,
                "episode_dir": str(episode_dir), "responses": responses,
                "initial_frame_count": len(initial["frames"]),
            })
        finally:
            if gateway is not None:
                gateway.stop()
            env.close()
        assert (episode_dir / "current_task.json").is_file(), episode_dir
        assert env.runner.inner._sandbox is None
        if args.recording:
            assert (episode_dir / "recording.mp4").stat().st_size > 0
            assert (episode_dir / "sandweave-recording" / "recording.json").is_file()
        (root / "results.json").write_text(json.dumps(results, indent=2) + "\n")
        print(f"PASS {mode}: reset={reset_seconds:.2f}s, idle clock delta={delta:.1f}ms", flush=True)
    if staged:
        staged.cleanup()


if __name__ == "__main__":
    main()
