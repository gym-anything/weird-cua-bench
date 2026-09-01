from __future__ import annotations

import json
from pathlib import Path


MECHANIC_ID = "fence_the_fox"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, mechanic: str, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{label}.png"))


def _cell(page, coordinate: list[int]):
    q, r = (int(coordinate[0]), int(coordinate[1]))
    return page.locator(f'.fox-cell[data-q="{q}"][data-r="{r}"]')


def _time_command(page, command: str) -> dict:
    response = page.evaluate(
        """async command => {
          const response = await fetch('/time-control', {
            method: 'POST',
            headers: {'content-type': 'application/json'},
            body: JSON.stringify({command}),
            cache: 'no-store',
          });
          if (!response.ok) throw new Error(`time command ${command} failed: ${response.status}`);
          return await response.json();
        }""",
        command,
    )
    sequence = int(response["sequence"])
    expected_state = "running" if command == "resume" else "paused"
    page.wait_for_function(
        """expected => {
          const status = WeirdCaptchaTime.status();
          return Number(status.sequence) === expected.sequence && status.state === expected.state;
        }""",
        arg={"sequence": sequence, "state": expected_state},
        timeout=8_000,
    )
    return response


def _settle_turn(page) -> dict:
    status = page.evaluate("() => window.WeirdCaptchaTime?.status?.() || {running: true}")
    was_paused = status.get("state") == "paused" or status.get("running") is False
    protocol_enabled = page.evaluate(
        "() => new URL(location.href).searchParams.get('time_control') === '1'"
    )
    if was_paused:
        if protocol_enabled:
            _time_command(page, "resume")
            _time_command(page, "settle_pause")
        else:
            # Standalone solver runs may omit the evaluator control route.
            # Supply the same action-settle boundary through the shared clock.
            page.evaluate(
                """async () => {
                  WeirdCaptchaTime.resume();
                  await WeirdCaptchaTime.pauseAfterActions();
                }"""
            )
    try:
        page.wait_for_function(
            """() => {
              const status = WeirdCaptchaTime.status();
              return (!window.fenceTheFoxModel?.busy || document.querySelector('.fox-verdict.is-fail'))
                && status.pending_action_count === 0;
            }""",
            polling=25,
            timeout=8_000,
        )
    except Exception as exc:
        diagnostic = page.evaluate(
            "() => ({clock: WeirdCaptchaTime.status(), busy: fenceTheFoxModel.busy, "
            "turns: fenceTheFoxModel.turns, terminal: fenceTheFoxModel.terminal, "
            "events: fenceTheFoxModel.events.length})"
        )
        raise AssertionError(f"fox turn did not settle: {diagnostic}") from exc
    finally:
        if was_paused and not protocol_enabled:
            page.evaluate("() => window.WeirdCaptchaTime.pause()")
    settled = page.evaluate("() => WeirdCaptchaTime.status()")
    if settled["pending_action_count"] != 0:
        raise AssertionError(f"fox action handle did not settle: {settled}")
    if was_paused and settled["state"] != "paused":
        raise AssertionError(f"paused action cycle did not restore the inference hold: {settled}")
    return {
        "before_settle": status,
        "after_settle": settled,
        "protocol": "loopback_resume_then_settle_pause" if was_paused and protocol_enabled else (
            "direct_shared_clock_settle_pause" if was_paused else "live_action_settle"
        ),
    }


def _place(page, coordinate: list[int], interaction: str) -> dict:
    target = _cell(page, coordinate)
    if interaction == "simplified":
        target.click()
    else:
        source = page.locator("#fox-stake-token")
        source_box = source.bounding_box()
        target_box = target.bounding_box()
        if source_box is None or target_box is None:
            raise AssertionError("stake drag endpoints are not visible")
        page.mouse.move(source_box["x"] + source_box["width"] / 2, source_box["y"] + source_box["height"] / 2)
        page.mouse.down()
        page.mouse.move(
            target_box["x"] + target_box["width"] / 2,
            target_box["y"] + target_box["height"] / 2,
            steps=8,
        )
        clock = page.evaluate("() => WeirdCaptchaTime.status()")
        if clock.get("state") == "paused" or clock.get("running") is False:
            page.evaluate("() => WeirdCaptchaTime.resume()")
            page.wait_for_timeout(130)
            page.evaluate("() => WeirdCaptchaTime.pause()")
        else:
            page.wait_for_timeout(130)
        checkpoints = page.locator(".fox-driver-checkpoint")
        checkpoints.first.wait_for(state="visible", timeout=3_000)
        for checkpoint_index in range(checkpoints.count()):
            checkpoint_box = checkpoints.nth(checkpoint_index).bounding_box()
            if checkpoint_box is None:
                raise AssertionError("stake-driver checkpoint is not visible")
            page.mouse.move(
                checkpoint_box["x"] + checkpoint_box["width"] / 2,
                checkpoint_box["y"] + checkpoint_box["height"] / 2,
                steps=4,
            )
        page.mouse.move(
            target_box["x"] + target_box["width"] / 2,
            target_box["y"] + target_box["height"] / 2,
            steps=4,
        )
        page.mouse.up()
    return _settle_turn(page)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = _read_json(state_dir / "ground_truth.json")["challenge_id"]
    page.locator("#fox-certify").click()
    page.locator(".fox-verdict.is-fail").wait_for(state="visible", timeout=8_000)
    after = _read_json(state_dir / "ground_truth.json")["challenge_id"]
    if before == after:
        raise AssertionError("failed enclosure check did not generate a fresh field")
    _screenshot(page, out_dir, mechanic, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> list[dict]:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read_json(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "simplified")
    plan = truth.get("canonical_plan") or []
    if not plan or len(plan) > int(truth["stake_budget"]):
        raise AssertionError(f"invalid canonical fence plan: {plan!r}")
    action_cycles = []
    for index, coordinate in enumerate(plan, start=1):
        action_cycles.append(_place(page, coordinate, interaction))
        event_count = page.evaluate("() => window.fenceTheFoxModel.events.length")
        if event_count != index:
            raise AssertionError(f"fox turn {index} did not archive exactly once: {event_count}")
        if index == 1:
            _screenshot(page, out_dir, mechanic, "active")
    contract = page.evaluate(
        """() => ({
          ready: window.fenceTheFoxModel.ready,
          terminal: window.fenceTheFoxModel.terminal,
          turns: window.fenceTheFoxModel.turns,
          events: window.fenceTheFoxModel.events.length,
        })"""
    )
    if not contract["ready"] or contract["terminal"] != "trapped" or contract["turns"] != len(plan) or contract["events"] != len(plan):
        raise AssertionError(f"canonical plan did not visibly contain the fox: {contract}")
    _screenshot(page, out_dir, mechanic, "solved")
    page.locator("#fox-certify").click()
    page.locator(".fox-verdict.is-pass").wait_for(state="visible", timeout=8_000)
    return action_cycles
