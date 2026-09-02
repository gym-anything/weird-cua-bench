from __future__ import annotations

import json
from pathlib import Path


MECHANIC_ID = "terrarium_order_of_operations"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _interaction(state_dir: Path) -> str:
    public = _read(state_dir / "public_state.json")
    return str((public.get("control_condition") or {}).get("interaction") or "full")


def _order(state_dir: Path) -> list[str]:
    return [str(item) for item in _read(state_dir / "ground_truth.json")["solution_order"]]


def _wait(page, state_dir: Path) -> None:
    public = _read(state_dir / "public_state.json")
    page.wait_for_timeout(int(public["parameters"]["cascade_ms"]) + 80)


def _inoculate(page, module_id: str, interaction: str) -> None:
    if interaction == "simplified":
        page.locator(f'[data-proxy-add="{module_id}"]').click()
        return
    capsule = page.locator(f'[data-capsule="{module_id}"]')
    hatch = page.locator("#too-hatch")
    capsule_box = capsule.bounding_box()
    hatch_box = hatch.bounding_box()
    if capsule_box is None or hatch_box is None:
        raise AssertionError(f"missing visible capsule or hatch geometry for {module_id}")
    start_x = capsule_box["x"] + capsule_box["width"] / 2
    start_y = capsule_box["y"] + capsule_box["height"] / 2
    end_x = hatch_box["x"] + hatch_box["width"] / 2
    end_y = hatch_box["y"] + hatch_box["height"] / 2
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(end_x, end_y, steps=10)
    page.mouse.up()


def _run(page, state_dir: Path, order: list[str]) -> None:
    interaction = _interaction(state_dir)
    for module_id in order:
        _inoculate(page, module_id, interaction)
        _wait(page, state_dir)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    challenge_before = _read(state_dir / "public_state.json")["challenge_id"]
    solution = _order(state_dir)
    wrong = list(reversed(solution))
    if wrong == solution:
        wrong[0], wrong[1] = wrong[1], wrong[0]
    _run(page, state_dir, wrong)
    page.locator(".too-verdict.is-fail").wait_for(state="visible")
    page.screenshot(path=str(out_dir / "same-world-failure.png"))
    page.locator("#too-reset").click()
    page.locator(".too-verdict").wait_for(state="detached")
    if _read(state_dir / "public_state.json")["challenge_id"] != challenge_before:
        raise AssertionError("local retry changed the generated causal world")
    page.screenshot(path=str(out_dir / "same-world-retry.png"))
    _run(page, state_dir, wrong)
    page.locator(".too-verdict.is-fail").wait_for(state="visible")
    page.screenshot(path=str(out_dir / "local-wilted-run.png"))
    page.locator("#too-certify").click()
    page.locator('.terrarium-order[data-fresh-failure="true"] .too-verdict.is-fail').wait_for(state="visible")


def exercise_local_recovery(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    """Create a visible failed run, then retry the same challenge without server regeneration."""
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    challenge_before = _read(state_dir / "public_state.json")["challenge_id"]
    solution = _order(state_dir)
    wrong = list(reversed(solution))
    _run(page, state_dir, wrong)
    page.locator(".too-verdict.is-fail").wait_for(state="visible")
    page.screenshot(path=str(out_dir / "same-world-failure.png"))
    page.locator("#too-reset").click()
    page.locator(".too-verdict").wait_for(state="detached")
    challenge_after = _read(state_dir / "public_state.json")["challenge_id"]
    if challenge_after != challenge_before:
        raise AssertionError("local retry changed the generated causal world")
    page.screenshot(path=str(out_dir / "same-world-retry.png"))


def solve(page, state_dir: Path, out_dir: Path, mechanic: str, *, certify: bool = True) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    solution = _order(state_dir)
    for index, module_id in enumerate(solution):
        _inoculate(page, module_id, _interaction(state_dir))
        if index == max(0, len(solution) // 2 - 1):
            page.screenshot(path=str(out_dir / "active-cascade.png"))
        _wait(page, state_dir)
    page.locator(".too-verdict.is-ready").wait_for(state="visible")
    page.screenshot(path=str(out_dir / "solved-before-certify.png"))
    if certify:
        page.locator("#too-certify").click()
        page.locator(".too-verdict.is-pass").wait_for(state="visible")
