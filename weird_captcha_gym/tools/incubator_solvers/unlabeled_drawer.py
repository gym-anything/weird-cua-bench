from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from weird_captcha_gym.shared_scripts.incubator_generators import unlabeled_drawer as visible_logic


MECHANIC_ID = "unlabeled_drawer"


def _state(state_dir: Path) -> dict[str, Any]:
    return json.loads((state_dir / "public_state.json").read_text(encoding="utf-8"))


def _choose_visible_probe_plan(state: dict[str, Any]) -> list[str]:
    plans = visible_logic.visible_probe_plans(state["probe_specimens"], state["parameters"])
    if not plans:
        raise AssertionError("no visible contrast set fits the calibration budget")
    return list(plans[0]["specimen_ids"])


def _infer_from_returned_outcomes(
    state: dict[str, Any],
    probe_ids: list[str],
    observed_outcomes: dict[str, bool],
) -> dict[str, bool]:
    return visible_logic.infer_visible_predictions(
        state["probe_specimens"],
        state["final_specimens"],
        state["parameters"],
        probe_ids,
        observed_outcomes,
    )


def _read_visible_outcome(page) -> bool:
    response = page.locator(".ud-archive-record strong").inner_text().strip().upper()
    if response not in {"FILE", "RETURN"}:
        raise AssertionError(f"visible cabinet response is invalid: {response!r}")
    return response == "FILE"


def _drag(page, source, destination) -> None:
    source_box = source.bounding_box()
    destination_box = destination.bounding_box()
    if source_box is None or destination_box is None:
        raise AssertionError("visible drag source or destination is missing")
    start_x = source_box["x"] + source_box["width"] / 2
    start_y = source_box["y"] + source_box["height"] / 2
    end_x = destination_box["x"] + destination_box["width"] / 2
    end_y = destination_box["y"] + destination_box["height"] * 0.62
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(end_x, end_y, steps=8)
    page.mouse.up()


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    del state_dir
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    page.locator("#ud-certify").click()
    page.locator(".ud-fresh-failure").wait_for(state="visible")
    page.screenshot(path=str(out_dir / "fresh-failure.png"))


def solve(page, state_dir: Path, out_dir: Path, mechanic: str, *, certify: bool = True) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    state = _state(state_dir)
    interaction = (state.get("control_condition") or {}).get("interaction") or "full"
    probe_ids = _choose_visible_probe_plan(state)
    observed_outcomes: dict[str, bool] = {}

    for index, specimen_id in enumerate(probe_ids, 1):
        specimen = next(item for item in state["probe_specimens"] if item["id"] == specimen_id)
        card = page.locator(f'[data-specimen-id="{specimen["id"]}"]')
        if interaction == "full":
            _drag(page, card, page.locator('[data-drop="probe"]'))
        else:
            card.click()
            page.locator("#ud-test").click()
        observed_outcomes[specimen_id] = _read_visible_outcome(page)
        page.screenshot(path=str(out_dir / f"probe-{index:02d}-feedback.png"))

    predictions = _infer_from_returned_outcomes(state, probe_ids, observed_outcomes)

    if len(probe_ids) > 1:
        for _ in range(len(probe_ids) - 1):
            page.locator("#ud-archive-prev").click()
        page.screenshot(path=str(out_dir / "archive-first-record.png"))
        for _ in range(len(probe_ids) - 1):
            page.locator("#ud-archive-next").click()
        page.screenshot(path=str(out_dir / "archive-last-record.png"))
    page.locator("#ud-open-final").click()
    page.screenshot(path=str(out_dir / "calibration-complete.png"))

    for index, specimen in enumerate(state["final_specimens"], 1):
        if index <= 2:
            page.screenshot(path=str(out_dir / f"final-{index:02d}-visible.png"))
        drawer = "accept" if predictions[specimen["id"]] else "reject"
        card = page.locator(f'[data-specimen-id="{specimen["id"]}"]')
        if interaction == "full":
            _drag(page, card, page.locator(f'[data-drop="{drawer}"]'))
        else:
            card.click()
            page.locator(f'[data-file-button="{drawer}"]').click()
    page.screenshot(path=str(out_dir / "final-sort-before-certify.png"))
    if certify:
        page.locator("#ud-certify").click()
        page.locator('.readout[data-status="passed"]').wait_for(state="visible")
