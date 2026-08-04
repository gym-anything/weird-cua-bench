from __future__ import annotations

import copy
import hashlib
import math
import random
from typing import Any


MECHANIC_ID = "ribbon_switchboard"
STAGE_WIDTH = 1000
STAGE_HEIGHT = 440
CONTROL_X = (70, 242, 414, 586, 758, 930)
SAMPLES_PER_SPAN = 18
COLORS = ("#ff5f6d", "#5fe0d0", "#ffd166", "#7e8cff", "#f39cde", "#93e85f")
HISTORICAL_MAX_CLOSE_RUN_THRESHOLD = 18
HISTORICAL_LAYOUT_ATTEMPT_LIMIT = 500
DENSE_LAYOUT_ATTEMPT_LIMIT = 5_000

# These values are the pre-control task contract.  L4 reproduces them exactly
# for a fixed seed; the other profiles vary the visible weave and the required
# local inspection and tracing work around that reference configuration.
DEFAULT_PARAMETERS = {
    "ribbon_count_min": 4,
    "ribbon_count_max": 6,
    "control_column_count": 6,
    "min_target_crossings": 5,
    "crossing_floor": 8,
    "crossing_per_ribbon_offset": 4,
    "min_target_crossing_spacing": 1.8,
    "maximum_close_run": 9,
    "third_ribbon_clearance": 16,
    "hover_radius_min": 58,
    "hover_radius_max": 66,
    "corridor_radius_min": 18,
    "corridor_radius_max": 22,
    "min_hover_samples": 26,
    "min_hover_cells": 14,
    "target_coverage_ratio": 0.66,
    "target_coverage_cap": 62,
    "min_crossing_coverage": 6,
    "min_trace_samples": 70,
    "trace_coverage_ratio": 0.78,
    "min_trace_ms": 560,
    "max_raw_step": 44,
    "max_parameter_jump": 4.5,
    "backtrack_tolerance": 1.5,
}
CONTROL_FIELDS = frozenset(DEFAULT_PARAMETERS)


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _transition(value: float, weight: float) -> float:
    if value <= 0:
        return 0.0
    if value >= 1:
        return 1.0
    first = value**1.7
    second = (1 - value) ** 1.7 * weight
    return first / (first + second)


def _control_parameters(task: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    condition = task.get("_control_condition")
    if condition is None:
        return None, dict(DEFAULT_PARAMETERS)
    if not isinstance(condition, dict):
        raise ValueError("ribbon control condition is malformed")
    parameters = dict(condition.get("difficulty_parameters") or {})
    if set(parameters) != CONTROL_FIELDS:
        missing = sorted(CONTROL_FIELDS - set(parameters))
        unexpected = sorted(set(parameters) - CONTROL_FIELDS)
        detail = ", ".join([*(f"missing {item}" for item in missing), *(f"unexpected {item}" for item in unexpected)])
        raise ValueError(f"ribbon control profile fields do not match: {detail}")
    merged = dict(DEFAULT_PARAMETERS)
    merged.update(parameters)
    integer_ranges = {
        "ribbon_count_min": (3, len(COLORS)),
        "ribbon_count_max": (3, len(COLORS)),
        "control_column_count": (4, 8),
        "min_target_crossings": (2, 14),
        "crossing_floor": (3, 30),
        "crossing_per_ribbon_offset": (0, 8),
        "maximum_close_run": (1, 18),
        "third_ribbon_clearance": (8, 48),
        "hover_radius_min": (28, 140),
        "hover_radius_max": (28, 140),
        "corridor_radius_min": (10, 44),
        "corridor_radius_max": (10, 44),
        "min_hover_samples": (1, 180),
        "min_hover_cells": (1, 80),
        "target_coverage_cap": (1, 180),
        "min_crossing_coverage": (1, 14),
        "min_trace_samples": (1, 220),
        "min_trace_ms": (0, 20_000),
        "max_raw_step": (10, 140),
    }
    for name, (low, high) in integer_ranges.items():
        value = merged[name]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"ribbon control parameter {name} must be an integer in {low}..{high}")
    for name in (
        "min_target_crossing_spacing",
        "target_coverage_ratio",
        "trace_coverage_ratio",
        "max_parameter_jump",
        "backtrack_tolerance",
    ):
        value = merged[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"ribbon control parameter {name} must be finite")
    if not (
        merged["ribbon_count_min"] <= merged["ribbon_count_max"]
        and merged["hover_radius_min"] <= merged["hover_radius_max"]
        and merged["corridor_radius_min"] <= merged["corridor_radius_max"]
        and 0 < float(merged["target_coverage_ratio"]) <= 1
        and 0 < float(merged["trace_coverage_ratio"]) <= 1
        and float(merged["min_target_crossing_spacing"]) > 0
        and float(merged["max_parameter_jump"]) > 0
        and float(merged["backtrack_tolerance"]) >= 0
    ):
        raise ValueError("ribbon control parameter ranges are invalid")
    return copy.deepcopy(condition), merged


def _control_x(count: int) -> tuple[int, ...]:
    if count == len(CONTROL_X):
        return CONTROL_X
    return tuple(round(CONTROL_X[0] + index * (CONTROL_X[-1] - CONTROL_X[0]) / (count - 1)) for index in range(count))


def _crossings(ribbons: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    crossings: list[dict[str, Any]] = []
    serial = 1
    for first_index, first in enumerate(ribbons):
        for second in ribbons[first_index + 1 :]:
            last_crossing = -10.0
            for index in range(len(first["points"]) - 1):
                first_delta = first["points"][index][1] - second["points"][index][1]
                second_delta = first["points"][index + 1][1] - second["points"][index + 1][1]
                if first_delta == 0:
                    fraction = 0.0
                elif first_delta * second_delta < 0:
                    fraction = abs(first_delta) / (abs(first_delta) + abs(second_delta))
                else:
                    continue
                parameter = index + fraction
                if parameter - last_crossing < 3.0:
                    continue
                x = round(first["points"][index][0] + (first["points"][index + 1][0] - first["points"][index][0]) * fraction)
                y = round(first["points"][index][1] + (first["points"][index + 1][1] - first["points"][index][1]) * fraction)
                over = rng.choice((first["id"], second["id"]))
                crossings.append({
                    "id": f"cross-{serial:02}",
                    "ribbons": [first["id"], second["id"]],
                    "over": over,
                    "under": second["id"] if over == first["id"] else first["id"],
                    "point": [x, y],
                    "parameters": {first["id"]: round(parameter, 4), second["id"]: round(parameter, 4)},
                })
                serial += 1
                last_crossing = parameter
    return crossings


def _max_close_run(ribbons: list[dict[str, Any]], threshold: int) -> int:
    maximum = 0
    for first_index, first in enumerate(ribbons):
        for second in ribbons[first_index + 1 :]:
            current = 0
            for first_point, second_point in zip(first["points"], second["points"]):
                if abs(first_point[1] - second_point[1]) < threshold:
                    current += 1
                    maximum = max(maximum, current)
                else:
                    current = 0
    return maximum


def _ambiguous_crossing(crossing: dict[str, Any], ribbons: list[dict[str, Any]], threshold: int = 16) -> bool:
    involved = set(crossing["ribbons"])
    parameter = next(iter(crossing["parameters"].values()))
    index = min(len(ribbons[0]["points"]) - 2, int(parameter))
    fraction = parameter - index
    y = crossing["point"][1]
    for ribbon in ribbons:
        if ribbon["id"] in involved:
            continue
        candidate = ribbon["points"][index][1] + (ribbon["points"][index + 1][1] - ribbon["points"][index][1]) * fraction
        if abs(candidate - y) < threshold:
            return True
    return False


def _make_layout(
    rng: random.Random,
    ribbon_count: int,
    target_id: str,
    control_x: tuple[int, ...],
    parameters: dict[str, Any],
    attempt_limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    ribbon_ids = [f"ribbon-{index + 1}" for index in range(ribbon_count)]
    slots = [round(67 + index * 306 / (ribbon_count - 1)) for index in range(ribbon_count)]
    for _attempt in range(attempt_limit):
        orders: list[list[int]] = [list(range(ribbon_count))]
        rng.shuffle(orders[0])
        for column in range(1, len(control_x)):
            previous = orders[-1]
            candidate = previous[:]
            for _ in range(100):
                rng.shuffle(candidate)
                moved = sum(a != b for a, b in zip(previous, candidate))
                if moved >= max(3, ribbon_count - 1):
                    break
            orders.append(candidate[:])

        y_controls: dict[int, list[int]] = {index: [] for index in range(ribbon_count)}
        for order in orders:
            for slot_index, ribbon_index in enumerate(order):
                y_controls[ribbon_index].append(slots[slot_index] + rng.randint(-4, 4))
        weights = {
            ribbon_index: [rng.uniform(0.48, 1.9) for _ in range(len(control_x) - 1)]
            for ribbon_index in range(ribbon_count)
        }
        bows = {
            ribbon_index: [rng.randint(-11, 11) for _ in range(len(control_x) - 1)]
            for ribbon_index in range(ribbon_count)
        }
        ribbons: list[dict[str, Any]] = []
        for ribbon_index, ribbon_id in enumerate(ribbon_ids):
            points: list[list[int]] = []
            for span in range(len(control_x) - 1):
                for sample in range(SAMPLES_PER_SPAN):
                    t = sample / SAMPLES_PER_SPAN
                    amount = _transition(t, weights[ribbon_index][span])
                    x = control_x[span] + (control_x[span + 1] - control_x[span]) * t
                    y = y_controls[ribbon_index][span] + (y_controls[ribbon_index][span + 1] - y_controls[ribbon_index][span]) * amount
                    y += math.sin(math.pi * t) * bows[ribbon_index][span]
                    point = [round(x), round(y)]
                    if not points or points[-1] != point:
                        points.append(point)
            points.append([control_x[-1], y_controls[ribbon_index][-1]])
            ribbons.append({
                "id": ribbon_id,
                "label": f"BUS {chr(65 + ribbon_index)}",
                "color": COLORS[ribbon_index],
                "points": points,
                "source": points[0],
                "terminal": points[-1],
            })
        crossings = _crossings(ribbons, rng)
        target_crossings = []
        for crossing in crossings:
            if target_id in crossing["ribbons"]:
                target_crossings.append({
                    **crossing,
                    "target_parameter": crossing["parameters"][target_id],
                    "target_is_over": crossing["over"] == target_id,
                })
        target_crossings.sort(key=lambda item: item["target_parameter"])
        spacings = [b["target_parameter"] - a["target_parameter"] for a, b in zip(target_crossings, target_crossings[1:])]
        # The historical generator measured this audit field at 18 px, while
        # third_ribbon_clearance (16 px at the historical baseline) applies to
        # the separate local-crossing ambiguity check below. Keeping these
        # distinct preserves every historical L4 state, including its public
        # clearance_audit value.
        max_close = _max_close_run(ribbons, HISTORICAL_MAX_CLOSE_RUN_THRESHOLD)
        if (
            len(crossings) >= max(int(parameters["crossing_floor"]), ribbon_count + int(parameters["crossing_per_ribbon_offset"]))
            and len(target_crossings) >= int(parameters["min_target_crossings"])
            and (not spacings or min(spacings) >= float(parameters["min_target_crossing_spacing"]))
            and max_close <= int(parameters["maximum_close_run"])
            and not any(_ambiguous_crossing(item, ribbons, int(parameters["third_ribbon_clearance"])) for item in target_crossings)
        ):
            audit = {
                "crossing_count": len(crossings),
                "target_crossing_count": len(target_crossings),
                "minimum_target_crossing_spacing": round(min(spacings) if spacings else len(ribbons[0]["points"]), 3),
                "maximum_close_run": max_close,
                "third_ribbon_clearance": int(parameters["third_ribbon_clearance"]),
            }
            return ribbons, crossings, audit
    raise RuntimeError("could not generate a distinguishable woven ribbon layout")


def _dense_fallback_layout(parameters: dict[str, Any], target_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Return a verified deterministic L5 layout if a random search is exhausted.

    The target-specific seeds below are not a second puzzle contract: they
    drive the same layout construction and acceptance checks as the sampled
    path. They have a known valid candidate for every possible L5 target bus,
    so a failed certification can always receive a new renderable challenge.
    """
    fallback_rng = random.Random(_seed_int(f"dense-layout-fallback|{target_id}", MECHANIC_ID))
    return _make_layout(
        fallback_rng,
        ribbon_count=6,
        target_id=target_id,
        control_x=_control_x(7),
        parameters=parameters,
        attempt_limit=DENSE_LAYOUT_ATTEMPT_LIMIT,
    )


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    condition, parameters = _control_parameters(task)
    ribbon_count = rng.randint(int(parameters["ribbon_count_min"]), int(parameters["ribbon_count_max"]))
    target_id = f"ribbon-{rng.randrange(ribbon_count) + 1}"
    # Preserve the historical 500-attempt random stream for the uncontrolled
    # task and L4. The denser L5 profile retains the same acceptance rules but
    # receives a larger deterministic search budget, so a rejected submission
    # cannot strand a player on a rare unrenderable replacement seed.
    attempt_limit = (
        DENSE_LAYOUT_ATTEMPT_LIMIT
        if condition is not None and int(condition["difficulty"]) == 5
        else HISTORICAL_LAYOUT_ATTEMPT_LIMIT
    )
    try:
        ribbons, crossings, clearance_audit = _make_layout(
            rng,
            ribbon_count,
            target_id,
            _control_x(int(parameters["control_column_count"])),
            parameters,
            attempt_limit,
        )
    except RuntimeError:
        if condition is None or int(condition["difficulty"]) != 5:
            raise
        ribbons, crossings, clearance_audit = _dense_fallback_layout(parameters, target_id)
    target = next(ribbon for ribbon in ribbons if ribbon["id"] == target_id)
    target_crossings = [
        {
            **crossing,
            "target_parameter": crossing["parameters"][target_id],
            "target_is_over": crossing["over"] == target_id,
        }
        for crossing in crossings
        if target_id in crossing["ribbons"]
    ]
    target_crossings.sort(key=lambda item: item["target_parameter"])
    hover_radius = rng.randint(int(parameters["hover_radius_min"]), int(parameters["hover_radius_max"]))
    corridor_radius = rng.randint(int(parameters["corridor_radius_min"]), int(parameters["corridor_radius_max"]))
    requirements = {
        "min_hover_samples": int(parameters["min_hover_samples"]),
        "min_hover_cells": int(parameters["min_hover_cells"]),
        "min_target_coverage": min(int(parameters["target_coverage_cap"]), round(len(target["points"]) * float(parameters["target_coverage_ratio"]))),
        "min_crossing_coverage": min(int(parameters["min_crossing_coverage"]), len(target_crossings)),
        "min_trace_samples": max(int(parameters["min_trace_samples"]), round(len(target["points"]) * float(parameters["trace_coverage_ratio"]))),
        "min_trace_ms": int(parameters["min_trace_ms"]),
        "max_raw_step": int(parameters["max_raw_step"]),
        "max_parameter_jump": float(parameters["max_parameter_jump"]),
        "backtrack_tolerance": float(parameters["backtrack_tolerance"]),
    }
    task_id = str(task.get("id") or "ribbon_switchboard_seed_0001@0.1")
    condition_token = "" if condition is None or int(condition["difficulty"]) == 4 else f"|d{int(condition['difficulty'])}"
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}{condition_token}".encode("utf-8")).hexdigest()[:12]
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": "Illuminate the weave locally. Carry the marked signal from its source to the true terminal without leaving the ribbon.",
        "submit_label": "CERTIFY ROUTED SIGNAL",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "generator": {"name": "analytic_woven_ribbon_field_v1", "variant_count": 9_400_000_000},
        "stage": {"width": STAGE_WIDTH, "height": STAGE_HEIGHT},
        "ribbons": ribbons,
        "crossings": crossings,
        "target_id": target_id,
        "target_color": target["color"],
        "source": target["source"],
        "terminals": [{"id": ribbon["id"], "label": ribbon["label"], "point": ribbon["terminal"], "color": ribbon["color"]} for ribbon in ribbons],
        "hover_radius": hover_radius,
        "corridor_radius": corridor_radius,
        "requirements": requirements,
        "clearance_audit": clearance_audit,
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "stage": public_state["stage"],
        "ribbons": ribbons,
        "crossings": crossings,
        "target_id": target_id,
        "target_path": target["points"],
        "target_terminal": target["terminal"],
        "target_crossings": target_crossings,
        "hover_radius": hover_radius,
        "corridor_radius": corridor_radius,
        "requirements": requirements,
        "clearance_audit": clearance_audit,
        "variant_count": public_state["generator"]["variant_count"],
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    assert len(target_crossings) >= int(parameters["min_target_crossings"]) and clearance_audit["maximum_close_run"] <= int(parameters["maximum_close_run"])
    return public_state, ground_truth
