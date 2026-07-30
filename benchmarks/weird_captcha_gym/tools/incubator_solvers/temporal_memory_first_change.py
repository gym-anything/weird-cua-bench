from __future__ import annotations

import math
from pathlib import Path

from playwright.sync_api import expect

from benchmarks.weird_captcha_gym.tools.incubator_solvers.reviewed_overhaul_common import (
    expect_fail_and_fresh,
    read_json,
    shot,
)

MECHANIC_ID = "temporal_memory_first_change"


def _settled_point(timeline: dict, object_id: str) -> tuple[float, float]:
    index = timeline["settle_order"].index(object_id)
    grid = timeline["settle_grid"]
    return grid["x0"] + index % grid["columns"] * grid["dx"], grid["y0"] + index // grid["columns"] * grid["dy"]


def _canvas_screen(page, x: float, y: float) -> tuple[float, float]:
    box = page.locator(".tracking-canvas").bounding_box()
    assert box
    return box["x"] + x / 700 * box["width"], box["y"] + y / 330 * box["height"]


def _set_review_time(page, timeline: dict, at_ms: int) -> None:
    slider = page.locator(".tracking-spool")
    slider.focus()
    page.keyboard.press("Home")
    steps = round(at_ms / int(timeline["review_step_ms"]))
    for _ in range(steps):
        page.keyboard.press("ArrowRight")


def _moving_point(item: dict, elapsed: float) -> tuple[float, float]:
    return (
        float(item["x0"]) + math.sin(float(item["phase"]) + elapsed * float(item["rate_x"])) * float(item["amp_x"]),
        float(item["y0"]) + math.cos(float(item["phase"]) * .83 + elapsed * float(item["rate_y"])) * float(item["amp_y"]),
    )


def _interaction(state: dict) -> str:
    return str((state.get("control_condition") or {}).get("interaction") or "full")


def _place_lens(page, state: dict, x: float, y: float) -> None:
    if _interaction(state) == "full":
        page.mouse.move(*_canvas_screen(page, x, y), steps=3)
        return
    page.locator(".tracking-lens-x").fill(str(round(x)))
    page.locator(".tracking-lens-y").fill(str(round(y)))
    page.locator(".tracking-place-lens").click()


def _select_settled(page, state: dict, timeline: dict, object_id: str) -> None:
    if _interaction(state) == "full":
        page.mouse.click(*_canvas_screen(page, *_settled_point(timeline, object_id)))
        return
    page.locator(f'.tracking-slot-controls [data-object-id="{object_id}"]').click()


def _wait_review(page) -> None:
    expect(page.locator('.tracking-review[data-visible="true"]')).to_be_visible(timeout=13_000)
    expect(page.locator(".tracking-return")).to_be_enabled()


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    assert mechanic == MECHANIC_ID
    state, truth = read_json(state_dir / "public_state.json"), read_json(state_dir / "ground_truth.json")
    before, timeline = truth["challenge_id"], state["timeline"]
    page.locator(".tracking-arm").click()
    _wait_review(page)
    page.locator(".tracking-return").click()
    wrong = next(item["id"] for item in timeline["objects"] if item["id"] != truth["target_object_id"])
    _select_settled(page, state, timeline, wrong)
    page.wait_for_timeout(120)
    shot(page, out_dir, mechanic, "wrong-uninspected-carrier-fail")
    expect_fail_and_fresh(page, state_dir, before)
    shot(page, out_dir, mechanic, "wrong-uninspected-carrier-rejected")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    assert mechanic == MECHANIC_ID
    state, truth = read_json(state_dir / "public_state.json"), read_json(state_dir / "ground_truth.json")
    timeline, target_id = state["timeline"], truth["target_object_id"]
    target = next(item for item in timeline["objects"] if item["id"] == target_id)
    first = timeline["events"][0]
    page.locator(".tracking-arm").click()
    _wait_review(page)

    proof = timeline["proof"]
    pre_count = int(proof["minimum_pre_hits"])
    change_count = int(proof["minimum_change_hits"])
    first_at = int(first["at_ms"])
    for index in range(pre_count):
        pre_time = first_at - 300 + int(220 * index / max(1, pre_count - 1))
        _set_review_time(page, timeline, pre_time)
        _place_lens(page, state, *_moving_point(target, pre_time))
        page.wait_for_timeout(180)
    for index in range(change_count):
        change_time = first_at + int(int(first["duration_ms"]) * (index + 1) / (change_count + 1))
        _set_review_time(page, timeline, change_time)
        _place_lens(page, state, *_moving_point(target, change_time))
        page.wait_for_timeout(180)
    shot(page, out_dir, mechanic, "active-review-lens-first-change")

    page.locator(".tracking-return").click()
    _select_settled(page, state, timeline, target_id)
