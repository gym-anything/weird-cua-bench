from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "modifier_stack_image_grid"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, mechanic: str, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{label}.png"), full_page=True)


def _wait_new(state_dir: Path, previous: str) -> None:
    deadline = time.time() + 8
    while time.time() < deadline:
        if str(_read(state_dir / "ground_truth.json").get("challenge_id")) != previous:
            return
        time.sleep(0.05)
    raise AssertionError("restoration press did not issue fresh film")


def _box(page) -> dict:
    box = page.locator("#restoration-canvas").bounding_box()
    if not box:
        raise AssertionError("restoration canvas is not visible")
    return box


def _screen(box: dict, point: list[float]) -> tuple[float, float]:
    return box["x"] + point[0] / 940 * box["width"], box["y"] + point[1] / 500 * box["height"]


def _center(rect: dict) -> list[float]:
    return [rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] / 2]


def _place(page, rack: dict, slot: dict) -> None:
    box = _box(page)
    page.mouse.move(*_screen(box, _center(rack)))
    page.mouse.down()
    # One endpoint event is a complete pointer drag. Placement must not depend
    # on action interpolation or on how long the caller happens to hold it.
    page.mouse.move(*_screen(box, _center(slot)))
    page.mouse.up()


def _invert(page, slot: dict) -> None:
    box = _box(page)
    page.mouse.click(*_screen(box, [slot["x"] + slot["width"] - 15, slot["y"] + 15]))


def _run_rail(page, rail: dict, minimum_samples: int) -> None:
    box = _box(page)
    page.mouse.move(*_screen(box, rail["start"]))
    page.mouse.down()
    sample_count = max(30, int(minimum_samples) + 4)
    for index in range(1, sample_count + 1):
        amount = index / sample_count
        point = [rail["start"][0] + (rail["end"][0] - rail["start"][0]) * amount, rail["start"][1]]
        page.mouse.move(*_screen(box, point), steps=1)
        page.wait_for_timeout(25)
    page.mouse.up()


def _proxy_place(page, token_id: str, slot_index: int) -> None:
    page.locator(f'[data-proxy-action="select"][data-token-id="{token_id}"]').click()
    page.locator(f'[data-proxy-action="place"][data-slot-index="{slot_index}"]').click()


def _proxy_invert(page, token_id: str) -> None:
    page.locator(f'[data-proxy-action="invert"][data-token-id="{token_id}"]').click()


def _proxy_rail(page, requirements: dict, out_dir: Path | None = None, mechanic: str | None = None) -> None:
    """Use the simplified input surface for the same held rail contract.

    The three controls retain a single restoration hold.  Each advance writes
    one rail sample; the wait before release satisfies the same minimum
    contact duration that the direct pointer path must satisfy.
    """

    page.locator('[data-proxy-action="rail-start"]').click()
    samples = int(requirements["minimum_rail_samples"])
    for index in range(samples):
        page.locator('[data-proxy-action="rail-advance"]').click()
        page.wait_for_timeout(18)
        if out_dir is not None and mechanic is not None and index + 1 == max(1, samples // 2):
            _shot(page, out_dir, mechanic, "simplified-active-rail-hold")
    page.wait_for_timeout(int(requirements["minimum_rail_ms"]) + 40)
    page.locator('[data-proxy-action="rail-end"]').click()


def _wait_for_work(page, truth: dict) -> None:
    """Wait through the visible film without making slow render hosts flaky."""

    longest_film = max(int(artifact["playback_ms"]) for artifact in truth["artifacts"])
    page.wait_for_function(
        "() => modifierRestorationModel.phase === 'work'",
        timeout=max(10_000, longest_film * 3),
    )


def _arrange(page, art: dict, slots: list[dict], interaction: str) -> None:
    racks = {item["token_id"]: item for item in art["rack_rects"]}
    for slot, token in zip(slots, reversed(art["stack"])):
        if interaction == "simplified":
            _proxy_place(page, str(token["id"]), int(slot["index"]))
            _proxy_invert(page, str(token["id"]))
        else:
            _place(page, racks[token["id"]], slot)
            _invert(page, slot)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator("#restoration-submit").click()
    _wait_new(state_dir, before)
    expect(page.locator('.restoration-press[data-fresh-failure="true"]')).to_be_visible(timeout=8_000)
    expect(page.locator(".readout")).to_have_text("FAIL")
    _shot(page, out_dir, mechanic, "fail-fresh-film")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    page.wait_for_timeout(1450)
    expect(page.locator('.restoration-press[data-phase="playback"]')).to_be_visible()
    _shot(page, out_dir, mechanic, "active-transformation-film")
    _wait_for_work(page, truth)

    # Spend the one permitted replay and preserve a second transient film state.
    page.locator("#restoration-replay").click()
    page.wait_for_timeout(1750)
    _shot(page, out_dir, mechanic, "costly-film-replay")
    _wait_for_work(page, truth)

    first = truth["artifacts"][0]
    racks = {item["token_id"]: item for item in first["rack_rects"]}
    if interaction == "simplified":
        _proxy_place(page, str(first["rack_order"][0]), int(truth["slots"][0]["index"]))
    else:
        _place(page, racks[first["rack_order"][0]], truth["slots"][0])
    page.locator("#restoration-reset").click()
    page.wait_for_function("() => Object.keys(modifierRestorationModel.placements).length === 0 && modifierRestorationModel.resetCount === 1")
    _shot(page, out_dir, mechanic, "partial-stack-reset")

    for index, art in enumerate(truth["artifacts"]):
        if index:
            _wait_for_work(page, truth)
        _arrange(page, art, truth["slots"], interaction)
        page.wait_for_function(
            "count => Object.keys(modifierRestorationModel.placements).length === count && modifierRestorationModel.inverted.size === count",
            arg=len(truth["slots"]),
        )
        if index == 0:
            _shot(page, out_dir, mechanic, "inverse-stack-armed")
        if interaction == "simplified":
            _proxy_rail(page, truth["requirements"], out_dir if index == 0 else None, mechanic)
        else:
            _run_rail(page, truth["rail"], int(truth["requirements"]["minimum_rail_samples"]))
        page.wait_for_function("count => modifierRestorationModel.completed.length === count", arg=index + 1, timeout=4_000)
    expect(page.locator('.restoration-press[data-completed="true"]')).to_be_visible()
    state = page.evaluate("() => ({complete:modifierRestorationModel.completed.length,replays:modifierRestorationModel.replayCount,resets:modifierRestorationModel.resetCount,samples:modifierRestorationModel.railSamples})")
    if state["complete"] != len(truth["artifacts"]) or state["replays"] != 1 or state["resets"] != 1 or state["samples"] < truth["requirements"]["minimum_rail_samples"] * len(truth["artifacts"]):
        raise AssertionError(f"restoration physical state is incomplete: {state}")
    _shot(page, out_dir, mechanic, "three-specimens-restored")
    page.locator("#restoration-submit").click()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=8_000)
    expect(page.locator(".restoration-verdict")).to_contain_text("PASS")
    expect(page.locator(".restoration-verdict")).not_to_contain_text("FAIL")
