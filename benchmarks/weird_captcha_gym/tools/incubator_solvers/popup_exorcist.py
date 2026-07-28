from __future__ import annotations

from pathlib import Path

from playwright.sync_api import expect

from benchmarks.weird_captcha_gym.tools.incubator_solvers.reviewed_overhaul_common import (
    center, read_json, shot, wait_fresh,
)

MECHANIC_ID = "popup_exorcist"


def _interaction(truth: dict) -> str:
    return str((truth.get("control_condition") or {}).get("interaction") or "full")


def _select(page, window_id: str) -> None:
    page.locator(f'[data-window-id="{window_id}"] header span').click()


def _close(page, window_id: str, interaction: str) -> None:
    if interaction == "simplified":
        _select(page, window_id)
        page.locator(".popup-close-selected").click()
    else:
        page.locator(f'[data-window-id="{window_id}"] .parasite-close').click()


def _provoke(
    page,
    state: dict,
    parasite: str,
    stage_ids: set[str],
) -> None:
    truth_interaction = str(state.get("interaction") or "full")
    parasite_z = next(int(item["z"]) for item in state["popups"] if item["id"] == parasite)
    for item in sorted(state["popups"], key=lambda value: int(value["z"]), reverse=True):
        if str(item["id"]) in stage_ids and int(item["z"]) > parasite_z:
            node = page.locator(f'[data-window-id="{item["id"]}"]')
            if "is-dead" not in (node.get_attribute("class") or ""):
                _close(page, item["id"], truth_interaction)
    _close(page, parasite, truth_interaction)
    expect(page.locator(".containment-well[data-active='true']")).to_be_visible()


def _parents(truth: dict) -> list[str]:
    return [str(item) for item in (truth.get("parasite_ids") or [truth["parasite_id"]])]


def _groups(truth: dict) -> dict[str, list[str]]:
    parents = _parents(truth)
    raw = truth.get("infection_groups") or {parents[0]: truth["echo_ids"]}
    return {str(parent): [str(item) for item in echoes] for parent, echoes in raw.items()}


def _stage_batches(truth: dict) -> list[list[str]]:
    raw = truth.get("stage_batches") or [truth["popup_ids"]]
    return [[str(item) for item in batch] for batch in raw]


def _wait_for_stage(page, index: int, bounds: dict) -> None:
    well = page.locator(".containment-well")
    expect(well).to_have_attribute("data-stage-index", str(index))
    expect(page.locator(".parasite-captcha")).to_have_attribute(
        "data-active-stage",
        str(index),
    )
    page.wait_for_timeout(450)
    field_box = page.locator(".popup-field").bounding_box()
    well_box = well.bounding_box()
    assert field_box and well_box
    actual_center = (
        well_box["x"] + well_box["width"] / 2 - field_box["x"],
        well_box["y"] + well_box["height"] / 2 - field_box["y"],
    )
    expected_center = (
        float(bounds["x"]) + float(bounds["w"]) / 2,
        float(bounds["y"]) + float(bounds["h"]) / 2,
    )
    assert abs(actual_center[0] - expected_center[0]) <= 4
    assert abs(actual_center[1] - expected_center[1]) <= 4


def _contain(page, echo_id: str, interaction: str, out_dir: Path, *, final: bool) -> None:
    echo = page.locator(f'[data-window-id="{echo_id}"]')
    if interaction == "simplified":
        _select(page, echo_id)
        page.locator(".popup-contain-selected").click()
        if final:
            shot(page, out_dir, MECHANIC_ID, "purge-before-grade")
        else:
            expect(page.locator(f'[data-window-id="{echo_id}"].is-dead')).to_have_count(1)
        return
    header = echo.locator("header")
    well = page.locator(".containment-well")
    sx, sy = center(header)
    wx, wy = center(well)
    echo_box = echo.bounding_box()
    header_box = header.bounding_box()
    assert echo_box and header_box
    end = (
        wx + (sx - (echo_box["x"] + echo_box["width"] / 2)),
        wy + (sy - (echo_box["y"] + echo_box["height"] / 2)),
    )
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.mouse.move(*end, steps=12)
    if final:
        shot(page, out_dir, MECHANIC_ID, "contained-before-release")
    page.mouse.up()
    if not final:
        expect(page.locator(f'[data-window-id="{echo_id}"].is-dead')).to_have_count(1)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    assert mechanic == MECHANIC_ID
    state, truth = read_json(state_dir / "public_state.json"), read_json(state_dir / "ground_truth.json")
    before = truth["challenge_id"]
    interaction = _interaction(truth)
    state["interaction"] = interaction
    parasite = _parents(truth)[0]
    _provoke(page, state, parasite, set(_stage_batches(truth)[0]))
    if interaction == "simplified":
        close = page.locator(".popup-close-selected")
    else:
        close = page.locator(f'[data-window-id="{parasite}"] .parasite-close')
    for _ in range(int(state.get("maximum_resistance_strikes") or 3)):
        close.click()
    expect(page.locator(".readout")).to_contain_text("FAIL", timeout=12_000)
    shot(page, out_dir, mechanic, "failure-visible")
    wait_fresh(state_dir, before)
    page.wait_for_timeout(1_050)
    expect(page.locator("body[data-mechanic]")).to_be_visible(timeout=8_000)
    shot(page, out_dir, mechanic, "retry-fresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    assert mechanic == MECHANIC_ID
    state, truth = read_json(state_dir / "public_state.json"), read_json(state_dir / "ground_truth.json")
    interaction = _interaction(truth)
    state["interaction"] = interaction
    groups = _groups(truth)
    stage_batches = _stage_batches(truth)
    containment_stages = truth.get("containment_stages") or [truth["containment"]]
    parents = _parents(truth)
    for index, parent in enumerate(parents):
        _provoke(page, state, parent, set(stage_batches[index]))
        if index == 0:
            shot(page, out_dir, mechanic, "replication-discovered")
        final = index == len(parents) - 1
        _contain(page, groups[parent][-1], interaction, out_dir, final=final)
        if not final:
            expect(page.locator(".readout")).to_contain_text(
                f"STRAIN {index + 1}/{len(parents)} CONTAINED"
            )
            _wait_for_stage(page, index + 1, containment_stages[index + 1])
            for window_id in stage_batches[index + 1]:
                expect(page.locator(f'[data-window-id="{window_id}"]')).to_be_visible()
            shot(
                page,
                out_dir,
                mechanic,
                "first-strain-contained" if index == 0 else "second-strain-contained",
            )
    expect(page.locator(".readout")).to_have_attribute("data-status", "passed", timeout=8_000)
    shot(page, out_dir, mechanic, "pass")
