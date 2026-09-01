"""Weird CUA's Codex CLI temporal adapter over Gym-Anything's CLI harness."""

from __future__ import annotations

import json
import logging
import math
import secrets
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from agents.agents.codex_cli import CodexCliAgent
from agents.shared.agent_sandbox import select_sandbox
from agents.shared.cli_harness import ActionGateway, build_harness_prompt

from weird_captcha_gym.evaluation.temporal_modes import (
    episode_clock_origin_ms,
    timestamps_enabled,
    validate_temporal_mode,
)

logger = logging.getLogger(__name__)


class WeirdCodexActionGateway(ActionGateway):
    """Bind Codex timing to the Weird episode clock and persist every event."""

    def __init__(
        self,
        *args: Any,
        timing_path: Path,
        temporal_mode: str = "live",
        **kwargs: Any,
    ) -> None:
        # Gym-Anything releases predating the temporal gateway do not accept a
        # temporal_mode keyword.  Weird owns that policy, so retain it here
        # instead of relying on an optional upstream constructor extension.
        super().__init__(*args, **kwargs)
        self.temporal_mode = validate_temporal_mode(temporal_mode)
        self._timing_path = timing_path
        self._timing_path.parent.mkdir(parents=True, exist_ok=True)
        self._timing_write_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._next_request_index = 0
        self._t0_ms: float | None = None

    @staticmethod
    def _frame_wall_ms(obs: dict[str, Any]) -> float | None:
        manifest_path = obs.get("capture_manifest")
        if not manifest_path:
            return None
        try:
            manifest = json.loads(Path(str(manifest_path)).read_text(encoding="utf-8"))
            frames = list(manifest.get("frames") or [])
            if not frames:
                return None
            return float(manifest["window_started_wall_ms"]) + float(
                frames[-1].get("offset_ms") or 0
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _timing_payload(
        self,
        obs: dict[str, Any],
        *,
        action_receipt: dict[str, float | None] | None,
        capture_finished_wall_ms: float,
    ) -> dict[str, Any] | None:
        if not timestamps_enabled(self.temporal_mode):
            return None
        if self._t0_ms is None:
            self._t0_ms = episode_clock_origin_ms(obs)
        frame_wall_ms = self._frame_wall_ms(obs)
        if frame_wall_ms is None:
            frame_wall_ms = capture_finished_wall_ms
        payload: dict[str, Any] = {
            "frame_captured_at_s": round((frame_wall_ms - self._t0_ms) / 1000, 6),
            "current_time_s": round((capture_finished_wall_ms - self._t0_ms) / 1000, 6),
        }
        if action_receipt:
            executed_wall_ms = action_receipt.get("executed_wall_ms")
            if executed_wall_ms is not None:
                payload["action_executed_at_s"] = round(
                    (float(executed_wall_ms) - self._t0_ms) / 1000,
                    6,
                )
            requested_s = action_receipt.get("requested_execute_at_s")
            if requested_s is not None:
                requested_s = float(requested_s)
                if math.isfinite(requested_s):
                    payload["previous_action_requested_execute_at_s"] = requested_s
                    if payload.get("action_executed_at_s") is not None:
                        payload["action_execution_lateness_s"] = round(
                            float(payload["action_executed_at_s"]) - requested_s,
                            6,
                        )
        return payload

    def _capture_with_timing(
        self,
        *,
        action_receipt: dict[str, float | None] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        obs = self.env.capture_observation()
        finished_wall_ms = time.time_ns() / 1_000_000
        timing = self._timing_payload(
            obs,
            action_receipt=action_receipt,
            capture_finished_wall_ms=finished_wall_ms,
        )
        return obs, timing

    def _env_actions_for(
        self,
        command: str,
    ) -> tuple[list[dict[str, Any]], bool, str | None]:
        """Expand CLI drag shorthand into one sampled native-input batch.

        Gym-Anything's generic parser emits ``left_click_drag`` as one opaque
        mouse action. The Weird runner's trusted Chromium receipt and Full
        interaction telemetry need the pointer down, sampled travel, and
        pointer up to cross one input barrier together. Clicks and all other
        actions keep the upstream representation unchanged.
        """
        actions, terminal, error = super()._env_actions_for(command)
        if error is not None:
            return actions, terminal, error
        expanded: list[dict[str, Any]] = []
        changed = False
        for action in actions:
            mouse = action.get("mouse") or {}
            drag_key = next(
                (
                    key
                    for key in ("left_click_drag", "right_click_drag")
                    if key in mouse
                ),
                None,
            )
            if drag_key is None:
                expanded.append(action)
                continue
            value = mouse.get(drag_key)
            if (
                not isinstance(value, (list, tuple))
                or len(value) != 2
                or any(
                    not isinstance(point, (list, tuple)) or len(point) != 2
                    for point in value
                )
            ):
                return [], terminal, f"invalid {drag_key} coordinates"
            start = [round(float(number)) for number in value[0]]
            end = [round(float(number)) for number in value[1]]
            button = "left" if drag_key.startswith("left") else "right"
            expanded.extend(
                [
                    {"mouse": {"move": start}},
                    {"mouse": {"buttons": {f"{button}_down": True}}},
                    *[
                        {
                            "mouse": {
                                "move": [
                                    round(start[0] + (end[0] - start[0]) * fraction),
                                    round(start[1] + (end[1] - start[1]) * fraction),
                                ]
                            }
                        }
                        for fraction in (0.2, 0.4, 0.6, 0.8, 1.0)
                    ],
                    {"mouse": {"buttons": {f"{button}_up": True}}},
                ]
            )
            changed = True
        if not changed:
            return expanded, terminal, error
        return [{"action": "input_batch", "actions": expanded}], terminal, error

    def _gateway_response(self, command: str) -> dict[str, Any]:
        """Compatibility implementation for temporal and pre-temporal gateways."""
        if self.steps_taken >= self.max_steps:
            obs, timing = self._capture_with_timing()
            return {
                "step": self.steps_taken,
                "budget_remaining": 0,
                "done": True,
                "error": "step budget exhausted",
                "screenshot_b64": self._display_screenshot_b64(obs),
                "observation": (obs.get("screen") or {}).get("path"),
                "timing": timing,
            }

        env_actions, is_terminal, error = self._env_actions_for(command)
        if error is not None:
            obs, timing = self._capture_with_timing()
            self.transcript.append(
                {"step": self.steps_taken, "command": command, "error": error}
            )
            return {
                "step": self.steps_taken,
                "budget_remaining": self.max_steps - self.steps_taken,
                "done": False,
                "error": error,
                "screenshot_b64": self._display_screenshot_b64(obs),
                "observation": (obs.get("screen") or {}).get("path"),
                "timing": timing,
            }

        action_receipt: dict[str, float | None] | None = None
        done = False
        if len(env_actions) == 1 and env_actions[0].get("action") == "screenshot":
            obs, timing = self._capture_with_timing()
        else:
            requested_execute_at_s = None
            try:
                parsed = json.loads(command)
                requested_execute_at_s = parsed.get("execute_at_s")
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass
            executed_wall_ms = time.time_ns() / 1_000_000
            try:
                _ignored_obs, _reward, done, _info = self.env.step(
                    env_actions,
                    capture_observation=False,
                    settle_after_actions=False,
                )
            except TypeError:
                _ignored_obs, _reward, done, _info = self.env.step(env_actions)
            action_receipt = {
                "executed_wall_ms": executed_wall_ms,
                "requested_execute_at_s": requested_execute_at_s,
            }
            obs, timing = self._capture_with_timing(action_receipt=action_receipt)

        self.steps_taken += 1
        self.transcript.append(
            {
                "step": self.steps_taken,
                "command": command,
                "env_actions": env_actions,
                "terminal_requested": is_terminal,
                "env_done": bool(done),
            }
        )
        return {
            "step": self.steps_taken,
            "budget_remaining": max(0, self.max_steps - self.steps_taken),
            "done": bool(done) or is_terminal or self.steps_taken >= self.max_steps,
            "error": None,
            "screenshot_b64": self._display_screenshot_b64(obs),
            "observation": (obs.get("screen") or {}).get("path"),
            "timing": timing,
        }

    def step_from_command(self, command: str) -> dict[str, Any]:
        with self._state_lock:
            request_index = self._next_request_index
            self._next_request_index += 1
            response = self._gateway_response(command)
        timing = response.get("timing")
        if isinstance(timing, dict):
            common = {
                "request_index": request_index,
                "step": response.get("step"),
                "command": command,
            }
            events: list[dict[str, Any]] = []
            if timing.get("action_executed_at_s") is not None:
                events.append(
                    {
                        "event": "action_executed",
                        **common,
                        "action_executed_at_s": timing["action_executed_at_s"],
                        "requested_execute_at_s": timing.get(
                            "previous_action_requested_execute_at_s"
                        ),
                        "action_execution_lateness_s": timing.get(
                            "action_execution_lateness_s"
                        ),
                    }
                )
            if timing.get("frame_captured_at_s") is not None:
                events.append(
                    {
                        "event": "screenshot_captured",
                        **common,
                        "observation": response.get("observation"),
                        "frame_captured_at_s": timing["frame_captured_at_s"],
                        "current_time_s": timing.get("current_time_s"),
                    }
                )
            with self._timing_write_lock:
                with self._timing_path.open("a", encoding="utf-8") as handle:
                    for event in events:
                        handle.write(json.dumps(event, sort_keys=True) + "\n")
        return response


class WeirdCodexCliAgent(CodexCliAgent):
    """Codex CLI using Weird's episode-clock and timing-artifact contract."""

    def run_episode(self, env: Any, task_description: str | None = None) -> None:
        task = task_description or self.task_description
        resolution = self.display_resolution
        max_steps = int(
            self.max_steps_override or getattr(env, "max_steps", None) or 50
        )
        logs_dir = (
            Path(self.save_path) / "cli_harness"
            if self.save_path
            else Path(tempfile.mkdtemp())
        )
        logs_dir.mkdir(parents=True, exist_ok=True)
        token = secrets.token_hex(16)
        gateway = WeirdCodexActionGateway(
            env,
            resolution,
            max_steps,
            token,
            temporal_mode=self.temporal_mode,
            timing_path=logs_dir / "timing.jsonl",
        )
        sandbox = select_sandbox(self.sandbox_spec(), logs_dir)
        sandbox_started = False

        port = gateway.start(host=sandbox.gateway_bind_host)
        try:
            sandbox.build()
            sandbox.start(
                gateway_port=port,
                gateway_token=token,
                container_env=self.container_env(),
            )
            sandbox_started = True
            self.prepare_sandbox(sandbox)
            prompt = build_harness_prompt(
                task,
                (gateway.display_w, gateway.display_h),
                max_steps,
                temporal_mode=self.temporal_mode,
            )
            (logs_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
            result = sandbox.exec(
                self.build_cli_command(), timeout_sec=self.timeout_sec
            )
            if result.returncode != 0 and self.verbose:
                logger.warning(
                    "CLI exited with %d; stderr: %s",
                    result.returncode,
                    result.stderr[:2000],
                )
        except subprocess.TimeoutExpired:
            logger.warning("CLI harness timed out after %ds", self.timeout_sec)
        finally:
            self._transcript = gateway.transcript
            gateway.stop()
            if sandbox_started:
                try:
                    self.collect_sandbox_artifacts(sandbox)
                except Exception:
                    logger.warning(
                        "Failed to collect CLI sandbox artifacts", exc_info=True
                    )
            sandbox.stop()
            self.done = True
