from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any, Protocol


COLLECTABLE_ARTIFACTS = {
    "current_task.json": "/tmp/weird_captcha_gym/current_task.json",
    "public_state.json": "/tmp/weird_captcha_gym/public_state.json",
    "parallel_grillmaster_witness_ledger.json": (
        "/tmp/weird_captcha_gym/parallel_grillmaster_witness_ledger.json"
    ),
    "parallel_grillmaster_witness_clock.json": (
        "/tmp/weird_captcha_gym/parallel_grillmaster_witness_clock.json"
    ),
    "slot_reel_witness_ledger.json": (
        "/tmp/weird_captcha_gym/slot_reel_witness_ledger.json"
    ),
    "slot_reel_witness_clock.json": (
        "/tmp/weird_captcha_gym/slot_reel_witness_clock.json"
    ),
}


def guest_json(env: Any, arguments: list[str]) -> dict[str, Any]:
    command = " ".join(shlex.quote(part) for part in arguments)
    output = env.runner.exec_capture(command)
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise RuntimeError(f"guest command returned no JSON object: {output}")


def time_command(env: Any, command: str) -> dict[str, Any]:
    if command not in {
        "status",
        "wait-ready",
        "pause",
        "settle-pause",
        "resume",
    }:
        raise ValueError(f"unsupported time command: {command}")
    return guest_json(
        env,
        [
            "python3",
            "/workspace/shared_scripts/time_control.py",
            command,
            "--timeout",
            "30",
        ],
    )


def capture_observation_window(
    env: Any,
    *,
    mode: str,
    duration_ms: int,
    frames_per_observation: int,
    turn: int,
    host_dir: Path,
    hold_paused: bool = False,
) -> dict[str, Any]:
    if mode not in {"live", "paused"}:
        raise ValueError(f"unsupported time mode: {mode}")
    if hold_paused and mode != "paused":
        raise ValueError("hold_paused is valid only for paused observations")
    if duration_ms < 0:
        raise ValueError("duration_ms must be non-negative")
    if frames_per_observation < 1:
        raise ValueError("frames_per_observation must be positive")
    if turn < 0:
        raise ValueError("turn must be non-negative")

    host_dir = host_dir.resolve()
    guest_dir = f"/tmp/weird_cua_observations/turn-{turn:04d}"
    command = [
        "python3",
        "/workspace/shared_scripts/capture_observation_window.py",
        "--mode",
        mode,
        "--duration-ms",
        str(duration_ms),
        "--frames",
        str(frames_per_observation),
        "--output-dir",
        guest_dir,
    ]
    if hold_paused:
        command.append("--hold-paused")
    manifest = guest_json(env, command)

    host_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for index, frame in enumerate(manifest["frames"]):
        host_path = host_dir / f"frame-{index:03d}.png"
        env.runner.copy_from(frame["path"], str(host_path))
        frames.append(
            {
                "path": str(host_path),
                "offset_ms": frame["offset_ms"],
                "target_offset_ms": frame["target_offset_ms"],
            }
        )

    manifest_path = host_dir / "guest-capture-manifest.json"
    env.runner.copy_from(f"{guest_dir}/manifest.json", str(manifest_path))
    time_status = manifest["time_status"]
    return {
        "screen": {
            "path": frames[-1]["path"],
            "format": "png",
            "resolution": [1280, 720],
        },
        "frames": frames,
        "capture_manifest": str(manifest_path),
        "time": {
            "mode": mode,
            "task_time_ms": time_status.get("task_time_ms"),
            "observation_window_ms": duration_ms,
            "frames_per_observation": frames_per_observation,
        },
    }


class EvaluationControl(Protocol):
    def configure(self, values: dict[str, str]) -> None: ...

    def time(self, command: str) -> dict[str, Any]: ...

    def capture(
        self,
        *,
        mode: str,
        duration_ms: int,
        frames_per_observation: int,
        turn: int,
        hold_paused: bool = False,
    ) -> dict[str, Any]: ...

    def collect_artifacts(self) -> None: ...

    @property
    def artifacts_dir(self) -> Path: ...


class LocalEvaluationControl:
    def __init__(self, env: Any):
        self.env = env

    def configure(self, values: dict[str, str]) -> None:
        self.env.env_spec.security.resolved_env.update(values)

    def time(self, command: str) -> dict[str, Any]:
        return time_command(self.env, command)

    @property
    def artifacts_dir(self) -> Path:
        if self.env.episode_dir is None:
            raise RuntimeError("environment has no active episode directory")
        return Path(self.env.episode_dir)

    def capture(
        self,
        *,
        mode: str,
        duration_ms: int,
        frames_per_observation: int,
        turn: int,
        hold_paused: bool = False,
    ) -> dict[str, Any]:
        return capture_observation_window(
            self.env,
            mode=mode,
            duration_ms=duration_ms,
            frames_per_observation=frames_per_observation,
            turn=turn,
            host_dir=self.artifacts_dir / "observations" / f"turn-{turn:04d}",
            hold_paused=hold_paused,
        )

    def collect_artifacts(self) -> None:
        for name, guest_path in COLLECTABLE_ARTIFACTS.items():
            try:
                present = self.env.runner.exec_capture(
                    f"test -s {shlex.quote(guest_path)} && echo present"
                )
                if "present" not in present.split():
                    continue
                self.env.runner.copy_from(guest_path, str(self.artifacts_dir / name))
            except Exception:
                continue


def control_for_environment(env: Any) -> EvaluationControl:
    from .remote import WeirdRemoteGymEnv

    if isinstance(env, WeirdRemoteGymEnv):
        return env.evaluation_control
    return LocalEvaluationControl(env)
