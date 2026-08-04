from __future__ import annotations

import hashlib
import math
import copy
import random
from typing import Any


MECHANIC_ID = "insider_trading_captcha"
ORDER_DELAY_TICKS = 3
FEE_CENTS = 19
MAX_POSITION = 4
SIDES = ("hold", "buy", "sell")


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _replay(
    prices: list[int],
    actions: list[str],
    initial_cash: int,
    *,
    delay: int = ORDER_DELAY_TICKS,
    fee: int = FEE_CENTS,
    max_position: int = MAX_POSITION,
) -> tuple[bool, int, int, list[dict[str, int | str]]]:
    cash = initial_cash
    position = 0
    ledger: list[dict[str, int | str]] = []
    for tick, price in enumerate(prices):
        placed_tick = tick - delay
        side = actions[placed_tick] if placed_tick >= 0 else "hold"
        if side == "buy":
            if position >= max_position or cash < price + fee:
                return False, cash, position, ledger
            cash -= price + fee
            position += 1
        elif side == "sell":
            if position <= 0:
                return False, cash, position, ledger
            cash += price - fee
            position -= 1
        elif side != "hold":
            return False, cash, position, ledger
        if side != "hold":
            ledger.append(
                {
                    "placed_tick": placed_tick,
                    "settle_tick": tick,
                    "side": side,
                    "price_cents": price,
                    "fee_cents": fee,
                    "cash_after_cents": cash,
                    "position_after": position,
                }
            )
    return True, cash, position, ledger


def _best_strategy(
    prices: list[int], initial_cash: int, *, delay: int = ORDER_DELAY_TICKS,
    fee: int = FEE_CENTS, max_position: int = MAX_POSITION,
) -> tuple[list[str], int, list[dict[str, int | str]]]:
    # At tick t the oldest queued order settles before a new order is selected.
    # A higher cash balance dominates a lower one for an otherwise identical
    # physical position and delayed order queue.
    initial_queue = ("hold",) * delay
    states: dict[tuple[int, tuple[str, ...]], tuple[int, list[str]]] = {
        (0, initial_queue): (initial_cash, [])
    }
    for tick, price in enumerate(prices):
        next_states: dict[tuple[int, tuple[str, ...]], tuple[int, list[str]]] = {}
        for (position, queue), (cash, actions) in states.items():
            next_position = position
            next_cash = cash
            settling = queue[0]
            if settling == "buy":
                if next_position >= max_position or next_cash < price + fee:
                    continue
                next_cash -= price + fee
                next_position += 1
            elif settling == "sell":
                if next_position <= 0:
                    continue
                next_cash += price - fee
                next_position -= 1

            choices = SIDES if tick <= len(prices) - delay - 1 else ("hold",)
            for side in choices:
                next_queue = (*queue[1:], side)
                # Do not allow a queued order book that is guaranteed to cross
                # the physical position limits when it settles.
                committed = next_position
                for pending in next_queue:
                    if pending == "buy":
                        committed += 1
                    elif pending == "sell":
                        committed -= 1
                    if committed < 0 or committed > max_position:
                        break
                else:
                    key = (next_position, next_queue)
                    candidate = (next_cash, actions + [side])
                    incumbent = next_states.get(key)
                    if incumbent is None or candidate[0] > incumbent[0]:
                        next_states[key] = candidate
        states = next_states

    candidates: list[tuple[int, list[str]]] = []
    for (position, queue), (cash, actions) in states.items():
        if position == 0 and queue == initial_queue:
            if "buy" in actions and "sell" in actions:
                candidates.append((cash, actions))
    if not candidates:
        raise RuntimeError("market generator did not produce a flat round trip")
    best_cash, best_actions = max(candidates, key=lambda item: (item[0], item[1]))
    valid, replay_cash, replay_position, ledger = _replay(
        prices, best_actions, initial_cash, delay=delay, fee=fee, max_position=max_position
    )
    if not valid or replay_cash != best_cash or replay_position != 0:
        raise RuntimeError("market strategy replay disagrees with dynamic program")
    return best_actions, best_cash, ledger


def _make_prices(
    rng: random.Random,
    count: int,
    *,
    regime_duration_min: int = 7,
    regime_duration_max: int = 12,
    trend_slope_min: int = 68,
    trend_slope_max: int = 136,
    noise_cents: int = 27,
    spike_probability: float = 0.08,
    spike_min: int = 42,
    spike_max: int = 86,
) -> list[int]:
    value = rng.randrange(1_850, 2_751, 25)
    prices = [value]
    direction = rng.choice((-1, 1))
    while len(prices) < count:
        choices = [-1, 0, 1]
        if direction in choices:
            choices.remove(direction)
        direction = rng.choices(choices, weights=[4 if item else 1 for item in choices], k=1)[0]
        duration = rng.randint(regime_duration_min, regime_duration_max)
        if trend_slope_min == 68 and trend_slope_max == 136:
            slope = rng.randrange(68, 137, 4)
        else:
            slope = rng.randint(trend_slope_min, trend_slope_max)
        for local in range(duration):
            if len(prices) >= count:
                break
            edge_scale = min(1.0, 0.55 + min(local, duration - 1 - local) * 0.18)
            if direction:
                movement = direction * slope * edge_scale + rng.randint(-noise_cents, noise_cents)
            else:
                anchor = sum(prices[-min(4, len(prices)):]) / min(4, len(prices))
                movement = (anchor - prices[-1]) * 0.35 + rng.randint(-noise_cents - 7, noise_cents + 7)
            if spike_probability > 0 and rng.random() < spike_probability:
                movement += rng.choice((-1, 1)) * rng.randint(spike_min, spike_max)
            value = int(round(max(525, min(5_800, prices[-1] + movement)) / 5.0) * 5)
            prices.append(value)
    return prices


def _causal_strategy(
    prices: list[int], initial_cash: int, *, delay: int = ORDER_DELAY_TICKS,
    fee: int = FEE_CENTS, max_position: int = MAX_POSITION,
) -> tuple[list[str], int, list[dict[str, int | str]]]:
    actions: list[str] = []
    queue = ["hold"] * delay
    position = 0
    liquidation_tick = len(prices) - delay - max_position - 1
    for tick, _price in enumerate(prices):
        settling = queue.pop(0)
        if settling == "buy":
            position += 1
        elif settling == "sell":
            position -= 1
        committed = position + sum(1 if item == "buy" else -1 if item == "sell" else 0 for item in queue)
        side = "hold"
        if tick < len(prices) - delay:
            if tick >= liquidation_tick:
                desired = 0
            elif tick >= 2:
                momentum = prices[tick] - prices[tick - 2]
                desired = max_position if momentum >= 72 else 0 if momentum <= -72 else committed
            else:
                desired = committed
            if committed < desired:
                side = "buy"
            elif committed > desired:
                side = "sell"
        queue.append(side)
        actions.append(side)
    valid, cash, final_position, ledger = _replay(
        prices, actions, initial_cash, delay=delay, fee=fee, max_position=max_position
    )
    if not valid or final_position != 0:
        raise RuntimeError("causal delayed-market policy failed to close flat")
    return actions, cash, ledger


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    condition = task.get("_control_condition")
    parameters = dict((condition or {}).get("difficulty_parameters") or {})
    count = rng.randint(int(parameters.get("tick_count_min", 34)), int(parameters.get("tick_count_max", 38)))
    delay = int(parameters.get("order_delay_ticks", ORDER_DELAY_TICKS))
    max_position = int(parameters.get("max_position", MAX_POSITION))
    fee = FEE_CENTS
    target_fraction = float(parameters.get("target_fraction", 0.75))
    target_floor = int(parameters.get("target_profit_floor_cents", 1_100))
    reference_settlements_min = int(parameters.get("reference_settlements_min", 10))
    if not 1 <= delay <= 6 or not 1 <= max_position <= 8 or not 0.25 <= target_fraction <= 0.95:
        raise ValueError("market difficulty parameters are outside supported limits")
    prices: list[int] = []
    initial_cash = 0
    causal_actions: list[str] = []
    causal_ledger: list[dict[str, int | str]] = []
    causal_cash = 0
    for _attempt in range(2_048):
        prices = _make_prices(
            rng,
            count,
            regime_duration_min=int(parameters.get("regime_duration_min", 7)),
            regime_duration_max=int(parameters.get("regime_duration_max", 12)),
            trend_slope_min=int(parameters.get("trend_slope_min", 68)),
            trend_slope_max=int(parameters.get("trend_slope_max", 136)),
            noise_cents=int(parameters.get("noise_cents", 27)),
            spike_probability=float(parameters.get("spike_probability", 0.08)),
            spike_min=int(parameters.get("spike_min", 42)),
            spike_max=int(parameters.get("spike_max", 86)),
        )
        initial_cash = max(prices) * max_position + 2_000
        try:
            causal_actions, causal_cash, causal_ledger = _causal_strategy(
                prices, initial_cash, delay=delay, fee=fee, max_position=max_position
            )
        except RuntimeError:
            # A purely causal momentum policy can bankrupt itself on a hostile
            # tape even when the tape has a valid clairvoyant strategy. Such a
            # tape is unsuitable for this benchmark contract, so reject it and
            # keep sampling rather than weakening the target afterward.
            continue
        causal_profit = causal_cash - initial_cash
        if (
            causal_profit >= (1_400 if not condition or int(condition["difficulty"]) == 2 else max(400, int(target_floor / target_fraction)))
            and len(causal_ledger) >= reference_settlements_min
            and "buy" in causal_actions
            and "sell" in causal_actions
        ):
            break
    else:
        raise RuntimeError("market generator did not produce a profitable causal tape")
    solver_actions, best_cash, solver_ledger = _best_strategy(
        prices, initial_cash, delay=delay, fee=fee, max_position=max_position
    )
    best_profit = best_cash - initial_cash
    if best_profit < 400:
        raise RuntimeError("generated market did not offer enough profitable motion")
    causal_profit = causal_cash - initial_cash
    target_profit = max(target_floor, int((causal_profit * target_fraction) // 25) * 25)
    target_profit = min(target_profit, best_profit - 100)

    task_id = str(task.get("id") or "")
    condition_token = f"|d{condition['difficulty']}|{task_id}" if condition else ""
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}{condition_token}".encode("utf-8")).hexdigest()[:12]
    symbol = rng.choice(("MOTH", "GHOST", "SLIME", "BELL", "FORK"))
    tick_values = parameters.get("tick_ms_values")
    if isinstance(tick_values, list) and tick_values:
        tick_ms = int(rng.choice(tick_values))
    elif parameters:
        tick_ms = rng.randint(int(parameters["tick_ms_min"]), int(parameters["tick_ms_max"]))
    else:
        tick_ms = rng.choice((640, 680, 720))
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language")
        or "Trade the live tape. Orders settle three ticks later. Close flat above target.",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_puzzles_v1.json",
        "generator": {"name": "nonperiodic_delayed_market_v2", "variant_count": 28_800_000_000},
        "symbol": symbol,
        "tick_ms": tick_ms,
        "tick_count": count,
        "order_delay_ticks": delay,
        "fee_cents": fee,
        "initial_cash_cents": initial_cash,
        "target_profit_cents": target_profit,
        "max_position": max_position,
        # The browser consumes this stream one quote at a time. It is never
        # drawn, announced, or placed in the DOM ahead of the active tick.
        "runtime_price_stream_cents": prices,
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "prices_cents": prices,
        "order_delay_ticks": delay,
        "fee_cents": fee,
        "initial_cash_cents": initial_cash,
        "target_profit_cents": target_profit,
        "max_position": max_position,
        "solver_actions": solver_actions,
        "solver_ledger": solver_ledger,
        "causal_reference_actions": causal_actions,
        "causal_reference_ledger": causal_ledger,
        "causal_reference_profit_cents": causal_profit,
        "max_profit_cents": best_profit,
        "variant_count": 28_800_000_000,
    }
    assert len(solver_actions) == count
    assert solver_actions[-delay:] == ["hold"] * delay
    assert "buy" in solver_actions and "sell" in solver_actions
    if condition:
        public_state["visible_chart_ticks"] = int(parameters.get("visible_chart_ticks", 0))
        ground_truth["visible_chart_ticks"] = int(parameters.get("visible_chart_ticks", 0))
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
