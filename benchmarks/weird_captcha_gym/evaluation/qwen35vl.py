from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image
from agents.agents.qwen35vl import Qwen35VLAgent
from agents.shared.llm_clients import smart_resize


def image_from_screen(value: Any) -> Image.Image:
    if isinstance(value, (str, Path)):
        with Image.open(value) as image:
            return image.convert("RGB")
    if not isinstance(value, dict):
        raise TypeError(f"unsupported screen value: {type(value).__name__}")
    image = value.get("image")
    if image is not None:
        return image.convert("RGB")
    encoded = value.get("png_b64")
    if encoded:
        with Image.open(BytesIO(base64.b64decode(encoded))) as decoded:
            return decoded.convert("RGB")
    path = value.get("path")
    if path:
        with Image.open(path) as decoded:
            return decoded.convert("RGB")
    raise ValueError("screen value has no image, png_b64, or path")


def observation_frames(obs: dict[str, Any]) -> list[Any]:
    frames = obs.get("frames")
    if isinstance(frames, list) and frames:
        return frames
    screen = obs.get("screen")
    if screen is None:
        raise ValueError("observation has no screen")
    return [screen]


class WeirdQwen35VLAgent(Qwen35VLAgent):
    """Gym Anything's Qwen 3.5 agent with chronological frame observations."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.frame_sequences: list[list[str]] = []
        self._current_extra_frames: list[str] = []

    def _process_frame(self, value: Any, *, step: int, index: int) -> tuple[str, str]:
        image = image_from_screen(value)
        width, height = image.size
        resized_height, resized_width = smart_resize(
            height=height,
            width=width,
            factor=32,
            max_pixels=16 * 16 * 4 * 1280,
        )
        image = image.resize((resized_width, resized_height))
        path = Path(self.save_folder_custom) / f"observation_{step}_frame_{index:03d}.png"
        image.save(path, format="PNG")
        encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
        self.b64_to_path[encoded] = str(path)
        return encoded, str(path)

    def step(self, obs, action_outputs):
        frames = observation_frames(obs)
        next_step = self.step_idx + 1
        self._current_extra_frames = [
            self._process_frame(frame, step=next_step, index=index)[0]
            for index, frame in enumerate(frames[:-1])
        ]
        latest = image_from_screen(frames[-1])
        latest_path = Path(self.save_folder_custom) / f"weird_input_{next_step}.png"
        latest.save(latest_path, format="PNG")
        normalized = dict(obs)
        normalized["screen"] = {
            "path": str(latest_path),
            "format": "png",
            "resolution": list(latest.size),
        }
        return super().step(normalized, action_outputs)

    @staticmethod
    def _image_parts(sequence: list[str]) -> list[dict[str, Any]]:
        parts: list[dict[str, Any]] = []
        if len(sequence) > 1:
            parts.append(
                {
                    "type": "text",
                    "text": (
                        "These screenshots are one observation in chronological order. "
                        "The final screenshot is the current state."
                    ),
                }
            )
        parts.extend(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{encoded}"},
            }
            for encoded in sequence
        )
        return parts

    def build_messages(self, current_screenshot_b64):
        current_sequence = [*self._current_extra_frames, current_screenshot_b64]
        self.frame_sequences.append(current_sequence)

        history_start_idx = max(0, len(self.history) - self.history_n)
        previous_actions = [
            f"Step {index + 1}: {self.history[index]}"
            for index in range(history_start_idx, len(self.history))
        ]
        previous_actions_text = "\n".join(previous_actions) if previous_actions else "None"
        instruction = (
            "Please generate the next move according to the UI screenshots, instruction, "
            "and previous actions.\n\n"
            f"Instruction: {self.task_description}\n\n"
            f"Previous actions:\n{previous_actions_text}"
        )
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": [{"type": "text", "text": self.get_system_prompt()}],
            }
        ]

        history_len = min(self.history_n, len(self.responses))
        if history_len:
            history_responses = self.responses[-history_len:]
            history_sequences = self.frame_sequences[-history_len - 1 : -1]
            for index, response in enumerate(history_responses):
                if index < len(history_sequences):
                    content = self._image_parts(history_sequences[index])
                    if index == 0:
                        content.append({"type": "text", "text": instruction})
                    messages.append({"role": "user", "content": content})
                messages.append(
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": str(response)}],
                    }
                )
            messages.append(
                {"role": "user", "content": self._image_parts(current_sequence)}
            )
        else:
            content = self._image_parts(current_sequence)
            content.append({"type": "text", "text": instruction})
            messages.append({"role": "user", "content": content})
        return messages
