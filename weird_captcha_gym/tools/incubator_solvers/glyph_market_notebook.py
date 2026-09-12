"""White-box oracle for browser wiring; all task actions use visible controls."""
from __future__ import annotations

import json
import time
from pathlib import Path


MECHANIC_ID = "glyph_market_notebook"


def _state(page):
    return page.evaluate("""() => {
      const m = window.glyphMarketNotebookModel;
      return {w: m.w, mode: m.mode, expected: m.expectedMapping, state: m.state};
    }""")


def _collect_and_annotate(page):
    state = _state(page)
    for scene_index in range(len(state["w"]["scenes"])):
        page.locator(f'[data-scene="{scene_index}"]').click()
        page.wait_for_selector(".gm-scene-view")
        scene = _state(page)["w"]["scenes"][scene_index]
        for spot in scene["spots"]:
            if state["mode"] == "full":
                selector = f'[data-spot="{spot["id"]}"]'
            else:
                selector = f'[data-proxy-spot="{spot["id"]}"]'
            page.wait_for_selector(selector)
            page.locator(selector).click()
        page.locator('[data-view="map"]').first.click()
        page.wait_for_selector(".gm-map-view")
    page.locator('[data-view="notebook"]').first.click()
    state = _state(page)
    # The notebook inputs are normal visible text fields.  These strings are
    # intentionally provisional; the exact answer is the later visual
    # assignment, not an OCR token.
    for glyph_id in page.evaluate("() => window.glyphMarketNotebookModel.notebook"):
        page.locator(f'[data-note-input="{glyph_id}"]').fill(f"market reading {glyph_id[-4:]}")
        page.locator(f'[data-save-note="{glyph_id}"]').click()


def _place(page, page_id, card_id, glyph_id, mode):
    if mode == "full":
        page.locator(f'[data-glyph-chip="{glyph_id}"]').drag_to(page.locator(f'[data-card="{card_id}"]'))
    else:
        page.locator(f'[data-glyph-chip="{glyph_id}"]').click()
        page.locator(f'[data-card="{card_id}"]').click()


def fail_once(page, state_dir, out_dir, mechanic=MECHANIC_ID):
    del state_dir, mechanic
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _collect_and_annotate(page)
    page.locator('[data-view="validate"]').first.click()
    data = _state(page)
    page_id = data["w"]["pages"][0]["id"]
    card = data["w"]["pages"][0]["cards"][0]
    expected = data["expected"][card["id"]]
    wrong = next(glyph["id"] for glyph in data["w"]["glyphs"] if glyph["id"] != expected)
    _place(page, page_id, card["id"], wrong, data["mode"])
    page.locator(f'[data-validate-page="{page_id}"]').click()
    page.screenshot(path=str(out_dir / "failure-recovery.png"))


def solve(page, state_dir, out_dir, mechanic=MECHANIC_ID, advance=None):
    del advance, mechanic
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    page.wait_for_selector(".gm-shell")
    page.screenshot(path=str(out_dir / "initial.png"))
    _collect_and_annotate(page)
    page.screenshot(path=str(out_dir / "notebook-annotated.png"))
    page.locator('[data-view="validate"]').first.click()
    data = _state(page)
    page.screenshot(path=str(out_dir / "validation-active.png"))
    for page_index, notebook_page in enumerate(data["w"]["pages"]):
        if page_index != data["w"]["pages"].index(notebook_page):
            continue
        for card in notebook_page["cards"]:
            glyph_id = data["expected"][card["id"]]
            _place(page, notebook_page["id"], card["id"], glyph_id, data["mode"])
        page.locator(f'[data-validate-page="{notebook_page["id"]}"]').click()
        data = _state(page)
    page.screenshot(path=str(out_dir / "solved-before-submit.png"))
    page.locator("[data-submit]").click()
    for _ in range(80):
        if page.locator(".readout").get_attribute("data-status") == "passed":
            break
        time.sleep(0.1)
    else:
        raise AssertionError("Glyph Market Notebook browser did not show PASS")
    page.screenshot(path=str(out_dir / "pass.png"))
    if state_dir:
        result_path = Path(state_dir) / "result.json"
        if result_path.exists():
            return json.loads(result_path.read_text(encoding="utf-8"))
    return {"passed": True}
