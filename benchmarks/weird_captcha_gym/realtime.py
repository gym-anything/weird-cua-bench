from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


SETTINGS_PATH = Path(__file__).with_name("real_time.json")


@dataclass(frozen=True)
class RealTimeSettings:
    play_time_seconds: int
    observation_window_ms: int
    frames_per_observation: int

    @classmethod
    def from_dict(cls, data: dict) -> "RealTimeSettings":
        settings = cls(
            play_time_seconds=int(data["play_time_seconds"]),
            observation_window_ms=int(data["observation_window_ms"]),
            frames_per_observation=int(data["frames_per_observation"]),
        )
        if settings.play_time_seconds <= 0:
            raise ValueError("play_time_seconds must be positive")
        if settings.observation_window_ms < 0:
            raise ValueError("observation_window_ms must be non-negative")
        if settings.frames_per_observation <= 0:
            raise ValueError("frames_per_observation must be positive")
        if settings.observation_window_ms == 0 and settings.frames_per_observation != 1:
            raise ValueError("a zero-length observation window must use one frame")
        return settings


def mechanic_id_from_env_dir(env_dir: str | Path) -> str:
    name = Path(env_dir).resolve().name
    if not name.endswith("_env"):
        raise ValueError(f"environment directory must end in _env: {env_dir}")
    return name.removesuffix("_env")


def load_real_time_settings(mechanic_id: str, path: str | Path = SETTINGS_PATH) -> RealTimeSettings:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        settings = data["environments"][mechanic_id]
    except KeyError as exc:
        raise KeyError(f"no real-time settings for {mechanic_id}") from exc
    return RealTimeSettings.from_dict(settings)
