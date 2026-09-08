from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
EVIDENCE = BENCHMARK / "evidence" / "round_four_v2"
ENVIRONMENTS = json.loads((EVIDENCE / "environments.json").read_text())


def test_batch_contains_exactly_the_previous_thirty_five():
    assert len(ENVIRONMENTS) == len(set(ENVIRONMENTS)) == 35
    assert not set(ENVIRONMENTS) & {
        "curtain_call_calendar_env", "orchard_exchange_env",
        "porcelain_turntable_env", "last_cut_studio_env",
    }


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_round_four_configuration_contract(environment):
    mechanic = environment.removesuffix("_env")
    folder = BENCHMARK / "environments" / environment
    controls = json.loads((folder / "controls.json").read_text())
    spec = json.loads((folder / "env.json").read_text())
    task = json.loads((folder / "tasks" / (mechanic + "_seed_0001") / "task.json").read_text())
    settings = json.loads((BENCHMARK / "real_time.json").read_text())["environments"][mechanic]
    split = json.loads((BENCHMARK / "splits" / (mechanic + "_split.json")).read_text())
    expected = {
        f"{mechanic}_d{level}_{interaction}_seed_0001{suffix}"
        for level in range(1, 6)
        for interaction in ("full", "simplified")
        for suffix in ("", "_tpaused")
    }
    assert len(split["variations_tasks"]) == 20
    assert set(split["variations_tasks"]) == expected
    assert set(settings) == {"play_time_seconds", "observation_window_ms", "frames_per_observation"}
    assert spec["runner_options"] == controls["real_time"] == settings
    screen, = [item for item in spec["observation"] if item["type"] in {"rgb_screen", "frame_window"}]
    assert screen["resolution"] == [1920, 1080]
    assert task["difficulty"] == controls["difficulty"][str(controls["baseline"]["difficulty"])]["label"]
    assert task["metadata"]["legacy_agent_sample_population"] is False


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_round_four_published_solution_recording(environment):
    mechanic = environment.removesuffix("_env")
    folder = EVIDENCE / "solution_videos"
    manifest = json.loads((folder / "manifest.json").read_text())
    record = manifest["videos"][mechanic]
    assert len(manifest["videos"]) == 35
    assert record["environment_id"] == environment
    for key in ("server_grade", "direct_grade", "verifier"):
        assert record[key]["passed"] is True
    for kind in ("mp4", "webm", "source_manifest", "export"):
        path = folder / record[kind]
        assert path.is_file() and path.stat().st_size > 0
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record[kind + "_sha256"]
    assert record["media"]["duration_seconds"] > 0
    assert record["viewport"] == {"width": 1920, "height": 1080}
    source = json.loads((folder / record["source_manifest"]).read_text())
    assert source["ok"] and source["source_unchanged"]
    assert source["source_before"] == source["source_after"]
    assert source["console_errors"] == []
