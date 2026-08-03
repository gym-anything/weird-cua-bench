#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from contextlib import contextmanager
from http.client import RemoteDisconnected
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

import agents.agents as agent_registry

from benchmarks.weird_captcha_gym.evaluation import (
    WeirdRemoteGymEnv,
    control_for_environment,
)
from benchmarks.weird_captcha_gym.evaluation.control import EvaluationControl
from benchmarks.weird_captcha_gym.evaluation.qwen35vl import WeirdQwen35VLAgent
from benchmarks.weird_captcha_gym.realtime import (
    RealTimeSettings,
    load_real_time_settings,
    mechanic_id_from_env_dir,
)
from benchmarks.weird_captcha_gym.tools.authoritative_observation_probe_agent import (
    AuthoritativeObservationProbeAgent,
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
    parser.add_argument("--fast-io", "--fast_io", action="store_true")
    parser.add_argument("--remote-url", "--remote_url")
    parser.add_argument("--remote-timeout", "--remote_timeout", type=int, default=300)
    parser.add_argument(
        "--remote-worker-reset-policy",
        "--remote_worker_reset_policy",
        choices=("core", "baseline_setup"),
        default="core",
    )
    parser.add_argument("--play-time-seconds", type=int)
    parser.add_argument("--observation-window-ms", type=int)
    parser.add_argument("--frames-per-observation", type=int)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--request-timeout-seconds", type=float, default=120)
    parser.add_argument("--request-attempts", type=int, default=3)
    parser.add_argument("--episode-summary-path", type=Path)
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


def _time_command(env, command: str) -> dict:
    return control_for_environment(env).time(command)


def _capture_observation(
    env,
    *,
    mode: str,
    settings: RealTimeSettings,
    turn: int,
    hold_paused: bool = False,
) -> dict[str, Any]:
    """Capture the evaluator's literal observation frames.

    ``hold_paused`` is an opt-in evidence/probe mode.  It preserves the normal
    paused evaluator behavior (a scheduled observation window that advances
    the task) by default, while allowing an evaluator caller to record the
    same scheduled frame sequence during the subsequent frozen model-inference
    hold.
    """
    return control_for_environment(env).capture(
        mode=mode,
        duration_ms=settings.observation_window_ms,
        frames_per_observation=settings.frames_per_observation,
        turn=turn,
        hold_paused=hold_paused,
    )


def _task_time_ms(env) -> float:
    return float(_time_command(env, "status").get("task_time_ms") or 0)


def _write_record(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")


class _ModelRequestDeadline(TimeoutError):
    pass


@contextmanager
def _request_deadline(seconds: float):
    if seconds <= 0:
        raise ValueError("request timeout must be positive")
    if not hasattr(signal, "setitimer"):
        yield
        return
    prior_handler = signal.getsignal(signal.SIGALRM)

    def expired(_signum, _frame):
        raise _ModelRequestDeadline(
            f"model request exceeded the evaluator deadline of {seconds:g}s"
        )

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, prior_handler)


def _http_status(error: BaseException) -> int | None:
    for candidate in (
        getattr(error, "status_code", None),
        getattr(error, "status", None),
        getattr(getattr(error, "response", None), "status_code", None),
    ):
        try:
            return int(candidate)
        except (TypeError, ValueError):
            continue
    return None


def _retryable_request_error(error: BaseException) -> bool:
    if isinstance(
        error,
        (
            TimeoutError,
            ConnectionError,
            RemoteDisconnected,
            BrokenPipeError,
            ConnectionResetError,
        ),
    ):
        return True
    status = _http_status(error)
    return status in {408, 429} or (
        status is not None and 500 <= status <= 599
    )


def _call_agent_with_retry(
    env,
    agent,
    obs: dict[str, Any],
    action_outputs: list[dict[str, Any]],
    *,
    timeout_seconds: float,
    attempts: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if attempts < 1:
        raise ValueError("request attempts must be positive")
    records = []
    for attempt in range(1, attempts + 1):
        before_task_ms = _task_time_ms(env)
        started = time.perf_counter()
        try:
            with _request_deadline(timeout_seconds):
                actions = agent.step(obs, action_outputs)
        except Exception as error:
            elapsed_ms = (time.perf_counter() - started) * 1000
            after_task_ms = _task_time_ms(env)
            retryable = _retryable_request_error(error)
            records.append(
                {
                    "attempt": attempt,
                    "outcome": "error",
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "retryable": retryable,
                    "wall_ms": elapsed_ms,
                    "task_time_before_request_ms": before_task_ms,
                    "task_time_after_request_ms": after_task_ms,
                    "task_time_delta_ms": after_task_ms - before_task_ms,
                }
            )
            if not retryable or attempt == attempts:
                raise
            continue
        elapsed_ms = (time.perf_counter() - started) * 1000
        after_task_ms = _task_time_ms(env)
        records.append(
            {
                "attempt": attempt,
                "outcome": "success",
                "retryable": False,
                "wall_ms": elapsed_ms,
                "task_time_before_request_ms": before_task_ms,
                "task_time_after_request_ms": after_task_ms,
                "task_time_delta_ms": after_task_ms - before_task_ms,
            }
        )
        return actions, records
    raise AssertionError("request loop ended without returning or raising")


def _task_description(env, args: argparse.Namespace) -> str:
    task_spec = env.task_spec
    description = task_spec.natural_language if task_spec else ""
    if not isinstance(description, str) or not description.strip():
        description = task_spec.description if task_spec else ""
    if not isinstance(description, str) or not description.strip():
        task_path = Path(args.env_dir) / "tasks" / args.task / "task.json"
        task = json.loads(task_path.read_text(encoding="utf-8"))
        description = task.get("natural_language") or task.get("description", "")
    return f"{description}\n\n{VISIBLE_UI_ONLY_RULE}"


def _mark_done(env, *, reason: str) -> tuple[dict, float, bool, dict]:
    obs, reward, done, info = env.step([], mark_done=True)
    info["benchmark_reason"] = reason
    return obs, reward, done, info


def _make_env(args: argparse.Namespace):
    if not args.remote_url:
        from gym_anything.api import from_config

        return from_config(args.env_dir, task_id=args.task, fast_io=args.fast_io)
    return WeirdRemoteGymEnv.from_config(
        remote_url=args.remote_url,
        env_dir=args.env_dir,
        task_id=args.task,
        timeout=args.remote_timeout,
        worker_reset_policy=args.remote_worker_reset_policy,
        fast_io=args.fast_io,
    )


def run(args: argparse.Namespace) -> int:
    mechanic_id, settings = _settings(args)
    agent_args = json.loads(args.agent_args)
    agent_args.setdefault("request_timeout_seconds", args.request_timeout_seconds)
    agent_args.setdefault("request_attempts", args.request_attempts)

    env = _make_env(args)
    control: EvaluationControl = control_for_environment(env)
    info: dict[str, Any] = {}
    agent = None
    episode_dir = None
    try:
        control.configure({
            "WEIRD_CAPTCHA_TIME_MODE": args.time_mode,
            "WEIRD_CAPTCHA_START_PAUSED": "1",
            "WEIRD_CAPTCHA_CHALLENGE_SEED": str(args.seed),
            "SEED": str(args.seed),
        })
        env.reset(
            seed=args.seed,
            use_cache=args.use_cache,
            cache_level=args.cache_level,
            use_savevm=args.use_savevm,
        )
        max_steps = args.steps or env.max_steps or 50
        env.set_episode_limits(max_steps=max_steps + 1, timeout_sec=86400)
        episode_dir = control.artifacts_dir
        timing_path = episode_dir / "realtime_timing.jsonl"

        ready = _time_command(env, "wait-ready")

        if args.agent == "AuthoritativeObservationProbeAgent":
            agent_cls = AuthoritativeObservationProbeAgent
        elif args.agent in {"Qwen35VLAgent", "WeirdQwen35VLAgent"}:
            agent_cls = WeirdQwen35VLAgent
        else:
            agent_cls = getattr(agent_registry, args.agent)
        agent = agent_cls(agent_args=agent_args, verbose=args.verbose, debug=args.debug)
        if getattr(agent, "autonomous", False):
            raise ValueError("the real-time evaluator requires turn-based agent.step observations")
        description = _task_description(env, args)
        agent.init(
            task_description=description,
            display_resolution=env.env_spec.observation[0].resolution,
            save_path=episode_dir,
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
            "fast_io": args.fast_io,
            "remote_url": args.remote_url,
            "request_retry_policy": {
                "single_layer": True,
                "total_attempt_limit": args.request_attempts,
                "retryable": [
                    "timeouts",
                    "connection/read/write errors",
                    "server disconnects and protocol errors",
                    "HTTP 408",
                    "HTTP 429",
                    "HTTP 5xx",
                ],
                "not_retryable": [
                    "safety blocks",
                    "authentication or authorization failures",
                    "invalid requests",
                ],
                "failed_attempts_consume_environment_steps": False,
            },
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
            actions, request_records = _call_agent_with_retry(
                env,
                agent,
                obs,
                action_outputs,
                timeout_seconds=args.request_timeout_seconds,
                attempts=args.request_attempts,
            )
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
                    "request_attempts": request_records,
                })
                break

            for group in actions:
                actual_actions = group["actions"]
                if args.time_mode == "paused":
                    _time_command(env, "resume")
                task_time_before_action_ms = _task_time_ms(env)
                action_started = time.perf_counter()
                try:
                    _ignored_obs, _reward, done, info = env.step(
                        actual_actions,
                        wait_between_actions=0.0,
                    )
                    task_time_after_execution_ms = _task_time_ms(env)
                finally:
                    if args.time_mode == "paused":
                        # A task may have an accepted finite transition (for
                        # example, a room rotation) still in flight.  The
                        # shared controller pauses only after such registered
                        # actions settle, so the next evaluator turn cannot
                        # silently lose its input to a frozen action lock.
                        clock_after_action = _time_command(env, "settle-pause")
                    else:
                        clock_after_action = _time_command(env, "status")
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
                    "task_time_before_action_ms": task_time_before_action_ms,
                    "task_time_after_execution_ms": task_time_after_execution_ms,
                    "task_time_delta_during_action_ms": (
                        task_time_after_execution_ms
                        - task_time_before_action_ms
                    ),
                    "clock_after_action": clock_after_action,
                    "task_time_ms": obs["time"]["task_time_ms"],
                    "following_observation_manifest": obs[
                        "capture_manifest"
                    ],
                    "following_observation_screen": obs["screen"]["path"],
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
                "request_attempts": request_records,
                "actions": action_records,
            })
            if getattr(agent, "done", False):
                reason = "agent_completed"
                break

        _, _reward, done, info = _mark_done(env, reason=reason)
        logger.info("Episode finished: %s", info)
    finally:
        if episode_dir is None and env.episode_dir:
            episode_dir = control.artifacts_dir
        if episode_dir is not None:
            try:
                control.collect_artifacts()
            except Exception as error:
                logger.warning("Could not collect Weird CUA artifacts: %s", error)
            if args.episode_summary_path is not None:
                args.episode_summary_path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                args.episode_summary_path.write_text(
                    json.dumps(
                        {
                            "episode_dir": str(episode_dir),
                            "mechanic_id": mechanic_id,
                            "task": args.task,
                            "seed": args.seed,
                            "time_mode": args.time_mode,
                            "info": info,
                        },
                        indent=2,
                        default=str,
                    ),
                    encoding="utf-8",
                )
        env.close()

    if agent is not None:
        agent.finish(info=info)
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
