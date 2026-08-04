"""Run a creation and independent audit loop for one Weird CUA environment."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import uuid
from pathlib import Path
from typing import Sequence


DEFAULT_MODEL = "gpt-5.6-sol"
DEFAULT_REASONING_EFFORT = "xhigh"
DEFAULT_TIMEOUT_SECONDS = 7200
DEFAULT_BLIND_NUDGES = 1
DEFAULT_AUDIT_ROUNDS = 3
ENVIRONMENTS_ROOT = Path("weird_captcha_gym/environments")
AUDIT_PASS = "PASS"
AUDIT_REVISION_REQUIRED = "REVISION_REQUIRED"
DESKTOP_ISOLATION_RULE = (
    "Never control the user's live browser, desktop, mouse, keyboard, or "
    "foreground applications. Do not use the in-app Browser, connected Chrome, "
    "Computer Use, AppleScript, osascript, open, or an existing browser profile. "
    "Browser checks may run only as isolated headless background processes with "
    "fresh temporary profiles. If that is impossible, report missing evidence."
)
DISABLED_INTERACTIVE_FEATURES = (
    "apps",
    "browser_use",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "in_app_browser",
    "computer_use",
)


def _repo_root() -> Path:
    root = Path(__file__).resolve().parents[4]
    if not (root / "weird_captcha_gym").is_dir():
        raise RuntimeError(
            f"Could not locate the Weird CUA Bench repository from {__file__}"
        )
    return root


def _memory_dir() -> Path:
    return Path(__file__).resolve().parent / "memory"


def _resolve_codex(explicit: str | None) -> Path:
    candidate = explicit or os.environ.get("CODEX_BIN") or shutil.which("codex")
    if not candidate:
        raise RuntimeError(
            "Could not find the Codex CLI. Pass --codex-bin or set CODEX_BIN."
        )
    path = Path(candidate).expanduser()
    if not path.is_file():
        raise RuntimeError(f"Codex CLI not found: {path}")
    return path.resolve()


def _environment_name(value: str) -> str:
    name = Path(value.rstrip("/")).name
    if not name or name != value.rstrip("/").split("/")[-1]:
        raise argparse.ArgumentTypeError(f"Invalid environment directory: {value!r}")
    return name


def _initial_prompt(
    environment: str,
    creation_prompt: Path,
    evidence_dir: Path,
) -> str:
    target = ENVIRONMENTS_ROOT / environment
    return (
        f"Read @{creation_prompt} and follow it. "
        f"The target environment is @{target}. "
        f"Write the required evidence to @{evidence_dir}. "
        "Do not ask for input. Do not stop after writing a plan. "
        f"{DESKTOP_ISOLATION_RULE}"
    )


def _nudge_prompt(creation_prompt: Path, evidence_dir: Path) -> str:
    return (
        f"Reread @{creation_prompt}. You have not completed the task yet. "
        f"Finish the implementation and the evidence in @{evidence_dir}. "
        f"{DESKTOP_ISOLATION_RULE}"
    )


def _audit_explore_prompt() -> str:
    return (
        "Deep explore this repository to understand what it is about and how "
        "its individual components work. Inspect files and existing artifacts "
        "directly. Do not modify any files. "
        f"{DESKTOP_ISOLATION_RULE}"
    )


def _audit_run_prompt(
    environment: str,
    audit_prompt: Path,
    evidence_dir: Path,
    audit_path: Path,
) -> str:
    target = ENVIRONMENTS_ROOT / environment
    return (
        f"Read @{audit_prompt} and follow it. "
        f"The target environment is @{target}. "
        f"The creator's evidence is @{evidence_dir}. "
        f"Save the complete audit to @{audit_path}. "
        "Do not modify the implementation. "
        f"{DESKTOP_ISOLATION_RULE}"
    )


def _audit_feedback_prompt(audit_text: str, evidence_dir: Path) -> str:
    return (
        "An independent audit of your work was performed. Here is the complete "
        f"audit:\n\n{audit_text}\n\nFix the supported issues. Re-run the relevant "
        f"checks and update the evidence in @{evidence_dir}. Do not merely edit "
        "the written claims. Never change the original uncontrolled task to make "
        "it fit a chosen difficulty level. Move the exact original configuration "
        "to its appropriate level instead. "
        f"{DESKTOP_ISOLATION_RULE}"
    )


def _audit_verdict(audit_text: str) -> str:
    markers = [
        line.removeprefix("AUDIT_VERDICT:").strip()
        for line in audit_text.splitlines()
        if line.startswith("AUDIT_VERDICT:")
    ]
    if len(markers) != 1 or markers[0] not in {
        AUDIT_PASS,
        AUDIT_REVISION_REQUIRED,
    }:
        raise RuntimeError(
            "Independent audit must contain exactly one final "
            "AUDIT_VERDICT: PASS or AUDIT_VERDICT: REVISION_REQUIRED marker"
        )
    return markers[0]


def _codex_command(
    binary: Path,
    prompt: str,
    *,
    workspace: Path,
    model: str,
    reasoning_effort: str,
    session_id: str | None,
    output_last_message: Path | None = None,
) -> list[str]:
    isolated_options = ["--ignore-user-config"]
    for feature in DISABLED_INTERACTIVE_FEATURES:
        isolated_options.extend(["--disable", feature])
    if session_id:
        command = [
            str(binary),
            "exec",
            "resume",
            *isolated_options,
            "--yolo",
            "--model",
            model,
            "-c",
            f'model_reasoning_effort="{reasoning_effort}"',
            "--json",
        ]
    else:
        command = [
            str(binary),
            "exec",
            *isolated_options,
            "--yolo",
            "--model",
            model,
            "-c",
            f'model_reasoning_effort="{reasoning_effort}"',
            "--cd",
            str(workspace),
            "--json",
        ]
    if output_last_message is not None:
        command.extend(["--output-last-message", str(output_last_message)])
    if session_id:
        command.append(session_id)
    command.append(prompt)
    return command


def _session_id_from_jsonl(output: str) -> str | None:
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started" and event.get("thread_id"):
            return str(event["thread_id"])
    return None


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        process.wait(timeout=5)
    except (ProcessLookupError, PermissionError, subprocess.TimeoutExpired):
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def _invoke_codex(
    binary: Path,
    prompt: str,
    *,
    workspace: Path,
    model: str,
    reasoning_effort: str,
    timeout_seconds: int,
    log_path: Path,
    phase: str,
    session_id: str | None = None,
    output_last_message: Path | None = None,
) -> str:
    command = _codex_command(
        binary,
        prompt,
        workspace=workspace,
        model=model,
        reasoning_effort=reasoning_effort,
        session_id=session_id,
        output_last_message=output_last_message,
    )
    process = subprocess.Popen(
        command,
        cwd=workspace,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        text=True,
    )
    try:
        output, _ = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_group(process)
        raise TimeoutError(
            f"Codex timed out during {phase} after {timeout_seconds}s"
        ) from exc

    output = output or ""
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n=== {phase} ===\n")
        log.write(output)
        if output and not output.endswith("\n"):
            log.write("\n")
    if output:
        print(output, end="" if output.endswith("\n") else "\n")

    if process.returncode != 0:
        raise RuntimeError(
            f"Codex failed during {phase} with exit code {process.returncode}"
        )

    observed_session = _session_id_from_jsonl(output)
    if session_id:
        return session_id
    if not observed_session:
        raise RuntimeError(f"Codex did not report a session id during {phase}")
    return observed_session


def run_creation_audit(
    *,
    environment: str,
    workspace: Path,
    memory_dir: Path,
    audits_dir: Path,
    logs_dir: Path,
    codex_bin: Path,
    model: str,
    reasoning_effort: str,
    timeout_seconds: int,
    blind_nudges: int,
    audit_rounds: int,
    start_idx: int,
    session_id: str | None,
) -> int:
    target = workspace / ENVIRONMENTS_ROOT / environment
    if not target.is_dir():
        raise FileNotFoundError(f"Unknown environment directory: {target}")
    if start_idx > 0 and not session_id:
        raise ValueError(
            "--session-id is required when --start-idx is greater than zero"
        )
    if min(blind_nudges, start_idx) < 0 or audit_rounds < 1:
        raise ValueError(
            "Blind nudges and --start-idx must be nonnegative; "
            "audit rounds must be positive"
        )

    creation_prompt = memory_dir / "creation_prompt.md"
    audit_prompt = memory_dir / "audit_prompt.md"
    for prompt_path in (creation_prompt, audit_prompt):
        if not prompt_path.is_file():
            raise FileNotFoundError(f"Missing prompt: {prompt_path}")

    evidence_dir = target / "evidence_docs"
    audits_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{environment}.jsonl"
    audit_path = audits_dir / f"audit_{environment}.md"
    creator_session = session_id
    ran_audit = False

    with log_path.open("w", encoding="utf-8") as log:
        log.write(
            json.dumps(
                {
                    "environment": environment,
                    "workspace": str(workspace),
                    "model": model,
                    "reasoning_effort": reasoning_effort,
                    "blind_nudges": blind_nudges,
                    "audit_rounds": audit_rounds,
                    "start_idx": start_idx,
                    "creator_session": creator_session,
                    "run_id": str(uuid.uuid4()),
                },
                sort_keys=True,
            )
            + "\n"
        )

    if start_idx <= 0:
        print("\n=== Initial creation ===")
        creator_session = _invoke_codex(
            codex_bin,
            _initial_prompt(environment, creation_prompt, evidence_dir),
            workspace=workspace,
            model=model,
            reasoning_effort=reasoning_effort,
            timeout_seconds=timeout_seconds,
            log_path=log_path,
            phase="initial creation",
        )

    assert creator_session is not None

    for index in range(blind_nudges):
        phase_idx = index + 1
        if start_idx > phase_idx:
            continue
        print(f"\n=== Blind recheck {index + 1} ===")
        _invoke_codex(
            codex_bin,
            _nudge_prompt(creation_prompt, evidence_dir),
            workspace=workspace,
            model=model,
            reasoning_effort=reasoning_effort,
            timeout_seconds=timeout_seconds,
            log_path=log_path,
            phase=f"blind recheck {index + 1}",
            session_id=creator_session,
        )

    for index in range(audit_rounds):
        phase_idx = blind_nudges + index + 1
        if start_idx > phase_idx:
            continue
        ran_audit = True
        print(f"\n=== Independent audit {index + 1} ===")
        audit_path.unlink(missing_ok=True)
        audit_last_message_path = (
            logs_dir / f"{environment}.audit-{index + 1}.last.md"
        )
        audit_last_message_path.unlink(missing_ok=True)
        auditor_session = _invoke_codex(
            codex_bin,
            _audit_explore_prompt(),
            workspace=workspace,
            model=model,
            reasoning_effort=reasoning_effort,
            timeout_seconds=timeout_seconds,
            log_path=log_path,
            phase=f"audit {index + 1} repository exploration",
        )
        _invoke_codex(
            codex_bin,
            _audit_run_prompt(environment, audit_prompt, evidence_dir, audit_path),
            workspace=workspace,
            model=model,
            reasoning_effort=reasoning_effort,
            timeout_seconds=timeout_seconds,
            log_path=log_path,
            phase=f"audit {index + 1} report",
            session_id=auditor_session,
            output_last_message=audit_last_message_path,
        )
        if (
            not audit_path.is_file()
            or not audit_path.read_text(encoding="utf-8").strip()
        ):
            raise RuntimeError(
                f"Independent audit {index + 1} produced no report at {audit_path}"
            )

        audit_text = audit_path.read_text(encoding="utf-8")
        verdict = _audit_verdict(audit_text)
        if verdict == AUDIT_PASS:
            print(
                "\nCreation and audit passed: "
                f"environment={environment}, creator_session={creator_session}, "
                f"audit={audit_path}"
            )
            return 0
        if index + 1 == audit_rounds:
            print(
                "\nCreation and audit stopped with unresolved findings: "
                f"environment={environment}, creator_session={creator_session}, "
                f"audit={audit_path}"
            )
            return 2

        print(f"\n=== Creator response to audit {index + 1} ===")
        _invoke_codex(
            codex_bin,
            _audit_feedback_prompt(audit_text, evidence_dir),
            workspace=workspace,
            model=model,
            reasoning_effort=reasoning_effort,
            timeout_seconds=timeout_seconds,
            log_path=log_path,
            phase=f"creator response to audit {index + 1}",
            session_id=creator_session,
        )

    if not ran_audit:
        raise RuntimeError("No independent audit ran for the requested phase range")
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="weird-cua-creation-audit",
        description="Create and independently audit controllability for one environment.",
    )
    parser.add_argument("--env-dir", required=True, type=_environment_name)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--reasoning-effort", default=DEFAULT_REASONING_EFFORT)
    parser.add_argument("--blind-nudges", type=int, default=DEFAULT_BLIND_NUDGES)
    parser.add_argument("--audit-rounds", type=int, default=DEFAULT_AUDIT_ROUNDS)
    parser.add_argument("--start-idx", type=int, default=0)
    parser.add_argument("--session-id")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--memory-dir", type=Path)
    parser.add_argument("--audits-dir", type=Path)
    parser.add_argument("--logs-dir", type=Path)
    parser.add_argument("--codex-bin")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workspace = (args.workspace or _repo_root()).resolve()
    memory_dir = (args.memory_dir or _memory_dir()).resolve()
    audits_dir = (args.audits_dir or workspace / "audits" / "controllability").resolve()
    logs_dir = (
        args.logs_dir or workspace / "creation_audit_logs" / "controllability"
    ).resolve()
    return run_creation_audit(
        environment=args.env_dir,
        workspace=workspace,
        memory_dir=memory_dir,
        audits_dir=audits_dir,
        logs_dir=logs_dir,
        codex_bin=_resolve_codex(args.codex_bin),
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        timeout_seconds=args.timeout_seconds,
        blind_nudges=args.blind_nudges,
        audit_rounds=args.audit_rounds,
        start_idx=args.start_idx,
        session_id=args.session_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
