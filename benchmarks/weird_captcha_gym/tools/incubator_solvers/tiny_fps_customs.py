from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import expect


TURN_STEP_MDEG = 15_000
MOVES_PER_CELL = 4


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot_path(out_dir: Path, mechanic: str, name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{mechanic}-{name}.png"


def _screenshot(page, out_dir: Path, mechanic: str, name: str) -> None:
    page.screenshot(path=str(_shot_path(out_dir, mechanic, name)), full_page=True)


def _wait_for_new_challenge(state_dir: Path, previous: str) -> str:
    deadline = time.time() + 10
    while time.time() < deadline:
        current = str(_read(state_dir / "ground_truth.json").get("challenge_id") or "")
        if current and current != previous:
            return current
        time.sleep(0.05)
    raise AssertionError("tiny_fps_customs did not regenerate after protected contact")


def _desired_angle(origin: dict[str, int], destination: dict[str, int]) -> int:
    dx = int(destination["x"]) - int(origin["x"])
    dy = int(destination["y"]) - int(origin["y"])
    angles = {(1, 0): 0, (0, 1): 90_000, (-1, 0): 180_000, (0, -1): 270_000}
    if (dx, dy) not in angles:
        raise AssertionError(f"non-cardinal solver route step {(dx, dy)}")
    return angles[(dx, dy)]


def _interaction_mode(truth: dict[str, Any]) -> str:
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    if interaction not in {"simplified", "full"}:
        raise AssertionError(f"unsupported customs interaction {interaction!r}")
    return interaction


def _press_proxy(page, command: str) -> None:
    button = page.locator(f'.fps-proxy-control[data-command="{command}"]')
    box = button.bounding_box()
    if box is None:
        raise AssertionError(f"customs proxy control {command!r} is not visibly measurable")
    # Use an ordinary visible mouse click. Locator clicks add substantial
    # per-action settling time to the hundreds of discrete maze controls.
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def _tap_key(page, key: str) -> None:
    # Keep the browser's ordinary keydown/keyup path while avoiding the
    # automation framework's per-press settling delay on long maze routes.
    page.keyboard.down(key)
    page.keyboard.up(key)


def _turn_to(page, current_angle: int, target_angle: int, interaction: str) -> int:
    current = current_angle % 360_000
    target = target_angle % 360_000
    signed = ((target - current + 180_000) % 360_000) - 180_000
    if signed % TURN_STEP_MDEG:
        raise AssertionError(f"solver angle {target} is not reachable in {TURN_STEP_MDEG} mdeg keyboard turns")
    key = "ArrowRight" if signed > 0 else "ArrowLeft"
    command = "turn-right" if signed > 0 else "turn-left"
    for _ in range(abs(signed) // TURN_STEP_MDEG):
        if interaction == "full":
            _tap_key(page, key)
        else:
            _press_proxy(page, command)
    return target


def _follow_segment(page, segment: dict[str, Any], current_angle: int, interaction: str) -> int:
    route = segment.get("route_cells") or []
    if not route:
        raise AssertionError("empty hidden customs solver route")
    for origin, destination in zip(route, route[1:]):
        current_angle = _turn_to(page, current_angle, _desired_angle(origin, destination), interaction)
        for _ in range(MOVES_PER_CELL):
            if interaction == "full":
                _tap_key(page, "w")
            else:
                _press_proxy(page, "move-forward")
    return _turn_to(page, current_angle, int(segment["aim_mdeg"]), interaction)


def _assert_ui_identity(page, truth: dict[str, Any]) -> None:
    challenge = page.locator(".tiny-fps-customs").get_attribute("data-challenge-id")
    if challenge != truth.get("challenge_id"):
        raise AssertionError(f"UI challenge {challenge!r} does not match hidden state {truth.get('challenge_id')!r}")


def _assert_all_warrants_fully_visible(page, expected_count: int) -> None:
    cards = page.locator(".fps-warrant")
    expect(cards).to_have_count(expected_count)
    bounds = page.evaluate(
        """() => {
          const dossier = document.querySelector('.fps-dossier')?.getBoundingClientRect();
          const cards = [...document.querySelectorAll('.fps-warrant')].map(node => node.getBoundingClientRect());
          return {dossier, cards};
        }"""
    )
    dossier = bounds.get("dossier")
    card_bounds = bounds.get("cards") or []
    if not dossier or len(card_bounds) != expected_count:
        raise AssertionError("customs warrant dossier did not expose every measurable warrant card")
    for index, card in enumerate(card_bounds, start=1):
        if (
            card["left"] < dossier["left"] - 1
            or card["right"] > dossier["right"] + 1
            or card["top"] < dossier["top"] - 1
            or card["bottom"] > dossier["bottom"] + 1
        ):
            raise AssertionError(f"warrant {index} is clipped outside the visible dossier: {card} vs {dossier}")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    state_dir = Path(state_dir)
    out_dir = Path(out_dir)
    truth = _read(state_dir / "ground_truth.json")
    before = str(truth["challenge_id"])
    interaction = _interaction_mode(truth)
    _assert_ui_identity(page, truth)
    expect(page.locator(".fps-world")).to_be_visible()
    _assert_all_warrants_fully_visible(page, len(truth.get("wanted_ids") or []))
    current_angle = int(truth["initial_pose"]["angle_mdeg"])
    current_angle = _follow_segment(page, truth["protected_test_plan"], current_angle, interaction)
    del current_angle
    _screenshot(page, out_dir, mechanic, "protected-in-crosshair")

    # Fire through the ordinary mouse surface. A protected geometric hit must
    # show a strong local failure before the server replaces the challenge.
    if interaction == "full":
        page.locator(".fps-world").click(position={"x": 360, "y": 210})
    else:
        _press_proxy(page, "fire")
    expect(page.locator('.fps-terminal[data-state="fail"]')).to_be_visible(timeout=2_000)
    expect(page.locator(".fps-terminal")).to_contain_text("FAIL")
    _screenshot(page, out_dir, mechanic, "protected-fail")

    _wait_for_new_challenge(state_dir, before)
    expect(page.locator('.tiny-fps-customs[data-fresh-failure="true"]')).to_be_visible(timeout=10_000)
    expect(page.locator(".readout")).to_contain_text("FAIL")
    _screenshot(page, out_dir, mechanic, "fail-fresh-manifest")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    state_dir = Path(state_dir)
    out_dir = Path(out_dir)
    truth = _read(state_dir / "ground_truth.json")
    interaction = _interaction_mode(truth)
    _assert_ui_identity(page, truth)
    expect(page.locator(".fps-world")).to_be_visible()
    _assert_all_warrants_fully_visible(page, len(truth.get("wanted_ids") or []))
    _screenshot(page, out_dir, mechanic, "initial-dossier")
    current_angle = int(truth["initial_pose"]["angle_mdeg"])
    plan = truth.get("solver_plan") or []
    total = len(truth.get("wanted_ids") or [])
    if len(plan) != total or total < 2:
        raise AssertionError("hidden customs solver must contain every warranted contact")

    for index, segment in enumerate(plan):
        current_angle = _follow_segment(page, segment, current_angle, interaction)
        if index == 1:
            _screenshot(page, out_dir, mechanic, "active-maze-navigation")
        if index == len(plan) - 1:
            _screenshot(page, out_dir, mechanic, "final-warrant-crosshair")
            if interaction == "full":
                page.locator(".fps-world").click(position={"x": 360, "y": 210})
            else:
                _press_proxy(page, "fire")
        else:
            if interaction == "full":
                _tap_key(page, "Space")
            else:
                _press_proxy(page, "fire")
            expect(page.locator(".fps-warrant-count")).to_have_text(f"{index + 1} / {total}")

    expect(page.locator('.fps-terminal[data-state="pass"]')).to_be_visible(timeout=10_000)
    expect(page.locator(".readout")).to_contain_text("PASS")
    expect(page.locator(".fps-warrant-count")).to_have_text(f"{total} / {total}")
    _screenshot(page, out_dir, mechanic, "pass")
