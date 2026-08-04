from __future__ import annotations

import json
from pathlib import Path

import pytest

from weird_captcha_gym.dashboard.export_trajectories import (
    export_trajectory_dashboard,
)


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_trajectory_export_preserves_model_evidence_and_lazy_image_urls(
    tmp_path: Path,
) -> None:
    evaluation = tmp_path / "evaluation"
    run_id = "sample_l1_simplified_live_seed42"
    record = {
        "index": 0,
        "run_id": run_id,
        "environment": "sample_env",
        "env_dir": str(tmp_path / "sample_env"),
        "mechanic_id": "sample",
        "task_id": "sample_d1_simplified_seed_0001",
        "difficulty": 1,
        "interaction": "simplified",
        "time_mode": "live",
        "seed": 42,
        "model": "Qwen/Qwen3.5-9B",
    }
    evaluation.mkdir()
    (evaluation / "manifest.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    _write_json(evaluation / "protocol.json", {"task_play_time_limit_seconds": None})

    task_path = tmp_path / "sample_env" / "tasks" / record["task_id"] / "task.json"
    _write_json(
        task_path,
        {
            "name": "Sample Machine · Difficulty 1 · Simplified",
            "natural_language": "Press the visible target.",
        },
    )
    run_dir = evaluation / "runs" / f"000_{run_id}"
    episode_dir = tmp_path / "episode"
    _write_json(
        run_dir / "done.json",
        {
            "outcome": "benchmark_failure",
            "benchmark_reason": "agent_completed",
            "duration_seconds": 12.5,
            "episode_dir": str(episode_dir),
            "verifier": {"passed": False, "score": 0, "feedback": "Wrong target."},
        },
    )
    episode_dir.mkdir()
    (episode_dir / "realtime_timing.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event": "setup",
                        "fast_io": True,
                        "task_play_time_limit_seconds": None,
                        "task_play_time_limit_enabled": False,
                    }
                ),
                json.dumps(
                    {
                        "event": "turn",
                        "model_ms": 820,
                        "task_time_before_model_ms": 100,
                        "request_attempts": [{"wall_ms": 800}],
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    agent_dir = (
        run_dir
        / "all_runs"
        / "experiment"
        / "Qwen"
        / "Qwen3.5-9B"
        / run_id
        / "run_0"
    )
    _write_json(
        agent_dir / "responses.json",
        {
            "model_responses": ["I will click the target."],
            "parsed_responses": [
                {
                    "actions": [{"mouse": {"left_click": [640, 360]}}],
                    "metadata": {"thought": "Target is centered.", "action_type": "left_click"},
                }
            ],
        },
    )
    (agent_dir / "weird_input_0.png").write_bytes(b"not-decoded-by-exporter")

    document = export_trajectory_dashboard(evaluation)

    assert document["stats"]["runs"] == 1
    assert document["stats"]["model_turns"] == 1
    assert document["stats"]["screenshots"] == 1
    assert document["runs"][0]["title"] == "Sample Machine"
    output = evaluation / "trajectory_dashboard"
    detail = json.loads((output / "data" / "runs" / "000.json").read_text())
    assert detail["instruction"] == "Press the visible target."
    assert detail["setup"]["fast_io"] is True
    assert detail["turns"][0]["response"] == "I will click the target."
    assert detail["turns"][0]["parsed"]["metadata"]["thought"] == "Target is centered."
    assert detail["turns"][0]["click"] == {"x": 640.0, "y": 360.0}
    assert detail["turns"][0]["frames"][0]["url"].startswith("../runs/")
    assert (output / "index.html").is_file()
    assert (output / "static" / "app.js").is_file()


def test_trajectory_output_must_remain_inside_the_evaluation_root(tmp_path: Path) -> None:
    evaluation = tmp_path / "evaluation"
    evaluation.mkdir()
    (evaluation / "manifest.jsonl").write_text(
        json.dumps({"index": 0, "run_id": "missing"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="child of the evaluation root"):
        export_trajectory_dashboard(evaluation, tmp_path / "elsewhere")
