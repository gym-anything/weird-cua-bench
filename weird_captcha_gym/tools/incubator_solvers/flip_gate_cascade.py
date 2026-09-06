from __future__ import annotations

import json
from pathlib import Path


MECHANIC_ID = "flip_gate_cascade"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"))


def _drag_marble(page, chute: int, step_delay_ms: int = 0) -> None:
    marble = page.locator(".feed-marble")
    mouth = page.locator(f'.cascade-chute[data-chute="{chute}"]')
    marble_box = marble.bounding_box()
    mouth_box = mouth.bounding_box()
    if marble_box is None or mouth_box is None:
        raise AssertionError(f"marble or chute {chute} has no visible bounds")
    start_x = marble_box["x"] + marble_box["width"] / 2
    start_y = marble_box["y"] + marble_box["height"] / 2
    end_x = mouth_box["x"] + mouth_box["width"] / 2
    end_y = mouth_box["y"] + mouth_box["height"] / 2
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    for step in range(1, 13):
        ratio = step / 12
        page.mouse.move(
            start_x + (end_x - start_x) * ratio,
            start_y + (end_y - start_y) * ratio,
        )
        if step_delay_ms:
            page.wait_for_timeout(step_delay_ms)
    page.mouse.up()


def _drop(
    page,
    chute: int,
    interaction: str,
    expected_events: int,
    *,
    active_shot: Path | None = None,
    step_delay_ms: int = 0,
) -> None:
    _send_drop(page, chute, interaction, step_delay_ms=step_delay_ms)
    if active_shot is not None:
        page.wait_for_timeout(320)
        page.screenshot(path=str(active_shot))
    page.wait_for_function(
        "expected => window.flipGateCascadeModel.events.length >= expected",
        arg=expected_events,
        timeout=8000,
    )


def _send_drop(page, chute: int, interaction: str, *, step_delay_ms: int = 0) -> None:
    if interaction == "simplified":
        page.locator(f'.cascade-chute[data-chute="{chute}"]').click()
    elif interaction == "full":
        _drag_marble(page, chute, step_delay_ms=step_delay_ms)
    else:
        raise AssertionError(f"unsupported interaction {interaction!r}")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    before = truth["challenge_id"]
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "simplified")
    sequence = [int(value) for value in truth.get("failure_chutes") or []]
    if len(sequence) != int(truth["machine"]["drop_budget"]):
        raise AssertionError("failure sequence does not consume the exact visible tray")
    for index, chute in enumerate(sequence[:-1], start=1):
        active = out_dir / f"{MECHANIC_ID}-active-path.png" if index == 1 else None
        _drop(page, chute, interaction, index, active_shot=active)
    _send_drop(page, sequence[-1], interaction)
    page.wait_for_function(
        "() => document.querySelector('.flip-gate-cascade')?.dataset.freshFailure === 'true' && document.querySelector('.flip-gate-cascade')?.classList.contains('is-failed')",
        timeout=10000,
    )
    _shot(page, out_dir, "failed")
    after = _read(state_dir / "ground_truth.json")["challenge_id"]
    if before == after:
        raise AssertionError("failed tray did not load a fresh challenge")
    page.wait_for_function(
        "() => document.querySelector('.flip-gate-cascade')?.dataset.freshFailure === 'true' && !document.querySelector('.flip-gate-cascade')?.classList.contains('is-failed')",
        timeout=10000,
    )
    status = page.evaluate(
        "() => ({failed: document.querySelector('.flip-gate-cascade')?.classList.contains('is-failed'), fresh: document.querySelector('.flip-gate-cascade')?.dataset.freshFailure})"
    )
    if status != {"failed": False, "fresh": "true"}:
        raise AssertionError(f"fresh cascade retained stale failure state: {status}")
    _shot(page, out_dir, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "simplified")
    solution = [int(value) for value in truth.get("solution_chutes") or []]
    if len(solution) != int(truth["machine"]["optimal_depth"]):
        raise AssertionError("solution is not the declared exact-depth path")
    for index, chute in enumerate(solution, start=1):
        active = out_dir / f"{MECHANIC_ID}-solution-path.png" if index == max(1, len(solution) // 2) else None
        _drop(page, chute, interaction, index, active_shot=active)
    page.wait_for_function(
        "() => document.querySelector('.flip-gate-cascade')?.classList.contains('is-passed')",
        timeout=10000,
    )
    contract = page.evaluate(
        "() => ({state: window.flipGateCascadeModel.current, events: window.flipGateCascadeModel.events.length, busy: window.flipGateCascadeModel.busy})"
    )
    if contract["state"] != truth["machine"]["target_state"] or contract["events"] != len(solution) or contract["busy"]:
        raise AssertionError(f"cascade did not visibly settle at the target: {contract}")
    _shot(page, out_dir, "passed")
