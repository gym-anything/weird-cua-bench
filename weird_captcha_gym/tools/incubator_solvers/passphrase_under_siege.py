from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import expect

from weird_captcha_gym.tools.incubator_solvers.reviewed_overhaul_common import (
    center,
    drag,
    read_json,
    shot,
    wait_fresh,
)


MECHANIC_ID = "passphrase_under_siege"
VOWELS = frozenset("AEIOUaeiou")


def _digit_sum(value: str) -> int:
    return sum(int(char) for char in value if char.isdigit())


def _digits_for_sum(remainder: int) -> str:
    digits = ""
    while remainder >= 9:
        digits += "9"
        remainder -= 9
    if remainder:
        digits += str(remainder)
    return digits


def canonical_password(state_or_contract: dict, clues: dict | None = None) -> str:
    if clues is None:
        contract = state_or_contract["contract"]
        clues = state_or_contract["clues"]
    else:
        contract = state_or_contract
    text = f"{clues['stamp']}!{clues.get('color') or ''}{clues.get('gauge_token') or ''}"
    remainder = int(contract["digit_sum_target"]) - _digit_sum(text)
    if remainder < 0:
        raise AssertionError("visible clues exceed the configured digit sum")
    text += _digits_for_sum(remainder)
    exact_length = int(contract.get("exact_length") or 0)
    target_length = exact_length or max(int(contract["minimum_length"]), len(text))
    if len(text) > target_length:
        raise AssertionError(f"canonical passphrase overflows target length: {len(text)} > {target_length}")
    text += "z" * (target_length - len(text))
    if len(text) < int(contract["minimum_length"]) or _digit_sum(text) != int(contract["digit_sum_target"]):
        raise AssertionError("canonical passphrase does not satisfy textual controls")
    return text


def _probe_password(contract: dict, stamp: str = "", color: str = "") -> str:
    text = f"{stamp or 'A'}!{color}"
    remainder = int(contract["digit_sum_target"]) - _digit_sum(text)
    if remainder < 0:
        raise AssertionError("visible probe clues exceed the configured digit sum")
    text += _digits_for_sum(remainder)
    target = max(int(contract["minimum_length"]), len(text))
    return text + ("z" * (target - len(text)))


def _clear_editor(page) -> None:
    editor = page.locator(".siege-editor")
    editor.click()
    page.keyboard.press("End")
    for _ in range(page.locator(".siege-char").count()):
        page.keyboard.press("Backspace")
    expect(page.locator(".siege-char")).to_have_count(0)


def _read_gauge_geometry(page) -> int:
    gauge = page.locator('.siege-rule[data-rule-id="gauge"] .siege-gauge')
    expect(gauge).to_be_visible(timeout=3_000)
    labels = gauge.locator(".siege-gauge-label").all_inner_texts()
    if labels != [str(value) for value in range(13)]:
        raise AssertionError(f"rendered gauge scale is incomplete: {labels}")
    angle = float(
        gauge.locator(".siege-gauge-needle").evaluate(
            """node => {
              const matrix = new DOMMatrixReadOnly(getComputedStyle(node).transform);
              return Math.atan2(matrix.b, matrix.a) * 180 / Math.PI;
            }"""
        )
    )
    if angle > 0.1:
        angle -= 360
    raw_value = (angle + 180) / 15
    value = round(raw_value)
    if not 0 <= value <= 12 or abs(raw_value - value) > 0.05:
        raise AssertionError(f"needle does not align with an integer gauge tick: {angle}")
    return value


def _read_visible_clues(page, contract: dict) -> dict[str, str]:
    editor = page.locator(".siege-editor")
    editor.click()
    page.keyboard.type(_probe_password(contract), delay=8)

    stamp_widget = page.locator('.siege-rule[data-rule-id="stamp"] .siege-stamp')
    expect(stamp_widget).to_be_visible(timeout=3_000)
    stamp = stamp_widget.inner_text().replace("\n", "").strip()
    if not stamp:
        raise AssertionError("rendered stamp has no visible text")

    color = ""
    gauge_token = ""
    if contract["include_color"]:
        page.keyboard.type(stamp, delay=8)
        color_code = page.locator('.siege-rule[data-rule-id="color"] .siege-chip-code')
        expect(color_code).to_be_visible(timeout=3_000)
        color = color_code.inner_text().strip()
        if re.fullmatch(r"#[0-9A-F]{6}", color) is None:
            raise AssertionError(f"rendered colour register is malformed: {color!r}")

    if contract["include_gauge"]:
        _clear_editor(page)
        page.keyboard.type(_probe_password(contract, stamp, color), delay=8)
        gauge_value = str(_read_gauge_geometry(page))
        gauge_token = f"G{gauge_value}"

    _clear_editor(page)
    return {"stamp": stamp, "color": color, "gauge_token": gauge_token}


def _select_range(page, start: int, end: int, interaction: str) -> None:
    if not 0 <= start < end:
        raise AssertionError(f"invalid requested range {start}:{end}")
    first = page.locator(f'.siege-char[data-index="{start}"]')
    last = page.locator(f'.siege-char[data-index="{end - 1}"]')
    expect(first).to_be_visible()
    expect(last).to_be_visible()
    if interaction == "simplified":
        first.click()
        last.click()
        return
    start_point = center(first)
    end_point = center(last)
    page.mouse.move(*start_point)
    page.mouse.down()
    page.mouse.move(*end_point, steps=max(2, end - start + 1))
    page.mouse.up()


def _format(page, selector: str) -> None:
    button = page.locator(selector)
    expect(button).to_be_visible()
    button.click()


def _apply_formatting(page, contract: dict, clues: dict, password: str, interaction: str) -> None:
    stamp = clues["stamp"]
    stamp_start = password.index(stamp)
    stamp_end = stamp_start + len(stamp)

    if contract["bold_vowels"]:
        for index, char in enumerate(password):
            if char in VOWELS:
                _select_range(page, index, index + 1, interaction)
                _format(page, '.siege-tool[data-style="bold"][data-value="true"]')
    if contract["stamp_bold"]:
        _select_range(page, stamp_start, stamp_end, interaction)
        _format(page, '.siege-tool[data-style="bold"][data-value="true"]')
    if contract["stamp_italic"]:
        _select_range(page, stamp_start, stamp_end, interaction)
        _format(page, '.siege-tool[data-style="italic"][data-value="true"]')
    if contract["stamp_font"]:
        _select_range(page, stamp_start, stamp_end, interaction)
        _format(page, '.siege-tool[data-style="font"][data-value="serif"]')
    gauge = clues.get("gauge_token") or ""
    if int(contract["gauge_size_px"]):
        gauge_start = password.index(gauge) + 1
        gauge_end = gauge_start + len(gauge) - 1
        _select_range(page, gauge_start, gauge_end, interaction)
        _format(page, f'.siege-tool[data-style="size"][data-value="{int(contract["gauge_size_px"])}"]')
    color = clues.get("color") or ""
    if contract["color_font"]:
        color_start = password.index(color)
        _select_range(page, color_start, color_start + len(color), interaction)
        _format(page, '.siege-tool[data-style="font"][data-value="serif"]')


def _feed(page, count: int, interaction: str) -> None:
    for _ in range(count):
        grain = page.locator(".siege-grain:not([hidden])").first
        hatchling = page.locator(".siege-hatchling")
        expect(grain).to_be_visible(timeout=5_000)
        expect(grain).to_be_enabled(timeout=8_000)
        expect(hatchling).to_be_visible(timeout=5_000)
        if interaction == "simplified":
            grain.click()
            hatchling.click()
        else:
            drag(page, grain, hatchling, steps=9)
        page.wait_for_timeout(80)


def _quench_all(page, count: int, interaction: str, out_dir: Path, mechanic: str) -> None:
    for index in range(count):
        if interaction == "simplified":
            proxy = page.locator(".siege-quench-proxy")
            expect(proxy).to_be_visible(timeout=8_000)
            if index == 0:
                shot(page, out_dir, mechanic, "active-ember")
            proxy.click()
        else:
            ember = page.locator(".siege-ember").first
            expect(ember).to_be_visible(timeout=8_000)
            if index == 0:
                shot(page, out_dir, mechanic, "active-ember")
            ember_id = ember.get_attribute("data-ember-id")
            if not ember_id:
                raise AssertionError("visible ember has no identity")
            live_ember = page.locator(f'.siege-ember[data-ember-id="{ember_id}"]')
            # The target keeps moving between actionability checks. A forced
            # locator click still emits ordinary browser pointer events, but it
            # skips Playwright's stability wait (which a moving target can
            # never satisfy) and resolves the visible box at dispatch time.
            for _ in range(12):
                if live_ember.count() == 0:
                    break
                try:
                    live_ember.click(force=True, timeout=400)
                except Exception:
                    if live_ember.count() != 0:
                        page.wait_for_timeout(8)
            expect(live_ember).to_have_count(0, timeout=1_000)
        page.wait_for_timeout(110)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    assert mechanic == MECHANIC_ID
    state = read_json(state_dir / "public_state.json")
    before = state["challenge_id"]
    editor = page.locator(".siege-editor")
    expect(editor).to_be_visible()
    editor.click()
    page.keyboard.type("BAD", delay=18)
    page.locator(".siege-attempt").click()
    verdict = page.locator(".siege-verdict.is-failure")
    expect(verdict).to_be_visible(timeout=12_000)
    expect(verdict.locator("strong")).to_have_text("FAIL")
    expect(page.locator(".readout")).to_contain_text("FAIL")
    shot(page, out_dir, mechanic, "failure")
    wait_fresh(state_dir, before)
    retry = verdict.locator(".siege-retry")
    expect(retry).to_be_enabled(timeout=8_000)
    retry.click()
    expect(page.locator(".siege-verdict")).to_have_count(0)
    expect(page.locator(".siege-editor")).to_be_visible()
    expect(page.locator(".siege-char")).to_have_count(0)
    shot(page, out_dir, mechanic, "recovery")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    assert mechanic == MECHANIC_ID
    state = read_json(state_dir / "public_state.json")
    interaction = str((state.get("control_condition") or {}).get("interaction") or "full")
    contract = state["contract"]
    clues = _read_visible_clues(page, contract)
    shot(page, out_dir, mechanic, "visible-clues-decoded")
    password = canonical_password(contract, clues)

    editor = page.locator(".siege-editor")
    editor.click()
    page.keyboard.type(password, delay=16)
    expect(page.locator(".siege-char")).to_have_count(len(password))
    shot(page, out_dir, mechanic, "authored-before-formatting")

    _apply_formatting(page, contract, clues, password, interaction)
    shot(page, out_dir, mechanic, "formatted-rule-stack")

    feed_required = int(contract["feed_required"])
    ember_count = int(contract["ember_count"])
    if feed_required or ember_count:
        expect(page.locator(".siege-editor-shell")).to_have_class(re.compile(r".*is-under-siege.*"), timeout=5_000)
    if feed_required:
        _feed(page, 1, interaction)
    if ember_count:
        _quench_all(page, ember_count, interaction, out_dir, mechanic)
    if feed_required > 1:
        _feed(page, feed_required - 1, interaction)
    if feed_required:
        shot(page, out_dir, mechanic, "hatchling-fed")

    seal = page.locator(".siege-seal")
    expect(seal).to_be_enabled(timeout=5_000)
    shot(page, out_dir, mechanic, "all-rules-green")
    seal.click()
    panel = page.locator(".siege-confirm-panel")
    expect(panel).to_be_visible()
    shot(page, out_dir, mechanic, "sealed-memory-retype")
    confirmation = page.locator(".siege-confirm-input")
    confirmation.click()
    page.keyboard.type(password, delay=14)
    page.locator(".siege-confirm").click()
    verdict = page.locator(".siege-verdict.is-pass")
    expect(verdict).to_be_visible(timeout=12_000)
    expect(verdict.locator("strong")).to_have_text("PASS")
    expect(page.locator(".readout")).to_have_attribute("data-status", "passed")
