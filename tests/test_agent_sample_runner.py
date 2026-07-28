from __future__ import annotations

import pickle
import sys
from pathlib import Path

from benchmarks.weird_captcha_gym.tools.run_agent_sample import (
    REPO_ROOT,
    build_command,
    corpus_snapshot,
    is_terminal_model_error_log,
    load_manifest,
    summarize_run,
)


MANIFEST = (
    REPO_ROOT
    / "benchmarks"
    / "weird_captcha_gym"
    / "evaluations"
    / "gemini_3_5_flash_random15_ui_only_fhd_request_retry_20260715"
    / "manifest.json"
)

STARRED_MANIFEST = (
    REPO_ROOT
    / "benchmarks"
    / "weird_captcha_gym"
    / "evaluations"
    / "gemini_3_5_flash_starred15_ui_only_fhd_request_retry_20260716"
    / "manifest.json"
)

STARRED_ENVIRONMENTS = [
    "board_game_captcha_env",
    "cursor_constellation_hunt_env",
    "cursor_lens_reveal_env",
    "exact_change_candy_cascade_env",
    "flat_pack_compliance_env",
    "flat_prisoner_env",
    "input_lag_forklift_env",
    "insider_trading_captcha_env",
    "minecraft_block_grid_env",
    "motion_only_ghost_jigsaw_env",
    "rotate_wrong_thing_upright_env",
    "rotating_keyboard_env",
    "slime_commute_env",
    "specular_lighthouse_relay_env",
    "surreal_apple_on_tree_grid_env",
]


def test_frozen_random_sample_matches_current_75_task_corpus() -> None:
    manifest = load_manifest(MANIFEST)
    population, digest = corpus_snapshot()

    assert len(population) == 75
    assert digest == manifest["selection"]["population_sha256"]
    assert len(manifest["tasks"]) == 15
    assert len({task["task_spec_id"] for task in manifest["tasks"]}) == 15


def test_command_uses_frozen_fairness_protocol() -> None:
    manifest = load_manifest(MANIFEST)
    command = build_command(manifest, manifest["tasks"][0])

    assert command[0] == sys.executable
    assert command[1:4] == ["-m", "gym_anything.cli", "benchmark"]
    assert "GeminiComputerUseAgent" in command
    assert "gemini-3.5-flash" in command
    assert command[command.index("--steps") + 1] == "100"
    assert command[command.index("--seed") + 1] == "42"
    assert "environment=desktop" in command
    assert 'decoding_params={"temperature":1.0,"thinking_level":"high"}' in command
    assert command[command.index("--post-reset-observation-delay") + 1] == "3.0"
    assert any(argument.startswith("task_instruction=") for argument in command)
    assert "no_candidate_retry_delays=[2.0,5.0]" in command
    assert (
        'http_retry_options={"attempts":5,"timeout_ms":180000,"initial_delay":1.0,"max_delay":16.0,'
        '"exp_base":2.0,"jitter":1.0,"http_status_codes":[408,429,500,502,503,504]}'
    ) in command
    assert "--fast-io" not in command


def test_starred_manifest_matches_the_supplied_shared_snapshot() -> None:
    baseline = load_manifest(MANIFEST)
    starred = load_manifest(STARRED_MANIFEST)

    assert starred["protocol"] == baseline["protocol"]
    assert starred["selection"]["sample_size"] == len(STARRED_ENVIRONMENTS) == 15
    assert [Path(task["environment_path"]).name for task in starred["tasks"]] == STARRED_ENVIRONMENTS
    assert len({task["task_spec_id"] for task in starred["tasks"]}) == 15


def test_summarize_run_treats_verifier_failure_as_scientific_outcome(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_0"
    run_dir.mkdir()
    with (run_dir / "info.pkl").open("wb") as handle:
        pickle.dump({"reason": "Agent Completed", "verifier": {"passed": False, "score": 0.0}}, handle)

    # Use a synthetic path beneath the repository so the stored path remains relative.
    repo_run = REPO_ROOT / ".pytest-agent-sample" / "run_0"
    repo_run.mkdir(parents=True, exist_ok=True)
    try:
        (repo_run / "info.pkl").write_bytes((run_dir / "info.pkl").read_bytes())
        result = summarize_run(repo_run, returncode=0, model_error=False)
    finally:
        (repo_run / "info.pkl").unlink(missing_ok=True)
        repo_run.rmdir()
        repo_run.parent.rmdir()

    assert result["outcome"] == "failed"
    assert result["verifier_passed"] is False


def test_summarize_run_keeps_model_api_failure_out_of_benchmark_failures(tmp_path: Path) -> None:
    run_dir = REPO_ROOT / ".pytest-agent-sample" / "run_0"
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        with (run_dir / "info.pkl").open("wb") as handle:
            pickle.dump({"reason": "Agent Completed", "verifier": {"passed": False}}, handle)
        result = summarize_run(run_dir, returncode=0, model_error=True)
    finally:
        (run_dir / "info.pkl").unlink(missing_ok=True)
        run_dir.rmdir()
        run_dir.parent.rmdir()

    assert result["outcome"] == "model_api_error"


def test_transient_empty_response_log_is_not_an_exhausted_model_error() -> None:
    transient = "[gemini-cu] no candidates returned (attempt 1/3, diagnostic={})"
    exhausted = "[gemini-cu] no candidate retries exhausted"

    assert is_terminal_model_error_log(transient) is False
    assert is_terminal_model_error_log(exhausted) is True
    assert is_terminal_model_error_log("[gemini-cu] generate_content error: timeout") is True
