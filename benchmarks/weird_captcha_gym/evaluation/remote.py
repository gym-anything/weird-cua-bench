from __future__ import annotations

from pathlib import Path
from typing import Any

from gym_anything.remote import RemoteGymEnv


WEIRD_CUA_WORKER_CAPABILITY = "weird_cua"


class RemoteEvaluationControl:
    def __init__(self, env: "WeirdRemoteGymEnv"):
        self.env = env

    def configure(self, values: dict[str, str]) -> None:
        response = self.env._request(
            "POST",
            f"/envs/{self.env.env_id}/weird/configure",
            json={"environment": values},
        )
        response.json()

    def time(self, command: str) -> dict[str, Any]:
        response = self.env._request(
            "POST",
            f"/envs/{self.env.env_id}/weird/time",
            json={"command": command},
        )
        return response.json()["status"]

    @property
    def artifacts_dir(self) -> Path:
        return self.env.local_artifacts_dir

    def capture(
        self,
        *,
        mode: str,
        duration_ms: int,
        frames_per_observation: int,
        turn: int,
        hold_paused: bool = False,
    ) -> dict[str, Any]:
        response = self.env._request(
            "POST",
            f"/envs/{self.env.env_id}/weird/capture-window",
            json={
                "mode": mode,
                "duration_ms": duration_ms,
                "frames_per_observation": frames_per_observation,
                "turn": turn,
                "hold_paused": hold_paused,
            },
        )
        observation = response.json()["observation"]
        local_dir = self.artifacts_dir / "observations" / f"turn-{turn:04d}"
        local_dir.mkdir(parents=True, exist_ok=True)
        for index, frame in enumerate(observation["frames"]):
            local_path = local_dir / f"frame-{index:03d}.png"
            self.env.fetch_path(frame["path"], str(local_path))
            frame["path"] = str(local_path)
        observation["screen"]["path"] = observation["frames"][-1]["path"]
        remote_manifest = observation["capture_manifest"]
        local_manifest = local_dir / "guest-capture-manifest.json"
        self.env.fetch_path(remote_manifest, str(local_manifest))
        observation["capture_manifest"] = str(local_manifest)
        return observation

    def collect_artifacts(self) -> None:
        response = self.env._request(
            "POST",
            f"/envs/{self.env.env_id}/weird/collect-artifacts",
            json={},
        )
        for name, remote_path in response.json().get("artifacts", {}).items():
            self.env.fetch_path(remote_path, str(self.artifacts_dir / name))


class WeirdRemoteGymEnv(RemoteGymEnv):
    """Gym Anything's remote environment with Weird CUA protocol controls."""

    def _infer_runner_hint(self) -> str:
        # Gym's master already filters workers by their advertised runner
        # capabilities. The Weird worker advertises this additional key so a
        # mixed fleet cannot route this client to an ordinary Gym worker that
        # lacks the benchmark's fixed clock and frame routes.
        return WEIRD_CUA_WORKER_CAPABILITY

    @property
    def local_artifacts_dir(self) -> Path:
        cache_dir = Path(self._cache_dir)
        path = cache_dir / "weird-cua-evaluation"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def evaluation_control(self) -> RemoteEvaluationControl:
        return RemoteEvaluationControl(self)
