"""Gemini Computer Use with explicit temporal grounding.

Every observation carries the capture timestamp of each frame, and the model
is told when its previous action had finished executing, plus a running log
of its own observe-to-execute latencies. All values are measured (frame wall
times from the capture manifest; execution bounded by the following window's
start, which fast_io begins ~0.3s after injection). The model may attach an
absolute time on that clock to a scheduled action.

Run via:
  --agent weird_captcha_gym.evaluation.gemini_timestamped:TimestampedGeminiComputerUseAgent
"""
from __future__ import annotations

import json
import math

from agents.agents.gemini_computer_use import GeminiComputerUseAgent
from google.genai import types
from weird_captcha_gym.evaluation.temporal_modes import (
    episode_clock_origin_ms,
    scheduled_execution_enabled,
    timestamps_enabled,
    validate_temporal_mode,
)

TIMING_NOTE = (
    "\n\nTiming information: every screenshot is annotated with the time it was "
    "captured (seconds since the task started). After each of your actions, the "
    "next observation reports when that action had finished executing. Your "
    "actions do NOT execute instantly: real time passes between the screenshots "
    "you see and the moment your action lands, and the interface keeps moving "
    "during that delay. A log of your own recent latencies is included."
)

SCHEDULING_NOTE = (
    " To schedule an action for a future instant, call schedule_action with an "
    "absolute execute_at_s on the same clock as current_time_s. Use the normal "
    "computer action when no scheduling is needed. A time that has already "
    "passed executes immediately."
)

SCHEDULED_ACTIONS = [
    "click",
    "right_click",
    "middle_click",
    "double_click",
    "triple_click",
    "move",
    "mouse_down",
    "mouse_up",
    "drag_and_drop",
    "type",
    "press_key",
    "hotkey",
    "scroll",
]


def scheduled_action_declaration() -> types.FunctionDeclaration:
    return types.FunctionDeclaration(
        name="schedule_action",
        description=(
            "Schedule one desktop action at an absolute time on the observation "
            "clock. Coordinates use the same normalized 0-1000 space as the "
            "computer tool. Supply the fields required by the selected action."
        ),
        parameters_json_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "execute_at_s": {
                    "type": "number",
                    "minimum": 0,
                    "description": "Absolute execution time on the current_time_s clock.",
                },
                "action": {"type": "string", "enum": SCHEDULED_ACTIONS},
                "x": {"type": "number"},
                "y": {"type": "number"},
                "start_x": {"type": "number"},
                "start_y": {"type": "number"},
                "end_x": {"type": "number"},
                "end_y": {"type": "number"},
                "text": {"type": "string"},
                "key": {"type": "string"},
                "keys": {"type": "array", "items": {"type": "string"}},
                "direction": {"type": "string", "enum": ["up", "down"]},
                "magnitude": {"type": "number"},
                "clear_before_typing": {"type": "boolean"},
                "press_enter": {"type": "boolean"},
            },
            "required": ["execute_at_s", "action"],
        },
    )


class TimestampedGeminiComputerUseAgent(GeminiComputerUseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.temporal_mode = validate_temporal_mode(
            self.agent_args.get("temporal_mode", "live_timestamped")
        )
        if scheduled_execution_enabled(self.temporal_mode):
            self.config.tools = [
                self.tool,
                types.Tool(function_declarations=[scheduled_action_declaration()]),
            ]
        self._t0_ms: float | None = None
        self._last_frame_seen_s: float | None = None
        self._latency_log: list[dict] = []
        self._pending_timing: dict | None = None
        self._scheduled_execute_at_s: float | None = None
        self._previous_requested_execute_at_s: float | None = None

    def init(self, task_description, display_resolution, save_path):
        note = TIMING_NOTE if timestamps_enabled(self.temporal_mode) else ""
        if scheduled_execution_enabled(self.temporal_mode):
            note += SCHEDULING_NOTE
        super().init(task_description + note, display_resolution, save_path)

    # -- measured clocks ----------------------------------------------------

    def _frame_times(self, obs) -> tuple[list[float], float] | None:
        path = obs.get("capture_manifest")
        if not path:
            return None
        try:
            manifest = json.load(open(path))
        except Exception:
            return None
        start = manifest.get("window_started_wall_ms")
        frames = manifest.get("frames") or []
        if start is None or not frames:
            return None
        if self._t0_ms is None:
            self._t0_ms = episode_clock_origin_ms(obs)
        rel = [
            round((float(start) + float(f.get("offset_ms") or 0) - self._t0_ms) / 1000.0, 2)
            for f in frames
        ]
        window_start_s = round((float(start) - self._t0_ms) / 1000.0, 2)
        return rel, window_start_s

    def _timing_payload(self, obs) -> dict | None:
        times = self._frame_times(obs)
        if times is None:
            return None
        frame_s, window_start_s = times
        payload: dict = {
            "screenshot_captured_at_s": frame_s,
            "current_time_s": frame_s[-1],
        }
        if self._last_frame_seen_s is not None:
            latency = round(window_start_s - self._last_frame_seen_s, 2)
            payload["previous_action_finished_executing_by_s"] = window_start_s
            payload["seconds_between_your_last_screenshot_and_that_action_landing"] = latency
            self._latency_log.append(latency)
            if len(self._latency_log) > 1:
                payload["your_recent_observe_to_execute_latencies_s"] = self._latency_log[-8:]
            if self._previous_requested_execute_at_s is not None:
                payload["previous_action_requested_execute_at_s"] = (
                    self._previous_requested_execute_at_s
                )
                self._previous_requested_execute_at_s = None
        self._last_frame_seen_s = frame_s[-1]
        return payload

    # -- injection points ---------------------------------------------------

    def step(self, obs, action_outputs):
        if not timestamps_enabled(self.temporal_mode):
            return super().step(obs, action_outputs)
        self._scheduled_execute_at_s = None
        self._pending_timing = self._timing_payload(obs)
        if not self.contents and self._pending_timing is not None:
            # First turn has no function_response to carry the payload; ride
            # on the task text, then restore it for later turns.
            original = self.task_description
            self.task_description = (
                original + "\n\n[timing] " + json.dumps(self._pending_timing)
            )
            try:
                groups = super().step(obs, action_outputs)
            finally:
                self.task_description = original
        else:
            groups = super().step(obs, action_outputs)
        if self._scheduled_execute_at_s is not None and self._t0_ms is not None:
            for group in groups:
                if not group.get("actions"):
                    continue
                metadata = group.setdefault("metadata", {})
                metadata["execute_at_s"] = self._scheduled_execute_at_s
                metadata["execute_at_wall_ms"] = (
                    self._t0_ms + self._scheduled_execute_at_s * 1000
                )
            if groups:
                self._previous_requested_execute_at_s = self._scheduled_execute_at_s
        return groups

    def _translate(self, name, args):
        if name != "schedule_action":
            return super()._translate(name, args)
        if not scheduled_execution_enabled(self.temporal_mode):
            return self._unsupported(
                name,
                "schedule_action is available only in live_timestamped_execution mode",
            )
        nested = dict(args)
        action = str(nested.pop("action", ""))
        raw_execute_at_s = nested.pop("execute_at_s", None)
        try:
            execute_at_s = float(raw_execute_at_s)
        except (TypeError, ValueError):
            return self._unsupported(name, "execute_at_s must be a number")
        if not math.isfinite(execute_at_s) or execute_at_s < 0:
            return self._unsupported(name, "execute_at_s must be finite and non-negative")
        actions = super()._translate(action, nested)
        if not self._last_unsupported:
            self._scheduled_execute_at_s = execute_at_s
        return actions

    def _function_response(self, name, fid, resp, shots):
        if self._pending_timing is not None:
            resp = dict(resp)
            resp["timing"] = self._pending_timing
        return super()._function_response(name, fid, resp, shots)
