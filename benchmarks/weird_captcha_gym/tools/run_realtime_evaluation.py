#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import shlex
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

import agents.agents as agent_registry
from gym_anything.api import from_config

from benchmarks.weird_captcha_gym.realtime import (
    RealTimeSettings,
    load_real_time_settings,
    mechanic_id_from_env_dir,
)


logger = logging.getLogger(__name__)

VISIBLE_UI_ONLY_RULE = (
    "Solve only from screenshots and visible controls in the task webpage. "
    "Do not use code, scripts, automation, Developer Tools, the console, debugger, "
    "inspector, network panel, source or DOM inspection, page-state inspection, a "
    "terminal, shell, Python, address-bar or URL changes, query edits, reload, "
    "navigation, browser extensions, external applications, or hidden-state access. "
    "Do not switch to unrelated tabs. A tab opened by a visible task control is allowed "
    "only when it is part of the task and only through its visible controls."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate Weird CUA Bench in live or paused time.")
    parser.add_argument("--env-dir", "--env_dir", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--agent-args", "--agent_args", required=True)
    parser.add_argument("--time-mode", choices=("live", "paused"), required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--steps", type=int)
    parser.add_argument("--use-cache", "--use_cache", action="store_true")
    parser.add_argument("--cache-level", "--cache_level", default="pre_start")
    parser.add_argument("--use-savevm", "--use_savevm", action="store_true")
    parser.add_argument("--play-time-seconds", type=int)
    parser.add_argument("--observation-window-ms", type=int)
    parser.add_argument("--frames-per-observation", type=int)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--request-timeout-seconds", type=int, default=120)
    parser.add_argument("--request-attempts", type=int, default=3)
    return parser


def _settings(args: argparse.Namespace) -> tuple[str, RealTimeSettings]:
    mechanic_id = mechanic_id_from_env_dir(args.env_dir)
    base = load_real_time_settings(mechanic_id)
    return mechanic_id, RealTimeSettings.from_dict({
        "play_time_seconds": args.play_time_seconds or base.play_time_seconds,
        "observation_window_ms": (
            base.observation_window_ms
            if args.observation_window_ms is None
            else args.observation_window_ms
        ),
        "frames_per_observation": (
            base.frames_per_observation
            if args.frames_per_observation is None
            else args.frames_per_observation
        ),
    })


def _guest_json(env, arguments: list[str]) -> dict:
    command = " ".join(shlex.quote(part) for part in arguments)
    output = env.runner.exec_capture(command)
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise RuntimeError(f"guest command returned no JSON object: {output}")


def _time_command(env, command: str) -> dict:
    return _guest_json(env, [
        "python3", "/workspace/shared_scripts/time_control.py", command, "--timeout", "30",
    ])


def _capture_observation(
    env,
    *,
    mode: str,
    settings: RealTimeSettings,
    turn: int,
) -> dict[str, Any]:
    guest_dir = f"/tmp/weird_cua_observations/turn-{turn:04d}"
    manifest = _guest_json(env, [
        "python3",
        "/workspace/shared_scripts/capture_observation_window.py",
        "--mode", mode,
        "--duration-ms", str(settings.observation_window_ms),
        "--frames", str(settings.frames_per_observation),
        "--output-dir", guest_dir,
    ])
    host_dir = Path(env.episode_dir) / "observations" / f"turn-{turn:04d}"
    host_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for index, frame in enumerate(manifest["frames"]):
        host_path = host_dir / f"frame-{index:03d}.png"
        env.runner.copy_from(frame["path"], str(host_path))
        frames.append({
            "path": str(host_path),
            "offset_ms": frame["offset_ms"],
            "target_offset_ms": frame["target_offset_ms"],
        })
    time_status = manifest["time_status"]
    return {
        "screen": {
            "path": frames[-1]["path"],
            "format": "png",
            "resolution": [1280, 720],
        },
        "frames": frames,
        "time": {
            "mode": mode,
            "task_time_ms": time_status.get("task_time_ms"),
            "observation_window_ms": settings.observation_window_ms,
            "frames_per_observation": settings.frames_per_observation,
        },
    }


def _task_time_ms(env) -> float:
    return float(_time_command(env, "status").get("task_time_ms") or 0)


def _write_record(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")


def _task_description(env, args: argparse.Namespace) -> str:
    description = env.task_spec.description if env.task_spec else ""
    if not description:
        task_path = Path(args.env_dir) / "tasks" / args.task / "task.json"
        description = json.loads(task_path.read_text(encoding="utf-8")).get("description", "")
    return f"{description}\n\n{VISIBLE_UI_ONLY_RULE}"


def _mark_done(env, *, reason: str) -> tuple[dict, float, bool, dict]:
    obs, reward, done, info = env.step(
        [],
        mark_done=True,
        capture_observation=False,
        settle_after_actions=False,
    )
    info["benchmark_reason"] = reason
    return obs, reward, done, info


def run(args: argparse.Namespace) -> int:
    mechanic_id, settings = _settings(args)
    agent_args = json.loads(args.agent_args)
    agent_args.setdefault("request_timeout_seconds", args.request_timeout_seconds)
    agent_args.setdefault("request_attempts", args.request_attempts)

    env = from_config(args.env_dir, task_id=args.task, fast_io=False)
    env.env_spec.security.resolved_env.update({
        "WEIRD_CAPTCHA_TIME_MODE": args.time_mode,
        "WEIRD_CAPTCHA_START_PAUSED": "1",
    })
    info: dict[str, Any] = {}
    agent = None
    episode_dir = None
    try:
        env.reset(
            seed=args.seed,
            use_cache=args.use_cache,
            cache_level=args.cache_level,
            use_savevm=args.use_savevm,
        )
        max_steps = args.steps or env.max_steps or 50
        env.set_episode_limits(max_steps=max_steps + 1, timeout_sec=86400)
        episode_dir = Path(env.episode_dir)
        timing_path = episode_dir / "realtime_timing.jsonl"

        ready = _time_command(env, "wait-ready")

        agent_cls = getattr(agent_registry, args.agent)
        agent = agent_cls(agent_args=agent_args, verbose=args.verbose, debug=args.debug)
        if getattr(agent, "autonomous", False):
            raise ValueError("the real-time evaluator requires turn-based agent.step observations")
        description = _task_description(env, args)
        agent.init(
            task_description=description,
            display_resolution=env.env_spec.observation[0].resolution,
            save_path=env.episode_dir,
        )
        if args.time_mode == "live":
            ready = _time_command(env, "resume")
        _write_record(timing_path, {
            "event": "setup",
            "mechanic_id": mechanic_id,
            "time_mode": args.time_mode,
            "settings": settings.__dict__,
            "clock": ready,
            "request_timeout_seconds": args.request_timeout_seconds,
            "request_attempts": args.request_attempts,
        })

        action_outputs = []
        obs = _capture_observation(env, mode=args.time_mode, settings=settings, turn=0)
        turn = 0
        model_turn = 0
        reason = "step_limit"
        done = False

        while turn < max_steps and model_turn < max_steps and not done:
            before_model_ms = _task_time_ms(env)
            if before_model_ms >= settings.play_time_seconds * 1000:
                reason = "play_time_limit"
                break

            model_started = time.perf_counter()
            actions = agent.step(obs, action_outputs)
            model_turn += 1
            model_ms = (time.perf_counter() - model_started) * 1000
            after_model_ms = _task_time_ms(env)
            action_outputs = []
            action_records = []

            if args.time_mode == "live" and after_model_ms >= settings.play_time_seconds * 1000:
                reason = "play_time_limit"
                _write_record(timing_path, {
                    "event": "turn",
                    "turn": turn,
                    "model_ms": model_ms,
                    "task_time_before_model_ms": before_model_ms,
                    "task_time_after_model_ms": after_model_ms,
                    "actions_applied": 0,
                    "stopped_before_action": True,
                })
                break

            for group in actions:
                actual_actions = group["actions"]
                if args.time_mode == "paused":
                    _time_command(env, "resume")
                action_started = time.perf_counter()
                try:
                    _ignored_obs, _reward, done, info = env.step(
                        actual_actions,
                        wait_between_actions=0.0,
                        capture_observation=False,
                        settle_after_actions=False,
                    )
                finally:
                    if args.time_mode == "paused":
                        _time_command(env, "pause")
                action_ms = (time.perf_counter() - action_started) * 1000

                turn += 1
                obs = _capture_observation(env, mode=args.time_mode, settings=settings, turn=turn)
                action_result = info.get("action_result", {"action": "other", "output": "Executed the action"})
                if action_result.get("action") == "screenshot":
                    action_result["output"] = obs["screen"]["path"]
                action_outputs.append({**action_result, "tool_id": group.get("tool_id"), "obs": obs})
                action_records.append({
                    "tool_id": group.get("tool_id"),
                    "action_count": len(actual_actions),
                    "action_ms": action_ms,
                    "task_time_ms": obs["time"]["task_time_ms"],
                })
                task_time_ms = float(obs["time"]["task_time_ms"] or 0)
                if done or turn >= max_steps or task_time_ms >= settings.play_time_seconds * 1000:
                    if task_time_ms >= settings.play_time_seconds * 1000:
                        reason = "play_time_limit"
                    break

            _write_record(timing_path, {
                "event": "turn",
                "turn": turn,
                "model_ms": model_ms,
                "task_time_before_model_ms": before_model_ms,
                "task_time_after_model_ms": after_model_ms,
                "actions": action_records,
            })
            if getattr(agent, "done", False):
                reason = "agent_completed"
                break

        _, _reward, done, info = _mark_done(env, reason=reason)
        logger.info("Episode finished: %s", info)
    finally:
        if episode_dir is None and env.episode_dir:
            episode_dir = Path(env.episode_dir)
        env.close()

    if agent is not None:
        agent.finish(info=info)
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
