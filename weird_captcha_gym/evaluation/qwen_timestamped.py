"""WeirdQwen35VLAgent with explicit temporal grounding.

Same experiment as gemini_timestamped: every observation is annotated with
each frame's capture time, when the previous action finished executing, and
a log of the model's own observe-to-execute latencies. All values measured
(frame wall times from the capture manifest; execution bounded by the next
window's start). Timing text rides as an extra text part in front of each
observation's screenshots, content-addressed by the observation's first
encoded frame so it survives history rebuilds and context-retry rebuilds.

Run via:
  --agent weird_captcha_gym.evaluation.qwen_timestamped:TimestampedWeirdQwen35VLAgent
"""
from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from weird_captcha_gym.evaluation.qwen35vl import (
    WeirdQwen35VLAgent,
    image_from_screen,
    observation_frames,
)
from weird_captcha_gym.evaluation.temporal_modes import (
    scheduled_execution_enabled,
    timestamps_enabled,
    validate_temporal_mode,
)

TIMING_NOTE = (
    "\n\nTiming information: every observation is annotated with the time each "
    "screenshot was captured (seconds since the task started), when your "
    "previous action finished executing, and a log of your own recent "
    "observe-to-execute latencies. Your actions do NOT execute instantly: real "
    "time passes between the screenshots you see and the moment your action "
    "lands, and the interface keeps moving during that delay."
)

SCHEDULING_NOTE = (
    " To schedule a UI action for a future instant, include execute_at_s in "
    "that computer_use call. It is an absolute time on the same clock as "
    "current_time_s; omit it to execute immediately. A time that has already "
    "passed executes immediately."
)


class TimestampedWeirdQwen35VLAgent(WeirdQwen35VLAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.temporal_mode = validate_temporal_mode(
            self.agent_args.get("temporal_mode", "live_timestamped")
        )
        self._t0_ms: float | None = None
        self._last_frame_seen_s: float | None = None
        self._latency_log: list[float] = []
        self._timing_by_key: dict[str, str] = {}
        self._previous_requested_execute_at_s: float | None = None

    def init(self, task_description, display_resolution, save_path):
        note = TIMING_NOTE if timestamps_enabled(self.temporal_mode) else ""
        if scheduled_execution_enabled(self.temporal_mode):
            note += SCHEDULING_NOTE
        super().init(task_description + note, display_resolution, save_path)

    def _timing_payload(self, obs) -> dict | None:
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
            self._t0_ms = float(start)
        rel = [
            round((float(start) + float(f.get("offset_ms") or 0) - self._t0_ms) / 1000.0, 2)
            for f in frames
        ]
        window_start_s = round((float(start) - self._t0_ms) / 1000.0, 2)
        payload: dict = {
            "screenshot_captured_at_s": rel,
            "current_time_s": rel[-1],
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
        self._last_frame_seen_s = rel[-1]
        return payload

    def _tools_def(self) -> dict[str, Any]:
        tool = deepcopy(WeirdQwen35VLAgent._tools_def())
        if scheduled_execution_enabled(self.temporal_mode):
            tool["function"]["parameters"]["properties"]["execute_at_s"] = {
                "type": "number",
                "description": (
                    "Optional absolute execution time in seconds on the clock "
                    "reported as current_time_s. Omit to execute immediately."
                ),
            }
        return tool

    @classmethod
    def _requested_execute_at_s(cls, response: str) -> float | None:
        params_list: list[dict[str, Any]] = []
        for match in re.finditer(r"<tool_call>(.*?)</tool_call>", response or "", re.DOTALL):
            params = cls._parse_xml_tool_call(match.group(1))
            if params:
                params_list.append(params)
        if not params_list:
            match = re.search(
                r'(\{"name"\s*:\s*"computer_use".*\})', response or "", re.DOTALL
            )
            if match:
                params = cls._parse_json_tool_call(match.group(1))
                if params:
                    params_list.append(params)
        values = [item.get("execute_at_s") for item in params_list if "execute_at_s" in item]
        if not values:
            return None
        try:
            value = float(values[-1])
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) and value >= 0 else None

    def _parse_response(self, response, original_width, original_height):
        parsed = super()._parse_response(response, original_width, original_height)
        if not scheduled_execution_enabled(self.temporal_mode):
            return parsed
        execute_at_s = self._requested_execute_at_s(response)
        self._previous_requested_execute_at_s = execute_at_s
        if execute_at_s is not None and self._t0_ms is not None and parsed["actions"]:
            parsed["metadata"]["execute_at_s"] = execute_at_s
            parsed["metadata"]["execute_at_wall_ms"] = (
                self._t0_ms + execute_at_s * 1000
            )
        return parsed

    # Mirror of WeirdQwen35VLAgent.step with one addition: after the extra
    # frames are encoded, the timing payload is keyed by the observation's
    # first encoded frame so _image_parts can attach it to the right window.
    def step(self, obs, action_outputs):
        if not timestamps_enabled(self.temporal_mode):
            return WeirdQwen35VLAgent.step(self, obs, action_outputs)
        payload = self._timing_payload(obs)

        frames = observation_frames(obs)
        next_step = self.step_idx + 1
        self._current_extra_frames = [
            self._process_frame(frame, step=next_step, index=index)[0]
            for index, frame in enumerate(frames[:-1])
        ]
        if payload is not None and self._current_extra_frames:
            self._timing_by_key[self._current_extra_frames[0][:96]] = json.dumps(payload)
        latest = image_from_screen(frames[-1])
        latest_path = Path(self.save_folder_custom) / f"weird_input_{next_step}.png"
        latest.save(latest_path, format="PNG")
        normalized = dict(obs)
        normalized["screen"] = {
            "path": str(latest_path),
            "format": "png",
            "resolution": list(latest.size),
        }
        # Skip WeirdQwen35VLAgent.step (whose body is duplicated above) and
        # call its parent directly.
        return super(WeirdQwen35VLAgent, self).step(normalized, action_outputs)

    def _image_parts(self, sequence: list[str]) -> list[dict[str, Any]]:
        parts = WeirdQwen35VLAgent._image_parts(sequence)
        timing = self._timing_by_key.get(sequence[0][:96]) if sequence else None
        if timing:
            parts.insert(0, {"type": "text", "text": f"[timing] {timing}"})
        return parts
