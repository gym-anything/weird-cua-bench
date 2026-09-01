"""Codex CLI computer-use agent isolated with Apple Container.

This evidence-only adapter exists because the installed Gym-Anything agent
sandbox supports Docker and Apptainer but this host has neither available. It
preserves the same action-gateway boundary while using Apple Container, a
fresh staged OAuth seed, and an ephemeral private Codex home.
"""

from __future__ import annotations

import logging
import os
import secrets
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from agents.shared.agent_sandbox import AgentSandbox, SandboxSpec
from agents.shared.cli_harness import build_harness_prompt

from weird_captcha_gym.evaluation.codex_cli import (
    WeirdCodexActionGateway,
    WeirdCodexCliAgent,
)


logger = logging.getLogger(__name__)


def _run(
    args: list[str],
    *,
    timeout: int | None = None,
    cwd: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        cwd=cwd,
    )


class AppleContainerSandbox(AgentSandbox):
    """One ephemeral Apple Container with only logs and staged auth mounted."""

    gateway_bind_host = "0.0.0.0"

    def __init__(self, spec: SandboxSpec, logs_dir: Path):
        super().__init__(spec, logs_dir)
        self.image_tag = f"weird-cua-agent-{spec.name}:{spec.digest()}"
        self.container_name = f"weird-cua-agent-{spec.name}-{os.urandom(4).hex()}"

    def gateway_url(self, port: int) -> str:
        return f"http://host.container.internal:{port}/act"

    def _dockerfile(self) -> str:
        return (
            f"FROM {self.spec.base_image}\n"
            "RUN apt-get update && apt-get install -y --no-install-recommends "
            "curl ca-certificates python3 procps && rm -rf /var/lib/apt/lists/*\n"
            f"RUN {self.spec.install}\n"
            "COPY act /usr/local/bin/act\n"
            "RUN chmod +x /usr/local/bin/act && mkdir -p /logs/work /logs/home\n"
            "WORKDIR /logs/work\n"
        )

    def build(self) -> None:
        if _run(["container", "image", "inspect", self.image_tag]).returncode == 0:
            return
        with tempfile.TemporaryDirectory(prefix="weird-cua-apple-agent-build-") as raw:
            build_dir = Path(raw)
            (build_dir / "act").write_text(self.spec.act_script, encoding="utf-8")
            (build_dir / "Dockerfile").write_text(
                self._dockerfile(),
                encoding="utf-8",
            )
            result = _run(
                [
                    "container",
                    "build",
                    "--progress",
                    "plain",
                    "--tag",
                    self.image_tag,
                    str(build_dir),
                ],
                timeout=1800,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "Apple Container agent image build failed:\n"
                    + result.stdout[-4000:]
                    + result.stderr[-4000:]
                )

    def start(
        self,
        gateway_port: int,
        gateway_token: str,
        container_env: dict[str, str],
    ) -> None:
        self._prepare_logs()
        auth_seed = Path(os.environ.get("WEIRD_CODEX_AUTH_SEED", "")).resolve()
        if not (auth_seed / "auth.json").is_file():
            raise RuntimeError("WEIRD_CODEX_AUTH_SEED is not a staged Codex auth directory")
        env = self._full_env(gateway_port, gateway_token, container_env)
        args = [
            "container",
            "run",
            "--detach",
            "--remove",
            "--name",
            self.container_name,
            "--read-only",
            "--tmpfs",
            "/tmp",
            "--cap-drop",
            "ALL",
            "--cpus",
            "4",
            "--memory",
            "4g",
            "--mount",
            f"type=bind,source={self.logs_dir.resolve()},target=/logs",
            "--mount",
            f"type=bind,source={auth_seed},target=/run/container-auth/codex,readonly",
        ]
        for key, value in env.items():
            args.extend(["--env", f"{key}={value}"])
        args.extend([self.image_tag, "sleep", "infinity"])
        result = _run(args, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(
                "Apple Container agent start failed:\n"
                + result.stdout[-2000:]
                + result.stderr[-2000:]
            )

    def exec(self, command: str, timeout_sec: int) -> subprocess.CompletedProcess[str]:
        wrapped = f"set -o pipefail; ({command}) 2>&1 | tee /logs/cli_stdout.jsonl"
        return _run(
            [
                "container",
                "exec",
                "--workdir",
                "/logs/work",
                self.container_name,
                "bash",
                "-lc",
                wrapped,
            ],
            timeout=timeout_sec,
        )

    def stop(self) -> None:
        _run(["container", "delete", "--force", self.container_name], timeout=60)


class AppleContainerCodexAgent(WeirdCodexCliAgent):
    """General Codex CLI agent using only the screenshot action gateway."""

    def container_env(self) -> dict[str, str]:
        return {}

    def build_cli_command(self) -> str:
        return (
            "export HOME=/tmp/agent-home CODEX_HOME=/tmp/codex-home && "
            "install -d -m 700 \"$HOME\" \"$CODEX_HOME\" && "
            "install -m 600 /run/container-auth/codex/auth.json \"$CODEX_HOME/auth.json\" && "
            "codex login status >/dev/null || { "
            "echo 'Codex authentication preflight failed' >&2; exit 78; } && "
            "codex exec "
            "--dangerously-bypass-approvals-and-sandbox "
            "--skip-git-repo-check "
            "--ignore-user-config "
            "--ignore-rules "
            "--ephemeral "
            "--json "
            "-- \"$(cat /logs/prompt.txt)\""
        )

    def run_episode(self, env: Any, task_description: str | None = None) -> None:
        task = task_description or self.task_description
        resolution = self.display_resolution
        temporal_mode = str(self.agent_args.get("temporal_mode") or "live")
        max_steps = int(
            self.max_steps_override or getattr(env, "max_steps", None) or 50
        )
        logs_dir = (
            Path(self.save_path) / "cli_harness"
            if self.save_path
            else Path(tempfile.mkdtemp(prefix="weird-cua-codex-logs-"))
        )
        logs_dir.mkdir(parents=True, exist_ok=True)
        token = secrets.token_hex(16)
        gateway = WeirdCodexActionGateway(
            env,
            resolution,
            max_steps,
            token,
            temporal_mode=temporal_mode,
            timing_path=logs_dir / "timing.jsonl",
        )
        sandbox = AppleContainerSandbox(self.sandbox_spec(), logs_dir)
        started = False
        port = gateway.start(host=sandbox.gateway_bind_host)
        try:
            sandbox.build()
            sandbox.start(
                gateway_port=port,
                gateway_token=token,
                container_env=self.container_env(),
            )
            started = True
            try:
                prompt = build_harness_prompt(
                    task,
                    (gateway.display_w, gateway.display_h),
                    max_steps,
                    temporal_mode=temporal_mode,
                )
            except TypeError:
                prompt = build_harness_prompt(
                    task,
                    (gateway.display_w, gateway.display_h),
                    max_steps,
                )
            (logs_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
            result = sandbox.exec(self.build_cli_command(), timeout_sec=self.timeout_sec)
            (logs_dir / "cli_exit.txt").write_text(
                f"returncode={result.returncode}\n",
                encoding="utf-8",
            )
            if result.returncode != 0:
                logger.warning(
                    "Apple Container Codex CLI exited with %d; stderr: %s",
                    result.returncode,
                    result.stderr[-2000:],
                )
        except subprocess.TimeoutExpired:
            logger.warning("Apple Container Codex CLI timed out after %ds", self.timeout_sec)
        finally:
            self._transcript = gateway.transcript
            gateway.stop()
            if started:
                sandbox.stop()
            else:
                sandbox.stop()
            self.done = True
