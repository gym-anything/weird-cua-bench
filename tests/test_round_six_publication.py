from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
EVIDENCE = BENCHMARK / "evidence" / "incubator_batch_round_six_3d_v1"
ENVIRONMENTS = json.loads((EVIDENCE / "environments.json").read_text())


def test_round_six_contains_fifteen_distinct_environments():
    assert len(ENVIRONMENTS) == len(set(ENVIRONMENTS)) == 15
    assert not set(ENVIRONMENTS) & {
        "curtain_call_calendar_env", "orchard_exchange_env",
        "porcelain_turntable_env", "last_cut_studio_env",
    }


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_round_six_launch_and_configuration_contract(environment, tmp_path):
    mechanic = environment.removesuffix("_env")
    folder = BENCHMARK / "environments" / environment
    controls = json.loads((folder / "controls.json").read_text())
    spec = json.loads((folder / "env.json").read_text())
    task_folder = folder / "tasks" / (mechanic + "_seed_0001")
    task = json.loads((task_folder / "task.json").read_text())
    settings = json.loads((BENCHMARK / "real_time.json").read_text())["environments"][mechanic]
    split = json.loads((BENCHMARK / "splits" / (mechanic + "_split.json")).read_text())
    expected = {
        f"{mechanic}_d{level}_{interaction}_seed_0001"
        for level in range(1, 6) for interaction in ("full", "simplified")
    }
    generated = materialize_environment(folder, tmp_path / "first")
    repeated = materialize_environment(folder, tmp_path / "second")
    assert len(split["variations_tasks"]) == len(generated) == 10
    assert set(split["variations_tasks"]) == {p.name for p in generated} == expected
    for first, second in zip(generated, repeated, strict=True):
        assert first.name == second.name
        for name in ("task.json", "verifier.py", "setup_task.sh", "export_result.sh"):
            assert (first / name).read_bytes() == (second / name).read_bytes()
    assert set(settings) == {"play_time_seconds", "observation_window_ms", "frames_per_observation"}
    assert spec["runner_options"] == controls["real_time"] == settings
    screen, = [item for item in spec["observation"] if item["type"] in {"rgb_screen", "frame_window"}]
    assert screen["resolution"] == [1920, 1080]
    assert task["difficulty"] == controls["difficulty"][str(controls["baseline"]["difficulty"])]["label"]
    assert task["metadata"]["legacy_agent_sample_population"] is False
    for name in ("install_puzzle_runtime.sh", "setup_puzzle_runtime.sh"):
        script = folder / "scripts" / name
        assert f"exec /workspace/shared_scripts/{name}" in script.read_text()
        assert script.stat().st_mode & 0o111
    assert task["hooks"] == {
        "pre_task": f"/workspace/tasks/{mechanic}_seed_0001/setup_task.sh",
        "post_task": f"/workspace/tasks/{mechanic}_seed_0001/export_result.sh",
    }
    for name in ("setup_task.sh", "export_result.sh"):
        script = task_folder / name
        assert "/workspace/shared_scripts" in script.read_text()
        assert script.stat().st_mode & 0o111
    assert f"/workspace/tasks/{mechanic}_seed_0001/task.json" in (task_folder / "setup_task.sh").read_text()


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_round_six_published_solution_recording(environment):
    mechanic = environment.removesuffix("_env")
    folder = EVIDENCE / "solution_videos"
    manifest = json.loads((folder / "manifest.json").read_text())
    assert len(manifest["videos"]) == 15
    record = manifest["videos"][mechanic]
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
