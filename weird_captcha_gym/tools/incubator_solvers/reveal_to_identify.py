from __future__ import annotations

import json
from pathlib import Path


MECHANIC_ID = "reveal_to_identify"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, mechanic: str, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{label}.png"))


def _reveal(page, point: list[float], interaction: str) -> None:
    x, y = float(point[0]), float(point[1])
    if interaction == "simplified":
        page.locator("#reveal-x").fill(str(round(x, 2)))
        page.locator("#reveal-y").fill(str(round(y, 2)))
        page.locator("#reveal-coordinate-button").click()
    else:
        canvas = page.locator("#reveal-plate")
        box = canvas.bounding_box()
        if box is None:
            raise AssertionError("fogged reveal plate is not visible")
        stage = page.evaluate("() => window.revealToIdentifyModel.state.stage")
        page.mouse.click(
            box["x"] + x / float(stage["width"]) * box["width"],
            box["y"] + y / float(stage["height"]) * box["height"],
        )
    page.wait_for_function(
        "() => WeirdCaptchaTime.status().pending_action_count === 0",
        polling=20,
        timeout=5_000,
    )


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read_json(state_dir / "ground_truth.json")
    challenge_before = truth["challenge_id"]
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    _reveal(page, truth["salient_points"][0], interaction)
    page.locator("#reveal-answer").fill("definitely not the object")
    page.locator("#reveal-submit").click()
    page.locator('.reveal-identify[data-fresh-failure="true"]').wait_for(
        state="visible", timeout=8_000
    )
    page.wait_for_function(
        "() => document.querySelector('.readout')?.textContent?.includes('FAIL')",
        timeout=8_000,
    )
    challenge_after = _read_json(state_dir / "ground_truth.json")["challenge_id"]
    if challenge_before == challenge_after:
        raise AssertionError("wrong identification did not generate a fresh plate")
    _screenshot(page, out_dir, mechanic, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> list[dict]:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read_json(state_dir / "ground_truth.json")
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    points = list(truth.get("salient_points") or [])
    budget = int(truth["reveal"]["budget"])
    if not points or len(points) > budget:
        raise AssertionError(f"invalid canonical reveal points: {points!r}")

    _screenshot(page, out_dir, mechanic, "initial")
    action_cycles: list[dict] = []
    for index, point in enumerate(points, start=1):
        before = page.evaluate("() => WeirdCaptchaTime.status()")
        _reveal(page, point, interaction)
        after = page.evaluate("() => WeirdCaptchaTime.status()")
        visible_count = page.get_attribute(".reveal-identify", "data-reveal-count")
        if int(visible_count or -1) != index:
            raise AssertionError(f"reveal {index} did not archive exactly once")
        action_cycles.append({"before": before, "after": after, "point": point})
        if index == 1:
            _screenshot(page, out_dir, mechanic, "active")

    page.locator("#reveal-answer").fill(str(truth["answer"]))
    _screenshot(page, out_dir, mechanic, "solved")
    page.locator("#reveal-submit").click()
    page.locator('.reveal-identify[data-verdict="pass"]').wait_for(
        state="visible", timeout=8_000
    )
    page.wait_for_function(
        "() => document.querySelector('.readout')?.textContent?.trim() === 'PASS'",
        timeout=8_000,
    )
    _screenshot(page, out_dir, mechanic, "pass")
    return action_cycles
