from __future__ import annotations

import json
from pathlib import Path

import pytest

from extras.research.controllability.creation_audit import method


def test_defaults_and_packaged_prompts_exist() -> None:
    args = method.build_parser().parse_args(["--env-dir", "rotating_keyboard_env"])

    assert args.model == "gpt-5.6-sol"
    assert args.reasoning_effort == "xhigh"
    assert args.blind_nudges == 1
    assert args.audit_rounds == 3
    assert (method._memory_dir() / "creation_prompt.md").is_file()
    assert (method._memory_dir() / "audit_prompt.md").is_file()


def test_audit_prompt_names_the_three_axes_and_forbids_edits() -> None:
    prompt = (method._memory_dir() / "audit_prompt.md").read_text(encoding="utf-8")

    assert "Difficulty baseline" in prompt
    assert "Interaction" in prompt
    assert "Real time" in prompt
    assert "evidence" in prompt
    assert "Do not fix them" in prompt
    assert "Changing the uncontrolled task" in prompt
    assert "AUDIT_VERDICT: PASS" in prompt


def test_codex_commands_start_and_resume_named_sessions(tmp_path: Path) -> None:
    binary = Path("/usr/bin/true")
    fresh = method._codex_command(
        binary,
        "create",
        workspace=tmp_path,
        model="gpt-5.6-sol",
        reasoning_effort="xhigh",
        session_id=None,
    )
    resumed = method._codex_command(
        binary,
        "continue",
        workspace=tmp_path,
        model="gpt-5.6-sol",
        reasoning_effort="xhigh",
        session_id="creator-session",
    )

    assert fresh[:3] == [str(binary), "exec", "--yolo"]
    assert "--cd" in fresh
    assert "resume" not in fresh
    assert resumed[:4] == [str(binary), "exec", "resume", "--yolo"]
    assert resumed[-2:] == ["creator-session", "continue"]


def test_session_id_is_read_from_codex_jsonl() -> None:
    output = "\n".join(
        [
            json.dumps({"type": "item.completed", "item": {"text": "starting"}}),
            json.dumps({"type": "thread.started", "thread_id": "thread-123"}),
        ]
    )

    assert method._session_id_from_jsonl(output) == "thread-123"


def test_loop_keeps_creator_and_uses_fresh_auditors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = "demo_env"
    target = tmp_path / method.ENVIRONMENTS_ROOT / environment
    target.mkdir(parents=True)
    audits = tmp_path / "audits"
    logs = tmp_path / "logs"
    calls: list[dict[str, object]] = []
    new_sessions = iter(["creator-session", "auditor-one", "auditor-two"])

    def fake_invoke(
        _binary: Path,
        prompt: str,
        *,
        phase: str,
        session_id: str | None = None,
        output_last_message: Path | None = None,
        **_kwargs: object,
    ) -> str:
        result = session_id or next(new_sessions)
        calls.append(
            {
                "prompt": prompt,
                "phase": phase,
                "session_id": session_id,
                "result": result,
                "output_last_message": output_last_message,
            }
        )
        if output_last_message is not None:
            output_last_message.parent.mkdir(parents=True, exist_ok=True)
            output_last_message.write_text(
                f"last message from {result}",
                encoding="utf-8",
            )
        if phase == "audit 1 report":
            (audits / f"audit_{environment}.md").write_text(
                "Complete first audit.\n"
                "AUDIT_VERDICT: REVISION_REQUIRED\n",
                encoding="utf-8",
            )
        if phase == "audit 2 report":
            (audits / f"audit_{environment}.md").write_text(
                "Complete second audit.\nAUDIT_VERDICT: PASS\n",
                encoding="utf-8",
            )
        return result

    monkeypatch.setattr(method, "_invoke_codex", fake_invoke)

    result = method.run_creation_audit(
        environment=environment,
        workspace=tmp_path,
        memory_dir=method._memory_dir(),
        audits_dir=audits,
        logs_dir=logs,
        codex_bin=Path("/usr/bin/true"),
        model="gpt-5.6-sol",
        reasoning_effort="xhigh",
        timeout_seconds=30,
        blind_nudges=1,
        audit_rounds=3,
        start_idx=0,
        session_id=None,
    )

    assert result == 0
    assert len(calls) == 7
    assert calls[0]["result"] == "creator-session"
    assert calls[1]["session_id"] == "creator-session"
    assert calls[2]["result"] == "auditor-one"
    assert calls[3]["session_id"] == "auditor-one"
    assert calls[4]["session_id"] == "creator-session"
    assert calls[5]["result"] == "auditor-two"
    assert calls[6]["session_id"] == "auditor-two"
    assert calls[3]["output_last_message"] != (
        audits / f"audit_{environment}.md"
    )
    assert calls[6]["output_last_message"] != (
        audits / f"audit_{environment}.md"
    )
    assert (
        audits / f"audit_{environment}.md"
    ).read_text() == "Complete second audit.\nAUDIT_VERDICT: PASS\n"


def test_loop_stops_on_a_final_failed_audit_without_an_unchecked_creator_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = "demo_env"
    target = tmp_path / method.ENVIRONMENTS_ROOT / environment
    target.mkdir(parents=True)
    audits = tmp_path / "audits"
    calls: list[str] = []
    new_sessions = iter(["creator-session", "auditor-one", "auditor-two"])

    def fake_invoke(
        _binary: Path,
        _prompt: str,
        *,
        phase: str,
        session_id: str | None = None,
        output_last_message: Path | None = None,
        **_kwargs: object,
    ) -> str:
        result = session_id or next(new_sessions)
        calls.append(phase)
        if output_last_message is not None:
            output_last_message.parent.mkdir(parents=True, exist_ok=True)
            output_last_message.write_text("short summary", encoding="utf-8")
        if phase in {"audit 1 report", "audit 2 report"}:
            audits.mkdir(parents=True, exist_ok=True)
            (audits / f"audit_{environment}.md").write_text(
                "Supported issue remains.\n"
                "AUDIT_VERDICT: REVISION_REQUIRED\n",
                encoding="utf-8",
            )
        return result

    monkeypatch.setattr(method, "_invoke_codex", fake_invoke)

    result = method.run_creation_audit(
        environment=environment,
        workspace=tmp_path,
        memory_dir=method._memory_dir(),
        audits_dir=audits,
        logs_dir=tmp_path / "logs",
        codex_bin=Path("/usr/bin/true"),
        model="gpt-5.6-sol",
        reasoning_effort="xhigh",
        timeout_seconds=30,
        blind_nudges=1,
        audit_rounds=2,
        start_idx=0,
        session_id=None,
    )

    assert result == 2
    assert calls.count("creator response to audit 1") == 1
    assert "creator response to audit 2" not in calls


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("details\nAUDIT_VERDICT: PASS\n", method.AUDIT_PASS),
        (
            "details\nAUDIT_VERDICT: REVISION_REQUIRED\n",
            method.AUDIT_REVISION_REQUIRED,
        ),
    ],
)
def test_audit_verdict_requires_one_structured_marker(
    text: str, expected: str
) -> None:
    assert method._audit_verdict(text) == expected


def test_audit_verdict_rejects_missing_or_conflicting_markers() -> None:
    with pytest.raises(RuntimeError, match="exactly one"):
        method._audit_verdict("Verdict: pass")
    with pytest.raises(RuntimeError, match="exactly one"):
        method._audit_verdict(
            "AUDIT_VERDICT: PASS\n"
            "AUDIT_VERDICT: REVISION_REQUIRED\n"
        )


def test_resume_requires_creator_session(tmp_path: Path) -> None:
    target = tmp_path / method.ENVIRONMENTS_ROOT / "demo_env"
    target.mkdir(parents=True)

    with pytest.raises(ValueError, match="session-id"):
        method.run_creation_audit(
            environment="demo_env",
            workspace=tmp_path,
            memory_dir=method._memory_dir(),
            audits_dir=tmp_path / "audits",
            logs_dir=tmp_path / "logs",
            codex_bin=Path("/usr/bin/true"),
            model="gpt-5.6-sol",
            reasoning_effort="xhigh",
            timeout_seconds=30,
            blind_nudges=1,
            audit_rounds=2,
            start_idx=1,
            session_id=None,
        )
