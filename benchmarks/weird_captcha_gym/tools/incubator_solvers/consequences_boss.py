from __future__ import annotations

import math
from pathlib import Path

from playwright.sync_api import expect

from benchmarks.weird_captcha_gym.tools.incubator_solvers.reviewed_overhaul_common import (
    center, drag, read_json, shot, wait_fresh,
)

MECHANIC_ID = "consequences_boss"


def _paused_mode(page) -> bool:
    return bool(
        page.evaluate(
            """() => Boolean(
              window.WeirdCaptchaTime
              && WeirdCaptchaTime.status().mode === "paused"
            )"""
        )
    )


def _resume_if_paused(page) -> bool:
    paused = _paused_mode(page)
    if paused:
        page.evaluate("WeirdCaptchaTime.resume()")
    return paused


def _restore_pause(page, paused: bool) -> None:
    if paused:
        page.evaluate("WeirdCaptchaTime.pause()")


def _seal(page, value: int, positions: int, interaction: str) -> None:
    if positions == 1:
        return
    if interaction == "simplified":
        page.locator(f'.covenant-seal-button[data-seal-value="{value}"]').click()
        return
    seal = page.locator(".covenant-seal")
    cx, cy = center(seal)
    angle = -0.5 * math.pi + value * (2 * math.pi / positions)
    point = (cx + 32 * math.cos(angle), cy + 32 * math.sin(angle))
    page.mouse.move(*point)
    page.mouse.down()
    page.mouse.move(*point, steps=2)
    page.mouse.up()


def _answer(page, socket: str, seal: int, positions: int, interaction: str) -> None:
    paused = _resume_if_paused(page)
    try:
        if interaction == "simplified":
            page.locator(
                f'.covenant-place-button[data-socket="{socket}"]'
            ).click()
        else:
            drag(
                page,
                page.locator(".covenant-relic"),
                page.locator(
                    f'.covenant-socket[data-socket="{socket}"]'
                ),
                steps=9,
            )
        _seal(page, seal, positions, interaction)
        page.locator(".covenant-bind").click()
    finally:
        _restore_pause(page, paused)


def _contract(state: dict) -> tuple[list[str], int, int, str]:
    condition = state.get("control_condition") or {}
    parameters = condition.get("difficulty_parameters") or {}
    sockets = [str(item) for item in parameters.get("socket_options", ["left", "right"])]
    positions = int(parameters.get("seal_positions", 4))
    distinct = int(parameters.get("minimum_distinct_states", 1))
    interaction = str(condition.get("interaction") or "full")
    return sockets, positions, distinct, interaction


def _commitments(state: dict) -> dict[str, tuple[str, int]]:
    sockets, positions, distinct, _ = _contract(state)
    states = [(socket, seal) for socket in sockets for seal in range(positions)]
    choices = {}
    for index, scene in enumerate(state["scenes"]):
        choices[scene["id"]] = states[index] if index < distinct else states[0]
    return choices


def _make(page, state: dict) -> dict[str, tuple[str, int]]:
    choices = _commitments(state)
    _, positions, _, interaction = _contract(state)
    for scene in state["scenes"]:
        _answer(page, *choices[scene["id"]], positions, interaction)
    paused = _resume_if_paused(page)
    try:
        expect(page.locator(".covenant-phase")).to_contain_text(
            "RECKONING",
            timeout=6_000,
        )
    finally:
        _restore_pause(page, paused)
    return choices


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    assert mechanic == MECHANIC_ID
    state = read_json(state_dir / "public_state.json")
    before = state["challenge_id"]
    choices = _make(page, state)
    sockets, positions, _, interaction = _contract(state)
    for index, scene_id in enumerate(state["boss_order"]):
        socket, seal = choices[scene_id]
        wrong_socket = sockets[(sockets.index(socket) + 1) % len(sockets)] if len(sockets) > 1 else socket
        wrong_seal = (seal + 1) % positions if len(sockets) == 1 and positions > 1 else seal
        _answer(
            page,
            wrong_socket if index == 0 else socket,
            wrong_seal if index == 0 else seal,
            positions,
            interaction,
        )
    verdict = page.locator(".covenant-verdict")
    expect(verdict).to_be_visible(timeout=12_000)
    expect(verdict.locator("strong")).to_have_text("FAIL")
    expect(page.locator(".readout")).to_contain_text("FAIL")
    shot(page, out_dir, mechanic, "failure")
    wait_fresh(state_dir, before)
    page.wait_for_timeout(1_200)
    expect(verdict).to_be_visible()
    expect(verdict.locator(".covenant-retry")).to_be_enabled()
    paused = _resume_if_paused(page)
    try:
        verdict.locator(".covenant-retry").click()
        expect(page.locator("body[data-mechanic]")).to_be_visible(
            timeout=8_000
        )
        expect(page.locator(".covenant-verdict")).to_have_count(0)
        expect(page.locator(".covenant-phase")).to_contain_text("THE MAKING")
    finally:
        _restore_pause(page, paused)
    shot(page, out_dir, mechanic, "recovery")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    assert mechanic == MECHANIC_ID
    state = read_json(state_dir / "public_state.json")
    choices = _make(page, state)
    _, positions, _, interaction = _contract(state)
    shot(page, out_dir, mechanic, "judgment-after-occlusion")
    for scene_id in state["boss_order"]:
        _answer(page, *choices[scene_id], positions, interaction)
