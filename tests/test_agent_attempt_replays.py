from __future__ import annotations

from pathlib import Path

from weird_captcha_gym.tools.render_agent_attempt_replays import (
    _ass_document,
    _outcome_text,
    _pointer_points,
    _provider_error_detail,
    build_segments,
    describe_action,
    frame_for_step,
)


def test_frame_for_step_uses_the_observation_immediately_before_action() -> None:
    frames = {
        -1: Path("observation_-1.png"),
        0: Path("observation_0.png"),
        1: Path("observation_1.png"),
    }

    assert frame_for_step(frames, 0).name == "observation_-1.png"
    assert frame_for_step(frames, 1).name == "observation_0.png"
    assert frame_for_step(frames, 2).name == "observation_1.png"


def test_action_annotations_use_executed_pixel_coordinates() -> None:
    step = {
        "action": "drag_and_drop",
        "args": {"start_x": 10, "start_y": 20, "end_x": 30, "end_y": 40},
        "env_actions": [{"mouse": {"left_click_drag": [[841, 527], [576, 527]]}}],
    }

    assert _pointer_points(step) == [
        (841, 527, "drag_start"),
        (576, 527, "drag_end"),
    ]
    assert describe_action(step) == "DRAG (841, 527) → (576, 527)"


def test_replay_discloses_acceleration_and_never_renders_private_reasoning() -> None:
    frames = {-1: Path("observation_-1.png")}
    step = {
        "step": 0,
        "action": "click",
        "intent": "Press the visible submit control.",
        "reasoning": "private chain of thought must never appear",
        "env_actions": [{"mouse": {"left_click": [900, 700]}}],
    }
    segments = build_segments(frames, [step], Path("blank.png"), 0.75)
    document = _ass_document(
        title="Test Task",
        task_id="test_seed_0001",
        model="gemini-3.5-flash",
        result={"outcome": "failed", "verifier_score": 0},
        segments=segments,
        steps_total=1,
    )

    assert "not continuous screen recording" in document
    assert "Press the visible submit control" in document
    assert "private chain of thought" not in document
    assert "\\pos(900,700)" in document
    assert r"\{\pos(900,700)" not in document


def test_outcome_labels_keep_provider_and_infrastructure_errors_separate() -> None:
    assert _outcome_text({"outcome": "passed", "verifier_score": 100}) == (
        "OutcomePass",
        "RECORDED OUTCOME · PASS · verifier score 100",
    )
    assert "excluded from pass/fail" in _outcome_text({"outcome": "model_api_error"})[1]
    assert "SAFETY BLOCK" in _outcome_text(
        {"outcome": "model_api_error", "provider_error_detail": "safety_block"}
    )[1]
    assert "invalid benchmark outcome" in _outcome_text({"outcome": "infrastructure_error"})[1]


def test_provider_safety_block_is_classified_from_the_preserved_log(tmp_path: Path) -> None:
    log = tmp_path / "attempt.log"
    log.write_text(
        "[gemini-cu] no candidates returned (diagnostic={'block_reason': "
        "'BlockedReason.SAFETY'})\n[gemini-cu] no candidate retries exhausted\n",
        encoding="utf-8",
    )

    assert _provider_error_detail(log) == "safety_block"
