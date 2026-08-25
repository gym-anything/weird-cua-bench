"""WeirdQwen35VLAgent variant for Qwen3.8-27B: encode frames at 1280x720.

Qwen3.8-27B converts its internal pixel estimates to the prompt's 0-999 grid
by assuming the screenshot is 1280x720. Fed native 1920x1080 frames (which the
server smart-resizes to ~1428x728), that assumption inflates x by 1428/1280 =
1.116 and every click slides ~11% right - measured on rk_d3_full_paused_seed44
step 1, where "click '7'" landed on the 'A' key three keys over. Resizing the
encoded frames to exactly 1280x720 removes the mismatch: the same replayed
request then clicks inside the '7' key (grid [581,260] -> pixel (1117,281)).

Only the pixels sent to the model shrink; observations stay native and grid
coordinates still scale to the true display resolution at parse time.

Run via:
  --agent weird_captcha_gym.evaluation.qwen38:WeirdQwen38VLAgent
"""
from __future__ import annotations

import base64
from functools import partial
import os
import time
from pathlib import Path
from typing import Any

import openai

from agents.shared.llm_clients import _openai_extra_body
from weird_captcha_gym.evaluation.qwen35vl import (
    NULL_RESPONSE_ATTEMPTS,
    WeirdQwen35VLAgent,
)

MODEL_INPUT_SIZE = (1280, 720)

# The ut tunnel intermittently wedges a single connection: the request never
# completes and the read never returns, so an episode hangs until something
# kills it (observed hangs of 90+ minutes; five episodes lost this way).
# call_llm() builds its OpenAI client without a timeout, so nothing unwedges
# it. This mirror of call_llm passes a hard per-request timeout; on expiry the
# next attempt opens a fresh connection, which restores the retry semantics
# the wedge was defeating.
REQUEST_TIMEOUT_S = 900


def call_qwen38_with_timeout(
    messages,
    model,
    temperature,
    top_p,
    top_k=-1,
    max_tokens=4096,
    repetition_penalty=1.0,
    disable_thinking=None,
    session_id=None,
    reasoning_effort=None,
    request_timeout_seconds=REQUEST_TIMEOUT_S,
):
    for null_attempt in range(1, NULL_RESPONSE_ATTEMPTS + 1):
        response = None
        for attempt in range(10):
            try:
                client = openai.OpenAI(
                    base_url=os.environ.get("VLM_BASE_URL", "http://localhost:8080/v1"),
                    api_key="EMPTY",
                    timeout=request_timeout_seconds,
                    max_retries=0,
                )
                request_options = {}
                if reasoning_effort is not None:
                    request_options["reasoning_effort"] = reasoning_effort
                raw = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    top_p=top_p,
                    extra_body=_openai_extra_body(
                        top_k=top_k,
                        repetition_penalty=repetition_penalty,
                        disable_thinking=False,
                        session_id=session_id,
                    ),
                    max_tokens=max_tokens,
                    **request_options,
                )
                message = raw.choices[0].message
                reasoning = getattr(message, "reasoning", None) or getattr(
                    message, "reasoning_content", None
                )
                content = message.content
                if reasoning:
                    response = f"<think>{reasoning}</think>\n{content}"
                else:
                    response = content
                break
            except openai.BadRequestError:
                raise
            except Exception as exc:
                print(f"Error calling llm (attempt {attempt + 1}/10): {exc}")
                time.sleep(min(2 ** (attempt + 1), 60))
        else:
            raise RuntimeError("Failed to get response from LLM after 10 attempts")
        if response is not None:
            return response
        print(f"Qwen returned content=null (attempt {null_attempt}/{NULL_RESPONSE_ATTEMPTS})")
    raise RuntimeError(
        f"Qwen returned content=null after {NULL_RESPONSE_ATTEMPTS} attempts"
    )


class WeirdQwen38VLAgent(WeirdQwen35VLAgent):
    llm_call = staticmethod(call_qwen38_with_timeout)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        reasoning_effort = self.agent_args.get("reasoning_effort")
        if reasoning_effort not in {None, "low", "medium", "xhigh"}:
            raise ValueError(
                "reasoning_effort must be one of: low, medium, xhigh"
            )
        self.reasoning_effort = reasoning_effort
        request_timeout_seconds = float(
            self.agent_args.get("request_timeout_seconds", REQUEST_TIMEOUT_S)
        )
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        self.request_timeout_seconds = request_timeout_seconds
        self.llm_call = partial(
            call_qwen38_with_timeout,
            reasoning_effort=reasoning_effort,
            request_timeout_seconds=request_timeout_seconds,
        )

    def _encode_resized(self, value: Any, path: Path) -> str:
        image = self._native_image(value).resize(MODEL_INPUT_SIZE)
        image.save(path, format="PNG")
        return base64.b64encode(path.read_bytes()).decode("utf-8")

    def process_image(self, image_path: str) -> tuple[str, str]:
        path = Path(self.save_folder_custom) / f"observation_{self.step_idx}.png"
        encoded = self._encode_resized(image_path, path)
        original_sizes = getattr(self, "original_sizes", None)
        if isinstance(original_sizes, list):
            # Grid coordinates must keep scaling to the real display.
            original_sizes.append(tuple(int(v) for v in self.display_resolution))
        self.processed_size = MODEL_INPUT_SIZE
        return encoded, str(path)

    def _process_frame(self, value: Any, *, step: int, index: int) -> tuple[str, str]:
        path = Path(self.save_folder_custom) / f"observation_{step}_frame_{index:03d}.png"
        encoded = self._encode_resized(value, path)
        self.b64_to_path[encoded] = str(path)
        return encoded, str(path)
