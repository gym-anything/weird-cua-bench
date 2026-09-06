"""Exercise the rendered text-selection surface, not synthetic DOM events."""
import json

import pytest

from tests.test_round_three_task_clocks import task_browser


@pytest.mark.parametrize("viewport", [(1280, 720), (1920, 1080)])
@pytest.mark.parametrize("interaction", ["full", "simplified"])
def test_hidden_tray_does_not_cover_editor_selection(tmp_path, viewport, interaction):
    pytest.importorskip("playwright.sync_api")
    from weird_captcha_gym.tools.incubator_solvers import passphrase_under_siege as solver

    with task_browser(tmp_path, "passphrase_under_siege", interaction, viewport) as (page, state):
        contract = json.loads((state / "ground_truth.json").read_text())["contract"]
        clues = solver._read_visible_clues(page, contract)
        password = solver.canonical_password(contract, clues)
        page.keyboard.type(password, delay=8)
        assert page.locator(".siege-grain-tray").is_hidden()
        for index, char in enumerate(password):
            if char not in solver.VOWELS:
                continue
            glyph = page.locator(f'.siege-char[data-index="{index}"]')
            point = solver.center(glyph)
            assert page.evaluate("p => document.elementFromPoint(...p)?.dataset.index", list(point)) == str(index)
            solver._select_range(page, index, index + 1, interaction)
            assert page.locator(".siege-char.is-selected").evaluate_all("nodes => nodes.map(n => n.dataset.index)") == [str(index)]
            solver._format(page, '.siege-tool[data-style="bold"][data-value="true"]')
            assert "is-bold" in glyph.get_attribute("class")
        page.screenshot(path=str(tmp_path / "selected-and-formatted.png"))
