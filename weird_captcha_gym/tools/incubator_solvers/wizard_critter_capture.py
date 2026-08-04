from __future__ import annotations

import json
from pathlib import Path


MECHANIC_ID = "wizard_critter_capture"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, mechanic: str, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{label}.png"), full_page=True)


def _arena_click(page, point: list[int]) -> None:
    canvas = page.locator("#wizard-arena")
    box = canvas.bounding_box()
    if box is None:
        raise AssertionError("wizard arena has no visible bounds")
    state = page.evaluate("() => wizardCritterCaptureModel.state.arena")
    x = box["x"] + (float(point[0]) / float(state["width"])) * box["width"]
    y = box["y"] + (float(point[1]) / float(state["height"])) * box["height"]
    page.mouse.click(x, y)


def _interaction(truth: dict) -> str:
    return str((truth.get("control_condition") or {}).get("interaction") or "full")


def _proxy_point(page, point: list[int]) -> None:
    page.locator("#wizard-proxy-x").fill(str(point[0]))
    page.locator("#wizard-proxy-y").fill(str(point[1]))


def _place_lure(page, truth: dict) -> None:
    if _interaction(truth) == "full":
        page.locator("#wizard-lure-arm").click()
        _arena_click(page, list(truth["solver_lure"]))
    else:
        _proxy_point(page, list(truth["solver_lure"]))
        page.locator("#wizard-proxy-place").click()
    page.wait_for_function("() => wizardCritterCaptureModel.phase === 'hunt' && Boolean(wizardCritterCaptureModel.lure)")


def _launch_net(page, truth: dict, point: list[int]) -> None:
    if _interaction(truth) == "full":
        _arena_click(page, point)
    else:
        _proxy_point(page, point)
        page.locator("#wizard-proxy-launch").click()


def _wait_ready(page) -> None:
    page.wait_for_function("() => wizardCritterCaptureModel.phase === 'ready'", timeout=6_000)


def _place_lure_and_freeze(page, truth: dict) -> None:
    _place_lure(page, truth)
    required = int(truth["solver_freeze_ticks"])
    if _interaction(truth) == "full":
        page.keyboard.down("f")
        page.wait_for_function(
            "required => wizardCritterCaptureModel.freezeTicksUsed >= required",
            arg=required,
            timeout=5_000,
        )
        page.keyboard.up("f")
    else:
        page.locator("#wizard-proxy-freeze").click()
    page.wait_for_function("() => !wizardCritterCaptureModel.freezeActive && wizardCritterCaptureModel.freezeReleases >= 1")


def _future_plan(page, plans: list[dict], margin: int = 3) -> dict:
    current = int(page.evaluate("() => wizardCritterCaptureModel.tick"))
    for plan in plans:
        if int(plan["shot_tick"]) >= current + margin:
            return plan
    raise AssertionError(f"no future interception window remains after tick {current}: {plans}")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    state_dir = Path(state_dir)
    truth = _read(state_dir / "ground_truth.json")
    before = str(truth["challenge_id"])
    _screenshot(page, out_dir, mechanic, "target-observation")
    _wait_ready(page)
    _place_lure(page, truth)
    miss_points = ([18, 420], [822, 420], [30, 414], [810, 414], [420, 425], [420, 12])[:int(truth["requirements"]["net_count"])]
    for index, point in enumerate(miss_points, start=1):
        _launch_net(page, truth, list(point))
        if index == 2:
            page.wait_for_function("() => wizardCritterCaptureModel.projectile?.age >= 4", timeout=3_000)
            _screenshot(page, out_dir, mechanic, "deliberate-net-miss")
        if index < len(miss_points):
            page.wait_for_function(
                "expected => wizardCritterCaptureModel.nets === expected && wizardCritterCaptureModel.projectile === null && wizardCritterCaptureModel.cooldown === 0",
                arg=int(truth["requirements"]["net_count"]) - index,
                timeout=5_000,
            )
    page.wait_for_function("() => document.querySelector('.readout')?.textContent.includes('FAIL')", timeout=10_000)
    after = _read(state_dir / "ground_truth.json")["challenge_id"]
    if after == before:
        raise AssertionError("spent-net failure did not produce a fresh observatory")
    _screenshot(page, out_dir, mechanic, "fail-fresh-observatory")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    state_dir = Path(state_dir)
    truth = _read(state_dir / "ground_truth.json")
    challenge = page.locator(".wizard-observatory").get_attribute("data-challenge-id")
    if challenge != truth.get("challenge_id"):
        raise AssertionError(f"UI challenge {challenge!r} differs from hidden challenge {truth.get('challenge_id')!r}")
    page.wait_for_function("() => !document.querySelector('.wizard-verdict-fresh')", timeout=3_000)
    _screenshot(page, out_dir, mechanic, "fresh-target-sigil")
    _wait_ready(page)
    _place_lure_and_freeze(page, truth)
    _screenshot(page, out_dir, mechanic, "lure-and-freeze-proof")
    plan = _future_plan(page, list(truth["solver_plans"]), margin=3)
    page.wait_for_function(
        "shotTick => wizardCritterCaptureModel.tick === shotTick",
        arg=int(plan["shot_tick"]),
        timeout=8_000,
    )
    _launch_net(page, truth, list(plan["aim"]))
    page.wait_for_function("() => wizardCritterCaptureModel.projectile?.age >= 3", timeout=3_000)
    _screenshot(page, out_dir, mechanic, "predictive-net-in-flight")
    page.wait_for_function("() => document.querySelector('.readout')?.textContent === 'PASS · PREDICTIVE INTERCEPTION CONFIRMED'", timeout=10_000)


def exercise_decoy_and_reset(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(Path(state_dir) / "ground_truth.json")
    _wait_ready(page)
    _place_lure_and_freeze(page, truth)
    plan = _future_plan(page, list(truth["decoy_plans"]), margin=3)
    page.wait_for_function("tick => wizardCritterCaptureModel.tick === tick", arg=int(plan["shot_tick"]), timeout=8_000)
    _launch_net(page, truth, list(plan["aim"]))
    page.wait_for_function("() => wizardCritterCaptureModel.decoyHits === 1 && wizardCritterCaptureModel.projectile === null", timeout=6_000)
    _screenshot(page, out_dir, mechanic, "deliberate-decoy-strike")
    page.locator("#wizard-reset").click()
    page.wait_for_function(
        "() => wizardCritterCaptureModel.phase === 'preview' && wizardCritterCaptureModel.tick === 0 && wizardCritterCaptureModel.nets === wizardCritterCaptureModel.state.requirements.net_count && wizardCritterCaptureModel.resetCount === 1",
        timeout=3_000,
    )
    _screenshot(page, out_dir, mechanic, "reset-restored")
