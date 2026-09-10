from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load(ROOT / "weird_captcha_gym/shared_scripts/incubator_generators/lampwrights_program.py", "lampwrights_generator")
GRADER = _load(ROOT / "weird_captcha_gym/shared_runtime/server/incubator_graders/lampwrights_program.py", "lampwrights_grader")
CONTROLS = json.loads((ROOT / "weird_captcha_gym/environments/lampwrights_program_env/controls.json").read_text())
MECHANIC_JS = (ROOT / "weird_captcha_gym/shared_runtime/app/mechanics/lampwrights_program.js").read_text()


def _task(level: int, interaction: str) -> dict:
    return {
        "id": f"lampwrights_program_d{level}_{interaction}_seed_0001",
        "metadata": {
            "mechanic_id": "lampwrights_program",
            "control_condition": {
                "difficulty": level,
                "interaction": interaction,
                "real_time": "live",
                "difficulty_parameters": CONTROLS["difficulty"][str(level)]["parameters"],
            },
        },
    }


def _valid_payload(public: dict, truth: dict, interaction: str) -> dict:
    ok, message, steps = GRADER._replay(truth["program_solution"], truth, capture_events=True)
    assert ok, message
    run_id = 1
    return {
        "mechanic_id": "lampwrights_program",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "program": truth["program_solution"],
        "editor_events": [{"input_source": "palette_click" if interaction == "simplified" else "drag_drop"}],
        "execution_events": (
            [{"type": "run_start", "run_id": run_id}]
            + [{"type": "step", "run_id": run_id} for _ in steps]
            + [{"type": "run_complete", "run_id": run_id}]
        ),
        "completed": True,
    }


def test_all_difficulty_profiles_replay_and_grade_in_both_modes():
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(_task(level, interaction), f"lampwrights-seed-{level}")
            result = GRADER.grade(_valid_payload(public, truth, interaction), truth, public)
            assert result["passed"] is True
            worlds.append(public["world"])
        assert worlds[0] == worlds[1]


def test_wrong_input_surface_and_stale_challenge_are_rejected():
    public, truth = GENERATOR.generate(_task(4, "simplified"), "lampwrights-surface-seed")
    payload = _valid_payload(public, truth, "full")
    result = GRADER.grade(payload, truth, public)
    assert result["passed"] is False
    assert "wrong interaction" in result["feedback"]
    payload = _valid_payload(public, truth, "simplified")
    payload["challenge_id"] = "stale"
    result = GRADER.grade(payload, truth, public)
    assert result["passed"] is False
    assert result["feedback"] == "stale challenge"


def test_height_rule_rejects_forward_across_a_step():
    public, truth = GENERATOR.generate(_task(4, "full"), "lampwrights-height-seed")
    program = {key: list(value) for key, value in truth["program_solution"].items()}
    program["A"] = ["G", "F", "F", "F", "F", "G"]
    ok, message, _ = GRADER._replay(program, truth)
    assert ok is False
    assert "elevation" in message or "rooftop" in message


def test_full_slot_drag_preserves_occupied_destination_as_reorder():
    assert "function reorderSlot(fromPanel, fromIndex, toPanel, toIndex)" in MECHANIC_JS
    assert 'type: "reorder"' in MECHANIC_JS
    assert 'reorderSlot(fromPanel, Number(fromIndex), slot.dataset.panel, Number(slot.dataset.index));' in MECHANIC_JS


@pytest.mark.parametrize('interaction', ['full','simplified'])
def test_edit_and_failed_rerun_invalidate_completion_in_native_browser(interaction):
    from playwright.sync_api import sync_playwright, expect
    from weird_captcha_gym.tools.incubator_solvers.lampwrights_program import _fill_solution, _place
    public,truth = GENERATOR.generate(_task(1,interaction),'completion-regression')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport=dict(width=1920,height=1080))
        # Isolated fixture setup only; subsequent editing/running uses native input.
        page.set_content('<div id="app"></div>')
        page.add_style_tag(path=str(ROOT/'weird_captcha_gym/shared_runtime/app/mechanics/lampwrights_program.css'))
        page.add_script_tag(path=str(ROOT/'weird_captcha_gym/shared_runtime/app/mechanics/lampwrights_program.js'))
        page.evaluate('state => WeirdCaptchaMechanics.lampwrights_program.render(state,{app:document.querySelector("#app"),setReadout:()=>{}})',public)
        expect(page.locator('#lp-certify')).to_be_enabled()
        _fill_solution(page,truth['program_solution'],interaction)
        page.locator('#lp-run').click()
        page.wait_for_function('lampwrightsProgramModel.completed && !lampwrightsProgramModel.playing')
        _place(page,'main',0,'J',interaction)
        assert page.evaluate('lampwrightsProgramModel.completed') is False
        page.locator('#lp-run').click()
        page.wait_for_function('!lampwrightsProgramModel.playing')
        assert page.evaluate('lampwrightsProgramModel.completed') is False
        expect(page.locator('#lp-status')).to_contain_text('BLOCKED')
        expect(page.locator('#lp-certify')).to_be_enabled()
        browser.close()
