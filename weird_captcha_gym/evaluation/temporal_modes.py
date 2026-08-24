"""Temporal-mode contract shared by the Weird CUA evaluator and agents."""

from __future__ import annotations


TEMPORAL_MODES = (
    "paused",
    "live",
    "live_timestamped",
    "live_timestamped_execution",
)


def validate_temporal_mode(mode: str) -> str:
    if mode not in TEMPORAL_MODES:
        choices = ", ".join(TEMPORAL_MODES)
        raise ValueError(f"temporal mode must be one of {choices}; got {mode!r}")
    return mode


def world_time_mode(mode: str) -> str:
    return "paused" if validate_temporal_mode(mode) == "paused" else "live"


def timestamps_enabled(mode: str) -> bool:
    return validate_temporal_mode(mode) in {
        "live_timestamped",
        "live_timestamped_execution",
    }


def scheduled_execution_enabled(mode: str) -> bool:
    return validate_temporal_mode(mode) == "live_timestamped_execution"
