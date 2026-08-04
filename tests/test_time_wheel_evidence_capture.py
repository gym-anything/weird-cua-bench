from __future__ import annotations

from pathlib import Path


def test_time_wheel_capture_adapts_the_shared_server_signature(monkeypatch, tmp_path: Path) -> None:
    """Keep the documented evidence command aligned with the shared smoke helper."""

    from weird_captcha_gym.tools import capture_thirty_year_time_wheel_controllability_evidence as capture

    calls: list[tuple[Path, str, str, Path, str]] = []

    def fake_start_server(
        task_path: Path, mechanic: str, interaction: str, state_dir: Path, setup_seed: str
    ) -> tuple[object, int]:
        calls.append((task_path, mechanic, interaction, state_dir, setup_seed))
        return object(), 47123

    monkeypatch.setattr(capture.browser_smoke, "start_server", fake_start_server)
    task_path = tmp_path / "task.json"
    state_dir = tmp_path / "state"
    process, port = capture.start_capture_server(task_path, "simplified", state_dir)

    assert process is not None
    assert port == 47123
    assert calls == [
        (task_path, capture.MECHANIC, "simplified", state_dir, capture.EVIDENCE_SEED)
    ]
