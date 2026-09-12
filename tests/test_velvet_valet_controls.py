from __future__ import annotations

import json
from pathlib import Path

from weird_captcha_gym.shared_runtime.server.incubator_graders import velvet_valet as grader
from weird_captcha_gym.shared_scripts.incubator_generators import velvet_valet as generator


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "weird_captcha_gym" / "environments" / "velvet_valet_env"


def _condition(level: int, interaction: str) -> dict:
    return {
        "difficulty": level,
        "difficulty_parameters": dict(generator.PROFILES[level]),
        "interaction": interaction,
        "real_time": "live",
    }


def test_velvet_valet_materializes_all_controlled_variants() -> None:
    task_dirs = sorted((ENV / "tasks").glob("velvet_valet_d*_seed_0001"))
    assert len(task_dirs) == 10
    observed = {
        (json.loads((task_dir / "task.json").read_text()) ["metadata"]["control_condition"]["difficulty"],
         json.loads((task_dir / "task.json").read_text()) ["metadata"]["control_condition"]["interaction"])
        for task_dir in task_dirs
    }
    assert observed == {(level, interaction) for level in range(1, 6) for interaction in ("full", "simplified")}
    controls = json.loads((ENV / "controls.json").read_text())
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    baseline = json.loads((ENV / "tasks" / "velvet_valet_seed_0001" / "task.json").read_text())
    assert baseline["metadata"]["control_condition"] == {
        "difficulty": 4,
        "difficulty_parameters": controls["difficulty"]["4"]["parameters"],
        "interaction": "full",
        "real_time": "live",
    }


def test_same_seed_preserves_world_across_interaction_pair() -> None:
    for level in range(1, 6):
        full_public, full_truth = generator.generate(
            {"id": f"velvet-d{level}-full", "_control_condition": _condition(level, "full")},
            "pair-seed",
        )
        button_public, button_truth = generator.generate(
            {"id": f"velvet-d{level}-simplified", "_control_condition": _condition(level, "simplified")},
            "pair-seed",
        )
        assert full_public["world"] == button_public["world"]
        assert full_truth["world"] == button_truth["world"]
        assert full_public["challenge_id"] == button_public["challenge_id"]
        assert len(full_public["world"]["obstacles"]) == generator.PROFILES[level]["obstacle_count"]
        assert grader._state_valid(full_public["world"]["start"] | {"speed": 0.0}, full_public["world"]) is None


def test_grader_rejects_stale_and_wrong_input_transcripts() -> None:
    public, truth = generator.generate(
        {"id": "velvet-d4-full", "_control_condition": _condition(4, "full")},
        "negative-seed",
    )
    base = {
        "mechanic_id": "velvet_valet",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "events": [],
        "final_tick": 0,
        "completed": True,
    }
    stale = dict(base, challenge_id="stale")
    assert grader.grade(stale, truth, public)["passed"] is False
    wrong_source = dict(base, events=[{"sequence": 1, "tick": 0, "type": "control", "command": "forward", "input_source": "control_button"}])
    assert grader.grade(wrong_source, truth, public)["passed"] is False


def test_full_keyboard_listener_cleanup_removes_keyup_handler() -> None:
    source = (ROOT / "weird_captcha_gym" / "shared_runtime" / "app" / "mechanics" / "velvet_valet.js").read_text()
    assert 'if (model?.keyUpHandler) window.removeEventListener("keyup", model.keyUpHandler);' in source
    assert 'window.removeEventListener("keyup", model.keyHandler)' not in source


def test_browser_and_python_bay_containment_use_exact_half_extents() -> None:
    source = (ROOT / "weird_captcha_gym" / "shared_runtime" / "app" / "mechanics" / "velvet_valet.js").read_text()
    assert "Number(target.width) / 2 + 1e-6" not in source
    assert "Number(target.length) / 2 + 1e-6" not in source
    assert "Math.abs(localX) <= Number(target.width) / 2" in source
    assert "Math.abs(localY) <= Number(target.length) / 2" in source


def test_difficulty_description_matches_protected_route_contract() -> None:
    controls = json.loads((ENV / "controls.json").read_text())
    interpretation = controls["difficulty_interpretation"]
    assert "traversable corridor" in interpretation
    assert "not a claim that the solver must thread close" in interpretation


def test_original_baseline_world_is_preserved_at_d4() -> None:
    baseline = json.loads((ENV / "tasks" / "velvet_valet_seed_0001" / "task.json").read_text())
    d4 = json.loads((ENV / "tasks" / "velvet_valet_d4_full_seed_0001" / "task.json").read_text())
    baseline_public, baseline_truth = generator.generate(baseline, "baseline-preservation")
    d4_public, d4_truth = generator.generate(
        {"id": d4["id"], "_control_condition": d4["metadata"]["control_condition"]},
        "baseline-preservation",
    )
    assert baseline_public["world"] == d4_public["world"]
    assert baseline_truth["world"] == d4_truth["world"]
