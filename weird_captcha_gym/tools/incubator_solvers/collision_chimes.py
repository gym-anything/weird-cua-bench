from __future__ import annotations

import json
from pathlib import Path


MECHANIC_ID = "collision_chimes"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=True)


def _place_full(page, cell: dict) -> None:
    target = page.locator(
        f'.grid-cell[data-row="{int(cell["row"])}"][data-col="{int(cell["col"])}"]'
    )
    page.locator("#chime-seed").drag_to(target)
    for _ in range(int(cell["direction"]) % 4):
        page.locator(f'.placed-cell[data-cell-id="{cell["id"]}"]').click()


def _place_simplified(page, cell: dict) -> None:
    target = page.locator(
        f'.grid-cell[data-row="{int(cell["row"])}"][data-col="{int(cell["col"])}"]'
    )
    target.click()
    page.locator("#add-cell").click()
    for _ in range(int(cell["direction"]) % 4):
        page.locator("#cycle-cell").click()


def _configure(page, cells: list[dict], interaction: str) -> None:
    for cell in cells:
        if interaction == "full":
            _place_full(page, cell)
        elif interaction == "simplified":
            _place_simplified(page, cell)
        else:
            raise AssertionError(f"unsupported interaction {interaction!r}")


def _run_and_check(page, out_dir: Path, label: str) -> None:
    page.locator("#run-film").click()
    page.wait_for_function(
        "() => window.collisionChimesModel?.phase === 'complete'",
        timeout=20_000,
    )
    _shot(page, out_dir, f"{label}-film")
    page.locator("#submit-sequence").click()


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    before = str(truth["challenge_id"])
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "simplified")
    _configure(page, truth.get("failure_cells") or [], interaction)
    _run_and_check(page, out_dir, "failure")
    page.wait_for_function(
        "() => document.querySelector('.collision-chimes')?.dataset.freshFailure === 'true' && document.querySelector('.collision-chimes')?.classList.contains('is-failed')",
        timeout=12_000,
    )
    _shot(page, out_dir, "failed")
    after = _read(state_dir / "ground_truth.json")["challenge_id"]
    if before == after:
        raise AssertionError("failed chime film did not load a fresh challenge")
    page.wait_for_function(
        "() => document.querySelector('.collision-chimes')?.dataset.freshFailure === 'true' && !document.querySelector('.collision-chimes')?.classList.contains('is-failed')",
        timeout=12_000,
    )
    status = page.evaluate(
        "() => ({failed: document.querySelector('.collision-chimes')?.classList.contains('is-failed'), fresh: document.querySelector('.collision-chimes')?.dataset.freshFailure})"
    )
    if status != {"failed": False, "fresh": "true"}:
        raise AssertionError(f"fresh chime board retained stale failure state: {status}")
    _shot(page, out_dir, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "simplified")
    _configure(page, truth.get("solution_cells") or [], interaction)
    _shot(page, out_dir, "configured")
    _run_and_check(page, out_dir, "solution")
    page.wait_for_function(
        "() => document.querySelector('.collision-chimes')?.classList.contains('is-passed')",
        timeout=12_000,
    )
    contract = page.evaluate(
        "() => ({phase: window.collisionChimesModel?.phase, beat: window.collisionChimesModel?.beat, events: window.collisionChimesModel?.wallEvents?.length, cells: window.collisionChimesModel?.cells?.length})"
    )
    if contract["phase"] != "submitting" or contract["beat"] != int(truth["contract"]["beats"]):
        raise AssertionError(f"chime film did not visibly settle before pass: {contract}")
    _shot(page, out_dir, "passed")

