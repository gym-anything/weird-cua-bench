#!/usr/bin/env python3
"""Run one isolated general Codex screenshot-only Turtle Forger attempt."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from weird_captcha_gym.tools.capture_turtle_forger_authoritative_evaluator_evidence import (
    BENCHMARK,
    ENVIRONMENT,
    EVALUATOR,
    ROOT,
    SEED,
    TASK_IDS,
    build_runtime_environment,
    read_json,
    read_jsonl,
    relative,
    sha256,
)


AGENT = (
    "weird_captcha_gym.tools.apple_container_codex_agent:"
    "AppleContainerCodexAgent"
)
AUTH_STAGER = Path(
    "/Users/pranjal/.codex/skills/authenticate-container-agents/"
    "scripts/stage_auth_cache.py"
)


def _json_or_none(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def main() -> None:
    out_dir = (
        ENVIRONMENT / "evidence_docs" / "authoritative_general_codex_attempt"
    ).resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    mode_dir = out_dir / "paused"
    mode_dir.mkdir()
    episode_summary_path = mode_dir / "episode-summary.json"
    agent_args = {
        "timeout_sec": 1200,
        "max_steps": 50,
        "agent_class": "general_codex_cli_screenshot_action_gateway",
    }

    with tempfile.TemporaryDirectory(prefix="turtle-general-codex-") as raw:
        temporary = Path(raw)
        auth_root = temporary / "auth-seed"
        stage = subprocess.run(
            [
                sys.executable,
                str(AUTH_STAGER),
                "--tool",
                "codex",
                "--destination",
                str(auth_root / "codex"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if stage.returncode != 0:
            raise RuntimeError(
                "Codex auth staging failed without launching an agent: "
                + stage.stderr[-1000:]
            )
        runtime_env = build_runtime_environment(temporary, out_dir)
        command = [
            sys.executable,
            "-B",
            str(EVALUATOR),
            "--env-dir",
            str(runtime_env),
            "--task",
            TASK_IDS["paused"],
            "--agent",
            AGENT,
            "--agent-args",
            json.dumps(agent_args, separators=(",", ":")),
            "--time-mode",
            "paused",
            "--seed",
            str(SEED),
            "--steps",
            "50",
            "--request-timeout-seconds",
            "120",
            "--request-attempts",
            "2",
            "--episode-summary-path",
            str(episode_summary_path),
        ]
        run_record = {
            "argv": command,
            "agent_args": agent_args,
            "authentication": {
                "host_login_preserved": True,
                "portable_cache_staged_fresh_for_this_launch": True,
                "staged_seed_mounted_read_only": True,
                "private_writable_codex_home_inside_container": True,
                "container_auth_preflight_required_before_agent": True,
                "credential_contents_logged_or_retained": False,
            },
            "isolation": {
                "agent_runtime": "Apple Container",
                "container_root_read_only": True,
                "container_tmpfs_private": True,
                "task_filesystem_mounted_into_agent": False,
                "agent_mounts": ["episode CLI logs", "read-only staged auth seed"],
                "host_foreground_application": False,
                "environment_vnc_ui_enabled": False,
                "interactive_vnc_client_opened": False,
                "runner_background_virtual_display": True,
                "ephemeral_environment_virtual_machine": True,
                "existing_browser_profile": False,
                "connected_browser_or_desktop_automation": False,
            },
            "evaluation_status": "exploratory_not_approved_for_calibration",
            "deadline_and_retry_boundary": {
                "outer_cli_episode_deadline_seconds": 1200,
                "evaluator_request_timeout_seconds": 120,
                "evaluator_request_attempts": 2,
                "qualification": (
                    "The autonomous Codex CLI manages its own provider calls and does not "
                    "expose a per-provider-request deadline/retry record to this evaluator. "
                    "Therefore this run is an exploratory general-agent attempt, not an "
                    "approved calibration episode."
                ),
            },
        }
        (mode_dir / "run-command.json").write_text(
            json.dumps(run_record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        environment = dict(os.environ)
        environment["WEIRD_CODEX_AUTH_SEED"] = str(auth_root / "codex")
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
        )
        (mode_dir / "evaluator.log").write_text(
            completed.stdout + completed.stderr,
            encoding="utf-8",
        )

    episode_summary = _json_or_none(episode_summary_path)
    episode_dir: Path | None = None
    verifier: dict[str, Any] = {}
    attempts: dict[str, Any] = {}
    cli_exit: str | None = None
    prompt_rule_present = False
    gateway_steps = 0
    missing_input_receipt_errors = 0
    gateway_error_count = 0
    if episode_summary is not None:
        episode_dir = Path(str(episode_summary["episode_dir"])).resolve()
        verifier = (episode_summary.get("info") or {}).get("verifier") or {}
        attempts = episode_summary.get("attempts") or {}
        cli_dir = episode_dir / "cli_harness"
        cli_exit_path = cli_dir / "cli_exit.txt"
        if cli_exit_path.is_file():
            cli_exit = cli_exit_path.read_text(encoding="utf-8").strip()
        prompt_path = cli_dir / "prompt.txt"
        if prompt_path.is_file():
            prompt = prompt_path.read_text(encoding="utf-8")
            prompt_rule_present = (
                "Solve only from screenshots" in prompt
                and "visible controls in the task webpage" in prompt
                and "Developer Tools" in prompt
                and "unrelated tabs" in prompt
                and "`act` command" in prompt
            )
        trajectory = _json_or_none(episode_dir / "trajectory.json") or {}
        gateway_steps = len(trajectory.get("steps") or [])
        cli_stdout_path = cli_dir / "cli_stdout.jsonl"
        if cli_stdout_path.is_file():
            cli_stdout = cli_stdout_path.read_text(encoding="utf-8")
            missing_input_receipt_errors = cli_stdout.count(
                "Chromium did not confirm"
            )
            gateway_error_count = cli_stdout.count("gateway error:")

    if episode_summary is None:
        outcome_class = "infrastructure_error_no_episode_summary"
    elif cli_exit == "returncode=78":
        outcome_class = "authentication_error_preflight"
    elif verifier.get("passed") is True:
        outcome_class = "general_codex_screenshot_only_pass_exploratory"
    elif completed.returncode != 0:
        outcome_class = "infrastructure_or_agent_runtime_error"
    else:
        outcome_class = "general_codex_screenshot_only_attempt_no_pass"

    sources = {
        "capture_driver": Path(__file__).resolve(),
        "apple_container_agent": BENCHMARK / "tools" / "apple_container_codex_agent.py",
        "evaluator": EVALUATOR,
        "runner": BENCHMARK / "runner.py",
        "temporal_gateway": BENCHMARK / "evaluation" / "codex_cli.py",
        "environment": ENVIRONMENT / "env.json",
        "controls": ENVIRONMENT / "controls.json",
        "task": ENVIRONMENT / "tasks" / "turtle_forger_seed_0001" / "task.json",
    }
    summary = {
        "environment": "Turtle Forger",
        "mode": "paused",
        "agent": "general Codex CLI via screenshot action gateway",
        "model": "Codex CLI account default; not pinned by the evidence driver",
        "evaluator_returncode": completed.returncode,
        "episode_dir": relative(episode_dir, out_dir) if episode_dir else None,
        "episode_summary": relative(episode_summary_path, out_dir)
        if episode_summary_path.is_file()
        else None,
        "cli_exit": cli_exit,
        "gateway_steps": gateway_steps,
        "gateway_error_count": gateway_error_count,
        "missing_input_receipt_errors": missing_input_receipt_errors,
        "verifier": verifier,
        "attempts": attempts,
        "visible_task_ui_only_rule_present": prompt_rule_present,
        "outcome_class": outcome_class,
        "approved_calibration_episode": False,
        "calibration_exclusion_reason": (
            "Codex CLI internal provider requests do not expose the benchmark's required "
            "per-request deadline and single retry-layer record, and the model was not pinned."
        ),
        "isolation": run_record["isolation"],
        "authentication": run_record["authentication"],
        "deadline_and_retry_boundary": run_record["deadline_and_retry_boundary"],
        "source_sha256": {name: sha256(path) for name, path in sources.items()},
        "evidence_boundary": (
            "This is a real general Codex screenshot-action-gateway attempt retained as its "
            "actual outcome. It is not human/VNC evidence and is excluded from empirical "
            "difficulty calibration because the autonomous CLI does not expose the required "
            "provider-request deadline/retry telemetry."
        ),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"outcome_class": outcome_class, "evidence": str(out_dir)},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
