from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "parallel_grillmaster"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, mechanic: str, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{label}.png"), full_page=True)


def _wait_new_challenge(state_dir: Path, old_challenge: str) -> None:
    deadline = time.time() + 8
    while time.time() < deadline:
        current = str(_read(state_dir / "ground_truth.json").get("challenge_id") or "")
        if current and current != old_challenge:
            return
        time.sleep(0.05)
    raise AssertionError("grillmaster challenge did not regenerate after failure")


def _move_food(page, food_id: str, destination: str, interaction: str) -> None:
    food = page.locator(f'.grill-food[data-food-id="{food_id}"]')
    if interaction == "full":
        food.drag_to(page.locator(f'.grill-zone[data-drop-zone="{destination}"]'))
    else:
        food.click()
        button = "#grill-start-selected" if destination == "grill" else "#grill-serve-selected"
        expect(page.locator(button)).to_be_enabled()
        page.locator(button).click()
    expect(
        page.locator(
            f'.grill-zone[data-drop-zone="{destination}"] '
            f'.grill-food[data-food-id="{food_id}"]'
        )
    ).to_be_visible()


def _assert_visible_layout(page) -> None:
    viewport = page.viewport_size
    if not viewport:
        raise AssertionError("grillmaster viewport size is unavailable")
    for locator in (
        page.locator(".grill-zone"),
        page.locator(".grill-food"),
        page.locator("#submit-grill"),
    ):
        for index in range(locator.count()):
            box = locator.nth(index).bounding_box()
            if not box:
                raise AssertionError("grillmaster control has no visible bounding box")
            if (
                box["x"] < -1
                or box["y"] < -1
                or box["x"] + box["width"] > viewport["width"] + 1
                or box["y"] + box["height"] > viewport["height"] + 1
            ):
                raise AssertionError(f"grillmaster control is clipped at the benchmark viewport: {box}")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    _assert_visible_layout(page)
    _screenshot(page, out_dir, mechanic, "initial")
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator("#submit-grill").click()
    _wait_new_challenge(state_dir, before)
    expect(page.locator(".readout")).to_have_text("FAIL", timeout=8_000)
    _assert_visible_layout(page)
    _screenshot(page, out_dir, mechanic, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    targets = truth["targets"]
    grill = page.locator('.grill-zone[data-drop-zone="grill"]')
    tray = page.locator('.grill-zone[data-drop-zone="tray"]')
    if not grill.is_visible() or not tray.is_visible():
        raise AssertionError("grill or tray is not visible")

    due: list[tuple[float, str]] = []
    ready: list[tuple[float, str]] = []
    for food_id, target in targets.items():
        _move_food(page, food_id, "grill", interaction)
        started = float(
            page.evaluate("foodId => grillModel.records[foodId].startedAt", food_id)
        )
        due.append((started + float(target["target_ms"]), food_id))
        ready.append(
            (
                started
                + float(target["target_ms"])
                - float(target["tolerance_ms"])
                + 120,
                food_id,
            )
        )
    _screenshot(page, out_dir, mechanic, "active-all-started")

    first_ready_at = min(item[0] for item in ready)
    now = float(page.evaluate("performance.now()"))
    if first_ready_at > now:
        page.wait_for_timeout(int(first_ready_at - now))
    expect(page.locator('.grill-food[data-cook-state="ready"]')).not_to_have_count(0)
    _screenshot(page, out_dir, mechanic, "active-ready-window")

    for due_at, food_id in sorted(due):
        now = float(page.evaluate("performance.now()"))
        if due_at > now:
            page.wait_for_timeout(int(due_at - now))
        _move_food(page, food_id, "tray", interaction)
    expect(tray.locator(".grill-food")).to_have_count(len(targets))
    _screenshot(page, out_dir, mechanic, "solved-before-submit")
    page.locator("#submit-grill").click()
    expect(page.locator(".readout")).to_have_attribute("data-status", "passed", timeout=8_000)
    _screenshot(page, out_dir, mechanic, "pass")

    result = _read(state_dir / "result.json")
    truth = _read(state_dir / "ground_truth.json")
    if (result.get("server_grade") or {}).get("passed") is not True:
        raise AssertionError(f"server rejected grillmaster solve: {result.get('server_grade')}")
    expected_source = "food_drag" if interaction == "full" else "grill_proxy_controls"
    witness = result.get("trusted_witness") or {}
    actions = witness.get("actions") or []
    if len(actions) != 2 * len(targets):
        raise AssertionError("grillmaster result lacks two witnessed actions per food")
    if any(action.get("input_source") != expected_source for action in actions):
        raise AssertionError("grillmaster witness contains a cross-mode input source")
    if witness.get("clock_source") != "server_active_task_clock_v1":
        raise AssertionError("grillmaster result lacks the trusted task-time clock")
    exported = {
        "public_state": _read(state_dir / "public_state.json"),
        "ground_truth": truth,
        "result": result,
    }
    (out_dir / "exported-result.json").write_text(
        json.dumps(exported, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
