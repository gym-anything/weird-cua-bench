from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "patchwork_skirmish"
DIRS = {"north": (-1, 0), "south": (1, 0), "west": (0, -1), "east": (0, 1)}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"patchwork_skirmish-{label}.png"), full_page=True)


def _wait_for_new_challenge(state_dir: Path, previous: str) -> None:
    deadline = time.time() + 8
    while time.time() < deadline:
        if str(_read(state_dir / "ground_truth.json").get("challenge_id") or "") != previous:
            return
        time.sleep(0.05)
    raise AssertionError("patchwork certification did not issue a fresh challenge")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    previous = str(_read(state_dir / "ground_truth.json").get("challenge_id") or "")
    page.locator("#patchwork-submit").click()
    _wait_for_new_challenge(state_dir, previous)
    expect(page.locator(".patchwork-skirmish")).to_have_attribute("data-fresh-failure", "true", timeout=8_000)
    expect(page.locator(".readout")).to_contain_text("FAIL", timeout=8_000)
    _shot(page, out_dir, "failure-fresh-patch")


def _snapshot(page) -> dict:
    return page.evaluate("() => window.patchworkSkirmishModel.snapshot()")


def _select(page, interaction: str, unit_id: str, state: dict) -> None:
    if interaction == "simplified":
        page.locator(f"[data-select-unit='{unit_id}']").click()
    else:
        cells = state["units"][unit_id]["cells"]
        row, col = cells[0]
        if page.locator(f".patchwork-cell.is-selected[data-unit-id='{unit_id}']").count() == 0:
            page.locator(f".patchwork-cell[data-cell='{row},{col}']").click()


def _click_move(page, interaction: str, unit_id: str, direction: str, state: dict) -> None:
    if interaction == "simplified":
        page.locator(f".patchwork-move[data-direction='{direction}']").click()
        return
    cells = state["units"][unit_id]["cells"]
    dr, dc = DIRS[direction]
    current = {tuple(cell) for cell in cells}
    candidates = [(row + dr, col + dc) for row, col in cells]
    other_targets = set()
    for other_direction, (other_dr, other_dc) in DIRS.items():
        if other_direction == direction:
            continue
        other_targets.update((row + other_dr, col + other_dc) for row, col in cells)
    row, col = next((cell for cell in candidates if cell not in current and cell not in other_targets), None) or next((cell for cell in candidates if cell not in current), candidates[0])
    page.locator(f".patchwork-cell[data-cell='{row},{col}']").click()


def _click_attack(page, interaction: str, target_id: str, state: dict) -> None:
    if interaction == "simplified":
        page.locator(f".patchwork-attack-target[data-target='{target_id}']").click()
        return
    row, col = state["units"][target_id]["cells"][0]
    page.locator(f".patchwork-cell[data-cell='{row},{col}']").click()


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    page.wait_for_function("() => document.querySelector('.patchwork-skirmish')?.dataset.freshFailure === 'false'", timeout=4_000)
    _shot(page, out_dir, "fresh-retry-start")

    # The oracle only supplies an ordinary move/strike/end-turn sequence for
    # construction evidence. Every event below is issued through the visible
    # roster, quilt cells, and turn button.
    grader_events = _load_plan(truth["world"])
    attack_seen = False
    end_seen = False
    for grader_index, item in enumerate(grader_events):
        state = _snapshot(page)
        event_type = item["type"]
        if event_type == "move":
            _select(page, interaction, item["unit_id"], state)
            _click_move(page, interaction, item["unit_id"], item["direction"], _snapshot(page))
        elif event_type == "attack":
            _select(page, interaction, item["unit_id"], state)
            _click_attack(page, interaction, item["target_id"], _snapshot(page))
            attack_seen = True
        elif event_type == "end_turn":
            page.locator("#patchwork-end-turn").click()
            end_seen = True
        else:
            raise AssertionError(f"unknown oracle event {event_type!r}")
        page.wait_for_timeout(8)
        committed = page.evaluate("() => window.patchworkSkirmishModel.events()")
        if len(committed) != grader_index + 1:
            raise AssertionError(f"visible control did not commit oracle event {grader_index + 1}: {committed[-2:]}")
        if attack_seen and not end_seen:
            _shot(page, out_dir, "first-strike"); attack_seen = False
        if end_seen and not attack_seen:
            _shot(page, out_dir, "rival-response"); end_seen = False

    expect(page.locator("#patchwork-status-line")).to_contain_text("CERTIFY", timeout=4_000)
    _shot(page, out_dir, "solved-board")
    page.locator("#patchwork-submit").click()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=8_000)
    expect(page.locator(".patchwork-skirmish")).to_have_attribute("data-verdict", "pass")


def _load_plan(world: dict) -> list[dict]:
    # Keep the browser driver independent from import path layout used by the
    # task server. This is a construction oracle, not a UI shortcut.
    import importlib.util

    path = Path(__file__).resolve().parents[2] / "shared_runtime" / "server" / "incubator_graders" / "patchwork_skirmish.py"
    spec = importlib.util.spec_from_file_location("patchwork_plan_grader", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.plan(world)
