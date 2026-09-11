"""The existing difficulty runner can run a separate audit without overwrites."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


RUNNERS = Path(__file__).resolve().parents[1] / "weird_captcha_gym/difficulty_audits/remaining_39_2026-09-10"


def load(name):
    spec = importlib.util.spec_from_file_location(name, RUNNERS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(tmp_path, custom=True):
    root = tmp_path / "audit"
    root.mkdir()
    source = tmp_path / "source"
    source.mkdir()
    prompt = "Frozen source-review instructions.\n"
    (root / "prompt.md").write_text(prompt)
    manifest = {
        "source_root": str(source),
        "source_revision": "test-revision",
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "cases": [{"case_index": 1, "environment_id": "example_env", "public_name": "Example", "difficulty": 2, "interaction_mode": "full"}],
    }
    if custom:
        manifest["review_wrapper_template"] = (
            "Review {public_name} L{difficulty} {interaction_mode}; source={source_root}; "
            "prompt={prompt_path}; output={output_path}."
        )
    (root / "manifest.json").write_text(json.dumps(manifest))
    return root


@pytest.mark.parametrize("custom", [False, True])
def test_fresh_review_uses_selected_audit_and_preserves_cli_contract(tmp_path, monkeypatch, custom):
    root = prepare(tmp_path, custom)
    module = load("run_reviewer")
    calls = []

    class Process:
        pid = 12345
        returncode = 0

        def communicate(self, wrapper, timeout):
            calls.append((wrapper, timeout))
            (root / "first_pass/001_example_env.json").write_text('{"label":"no"}')

    def popen(command, **kwargs):
        calls.append(command)
        return Process()

    monkeypatch.setattr(module.subprocess, "Popen", popen)
    monkeypatch.setattr("sys.argv", ["run_reviewer.py", "1", "--audit-dir", str(root)])
    with pytest.raises(SystemExit) as result:
        module.main()
    assert result.value.code == 0
    command = calls[0]
    assert command[command.index("--model") + 1] == "gpt-5.6-luna"
    assert 'model_reasoning_effort="max"' in command
    assert "--ignore-user-config" in command
    assert command[command.index("--sandbox") + 1] == "workspace-write"
    assert command[command.index("--cd") + 1] == str(root / "outputs/001_example_env")
    wrapper, timeout = calls[1]
    assert timeout == 2700
    assert str(root / "prompt.md") in wrapper
    assert ("Review Example L2 full" if custom else "independent difficulty audit") in wrapper
    receipt = json.loads((root / "provenance/001_example_env.json").read_text())
    assert receipt["status"] == "completed"
    assert receipt["difficulty"] == 2 and receipt["interaction_mode"] == "full"
    assert receipt["source_revision"] == "test-revision"
    assert receipt["manifest_sha256"] == hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()
    with pytest.raises(AssertionError, match="Never overwrite"):
        module.main()
    assert len(calls) == 2


def test_changed_prompt_is_rejected_before_launch(tmp_path, monkeypatch):
    root = prepare(tmp_path)
    (root / "prompt.md").write_text("Changed instructions")
    module = load("run_reviewer")
    monkeypatch.setattr("sys.argv", ["run_reviewer.py", "1", "--audit-dir", str(root)])
    with pytest.raises(ValueError, match="Frozen audit prompt has changed"):
        module.main()
    assert not (root / "outputs").exists()


def test_queue_forwards_audit_directory(tmp_path, monkeypatch):
    root = prepare(tmp_path)
    module = load("run_queue")
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", run)
    monkeypatch.setattr("sys.argv", ["run_queue.py", "1", "--audit-dir", str(root)])
    with pytest.raises(SystemExit) as result:
        module.main()
    assert result.value.code == 0
    assert calls[0][1:] == [str(RUNNERS / "run_reviewer.py"), "1", "--audit-dir", str(root)]
    assert json.loads((root / "provenance/queue_001.json").read_text())["status"] == "completed"


def test_queue_refuses_already_completed_cases(tmp_path, monkeypatch):
    root = prepare(tmp_path)
    (root / "first_pass").mkdir()
    (root / "first_pass/001_example_env.json").write_text('{"label":"no"}')
    module = load("run_queue")
    monkeypatch.setattr("sys.argv", ["run_queue.py", "1", "--audit-dir", str(root)])
    with pytest.raises(AssertionError):
        module.main()
    assert not (root / "provenance").exists()


@pytest.mark.parametrize("terminal_status", ["completed", "failed", "outer_deadline_exceeded"])
def test_queue_handoff_waits_without_rerunning_existing_case(tmp_path, monkeypatch, terminal_status):
    root = prepare(tmp_path)
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["cases"].append({**manifest["cases"][0], "case_index": 2})
    (root / "manifest.json").write_text(json.dumps(manifest))
    module = load("run_queue")
    calls = []

    def wait(audit_root, case):
        state = json.loads((root / "provenance/queue_001.json").read_text())
        assert state["status"] == "waiting_for_existing_review"
        assert state["wait_for_case_index"] == 2
        calls.append(("wait", case["case_index"]))
        return {"status": terminal_status}

    def run(command, **kwargs):
        calls.append(("run", int(command[2])))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module, "wait_for_case", wait)
    monkeypatch.setattr(module.subprocess, "run", run)
    monkeypatch.setattr("sys.argv", ["run_queue.py", "1", "--audit-dir", str(root), "--wait-for-case", "2"])
    with pytest.raises(SystemExit) as result:
        module.main()
    assert result.value.code == 0
    assert calls == [("wait", 2), ("run", 1)]
    state = json.loads((root / "provenance/queue_001.json").read_text())
    assert state["handoff_receipt_status"] == terminal_status


def test_handoff_wait_requires_terminal_receipt(tmp_path, monkeypatch):
    root = prepare(tmp_path)
    module = load("run_queue")
    provenance = root / "provenance"
    provenance.mkdir()
    path = provenance / "001_example_env.json"
    receipt = {"started_at": module.now(), "outer_case_deadline_seconds": 2700, "status": "running"}
    path.write_text(json.dumps(receipt))
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        path.write_text(json.dumps({**receipt, "status": "completed", "finished_at": module.now()}))

    monkeypatch.setattr(module.time, "sleep", sleep)
    assert module.wait_for_case(root, {"case_index": 1, "environment_id": "example_env"})["status"] == "completed"
    assert sleeps == [1]


def test_handoff_wait_does_not_start_after_expired_receipt(tmp_path):
    root = prepare(tmp_path)
    module = load("run_queue")
    (root / "provenance").mkdir()
    (root / "provenance/001_example_env.json").write_text(json.dumps({
        "started_at": "2000-01-01T00:00:00+00:00", "outer_case_deadline_seconds": 2700, "status": "running"
    }))
    with pytest.raises(TimeoutError, match="no terminal receipt"):
        module.wait_for_case(root, {"case_index": 1, "environment_id": "example_env"})


def test_game_assignment_uses_one_process_for_all_ten_configs(tmp_path, monkeypatch):
    root = prepare(tmp_path)
    manifest = json.loads((root / "manifest.json").read_text())
    configs = [{"case_index": 2 * (level - 1) + offset + 1, "difficulty": level, "interaction_mode": mode} for level in range(1, 6) for offset, mode in enumerate(("full", "simplified"))]
    manifest["cases"] = [{"case_index": 1, "environment_id": "example_env", "public_name": "Example", "review_configurations_json": json.dumps(configs)}]
    manifest["review_wrapper_template"] = "One game: {public_name}; CONFIGURATIONS={review_configurations_json}; prompt={prompt_path}; output={output_path}"
    (root / "manifest.json").write_text(json.dumps(manifest))
    module = load("run_reviewer")
    launches = []

    class Process:
        pid = 12345
        returncode = 0

        def communicate(self, wrapper, timeout):
            assert json.dumps(configs) in wrapper
            assert timeout == 2700
            (root / "first_pass/001_example_env.json").write_text(json.dumps({"case_index": 1, "configuration_reports": configs}))

    def popen(command, **kwargs):
        launches.append(command)
        return Process()

    monkeypatch.setattr(module.subprocess, "Popen", popen)
    monkeypatch.setattr("sys.argv", ["run_reviewer.py", "1", "--audit-dir", str(root)])
    with pytest.raises(SystemExit) as result:
        module.main()
    assert result.value.code == 0 and len(launches) == 1
    receipt = json.loads((root / "provenance/001_example_env.json").read_text())
    assert receipt["status"] == "completed" and "difficulty" not in receipt
