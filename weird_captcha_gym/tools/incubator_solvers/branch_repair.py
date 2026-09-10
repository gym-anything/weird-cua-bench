from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "branch_repair"
VIEWS = ("xy", "xz", "yz")
VIEW_NORMAL = {"xy": "z", "xz": "y", "yz": "x"}
AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"branch_repair-{name}.png"), full_page=True)


def _wait_new(state_dir: Path, before: str) -> None:
    deadline = time.time() + 8
    while time.time() < deadline:
        if str(_read(state_dir / "ground_truth.json").get("challenge_id")) != before:
            return
        time.sleep(0.05)
    raise AssertionError("branch repair challenge did not regenerate after failure")


def _interaction(truth: dict) -> str:
    return str((truth.get("control_condition") or {}).get("interaction") or truth.get("interaction") or "full")


def _view_with_pair(truth: dict, edge: list[str]) -> tuple[str, int]:
    by_id = {node["id"]: node for node in truth["nodes"]}
    count = int(truth["slice_contract"]["index_count"])
    for view in VIEWS:
        normal = {"xy": 2, "xz": 1, "yz": 0}[view]
        lo = min(float(by_id[edge[0]]["p"][normal]), float(by_id[edge[1]]["p"][normal]))
        hi = max(float(by_id[edge[0]]["p"][normal]), float(by_id[edge[1]]["p"][normal]))
        for index in range(count):
            level = -4.0 + 8.0 * index / max(1, count - 1)
            if abs(level - lo) <= 0.72 and abs(level - hi) <= 0.72:
                return view, index
    raise AssertionError(f"no linked plane contains edge {edge}")


def _set_focus_simplified(page, axis: str, target: int) -> None:
    current = int(page.evaluate("axis => window.branchRepairModel.focus[{x:0,y:1,z:2}[axis]]", axis))
    selector = f".branch-slice-step[data-axis='{axis}'][data-delta='{{delta}}']"
    while current != target:
        delta = 1 if target > current else -1
        page.locator(selector.format(delta=delta)).click()
        current += delta


def _set_focus_full(page, view: str, target: int) -> None:
    axis = {"xy": "z", "xz": "y", "yz": "x"}[view]
    current = int(page.evaluate("axis => window.branchRepairModel.focus[{x:0,y:1,z:2}[axis]]", axis))
    canvas = page.locator(f".branch-slice[data-view='{view}']")
    box = canvas.bounding_box()
    if not box:
        raise AssertionError(f"missing {view} canvas")
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    while current != target:
        direction = 1 if target > current else -1
        page.mouse.wheel(0, 100 if direction > 0 else -100)
        current += direction
        page.wait_for_timeout(12)


def _collect_slice_observations(page, truth: dict, interaction: str, out_dir: Path | None = None) -> None:
    count = int(truth["slice_contract"]["index_count"])
    # These are ordinary initial observations for the film, not a grader
    # quota.  The grader's required observations are the inspections emitted
    # after each topology edit below.
    candidates = [0, count - 1] if count > 1 else [0]
    view = "xy" if interaction == "full" else None
    for offset, index in enumerate(candidates):
        if interaction == "full":
            _set_focus_full(page, view, index)
        else:
            _set_focus_simplified(page, "z", index)
        if offset == 1 and out_dir is not None:
            _shot(page, out_dir, "linked-slices")


def _orbit(page, truth: dict, interaction: str) -> None:
    required = 1
    if interaction == "simplified":
        directions = ["right", "up", "left", "down"]
        for index in range(required):
            page.locator(f".branch-orbit[data-direction='{directions[index % len(directions)]}']").click()
        return
    mesh = page.locator(".branch-mesh")
    box = mesh.bounding_box()
    if not box:
        raise AssertionError("missing branch mesh")
    for index in range(required):
        start = (box["x"] + box["width"] - 38, box["y"] + 28)
        end = (start[0] - 28 - index * 3, start[1] + 18 + index * 2)
        page.mouse.move(*start); page.mouse.down(); page.mouse.move(*end, steps=8); page.mouse.up(); page.wait_for_timeout(20)


def _mesh_point(page, node_id: str) -> tuple[float, float]:
    value = page.evaluate("node => window.branchRepairModel.projectNode(node)", node_id)
    if not value:
        raise AssertionError(f"node is not projected: {node_id}")
    box = page.locator(".branch-mesh").bounding_box()
    if not box:
        raise AssertionError("missing branch mesh")
    return box["x"] + float(value[0]) / 720 * box["width"], box["y"] + float(value[1]) / 290 * box["height"]


def _merge_missing(page, truth: dict, interaction: str, out_dir: Path | None = None) -> None:
    for index, edge in enumerate(truth["missing_edges"]):
        if interaction == "simplified":
            page.locator("#branch-merge-a").select_option(edge[0])
            page.locator("#branch-merge-b").select_option(edge[1])
            page.locator(".branch-select-pair").click()
            page.locator(".branch-merge").click()
        else:
            start = _mesh_point(page, edge[0]); end = _mesh_point(page, edge[1])
            page.mouse.move(*start); page.mouse.down(); page.mouse.move(*end, steps=10); page.mouse.up(); page.wait_for_timeout(30)
        if index == 0 and out_dir is not None:
            _shot(page, out_dir, "missing-join-regenerated")
        _inspect_after_edit(page, truth, interaction, index)


def _inspect_after_edit(page, truth: dict, interaction: str, edit_index: int) -> None:
    count = int(truth["slice_contract"]["index_count"])
    axis = ("z", "y", "x")[edit_index % 3]
    current = int(page.evaluate("axis => window.branchRepairModel.focus[{x:0,y:1,z:2}[axis]]", axis))
    target = (current + 1) % count if count > 1 else current
    if interaction == "full":
        _set_focus_full(page, {"x": "yz", "y": "xz", "z": "xy"}[axis], target)
    else:
        _set_focus_simplified(page, axis, target)


def _seed_click_full(page, view: str, node_id: str) -> None:
    local = page.evaluate("args => window.branchRepairModel.seedScreen(args.view, args.node)", {"view": view, "node": node_id})
    if not local:
        raise AssertionError(f"{node_id} is not visible in {view}")
    canvas = page.locator(f".branch-slice[data-view='{view}']")
    box = canvas.bounding_box()
    if not box:
        raise AssertionError(f"missing {view} canvas")
    page.mouse.click(box["x"] + float(local[0]) / 230 * box["width"], box["y"] + float(local[1]) / 154 * box["height"])


def _cut_false(page, truth: dict, interaction: str, out_dir: Path | None = None) -> None:
    for index, edge in enumerate(truth["false_edges"]):
        view, focus_index = _view_with_pair(truth, edge)
        if interaction == "full":
            _set_focus_full(page, view, focus_index)
            page.locator(".branch-seed-color[data-color='red']").click()
            _seed_click_full(page, view, edge[0])
            page.locator(".branch-seed-color[data-color='green']").click()
            _seed_click_full(page, view, edge[1])
        else:
            _set_focus_simplified(page, {"xy": "z", "xz": "y", "yz": "x"}[view], focus_index)
            page.locator("#branch-seed-view").select_option(view)
            page.locator("#branch-seed-segment").select_option(edge[0])
            page.locator(".branch-seed-color[data-color='red']").click(); page.locator(".branch-place-seed").click()
            page.locator("#branch-seed-segment").select_option(edge[1])
            page.locator(".branch-seed-color[data-color='green']").click(); page.locator(".branch-place-seed").click()
        page.locator(".branch-cut").click()
        if index == 0 and out_dir is not None:
            _shot(page, out_dir, "opposite-seed-cut")
        _inspect_after_edit(page, truth, interaction, len(truth["missing_edges"]) + index)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(mechanic)
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator(".branch-certify").click()
    _wait_new(state_dir, before)
    expect(page.locator(".branch-repair-captcha[data-fresh-failure='true']")).to_be_visible(timeout=8_000)
    _shot(page, out_dir, "fail-fresh-specimen")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(mechanic)
    truth = _read(state_dir / "ground_truth.json")
    interaction = _interaction(truth)
    _collect_slice_observations(page, truth, interaction, out_dir)
    _orbit(page, truth, interaction)
    _merge_missing(page, truth, interaction, out_dir)
    _cut_false(page, truth, interaction, out_dir)
    _shot(page, out_dir, "repaired-topology")
    page.locator(".branch-certify").click()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=8_000)
    _shot(page, out_dir, "pass")
