from __future__ import annotations

import calendar
import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "thirty_year_time_wheel"
MIN_YEAR = 1996
MAX_YEAR = 2025
PALETTES = ("orrery", "verdigris", "eclipse", "almanac")


def _days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _step_month(
    date: dict[str, int],
    direction: int,
    minimum: int = MIN_YEAR,
    maximum: int = MAX_YEAR,
) -> dict[str, int]:
    year, month, day = date["year"], date["month"], date["day"]
    ordinal = year * 12 + month - 1 + direction
    minimum_ordinal = minimum * 12
    maximum_ordinal = maximum * 12 + 11
    ordinal = max(minimum_ordinal, min(maximum_ordinal, ordinal))
    next_year, month_index = divmod(ordinal, 12)
    next_month = month_index + 1
    return {"year": next_year, "month": next_month, "day": min(day, _days_in_month(next_year, next_month))}


def _step_year(
    date: dict[str, int],
    direction: int,
    minimum: int = MIN_YEAR,
    maximum: int = MAX_YEAR,
) -> dict[str, int]:
    year = max(minimum, min(maximum, date["year"] + direction))
    return {"year": year, "month": date["month"], "day": min(date["day"], _days_in_month(year, date["month"]))}


def _step_day(date: dict[str, int], direction: int) -> dict[str, int]:
    maximum = _days_in_month(date["year"], date["month"])
    day = ((date["day"] - 1 + direction) % maximum) + 1
    return {"year": date["year"], "month": date["month"], "day": day}


def _apply(
    date: dict[str, int],
    component: str,
    steps: int,
    minimum: int = MIN_YEAR,
    maximum: int = MAX_YEAR,
) -> dict[str, int]:
    current = dict(date)
    direction = 1 if steps >= 0 else -1
    for _ in range(abs(steps)):
        if component == "month":
            current = _step_month(current, direction, minimum, maximum)
        elif component == "year":
            current = _step_year(current, direction, minimum, maximum)
        elif component == "day":
            current = _step_day(current, direction)
        else:
            raise ValueError(f"unknown component {component}")
    return current


def _generate_dates(rng: random.Random) -> tuple[dict[str, int], dict[str, int], list[dict[str, Any]]]:
    for _attempt in range(200):
        initial_year = rng.randint(MIN_YEAR, MAX_YEAR)
        initial_month = rng.randint(1, 12)
        initial_day = rng.randint(1, _days_in_month(initial_year, initial_month))
        target_year = rng.choice([year for year in range(MIN_YEAR, MAX_YEAR + 1) if year != initial_year])
        target_month = rng.choice([month for month in range(1, 13) if month != initial_month])
        target_day = rng.randint(1, _days_in_month(target_year, target_month))
        if target_day == initial_day:
            continue
        initial = {"year": initial_year, "month": initial_month, "day": initial_day}
        target = {"year": target_year, "month": target_month, "day": target_day}
        current = dict(initial)
        month_steps = target_month - current["month"]
        current = _apply(current, "month", month_steps)
        year_steps = target_year - current["year"]
        current = _apply(current, "year", year_steps)
        day_steps = target_day - current["day"]
        if day_steps == 0:
            continue
        current = _apply(current, "day", day_steps)
        if current != target:
            continue
        route = [
            {"component": "month", "steps": month_steps},
            {"component": "year", "steps": year_steps},
            {"component": "day", "steps": day_steps},
        ]
        if all(item["steps"] != 0 for item in route):
            return initial, target, route
    raise ValueError("could not generate a practical three-ring date route")


def _generate_controlled_dates(
    rng: random.Random,
    *,
    minimum: int,
    maximum: int,
    required_components: tuple[str, ...],
    force_calendar_clamp: bool,
) -> tuple[dict[str, int], dict[str, int], list[dict[str, Any]]]:
    """Generate the profile's visible calendar and a canonical useful route."""

    required = set(required_components)
    for _attempt in range(400):
        if force_calendar_clamp:
            initial_year = rng.randint(minimum, maximum)
            initial_month = rng.choice((1, 3, 5, 7, 8, 10, 12))
            initial_day = 31
            target_month = rng.choice((2, 4, 6, 9, 11))
        else:
            initial_year = rng.randint(minimum, maximum)
            initial_month = rng.randint(1, 12)
            initial_day = rng.randint(1, _days_in_month(initial_year, initial_month))
            target_month = initial_month
        target_year = initial_year
        if "year" in required:
            target_year = rng.choice([year for year in range(minimum, maximum + 1) if year != initial_year])
        if "month" in required:
            if not force_calendar_clamp:
                target_month = rng.choice([month for month in range(1, 13) if month != initial_month])
        if "day" not in required:
            initial_day = min(initial_day, _days_in_month(initial_year, initial_month))
        elif not force_calendar_clamp:
            # Keep L2 free of a hidden clamp; the calendar dependency is the
            # visible later day adjustment, not an accidental February trap.
            initial_day = min(initial_day, 25)

        initial = {"year": initial_year, "month": initial_month, "day": initial_day}
        month_steps = target_month - initial_month if "month" in required else 0
        after_month = _apply(initial, "month", month_steps, minimum, maximum)
        year_steps = target_year - after_month["year"] if "year" in required else 0
        after_year = _apply(after_month, "year", year_steps, minimum, maximum)
        if "day" in required:
            target_day = rng.randint(1, _days_in_month(target_year, target_month))
            if target_day == after_year["day"]:
                continue
            day_steps = target_day - after_year["day"]
        else:
            target_day = after_year["day"]
            day_steps = 0
        target = {"year": target_year, "month": target_month, "day": target_day}
        route = [
            {"component": "month", "steps": month_steps},
            {"component": "year", "steps": year_steps},
            {"component": "day", "steps": day_steps},
        ]
        if any(item["steps"] == 0 for item in route if item["component"] in required):
            continue
        current = dict(initial)
        for item in route:
            current = _apply(current, item["component"], item["steps"], minimum, maximum)
        if current == target:
            return initial, target, [item for item in route if item["component"] in required]
    raise ValueError("could not generate a practical controlled time-wheel route")


def _controlled_profile(task: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    condition = task.get("_control_condition")
    if not isinstance(condition, dict):
        return None, {}
    parameters = condition.get("difficulty_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("time-wheel controlled task has no difficulty parameters")
    return condition, dict(parameters)


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition, parameters = _controlled_profile(task)
    difficulty = int(condition["difficulty"]) if condition is not None else 3
    minimum = int(parameters.get("year_min", MIN_YEAR))
    maximum = int(parameters.get("year_max", MAX_YEAR))
    required_components = tuple(str(item) for item in parameters.get("required_components", ("month", "year", "day")))
    if (
        minimum > maximum
        or not required_components
        or len(set(required_components)) != len(required_components)
        or any(component not in {"day", "month", "year"} for component in required_components)
    ):
        raise ValueError("time-wheel profile has an invalid calendar contract")
    detent_degrees = int(parameters.get("detent_degrees", 12))
    inertia = dict(parameters.get("inertia") or {"minimum_velocity_rad_s": 0.8, "tick_ms": 90, "maximum_detents": 10})
    if detent_degrees <= 0 or 360 % detent_degrees != 0:
        raise ValueError("time-wheel detents must divide one full turn")
    if not {"minimum_velocity_rad_s", "tick_ms", "maximum_detents"} <= set(inertia):
        raise ValueError("time-wheel inertia profile is incomplete")

    difficulty_suffix = "" if difficulty == 3 else f"|difficulty-{difficulty}"
    digest = hashlib.sha256(f"{seed}|{MECHANIC_ID}{difficulty_suffix}".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    baseline_profile = (
        difficulty == 3
        and minimum == MIN_YEAR
        and maximum == MAX_YEAR
        and required_components == ("month", "year", "day")
        and not bool(parameters.get("force_calendar_clamp", False))
    )
    if baseline_profile:
        # This is the exact pre-control generator path. The controlled L3
        # task adds only its explicit condition identity to the emitted state.
        initial, target, direct_route = _generate_dates(rng)
    else:
        initial, target, direct_route = _generate_controlled_dates(
            rng,
            minimum=minimum,
            maximum=maximum,
            required_components=required_components,
            force_calendar_clamp=bool(parameters.get("force_calendar_clamp", False)),
        )
    task_id = str(task.get("id") or "thirty_year_time_wheel_seed_0001@0.1")
    challenge_id = hashlib.sha256(f"{seed}|thirty-year-time-wheel{difficulty_suffix}".encode("utf-8")).hexdigest()[:12]
    palette = PALETTES[rng.randrange(len(PALETTES))]
    ring_offsets = {component: rng.randrange(0, 360, 6) for component in ("day", "month", "year")}
    variant_lower_bound = len(PALETTES) * 30 * 29 * 12 * 11 * 26 * (60**3)
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language")
        or "Wind all three calendar rings to the target. Stop every moving ring before locking.",
        "submit_label": "LOCK CHRONOMETER",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_puzzles_v1.json",
        "generator": {
            "name": "thirty_year_time_wheel_v1",
            "year_span": 30,
            "variant_count": variant_lower_bound,
            "variant_count_kind": "conservative valid date/ring-offset lower bound",
        },
        "year_range": {"minimum": minimum, "maximum": maximum},
        "initial_date": initial,
        "target_date": target,
        "ring_offsets": ring_offsets,
        "detent_degrees": detent_degrees,
        "inertia": inertia,
        "palette": palette,
        "rules": {
            "day": "Day detents wrap inside the current month's real length.",
            "month_year": "Month and year changes clamp invalid dates, including leap day.",
            "proof": "LOCK requires the exact date, all three necessary rings, and no remaining momentum.",
        },
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "year_range": {"minimum": minimum, "maximum": maximum},
        "initial_date": initial,
        "target_date": target,
        "detent_degrees": detent_degrees,
        "inertia": inertia,
        "direct_recovery_route": direct_route,
        "ring_offsets": ring_offsets,
        "palette": palette,
        "variant_count": variant_lower_bound,
        "variant_count_kind": "conservative valid date/ring-offset lower bound",
    }
    if not baseline_profile:
        public_state["required_components"] = list(required_components)
        ground_truth["required_components"] = list(required_components)
        public_state["rules"]["proof"] = (
            f"LOCK requires the exact date, every required ring ({', '.join(required_components)}), and no remaining momentum."
        )
        public_state["target_presentation"] = str(parameters.get("target_presentation") or "direct")
        ground_truth["target_presentation"] = public_state["target_presentation"]
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
