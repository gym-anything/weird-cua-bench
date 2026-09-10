"""Task-local browser regressions in fresh, headless contexts."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


BENCHMARK = Path(__file__).resolve().parents[1] / "weird_captcha_gym"
MECHANICS = BENCHMARK / "shared_runtime/app/mechanics"


def state_for(mechanic, level, interaction):
    folder = BENCHMARK / "environments" / (mechanic + "_env")
    task = json.loads((folder / "tasks" / (mechanic + "_seed_0001") / "task.json").read_text())
    controls = json.loads((folder / "controls.json").read_text())
    task["_control_condition"] = {
        "difficulty": level, "interaction": interaction, "real_time": "live",
        "difficulty_parameters": controls["difficulty"][str(level)]["parameters"],
    }
    spec = importlib.util.spec_from_file_location(
        "round_four_browser_" + mechanic,
        BENCHMARK / "shared_scripts/incubator_generators" / (mechanic + ".py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.generate(task, "round-four-browser-regression")


@pytest.fixture(scope="module")
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1920, "height": 1080})
    context.route("**/*", lambda route: route.abort())
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.clock.install()
    page.set_content('<main id="app"></main>')
    try:
        yield page
        assert not errors, errors
    finally:
        context.close()


def render(page, mechanic, state):
    page.add_style_tag(path=str(MECHANICS / (mechanic + ".css")))
    page.add_script_tag(path=str(MECHANICS / (mechanic + ".js")))
    page.evaluate("""async ([mechanic, state]) => {
      window.actionTokens = [];
      const app = document.querySelector('#app');
      const helpers = {app,
        setReadout(text, status='idle') {
          const node = app.querySelector('.readout');
          if (node) { node.textContent = text; node.dataset.status = status; }
        },
        beginAction(label) {
          const item = {label, settles: 0};
          actionTokens.push(item);
          return {settle() { item.settles += 1; }};
        },
        interactionNow() { return performance.now(); },
      };
      await WeirdCaptchaMechanics[mechanic].render(state, helpers);
    }""", [mechanic, state])


def drag(page, source, target):
    source.scroll_into_view_if_needed()
    first = source.bounding_box()
    target.scroll_into_view_if_needed()
    last = target.bounding_box()
    page.mouse.move(first["x"] + first["width"] / 2, first["y"] + first["height"] / 2)
    page.mouse.down()
    page.mouse.move(last["x"] + last["width"] / 2, last["y"] + last["height"] / 2, steps=4)
    page.mouse.up()


def test_marble_drag_tokens_settle_once_on_every_exit(page, tmp_path):
    state, _ = state_for("tomorrows_marble", 2, "full")
    render(page, "tomorrows_marble", state)
    source = page.locator('.tm-piece[data-piece-index="0"]')
    first = page.locator('.tm-cell[data-machine-index="0"][data-slot="0"]')
    second = page.locator('.tm-cell[data-machine-index="0"][data-slot="1"]')
    drag(page, source, first)
    assert page.locator(".tm-arrival").count() == 1
    drag(page, source, first)  # Occupied destination still completes the action.
    assert page.locator(".tm-arrival").count() == 1
    drag(page, page.locator(".tm-arrival"), second)
    assert second.locator(".tm-arrival").count() == 1
    drag(page, page.locator(".tm-arrival"), page.locator("#tm-trash"))
    assert page.locator(".tm-arrival").count() == 0
    drag(page, source, page.locator(".tm-header"))  # Drop outside the timeline.
    box = source.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.evaluate("document.dispatchEvent(new PointerEvent('pointercancel', {pointerId: 1}))")
    page.mouse.up()
    tokens = page.evaluate("actionTokens")
    assert len(tokens) == 6, tokens
    assert all(token["settles"] == 1 for token in tokens), tokens
    assert page.evaluate("tomorrowsMarbleModel.drag") is None
    page.screenshot(path=str(tmp_path / "marble-drag-cancelled.png"))


def test_marble_removal_invalidates_a_successful_run(page, tmp_path):
    state, truth = state_for("tomorrows_marble", 2, "simplified")
    render(page, "tomorrows_marble", state)
    for node in truth["solution_schedule"]:
        page.locator(f'.tm-piece[data-piece-index="{node["piece_index"]}"]').click()
        page.locator(f'.tm-cell[data-machine-index="{node["machine_index"]}"][data-slot="{node["slot"]}"]').click()
    page.locator("#tm-run").click()
    page.clock.run_for(state["run_duration_ms"] + 100)
    assert page.evaluate("tomorrowsMarbleModel.runSummary.passed") is True
    assert page.locator("#tm-run-clock").inner_text() == "LOOP CLOSED"
    assert page.locator("#tm-certify").is_enabled()
    page.locator(".tm-arrival").first.click()
    assert page.evaluate("tomorrowsMarbleModel.runSummary") is None
    assert page.locator("#tm-certify").is_disabled()
    assert page.locator("#tm-ledger-box").get_attribute("data-state") == "waiting"
    assert page.locator("#tm-run-clock").inner_text() == "IDLE"
    page.screenshot(path=str(tmp_path / "marble-removal-invalidates-run.png"))


def test_same_beat_wall_hits_remain_visible_together(page, tmp_path):
    state, _ = state_for("collision_chimes", 2, "simplified")
    render(page, "collision_chimes", state)
    for col in (0, 1):
        page.locator(f'.grid-cell[data-row="0"][data-col="{col}"]').click()
        page.locator("#add-cell").click()
    page.locator("#step-beat").click()
    hits = page.locator('.wall-rail[data-side="top"] .wall-slot.is-hit')
    assert hits.count() == 2
    assert [hits.nth(i).get_attribute("data-slot") for i in range(2)] == ["0", "1"]
    assert page.locator("#event-log .event-row").count() == 2
    page.screenshot(path=str(tmp_path / "collision-two-simultaneous-hits.png"))
    page.locator("#reset-board").click()
    assert page.locator(".wall-slot.is-hit").count() == 0


@pytest.mark.parametrize("interaction", ["full", "simplified"])
def test_carbon_rejection_is_visible_and_preserves_the_hand(page, tmp_path, interaction):
    state, _ = state_for("last_carbon_isles", 2, interaction)
    state["budget"] = 0
    render(page, "last_carbon_isles", state)
    card = state["hand"][0]
    source = page.locator(f'.carbon-card[data-card-id="{card["id"]}"]')
    target = page.locator(f'.carbon-isle[data-region-id="{card["home_region"]}"]')
    if interaction == "full":
        drag(page, source, target)
    else:
        source.click()
        target.click()
    assert page.locator(".footer-state").inner_text() == "THE LEDGER CANNOT FUND THAT MOVE"
    assert page.locator(".footer-state").get_attribute("data-status") == "error"
    assert source.count() == 1
    assert page.locator(".carbon-card").count() == len(state["hand"])
    page.screenshot(path=str(tmp_path / f"carbon-{interaction}-rejection.png"))


def test_animation_preview_treats_line_endpoints_as_unordered(page, tmp_path):
    state, truth = state_for("pocket_animation_studio", 4, "full")
    program = copy.deepcopy(truth["target_program"])
    for shape in program:
        if shape["kind"] == "line":
            expressions = shape["expressions"]
            for first, second in (("x1", "x2"), ("y1", "y2")):
                expressions[first], expressions[second] = expressions[second], expressions[first]
    render(page, "pocket_animation_studio", state)
    # Seed editor state for this visual-comparison unit test. Separate grader
    # tests validate that the input transcript constructs the submitted program.
    page.evaluate("program => { pocketAnimationStudioModel.program = program; }", program)
    page.locator("#pas-run").click()
    page.clock.run_for(truth["duration_ms"] + 100)
    assert page.locator(".pas-drift-value").inner_text() == "MAX 0.0 / MEAN 0.0"
    assert page.locator(".pas-readout").get_attribute("data-status") == "idle"
    page.screenshot(path=str(tmp_path / "animation-reversed-endpoints-match.png"))
