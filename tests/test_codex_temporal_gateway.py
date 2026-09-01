from __future__ import annotations

import json
import time
from pathlib import Path

from weird_captcha_gym.evaluation.codex_cli import WeirdCodexActionGateway


class TimedEnvironment:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.origin_ms = time.time_ns() / 1_000_000 - 1_000
        self.capture_count = 0
        self.step_calls: list[tuple[list[dict], bool, bool]] = []

    def capture_observation(self) -> dict:
        index = self.capture_count
        self.capture_count += 1
        frame = self.root / f"frame-{index}.png"
        frame.write_bytes(b"test-frame")
        manifest = self.root / f"manifest-{index}.json"
        manifest.write_text(
            json.dumps(
                {
                    "window_started_wall_ms": self.origin_ms + 250 + index * 100,
                    "frames": [{"offset_ms": 0}],
                }
            ),
            encoding="utf-8",
        )
        return {
            "screen": {"path": str(frame)},
            "frames": [{"path": str(frame), "offset_ms": 0}],
            "capture_manifest": str(manifest),
            "time": {"episode_started_wall_ms": self.origin_ms},
        }

    def step(
        self,
        actions: list[dict],
        *,
        capture_observation: bool,
        settle_after_actions: bool,
    ) -> tuple[dict, float, bool, dict]:
        self.step_calls.append(
            (actions, capture_observation, settle_after_actions)
        )
        return {}, 0.0, False, {}


def test_codex_clock_starts_before_first_frame_and_persists_every_event(
    tmp_path: Path,
) -> None:
    timing_path = tmp_path / "timing.jsonl"
    env = TimedEnvironment(tmp_path)
    gateway = WeirdCodexActionGateway(
        env,
        (1280, 720),
        5,
        "token",
        temporal_mode="live_timestamped_execution",
        timing_path=timing_path,
    )

    first = gateway.step_from_command('{"action": "screenshot"}')
    action = gateway.step_from_command(
        '{"action": "left_click", "coordinate": [20, 30]}'
    )

    assert first["timing"]["frame_captured_at_s"] == 0.25
    assert action["timing"]["frame_captured_at_s"] == 0.35
    assert action["timing"]["action_executed_at_s"] >= 0
    assert env.step_calls == [
        ([{"mouse": {"left_click": [20, 30]}}], False, False)
    ]
    events = [json.loads(line) for line in timing_path.read_text().splitlines()]
    assert [event["event"] for event in events] == [
        "screenshot_captured",
        "action_executed",
        "screenshot_captured",
    ]
    assert events[0]["frame_captured_at_s"] == 0.25
    assert events[1]["action_executed_at_s"] == action["timing"][
        "action_executed_at_s"
    ]


def test_codex_timestamped_gateway_rejects_a_missing_episode_origin(
    tmp_path: Path,
) -> None:
    env = TimedEnvironment(tmp_path)
    original_capture = env.capture_observation

    def capture_without_origin() -> dict:
        observation = original_capture()
        observation["time"] = {}
        return observation

    env.capture_observation = capture_without_origin  # type: ignore[method-assign]
    gateway = WeirdCodexActionGateway(
        env,
        (1280, 720),
        5,
        "token",
        temporal_mode="live_timestamped",
        timing_path=tmp_path / "timing.jsonl",
    )

    try:
        gateway.step_from_command('{"action": "screenshot"}')
    except RuntimeError as error:
        assert "episode_started_wall_ms" in str(error)
    else:
        raise AssertionError("missing episode clock origin was accepted")


def test_codex_gateway_expands_drag_into_one_sampled_input_batch(tmp_path: Path) -> None:
    gateway = WeirdCodexActionGateway(
        TimedEnvironment(tmp_path),
        (1920, 1080),
        5,
        "token",
        timing_path=tmp_path / "timing.jsonl",
        temporal_mode="paused",
    )

    actions, terminal, error = gateway._env_actions_for(
        '{"action":"drag","coordinate":[100,100],"coordinate2":[500,300]}'
    )

    assert terminal is False
    assert error is None
    assert len(actions) == 1
    batch = actions[0]
    assert batch["action"] == "input_batch"
    gesture = batch["actions"]
    assert gesture[0] == {"mouse": {"move": [150, 150]}}
    assert gesture[1] == {"mouse": {"buttons": {"left_down": True}}}
    assert gesture[-1] == {"mouse": {"buttons": {"left_up": True}}}
    moves = [item["mouse"]["move"] for item in gesture if "move" in item["mouse"]]
    assert len(moves) == 6
    assert moves[-1] == [750, 450]
