from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from weird_captcha_gym.evaluation.gemini_timestamped import (
    TimestampedGeminiComputerUseAgent,
    scheduled_action_declaration,
)
from weird_captcha_gym.evaluation.qwen_timestamped import (
    TimestampedWeirdQwen35VLAgent,
)
from weird_captcha_gym.shared_scripts.time_control import wait_until_wall_time
from weird_captcha_gym.tools.run_realtime_evaluation import _actions_with_schedule


def _manifest(
    path: Path,
    *,
    start_ms: float,
    offsets: list[float],
    episode_started_wall_ms: float = 9_000,
) -> dict:
    path.write_text(
        json.dumps(
            {
                "window_started_wall_ms": start_ms,
                "frames": [{"offset_ms": offset} for offset in offsets],
            }
        )
    )
    return {
        "capture_manifest": str(path),
        "time": {"episode_started_wall_ms": episode_started_wall_ms},
    }


def _bare_timestamped_qwen(
    temporal_mode: str = "live_timestamped_execution",
) -> TimestampedWeirdQwen35VLAgent:
    agent = object.__new__(TimestampedWeirdQwen35VLAgent)
    agent.temporal_mode = temporal_mode
    agent._t0_ms = None
    agent._last_frame_seen_s = None
    agent._latency_log = []
    agent._timing_by_key = {}
    agent._previous_requested_execute_at_s = None
    return agent


def test_qwen_schedule_uses_the_observation_clock() -> None:
    agent = _bare_timestamped_qwen()
    agent._t0_ms = 1_000.0
    response = """Action: click at 4.25 seconds
<tool_call>
<function=computer_use>
<parameter=action>left_click</parameter>
<parameter=coordinate>[500, 250]</parameter>
<parameter=execute_at_s>4.25</parameter>
</function>
</tool_call>"""

    parsed = agent._parse_response(response, 1920, 1080)

    assert parsed["actions"] == [{"mouse": {"left_click": [960, 270]}}]
    assert parsed["metadata"]["execute_at_s"] == 4.25
    assert parsed["metadata"]["execute_at_wall_ms"] == 5_250.0
    assert agent._tools_def()["function"]["parameters"]["properties"][
        "execute_at_s"
    ]["type"] == "number"


def test_existing_timing_fields_survive_scheduled_action(tmp_path: Path) -> None:
    agent = _bare_timestamped_qwen()
    first = _manifest(tmp_path / "first.json", start_ms=10_000, offsets=[0, 400, 800])
    second = _manifest(tmp_path / "second.json", start_ms=13_000, offsets=[0, 400, 800])

    assert agent._timing_payload(first) == {
        "screenshot_captured_at_s": [1.0, 1.4, 1.8],
        "current_time_s": 1.8,
    }
    agent._previous_requested_execute_at_s = 2.5
    payload = agent._timing_payload(second)

    assert payload["previous_action_finished_executing_by_s"] == 4.0
    assert payload["seconds_between_your_last_screenshot_and_that_action_landing"] == 2.2
    assert payload["previous_action_requested_execute_at_s"] == 2.5
    assert agent._latency_log == [2.2]


def test_evaluator_prepends_absolute_runner_wait() -> None:
    group = {
        "actions": [{"mouse": {"left_click": [12, 34]}}],
        "metadata": {"execute_at_s": 3.5, "execute_at_wall_ms": 12_345.0},
    }
    assert _actions_with_schedule(
        group, temporal_mode="live_timestamped_execution"
    ) == [
        {"action": "wait_until", "wall_time_ms": 12_345.0},
        {"mouse": {"left_click": [12, 34]}},
    ]
    for mode in ("paused", "live", "live_timestamped"):
        with pytest.raises(ValueError, match="live_timestamped_execution"):
            _actions_with_schedule(group, temporal_mode=mode)


def test_timestamp_only_qwen_does_not_expose_or_apply_execute_at() -> None:
    agent = _bare_timestamped_qwen("live_timestamped")
    assert "execute_at_s" not in agent._tools_def()["function"]["parameters"][
        "properties"
    ]
    agent._t0_ms = 1_000.0
    response = """Action: click
<tool_call>
<function=computer_use>
<parameter=action>left_click</parameter>
<parameter=coordinate>[500, 250]</parameter>
<parameter=execute_at_s>4.25</parameter>
</function>
</tool_call>"""
    parsed = agent._parse_response(response, 1920, 1080)
    assert "execute_at_s" not in parsed["metadata"]
    assert "execute_at_wall_ms" not in parsed["metadata"]


def test_past_wall_deadline_returns_without_a_server() -> None:
    result = wait_until_wall_time(0)
    assert result["requested_wall_time_ms"] == 0
    assert result["wait_completed_wall_ms"] > 0
    assert result["wait_lateness_ms"] > 0


def test_gemini_exposes_and_translates_scheduled_actions() -> None:
    declaration = scheduled_action_declaration()
    schema = declaration.parameters_json_schema
    assert declaration.name == "schedule_action"
    assert schema["required"] == ["execute_at_s", "action"]

    agent = object.__new__(TimestampedGeminiComputerUseAgent)
    agent.temporal_mode = "live_timestamped_execution"
    agent.display_resolution = (1920, 1080)
    agent.consecutive_unsupported = 0
    agent._last_unsupported = False
    agent._scheduled_execute_at_s = None
    actions = agent._translate(
        "schedule_action",
        {"execute_at_s": 7.75, "action": "click", "x": 500, "y": 250},
    )
    assert actions == [{"mouse": {"left_click": [960, 270]}}]
    assert agent._scheduled_execute_at_s == 7.75


def test_gemini_adds_schedule_tool_only_in_execution_mode(monkeypatch) -> None:
    from agents.agents.gemini_computer_use import GeminiComputerUseAgent

    base_tool = object()

    def fake_init(self, *args, **kwargs):
        self.agent_args = kwargs.get("agent_args", {})
        self.tool = base_tool
        self.config = SimpleNamespace(tools=[base_tool])

    monkeypatch.setattr(GeminiComputerUseAgent, "__init__", fake_init)
    timestamped = TimestampedGeminiComputerUseAgent(
        agent_args={"temporal_mode": "live_timestamped"}
    )
    execution = TimestampedGeminiComputerUseAgent(
        agent_args={"temporal_mode": "live_timestamped_execution"}
    )

    assert timestamped.config.tools == [base_tool]
    assert len(execution.config.tools) == 2
