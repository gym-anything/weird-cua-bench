"""Procedural generator for Reflected Rival.

The selected source mechanic is a two-racer course in which every steering
input is mirrored onto the opponent.  This implementation keeps that causal
coupling, but uses an original, deterministic, visible terrain board rather
than copying the source demo's code or presentation.
"""

from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "reflected_rival"


PROFILES: dict[int, dict[str, Any]] = {
    1: {
        "lane_count": 3,
        "segment_count": 5,
        "decoy_fraction": 0.12,
        "boost_multiplier": 1.18,
        "slow_multiplier": 0.84,
        "neutral_multiplier": 0.96,
        "base_rate": 0.050,
        "tick_ms": 100,
        "max_ticks": 900,
    },
    2: {
        "lane_count": 4,
        "segment_count": 7,
        "decoy_fraction": 0.26,
        "boost_multiplier": 1.21,
        "slow_multiplier": 0.80,
        "neutral_multiplier": 0.95,
        "base_rate": 0.055,
        "tick_ms": 95,
        "max_ticks": 850,
    },
    3: {
        "lane_count": 5,
        "segment_count": 9,
        "decoy_fraction": 0.40,
        "boost_multiplier": 1.24,
        "slow_multiplier": 0.76,
        "neutral_multiplier": 0.94,
        "base_rate": 0.060,
        "tick_ms": 90,
        "max_ticks": 750,
    },
    4: {
        "lane_count": 6,
        "segment_count": 12,
        "decoy_fraction": 0.56,
        "boost_multiplier": 1.27,
        "slow_multiplier": 0.72,
        "neutral_multiplier": 0.93,
        "base_rate": 0.064,
        "tick_ms": 85,
        "max_ticks": 760,
    },
    5: {
        "lane_count": 7,
        "segment_count": 15,
        "decoy_fraction": 0.72,
        "boost_multiplier": 1.30,
        "slow_multiplier": 0.68,
        "neutral_multiplier": 0.92,
        "base_rate": 0.078,
        "tick_ms": 80,
        "max_ticks": 700,
    },
}


def _seed_int(seed: str) -> int:
    return int.from_bytes(
        hashlib.sha256(f"{seed}|{MECHANIC_ID}|v3".encode("utf-8")).digest()[:8],
        "big",
    )


def _profile(task: dict[str, Any]) -> tuple[int, dict[str, Any], dict[str, Any] | None]:
    condition = copy.deepcopy(task.get("_control_condition"))
    level = int((condition or {}).get("difficulty", 4))
    if level not in PROFILES:
        raise ValueError("reflected rival difficulty must be 1 through 5")
    parameters = dict(PROFILES[level])
    parameters.update(dict((condition or {}).get("difficulty_parameters") or {}))
    required_ints = ("lane_count", "segment_count", "tick_ms", "max_ticks")
    for name in required_ints:
        parameters[name] = int(parameters[name])
    for name in ("decoy_fraction", "boost_multiplier", "slow_multiplier", "neutral_multiplier", "base_rate"):
        parameters[name] = float(parameters[name])
    if not 3 <= parameters["lane_count"] <= 9:
        raise ValueError("reflected rival lane count is outside supported limits")
    if not 4 <= parameters["segment_count"] <= 18:
        raise ValueError("reflected rival segment count is outside supported limits")
    if not 0.0 <= parameters["decoy_fraction"] <= 1.0:
        raise ValueError("reflected rival decoy fraction is outside supported limits")
    if not 1.0 < parameters["boost_multiplier"] <= 1.6:
        raise ValueError("reflected rival boost multiplier is outside supported limits")
    if not 0.45 <= parameters["slow_multiplier"] < 1.0:
        raise ValueError("reflected rival slow multiplier is outside supported limits")
    if not 0.75 <= parameters["neutral_multiplier"] <= 1.0:
        raise ValueError("reflected rival neutral multiplier is outside supported limits")
    if not 0.035 <= parameters["base_rate"] <= 0.13:
        raise ValueError("reflected rival base rate is outside supported limits")
    if not 60 <= parameters["tick_ms"] <= 180:
        raise ValueError("reflected rival tick interval is outside supported limits")
    return level, parameters, condition


def _route(rng: random.Random, lane_count: int, segment_count: int) -> tuple[int, int, list[int]]:
    player = max(0, lane_count // 2 - 1)
    rival = min(lane_count - 1, lane_count // 2 + 1)
    commands = [0]
    for _segment in range(1, segment_count):
        candidates = [direction for direction in (-1, 1) if 0 <= player + direction < lane_count and 0 <= rival - direction < lane_count]
        candidates.append(0)
        rng.shuffle(candidates)
        # Prefer a lane change, but leave a few hold decisions so the board
        # cannot be solved by alternating keys mechanically.
        if rng.random() < 0.22 and 0 in candidates:
            direction = 0
        else:
            direction = next((item for item in candidates if item != 0), 0)
        player += direction
        rival -= direction
        commands.append(direction)
    return max(0, lane_count // 2 - 1), min(lane_count - 1, lane_count // 2 + 1), commands


def _cell(kind: str, multiplier: float) -> dict[str, Any]:
    return {"kind": kind, "multiplier": round(float(multiplier), 4)}


def _build_course(
    rng: random.Random,
    parameters: dict[str, Any],
    player_start: int,
    rival_start: int,
    commands: list[int],
    bait_commands: list[int],
) -> list[dict[str, Any]]:
    lanes = int(parameters["lane_count"])
    boost = float(parameters["boost_multiplier"])
    slow = float(parameters["slow_multiplier"])
    neutral = float(parameters["neutral_multiplier"])
    decoy_fraction = float(parameters["decoy_fraction"])
    player = player_start
    rival = rival_start
    bait_player = player_start
    bait_rival = rival_start
    # The bait route is a visible, locally attractive route for WHITE.  Its
    # mirrored BLUE cells are deliberately stronger, so a solver that only
    # maximizes WHITE's next multiplier can lose the race.
    bait_white = min(boost - 0.04, neutral + 0.12)
    bait_blue = min(1.58, boost + 0.12)
    course: list[dict[str, Any]] = []
    for segment, command in enumerate(commands):
        if segment:
            player = max(0, min(lanes - 1, player + command))
            rival = max(0, min(lanes - 1, rival - command))
            bait_command = int(bait_commands[segment])
            bait_player = max(0, min(lanes - 1, bait_player + bait_command))
            bait_rival = max(0, min(lanes - 1, bait_rival - bait_command))
        cells = [_cell("plain", neutral) for _ in range(lanes)]
        cells[player] = _cell("plain", neutral)
        if rival != player:
            cells[rival] = _cell("slow", slow)

        # Put a slightly faster cell under the locally attractive WHITE bait
        # route and a stronger boost under its mirrored BLUE route.  When the
        # routes overlap, the strongest visible value wins; the generator
        # below rejects boards unless the resulting greedy path really loses.
        if cells[bait_player]["multiplier"] < bait_white:
            cells[bait_player] = _cell("boost", bait_white)
        if cells[bait_rival]["multiplier"] < bait_blue:
            cells[bait_rival] = _cell("boost", bait_blue)

        # Decoys make the visible course a planning problem.  Do not overwrite
        # cells used by either visible route, so the public board remains a
        # faithful record of the constructed two-body tradeoff.
        decoy_count = round((lanes - 2) * decoy_fraction)
        protected = {player, rival, bait_player, bait_rival}
        candidates = [index for index in range(lanes) if index not in protected]
        rng.shuffle(candidates)
        for index in candidates[:decoy_count]:
            if rng.random() < 0.55:
                cells[index] = _cell("boost", boost - 0.045)
            else:
                cells[index] = _cell("slow", slow + 0.055)
        course.append({"index": segment, "cells": cells})
    return course


def white_only_greedy_commands(board: dict[str, Any]) -> list[int]:
    """Choose the locally fastest visible WHITE lane without using BLUE state."""

    lanes = int(board["lane_count"])
    segments = int(board["segment_count"])
    player_lane = int(board["player_start_lane"])
    commands = [0]
    for segment in range(1, segments):
        choices: list[tuple[float, int, int, int]] = []
        for direction in (-1, 0, 1):
            lane = player_lane + direction
            if 0 <= lane < lanes:
                multiplier = float(board["course"][segment]["cells"][lane]["multiplier"])
                choices.append((multiplier, int(direction == 0), -abs(direction), direction))
        _multiplier, _hold, _distance, direction = max(choices)
        commands.append(direction)
        player_lane = max(0, min(lanes - 1, player_lane + direction))
    return commands


def simulate_solution(board: dict[str, Any], commands: list[int]) -> dict[str, Any]:
    """Replay the constructive route using only visible board values."""

    segments = int(board["segment_count"])
    lanes = int(board["lane_count"])
    player_lane = int(board["player_start_lane"])
    rival_lane = int(board["rival_start_lane"])
    player_progress = 0.0
    rival_progress = 0.0
    tick = 0
    next_command = 1
    player_finish: int | None = None
    rival_finish: int | None = None
    while tick < int(board["max_ticks"]):
        player_segment = min(segments - 1, int(player_progress))
        if next_command < segments and player_segment >= next_command:
            direction = int(commands[next_command])
            player_lane = max(0, min(lanes - 1, player_lane + direction))
            rival_lane = max(0, min(lanes - 1, rival_lane - direction))
            next_command += 1
        player_segment = min(segments - 1, int(player_progress))
        rival_segment = min(segments - 1, int(rival_progress))
        player_progress += float(board["base_rate"]) * float(board["course"][player_segment]["cells"][player_lane]["multiplier"])
        rival_progress += float(board["base_rate"]) * float(board["course"][rival_segment]["cells"][rival_lane]["multiplier"])
        tick += 1
        if player_finish is None and player_progress >= segments:
            player_finish = tick
        if rival_finish is None and rival_progress >= segments:
            rival_finish = tick
        if player_finish is not None and rival_finish is not None:
            break
    return {
        "player_finish_tick": player_finish,
        "rival_finish_tick": rival_finish,
        "ticks": tick,
        "player_wins": player_finish is not None and rival_finish is not None and player_finish < rival_finish,
    }


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    level, parameters, condition = _profile(task)
    rng = random.Random(_seed_int(seed))
    lanes = int(parameters["lane_count"])
    segments = int(parameters["segment_count"])
    player_start = max(0, lanes // 2 - 1)
    rival_start = min(lanes - 1, lanes // 2 + 1)

    chosen: tuple[list[dict[str, Any]], list[int], dict[str, Any]] | None = None
    max_attempts = 1200
    for _attempt in range(max_attempts):
        _, _, commands = _route(rng, lanes, segments)
        _, _, bait_commands = _route(rng, lanes, segments)
        course = _build_course(rng, parameters, player_start, rival_start, commands, bait_commands)
        board = {
            "lane_count": lanes,
            "segment_count": segments,
            "player_start_lane": player_start,
            "rival_start_lane": rival_start,
            "base_rate": float(parameters["base_rate"]),
            "tick_ms": int(parameters["tick_ms"]),
            "max_ticks": int(parameters["max_ticks"]),
            "course": course,
        }
        replay = simulate_solution(board, commands)
        greedy_commands = white_only_greedy_commands(board)
        greedy_replay = simulate_solution(board, greedy_commands)
        if replay["player_wins"] and not greedy_replay["player_wins"]:
            chosen = (course, commands, replay)
            break
    if chosen is None:
        # Never silently emit a board that bypasses the coupled-race predicate.
        # A profile or seed that cannot construct both a private winning route
        # and a public-board-only greedy loss is a generator defect, not a
        # valid fallback instance.
        raise RuntimeError(
            "reflected rival could not construct a coupled-race board "
            f"after {max_attempts} attempts"
        )
    else:
        course, commands, replay = chosen
        board = {
            "lane_count": lanes,
            "segment_count": segments,
            "player_start_lane": player_start,
            "rival_start_lane": rival_start,
            "base_rate": float(parameters["base_rate"]),
            "tick_ms": int(parameters["tick_ms"]),
            "max_ticks": int(parameters["max_ticks"]),
            "course": course,
        }

    condition_token = f"|d{level}|{condition.get('interaction')}" if condition else "|baseline"
    challenge_id = hashlib.sha256(
        f"{seed}|{MECHANIC_ID}{condition_token}".encode("utf-8")
    ).hexdigest()[:16]
    public = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Win the mirrored race.",
        "asset_manifest": "shared_runtime/assets/provenance/reflected_rival_v0.json",
        "generator": {"name": "reflected_dual_course_v2", "variant_count": 7 * 15 * 3**15},
        "board": copy.deepcopy(board),
    }
    truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "seed": seed,
        "challenge_id": challenge_id,
        "board": copy.deepcopy(board),
        "solution_commands": commands,
        "constructive_replay": replay,
    }
    if condition is not None:
        public["control_condition"] = copy.deepcopy(condition)
        truth["control_condition"] = copy.deepcopy(condition)
    return public, truth


__all__ = ["MECHANIC_ID", "PROFILES", "generate", "simulate_solution", "white_only_greedy_commands"]
