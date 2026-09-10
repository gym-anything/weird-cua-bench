"""Visible-input Playwright solver used for Last Seats in the Lagoon evidence."""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect


DELTAS = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, mechanic: str, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{name}.png"), full_page=True)


def _boat_cells(boat: dict, anchor: tuple[int, int] | None = None) -> set[tuple[int, int]]:
    x, y = anchor or (int(boat["x"]), int(boat["y"]))
    width, height = (2, 1) if boat.get("orientation") == "horizontal" else (1, 2)
    return {(x + dx, y + dy) for dx in range(width) for dy in range(height)}


def _candidate_clear(state: dict, boat: dict, anchor: tuple[int, int]) -> bool:
    columns = int(state["board"]["columns"])
    rows = int(state["board"]["rows"])
    footprint = _boat_cells(boat, anchor)
    if any(x < 0 or y < 0 or x >= columns or y >= rows for x, y in footprint):
        return False
    if footprint & {tuple(item) for item in state.get("reefs", [])}:
        return False
    return all(
        not footprint.intersection(_boat_cells(other))
        for other in state.get("boats", [])
        if str(other.get("id")) != str(boat.get("id"))
    )


def blocked_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    """Exercise one visibly blocked move, then leave the board unchanged.

    The browser mechanic reports the blocked attempt but must not add it to the
    certifiable action transcript.  This is a recovery check, not an agent
    result: the route witness is still used by ``solve`` after this probe.
    """
    state = _read(state_dir / "public_state.json")
    blocked: tuple[str, str] | None = None
    for boat in state.get("boats", []):
        for direction, (dx, dy) in DELTAS.items():
            anchor = (int(boat["x"]) + dx, int(boat["y"]) + dy)
            if not _candidate_clear(state, boat, anchor):
                blocked = (str(boat["id"]), direction)
                break
        if blocked is not None:
            break
    if blocked is None:
        raise AssertionError("could not find a legal initial boat movement to reject")
    boat_id, direction = blocked
    interaction = str((state.get("control_condition") or {}).get("interaction") or "full")
    if interaction == "simplified":
        page.locator(f'[data-lagoon-select="{boat_id}"]').click()
        page.locator(f'[data-lagoon-direction="{direction}"]').click()
    else:
        _drag_one_cell(
            page,
            boat_id,
            direction,
            int(state["board"]["columns"]),
            int(state["board"]["rows"]),
        )
    expect(page.locator(".lagoon-footer .readout")).to_have_text("MOVE BLOCKED", timeout=6000)
    if _read(state_dir / "public_state.json")["challenge_id"] != state["challenge_id"]:
        raise AssertionError("blocked movement changed the challenge")
    _screenshot(page, out_dir, mechanic, "blocked-recovery")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator(".lagoon-abandon").click()
    expect(page.locator(".lagoon-footer .readout")).to_contain_text("FAIL", timeout=6000)
    after = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    if before == after:
        raise AssertionError("last_seats_in_the_lagoon did not regenerate after deliberate failure")
    # The failure frame belongs to the old challenge.  The server response
    # carries a new challenge, which must render with a neutral READY state.
    _screenshot(page, out_dir, mechanic, "fail-refresh")
    # Locator assertions poll from Playwright rather than the task's frozen
    # requestAnimationFrame clock in a zero-window paused run.
    expect(page.locator(".lagoon-captcha")).to_have_attribute(
        "data-challenge-id", after, timeout=6000
    )
    expect(page.locator(".lagoon-footer .readout")).to_have_text("READY", timeout=6000)
    if page.locator(".lagoon-captcha.is-failed").count():
        raise AssertionError("fresh lagoon still carries the previous failure overlay")
    _screenshot(page, out_dir, mechanic, "fresh-neutral")


def _drag_one_cell(page, boat_id: str, direction: str, columns: int, rows: int) -> None:
    boat = page.locator(f'.lagoon-boat[data-boat-id="{boat_id}"]')
    box = boat.bounding_box()
    board = page.locator(".lagoon-board").bounding_box()
    if box is None or board is None:
        raise AssertionError(f"could not locate {boat_id} for visible drag")
    dx, dy = DELTAS[direction]
    start_x = box["x"] + box["width"] / 2
    start_y = box["y"] + box["height"] / 2
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(
        start_x + dx * board["width"] / columns,
        start_y + dy * board["height"] / rows,
        steps=2,
    )
    page.mouse.up()


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    truth = _read(state_dir / "ground_truth.json")
    state = _read(state_dir / "public_state.json")
    route = list(truth["solution_path"])
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    columns = int(state["board"]["columns"])
    rows = int(state["board"]["rows"])
    _screenshot(page, out_dir, mechanic, "initial")
    for index, step in enumerate(route):
        boat_id = str(step["boat_id"])
        direction = str(step["direction"])
        if interaction == "simplified":
            page.locator(f'[data-lagoon-select="{boat_id}"]').click()
            page.locator(f'[data-lagoon-direction="{direction}"]').click()
        else:
            _drag_one_cell(page, boat_id, direction, columns, rows)
        page.wait_for_timeout(20)
        if index == max(1, len(route) // 2):
            _screenshot(page, out_dir, mechanic, "active")
    page.locator(".lagoon-certify").click()
    expect(page.locator(".lagoon-footer .readout")).to_contain_text("PASS", timeout=8000)
    _screenshot(page, out_dir, mechanic, "pass")
