from __future__ import annotations

import json
from pathlib import Path


MECHANIC_ID = "two_season_strand"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=True)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = str(_read_json(state_dir / "ground_truth.json")["challenge_id"])
    page.locator("#strand-seal").click()
    # A truly paused observation freezes requestAnimationFrame, including the
    # default page-side wait polling. Wait on the visible locator from
    # Playwright's process instead, just as the pass path does.
    page.locator(".strand-verdict-fail").wait_for(state="visible", timeout=10000)
    after = str(_read_json(state_dir / "ground_truth.json")["challenge_id"])
    if before == after:
        raise AssertionError("failed seal did not create a fresh challenge")
    if page.locator(".two-season-strand").get_attribute("data-challenge-id") != after:
        raise AssertionError("visible fresh challenge differs from the exported fresh state")
    _screenshot(page, out_dir, "failure-fresh")


def _paint_run(page, indices: list[int], color: int) -> None:
    page.locator(f'.strand-swatch[data-palette-color="{color}"]').click()
    start = page.locator(f'.strand-bead[data-index="{indices[0]}"]').bounding_box()
    end = page.locator(f'.strand-bead[data-index="{indices[-1]}"]').bounding_box()
    if start is None or end is None:
        raise AssertionError("paint run is not visible")
    page.mouse.move(start["x"] + start["width"] / 2, start["y"] + start["height"] / 2)
    page.mouse.down()
    if len(indices) == 1:
        page.mouse.move(start["x"] + start["width"] / 2, start["y"] + start["height"] / 2 - 7, steps=3)
        page.mouse.move(start["x"] + start["width"] / 2, start["y"] + start["height"] / 2 + 7, steps=4)
    else:
        page.mouse.move(end["x"] + end["width"] / 2, end["y"] + end["height"] / 2, steps=12)
    page.mouse.up()


def _switch_season(page, season: str) -> None:
    tab = page.locator(f"#strand-tab-{season}")
    tab.click()
    tab.wait_for(state="visible", timeout=5000)
    if tab.get_attribute("aria-selected") != "true":
        raise AssertionError(f"{season} fold tab did not become active")
    panel = page.locator(f'.season-card[data-season="{season}"]')
    panel.wait_for(state="visible", timeout=5000)


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read_json(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    canonical = list(truth["canonical_sequence"])
    mutated = list(truth["mutated_indices"])
    painted: set[int] = set()
    # The selected interaction form includes switching between the two live
    # views. Exercise both real tabs before editing rather than treating the
    # inactive season's DOM as evidence.
    _switch_season(page, "winter")
    _switch_season(page, "spring")
    if interaction == "full":
        run = list(truth["canonical_paint_run"])
        if len(run) != 2 or any(index not in mutated for index in run):
            raise AssertionError("canonical physical paint run is invalid")
        _paint_run(page, run, int(canonical[run[0]]))
        painted.update(run)
        page.wait_for_function("() => window.twoSeasonStrandModel.edits.length === 1", polling=50)
    for index in mutated:
        if index in painted:
            continue
        if interaction == "full":
            _paint_run(page, [index], int(canonical[index]))
        else:
            page.locator(f'.strand-swatch[data-palette-color="{canonical[index]}"]').click()
            page.locator(f'.strand-bead[data-index="{index}"]').click()
    page.wait_for_function("() => window.twoSeasonStrandModel.ready === true", polling=50)
    page.wait_for_timeout(260)
    _switch_season(page, "winter")
    _screenshot(page, out_dir, f"{interaction}-both-folds-match")
    page.locator("#strand-seal").click()
    # Playwright's default wait_for_function polling uses requestAnimationFrame,
    # which is intentionally frozen during a paused observation. Poll the
    # visible verdict through Playwright's out-of-page locator machinery.
    page.locator(".strand-verdict-pass").wait_for(state="visible", timeout=10000)
    _screenshot(page, out_dir, f"{interaction}-pass")
