from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "pocket_animation_studio"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{MECHANIC_ID}-{label}.png"), full_page=True)


def _wait_result(state_dir: Path, passed: bool) -> dict:
    deadline = time.time() + 12
    while time.time() < deadline:
        result_path = state_dir / "result.json"
        if result_path.exists():
            result = _read(result_path)
            if bool((result.get("server_grade") or {}).get("passed")) is passed:
                return result
        time.sleep(.05)
    raise AssertionError("Pocket Animation Studio result was not written")


def _wait_failed_attempt(state_dir: Path) -> dict:
    deadline = time.time() + 12
    while time.time() < deadline:
        path = state_dir / "attempts.jsonl"
        if path.exists():
            lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            if lines:
                attempt = json.loads(lines[-1])
                if bool((attempt.get("server_grade") or {}).get("passed")) is False:
                    return attempt
        time.sleep(.05)
    raise AssertionError("Pocket Animation Studio failed attempt was not archived")


def _fill_values(page, shape_id: str, field: str, expression: dict) -> None:
    for part in ("a", "b", "frequency"):
        value = expression.get(part, 1 if part == "frequency" else 0)
        locator = page.locator(
            f'[data-shape-id="{shape_id}"][data-field="{field}"][data-part="{part}"]'
        )
        locator.fill(str(value))
        locator.press("Tab")


def _build_full(page, truth: dict, out_dir: Path) -> None:
    for shape in truth["target_program"]:
        page.locator(f'[data-shape-kind="{shape["kind"]}"]').first.drag_to(page.locator("#pas-program-stack"))
        page.wait_for_timeout(25)
    _shot(page, out_dir, "active-shape-blocks")
    for shape in truth["target_program"]:
        for field, expression in shape["expressions"].items():
            page.locator(f'[data-expression-kind="{expression["kind"]}"]').first.drag_to(
                page.locator(f'[data-shape-id="{shape["id"]}"][data-field="{field}"]')
            )
            page.wait_for_timeout(15)
            _fill_values(page, shape["id"], field, expression)


def _build_simplified(page, truth: dict, out_dir: Path) -> None:
    for shape in truth["target_program"]:
        page.locator(f'.pas-proxy-panel button[data-shape-kind="{shape["kind"]}"]').click()
        page.wait_for_timeout(25)
    _shot(page, out_dir, "active-proxy-shapes")
    for shape in truth["target_program"]:
        for field, expression in shape["expressions"].items():
            page.locator(
                f'[data-shape-id="{shape["id"]}"][data-field="{field}"] '
                f'button[data-proxy-kind="{expression["kind"]}"]'
            ).click()
            page.wait_for_timeout(12)
            _fill_values(page, shape["id"], field, expression)


def _build(page, truth: dict, out_dir: Path) -> None:
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    if interaction == "simplified":
        _build_simplified(page, truth, out_dir)
    else:
        _build_full(page, truth, out_dir)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(mechanic)
    truth = _read(state_dir / "ground_truth.json")
    _build(page, truth, out_dir)
    first_shape = truth["target_program"][0]
    first_field = next(iter(first_shape["expressions"]))
    wrong = "0" if float(first_shape["expressions"][first_field].get("a", 50)) > 1 else "100"
    page.locator(f'[data-shape-id="{first_shape["id"]}"][data-field="{first_field}"][data-part="a"]').fill(wrong)
    page.locator(f'[data-shape-id="{first_shape["id"]}"][data-field="{first_field}"][data-part="a"]').press("Tab")
    page.locator("#pas-run").click()
    duration = int(truth.get("duration_ms") or 4200)
    page.wait_for_timeout(duration + 200)
    expect(page.locator(".pas-readout")).to_contain_text("PREVIEW COMPLETE", timeout=15_000)
    page.locator("#pas-certify").click()
    _wait_failed_attempt(state_dir)
    expect(page.locator(".pas-readout")).to_contain_text("FAIL", timeout=12_000)
    _shot(page, out_dir, "fail-fresh-reference")
    after = _read(state_dir / "ground_truth.json")
    if str(after.get("challenge_id")) == str(truth.get("challenge_id")):
        raise AssertionError("failed submission did not regenerate a fresh reference")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(mechanic)
    truth = _read(state_dir / "ground_truth.json")
    _build(page, truth, out_dir)
    page.locator("#pas-run").click()
    duration = int(truth.get("duration_ms") or 4200)
    page.wait_for_timeout(duration + 260)
    expect(page.locator(".pas-readout")).to_contain_text("PREVIEW COMPLETE", timeout=15_000)
    _shot(page, out_dir, "solved-before-certify")
    page.locator("#pas-certify").click()
    expect(page.locator(".pas-readout")).to_contain_text("PASS", timeout=15_000)
    result = _wait_result(state_dir, True)
    grade = result.get("server_grade") or {}
    if grade.get("passed") is not True:
        raise AssertionError(f"Pocket Animation Studio solver result was not accepted: {grade}")
    _shot(page, out_dir, "pass")

