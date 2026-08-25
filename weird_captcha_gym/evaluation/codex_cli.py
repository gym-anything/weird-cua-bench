"""Weird CUA's Codex CLI temporal adapter over Gym-Anything's CLI harness."""

from __future__ import annotations

import json
import logging
import secrets
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

from agents.agents.codex_cli import CodexCliAgent
from agents.shared.agent_sandbox import select_sandbox
from agents.shared.cli_harness import ActionGateway, build_harness_prompt

from weird_captcha_gym.evaluation.temporal_modes import (
    episode_clock_origin_ms,
    timestamps_enabled,
)

logger = logging.getLogger(__name__)


class WeirdCodexActionGateway(ActionGateway):
    """Bind Codex timing to the Weird episode clock and persist every event."""

    def __init__(self, *args: Any, timing_path: Path, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._timing_path = timing_path
        self._timing_path.parent.mkdir(parents=True, exist_ok=True)
        self._timing_write_lock = threading.Lock()
        self._next_request_index = 0

    def _timing_payload(
        self,
        obs: dict[str, Any],
        *,
        action_receipt: dict[str, float | None] | None,
        capture_finished_wall_ms: float,
    ) -> dict[str, Any] | None:
        if timestamps_enabled(self.temporal_mode) and self._t0_ms is None:
            self._t0_ms = episode_clock_origin_ms(obs)
        return super()._timing_payload(
            obs,
            action_receipt=action_receipt,
            capture_finished_wall_ms=capture_finished_wall_ms,
        )

    def step_from_command(self, command: str) -> dict[str, Any]:
        with self._state_lock:
            request_index = self._next_request_index
            self._next_request_index += 1
        response = super().step_from_command(command)
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
