"""Deterministic and isolated browser checks for Crater Walker."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1] / "weird_captcha_gym"
ENV = ROOT / "environments" / "crater_walker_env"
TASK = json.loads((ENV / "tasks" / "crater_walker_seed_0001" / "task.json").read_text())
CONTROLS = json.loads((ENV / "controls.json").read_text())


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GEN = _load("crater_walker_test_generator", ROOT / "shared_scripts/incubator_generators/crater_walker.py")
GRADER = _load("crater_walker_test_grader", ROOT / "shared_runtime/server/incubator_graders/crater_walker.py")


def condition(level: int, interaction: str) -> dict:
    return {
        "difficulty": level,
        "interaction": interaction,
        "real_time": "live",
        "difficulty_parameters": copy.deepcopy(CONTROLS["difficulty"][str(level)]["parameters"]),
    }


def state_for(level: int, interaction: str, seed: str = "crater-browser-test"):
    task = copy.deepcopy(TASK)
    task["_control_condition"] = condition(level, interaction)
    return GEN.generate(task, seed)


def _valid_actions(truth: dict, source: str = "nudge_button") -> list[dict]:
    state = GRADER.initial_state(truth["world"])
    actions = []
    tick = 0

    def control(leg: str, actuator: str, target: int):
        current = int(state["actuators"][leg][actuator])
        step = 1 if target > current else -1
        while current != target:
            value = current + step
            actions.append({"seq": len(actions) + 1, "tick": tick, "type": "control", "input_source": source, "leg": leg, "actuator": actuator, "before": current, "value": value, "after": value})
            state["actuators"][leg][actuator] = value
            current = value

    def settle():
        nonlocal tick
        tick += 1
        before = int(state["stage"])
        body_before = copy.deepcopy(state["body"])
        GRADER.apply_settle(state, truth["world"])
        actions.append({"seq": len(actions) + 1, "tick": tick, "type": "settle", "input_source": "settle_button", "stage_before": before, "stage_after": state["stage"], "contacts_after": copy.deepcopy(state["contacts"]), "support_count": sum(value is not None for value in state["contacts"].values()), "failed": state["failed"], "roll": 0, "pitch": 0})
        actions[-1].update({
            "body_before": body_before,
            "body_after": copy.deepcopy(state["body"]),
            "motion_step_after": state["motion"]["step"] if state.get("motion") is not None else None,
        })

    for transfer in truth["transfer_controls"]:
        leg = str(transfer["leg"])
        controls = transfer["controls"]
        control(leg, "lift", 3)
        settle()
        control(leg, "yaw", int(controls["yaw"]))
        control(leg, "extend", int(controls["extend"]))
        settle()
        control(leg, "lift", int(controls["lift"]))
        settle()
        while state.get("motion") is not None:
            settle()
    return actions, state


def test_materialization_contract_and_baseline_preservation():
    assert CONTROLS["baseline"] == {"difficulty": 4, "interaction": "simplified", "real_time": "live"}
    worlds = {}
    for level in range(1, 6):
        for interaction in ("simplified", "full"):
            public, truth = state_for(level, interaction)
            assert public["world"] == truth["world"]
            assert public["control_condition"] == condition(level, interaction)
            worlds.setdefault(level, public["world"])
            actions, replay = _valid_actions(truth, "nudge_button" if interaction == "simplified" else "slider_drag")
            payload = {"mechanic_id": "crater_walker", "task_id": truth["task_id"], "challenge_id": truth["challenge_id"], "completed": True, "actions": actions, "final_stage": replay["stage"], "final_contacts": replay["contacts"]}
            assert GRADER.grade(payload, truth, public)["passed"] is True
        public_full, _ = state_for(level, "full")
        assert public_full["world"] == worlds[level]
    public, truth = state_for(4, "simplified", "terrain-contract-test")
    surfaces = {str(quad["pad_id"]): quad for quad in truth["world"]["terrain_quads"] if quad.get("kind") == "support_surface"}
    assert set(surfaces) == {str(pad["id"]) for pad in truth["world"]["pads"]}
    assert all(len(stage.get("body_path_from_previous") or []) == 4 for stage in truth["world"]["stages"][1:])
    assert max(float(vertex["z"]) for quad in truth["world"]["terrain_quads"] for vertex in quad["vertices"]) >= max(float(pad["z"]) for pad in truth["world"]["pads"])
    terrain_without_support_patches = copy.deepcopy(truth["world"])
    terrain_without_support_patches["terrain_quads"] = [quad for quad in terrain_without_support_patches["terrain_quads"] if quad.get("kind") != "support_surface"]
    first = truth["world"]["stages"][0]
    assert not any(GRADER.contacts_for(terrain_without_support_patches, first["body_pose"], first["stance_controls"]).values())
    terrain_without_any_geometry = copy.deepcopy(terrain_without_support_patches)
    terrain_without_any_geometry["terrain_quads"] = []
    assert not GRADER.body_clear_of_terrain(terrain_without_any_geometry, truth["world"]["stages"][1]["body_path_from_previous"][0])


@pytest.fixture(scope="module")
def browser():
    runtime = pytest.importorskip("playwright.sync_api")
    with runtime.sync_playwright() as playwright:
        instance = playwright.chromium.launch(headless=True)
        try:
            yield instance
        finally:
            instance.close()


def _render(page, state):
    page.set_content('<base href="http://127.0.0.1/"><main id="app"></main>')
    page.add_style_tag(path=str(ROOT / "shared_runtime/app/mechanics/crater_walker.css"))
    page.add_script_tag(path=str(ROOT / "shared_runtime/app/mechanics/crater_walker.js"))
    page.evaluate(
        """async (state) => {
          const app = document.querySelector('#app');
          await WeirdCaptchaMechanics.crater_walker.render(state, {
            app,
            setReadout(text, status='idle') {
              const node = app.querySelector('.readout');
              if (node) { node.textContent = text; node.dataset.status = status; }
            },
            cheatPanelTemplate() { return ''; }
          });
        }""",
        state,
    )


def _drive(page, truth, mode):
    for transfer_index, transfer in enumerate(truth["transfer_controls"]):
        leg = str(transfer["leg"])
        target = transfer["controls"]
        assert page.locator(".crater-transfer-leg").inner_text() == leg.replace("_", " ").upper()
        card = page.locator(f'[data-leg="{leg}"]')
        if mode == "full":
            card.locator('input[data-actuator="lift"]').fill("3")
            page.locator(".crater-settle").click()
            card.locator('input[data-actuator="yaw"]').fill(str(target["yaw"]))
            card.locator('input[data-actuator="extend"]').fill(str(target["extend"]))
            page.locator(".crater-settle").click()
            card.locator('input[data-actuator="lift"]').fill(str(target["lift"]))
            page.locator(".crater-settle").click()
        else:
            for actuator, wanted in (("lift", 3), ("yaw", int(target["yaw"])), ("extend", int(target["extend"])), ("lift", int(target["lift"]))):
                value = int(card.locator(f'[data-value-for="{actuator}"]').inner_text())
                while value != wanted:
                    delta = 1 if wanted > value else -1
                    card.locator(f'button[data-actuator="{actuator}"][data-nudge="{delta}"]').click()
                    value += delta
                if actuator == "lift" and wanted in (3, int(target["lift"])):
                    page.locator(".crater-settle").click()
            # The yaw/extend pair is intentionally settled together.
            if int(target["lift"]) != 3:
                pass
        target_stage = truth["transfer_controls"].index(transfer) + 2
        for _ in range(5):
            if page.locator(".crater-stage").inner_text().startswith(f"{target_stage} /"):
                break
            page.locator(".crater-settle").click()
            page.wait_for_timeout(10)
        assert page.locator(".crater-stage").inner_text().startswith(f"{target_stage} /")
        if transfer_index + 1 < len(truth["transfer_controls"]):
            next_leg = str(truth["transfer_controls"][transfer_index + 1]["leg"])
            assert page.locator(".crater-transfer-leg").inner_text() == next_leg.replace("_", " ").upper()
        page.wait_for_timeout(10)
    assert page.locator(".crater-certify").is_enabled()
    page.locator(".crater-certify").click()
    page.wait_for_timeout(30)
    assert "PASS" in page.locator(".crater-readout").inner_text()


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("interaction", ["simplified", "full"])
def test_all_difficulty_interaction_variants_use_visible_controls(browser, level, interaction):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    page.route("**/result", lambda route: route.fulfill(json={"ok": True, "passed": True}))
    public, truth = state_for(level, interaction)
    _render(page, public)
    assert page.locator(".crater-canvas").count() == 1
    assert page.locator("[data-leg-card]").count() == 4
    assert page.locator(".crater-transfer-leg").inner_text() == "FRONT LEFT"
    assert page.locator('[data-leg="front_left"]').get_attribute("class").find("is-indicated") >= 0
    _drive(page, truth, interaction)
    context.close()


def test_failure_feedback_retry_and_wrong_surface_rejection(browser):
    public, truth = state_for(4, "simplified", "crater-failure-test")
    replacement, _ = state_for(4, "simplified", "crater-retry-test")
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()

    def result(route):
        payload = route.request.post_data_json
        if payload.get("completed") is False:
            route.fulfill(json={"ok": True, "passed": False, "state": replacement})
        else:
            route.fulfill(json={"ok": True, "passed": True})

    page.route("**/result", result)
    _render(page, public)
    for leg in ("front_left", "front_right"):
        card = page.locator(f'[data-leg="{leg}"]')
        for _ in range(3): card.locator('button[data-actuator="lift"][data-nudge="1"]').click()
    page.locator(".crater-settle").click()
    assert page.locator(".crater-readout").get_attribute("data-status") == "error"
    page.locator(".crater-retry").click()
    page.wait_for_timeout(20)
    assert page.locator(".crater-readout").inner_text().startswith("READY")

    actions, replay = _valid_actions(truth, "slider_drag")
    wrong = {"mechanic_id": "crater_walker", "task_id": truth["task_id"], "challenge_id": truth["challenge_id"], "completed": True, "actions": actions, "final_stage": replay["stage"], "final_contacts": replay["contacts"]}
    decision = GRADER.grade(wrong, truth, public)
    assert decision["passed"] is False and "wrong interaction" in decision["feedback"]
    context.close()
