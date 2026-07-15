from __future__ import annotations

from collections import Counter
import hashlib
import random
from typing import Any


MECHANIC_ID = "exact_change_candy_cascade"
HEIGHT = 5
WIDTH = 5
MOVE_BUDGET = 4
CANDIES = ("cherry", "lemon", "mint", "plum", "orange")
FORBIDDEN = "black_licorice"
PALETTES = ("soda-pop", "night-shift", "sea-glass", "paper-wrapper")

Coord = tuple[int, int]
Swap = tuple[Coord, Coord]


def _all_swaps() -> list[Swap]:
    swaps: list[Swap] = []
    for row in range(HEIGHT):
        for column in range(WIDTH):
            if column + 1 < WIDTH:
                swaps.append(((row, column), (row, column + 1)))
            if row + 1 < HEIGHT:
                swaps.append(((row, column), (row + 1, column)))
    return swaps


ALL_SWAPS = _all_swaps()


def _matches(board: list[list[str]]) -> set[Coord]:
    matched: set[Coord] = set()
    for row in range(HEIGHT):
        start = 0
        while start < WIDTH:
            candy = board[row][start]
            end = start + 1
            while end < WIDTH and board[row][end] == candy:
                end += 1
            if candy != FORBIDDEN and end - start >= 3:
                matched.update((row, column) for column in range(start, end))
            start = end
    for column in range(WIDTH):
        start = 0
        while start < HEIGHT:
            candy = board[start][column]
            end = start + 1
            while end < HEIGHT and board[end][column] == candy:
                end += 1
            if candy != FORBIDDEN and end - start >= 3:
                matched.update((row, column) for row in range(start, end))
            start = end
    return matched


def _resolve(board: list[list[str]], refill: list[str], refill_index: int) -> tuple[list[list[str]], int, int, int]:
    board = [row[:] for row in board]
    score = 0
    wave = 0
    while True:
        matched = _matches(board)
        if not matched:
            return board, refill_index, score, wave
        wave += 1
        if wave > 20:
            raise ValueError("cascade did not settle")
        score += len(matched) * 10 * wave
        for column in range(WIDTH):
            survivors = [board[row][column] for row in range(HEIGHT) if (row, column) not in matched]
            holes = HEIGHT - len(survivors)
            additions = refill[refill_index : refill_index + holes]
            if len(additions) != holes:
                raise ValueError("refill stream exhausted")
            refill_index += holes
            rebuilt = additions + survivors
            for row, candy in enumerate(rebuilt):
                board[row][column] = candy


def _apply(board: list[list[str]], refill: list[str], refill_index: int, swap: Swap) -> tuple[list[list[str]], int, int, int] | None:
    first, second = swap
    if board[first[0]][first[1]] == FORBIDDEN or board[second[0]][second[1]] == FORBIDDEN:
        return None
    swapped = [row[:] for row in board]
    swapped[first[0]][first[1]], swapped[second[0]][second[1]] = swapped[second[0]][second[1]], swapped[first[0]][first[1]]
    if not _matches(swapped):
        return None
    return _resolve(swapped, refill, refill_index)


def _serialize_swap(swap: Swap) -> list[list[int]]:
    return [[swap[0][0], swap[0][1]], [swap[1][0], swap[1][1]]]


def _routes(board: list[list[str]], refill: list[str]) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []

    def walk(
        current: list[list[str]],
        refill_index: int,
        depth: int,
        swaps: list[Swap],
        scores: list[int],
        waves: list[int],
    ) -> None:
        if depth == MOVE_BUDGET:
            routes.append(
                {
                    "target_score": sum(scores),
                    "solution_swaps": [_serialize_swap(swap) for swap in swaps],
                    "move_scores": scores[:],
                    "wave_counts": waves[:],
                    "final_board": [row[:] for row in current],
                    "final_refill_index": refill_index,
                }
            )
            return
        for swap in ALL_SWAPS:
            outcome = _apply(current, refill, refill_index, swap)
            if outcome is None:
                continue
            next_board, next_refill, score, wave = outcome
            walk(next_board, next_refill, depth + 1, [*swaps, swap], [*scores, score], [*waves, wave])

    walk(board, 0, 0, [], [], [])
    return routes


def _build_solved_instance(rng: random.Random) -> dict[str, Any]:
    best: tuple[int, dict[str, Any]] | None = None
    for attempt in range(160):
        board = [[rng.choice(CANDIES) for _ in range(WIDTH)] for _ in range(HEIGHT)]
        forbidden = (rng.randrange(HEIGHT), rng.randrange(WIDTH))
        board[forbidden[0]][forbidden[1]] = FORBIDDEN
        if _matches(board):
            continue
        refill = [rng.choice(CANDIES) for _ in range(900)]
        candidates = [
            route
            for route in _routes(board, refill)
            if max(route["wave_counts"], default=0) >= 3 and sum(route["wave_counts"]) >= 7
        ]
        if not candidates:
            continue
        score_counts = Counter(candidate["target_score"] for candidate in candidates)
        candidates.sort(
            key=lambda candidate: (
                score_counts[candidate["target_score"]],
                -max(candidate["wave_counts"]),
                -sum(candidate["wave_counts"]),
                -candidate["target_score"],
            )
        )
        chosen = candidates[0]
        multiplicity = score_counts[chosen["target_score"]]
        record = {
            "board": board,
            "refill": refill,
            "forbidden": [forbidden[0], forbidden[1]],
            "attempt": attempt,
            "solution_count_for_target": multiplicity,
            **chosen,
        }
        if multiplicity <= 3:
            return record
        if best is None or multiplicity < best[0]:
            best = (multiplicity, record)
    if best is not None and best[0] <= 8:
        return best[1]
    raise ValueError("could not produce an audited four-swap exact-change board")


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    digest = hashlib.sha256(f"{seed}|{MECHANIC_ID}|v2".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    instance = _build_solved_instance(rng)
    task_id = str(task.get("id") or "exact_change_candy_cascade_seed_0001@0.1")
    challenge_id = hashlib.sha256(f"{seed}|exact-change-candy-cascade-v2".encode("utf-8")).hexdigest()[:12]
    palette = PALETTES[rng.randrange(len(PALETTES))]
    variant_upper_bound = len(PALETTES) * HEIGHT * WIDTH * (len(CANDIES) ** (HEIGHT * WIDTH - 1))
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Make exactly the posted change in four valid swaps. Never disturb the black licorice.",
        "submit_label": "STAMP EXACT",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_puzzles_v1.json",
        "generator": {
            "name": "exact_change_candy_cascade_v2",
            "search_attempt": instance["attempt"],
            "variant_count": variant_upper_bound,
            "variant_count_kind": "pre-search board/palette upper bound",
        },
        "board": instance["board"],
        "refill_stream": instance["refill"],
        "target_score": instance["target_score"],
        "move_budget": MOVE_BUDGET,
        "forbidden": {
            "candy": FORBIDDEN,
            "position": instance["forbidden"],
            "rule": "Swapping the black licorice voids the entire receipt immediately.",
        },
        "score_rule": "Each wave pays 10 points per candy multiplied by its cascade wave (1x, 2x, 3x…).",
        "palette": palette,
        "variant_count": variant_upper_bound,
        "variant_count_kind": "pre-search board/palette upper bound",
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "initial_board": instance["board"],
        "refill_stream": instance["refill"],
        "target_score": instance["target_score"],
        "move_budget": MOVE_BUDGET,
        "forbidden_candy": FORBIDDEN,
        "forbidden_position": instance["forbidden"],
        "solution_swaps": instance["solution_swaps"],
        "solution_move_scores": instance["move_scores"],
        "solution_wave_counts": instance["wave_counts"],
        "solution_final_board": instance["final_board"],
        "solution_refill_index": instance["final_refill_index"],
        "solution_count_for_target": instance["solution_count_for_target"],
        "palette": palette,
        "variant_count": variant_upper_bound,
        "variant_count_kind": "pre-search board/palette upper bound",
    }
    return public_state, ground_truth
