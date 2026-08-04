from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from weird_captcha_gym.evaluation import run_control_matrix


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_main_control_matrix_records_and_passes_no_task_time_limit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    env_dir = repo / "weird_captcha_gym" / "environments" / "sample_env"
    _write_json(
        env_dir / "controls.json",
        {
            "mechanic_id": "sample",
            "interaction": {
                "simplified": {"implemented": True},
                "full": {"implemented": True},
            },
        },
    )
    for interaction in run_control_matrix.INTERACTIONS:
        _write_json(
            env_dir
            / "tasks"
            / f"sample_d1_{interaction}_seed_0001"
            / "task.json",
            {
                "metadata": {
                    "control_condition": {
                        "difficulty": 1,
                        "interaction": interaction,
                    }
                }
            },
        )
    monkeypatch.setattr(run_control_matrix.subprocess, "check_output", lambda *args, **kwargs: "abc123\n")
    output = tmp_path / "evaluation"
    create_args = argparse.Namespace(
        repo_root=repo,
        output_root=output,
        difficulty=1,
        seed=42,
        model="Qwen/Qwen3.5-9B",
        expected_environments=1,
        request_timeout_seconds=300.0,
        request_attempts=1,
        max_steps=200,
        remote_url="http://master:5800",
        vlm_base_url="http://model:8600/v1",
    )
    assert run_control_matrix.create_manifest(create_args) == 0
    protocol = json.loads((output / "protocol.json").read_text())
    assert protocol["max_steps"] == 200
    assert protocol["task_play_time_limit_seconds"] is None

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(run_control_matrix.subprocess, "run", fake_run)
    run_args = argparse.Namespace(
        manifest=output / "manifest.jsonl",
        index=0,
        evaluator="weird-cua-evaluate",
        rerun=False,
    )
    assert run_control_matrix.run_item(run_args) == 0
    assert "--fast-io" in captured["command"]
    assert captured["command"][captured["command"].index("--steps") + 1] == "200"
    assert "--no-play-time-limit" in captured["command"]
