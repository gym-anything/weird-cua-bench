from __future__ import annotations

import json
from pathlib import Path

import pytest

from extras.research.controllability.creation_audit import method


def test_defaults_and_packaged_prompts_exist() -> None:
    args = method.build_parser().parse_args(["--env-dir", "rotating_keyboard_env"])

    assert args.model == "gpt-5.6-luna"
    assert args.reasoning_effort == "max"
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


@pytest.mark.parametrize(
    ("model", "effort"),
    [("gpt-6-astra", "low"), ("gpt-5.6-sol", "xhigh"), ("gpt-5.6-luna", "max")],
)
def test_codex_commands_start_and_resume_named_sessions(
    tmp_path: Path, model: str, effort: str
) -> None:
    binary = Path("/usr/bin/true")
    fresh = method._codex_command(
        binary,
        "create",
        workspace=tmp_path,
        model=model,
        reasoning_effort=effort,
        session_id=None,
    )
    resumed = method._codex_command(
        binary,
        "continue",
        workspace=tmp_path,
        model=model,
        reasoning_effort=effort,
        session_id="creator-session",
    )

    assert fresh[:3] == [str(binary), "exec", "--ignore-user-config"]
    assert "--cd" in fresh
    assert "resume" not in fresh
    assert resumed[:4] == [str(binary), "exec", "resume", "--ignore-user-config"]
    for command in (fresh, resumed):
        assert "--yolo" in command
        assert command[command.index("--model") + 1] == model
        assert f'model_reasoning_effort="{effort}"' in command
        assert "--ephemeral" not in command
        for feature in method.DISABLED_INTERACTIVE_FEATURES:
            index = command.index(feature)
            assert command[index - 1] == "--disable"
    assert resumed[-2:] == ["creator-session", "continue"]


def test_session_id_is_read_from_codex_jsonl() -> None:
    output = "\n".join(
        [
            json.dumps({"type": "item.completed", "item": {"text": "starting"}}),
            json.dumps({"type": "thread.started", "thread_id": "thread-123"}),
        ]
    )

    assert method._session_id_from_jsonl(output) == "thread-123"


@pytest.mark.parametrize("with_selection", [False, True])
def test_loop_keeps_creator_and_uses_fresh_auditors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, with_selection: bool
) -> None:
    environment = "demo_env"
    target = tmp_path / method.ENVIRONMENTS_ROOT / environment
    target.mkdir(parents=True)
    audits = tmp_path / "audits"
    logs = tmp_path / "logs"
    calls: list[dict[str, object]] = []
    new_sessions = iter(["creator-session", "auditor-one", "auditor-two"])
    selection_file = tmp_path / "selection.json" if with_selection else None
    survey_root = tmp_path / "survey" if with_selection else None
    if with_selection:
        assert selection_file is not None and survey_root is not None
        survey_root.mkdir()
        selection_file.write_text(json.dumps({"picks": [{"env_dir": environment}]}))

    def fake_invoke(
        _binary: Path,
        prompt: str,
        *,
        phase: str,
        session_id: str | None = None,
        output_last_message: Path | None = None,
        **_kwargs: object,
    ) -> str:
        assert _kwargs["model"] == "gpt-5.6-luna"
        assert _kwargs["reasoning_effort"] == "max"
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
        model=method.DEFAULT_MODEL,
        reasoning_effort=method.DEFAULT_REASONING_EFFORT,
        timeout_seconds=30,
        blind_nudges=1,
        audit_rounds=3,
        start_idx=0,
        session_id=None,
        selection_file=selection_file,
        survey_root=survey_root,
    )

    assert result == 0
    assert len(calls) == 7
    if with_selection:
        for call in calls:
            assert str(selection_file) in call["prompt"]
            assert str(survey_root) in call["prompt"]
            assert "read-only source material" in call["prompt"]
    metadata = json.loads((logs / f"{environment}.jsonl").read_text().splitlines()[0])
    assert metadata["model"] == "gpt-5.6-luna"
    assert metadata["reasoning_effort"] == "max"
    assert metadata["selection_file"] == (
        str(selection_file) if with_selection else None
    )
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


@pytest.mark.parametrize("missing", ["selection", "survey"])
def test_selection_requires_both_paths(tmp_path: Path, missing: str) -> None:
    with pytest.raises(ValueError, match="supplied together"):
        method._selection_context(
            "demo_env",
            None if missing == "selection" else tmp_path / "selection.json",
            None if missing == "survey" else tmp_path,
        )


@pytest.mark.parametrize(
    "selection",
    [
        {}, [], {"picks": {}}, {"picks": []},
        {"picks": [{"env_dir": "other_env"}]},
        {"picks": [{"env_dir": "demo_env"}] * 2},
    ],
)
def test_selection_rejects_missing_or_ambiguous_target(
    tmp_path: Path, selection: object
) -> None:
    selection_file = tmp_path / "selection.json"
    selection_file.write_text(json.dumps(selection))
    with pytest.raises(ValueError, match="picks list|exactly one"):
        method._selection_context("demo_env", selection_file, tmp_path)


def test_selection_rejects_missing_sources(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Survey directory"):
        method._selection_context(
            "demo_env", tmp_path / "selection.json", tmp_path / "missing"
        )
    with pytest.raises(FileNotFoundError):
        method._selection_context("demo_env", tmp_path / "selection.json", tmp_path)


def test_main_passes_defaults_and_source_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(**kwargs: object) -> int:
        assert kwargs["model"] == "gpt-5.6-luna"
        assert kwargs["reasoning_effort"] == "max"
        assert kwargs["selection_file"] == tmp_path / "selection.json"
        assert kwargs["survey_root"] == tmp_path / "survey"
        return 2

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(method, "run_creation_audit", fake_run)
    assert method.main(
        [
            "--env-dir", "demo_env", "--workspace", str(tmp_path),
            "--selection-file", "selection.json", "--survey-root", "survey",
            "--codex-bin", "/usr/bin/true",
        ]
    ) == 2


def test_construction_prompt_uses_supplied_paths() -> None:
    prompt = (
        method._memory_dir().parent / "memory_construction" / "creation_prompt.md"
    ).read_text(encoding="utf-8")
    assert "--selection-file" in prompt
    assert "--survey-root" in prompt
    assert "/Users/" not in prompt
