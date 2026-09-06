from __future__ import annotations

import json
import time
from pathlib import Path


MECHANIC_ID = "silent_colleague"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _interaction(state_dir: Path) -> str:
    public = _read(state_dir / "public_state.json")
    return str((public.get("control_condition") or {}).get("interaction") or "full")


def _positions(page) -> tuple[int, int]:
    player = int(page.locator(".sc-avatar.player").get_attribute("data-loop-index"))
    colleague = int(page.locator(".sc-avatar.colleague").get_attribute("data-loop-index"))
    return player, colleague


def _step(page, direction: int, interaction: str) -> None:
    if interaction == "full":
        page.keyboard.press("ArrowRight" if direction > 0 else "ArrowLeft")
    else:
        selector = '[data-sc-act="cw"]' if direction > 0 else '[data-sc-act="ccw"]'
        box = page.locator(selector).bounding_box()
        if not box:
            raise AssertionError(f"visible movement control has no pointer target: {selector}")
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def _use(page, interaction: str) -> None:
    if interaction == "full":
        page.keyboard.press("Space")
    else:
        selector = '[data-sc-act="use"]'
        box = page.locator(selector).bounding_box()
        if not box:
            raise AssertionError("visible use control has no pointer target")
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def _move_to(page, target: int, interaction: str, size: int = 20) -> None:
    for _ in range(size * 8):
        player, colleague = _positions(page)
        if player == target:
            return
        cw_path = [(player + step) % size for step in range(1, (target - player) % size + 1)]
        ccw_path = [(player - step) % size for step in range(1, (player - target) % size + 1)]
        if colleague not in cw_path and (colleague in ccw_path or len(cw_path) <= len(ccw_path)):
            preferred = 1
        else:
            preferred = -1
        _step(page, preferred, interaction)
        page.wait_for_timeout(16)
    raise AssertionError(f"could not reach loop tile {target}")


def _wait_phase(page, phase: str, direction: int, interaction: str, *, ready: bool = False, timeout: int = 30000) -> None:
    deadline = time.monotonic() + timeout / 1000
    while time.monotonic() < deadline:
        root = page.locator(".silent-colleague")
        if ready and root.get_attribute("data-ready") == "true":
            return
        if not ready and root.get_attribute("data-phase") == phase:
            return
        player, colleague = _positions(page)
        if (colleague + direction) % 20 == player:
            _step(page, direction, interaction)
        page.wait_for_timeout(35)
    raise AssertionError(f"timed out waiting for {'ready state' if ready else phase}")


def _wait_delivered(page, count: int, direction: int, interaction: str, timeout: int = 45000) -> None:
    deadline = time.monotonic() + timeout / 1000
    while time.monotonic() < deadline:
        if page.locator(".sc-ticket.is-done").count() >= count:
            return
        player, colleague = _positions(page)
        if (colleague + direction) % 20 == player:
            _step(page, direction, interaction)
        page.wait_for_timeout(35)
    raise AssertionError(f"timed out waiting for delivery {count}")


def _solve_ticket(
    page, public: dict, truth: dict, ticket_id: str, interaction: str, index: int,
    out_dir: Path, *, critical_delay_ms: int = 0,
) -> dict | None:
    workshop = public["workshop"]
    ticket = next(item for item in truth["workshop"]["tickets"] if item["id"] == ticket_id)
    fruit = next(item for item in workshop["fruits"] if item["id"] == ticket["fruit_id"])
    _move_to(page, int(fruit["station"]), interaction)
    _use(page, interaction)
    _move_to(page, int(workshop["stations"]["handoff"]), interaction)
    _use(page, interaction)
    _move_to(page, (int(workshop["stations"]["handoff"]) + 2 * int(ticket["direction"])) % int(workshop["loop_size"]), interaction)
    _wait_phase(page, "press_wait", int(ticket["direction"]), interaction, timeout=45000)
    _move_to(page, int(workshop["stations"]["player_press"]), interaction)
    critical = None
    if index == 0 and critical_delay_ms > 0:
        before = float(page.evaluate("WeirdCaptchaTime.status().task_time_ms"))
        page.screenshot(path=str(out_dir / "press-before-delay.png"))
        page.wait_for_timeout(critical_delay_ms)
        after = float(page.evaluate("WeirdCaptchaTime.status().task_time_ms"))
        page.screenshot(path=str(out_dir / f"press-after-{critical_delay_ms}ms-delay.png"))
        critical = {
            "wall_delay_ms": critical_delay_ms,
            "task_time_before_ms": before,
            "task_time_after_ms": after,
            "task_time_delta_ms": round(after - before, 3),
        }
    _use(page, interaction)
    if index == 0:
        page.screenshot(path=str(out_dir / "paired-press-result.png"))
    _move_to(page, (int(workshop["stations"]["player_press"]) + 3 * int(ticket["direction"])) % int(workshop["loop_size"]), interaction)
    _wait_delivered(page, index + 1, int(ticket["direction"]), interaction)
    return critical


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = _read(state_dir / "public_state.json")["challenge_id"]
    page.locator("#sc-certify").click()
    page.locator('.silent-colleague[data-fresh-failure="true"]').wait_for(state="visible")
    after = _read(state_dir / "public_state.json")["challenge_id"]
    if before == after:
        raise AssertionError("failed certification did not issue a fresh challenge")
    page.screenshot(path=str(out_dir / "failure-fresh-shift.png"))


def solve(
    page, state_dir: Path, out_dir: Path, mechanic: str, *, certify: bool = True,
    critical_delay_ms: int = 0,
) -> dict:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    public = _read(state_dir / "public_state.json")
    truth = _read(state_dir / "ground_truth.json")
    interaction = _interaction(state_dir)
    sequence = truth["workshop"]["runtime_ticket_sequence"]
    critical_delay = None
    for index, ticket_id in enumerate(sequence):
        result = _solve_ticket(
            page, public, truth, ticket_id, interaction, index, out_dir,
            critical_delay_ms=critical_delay_ms,
        )
        if result is not None:
            critical_delay = result
    last_ticket = next(item for item in truth["workshop"]["tickets"] if item["id"] == sequence[-1])
    _wait_phase(page, "signal", int(last_ticket["direction"]), interaction, ready=True, timeout=45000)
    page.screenshot(path=str(out_dir / "filled-before-certify.png"))
    if certify:
        page.locator("#sc-certify").click()
        page.locator(".sc-verdict.is-pass").wait_for(state="visible", timeout=15000)
    return {"critical_delay": critical_delay}
